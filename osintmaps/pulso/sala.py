"""La sala de control: pone en marcha el cruce y contesta a lo que pide su pantalla.

Al arrancar el programa:

1. Baja (si falta o ha caducado) el mapa de barrios y calles del Ajuntament y monta el
   nomenclátor. A partir de ahí, todo lo que entra se sitúa en su barrio.
2. Sitúa lo que entró mientras no había mapa y calcula el cruce del histórico que falte
   (los rasgos de cada barrio y lo normal; los sucesos, de las últimas 24 horas).
3. Cada diez minutos da un paso del cruce. En otro hilo baja el resto de capas (patrimonio,
   quejas, accidentes...) para las fichas, y si hay IA local la pone a trabajar.

Lo que contesta, en /vivo/sala/...:

    estado      todo lo de la pantalla principal: barrios, sucesos, ciudad, agenda, textos, parte
    barrios     el mapa de barrios (GeoJSON) con su contexto
    evento      un suceso entero: señales a lo largo del tiempo, causa, textos, helicópteros
    barrio      la ficha de un barrio
    lugar       la ficha de un punto (un inmueble): ?lat=&lon=
    items       buscar en lo publicado: ?q=&barrio=&fuente=&desde=&hasta=
    comparar    un rasgo en dos tipos de día o dos fechas: ?rasgo=&a=L&b=S
    movilidad   bicis que llegan y salen de cada barrio: ?horas=
    flujos      viajes entre distritos hora a hora en un día tipo (MITMA): ?dia=AAAA-MM-DD
    cielo       helicópteros en el aire y su recorrido del último cuarto de hora

En la web publicada no hay programa detrás: el ordenador sube cada cuarto de hora sala.json (lo
mismo que «estado», sin el texto de las publicaciones de redes, que se queda en el ordenador),
sala-barrios.json y sala-perfiles.json.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from ..red import nueva_sesion
from . import contexto, movilidad as mitma
from .catalogo import INDICADORES
from .cruce import BIN, CIUDAD, FAMILIAS, RASGOS, TIPOS_SUCESO, Cruce, franja
from .fichas import Fichas
from .ia import CADA_PARTE, IA, firma_del_parte
from .zonas import Zonas

log = logging.getLogger("osintmaps.pulso")

BASICO = ("barrios", "distritos", "calles", "metro", "monumentos", "recursos_turisticos")
DIAS_RECONSTRUIR = 21
REDES = ("bluesky", "mastodon")
RASGOS_PERFIL = ("trafico", "aforo", "bici_ocupacion", "parking", "metro", "social", "bici_llegadas", "bici_salidas")
DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
FICHEROS_WEB = ("sala.json", "sala-barrios.json", "sala-perfiles.json", "sala-movilidad.json")


def nivel_de_ciudad(n: float) -> tuple[str, str]:
    if n >= 8:
        return "muy alta", "Actividad muy por encima de lo normal"
    if n >= 5:
        return "alta", "Actividad claramente por encima de lo normal"
    if n >= 3:
        return "atencion", "Algo fuera de lo normal"
    return "normal", "Dentro de lo normal"


class Sala:
    def __init__(self, pulso, recoger: bool = True, ia: bool = True):
        self.pulso = pulso
        self.ia_permitida = ia
        self.almacen = pulso.almacen
        self.datos = Path(pulso.carpeta_datos)
        self.recoger = recoger
        self.zonas: Zonas | None = None
        self.cruce: Cruce | None = None
        self.fichas: Fichas | None = None
        self.ia: IA | None = None
        self.fase = "esperando el mapa de barrios"
        self.contexto: dict[str, str] = {}
        self._parar = threading.Event()
        self._hilos: list[threading.Thread] = []
        self._cache: dict[str, tuple[float, object]] = {}
        self._candado = threading.Lock()
        self._cargar_zonas()

    # ------------------------------------------------------------ en marcha

    def _cargar_zonas(self) -> bool:
        try:
            zonas = Zonas(self.datos)
        except Exception:  # noqa: BLE001
            log.warning("Sala: no se ha podido leer el mapa de barrios", exc_info=True)
            return False
        if not zonas.hay:
            return False
        self.zonas = zonas
        self.cruce = Cruce(self.almacen, zonas, ia=self.ia)
        self.fichas = Fichas(self.datos, zonas)
        if getattr(self.pulso, "recolector", None) is not None:
            self.pulso.recolector.zonas = zonas
        if self.ia is not None:
            self.ia.cruce, self.ia.zonas = self.cruce, zonas
        self._cache.clear()
        return True

    def arrancar(self) -> None:
        if self._hilos or not self.recoger:
            return
        self._parar.clear()
        self._hilos = [threading.Thread(target=self._vida, name="pulso-sala", daemon=True)]
        self._hilos[0].start()

    def parar(self) -> None:
        self._parar.set()
        if self.ia:
            self.ia.parar()
        for h in self._hilos:
            h.join(timeout=5)
        self._hilos = []

    def _vida(self) -> None:
        sesion = nueva_sesion()
        while not self._parar.is_set():
            self.fase = "bajando el mapa de barrios y calles"
            try:
                hecho = contexto.actualizar(self.datos, sesion, solo=BASICO)
                self.contexto.update(hecho)
                if hecho or self.zonas is None:
                    self._cargar_zonas()
            except Exception:  # noqa: BLE001
                log.warning("Sala: fallo al bajar el contexto", exc_info=True)
            if self.zonas is not None:
                break
            self.fase = "sin mapa de barrios (se reintenta en 10 min)"
            self._parar.wait(600)
        if self._parar.is_set():
            return
        self.fase = "situando lo que entró sin mapa"
        self.situar_pendientes()
        self.fase = "calculando el histórico"
        ahora = int(time.time())
        primera = self.almacen._filas("SELECT MIN(t) FROM tomas WHERE ok=1")[0][0]
        desde = max(primera or ahora, ahora - DIAS_RECONSTRUIR * 86400)
        try:
            n = self.cruce.reconstruir(desde, ahora // BIN * BIN, sucesos_desde=ahora - 24 * 3600)
            log.info("Sala: %d intervalos del histórico calculados", n)
        except Exception:  # noqa: BLE001
            log.warning("Sala: fallo al reconstruir el histórico", exc_info=True)
        if self.ia_permitida:
            self.ia = IA(self.almacen, self.cruce, self.zonas)
            self.ia.preparar_parte = self.datos_del_parte
            self.cruce.ia = self.ia
            self.ia.arrancar()
        resto = threading.Thread(target=self._contexto_resto, name="pulso-contexto", daemon=True)
        self._hilos.append(resto)
        resto.start()
        self.fase = "en marcha"
        ultima_situacion = time.monotonic()
        while not self._parar.is_set():
            # Cada diez minutos, 40 s después del final del intervalo: que hayan entrado las tomas.
            espera = BIN - (time.time() % BIN) + 40
            if self._parar.wait(espera):
                return
            try:
                self.cruce.paso(int(time.time()) - 40)
                self._cache.clear()
                if time.monotonic() - ultima_situacion > 1800:
                    self.situar_pendientes()
                    ultima_situacion = time.monotonic()
            except Exception:  # noqa: BLE001
                log.warning("Sala: fallo en un paso del cruce", exc_info=True)

    def _contexto_resto(self) -> None:
        """Las capas de las fichas: sin prisa, y una vez al día se mira si alguna ha caducado."""
        while not self._parar.is_set():
            try:
                hecho = contexto.actualizar(self.datos, nueva_sesion())
                self.contexto.update(hecho)
                if hecho:
                    self.fichas.olvidar()
                n = self.fichas.situar_accidentes()
                if n > 0:
                    log.info("Sala: %d accidentes situados", n)
                self.fichas.todos_los_barrios()
                # Los viajes entre distritos del MITMA: se bajan una vez (unos días sueltos) y no cambian.
                hecho = mitma.importar(self.datos, nueva_sesion())
                if any(not v.startswith("ya") for v in hecho.values()):
                    log.info("Sala: movilidad del MITMA %s", hecho)
                    self._cache.pop("mitma", None)
            except Exception:  # noqa: BLE001
                log.warning("Sala: fallo al preparar las fichas", exc_info=True)
            if self._parar.wait(86400):
                return

    def situar_pendientes(self, horas: int = 72) -> int:
        """Lo que entró sin barrio (porque aún no había mapa): textos, agenda y puntos sin posición."""
        if self.zonas is None:
            return 0
        z, n = self.zonas, 0
        desde = int(time.time()) - horas * 3600
        cambios = []
        for ident, titulo, texto, lat, lon in self.almacen._filas(
                "SELECT id, titulo, texto, lat, lon FROM items WHERE barrio IS NULL AND t>? AND fuente IN ('prensa','bluesky','mastodon','dgt') "
                "AND (categoria IS NULL OR categoria!='fuera')", (desde,)):
            if lat is not None:
                b = z.barrio_de(lat, lon)
                if b:
                    cambios.append((lat, lon, b, None, ident))
                continue
            sitio = next((l for l in z.buscar(f"{titulo}. {texto or ''}") if l.barrio), None)
            if sitio:
                cambios.append((sitio.lat, sitio.lon, sitio.barrio, sitio.nombre, ident))
        with self.almacen._candado:
            self.almacen._bd.executemany("UPDATE items SET lat=?, lon=?, barrio=?, lugar=COALESCE(?, lugar) WHERE id=?", cambios)
            n += len(cambios)
            filas = self.almacen._bd.execute("SELECT id, lat, lon FROM agenda WHERE barrio IS NULL AND lat IS NOT NULL").fetchall()
            self.almacen._bd.executemany("UPDATE agenda SET barrio=? WHERE id=?",
                                         [(b, i) for i, la, lo in filas if (b := z.barrio_de(la, lo))])
            puntos = self.almacen._bd.execute("SELECT serie, id, nombre FROM puntos WHERE lat IS NULL AND nombre!=''").fetchall()
        situados = []
        for serie, ident, nombre in puntos:
            sitio = next(iter(z.buscar(nombre)), None)
            if sitio:
                situados.append((sitio.lat, sitio.lon, serie, ident))
        with self.almacen._candado:
            self.almacen._bd.executemany("UPDATE puntos SET lat=?, lon=? WHERE serie=? AND id=?", situados)
        return n + len(situados)

    # ------------------------------------------------------------ utilidades

    def _guardado(self, clave: str, vida: float, hacer):
        with self._candado:
            hecho = self._cache.get(clave)
        if hecho and time.monotonic() - hecho[0] < vida:
            return hecho[1]
        valor = hacer()
        with self._candado:
            self._cache[clave] = (time.monotonic(), valor)
        return valor

    def _nombre(self, b: str | None) -> str:
        if b == CIUDAD:
            return "València"
        return (self.zonas.nombre(b) if self.zonas else "") or (b or "")

    @staticmethod
    def _suceso_corto(ev: dict) -> dict:
        causa = ev.get("causa") or {}
        return {k: ev.get(k) for k in ("id", "tipo", "estado", "titulo", "inicio", "fin", "pico", "puntuacion", "lat", "lon", "barrios", "resumen")} | {
            "ahora": (ev.get("evidencias") or {}).get("ahora", []), "explicado": bool(causa.get("explicado")),
            "causa": causa.get("probable"), "tipo_nombre": TIPOS_SUCESO.get(ev.get("tipo"), ev.get("tipo"))}

    # ------------------------------------------------------------ estado

    def estado(self, publico: bool = False) -> dict:
        return self._guardado(f"estado{publico}", 8, lambda: self._estado(publico))

    def _estado(self, publico: bool) -> dict:
        ahora = int(time.time())
        e = self.cruce.estado if self.cruce else {}
        sucesos = [self._suceso_corto(ev) for ev in self.cruce.eventos(ahora - 24 * 3600, ahora + 1, 60)] if self.cruce else []
        activos = [s for s in sucesos if s["estado"] == "activo"]
        barrios = {}
        for b, x in (e.get("barrios") or {}).items():
            barrios[b] = {"nivel": x["nivel"], "tipos": x["tipos"], "familias": x["familias"], "senales": x["senales"][:3],
                          "valores": x["valores"], "normal": x["normal"]}
        # Alto o muy alto solo si hay sucesos de verdad (varias fuentes a la vez); sin ellos, una señal suelta de
        # la ciudad entera se queda, como mucho, en «atención».
        nivel = max([min(barrios.get(CIUDAD, {}).get("nivel", 0), 4.9)] + [s["puntuacion"] or 0 for s in activos])
        clase, frase = nivel_de_ciudad(nivel)
        return {
            "generado": ahora, "publico": publico, "hay": self.zonas is not None, "fase": self.fase, "t": e.get("t"),
            "aprendiendo": e.get("aprendiendo"), "nivel": {"valor": round(nivel, 1), "clase": clase, "frase": frase},
            "barrios": barrios, "desplazamiento": e.get("desplazamiento", {}),
            "sucesos": sucesos, "ciudad": self._ciudad(ahora), "agenda": self._agenda(ahora),
            "feed": self._feed(ahora, publico), "avisos": self._avisos(ahora), "conversacion": self._conversacion(ahora),
            "fuentes": self._fuentes(), "parte": self.parte(),
            "ia": self.ia.estado() if self.ia else {"disponible": False},
            "rasgos": {r: {"nombre": i["nombre"], "unidad": i["unidad"], "tipo": i["tipo"]} for r, i in RASGOS.items()},
            "familias": FAMILIAS, "tipos": TIPOS_SUCESO,
        }

    def _ciudad(self, ahora: int) -> list[dict]:
        """Las cifras de toda la ciudad: lo último de cada indicador y cómo está frente a lo normal."""
        ultimos: dict[str, tuple[int, float]] = {}
        for clave, t, v in self.almacen._filas("SELECT clave, t, v FROM indicadores WHERE t>? ORDER BY t", (ahora - 2 * 3600,)):
            ultimos[clave] = (t, v)
        comparadas = {c["clave"]: c for c in (getattr(self.pulso.recolector, "comparaciones", None) or [])} if getattr(self.pulso, "recolector", None) else {}
        salida = []
        for clave, (t, v) in ultimos.items():
            info = INDICADORES.get(clave, {})
            c = comparadas.get(clave, {})
            salida.append({"clave": clave, "nombre": info.get("nombre", clave), "unidad": info.get("unidad", ""), "valor": round(v, 1), "t": t,
                           "normal": c.get("normal"), "z": c.get("z"), "fuente": info.get("fuente"), "nota": info.get("nota")})
        return salida

    def _agenda(self, ahora: int) -> dict:
        hoy = datetime.fromtimestamp(ahora).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        filas = self.almacen._filas("SELECT id, tipo, titulo, desde, hasta, lat, lon, barrio, fuente, url FROM agenda WHERE hasta>=? AND desde<=?",
                                    (ahora - 3600, ahora + 2 * 86400))
        destacado, planificado = [], []
        cuenta = Counter()
        for ident, tipo, titulo, a, b, lat, lon, barrio, fuente, url in filas:
            base = tipo.split(":")[0]
            fila = {"id": ident, "tipo": base, "subtipo": tipo, "titulo": titulo, "desde": a, "hasta": b, "lat": lat, "lon": lon,
                    "barrio": barrio, "fuente": fuente, "url": url}
            if base in ("partido", "festejo", "festivo", "fiesta"):
                if base in ("festivo", "fiesta") and b < hoy:
                    continue
                destacado.append(fila)
            elif a <= ahora:
                cuenta[base] += 1
                if lat is not None:
                    planificado.append(fila)
        destacado.sort(key=lambda f: f["desde"])
        return {"destacado": destacado[:30], "planificado": planificado[:800], "cuenta": dict(cuenta)}

    def _feed(self, ahora: int, publico: bool) -> list[dict]:
        """Lo último que se ha publicado o avisado. En la web, sin las publicaciones de redes (solo se cuentan)."""
        filtro = " AND fuente NOT IN ('bluesky','mastodon')" if publico else ""
        salida = []
        for ident, fuente, t, titulo, url, lat, lon, barrio, lugar, cat, urg, extra, visto in self.almacen._filas(
                "SELECT id, fuente, t, titulo, url, lat, lon, barrio, lugar, categoria, urgencia, extra, visto FROM items WHERE t>? "
                f"AND (categoria IS NULL OR categoria!='fuera'){filtro} ORDER BY t DESC LIMIT 120", (ahora - 24 * 3600,)):
            extra = json.loads(extra) if extra else {}
            salida.append({"id": ident, "fuente": fuente, "t": t, "titulo": titulo, "url": url, "lat": lat, "lon": lon, "barrio": barrio,
                           "lugar": lugar, "categoria": cat, "urgencia": urg, "medio": extra.get("medio"),
                           "activo": fuente in ("dgt", "renfe") and (visto or 0) > ahora - 1200})
        return salida

    def _avisos(self, ahora: int) -> list[dict]:
        """Lo que sigue activo: incidencias de la DGT y Renfe vistas en los últimos 20 min y avisos meteorológicos en vigor."""
        salida = []
        for ident, fuente, t, titulo, url, lat, lon, barrio, cat, urg, extra in self.almacen._filas(
                "SELECT id, fuente, t, titulo, url, lat, lon, barrio, categoria, urgencia, extra FROM items WHERE "
                "(fuente IN ('dgt','renfe') AND visto>?) OR (fuente='meteoalarm' AND visto>?) ORDER BY urgencia DESC, t DESC LIMIT 150",
                (ahora - 1200, ahora - 3 * 3600)):
            extra = json.loads(extra) if extra else {}
            if fuente == "meteoalarm" and (extra.get("hasta") or ahora) < ahora:
                continue
            salida.append({"id": ident, "fuente": fuente, "t": t, "titulo": titulo, "url": url, "lat": lat, "lon": lon, "barrio": barrio,
                           "categoria": cat, "urgencia": urg, "tipo": extra.get("tipo"), "hasta": extra.get("hasta")})
        return salida

    def _conversacion(self, ahora: int) -> dict:
        """De qué se habla: en las últimas dos horas, cuánto y de qué en prensa y en redes."""
        cuenta = {"prensa": Counter(), "redes": Counter()}
        for fuente, cat in self.almacen._filas("SELECT fuente, categoria FROM items WHERE t>? AND fuente IN ('prensa','bluesky','mastodon') "
                                               "AND (categoria IS NULL OR categoria!='fuera')", (ahora - 7200,)):
            cuenta["redes" if fuente in REDES else "prensa"][cat or "otros"] += 1
        social = (self.cruce.estado.get("barrios") or {}) if self.cruce else {}
        barrios = sorted(((b, x["valores"].get("social", 0)) for b, x in social.items() if b != CIUDAD and x["valores"].get("social")),
                         key=lambda x: -x[1])[:8]
        return {"noticias": sum(cuenta["prensa"].values()), "publicaciones": sum(cuenta["redes"].values()),
                "temas_prensa": cuenta["prensa"].most_common(6), "temas_redes": cuenta["redes"].most_common(6),
                "barrios": [{"barrio": b, "nombre": self._nombre(b), "n": n} for b, n in barrios]}

    def _fuentes(self) -> list[dict]:
        try:
            fuentes = self.pulso.estado().get("fuentes", [])
        except Exception:  # noqa: BLE001
            return []
        return [{k: f.get(k) for k in ("id", "nombre", "origen", "ultima", "ok", "fallos_seguidos", "error", "cada")} for f in fuentes]

    # ------------------------------------------------------------ parte

    def datos_del_parte(self) -> dict:
        """Los hechos del parte: los mismos para las reglas y para la IA."""
        ahora = int(time.time())
        d = datetime.fromtimestamp(ahora)
        sucesos = [self._suceso_corto(ev) for ev in self.cruce.eventos(ahora - 3600, ahora + 1, 20)] if self.cruce else []
        activos = sorted((s for s in sucesos if s["estado"] == "activo"), key=lambda s: -(s["puntuacion"] or 0))
        lecturas = self._ciudad(ahora)
        fuera = sorted((c for c in lecturas if c.get("z") is not None and abs(c["z"]) >= 2), key=lambda c: -abs(c["z"]))[:6]
        agenda = self._agenda(ahora)
        hoy_fin = d.replace(hour=23, minute=59).timestamp()
        de_hoy = [a for a in agenda["destacado"] if a["desde"] <= hoy_fin]
        barrios = (self.cruce.estado.get("barrios") or {}) if self.cruce else {}
        destacados = sorted(((b, x) for b, x in barrios.items() if b != CIUDAD and x["nivel"] >= 2.5), key=lambda x: -x[1]["nivel"])[:5]
        conversacion = self._conversacion(ahora)
        return {
            "momento": f"{DIAS_SEMANA[d.weekday()]} {d.day} de {MESES[d.month - 1]}, {d:%H:%M}",
            "sucesos_activos": [{"titulo": s["titulo"], "desde": time.strftime("%H:%M", time.localtime(s["inicio"])), "puntuacion": s["puntuacion"],
                                 "resumen": s.get("resumen")} for s in activos[:5]],
            "ciudad_fuera_de_lo_normal": [{"nombre": c["nombre"], "valor": c["valor"], "unidad": c["unidad"], "normal": c["normal"], "z": c["z"],
                                           "nota": c["nota"]} for c in fuera],
            "lluvia": _lluvia(lecturas),
            "hoy": [f"{time.strftime('%H:%M', time.localtime(a['desde'])) if a['tipo'] == 'partido' else ''} {a['titulo']}".strip() for a in de_hoy],
            "agenda_hoy": [{"que": a["titulo"], "cuando": _cuando(a, ahora)} for a in de_hoy],
            "obras_y_ocupaciones_activas": sum(agenda["cuenta"].values()),
            "avisos": [a["titulo"] for a in self._avisos(ahora) if a["fuente"] == "meteoalarm"][:3],
            "incidencias_trafico": [a["titulo"] for a in self._avisos(ahora) if a["fuente"] == "dgt" and (a["urgencia"] or 0) >= 1][:5],
            "barrios_destacados": [{"barrio": self._nombre(b), "nivel": x["nivel"],
                                    "senal": f"{RASGOS[x['senales'][0]['rasgo']]['nombre']} {x['senales'][0]['valor']} (normal {x['senales'][0]['normal']})"
                                    if x["senales"] else ""} for b, x in destacados],
            "conversacion_2h": {"noticias": conversacion["noticias"], "publicaciones": conversacion["publicaciones"],
                                "temas": [t for t, _ in conversacion["temas_prensa"][:3]]},
        }

    def parte(self) -> dict:
        def hacer():
            if self.cruce is None:
                return {"texto": "Preparando el mapa de la ciudad…", "fuente": "reglas", "t": int(time.time())}
            d = self.datos_del_parte()
            texto = parte_por_reglas(d)
            salida = {"texto": texto, "fuente": "reglas", "t": int(time.time()), "momento": d["momento"]}
            # El de la IA se enseña solo si se escribió para la situación de ahora: con otro suceso en marcha, otra cifra
            # fuera de lo normal o el partido ya empezado, queda el de reglas hasta que la IA escriba el nuevo.
            escrito = self.ia.parte if self.ia else None
            if escrito and escrito.get("firma") == firma_del_parte(d) and time.time() - escrito["t"] < 2 * CADA_PARTE:
                salida["ia"] = {k: escrito[k] for k in ("texto", "t", "modelo")}
            return salida
        return self._guardado("parte", 60, hacer)

    # ------------------------------------------------------------ fichas

    def barrios_geojson(self) -> dict:
        def hacer():
            if self.zonas is None:
                return {"type": "FeatureCollection", "features": []}
            geo = self.zonas.geojson_barrios()
            contexto_barrios = self.fichas.todos_los_barrios() if self.fichas else {}
            for f in geo["features"]:
                c = contexto_barrios.get(f["properties"]["codigo"], {})
                v = c.get("vulnerabilidad") or {}
                b = self.zonas.barrios.get(f["properties"]["codigo"], {})
                f["properties"].update({"lat": b.get("lat"), "lon": b.get("lon"), "vulnerabilidad": v.get("ind_global"), "vulnerabilidad_texto": v.get("vul_global"),
                                        "quejas": (c.get("quejas") or {}).get("total"), "accidentes": (c.get("accidentes") or {}).get("total")})
            return geo
        return self._guardado("barrios", 3600, hacer)

    def evento(self, ident: str) -> dict:
        ev = self.cruce.evento(ident) if self.cruce else None
        if not ev:
            raise ValueError("no existe ese suceso")
        desde, hasta = ev["inicio"] - 2 * 3600, min(ev["fin"] + 3600, int(time.time()))
        barrios = [b for b in (ev["evidencias"].get("ahora") or ev["barrios"]) if b != CIUDAD][:4] or [CIUDAD]
        rasgos = list(dict.fromkeys(s["rasgo"] for s in (ev["evidencias"].get("pico") or []) + (ev["evidencias"].get("ultimo") or [])))[:5]
        series = {}
        for r in rasgos:
            por_barrio = self.cruce.serie(r, barrios, desde, hasta)
            normales = {}
            for b in barrios:
                # Lo normal, media hora a media hora (la mediana de las muestras de esa franja).
                puntos = []
                for fin in range((desde // 1800 + 1) * 1800, hasta + 1800, 1800):
                    m = self.cruce.muestras(r, b, fin)
                    if m:
                        puntos.append((fin, round(sorted(m)[len(m) // 2], 2)))
                normales[b] = puntos
            series[r] = {"valores": por_barrio, "normal": normales}
        nivel = self.cruce.serie("nivel", barrios, desde, hasta)
        helis = {}
        if CIUDAD not in barrios:
            area = set(ev["barrios"]) | {v for b in ev["barrios"] for v in self.zonas.vecinos.get(b, ())}
            for ident_h, obj in self.almacen.rastros("helicopteros", ev["inicio"] - 1800, ev["fin"] + 600, 15).items():
                # Un helicóptero que ha pasado por la zona: se enseña su recorrido de ese rato.
                if any(self.zonas.barrio_de(x[1], x[2]) in area for x in obj["p"]):
                    helis[ident_h] = {"nombre": obj["nombre"], "p": obj["p"]}
        return {"suceso": ev, "nombres": {b: self._nombre(b) for b in set(ev["barrios"]) | set(barrios)}, "desde": desde, "hasta": hasta,
                "series": series, "nivel": nivel, "helicopteros": helis,
                "rasgos": {r: {"nombre": RASGOS[r]["nombre"], "unidad": RASGOS[r]["unidad"]} for r in rasgos}}

    def barrio(self, codigo: str) -> dict:
        if self.zonas is None or codigo not in self.zonas.barrios:
            raise ValueError("no existe ese barrio")
        ahora = int(time.time())
        info = self.zonas.barrios[codigo]
        actual = ((self.cruce.estado.get("barrios") or {}).get(codigo)) if self.cruce else None
        sucesos = [self._suceso_corto(ev) for ev in (self._eventos_de_barrio(codigo, ahora - 30 * 86400) if self.cruce else [])]
        items = [dict(zip(("id", "fuente", "t", "titulo", "url", "categoria", "urgencia"), f)) for f in self.almacen._filas(
            "SELECT id, fuente, t, titulo, url, categoria, urgencia FROM items WHERE barrio=? AND t>? AND (categoria IS NULL OR categoria!='fuera') "
            "ORDER BY t DESC LIMIT 60", (codigo, ahora - 7 * 86400))]
        agenda = [dict(zip(("id", "tipo", "titulo", "desde", "hasta", "lat", "lon"), f)) for f in self.almacen._filas(
            "SELECT id, tipo, titulo, desde, hasta, lat, lon FROM agenda WHERE barrio=? AND hasta>=? ORDER BY desde LIMIT 80", (codigo, ahora))]
        return {"codigo": codigo, "nombre": info["nombre"], "distrito": self.zonas.distritos.get(info.get("distrito"), ""),
                "vecinos": [{"codigo": v, "nombre": self._nombre(v)} for v in sorted(self.zonas.vecinos.get(codigo, ()))],
                "actual": actual, "nivel_24h": self.cruce.serie("nivel", [codigo], ahora - 86400, ahora).get(codigo, []) if self.cruce else [],
                "sucesos": sucesos, "items": items, "agenda": agenda, "contexto": self.fichas.barrio(codigo) if self.fichas else {},
                "rasgos": {r: {"nombre": i["nombre"], "unidad": i["unidad"]} for r, i in RASGOS.items()}}

    def _eventos_de_barrio(self, codigo: str, desde: int) -> list[dict]:
        filas = self.almacen._filas("SELECT * FROM eventos WHERE fin>=? AND barrios LIKE ? ORDER BY inicio DESC LIMIT 60", (desde, f'%"{codigo}"%'))
        return [self.cruce._fila_evento(f) for f in filas]

    def lugar(self, lat: float, lon: float) -> dict:
        if self.fichas is None:
            raise ValueError("aún no hay mapa de la ciudad")
        if not (39.2 < lat < 39.7 and -0.6 < lon < -0.2):
            raise ValueError("fuera de València")
        ficha = self.fichas.punto(lat, lon)
        ahora = int(time.time())
        d = 150 / 111_000
        ficha["textos"] = [dict(zip(("id", "fuente", "t", "titulo", "url", "categoria", "lugar"), f)) for f in self.almacen._filas(
            "SELECT id, fuente, t, titulo, url, categoria, lugar FROM items WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND t>? "
            "AND fuente!='bluesky' AND fuente!='mastodon' ORDER BY t DESC LIMIT 30", (lat - d, lat + d, lon - d * 1.3, lon + d * 1.3, ahora - 180 * 86400))]
        d = 60 / 111_000
        ficha["agenda"] = [dict(zip(("id", "tipo", "titulo", "desde", "hasta"), f)) for f in self.almacen._filas(
            "SELECT id, tipo, titulo, desde, hasta FROM agenda WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND tipo NOT LIKE 'partido%' "
            "ORDER BY desde DESC LIMIT 30", (lat - d, lat + d, lon - d * 1.3, lon + d * 1.3))]
        if ficha.get("barrio") and self.cruce:
            ficha["sucesos"] = [self._suceso_corto(ev) for ev in self._eventos_de_barrio(ficha["barrio"], ahora - 90 * 86400)[:10]]
        return ficha

    def items(self, q: dict[str, list[str]]) -> dict:
        ahora = int(time.time())
        hasta = _entero(q, "hasta", ahora)
        desde = _entero(q, "desde", hasta - 7 * 86400)
        condiciones, valores = ["t>?", "t<=?", "(categoria IS NULL OR categoria!='fuera')"], [desde, hasta]
        for campo in ("barrio", "fuente", "categoria"):
            v = (q.get(campo) or [""])[0]
            if v:
                condiciones.append(f"{campo}=?")
                valores.append(v[:40])
        texto = (q.get("q") or [""])[0].strip()
        if texto:
            condiciones.append("(titulo LIKE ? OR texto LIKE ?)")
            valores += [f"%{texto[:60]}%"] * 2
        filas = self.almacen._filas(f"SELECT id, fuente, t, titulo, texto, url, lat, lon, barrio, lugar, categoria, urgencia FROM items WHERE "
                                    f"{' AND '.join(condiciones)} ORDER BY t DESC LIMIT 300", tuple(valores))
        claves = ("id", "fuente", "t", "titulo", "texto", "url", "lat", "lon", "barrio", "lugar", "categoria", "urgencia")
        return {"desde": desde, "hasta": hasta, "items": [dict(zip(claves, f)) for f in filas]}

    def comparar(self, q: dict[str, list[str]]) -> dict:
        if self.cruce is None:
            raise ValueError("aún no hay cruce")
        rasgo = (q.get("rasgo") or ["bici_ocupacion"])[0]
        if rasgo not in RASGOS and rasgo != "nivel":
            raise ValueError("rasgo desconocido")
        lados = {}
        for lado, por_defecto in (("a", "L"), ("b", "S")):
            v = (q.get(lado) or [por_defecto])[0]
            if v in ("L", "S", "D"):
                lados[lado] = {"clave": v, "nombre": {"L": "laborable", "S": "sábado", "D": "domingo o festivo"}[v], "valores": self.cruce.perfil(rasgo, v)}
            else:
                try:
                    datetime.fromisoformat(v)
                except ValueError as exc:
                    raise ValueError("fecha no válida") from exc
                lados[lado] = {"clave": v, "nombre": v, "valores": self.cruce.perfil_de_dia(rasgo, v)}
        info = RASGOS.get(rasgo, {"nombre": "Nivel", "unidad": ""})
        return {"rasgo": rasgo, "nombre": info["nombre"], "unidad": info["unidad"], **lados, "dias": self.cruce.dias_con_datos()}

    def movilidad(self, q: dict[str, list[str]]) -> dict:
        """Bicis que llegan y salen de cada barrio en las últimas horas, y la curva del día frente a lo normal."""
        if self.cruce is None:
            raise ValueError("aún no hay cruce")
        horas = max(1, min(24, _entero(q, "horas", 1)))
        ahora = int(time.time())
        balance = defaultdict(lambda: {"llegan": 0.0, "salen": 0.0})
        for rasgo, b, v in self.almacen._filas("SELECT rasgo, barrio, SUM(v) FROM rasgos WHERE rasgo IN ('bici_llegadas','bici_salidas') AND t>? "
                                               "GROUP BY rasgo, barrio", (ahora - horas * 3600,)):
            balance[b]["llegan" if rasgo == "bici_llegadas" else "salen"] = round(v or 0)
        hoy = datetime.fromtimestamp(ahora).date().isoformat()
        tipo = "L" if datetime.fromtimestamp(ahora).weekday() < 5 else ("S" if datetime.fromtimestamp(ahora).weekday() == 5 else "D")
        return {"horas": horas, "barrios": {b: dict(v, neto=v["llegan"] - v["salen"], nombre=self._nombre(b)) for b, v in balance.items()},
                "hoy": {r: self.cruce.perfil_de_dia(r, hoy).get(CIUDAD) for r in ("bici_llegadas", "bici_salidas", "trafico", "metro")},
                "normal": {r: self.cruce.perfil(r, tipo).get(CIUDAD) for r in ("bici_llegadas", "bici_salidas", "trafico", "metro")},
                "franja": franja(ahora) % 48}

    def cielo(self) -> dict:
        """Los helicópteros en el aire ahora (vistos hace menos de dos minutos) y su recorrido del último cuarto
        de hora. Sale de lo que ya recoge el pulso: no se pregunta a nadie más."""
        ahora = int(time.time())
        helis = self.almacen.rastros("helicopteros", ahora - 900, ahora)
        return {"t": ahora, "helicopteros": {k: v for k, v in helis.items() if v["p"] and v["p"][-1][0] > ahora - 120}}

    def _centros_distritos(self) -> dict[str, tuple[float, float]]:
        grupos: dict[str, list] = defaultdict(list)
        for b in (self.zonas.barrios.values() if self.zonas else []):
            grupos[b.get("distrito", "")].append((b["lat"], b["lon"]))
        return {d: (round(sum(p[0] for p in ps) / len(ps), 5), round(sum(p[1] for p in ps) / len(ps), 5)) for d, ps in grupos.items() if ps}

    def flujos(self, q: dict[str, list[str]] | None = None, todo: bool = False) -> dict:
        """Los viajes entre distritos del MITMA: los días que hay, sus zonas con nombre y centro, y las horas de un día
        (o de todos, con `todo`, para la web)."""
        datos = self._guardado("mitma", 3600, lambda: mitma.leer(self.datos))
        if not datos or not datos.get("dias"):
            raise ValueError("aún no están los viajes del MITMA (se bajan solos la primera vez que arranca la sala)")
        centros = self._centros_distritos()
        zonas = {}
        for z, info in datos["zonas"].items():
            d = (info or {}).get("distrito")
            lat, lon = centros.get(d, (None, None))
            zonas[z] = {"nombre": (self.zonas.distritos.get(d) if self.zonas and d else None) or ("Fuera de València" if z == mitma.FUERA else z),
                        "distrito": d, "lat": lat, "lon": lon}
        dias = [{"dia": d, "tipo": x["tipo"], "nombre": mitma.nombre_del_dia(d), "total": x["total"],
                 "por_hora": [round(sum(v for _, _, v in h)) for h in x["horas"]],
                 "dentro": [round(sum(v for o, de, v in h if o != mitma.FUERA and de != mitma.FUERA)) for h in x["horas"]]}
                for d, x in sorted(datos["dias"].items())]
        salida = {"dias": dias, "zonas": zonas, "fuente": "Ministerio de Transportes (MITMA), estudio de movilidad con big data"}
        if todo:
            salida["horas"] = {d: x["horas"] for d, x in datos["dias"].items()}
        else:
            dia = ((q or {}).get("dia") or [dias[0]["dia"]])[0]
            if dia not in datos["dias"]:
                raise ValueError("ese día no está")
            salida["dia"], salida["horas"] = dia, datos["dias"][dia]["horas"]
        return salida

    # ------------------------------------------------------------ web

    def ficheros_web(self) -> dict[str, bytes]:
        """Lo que se sube a la web cada cuarto de hora."""
        if self.zonas is None:
            return {}
        a_bytes = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":")).encode("utf-8")  # noqa: E731
        salida = {"sala.json": a_bytes(self.estado(publico=True)),
                  "sala-barrios.json": self._guardado("web-barrios", 6 * 3600, lambda: a_bytes(self.barrios_geojson()))}

        def perfiles():
            datos = {"generado": int(time.time()), "rasgos": {}}
            for r in RASGOS_PERFIL:
                datos["rasgos"][r] = {"nombre": RASGOS[r]["nombre"], "unidad": RASGOS[r]["unidad"],
                                      **{t: self.cruce.perfil(r, t) for t in ("L", "S", "D")}}
            return a_bytes(datos)
        salida["sala-perfiles.json"] = self._guardado("web-perfiles", 3 * 3600, perfiles)

        def flujos():
            try:
                return a_bytes(self.flujos(todo=True))
            except ValueError:
                return None
        datos_mitma = self._guardado("web-mitma", 24 * 3600, flujos)
        if datos_mitma:
            salida["sala-movilidad.json"] = datos_mitma
        return salida


def parte_por_reglas(d: dict) -> str:
    """El parte escrito con reglas, a partir de los hechos de `datos_del_parte`."""
    frases = []
    activos = d.get("sucesos_activos") or []
    fuera = d.get("ciudad_fuera_de_lo_normal") or []
    if activos:
        n = len(activos)
        lista = "; ".join(f"{s['titulo']} (desde las {s['desde']})" for s in activos[:3])
        frases.append(f"{'Un suceso' if n == 1 else f'{n} sucesos'} en marcha: {lista}.")
    if fuera:
        partes = [f"{c['nombre'].lower()} {_cifra(c['valor'])}{(' ' + c['unidad']) if c['unidad'] and c['unidad'] not in ('%',) else c['unidad']} "
                  f"(lo normal, {_cifra(c['normal'])})" for c in fuera[:4]]
        frases.append("Fuera de lo normal en toda la ciudad: " + "; ".join(partes) + ".")
    if not activos and not fuera:
        frases.append("La ciudad está dentro de lo normal para esta hora.")
    destacados = [b for b in (d.get("barrios_destacados") or []) if b.get("senal")]
    if destacados and not activos:
        frases.append("Por barrios, lo más movido: " + "; ".join(f"{b['barrio']} ({b['senal']})" for b in destacados[:3]) + ".")
    if d.get("hoy"):
        frases.append("Hoy: " + "; ".join(d["hoy"][:4]) + ".")
    if d.get("avisos"):
        frases.append("Avisos: " + "; ".join(d["avisos"]) + ".")
    if d.get("incidencias_trafico"):
        n = len(d["incidencias_trafico"])
        frases.append(f"{n} incidencia{'s' if n != 1 else ''} de tráfico activa{'s' if n != 1 else ''} en el área (DGT).")
    c = d.get("conversacion_2h") or {}
    if c.get("noticias") or c.get("publicaciones"):
        temas = f" Temas: {', '.join(c['temas'])}." if c.get("temas") else ""
        frases.append(f"En las últimas dos horas, {c.get('noticias', 0)} noticias y {c.get('publicaciones', 0)} publicaciones sobre la ciudad.{temas}")
    return " ".join(frases)


def _lluvia(lecturas: list[dict]) -> str | None:
    """Si llueve en la ciudad (las estaciones del Ajuntament), para el parte; si no, nada."""
    mm = next((c["valor"] for c in lecturas if c["clave"] == "meteo_lluvia"), None)
    return f"lloviendo ({_cifra(mm)} mm en la última lectura)" if mm else None


def _cuando(cita: dict, ahora: int) -> str:
    """Cuándo es algo de la agenda de hoy, dicho para el parte: a qué hora y si aún no ha empezado, sigue o ya acabó."""
    if (cita["hasta"] or cita["desde"]) - cita["desde"] >= 20 * 3600:
        return "todo el día"
    hora = time.strftime("%H:%M", time.localtime(cita["desde"]))
    if cita["desde"] > ahora:
        return f"a las {hora}, aún no ha empezado"
    if (cita["hasta"] or 0) > ahora:
        return f"ya en marcha (empezó a las {hora})"          # «en marcha ahora» lo leía el modelo como «empieza ahora»
    return f"ya acabado (empezó a las {hora})"


def _cifra(v) -> str:
    if v is None:
        return "—"
    return f"{v:.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.1f}".replace(".", ",")


def _entero(q: dict[str, list[str]], clave: str, por_defecto: int) -> int:
    try:
        return int(float(q[clave][0]))
    except (KeyError, IndexError, ValueError):
        return por_defecto


def _real(q: dict[str, list[str]], clave: str) -> float:
    try:
        return float(q[clave][0])
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(f"falta {clave}") from exc


def atender(sala: "Sala | None", ruta: str, consulta: str) -> tuple[int, bytes]:
    """Contesta a /vivo/sala/...: (código HTTP, cuerpo en JSON)."""
    if sala is None:
        return (200, b'{"hay":false,"fase":"sin pulso"}') if ruta == "/vivo/sala/estado" else (404, b'{"error":"sin pulso"}')
    q = parse_qs(consulta)
    try:
        if ruta == "/vivo/sala/estado":
            datos = sala.estado()
        elif ruta == "/vivo/sala/barrios":
            datos = sala.barrios_geojson()
        elif ruta == "/vivo/sala/evento":
            datos = sala.evento((q.get("id") or [""])[0][:60])
        elif ruta == "/vivo/sala/barrio":
            datos = sala.barrio((q.get("codigo") or [""])[0][:6])
        elif ruta == "/vivo/sala/lugar":
            datos = sala.lugar(_real(q, "lat"), _real(q, "lon"))
        elif ruta == "/vivo/sala/items":
            datos = sala.items(q)
        elif ruta == "/vivo/sala/comparar":
            datos = sala.comparar(q)
        elif ruta == "/vivo/sala/movilidad":
            datos = sala.movilidad(q)
        elif ruta == "/vivo/sala/cielo":
            datos = sala.cielo()
        elif ruta == "/vivo/sala/flujos":
            datos = sala.flujos(q)
        else:
            return 404, b'{"error":"no existe"}'
    except ValueError as exc:
        return 400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
    return 200, json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
