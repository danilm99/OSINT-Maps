"""El cruce: de muchas señales sueltas a «qué está pasando y dónde».

Cada diez minutos, todo lo recogido se lleva a los barrios y se convierte en **rasgos**: cómo está
el tráfico del barrio, cuántos tramos hay cortados, cuántas bicis llegan o salen de sus estaciones,
cómo están sus aparcamientos, cuántos metros salen, de cuántas cosas se habla allí, si hay un
helicóptero encima... Todo son cifras de conjunto: ninguna dice nada de nadie en concreto.

Cada rasgo se compara con **lo normal** para ese barrio a esa media hora de la semana: la mediana
de las últimas ocho semanas o, mientras no las hay, de los días del mismo tipo (laborable, sábado,
domingo o festivo). La medida es la «z»: cuánto se separa de lo normal comparado con lo que suele
variar. Los recuentos que casi siempre valen cero (publicaciones, avisos, helicópteros) se miden por
lo raro que es ver tantos (binomial negativa: las publicaciones llegan a rachas).

Lo que se mueve en **toda la ciudad a la vez** (la lluvia deja las bicis ancladas en todas partes) no
es de ningún barrio: a cada barrio se le quita la mediana de todos, y ese movimiento general se
cuenta aparte, como suceso de la ciudad.

Los rasgos se agrupan en **familias**:

    afluencia   llega gente: estaciones que se llenan, aparcamientos que se llenan, más bicis por el carril
    salida      se va gente: estaciones y aparcamientos que se vacían
    congestion  tráfico denso, más vehículos por hora de lo normal
    corte       tramos cortados, menos vehículos de lo normal (algo cierra la calle)
    servicio    el metro deja de salir
    atencion    se habla del sitio más de lo normal (prensa, redes)
    alerta      helicóptero encima, incidencias de la DGT o Renfe, textos urgentes (incendio, herido...)

Un **suceso** necesita señales de **fuentes distintas** a la vez: Valenbisi sola (un camión que
reparte bicis) no basta, Valenbisi y los aparcamientos sí. Los barrios vecinos con señales forman un
solo suceso, que se sigue en el tiempo hasta que todo vuelve a lo normal. Para cada uno se busca la
**causa**: algo previsto (un partido, un festejo, una obra, un festivo), el tiempo, lo que se publica
de ese sitio. Si no hay ninguna queda «sin causa conocida», que es justo lo interesante.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import threading
import time
from collections import defaultdict
from datetime import date, datetime
from typing import NamedTuple

from . import agenda as _agenda
from .almacen import Almacen, semana_local
from .catalogo import POR_ID

log = logging.getLogger("osintmaps.pulso")

BIN = 600                   # segundos de cada rasgo
FRANJA = 1800               # lo normal se calcula por medias horas de la semana
SEMANA = 7 * 86400
CIUDAD = "VLC"              # el «barrio» que es la ciudad entera
MIN_MUESTRAS = 4
REDES = ("bluesky", "mastodon")
ALTURA_HELIS = 1500         # metros: por encima, un helicóptero va de paso

# Cada rasgo: nombre, unidad, tipo (continuo o conteo), de qué fuente sale (para contar fuentes
# independientes), a qué familia apunta si sube (+1) o baja (-1), y cómo medirlo:
#   continuo: «suelo» y «rel» ponen un mínimo a lo que se considera variación normal
#   conteo:   «prior» (lo que se espera por barrio sin saber nada), «ciudad» (lo mismo para toda la
#             ciudad) y «r» (lo a rachas que llega: cuanto más pequeño, más a rachas). «con_historia»: lo que
#             cambia tanto de un barrio a otro (bicis, publicaciones, obras) que sin histórico no se juzga.
#   «suavizar»: se compara la media de los últimos veinte minutos y no la foto de ahora (un barrio con cuatro
#             tramos de calle salta de 12 en 12 puntos cada vez que uno cambia de color).
RASGOS: dict[str, dict] = {
    "trafico": {"nombre": "Tráfico", "unidad": "sobre 100", "tipo": "continuo", "fuente": "trafico", "suelo": 8.0,
                "familias": {+1: "congestion"}, "suavizar": True},
    "cortes": {"nombre": "Tramos cortados", "unidad": "tramos", "tipo": "conteo", "fuente": "trafico", "prior": 0.1, "ciudad": 4.0, "r": 3,
               "familias": {+1: "corte"}, "con_historia": True},
    "aforo": {"nombre": "Vehículos por hora", "unidad": "veh/h", "tipo": "continuo", "fuente": "aforo", "suelo": 40.0, "rel": 0.08,
              "familias": {+1: "congestion", -1: "corte"}},
    "aforo_bici": {"nombre": "Bicis y patinetes por hora", "unidad": "por hora", "tipo": "continuo", "fuente": "aforo_bici", "suelo": 15.0,
                   "rel": 0.1, "familias": {+1: "afluencia"}, "peso": 0.7},
    "ora": {"nombre": "Zona azul prevista", "unidad": "%", "tipo": "continuo", "fuente": "ora", "suelo": 4.0,
            "familias": {+1: "afluencia"}, "peso": 0.6},
    "parking": {"nombre": "Aparcamientos ocupados", "unidad": "%", "tipo": "continuo", "fuente": "parking", "suelo": 4.0,
                "familias": {+1: "afluencia", -1: "salida"}},
    "bici_ocupacion": {"nombre": "Valenbisi: anclajes con bici", "unidad": "%", "tipo": "continuo", "fuente": "bicis", "suelo": 5.0,
                       "familias": {+1: "afluencia", -1: "salida"}, "suavizar": True},
    "bici_llegadas": {"nombre": "Bicis que llegan", "unidad": "en 10 min", "tipo": "conteo", "fuente": "bicis", "prior": 2.0, "ciudad": 150.0,
                      "r": 4, "familias": {+1: "afluencia"}, "con_historia": True},
    "bici_salidas": {"nombre": "Bicis que salen", "unidad": "en 10 min", "tipo": "conteo", "fuente": "bicis", "prior": 2.0, "ciudad": 150.0,
                     "r": 4, "familias": {+1: "salida"}, "con_historia": True},
    "metro": {"nombre": "Salidas de metro", "unidad": "en 30 min", "tipo": "continuo", "fuente": "metro", "suelo": 1.5,
              "familias": {-1: "servicio"}},
    "social": {"nombre": "Publicaciones", "unidad": "en 30 min", "tipo": "conteo", "fuente": "redes", "prior": 0.15, "ciudad": 4.0, "r": 2,
               "familias": {+1: "atencion"}, "con_historia": True},
    "prensa": {"nombre": "Noticias", "unidad": "en 2 h", "tipo": "conteo", "fuente": "prensa", "prior": 0.1, "ciudad": 8.0, "r": 3,
               "familias": {+1: "atencion"}},
    "alertas": {"nombre": "Incidencias de tráfico y transporte", "unidad": "activas", "tipo": "conteo", "fuente": "dgt", "prior": 0.05,
                "ciudad": 3.0, "r": 5, "familias": {+1: "alerta"}},
    "urgentes": {"nombre": "Textos urgentes", "unidad": "en 1 h", "tipo": "conteo", "fuente": "textos", "prior": 0.03, "ciudad": 0.5, "r": 3,
                 "familias": {+1: "alerta"}},
    "helis": {"nombre": "Helicóptero encima", "unidad": "min", "tipo": "conteo", "fuente": "aviones", "prior": 0.1, "ciudad": 1.0, "r": 1,
              "familias": {+1: "alerta"}},
    "no2": {"nombre": "NO₂", "unidad": "µg/m³", "tipo": "continuo", "fuente": "aire", "suelo": 6.0,
            "familias": {+1: "ambiente"}, "peso": 0.5},
}
FAMILIAS = {
    "afluencia": "llega gente", "salida": "se va gente", "congestion": "más tráfico de lo normal",
    "corte": "calles cortadas o con menos tráfico del normal", "servicio": "el metro no sale", "atencion": "se habla del sitio",
    "alerta": "avisos y señales de incidente", "ambiente": "aire peor de lo normal",
}
TIPOS_SUCESO = {
    "concentracion": "Afluencia", "salida": "Salida de gente", "incidente": "Posible incidente", "congestion": "Congestión",
    "corte": "Posible corte", "servicio": "Metro sin servicio", "conversacion": "Se habla de", "ciudad": "Toda la ciudad",
}
# Qué categorías de texto encajan con cada tipo de suceso (para elegir la causa).
CATEGORIAS_DE = {
    "concentracion": {"evento", "deporte", "protesta", "politica"},
    "salida": {"evento", "deporte", "protesta", "emergencia"},
    "incidente": {"emergencia", "accidente", "seguridad"},
    "corte": {"trafico", "accidente", "protesta", "urbanismo", "evento"},
    "congestion": {"trafico", "accidente", "evento", "deporte"},
    "servicio": {"transporte", "protesta"},
    "conversacion": set(),
    "ciudad": {"meteo", "emergencia", "protesta", "transporte"},
}
PESO_FUENTE_TEXTO = {"prensa": 0.45, "dgt": 0.55, "renfe": 0.55, "meteoalarm": 0.5, "bluesky": 0.3, "mastodon": 0.3}


class Senal(NamedTuple):
    familia: str
    fuerza: float
    rasgo: str
    fuente: str
    valor: float
    normal: float
    z: float


# --------------------------------------------------------------------------
# Tiempo
# --------------------------------------------------------------------------

def franja(t: int) -> int:
    """Media hora de la semana (0 = lunes 0:00-0:30, hora local)."""
    lt = time.localtime(t)
    return lt.tm_wday * 48 + lt.tm_hour * 2 + (lt.tm_min >= 30)


def _dia(t: int) -> date:
    lt = time.localtime(t)
    return date(lt.tm_year, lt.tm_mon, lt.tm_mday)


def tipo_dia(t: int) -> str:
    """L laborable, S sábado, D domingo o festivo."""
    if time.localtime(t).tm_wday == 6 or _agenda.es_festivo(_dia(t)):
        return "D"
    return "S" if time.localtime(t).tm_wday == 5 else "L"


def franjas_del_tipo(tipo: str, slot: int) -> list[int]:
    dias = {"L": range(5), "S": (5,), "D": (6,)}[tipo]
    return [d * 48 + slot for d in dias]


# --------------------------------------------------------------------------
# Estadística
# --------------------------------------------------------------------------

_NORMAL = statistics.NormalDist()


def z_continuo(x: float, muestras: list[float], suelo: float, rel: float = 0.0) -> tuple[float, float]:
    """(z robusta, mediana): mediana y desviación absoluta mediana, con un mínimo de variación."""
    med = statistics.median(muestras)
    mad = statistics.median(abs(m - med) for m in muestras)
    escala = max(mad, suelo, rel * abs(med))
    return 0.6745 * (x - med) / escala, med


def z_conteo(k: float, muestras: list[float], prior: float, r: float | None = None) -> tuple[float, float]:
    """(z, esperado) de ver `k` o más. Lo esperado es la media del histórico con un prior que pesa como dos
    muestras (para no fiarse de unos pocos ceros). Con `r`, binomial negativa (llegan a rachas); sin él,
    Poisson. Solo mide subidas: bajar de un recuento casi nulo no dice nada."""
    lam = max((sum(muestras) + 2 * prior) / (len(muestras) + 2), 1e-3)
    k = int(round(k))
    if k <= lam:
        return 0.0, lam
    acumulado = 0.0
    if r is None:
        termino = math.exp(-lam)
        for i in range(k):
            acumulado += termino
            termino *= lam / (i + 1)
    else:
        p = r / (r + lam)
        log_p, log_q, base = math.log(p), math.log1p(-p), math.lgamma(r)
        for i in range(k):
            acumulado += math.exp(math.lgamma(i + r) - base - math.lgamma(i + 1) + r * log_p + i * log_q)
    cola = min(1.0, max(1e-15, 1.0 - acumulado))
    return max(0.0, min(8.0, _NORMAL.inv_cdf(1 - cola))), lam


# --------------------------------------------------------------------------
# El motor
# --------------------------------------------------------------------------

class Cruce:
    def __init__(self, almacen: Almacen, zonas, ia=None):
        self.almacen = almacen
        self.zonas = zonas
        self.ia = ia
        self._candado = threading.RLock()
        self._mapa_puntos: dict[str, tuple[float, dict[str, str]]] = {}     # serie -> (cuándo, id -> barrio)
        self.estado: dict = {}          # lo último calculado (para la sala)
        self.ultimo_bin = 0
        self._ultima_franja = 0

    # ------------------------------------------------------------ rasgos

    def _barrio_de_puntos(self, serie: str) -> dict[str, str]:
        hecho = self._mapa_puntos.get(serie)
        if hecho and time.time() - hecho[0] < 3600:
            return hecho[1]
        mapa = {}
        for ident, p in self.almacen.puntos(serie).items():
            b = self.zonas.barrio_de(p.get("lat"), p.get("lon"))
            if b:
                mapa[ident] = b
        self._mapa_puntos[serie] = (time.time(), mapa)
        return mapa

    def _cubierto(self, fuente: str, instantes: list[int]) -> list[bool]:
        """Para cada instante: ¿la fuente estaba contestando? Lo que no se sabe no cuenta como cero."""
        f = POR_ID.get(fuente)
        if not f or not instantes:
            return [False] * len(instantes)
        margen = max(3 * f.cada, 900)
        ratos = self.almacen.cobertura(fuente, int(instantes[0] - margen), instantes[-1], margen)
        return [any(a <= t <= b + margen for a, b in ratos) for t in instantes]

    def calcular_rasgos(self, instantes: list[int]) -> dict[int, dict[str, dict[str, float]]]:
        """Los rasgos de cada barrio al final de cada intervalo de diez minutos: {t: {rasgo: {barrio: valor}}}.
        Lo que no tiene datos (la fuente no contestaba) no sale."""
        if not instantes or not self.zonas or not self.zonas.hay:
            return {}
        salida: dict[int, dict[str, dict[str, float]]] = {t: defaultdict(dict) for t in instantes}
        for paso in (self._rasgos_de_puntos, self._rasgos_de_bicis, self._rasgos_de_textos, self._rasgos_de_helicopteros):
            try:
                paso(instantes, salida)
            except Exception:  # noqa: BLE001 - un rasgo que falla no tumba a los demás
                log.warning("Cruce: %s ha fallado", paso.__name__, exc_info=True)
        self._agregar_ciudad(instantes, salida)
        return {t: dict(v) for t, v in salida.items()}

    def _rasgos_de_puntos(self, instantes, salida) -> None:
        def media(vs):
            return sum(x for x, _ in vs) / len(vs)

        def suma(vs):
            return sum(x for x, _ in vs)

        def bicis(vs):            # % de anclajes con bici
            cap = sum((c or 0) for _, c in vs)
            return 100 * sum(x for x, _ in vs) / cap if cap else None

        def parking(vs):          # % de plazas ocupadas (el valor guardado son plazas libres)
            cap = sum(c for _, c in vs if c)
            return 100 * (1 - sum(min(x, c) for x, c in vs if c) / cap) if cap else None

        def trafico(vs):          # 0 fluido .. 100 congestionado; los cortados no cuentan aquí
            abiertos = [x for x, _ in vs if x < 3]
            return 100 * sum(abiertos) / (2 * len(abiertos)) if abiertos else None

        def cortes(vs):
            return sum(1 for x, _ in vs if x >= 3)

        tabla = (("trafico", "trafico", (("trafico", trafico), ("cortes", cortes))),
                 ("aforo", "aforo", (("aforo", media),)),
                 ("aforo_bici", "aforo_bici", (("aforo_bici", media),)),
                 ("ora", "ora", (("ora", media),)),
                 ("parking", "parking", (("parking", parking),)),
                 ("bicis", "bicis", (("bici_ocupacion", bicis),)),
                 ("metro", "metro", (("metro", suma),)),
                 ("no2", "aire", (("no2", media),)))
        for serie, fuente, rasgos in tabla:
            mapa = self._barrio_de_puntos(serie)
            if not mapa:
                continue
            cubierto = self._cubierto(fuente, instantes)
            if not any(cubierto):
                continue
            rejilla = self.almacen.valores_en_rejilla(serie, instantes, list(mapa))
            caps = {i: p.get("cap") for i, p in self.almacen.puntos(serie).items()}
            for k, t in enumerate(instantes):
                if not cubierto[k]:
                    continue
                grupos: dict[str, list] = defaultdict(list)
                for ident, valores in rejilla.items():
                    if valores[k] is not None:
                        grupos[mapa[ident]].append((valores[k], caps.get(ident)))
                for rasgo, convertir in rasgos:
                    for b, vs in grupos.items():
                        v = convertir(vs) if vs else None
                        if v is not None:
                            salida[t][rasgo][b] = round(float(v), 2)

    def _rasgos_de_bicis(self, instantes, salida) -> None:
        """Bicis que llegan y salen: lo que sube y baja cada estación en esos diez minutos, sumado por barrio."""
        mapa = self._barrio_de_puntos("bicis")
        cubierto = self._cubierto("bicis", instantes)
        if not mapa or not any(cubierto):
            return
        llegan = [defaultdict(float) for _ in instantes]
        salen = [defaultdict(float) for _ in instantes]
        for ident, serie in self.almacen.cambios("bicis", instantes[0] - BIN, instantes[-1]).items():
            b = mapa.get(ident)
            if not b:
                continue
            for (_, v0), (t1, v1) in zip(serie, serie[1:]):
                k = _indice_bin(instantes, t1)
                if k is None or v0 is None or v1 is None:
                    continue
                (llegan if v1 > v0 else salen)[k][b] += abs(v1 - v0)
        barrios = set(mapa.values())
        for k, t in enumerate(instantes):
            if cubierto[k]:
                for b in barrios:
                    salida[t]["bici_llegadas"][b] = llegan[k].get(b, 0.0)
                    salida[t]["bici_salidas"][b] = salen[k].get(b, 0.0)

    def _rasgos_de_textos(self, instantes, salida) -> None:
        """Publicaciones (30 min), noticias (2 h), incidencias activas y textos urgentes (1 h). La ciudad cuenta
        también lo que no se ha podido situar en un barrio."""
        desde = instantes[0] - 7200
        filas = self.almacen._filas("SELECT fuente, t, barrio, urgencia, visto FROM items WHERE (t>? OR visto>?) AND t<=? "
                                    "AND (categoria IS NULL OR categoria!='fuera')", (desde, desde, instantes[-1]))
        cub = {"social": self._cubierto("bluesky", instantes), "prensa": self._cubierto("prensa", instantes),
               "alertas": self._cubierto("dgt", instantes), "urgentes": self._cubierto("prensa", instantes)}
        for k, t in enumerate(instantes):
            cuenta = {r: defaultdict(int) for r in cub}
            for fuente, ti, b, urg, visto in filas:
                if ti > t:
                    continue
                urg = urg or 0
                if fuente in REDES and ti > t - 1800:
                    cuenta["social"][b] += 1
                if fuente == "prensa" and ti > t - 7200:
                    cuenta["prensa"][b] += 1
                # Incidencias activas (vistas en los últimos 20 min); las obras y los límites de velocidad
                # (urgencia 0) son de todos los días y no cuentan.
                if fuente in ("dgt", "renfe") and urg >= 1 and (visto or ti) > t - 1200:
                    cuenta["alertas"][b] += 1
                if (fuente == "prensa" or fuente in REDES) and urg >= 2 and ti > t - 3600:
                    cuenta["urgentes"][b] += 1
            for rasgo, c in cuenta.items():
                if not cub[rasgo][k]:
                    continue
                for b in self.zonas.barrios:
                    salida[t][rasgo][b] = c.get(b, 0)
                salida[t][rasgo][CIUDAD] = sum(c.values())

    def _rasgos_de_helicopteros(self, instantes, salida) -> None:
        """Minutos con un helicóptero en vuelo por debajo de 1.500 m encima de cada barrio."""
        cubierto = self._cubierto("aviones", instantes)
        if not any(cubierto):
            return
        minutos = [defaultdict(float) for _ in instantes]
        for obj in self.almacen.rastros("helicopteros", instantes[0] - BIN, instantes[-1]).values():
            p = obj["p"]
            for i, (ti, lat, lon, alt, _) in enumerate(p):
                if alt is not None and (alt > ALTURA_HELIS or alt <= 0):      # de paso, o posado
                    continue
                k = _indice_bin(instantes, ti)
                b = self.zonas.barrio_de(lat, lon)
                if k is None or not b:
                    continue
                # Cada posición vale el rato hasta la siguiente (como mucho un minuto: si no hay más, se fue).
                siguiente = p[i + 1][0] if i + 1 < len(p) else ti + 30
                minutos[k][b] += min(60, max(0, siguiente - ti)) / 60
        for k, t in enumerate(instantes):
            if cubierto[k]:
                for b in self.zonas.barrios:
                    salida[t]["helis"][b] = round(minutos[k].get(b, 0.0), 1)

    @staticmethod
    def _agregar_ciudad(instantes, salida) -> None:
        """La ciudad entera: la media de lo continuo y la suma de los recuentos (si no se ha puesto ya)."""
        for t in instantes:
            for rasgo, por_barrio in salida[t].items():
                if CIUDAD in por_barrio or not por_barrio:
                    continue
                vals = list(por_barrio.values())
                continuo = RASGOS[rasgo]["tipo"] == "continuo"
                salida[t][rasgo][CIUDAD] = round(sum(vals) / len(vals) if continuo else sum(vals), 2)

    def guardar_rasgos(self, rasgos: dict[int, dict[str, dict[str, float]]]) -> int:
        filas = [(r, b, t, v) for t, por_rasgo in rasgos.items() for r, por_barrio in por_rasgo.items() for b, v in por_barrio.items()]
        with self.almacen._candado:
            self.almacen._bd.executemany("INSERT OR REPLACE INTO rasgos VALUES (?,?,?,?)", filas)
        return len(filas)

    def guardar_muestras(self, fin_franja: int) -> None:
        """Al cerrar cada media hora, su media va a las muestras de lo normal."""
        inicio = fin_franja - FRANJA
        festivo = int(_agenda.es_festivo(_dia(inicio)))
        with self.almacen._candado:
            self.almacen._bd.execute(
                "INSERT OR REPLACE INTO muestras SELECT rasgo, barrio, ?, ?, AVG(v), ? FROM rasgos "
                "WHERE t>? AND t<=? AND rasgo!='nivel' GROUP BY rasgo, barrio",
                (franja(inicio), semana_local(inicio), festivo, inicio, fin_franja))

    def _muestras_hasta(self, t: int) -> None:
        """Las muestras de las medias horas cerradas desde la última vez (aunque algún paso se haya saltado)."""
        fin = t // FRANJA * FRANJA
        if fin > self._ultima_franja:
            for f in range(max(self._ultima_franja + FRANJA, fin - 6 * FRANJA), fin + 1, FRANJA):
                self.guardar_muestras(f)
            self._ultima_franja = fin

    # ------------------------------------------------------------ lo normal

    def muestras(self, rasgo: str, barrio: str, t: int) -> list[float]:
        """Lo que valió este rasgo en este barrio otras veces a esta media hora. Nunca de hoy ni de después: lo que
        está pasando no puede ser su propio «normal» (ni lo de mañana, al reconstruir el histórico)."""
        fr, actual = franja(t - 1), semana_local(t - 1)
        festivo = _agenda.es_festivo(_dia(t - 1))
        if not festivo:
            filas = self.almacen._filas(
                "SELECT v FROM muestras WHERE rasgo=? AND barrio=? AND franja=? AND festivo=0 AND semana<? ORDER BY semana DESC LIMIT 8",
                (rasgo, barrio, fr, actual))
            if len(filas) >= MIN_MUESTRAS:
                return [f[0] for f in filas]
        # Con poco histórico (o si hoy es festivo): los días del mismo tipo, a la misma media hora; y si aún
        # no llega, también la media hora de antes y la de después (las primeras semanas).
        tipo, slot = tipo_dia(t - 1), fr % 48
        filas = []
        for slots in ((slot,), ((slot - 1) % 48, slot, (slot + 1) % 48)):
            franjas = [f for s in slots for f in franjas_del_tipo(tipo, s)]
            condicion = f"(franja IN ({','.join('?' * len(franjas))}) AND festivo=0)"
            if tipo == "D":
                condicion += f" OR (festivo=1 AND franja % 48 IN ({','.join(str(s) for s in slots)}))"
            filas = self.almacen._filas(
                f"SELECT v FROM muestras WHERE rasgo=? AND barrio=? AND ({condicion}) AND (semana<? OR (semana=? AND franja/48<?)) "
                "ORDER BY semana DESC, franja DESC LIMIT 15", (rasgo, barrio, *franjas, actual, actual, fr // 48))
            if len(filas) >= MIN_MUESTRAS:
                break
        return [f[0] for f in filas]

    def comparar(self, rasgo: str, barrio: str, t: int, valor: float) -> dict | None:
        """{z, normal, n} o None si aún no se sabe qué es lo normal."""
        info = RASGOS[rasgo]
        muestras = self.muestras(rasgo, barrio, t)
        if info["tipo"] == "conteo":
            prior = info.get("ciudad", info["prior"]) if barrio == CIUDAD else info["prior"]
            r = info.get("r")
            if len(muestras) < MIN_MUESTRAS and info.get("con_historia"):
                return None
            if len(muestras) < MIN_MUESTRAS:
                # Mientras no hay histórico, lo esperado es casi una suposición: se le da mucho margen.
                r = min(r or 1.5, 1.5)
            z, normal = z_conteo(valor, muestras, prior, r)
            return {"z": round(z, 2), "normal": round(normal, 2), "n": len(muestras)}
        if len(muestras) < MIN_MUESTRAS:
            return None
        z, normal = z_continuo(valor, muestras, info.get("suelo", 1.0), info.get("rel", 0.0))
        return {"z": round(z, 2), "normal": round(normal, 2), "n": len(muestras)}

    # ------------------------------------------------------------ detectar

    @staticmethod
    def desplazamiento(comparaciones: dict[str, dict[str, dict]]) -> dict[str, float]:
        """Cuánto se ha movido cada rasgo en toda la ciudad a la vez: la mediana de la z de los barrios."""
        salida = {}
        for rasgo in RASGOS:
            zs = [c[rasgo]["z"] for b, c in comparaciones.items() if b != CIUDAD and rasgo in c]
            if len(zs) >= 6:
                m = statistics.median(zs)
                if abs(m) >= 1.0:
                    salida[rasgo] = round(m, 2)
        return salida

    @staticmethod
    def evaluar(comparaciones: dict[str, dict], valores: dict[str, float], desplazamiento: dict[str, float] | None = None) -> dict:
        """Señales, puntuación de cada familia y tipos de suceso de un barrio. A cada z se le quita lo que se
        ha movido toda la ciudad (si se da `desplazamiento`)."""
        desplazamiento = desplazamiento or {}
        senales: list[Senal] = []
        for rasgo, c in comparaciones.items():
            z = c["z"] - desplazamiento.get(rasgo, 0.0)
            if abs(z) < 1.0:
                continue
            info = RASGOS[rasgo]
            familia = info["familias"].get(1 if z > 0 else -1)
            if familia:
                senales.append(Senal(familia, round(abs(z) * info.get("peso", 1.0), 2), rasgo, info["fuente"], valores.get(rasgo), c["normal"],
                                     round(z, 2)))
        # Por familia: la mejor señal de cada fuente; la puntuación es la mayor más la mitad de las dos siguientes.
        mejores: dict[str, dict[str, Senal]] = defaultdict(dict)
        for s in senales:
            if s.fuerza > getattr(mejores[s.familia].get(s.fuente), "fuerza", 0):
                mejores[s.familia][s.fuente] = s
        puntos = {}
        for familia, por_fuente in mejores.items():
            f = sorted((s.fuerza for s in por_fuente.values()), reverse=True)
            puntos[familia] = round(f[0] + 0.5 * sum(f[1:3]), 2)

        def g(familia):
            return puntos.get(familia, 0.0)

        def fuentes_fuertes(familia, umbral=2.0):
            return sum(1 for s in mejores.get(familia, {}).values() if s.fuerza >= umbral)

        tipos = []
        if fuentes_fuertes("afluencia") >= 2 or (g("afluencia") >= 3 and (g("congestion") >= 2 or g("atencion") >= 2)):
            tipos.append(("concentracion", g("afluencia") + 0.5 * max(g("congestion"), g("atencion"))))
        if fuentes_fuertes("salida") >= 2 or (g("salida") >= 3 and g("congestion") >= 1.5):
            tipos.append(("salida", g("salida") + 0.5 * g("congestion")))
        # Un helicóptero cuatro minutos o más sobre un barrio donde no suele haberlos basta por sí solo (junto
        # a un hospital con helipuerto es lo normal, y lo normal se aprende).
        helis = next((s for s in senales if s.rasgo == "helis"), None)
        helis_raro = helis is not None and (helis.valor or 0) >= 4 and helis.z >= 3
        if (g("alerta") >= 3 and (fuentes_fuertes("alerta") >= 2 or g("atencion") >= 2 or g("congestion") >= 2 or g("corte") >= 2)) or helis_raro:
            tipos.append(("incidente", max(g("alerta"), 3.0) + 0.5 * max(g("atencion"), g("congestion"), g("corte"))))
        if g("corte") >= 3 and (g("congestion") >= 1.5 or g("alerta") >= 1.5 or fuentes_fuertes("corte") >= 2):
            tipos.append(("corte", g("corte") + 0.5 * max(g("congestion"), g("alerta"))))
        elif fuentes_fuertes("congestion", 2.5) >= 2 or g("congestion") >= 4.5:
            tipos.append(("congestion", g("congestion")))
        if g("servicio") >= 3:
            tipos.append(("servicio", g("servicio")))
        if not tipos and g("atencion") >= 4:
            tipos.append(("conversacion", g("atencion")))
        # Un incidente suele traer cortes y atascos: si lo hay, es lo principal (lo demás son sus consecuencias).
        return {"puntos": puntos, "nivel": round(max(puntos.values(), default=0.0), 2),
                "tipos": sorted(((t, round(p, 2)) for t, p in tipos), key=lambda x: (x[0] != "incidente", -x[1])),
                "senales": sorted(senales, key=lambda s: -s.fuerza)[:8]}

    def paso(self, t: int | None = None) -> dict:
        """Un paso del cruce al final del intervalo que acaba en `t`: rasgos, muestras, evaluación, sucesos."""
        with self._candado:
            t = int(t or time.time()) // BIN * BIN
            rasgos = self.calcular_rasgos([t]).get(t, {})
            if not rasgos:
                return self.estado
            self.guardar_rasgos({t: rasgos})
            self._muestras_hasta(t)
            return self._evaluar(t, rasgos, vivo=True)

    def _evaluar(self, t: int, rasgos: dict[str, dict[str, float]], vivo: bool) -> dict:
        por_barrio: dict[str, dict[str, float]] = defaultdict(dict)
        for rasgo, valores in rasgos.items():
            if rasgo in RASGOS:
                for b, v in valores.items():
                    por_barrio[b][rasgo] = v
        suaves = [r for r, info in RASGOS.items() if info.get("suavizar")]
        for rasgo, b, previo in self.almacen._filas(f"SELECT rasgo, barrio, v FROM rasgos WHERE t=? AND rasgo IN ({','.join('?' * len(suaves))})",
                                                     (t - BIN, *suaves)):
            if rasgo in por_barrio.get(b, {}):
                por_barrio[b][rasgo] = round((por_barrio[b][rasgo] + previo) / 2, 2)
        comparaciones = {}
        for b, valores in por_barrio.items():
            comparaciones[b] = {r: c for r, v in valores.items() if (c := self.comparar(r, b, t, v))}
        desplazamiento = self.desplazamiento(comparaciones)
        evaluacion = {b: self.evaluar(c, por_barrio[b], desplazamiento if b != CIUDAD else None) for b, c in comparaciones.items()}
        self.guardar_rasgos({t: {"nivel": {b: e["nivel"] for b, e in evaluacion.items()}}})
        eventos = self._seguir_sucesos(t, evaluacion, desplazamiento)
        estado = self._estado(t, por_barrio, comparaciones, evaluacion, eventos, desplazamiento)
        if vivo:
            self.estado, self.ultimo_bin = estado, t
        return estado

    # ------------------------------------------------------------ seguir sucesos

    def _seguir_sucesos(self, t: int, evaluacion: dict[str, dict], desplazamiento: dict[str, float]) -> list[dict]:
        """Junta barrios vecinos con suceso, los empareja con los sucesos abiertos y cierra los que se apagan."""
        # Barrios vecinos con el mismo tipo de suceso son un solo suceso; un incendio al lado de un partido, dos.
        principal = {b: e["tipos"][0][0] for b, e in evaluacion.items() if e["tipos"] and b != CIUDAD}
        tipos_de = {b: {x for x, _ in evaluacion[b]["tipos"]} for b in principal}
        grafo = {b: {v for v in self.zonas.vecinos.get(b, set()) if v in principal and (principal[b] in tipos_de[v] or principal[v] in tipos_de[b])}
                 for b in principal}
        grupos = _componentes(set(principal), grafo)
        # Un vecino con señales (aunque no lleguen a suceso) se suma al grupo de al lado que esté más fuera de lo normal.
        for b, e in evaluacion.items():
            if b == CIUDAD or b in principal or e["nivel"] < 2.5:
                continue
            junto = [g for g in grupos if self.zonas.vecinos.get(b, set()) & g]
            if junto:
                max(junto, key=lambda g: max(evaluacion[x]["nivel"] for x in g)).add(b)
        con_suceso = set(principal)
        abiertos = self._eventos_abiertos()
        resumen = []
        for grupo in grupos:
            tipos: dict[str, float] = defaultdict(float)
            for b in grupo & con_suceso:
                for tipo, p in evaluacion[b]["tipos"]:
                    tipos[tipo] = max(tipos[tipo], p)
            tipo, puntos = max(tipos.items(), key=lambda x: x[1])
            resumen.append((grupo, tipo, puntos))
        asignados = self._emparejar(abiertos, [(g, tipo) for g, tipo, _ in resumen])
        vistos = []
        for k, (grupo, tipo, puntos) in enumerate(resumen):
            orden = sorted(grupo, key=lambda b: -evaluacion[b]["nivel"])
            senales = [_senal_dict(s, b, t) for b in orden[:4] for s in evaluacion[b]["senales"][:4]]
            vistos.append(self._actualizar_evento(asignados.get(k), t, orden, tipo, puntos, senales))
        ciudad = self._suceso_ciudad(t, evaluacion.get(CIUDAD), desplazamiento)
        if ciudad:
            puntos, senales = ciudad
            ev = next((e for e in abiertos if e["tipo"] == "ciudad"), None)
            vistos.append(self._actualizar_evento(ev, t, [CIUDAD], "ciudad", puntos, senales))
        ids = {e["id"] for e in vistos}
        for e in abiertos:
            if e["id"] not in ids and e["fin"] < t - 1800:
                e["estado"] = "cerrado"
                self._guardar_evento(e)
        return vistos

    @staticmethod
    def _suceso_ciudad(t: int, ev_ciudad: dict | None, desplazamiento: dict[str, float]) -> tuple[float, list[dict]] | None:
        """Toda la ciudad fuera de lo normal: por sus propias cifras o porque la mayoría de los barrios se
        han movido a la vez en el mismo sentido."""
        senales, puntos = [], 0.0
        # Un incidente es siempre de un sitio: el helicóptero o las noticias de un incendio ya salen en su barrio.
        # De la ciudad entera solo cuenta lo que es de verdad de conjunto (más tráfico, más gente, de qué se habla).
        tipos = [x for x in (ev_ciudad or {}).get("tipos", []) if x[0] not in ("incidente",)]
        if tipos:
            puntos = tipos[0][1]
            familias = {"concentracion": ("afluencia",), "salida": ("salida",), "congestion": ("congestion",), "corte": ("corte",),
                        "servicio": ("servicio",), "conversacion": ("atencion",)}.get(tipos[0][0], ())
            senales += [_senal_dict(s, CIUDAD, t) for s in ev_ciudad["senales"] if s.familia in familias][:5]
        for rasgo, z in desplazamiento.items():
            info = RASGOS[rasgo]
            familia = info["familias"].get(1 if z > 0 else -1)
            if familia and familia != "ambiente" and abs(z) >= 1.5:
                fuerza = abs(z) * info.get("peso", 1.0)
                puntos = max(puntos, fuerza + 1.5)
                senales.append({"t": t, "barrio": "barrios", "familia": familia, "rasgo": rasgo, "fuente": info["fuente"],
                                "valor": None, "normal": None, "z": z, "fuerza": round(fuerza, 2)})
        return (round(puntos, 2), senales) if senales and puntos >= 3 else None

    def _eventos_abiertos(self) -> list[dict]:
        return [self._fila_evento(f) for f in self.almacen._filas("SELECT * FROM eventos WHERE estado='activo'")]

    def _emparejar(self, abiertos: list[dict], grupos: list[tuple[set[str], str]]) -> dict[int, dict]:
        """Qué suceso abierto sigue cada grupo de barrios de ahora: {índice del grupo: suceso}.

        Primero, por barrios en común (el par que más comparte, antes). Después, a los grupos que quedan, el suceso
        del mismo tipo que tenga barrios al lado: algo que se mueve (una manifestación que avanza) sigue siendo lo
        mismo, pero un incendio junto a un partido no es el partido."""
        locales = [e for e in abiertos if e["tipo"] != "ciudad"]
        actuales = {e["id"]: set((e.get("evidencias") or {}).get("ahora") or e["barrios"]) for e in locales}
        pares = sorted(((len(actuales[e["id"]] & g), k, e) for k, (g, _) in enumerate(grupos) for e in locales),
                       key=lambda x: (-x[0], x[1]))
        asignados: dict[int, dict] = {}
        usados: set[str] = set()
        for comun, k, e in pares:
            if comun == 0:
                break
            if k not in asignados and e["id"] not in usados:
                asignados[k] = e
                usados.add(e["id"])
        for k, (g, tipo) in enumerate(grupos):
            if k in asignados:
                continue
            cerca = [e for e in locales if e["id"] not in usados and e["tipo"] == tipo
                     and any(self.zonas.vecinos.get(b, set()) & actuales[e["id"]] for b in g)]
            if cerca:
                e = max(cerca, key=lambda x: x["puntuacion"])
                asignados[k] = e
                usados.add(e["id"])
        return asignados

    def _actualizar_evento(self, ev: dict | None, t: int, barrios: list[str], tipo: str, puntos: float, senales: list[dict]) -> dict:
        if ev is None:
            ev = {"id": f"{t}-{min(barrios)}", "tipo": tipo, "estado": "activo", "inicio": t - BIN, "fin": t, "pico": t, "puntuacion": puntos,
                  "barrios": list(barrios), "evidencias": {"pico": senales, "ultimo": senales, "ahora": list(barrios)}, "resumen": None, "causa": None}
        else:
            ev["fin"], ev["estado"] = t, "activo"
            ev["barrios"] = ev["barrios"] + [b for b in barrios if b not in ev["barrios"]]
            ev["evidencias"] = dict(ev.get("evidencias") or {})
            if puntos > ev["puntuacion"]:
                ev["puntuacion"], ev["pico"] = puntos, t
                ev["evidencias"]["pico"] = senales
                if tipo != "conversacion":
                    ev["tipo"] = tipo
            ev["evidencias"]["ultimo"], ev["evidencias"]["ahora"] = senales, list(barrios)
        if CIUDAD in ev["barrios"]:
            ev["lat"], ev["lon"] = 39.4699, -0.3763
        else:
            centros = [(self.zonas.barrios[b]["lat"], self.zonas.barrios[b]["lon"]) for b in barrios if b in self.zonas.barrios]
            ev["lat"] = round(sum(c[0] for c in centros) / len(centros), 5) if centros else None
            ev["lon"] = round(sum(c[1] for c in centros) / len(centros), 5) if centros else None
        ev["causa"] = self.explicar(ev, t)
        ev["titulo"] = self.titular(ev)
        ev["actualizado"] = t
        self._guardar_evento(ev)
        if self.ia is not None:
            try:
                self.ia.encargar_resumen(ev["id"])
            except Exception:  # noqa: BLE001
                log.debug("IA: no se ha podido encargar el resumen", exc_info=True)
        return ev

    def _guardar_evento(self, ev: dict) -> None:
        with self.almacen._candado:
            self.almacen._bd.execute(
                "INSERT OR REPLACE INTO eventos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ev["id"], ev["tipo"], ev["estado"], ev["inicio"], ev["fin"], ev["pico"], ev["puntuacion"], ev.get("lat"), ev.get("lon"),
                 json.dumps(ev["barrios"]), ev.get("titulo"), ev.get("resumen"), json.dumps(ev.get("causa"), ensure_ascii=False),
                 json.dumps(ev.get("evidencias") or {}, ensure_ascii=False, separators=(",", ":")), ev.get("actualizado")))

    @staticmethod
    def _fila_evento(f: tuple) -> dict:
        claves = ("id", "tipo", "estado", "inicio", "fin", "pico", "puntuacion", "lat", "lon", "barrios", "titulo", "resumen", "causa",
                  "evidencias", "actualizado")
        ev = dict(zip(claves, f))
        ev["barrios"] = json.loads(ev["barrios"]) if ev["barrios"] else []
        ev["causa"] = json.loads(ev["causa"]) if ev["causa"] else None
        ev["evidencias"] = json.loads(ev["evidencias"]) if ev["evidencias"] else {}
        return ev

    def eventos(self, desde: int, hasta: int, limite: int = 200) -> list[dict]:
        return [self._fila_evento(f) for f in self.almacen._filas(
            "SELECT * FROM eventos WHERE fin>=? AND inicio<=? ORDER BY (estado='activo') DESC, puntuacion DESC LIMIT ?", (desde, hasta, limite))]

    def evento(self, ident: str) -> dict | None:
        filas = self.almacen._filas("SELECT * FROM eventos WHERE id=?", (ident,))
        return self._fila_evento(filas[0]) if filas else None

    def guardar_resumen(self, ident: str, resumen: str) -> None:
        with self.almacen._candado:
            self.almacen._bd.execute("UPDATE eventos SET resumen=? WHERE id=?", (resumen, ident))

    # ------------------------------------------------------------ explicar

    def explicar(self, ev: dict, t: int) -> dict:
        """Busca por qué: algo previsto en esos barrios (o al lado), el tiempo, lo que se publica de allí."""
        ciudad = ev["tipo"] == "ciudad"
        barrios = set(ev["barrios"]) - {CIUDAD}
        zona = set(barrios)
        for b in barrios:
            zona |= self.zonas.vecinos.get(b, set())
        desde, hasta = ev["inicio"], max(ev["fin"], t)
        candidatas = []
        for (ident, tipo, titulo, a, b, lat, lon, barrio, _fuente, url, _extra, _visto) in self.almacen._filas(
                "SELECT * FROM agenda WHERE desde<=? AND hasta>=?", (hasta + 3 * 3600, desde - 4 * 3600)):
            base = tipo.split(":")[0]
            if base in ("festivo", "fiesta"):
                if a <= hasta and b >= desde:
                    peso = (0.7 if ciudad else 0.3) if base == "festivo" else 0.6
                    candidatas.append({"tipo": base, "titulo": titulo, "peso": peso, "id": ident, "desde": a, "hasta": b})
                continue
            if ciudad:
                continue
            if barrio is None and lat is not None:
                barrio = self.zonas.barrio_de(lat, lon)
            if barrio not in zona:
                continue
            cerca = 1.0 if barrio in barrios else 0.7
            if base == "partido":
                # Se nota de dos horas y media antes a hora y media después.
                if not (a - 9000 <= hasta and b + 5400 >= desde):
                    continue
                peso = 0.95 if ev["tipo"] in ("concentracion", "salida", "congestion", "corte", "conversacion") else 0.5
            elif not (a <= hasta and b >= desde):
                continue
            elif base == "festejo":
                peso = 0.85 if ev["tipo"] in ("concentracion", "salida", "congestion", "corte", "conversacion") else 0.3
            elif base in ("obra", "ocupacion"):
                peso = 0.7 if ev["tipo"] in ("congestion", "corte") else 0.25
            elif base == "mudanza":
                peso = 0.4 if ev["tipo"] in ("congestion", "corte") else 0.1
            else:
                peso = 0.4
            candidatas.append({"tipo": base, "titulo": titulo, "peso": round(peso * cerca, 2), "id": ident, "url": url, "desde": a, "hasta": b,
                               "barrio": barrio})
        # El tiempo: la lluvia cambia el tráfico y las bicis de toda la ciudad.
        lluvia = self.almacen._filas("SELECT MAX(v) FROM indicadores WHERE clave='meteo_lluvia' AND t>? AND t<=?", (desde - 3600, hasta))
        if lluvia and lluvia[0][0] and lluvia[0][0] > 0.1:
            peso = 0.65 if ciudad or ev["tipo"] in ("congestion", "salida") else 0.2
            candidatas.append({"tipo": "lluvia", "titulo": f"Lluvia ({lluvia[0][0]:.1f} mm)", "peso": peso})
        # Lo que se publica: de esos barrios o, para la ciudad y el metro, de cualquier sitio.
        encajan = CATEGORIAS_DE.get(ev["tipo"], set())
        if ciudad or ev["tipo"] == "servicio":
            filas = self.almacen._filas(
                "SELECT id, fuente, t, titulo, url, categoria, urgencia, barrio FROM items WHERE (t>? OR visto>?) AND t<=? AND "
                "(urgencia>=2 OR categoria IN ('meteo','transporte','protesta','emergencia')) ORDER BY urgencia DESC, t DESC LIMIT 40",
                (desde - 6 * 3600, desde, hasta))
            if ev["tipo"] == "servicio":
                filas = [f for f in filas if any(p in (f[3] or "").lower() for p in ("metro", "fgv", "tranvía", "tranvia"))]
        else:
            marcas = ",".join("?" * len(zona))
            filas = self.almacen._filas(
                f"SELECT id, fuente, t, titulo, url, categoria, urgencia, barrio FROM items WHERE barrio IN ({marcas}) AND (t>? OR visto>?) AND t<=? "
                "ORDER BY urgencia DESC, t DESC LIMIT 40", (*zona, desde - 3600, desde - 3600, hasta))
        textos = []
        for ident, fuente, ti, titulo, url, cat, urg, barrio in filas:
            peso = PESO_FUENTE_TEXTO.get(fuente, 0.3) + 0.08 * (urg or 0) + (0.15 if cat in encajan else 0) + (0.1 if barrio in barrios else 0)
            textos.append({"id": ident, "fuente": fuente, "t": ti, "titulo": titulo, "url": url, "categoria": cat, "urgencia": urg,
                           "barrio": barrio, "peso": round(min(peso, 0.9), 2)})
        textos.sort(key=lambda x: (-x["peso"], -x["t"]))
        for tx in textos[:3]:
            # Una publicación suelta en redes no explica nada por sí sola: hace falta prensa, un aviso o urgencia.
            if tx["fuente"] not in REDES or (tx["urgencia"] or 0) >= 2:
                candidatas.append({"tipo": "texto", "titulo": tx["titulo"], "peso": tx["peso"], "id": tx["id"], "url": tx["url"], "fuente": tx["fuente"]})
        candidatas.sort(key=lambda c: -c["peso"])
        probable = candidatas[0] if candidatas and candidatas[0]["peso"] >= 0.5 else None
        return {"probable": probable, "candidatas": candidatas[:6], "textos": textos[:10], "explicado": probable is not None}

    def titular(self, ev: dict) -> str:
        causa = (ev.get("causa") or {}).get("probable")
        if ev["tipo"] == "ciudad":
            # Se dice qué se ha movido y no qué significa: la lluvia llena las estaciones de bicis sin que
            # «llegue gente» a ningún sitio.
            senales = sorted((ev.get("evidencias") or {}).get("ultimo") or [], key=lambda s: -(s.get("fuerza") or 0))
            if senales:
                s = senales[0]
                base = f"Toda la ciudad: {RASGOS[s['rasgo']]['nombre'].lower()} {'por encima' if (s.get('z') or 0) > 0 else 'por debajo'} de lo normal"
            else:
                base = "Toda la ciudad fuera de lo normal"
        else:
            principales = [b for b in (ev.get("evidencias") or {}).get("ahora", []) if b != CIUDAD] or ev["barrios"]
            nombres = [self.zonas.nombre(b) or b for b in principales[:3]]
            lugar = " y ".join([", ".join(nombres[:-1]), nombres[-1]]) if len(nombres) > 1 else (nombres[0] if nombres else "")
            if len(principales) > 3:
                lugar += f" (+{len(principales) - 3})"
            conector = " " if ev["tipo"] == "conversacion" else " en "
            base = f"{TIPOS_SUCESO.get(ev['tipo'], 'Suceso')}{conector}{lugar}"
        if causa:
            return f"{base} — {causa['titulo'][:90]}"
        return base if ev["tipo"] == "ciudad" else f"{base} — sin causa conocida"

    # ------------------------------------------------------------ estado y reconstrucción

    def _estado(self, t: int, por_barrio: dict, comparaciones: dict, evaluacion: dict, eventos: list[dict], desplazamiento: dict) -> dict:
        barrios = {}
        for b, e in evaluacion.items():
            barrios[b] = {"nivel": e["nivel"], "familias": e["puntos"], "tipos": [x[0] for x in e["tipos"]],
                          "senales": [_senal_dict(s, b, t) for s in e["senales"][:5]],
                          "valores": por_barrio.get(b, {}),
                          "normal": {r: c["normal"] for r, c in comparaciones.get(b, {}).items()}}
        primera = self.almacen._filas("SELECT MIN(semana) FROM muestras")[0][0]
        semanas = 0 if primera is None else (semana_local(t) - primera)
        return {"t": t, "barrios": barrios, "desplazamiento": desplazamiento, "activos": [e["id"] for e in eventos],
                "aprendiendo": {"semanas": semanas, "listo": semanas >= 4}}

    def reconstruir(self, desde: int, hasta: int, sucesos_desde: int | None = None, por_tanda: int = 72) -> int:
        """Calcula lo que falte de un rato pasado (al arrancar con histórico de antes): los rasgos, las muestras
        de lo normal y, desde `sucesos_desde`, los sucesos. Devuelve cuántos intervalos ha calculado."""
        with self._candado:
            hechos = {f[0] for f in self.almacen._filas("SELECT DISTINCT t FROM rasgos WHERE t>=? AND t<=? AND rasgo='nivel'", (desde, hasta))}
            faltan = [t for t in range(desde // BIN * BIN + BIN, hasta + 1, BIN) if t not in hechos]
            for i in range(0, len(faltan), por_tanda):
                self.guardar_rasgos(self.calcular_rasgos(faltan[i:i + por_tanda]))
            for f in range(desde // FRANJA * FRANJA + FRANJA, hasta + 1, FRANJA):
                self.guardar_muestras(f)
            self._ultima_franja = max(self._ultima_franja, hasta // FRANJA * FRANJA)
            for t in faltan:
                rasgos: dict[str, dict[str, float]] = defaultdict(dict)
                if sucesos_desde is not None and t >= sucesos_desde:
                    for rasgo, barrio, v in self.almacen._filas("SELECT rasgo, barrio, v FROM rasgos WHERE t=? AND rasgo!='nivel'", (t,)):
                        rasgos[rasgo][barrio] = v
                if rasgos:
                    self._evaluar(t, rasgos, vivo=(t == faltan[-1]))
                else:
                    # Un «nivel» de la ciudad a 0 marca el intervalo como hecho, para no repetirlo al volver a abrir.
                    self.guardar_rasgos({t: {"nivel": {CIUDAD: 0.0}}})
            return len(faltan)

    # ------------------------------------------------------------ consultas para la sala

    def serie(self, rasgo: str, barrios: list[str], desde: int, hasta: int) -> dict[str, list[tuple[int, float]]]:
        marcas = ",".join("?" * len(barrios))
        salida: dict[str, list] = defaultdict(list)
        for b, t, v in self.almacen._filas(f"SELECT barrio, t, v FROM rasgos WHERE rasgo=? AND barrio IN ({marcas}) AND t>? AND t<=? ORDER BY t",
                                           (rasgo, *barrios, desde, hasta)):
            salida[b].append((t, v))
        return dict(salida)

    def perfil(self, rasgo: str, tipo: str) -> dict[str, list[float | None]]:
        """Cómo es un tipo de día (L, S, D) media hora a media hora, con todo el histórico: {barrio: [48 valores]}."""
        if tipo == "D":
            filas = self.almacen._filas("SELECT barrio, franja % 48, AVG(v) FROM muestras WHERE rasgo=? AND (festivo=1 OR franja>=288) "
                                        "GROUP BY barrio, franja % 48", (rasgo,))
        else:
            franjas = [f for s in range(48) for f in franjas_del_tipo(tipo, s)]
            filas = self.almacen._filas(f"SELECT barrio, franja % 48, AVG(v) FROM muestras WHERE rasgo=? AND festivo=0 AND franja IN "
                                        f"({','.join(map(str, franjas))}) GROUP BY barrio, franja % 48", (rasgo,))
        salida: dict[str, list] = defaultdict(lambda: [None] * 48)
        for b, i, v in filas:
            salida[b][int(i)] = round(v, 2)
        return dict(salida)

    def perfil_de_dia(self, rasgo: str, dia: str) -> dict[str, list[float | None]]:
        """Un día concreto (AAAA-MM-DD) media hora a media hora, de los rasgos guardados (45 días)."""
        inicio = int(datetime.fromisoformat(dia).timestamp())
        salida: dict[str, list] = defaultdict(lambda: [None] * 48)
        for b, i, v in self.almacen._filas("SELECT barrio, (t-1-?)/1800 AS i, AVG(v) FROM rasgos WHERE rasgo=? AND t>? AND t<=? GROUP BY barrio, i",
                                           (inicio, rasgo, inicio, inicio + 86400)):
            if 0 <= i < 48:
                salida[b][int(i)] = round(v, 2)
        return dict(salida)

    def dias_con_datos(self) -> list[str]:
        filas = self.almacen._filas("SELECT MIN(t), MAX(t) FROM rasgos WHERE rasgo='trafico' OR rasgo='bici_ocupacion'")
        if not filas or filas[0][0] is None:
            return []
        dias, t = [], filas[0][0]
        while t <= filas[0][1]:
            d = _dia(t).isoformat()
            if not dias or dias[-1] != d:
                dias.append(d)
            t += 3600
        ultimo = _dia(filas[0][1]).isoformat()
        return dias if dias and dias[-1] == ultimo else dias + [ultimo]


def _senal_dict(s: Senal, barrio: str, t: int) -> dict:
    return {"t": t, "barrio": barrio, "familia": s.familia, "rasgo": s.rasgo, "fuente": s.fuente, "valor": s.valor, "normal": s.normal,
            "z": s.z, "fuerza": s.fuerza}


def _indice_bin(instantes: list[int], t: int) -> int | None:
    """El intervalo (t-BIN, t] de la lista al que pertenece `t`."""
    k = (t + BIN - 1) // BIN * BIN
    if not instantes or k < instantes[0] or k > instantes[-1]:
        return None
    i = (k - instantes[0]) // BIN
    return i if 0 <= i < len(instantes) and instantes[i] == k else None


def _componentes(nodos: set[str], vecinos: dict[str, set[str]]) -> list[set[str]]:
    pendientes, grupos = set(nodos), []
    while pendientes:
        semilla = pendientes.pop()
        grupo, cola = {semilla}, [semilla]
        while cola:
            for v in vecinos.get(cola.pop(), ()):
                if v in pendientes:
                    pendientes.discard(v)
                    grupo.add(v)
                    cola.append(v)
        grupos.append(grupo)
    return grupos
