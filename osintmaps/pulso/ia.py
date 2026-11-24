"""IA local (opcional): un modelo de lenguaje en el propio ordenador, servido por Ollama.

Hace tres cosas, siempre en segundo plano y sin que nada dependa de ella:

- **Lee los textos** (prensa y redes) y afina lo que las reglas de clasificar.py ponen: la categoría,
  la urgencia, si de verdad es de València y el sitio exacto del que habla.
- **Resume cada suceso** en dos o tres frases a partir de sus señales y de lo que se publica.
- **Escribe el parte** de la ciudad: el estado en un párrafo. Cada media hora, o antes si cambia lo que
  cuenta (un suceso, una cifra fuera de lo normal, un partido que empieza); lo escrito que ya no vale no se enseña.

Si Ollama no está instalado o no contesta, todo sigue con las reglas: la sala lo dice y ya.
El modelo recibe solo cifras de conjunto y titulares públicos; se le pide expresamente que no
hable de personas concretas.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time

import requests

from .cruce import RASGOS, TIPOS_SUCESO

log = logging.getLogger("osintmaps.pulso")

OLLAMA = "http://127.0.0.1:11434"
MODELOS_PREFERIDOS = ("qwen3:8b", "qwen3:4b", "qwen2.5:7b", "llama3.1:8b", "gemma3:4b")
CADA_PARTE = 30 * 60          # el parte se reescribe cada media hora aunque nada cambie...
MIN_ENTRE_PARTES = 5 * 60     # ...y antes si cambia lo que cuenta, pero nunca más de uno cada cinco minutos
MAX_TEXTOS_POR_VUELTA = 15
# Tras cinco minutos sin trabajo, Ollama saca el modelo de la memoria de la gráfica: el ordenador queda libre
# para lo demás (vídeo, 3D...) y solo se ocupa unos segundos cada vez que hay algo que leer o resumir.
MANTENER = "5m"
CATEGORIAS_IA = ("emergencia", "accidente", "seguridad", "protesta", "trafico", "transporte", "meteo", "evento", "vivienda",
                 "urbanismo", "sanidad", "medioambiente", "politica", "deporte", "cultura", "economia", "otros")

SISTEMA = ("Eres el analista de una sala de control que vigila la ciudad de València con datos públicos y de conjunto "
           "(tráfico, bicis compartidas, aparcamientos, metro, helicópteros, prensa, publicaciones). Escribes en castellano, "
           "claro y breve, como un parte de servicio. Usas solo los datos que te dan: si algo no está en ellos, no lo afirmas. "
           "Nunca hablas de personas concretas ni intentas identificar a nadie: solo de lo que pasa en la ciudad.")

ESQUEMA_TEXTO = {"type": "object", "properties": {
    "categoria": {"type": "string", "enum": list(CATEGORIAS_IA)},
    "urgencia": {"type": "integer", "minimum": 0, "maximum": 3},
    "de_valencia": {"type": "boolean"},
    "lugar": {"type": "string"}}, "required": ["categoria", "urgencia", "de_valencia", "lugar"]}
ESQUEMA_SUCESO = {"type": "object", "properties": {
    "resumen": {"type": "string"}, "confianza": {"type": "string", "enum": ["alta", "media", "baja"]}}, "required": ["resumen", "confianza"]}
ESQUEMA_PARTE = {"type": "object", "properties": {"parte": {"type": "string"}}, "required": ["parte"]}
PEDIDO_PARTE = (
    "Escribe el parte de la ciudad para ahora mismo, como un parte de radio: como mucho cuatro frases cortas, en prosa y "
    "con tus palabras. Primero, lo que pasa: los sucesos en marcha y lo que está fuera de lo normal; si viene «situacion», "
    "di en su lugar que la ciudad está dentro de lo normal para la hora. Después, lo que hay hoy en la agenda: qué, dónde "
    "y si aún no ha empezado, sigue o ya acabó. Luego, si los hay, la lluvia y los avisos. Al final, en pocas palabras, de "
    "qué se habla.\n"
    "Lo que está fuera de lo normal, dilo como «por encima» o «por debajo de lo normal para la hora», con su cifra y la "
    "normal, sin calificarlo de otra manera (ni moderado, ni alto, ni bajo). De cada suceso, cuenta lo que dice su resumen "
    "sin dar por hecho lo que solo se publica: si habla de lo que dicen las publicaciones o de una causa sin confirmar, "
    "dilo así. No le atribuyas a una fuente lo que es de otra, no añadas causas ni previsiones y no copies los nombres de "
    "los datos ni empieces frases con «La situación:», «La agenda:» o parecidas.\nDatos:\n")


class IA:
    def __init__(self, almacen, cruce, zonas=None, url: str = OLLAMA, modelo: str | None = None, sesion: requests.Session | None = None):
        self.almacen, self.cruce, self.zonas = almacen, cruce, zonas
        self.url, self.modelo_pedido = url.rstrip("/"), modelo
        self.modelo: str | None = None
        self.sesion = sesion or requests.Session()
        self._pendientes: dict[str, float] = {}          # sucesos por resumir -> puntuación cuando se pidió
        self._resumidos: dict[str, float] = {}           # sucesos -> puntuación del último resumen
        self._candado = threading.Lock()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._comprobado: float | None = None            # cuándo se miró por última vez si hay Ollama (None: nunca)
        self.parte: dict | None = None                    # {"texto", "t", "modelo", "firma"}
        self.preparar_parte = None                        # función que da los datos del parte (la pone la sala)
        self.ultimo_error: str | None = None
        self.hechos = {"textos": 0, "sucesos": 0, "partes": 0}

    # ------------------------------------------------------------ Ollama

    def disponible(self) -> bool:
        """¿Hay Ollama con algún modelo útil? Se mira como mucho una vez por minuto."""
        if self._comprobado is not None and time.monotonic() - self._comprobado < 60:
            return self.modelo is not None
        self._comprobado = time.monotonic()
        try:
            nombres = [m.get("name", "") for m in self.sesion.get(f"{self.url}/api/tags", timeout=3).json().get("models", [])]
        except Exception:  # noqa: BLE001
            self.modelo = None
            return False
        if self.modelo_pedido:
            self.modelo = self.modelo_pedido if any(n.startswith(self.modelo_pedido) for n in nombres) else None
        else:
            self.modelo = next((p for p in MODELOS_PREFERIDOS for n in nombres if n.startswith(p)), nombres[0] if nombres else None)
        return self.modelo is not None

    def chat(self, usuario: str, esquema: dict, max_tokens: int = 400) -> dict:
        """Una pregunta al modelo con la respuesta obligada a un esquema JSON."""
        cuerpo = {"model": self.modelo, "stream": False, "format": esquema, "think": False, "keep_alive": MANTENER,
                  "messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}],
                  "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": max_tokens}}
        r = self.sesion.post(f"{self.url}/api/chat", json=cuerpo, timeout=180)
        if r.status_code == 400 and "think" in r.text:
            cuerpo.pop("think")                 # versiones de Ollama que no conocen «think»
            r = self.sesion.post(f"{self.url}/api/chat", json=cuerpo, timeout=180)
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])

    # ------------------------------------------------------------ encargos

    def encargar_resumen(self, ident: str) -> None:
        """El cruce avisa de que un suceso ha cambiado: se resume si es nuevo o si ha crecido bastante."""
        ev = self.cruce.evento(ident) if self.cruce else None
        if not ev:
            return
        with self._candado:
            antes = self._resumidos.get(ident)
            if antes is None or ev["puntuacion"] >= antes * 1.3 or not ev.get("resumen"):
                self._pendientes[ident] = ev["puntuacion"]

    def arrancar(self) -> None:
        if self._hilo:
            return
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, name="pulso-ia", daemon=True)
        self._hilo.start()

    def parar(self) -> None:
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout=5)
        self._hilo = None

    def estado(self) -> dict:
        return {"disponible": self.modelo is not None, "modelo": self.modelo, "url": self.url, "hechos": dict(self.hechos),
                "pendientes": len(self._pendientes), "error": self.ultimo_error}

    def _bucle(self) -> None:
        # Reloj monótono: en un ordenador recién encendido vale poco, y el primer parte no tiene por qué esperar.
        ultimo_parte = mirado = float("-inf")
        while not self._parar.is_set():
            if not self.disponible():
                self._parar.wait(60)
                continue
            try:
                hecho = self._un_suceso()
                if not hecho and self.preparar_parte and time.monotonic() - mirado >= 60:
                    mirado = time.monotonic()
                    datos = self.preparar_parte()
                    if self._toca_parte(datos, mirado - ultimo_parte):
                        self._escribir_parte(datos)
                        ultimo_parte = time.monotonic()
                        hecho = True
                if not hecho:
                    hecho = self._textos() > 0
                self.ultimo_error = None
            except Exception as exc:  # noqa: BLE001  (la IA nunca debe tumbar nada)
                self.ultimo_error = f"{type(exc).__name__}: {exc}"[:200]
                log.debug("IA: %s", self.ultimo_error)
                hecho = False
            self._parar.wait(2 if hecho else 20)

    # ------------------------------------------------------------ tareas

    def _un_suceso(self) -> bool:
        with self._candado:
            if not self._pendientes:
                return False
            ident = max(self._pendientes, key=self._pendientes.get)
            self._pendientes.pop(ident)
        ev = self.cruce.evento(ident)
        if not ev:
            return False
        respuesta = self.chat(describir_suceso(ev, self.zonas), ESQUEMA_SUCESO, 220)
        texto = (respuesta.get("resumen") or "").strip()
        if texto:
            self.cruce.guardar_resumen(ident, texto[:800])
            self._resumidos[ident] = ev["puntuacion"]
            self.hechos["sucesos"] += 1
        return True

    def _toca_parte(self, datos: dict, desde_el_ultimo: float) -> bool:
        """Cada media hora; antes si lo escrito ya no vale (otro suceso, otra cifra fuera de lo normal, el partido que
        empieza...), pero no más de uno cada cinco minutos aunque todo cambie."""
        if desde_el_ultimo > CADA_PARTE:
            return True
        return desde_el_ultimo > MIN_ENTRE_PARTES and (self.parte is None or self.parte.get("firma") != firma_del_parte(datos))

    def _escribir_parte(self, datos: dict | None = None) -> None:
        if datos is None:
            if not self.preparar_parte:
                return
            datos = self.preparar_parte()
        respuesta = self.chat(PEDIDO_PARTE + json.dumps(hechos_del_parte(datos), ensure_ascii=False, indent=1), ESQUEMA_PARTE, 350)
        texto = (respuesta.get("parte") or "").strip()
        if texto:
            self.parte = {"texto": texto[:1500], "t": int(time.time()), "modelo": self.modelo, "firma": firma_del_parte(datos)}
            self.hechos["partes"] += 1

    def _textos(self) -> int:
        """Lee los textos recientes que aún no ha leído y corrige lo que las reglas pusieron. Solo los que cuentan en
        el cruce: las noticias y lo de redes que se ha situado en un barrio (lo demás solo suma en la ciudad entera)."""
        filas = self.almacen._filas(
            "SELECT id, fuente, titulo, texto, lat, barrio FROM items WHERE ia=0 AND t>? AND (fuente='prensa' OR "
            "(fuente IN ('bluesky','mastodon') AND barrio IS NOT NULL)) ORDER BY t DESC LIMIT ?", (int(time.time()) - 3 * 3600, MAX_TEXTOS_POR_VUELTA))
        for ident, fuente, titulo, texto, lat, barrio in filas:
            if self._parar.is_set():
                break
            r = self.chat("Clasifica este texto publicado sobre la ciudad. «lugar» es la calle, plaza o sitio concreto de València del que "
                          "habla (vacío si no nombra ninguno). «de_valencia» es falso si habla de otro municipio o de otro país.\n\n"
                          f"Fuente: {fuente}\nTítulo: {titulo}\nTexto: {(texto or '')[:600]}", ESQUEMA_TEXTO, 120)
            cambios = {"ia": 1, "categoria": r.get("categoria") if r.get("categoria") in CATEGORIAS_IA else None,
                       "urgencia": max(0, min(3, int(r.get("urgencia") or 0)))}
            if r.get("de_valencia") is False:
                cambios.update(categoria="fuera", urgencia=0, barrio=None)
            elif lat is None and (r.get("lugar") or "").strip() and self.zonas is not None and self.zonas.hay:
                sitio = next((l for l in self.zonas.buscar(r["lugar"]) if l.barrio), None)
                if sitio:
                    cambios.update(lat=sitio.lat, lon=sitio.lon, barrio=sitio.barrio, lugar=sitio.nombre)
            cambios = {k: v for k, v in cambios.items() if v is not None or k == "barrio"}
            columnas = ", ".join(f"{k}=?" for k in cambios)
            with self.almacen._candado:
                self.almacen._bd.execute(f"UPDATE items SET {columnas} WHERE id=?", (*cambios.values(), ident))
            self.hechos["textos"] += 1
        return len(filas)


def _hora(t: int | None) -> str:
    return time.strftime("%H:%M", time.localtime(t)) if t else "?"


def _num(v) -> str:
    if v is None:
        return "?"
    return f"{v:.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.1f}".replace(".", ",")


def _frente_a_lo_normal(c: dict) -> str:
    """La comparación delante y la cifra detrás: el modelo se queda con el principio de cada frase."""
    unidad = f" {c['unidad']}" if c.get("unidad") else ""
    nota = f"; {c['nota']}" if c.get("nota") else ""
    sentido = "por encima" if (c.get("z") or 0) > 0 else "por debajo"
    return (f"{c['nombre']} {sentido} de lo normal para la hora: {_num(c.get('valor'))}{unidad}, "
            f"cuando lo normal es {_num(c.get('normal'))}{unidad}{nota}")


def hechos_del_parte(d: dict) -> dict:
    """Los hechos del parte (los de `Sala.datos_del_parte`) tal como se le dan al modelo: solo lo que importa, y cada
    cifra con lo que significa y frente a qué se compara. Un modelo pequeño cuenta todo lo que recibe y lee mal las
    lecturas sueltas: con «tráfico 0 sobre 100» escribía «tráfico muy bajo» (el 0 solo dice que ningún tramo está
    congestionado) y le ponía al metro el retraso de Cercanías. Así que no van las lecturas dentro de lo normal, ni
    cuántas noticias o incidencias de carretera hay (sin saber cuántas son lo normal, no dicen nada), ni los barrios
    más movidos, que cambian cada diez minutos: el parte de reglas, al lado, lo dice todo."""
    activos = d.get("sucesos_activos") or []
    fuera = d.get("ciudad_fuera_de_lo_normal") or []
    h: dict = {"momento": d.get("momento")}
    if not activos and not fuera:
        h["situacion"] = "todo dentro de lo normal para esta hora"
    if activos:
        h["sucesos_en_marcha"] = [{"que": s.get("titulo"), "desde_las": s.get("desde"), **({"resumen": s["resumen"]} if s.get("resumen") else {})}
                                  for s in activos]
    if fuera:
        h["fuera_de_lo_normal"] = [_frente_a_lo_normal(c) for c in fuera]
    if d.get("agenda_hoy"):
        h["agenda_de_hoy"] = [f"{a['que']}: {a['cuando']}" for a in d["agenda_hoy"][:5]]
    if d.get("lluvia"):
        h["lluvia"] = d["lluvia"]
    if d.get("avisos"):
        h["avisos_meteorologicos_en_vigor"] = d["avisos"]
    temas = (d.get("conversacion_2h") or {}).get("temas")
    if temas:
        h["temas_de_los_que_mas_se_habla"] = temas
    return h


def firma_del_parte(d: dict) -> str:
    """Lo que, si cambia, deja viejo un parte ya escrito: los sucesos en marcha, qué cifras están fuera de lo normal,
    la agenda de hoy (también cuando un partido empieza o acaba) y los avisos. Las cifras exactas no cuentan."""
    clave = [sorted(s.get("titulo") or "" for s in d.get("sucesos_activos") or []),
             sorted(c.get("nombre") or "" for c in d.get("ciudad_fuera_de_lo_normal") or []),
             [f"{a.get('que')}|{a.get('cuando')}" for a in d.get("agenda_hoy") or []],
             sorted(d.get("avisos") or [])]
    return hashlib.sha1(json.dumps(clave, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def describir_suceso(ev: dict, zonas=None) -> str:
    """Los hechos de un suceso, en texto, para el modelo."""
    nombre = (lambda b: zonas.nombre(b) or b) if zonas is not None else (lambda b: b)
    ev_senales = (ev.get("evidencias") or {}).get("pico") or []
    senales = []
    for s in ev_senales[:8]:
        info = RASGOS.get(s.get("rasgo"), {})
        senales.append(f"- {nombre(s.get('barrio'))}: {info.get('nombre', s.get('rasgo'))} {s.get('valor')} {info.get('unidad', '')} "
                       f"(lo normal a esta hora: {s.get('normal')}; z={s.get('z')})")
    causa = ev.get("causa") or {}
    candidatas = [f"- {c.get('tipo')}: {c.get('titulo')} (peso {c.get('peso')})" for c in (causa.get("candidatas") or [])[:4]]
    textos = [f"- [{tx.get('fuente')} {_hora(tx.get('t'))}] {tx.get('titulo')}" for tx in (causa.get("textos") or [])[:6]]
    return (f"Resume este suceso en 2 o 3 frases: qué se ha detectado, dónde, desde cuándo y la causa más probable "
            f"(o que no se conoce). Tipo: {TIPOS_SUCESO.get(ev.get('tipo'), ev.get('tipo'))}. "
            f"Barrios: {', '.join(nombre(b) for b in ev.get('barrios', [])[:6])}. Desde las {_hora(ev.get('inicio'))} hasta las "
            f"{_hora(ev.get('fin'))} ({ev.get('estado')}).\nSeñales en el momento más fuerte:\n" + "\n".join(senales or ["- (ninguna)"])
            + "\nPosibles causas:\n" + "\n".join(candidatas or ["- ninguna"]) + "\nLo que se ha publicado de esos barrios:\n"
            + "\n".join(textos or ["- nada"]))
