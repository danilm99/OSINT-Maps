"""Informes y cruces de la sala que miran más allá del momento: la línea de tiempo del día, lo que se espera de
algo previsto frente a lo que pasa, hasta dónde llega un suceso, dónde ha habido más accidentes a esta hora, el
parte de relevo de un turno, la cronología de un suceso y la calidad de la semana.

Todo sale del histórico (rasgos, sucesos, textos, agenda, tomas) y de lo situado por `fichas`: aquí no se
pregunta a ninguna fuente. Como en el resto de la sala, son cifras de conjunto por barrio o por lugar, nunca de
personas.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import datetime

from .agenda import recinto_de
from .cruce import BIN, CIUDAD, CLASE_FUENTE, RASGOS, TIPOS_SUCESO, tipo_dia

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
# Lo que se mira alrededor de algo previsto: cómo se llena y se vacía el barrio.
RASGOS_DE_EVENTO = ("parking", "bici_ocupacion", "bici_llegadas", "bici_salidas", "aforo", "trafico")
ANTES, DESPUES = 3 * 3600, 2 * 3600          # la ventana alrededor de la hora de inicio y de la de final


def _hora(t: int | None) -> str:
    return time.strftime("%H:%M", time.localtime(t)) if t else "?"


def _dia_hora(t: int) -> str:
    d = datetime.fromtimestamp(t)
    return f"{DIAS[d.weekday()]} {d.day}, {d:%H:%M}"


class Informes:
    def __init__(self, sala):
        self.sala = sala

    @property
    def almacen(self):
        return self.sala.almacen

    @property
    def cruce(self):
        return self.sala.cruce

    @property
    def zonas(self):
        return self.sala.zonas

    # ------------------------------------------------------------ línea de tiempo

    def linea(self, horas: int = 24, ahora: int | None = None) -> dict:
        """Las últimas `horas`, de diez en diez minutos: lo fuera de lo normal que estaba cada barrio (y el más alto
        de todos) y los sucesos con su principio y su final. Para rebobinar el mapa sin abrir el histórico."""
        ahora = int(ahora or time.time())
        fin = ahora // BIN * BIN
        instantes = list(range(fin - horas * 3600 + BIN, fin + 1, BIN))
        indice = {t: k for k, t in enumerate(instantes)}
        barrios: dict[str, list] = {}
        for b, t, v in self.almacen._filas("SELECT barrio, t, v FROM rasgos WHERE rasgo='nivel' AND t>? AND t<=?", (instantes[0] - 1, fin)):
            if t in indice and v >= 1.5:               # lo que está dentro de lo normal no se manda
                barrios.setdefault(b, [0] * len(instantes))[indice[t]] = round(v, 1)
        maximo = [max((fila[k] for b, fila in barrios.items() if b != CIUDAD), default=0) for k in range(len(instantes))]
        sucesos = []
        if self.cruce:
            for ev in self.cruce.eventos(instantes[0], fin + 1, 80):
                corto = self.sala._suceso_corto(ev)
                sucesos.append({k: corto[k] for k in ("id", "tipo", "titulo", "inicio", "fin", "estado", "puntuacion", "confianza", "barrios", "lat", "lon")})
        return {"desde": instantes[0], "paso": BIN, "n": len(instantes), "maximo": maximo, "barrios": barrios, "sucesos": sucesos}

    # ------------------------------------------------------------ riesgo de accidente

    def riesgo(self, ahora: int | None = None) -> dict:
        """Dónde ha habido más accidentes de tráfico a esta hora (dos horas arriba y abajo) en días como hoy
        (laborable, sábado, o domingo y festivo), con los datos del Ajuntament: puntos para un mapa de calor
        (peso mayor cuanto más grave) y los diez cruces con más. Es por lugar y hora: nada de personas."""
        ahora = int(ahora or time.time())
        fichas = self.sala.fichas
        if fichas is None:
            return {"puntos": [], "cruces": [], "n": 0}
        tipo = tipo_dia(ahora)
        hora = time.localtime(ahora).tm_hour
        celdas: dict[tuple[float, float], list] = {}
        n = 0
        for t, lat, lon, barrio, gravedad, _tipo, _unidades, ubicacion in fichas.accidentes():
            h = time.localtime(t).tm_hour
            if min((h - hora) % 24, (hora - h) % 24) > 2 or tipo_dia(t) != tipo:
                continue
            n += 1
            clave = (round(lat, 4), round(lon, 4))
            celda = celdas.setdefault(clave, [0, 0.0, ubicacion, barrio, 0])
            celda[0] += 1
            celda[1] += 1 + 0.75 * (gravedad or 0)
            celda[4] = max(celda[4], gravedad or 0)
        tope = max((c[1] for c in celdas.values()), default=1.0)
        puntos = [[la, lo, round(min(1.5, 1.5 * c[1] / tope + 0.15), 3)] for (la, lo), c in celdas.items()]
        cruces = sorted(({"lat": la, "lon": lo, "n": c[0], "ubicacion": c[2], "barrio": c[3], "barrio_nombre": self.sala._nombre(c[3]), "gravedad": c[4]}
                         for (la, lo), c in celdas.items()), key=lambda x: -x["n"])[:10]
        nombres = {"L": "laborables", "S": "sábados", "D": "domingos y festivos"}
        return {"puntos": puntos, "cruces": cruces, "n": n, "dias": nombres.get(tipo, tipo),
                "franja": f"de {(hora - 2) % 24:02d}:00 a {(hora + 3) % 24:02d}:00"}

    # ------------------------------------------------------------ lo previsto: esperado frente a observado

    def _cita(self, ident: str) -> dict | None:
        filas = self.almacen._filas("SELECT id, tipo, titulo, desde, hasta, lat, lon, barrio, fuente, url FROM agenda WHERE id=?", (ident,))
        if not filas:
            return None
        cita = dict(zip(("id", "tipo", "titulo", "desde", "hasta", "lat", "lon", "barrio", "fuente", "url"), filas[0]))
        if cita["barrio"] is None and cita["lat"] is not None and self.zonas:
            cita["barrio"] = self.zonas.barrio_de(cita["lat"], cita["lon"])
        cita["recinto"] = recinto_de(cita["titulo"], cita["lat"], cita["lon"])
        return cita

    def _curvas(self, barrios: list[str], inicio: int) -> dict[str, list]:
        """Cada rasgo en esos barrios (la media), de tres horas antes a cuatro después de `inicio`, cada diez
        minutos; None donde no hay datos."""
        desde, hasta = inicio - ANTES, inicio + 4 * 3600
        pasos = (hasta - desde) // BIN + 1
        curvas = {}
        for r in RASGOS_DE_EVENTO:
            suma, cuenta = [0.0] * pasos, [0] * pasos
            for _b, puntos in self.cruce.serie(r, barrios, desde - 1, hasta).items():
                for t, v in puntos:
                    k = (t - desde) // BIN
                    if 0 <= k < pasos:
                        suma[k] += v
                        cuenta[k] += 1
            if any(cuenta):
                curvas[r] = [round(suma[k] / cuenta[k], 1) if cuenta[k] else None for k in range(pasos)]
        return curvas

    def previsto(self, ident: str, ahora: int | None = None) -> dict:
        """Algo previsto con sitio (un partido, un festejo): lo que pasa alrededor frente a lo que pasó las otras
        veces en ese mismo sitio. Con eso se ve si la gente llega antes o después, si el aparcamiento se llena
        más, y qué esperar de lo que aún no ha empezado."""
        ahora = int(ahora or time.time())
        cita = self._cita(ident)
        if cita is None or self.cruce is None:
            raise ValueError("no existe eso en la agenda")
        if cita["barrio"] is None:
            raise ValueError("eso no tiene un sitio en el mapa")
        barrios = [cita["barrio"]] + sorted(self.zonas.vecinos.get(cita["barrio"], ()))
        base = cita["tipo"].split(":")[0]
        # Las otras veces: lo del mismo tipo en el mismo sitio de las últimas semanas (el histórico de rasgos dura tres).
        anteriores = []
        for fila in self.almacen._filas("SELECT id, titulo, desde, hasta, lat, lon, barrio FROM agenda WHERE tipo LIKE ? AND id!=? AND desde<? AND desde>? "
                                        "ORDER BY desde DESC", (base + "%", ident, min(cita["desde"], ahora), ahora - 21 * 86400)):
            otra = dict(zip(("id", "titulo", "desde", "hasta", "lat", "lon", "barrio"), fila))
            barrio = otra["barrio"] or (self.zonas.barrio_de(otra["lat"], otra["lon"]) if otra["lat"] is not None else None)
            if barrio == cita["barrio"]:
                anteriores.append(otra | {"curvas": self._curvas(barrios, otra["desde"])})
        anteriores = [a for a in anteriores if a["curvas"]][:4]
        curvas = self._curvas(barrios, cita["desde"])
        pasos = (ANTES + 4 * 3600) // BIN + 1
        rasgos = {}
        for r in RASGOS_DE_EVENTO:
            otras = [a["curvas"][r] for a in anteriores if r in a["curvas"]]
            if r not in curvas and not otras:
                continue
            esperado = []
            for k in range(pasos):
                vs = [o[k] for o in otras if o[k] is not None]
                esperado.append(round(sum(vs) / len(vs), 1) if vs else None)
            rasgos[r] = {"nombre": RASGOS[r]["nombre"], "unidad": RASGOS[r]["unidad"], "ahora": curvas.get(r), "esperado": esperado if otras else None}
        return {"cita": cita, "barrios": [{"codigo": b, "nombre": self.sala._nombre(b)} for b in barrios], "desde": cita["desde"] - ANTES, "paso": BIN,
                "rasgos": rasgos, "anteriores": [{k: a[k] for k in ("id", "titulo", "desde")} for a in anteriores],
                "frases": self._frases_previsto(cita, rasgos, ahora, len(anteriores))}

    @staticmethod
    def _frases_previsto(cita: dict, rasgos: dict, ahora: int, n_anteriores: int) -> list[str]:
        frases = []
        recinto = cita.get("recinto")
        if recinto:
            frases.append(f"{recinto['nombre']}: caben unas {recinto['aforo']:,} personas.".replace(",", "."))
        k_ahora = (ahora - (cita["desde"] - ANTES)) // BIN
        for r in ("parking", "bici_ocupacion"):
            x = rasgos.get(r)
            if not x:
                continue
            esperado, visto = x.get("esperado"), x.get("ahora")
            if esperado:
                pico = max(((v, k) for k, v in enumerate(esperado) if v is not None), default=None)
                if pico:
                    minutos = (pico[1] * BIN - ANTES) // 60
                    cuando = f"{abs(minutos)} min {'antes de' if minutos < 0 else 'después de'} empezar" if minutos else "al empezar"
                    frases.append(f"Otras veces, {x['nombre'].lower()} llegó a {pico[0]:g} {x['unidad']} {cuando}.")
            if esperado and visto and 0 <= k_ahora < len(visto):
                k = min(k_ahora, len(visto) - 1)
                while k >= 0 and (visto[k] is None or esperado[k] is None):
                    k -= 1
                if k >= 0:
                    diferencia = visto[k] - esperado[k]
                    if abs(diferencia) >= 5:
                        frases.append(f"Ahora, {x['nombre'].lower()}: {visto[k]:g} {x['unidad']}, {abs(diferencia):g} "
                                      f"{'más' if diferencia > 0 else 'menos'} que otras veces a esta altura.")
        if not n_anteriores:
            frases.append("Aún no hay otras veces en este sitio con las que comparar (el histórico guarda tres semanas).")
        return frases

    # ------------------------------------------------------------ hasta dónde llega un suceso

    def propagacion(self, ev: dict) -> list[dict]:
        """Los barrios de alrededor de un suceso (a uno y dos barrios de distancia) que se han salido de lo normal
        desde que empezó: cuánto, cuántos minutos después y qué es lo que más se ha movido."""
        if self.cruce is None or self.zonas is None:
            return []
        nucleo = {b for b in ev["barrios"] if b != CIUDAD}
        if not nucleo:
            return []
        # Lo que es de otro suceso de ese rato (el partido de al lado) no es alcance de este.
        de_otros = {b for otro in self.cruce.eventos(ev["inicio"], ev["fin"] + 1, 40) if otro["id"] != ev["id"] for b in otro["barrios"]}
        anillo1 = {v for b in nucleo for v in self.zonas.vecinos.get(b, ())} - nucleo - de_otros
        anillo2 = {v for b in anillo1 for v in self.zonas.vecinos.get(b, ())} - nucleo - anillo1 - de_otros
        desde, hasta = ev["inicio"] - BIN, ev["fin"] + 1800
        niveles = self.cruce.serie("nivel", sorted(anillo1 | anillo2), desde, hasta)
        salida = []
        for b, puntos in niveles.items():
            t_max, n_max = max(puntos, key=lambda p: p[1])
            if n_max < 2.5:
                continue
            # Qué rasgo se separó más de lo normal en ese momento.
            mejor = None
            for r, info in RASGOS.items():
                fila = self.almacen._filas("SELECT v FROM rasgos WHERE rasgo=? AND barrio=? AND t=?", (r, b, t_max))
                if not fila:
                    continue
                c = self.cruce.comparar(r, b, t_max, fila[0][0])
                if c and (mejor is None or abs(c["z"]) > abs(mejor[1]["z"])):
                    mejor = (r, c, fila[0][0])
            salida.append({"barrio": b, "nombre": self.sala._nombre(b), "anillo": 1 if b in anillo1 else 2, "nivel": round(n_max, 1), "t": t_max,
                           "minutos": max(0, (t_max - ev["inicio"]) // 60),
                           "senal": None if mejor is None else {"rasgo": mejor[0], "nombre": RASGOS[mejor[0]]["nombre"], "valor": mejor[2],
                                                                "normal": mejor[1]["normal"], "z": mejor[1]["z"]}})
        return sorted(salida, key=lambda x: (x["anillo"], -x["nivel"]))

    # ------------------------------------------------------------ cronología de un suceso

    def cronologia(self, ident: str) -> dict:
        """Lo que pasó en un suceso, en orden: cuándo empezó, cada señal en su momento más fuerte, lo que se
        publicó de la zona, hasta dónde llegó y cuándo se cerró. Para el informe posterior."""
        ev = self.cruce.evento(ident) if self.cruce else None
        if not ev:
            raise ValueError("no existe ese suceso")
        corto = self.sala._suceso_corto(ev)
        hitos = [{"t": ev["inicio"], "que": "Empieza", "detalle": TIPOS_SUCESO.get(ev["tipo"], ev["tipo"]) + " en "
                  + ", ".join(self.sala._nombre(b) for b in ev["barrios"][:4])}]
        for s in sorted((ev["evidencias"].get("pico") or []), key=lambda s: -(s.get("fuerza") or 0))[:6]:
            info = RASGOS.get(s["rasgo"], {})
            normal = "" if s.get("normal") is None else f" (lo normal, {s['normal']:g})"
            valor = "" if s.get("valor") is None else f": {s['valor']:g} {info.get('unidad', '')}"
            hitos.append({"t": s.get("t") or ev["pico"], "que": info.get("nombre", s["rasgo"]), "barrio": self.sala._nombre(s.get("barrio")),
                          "detalle": f"{self.sala._nombre(s.get('barrio'))}{valor}{normal}", "clase": CLASE_FUENTE.get(s.get("fuente"), "sensor")})
        for tx in ((ev.get("causa") or {}).get("textos") or [])[:8]:
            hitos.append({"t": tx["t"], "que": "Se publica", "detalle": tx["titulo"], "url": tx.get("url"), "clase": "texto", "fuente": tx.get("fuente")})
        hitos.append({"t": ev["pico"], "que": "Momento más fuerte", "detalle": f"puntuación {ev['puntuacion']:g}"})
        alcance = self.propagacion(ev)
        for a in alcance[:6]:
            hitos.append({"t": a["t"], "que": "Llega a", "detalle": f"{a['nombre']} (nivel {a['nivel']:g})" + (f": {a['senal']['nombre'].lower()}" if a["senal"] else ""),
                          "clase": "sensor"})
        if ev["estado"] != "activo":
            hitos.append({"t": ev["fin"], "que": "Se cierra", "detalle": f"tras {(ev['fin'] - ev['inicio']) // 60} minutos"})
        hitos.sort(key=lambda h: h["t"])
        return {"suceso": corto, "confianza": ev["evidencias"].get("confianza"), "causa": (ev.get("causa") or {}).get("probable"),
                "candidatas": (ev.get("causa") or {}).get("candidatas") or [], "hitos": hitos, "alcance": alcance,
                "nombres": {b: self.sala._nombre(b) for b in ev["barrios"]}}

    # ------------------------------------------------------------ relevo de turno

    def relevo(self, horas: int = 8, ahora: int | None = None, publico: bool = False) -> dict:
        """El parte para quien entra de turno: lo que ha pasado en las últimas `horas`, lo que sigue abierto, los
        avisos en vigor, las fuentes que fallan y lo que viene en las próximas `horas`."""
        ahora = int(ahora or time.time())
        horas = max(1, min(24, int(horas)))
        desde, hasta = ahora - horas * 3600, ahora + horas * 3600
        sucesos = [self.sala._suceso_corto(ev) for ev in self.cruce.eventos(desde, ahora + 1, 80)] if self.cruce else []
        sucesos = [s for s in sucesos if s.get("valoracion") != "falso"]
        abiertos = sorted((s for s in sucesos if s["estado"] == "activo"), key=lambda s: -(s["puntuacion"] or 0))
        cerrados = sorted((s for s in sucesos if s["estado"] != "activo"), key=lambda s: -s["fin"])
        urgentes = [dict(zip(("id", "fuente", "t", "titulo", "url", "barrio", "categoria"), f)) for f in self.almacen._filas(
            "SELECT id, fuente, t, titulo, url, barrio, categoria FROM items WHERE t>? AND urgencia>=2 AND fuente='prensa' "
            "AND categoria IN ('emergencia','accidente','seguridad') ORDER BY t DESC LIMIT 12", (desde,))]
        for u in urgentes:
            u["barrio_nombre"] = self.sala._nombre(u["barrio"]) if u["barrio"] else None
        avisos = self.sala._avisos(ahora)
        proximo = []
        for ident, tipo, titulo, a, b, lat, lon, barrio in self.almacen._filas(
                "SELECT id, tipo, titulo, desde, hasta, lat, lon, barrio FROM agenda WHERE desde<=? AND hasta>=? AND "
                "(tipo LIKE 'partido%' OR tipo LIKE 'festejo%' OR tipo LIKE 'festivo%' OR tipo LIKE 'fiesta%') ORDER BY desde", (hasta, ahora)):
            recinto = recinto_de(titulo, lat, lon)
            if barrio is None and lat is not None and self.zonas:
                barrio = self.zonas.barrio_de(lat, lon)
            proximo.append({"id": ident, "tipo": tipo.split(":")[0], "titulo": titulo, "desde": a, "hasta": b, "barrio": barrio,
                            "barrio_nombre": self.sala._nombre(barrio) if barrio else None, "aforo": recinto["aforo"] if recinto else None,
                            "en_marcha": a <= ahora})
        cortes = self.almacen._filas("SELECT COUNT(*) FROM agenda WHERE desde>? AND desde<=? AND (tipo LIKE 'obra%' OR tipo LIKE 'ocupacion%')", (ahora, hasta))[0][0]
        fuentes = self.sala._fuentes()
        caidas = [f["nombre"] for f in fuentes if not f.get("ok") or (f.get("ultima") and ahora - f["ultima"] > max(3 * (f.get("cada") or 600), 3600))]
        datos = {"generado": ahora, "horas": horas, "desde": desde, "hasta": hasta, "abiertos": abiertos, "cerrados": cerrados[:15],
                 "urgentes": urgentes, "avisos": [a for a in avisos if a["fuente"] == "meteoalarm" or (a.get("urgencia") or 0) >= 2][:12],
                 "incidencias": sum(1 for a in avisos if a["fuente"] == "dgt"), "proximo": proximo[:15], "cortes_previstos": cortes,
                 "fuentes_caidas": caidas, "fuentes": len(fuentes),
                 "aprendiendo": self.cruce.aprendizaje(ahora) if self.cruce else None}
        datos["texto"] = relevo_en_texto(datos)
        return datos

    # ------------------------------------------------------------ calidad de la semana

    def calidad(self, dias: int = 7, ahora: int | None = None) -> dict:
        """Cómo ha ido la sala estos días: cuántos sucesos de cada tipo y confianza, cuántos se han confirmado o
        eran falsos positivos, qué barrios saltan más y qué fuentes han fallado."""
        ahora = int(ahora or time.time())
        desde = ahora - dias * 86400
        sucesos = [self.sala._suceso_corto(ev) for ev in self.cruce.eventos(desde, ahora + 1, 2000)] if self.cruce else []
        por_tipo, por_confianza, por_barrio, por_dia = Counter(), Counter(), Counter(), Counter()
        explicados = 0
        for s in sucesos:
            por_tipo[s["tipo_nombre"]] += 1
            por_confianza[s.get("confianza") or "baja"] += 1
            explicados += bool(s["explicado"])
            por_dia[time.strftime("%Y-%m-%d", time.localtime(s["inicio"]))] += 1
            for b in s["barrios"][:3]:
                por_barrio[b] += 1
        valoraciones = Counter(v for (v,) in self.almacen._filas("SELECT valor FROM valoraciones WHERE t>?", (desde,)))
        fuentes = []
        for fuente, total, bien in self.almacen._filas("SELECT fuente, COUNT(*), SUM(ok) FROM tomas WHERE t>? GROUP BY fuente", (desde,)):
            fuentes.append({"id": fuente, "tomas": total, "bien": round(100 * (bien or 0) / total, 1) if total else None})
        fuentes.sort(key=lambda f: f["bien"] if f["bien"] is not None else 0)
        nombres = {f["id"]: f["nombre"] for f in self.sala._fuentes()}
        for f in fuentes:
            f["nombre"] = nombres.get(f["id"], f["id"])
        valorados = valoraciones["falso"] + valoraciones["confirmado"]
        return {"generado": ahora, "dias": dias, "sucesos": len(sucesos), "por_tipo": por_tipo.most_common(), "por_confianza": dict(por_confianza),
                "explicados": explicados, "por_dia": sorted(por_dia.items()),
                "barrios": [{"codigo": b, "nombre": self.sala._nombre(b), "n": n} for b, n in por_barrio.most_common(8)],
                "valoraciones": {"falsos": valoraciones["falso"], "confirmados": valoraciones["confirmado"], "sin_valorar": max(0, len(sucesos) - valorados),
                                 "acierto": round(100 * valoraciones["confirmado"] / valorados) if valorados else None},
                "fuentes": fuentes, "aprendiendo": self.cruce.aprendizaje(ahora) if self.cruce else None}


def relevo_en_texto(d: dict) -> str:
    """El relevo en texto llano, para copiar y pegar."""
    lineas = [f"RELEVO DE TURNO. València, {_dia_hora(d['generado'])}. Últimas {d['horas']} horas y próximas {d['horas']}.", ""]
    ap = d.get("aprendiendo")
    if ap and not ap["listo"]:
        lineas += [f"Aviso: la sala lleva {str(ap['dias']).replace('.', ',')} días aprendiendo lo normal de cada barrio (necesita 28); lo de confianza baja puede no ser nada.", ""]
    lineas.append(f"ABIERTO AHORA ({len(d['abiertos'])})")
    for s in d["abiertos"]:
        lineas.append(f"- {s['titulo']} | desde las {_hora(s['inicio'])} | confianza {s.get('confianza') or 'baja'}")
    if not d["abiertos"]:
        lineas.append("- Nada.")
    lineas += ["", f"CERRADO EN EL TURNO ({len(d['cerrados'])})"]
    for s in d["cerrados"]:
        lineas.append(f"- {_hora(s['inicio'])}-{_hora(s['fin'])} {s['titulo']} | confianza {s.get('confianza') or 'baja'}")
    if not d["cerrados"]:
        lineas.append("- Nada.")
    if d["urgentes"]:
        lineas += ["", "NOTICIAS URGENTES"]
        lineas += [f"- {_hora(u['t'])} {u['titulo']}" + (f" ({u['barrio_nombre']})" if u.get("barrio_nombre") else "") for u in d["urgentes"]]
    lineas += ["", "AVISOS EN VIGOR"]
    lineas += [f"- {a['titulo']}" for a in d["avisos"]] or ["- Ninguno."]
    lineas.append(f"- Incidencias de carretera activas en el área (DGT): {d['incidencias']}")
    lineas += ["", f"PRÓXIMAS {d['horas']} HORAS"]
    for p in d["proximo"]:
        cuando = "en marcha" if p["en_marcha"] else _dia_hora(p["desde"])
        aforo = f" | aforo {p['aforo']:,}".replace(",", ".") if p.get("aforo") else ""
        lugar = f" | {p['barrio_nombre']}" if p.get("barrio_nombre") else ""
        lineas.append(f"- {cuando}: {p['titulo']}{lugar}{aforo}")
    if not d["proximo"]:
        lineas.append("- Nada destacado en la agenda.")
    if d["cortes_previstos"]:
        lineas.append(f"- Empiezan {d['cortes_previstos']} obras u ocupaciones de la vía.")
    lineas += ["", "FUENTES"]
    lineas.append(f"- Fallan: {', '.join(d['fuentes_caidas'])}." if d["fuentes_caidas"] else f"- Las {d['fuentes']} contestan.")
    return "\n".join(lineas)
