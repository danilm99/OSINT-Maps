"""Las fuentes del pulso: qué se pregunta y cómo se lee.

Cada fuente es una función que recibe la sesión HTTP y devuelve una `Toma`: lo que ha
visto en ese momento. Ninguna guarda nada ni sabe de horarios; eso es cosa del recolector.

Una toma puede traer tres cosas:

- **valores**: una cifra por punto fijo (bicis en una estación, plazas en un aparcamiento,
  estado de un tramo de calle). Van agrupados por «serie».
- **indicadores**: cifras de toda la ciudad calculadas con esos valores (bicis ancladas en
  total, tramos atascados). Son las curvas de la línea de tiempo.
- **objetos**: cosas que se mueven (aviones, trenes), con su posición.

Todas las fuentes son públicas, gratuitas y sin clave.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import requests

GEOPORTAL = "https://geoportal.valencia.es/server/rest/services/OPENDATA"      # datos abiertos del Ajuntament de València
ADSB = "https://api.adsb.lol/v2"
RENFE = "https://gtfsrt.renfe.com/vehicle_positions.json"

# El centro del mapa del pulso: la plaza del Ayuntamiento. Los aviones se piden alrededor de aquí.
CENTRO = (39.4699, -0.3763)
MILLAS_AVIONES = 40             # unos 74 km: entra la aproximación a Manises entera
# Los trenes llegan de toda España; se guardan los de esta caja (oeste, sur, este, norte): València y sus Cercanías.
CAJA_TRENES = (-1.35, 38.75, 0.05, 40.05)
PIES = 0.3048


@dataclass
class Punto:
    """Un punto fijo que se mide: dónde está y cómo se llama. Se guarda una vez y se actualiza si cambia."""
    nombre: str = ""
    lat: float | None = None
    lon: float | None = None
    cap: float | None = None            # capacidad: anclajes de la estación, plazas del aparcamiento
    geo: list | None = None             # para los tramos de calle: [[lat, lon], ...]


@dataclass
class Objeto:
    """Algo que se mueve, visto en un momento."""
    id: str
    lat: float
    lon: float
    nombre: str = ""
    rumbo: float | None = None
    alt: float | None = None            # metros; None si no se sabe, 0 si está en tierra


@dataclass
class Toma:
    valores: dict[str, dict[str, float]] = field(default_factory=dict)         # serie -> id -> valor
    puntos: dict[str, dict[str, Punto]] = field(default_factory=dict)          # serie -> id -> punto
    indicadores: dict[str, float] = field(default_factory=dict)
    objetos: dict[str, list[Objeto]] = field(default_factory=dict)             # tipo -> objetos

    @property
    def n(self) -> int:
        """Cuántas cosas trae, para el registro."""
        return sum(len(v) for v in self.valores.values()) + sum(len(o) for o in self.objetos.values())


@dataclass(frozen=True)
class Fuente:
    id: str
    nombre: str
    cada: float                         # segundos entre dos tomas
    tomar: Callable[..., Toma]
    grupo: str = "ciudad"               # las de un mismo grupo se preguntan una detrás de otra
    origen: str = ""                    # de quién son los datos, para citarlo


def _numero(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _media(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def _poner(destino: dict[str, float], clave: str, valor: float | None, decimales: int = 1) -> None:
    if valor is not None:
        destino[clave] = round(valor, decimales)


# --------------------------------------------------------------------------
# Geoportal de València
# --------------------------------------------------------------------------

def pedir_geoportal(sesion: requests.Session, servicio: str, *, geometria: bool = True, campos: str = "*",
                    por_pagina: int = 1000, timeout: float = 25.0) -> list[dict]:
    """Todos los elementos de una capa del geoportal («Trafico/228»), como GeoJSON.

    El geoportal entrega como mucho unos miles de elementos por petición y avisa con
    `exceededTransferLimit` cuando quedan más: se sigue pidiendo desde donde se quedó.
    """
    tema, numero = servicio.split("/")
    url = f"{GEOPORTAL}/{tema}/MapServer/{numero}/query"
    elementos: list[dict] = []
    for _ in range(40):                 # tope de seguridad: 40.000 elementos
        resp = sesion.get(url, timeout=timeout, params={
            "where": "1=1", "outFields": campos, "outSR": 4326, "f": "geojson",
            "returnGeometry": "true" if geometria else "false", "geometryPrecision": 5,
            "resultOffset": len(elementos), "resultRecordCount": por_pagina,
        })
        resp.raise_for_status()
        datos = resp.json()
        if "features" not in datos:     # el geoportal contesta 200 también cuando falla, con {"error": ...}
            raise ValueError(f"respuesta sin elementos de {servicio}: {str(datos)[:120]}")
        pagina = datos["features"]
        elementos.extend(pagina)
        mas = datos.get("exceededTransferLimit") or (datos.get("properties") or {}).get("exceededTransferLimit")
        if not mas or not pagina:
            break
    return elementos


def _coordenadas(elemento: dict) -> tuple[float | None, float | None]:
    g = elemento.get("geometry") or {}
    if g.get("type") == "Point" and g.get("coordinates"):
        lon, lat = g["coordinates"][:2]
        return round(lat, 6), round(lon, 6)
    return None, None


def _linea(elemento: dict) -> list | None:
    """Los puntos de un tramo de calle, como [[lat, lon], ...]. Si viene partido en varios, el más largo."""
    g = elemento.get("geometry") or {}
    if g.get("type") == "LineString":
        trozos = [g.get("coordinates") or []]
    elif g.get("type") == "MultiLineString":
        trozos = g.get("coordinates") or []
    else:
        return None
    mejor = max(trozos, key=len, default=[])
    return [[round(p[1], 5), round(p[0], 5)] for p in mejor] if len(mejor) > 1 else None


def tomar_bicis(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Valenbisi: bicis ancladas en cada estación. Cuantas menos hay ancladas, más hay rodando."""
    toma = Toma(valores={"bicis": {}}, puntos={"bicis": {}})
    ancladas = anclajes = vacias = llenas = 0
    for e in pedir_geoportal(sesion, "Trafico/228", geometria=geometria):
        p = e.get("properties") or {}
        bicis, huecos, total = _numero(p.get("available")), _numero(p.get("free")), _numero(p.get("total"))
        if p.get("number") is None or bicis is None or p.get("open") == "F":
            continue
        ident = str(int(p["number"])) if _numero(p["number"]) is not None else str(p["number"])
        toma.valores["bicis"][ident] = bicis
        if geometria:
            lat, lon = _coordenadas(e)
            toma.puntos["bicis"][ident] = Punto(str(p.get("address") or p.get("name") or "").strip(), lat, lon, total)
        ancladas += bicis
        anclajes += total if total else bicis + (huecos or 0)
        vacias += bicis == 0
        llenas += huecos == 0
    if toma.valores["bicis"]:
        toma.indicadores = {"bicis_ancladas": ancladas, "bicis_vacias": vacias, "bicis_llenas": llenas}
        if anclajes:
            _poner(toma.indicadores, "bicis_fuera", 100 * (1 - ancladas / anclajes))
    return toma


def tomar_parking(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Aparcamientos públicos: plazas libres en cada uno."""
    toma = Toma(valores={"parking": {}}, puntos={"parking": {}})
    libres_total = plazas_total = 0
    for e in pedir_geoportal(sesion, "Trafico/194", geometria=geometria):
        p = e.get("properties") or {}
        libres, plazas = _numero(p.get("plazaslibr")), _numero(p.get("plazastota"))
        if p.get("id_aparcamiento") is None or libres is None:
            continue
        ident = str(p["id_aparcamiento"])
        toma.valores["parking"][ident] = libres
        if geometria:
            lat, lon = _coordenadas(e)
            toma.puntos["parking"][ident] = Punto(str(p.get("nombre") or "").strip().title(), lat, lon, plazas)
        if plazas:
            libres_total += min(libres, plazas)
            plazas_total += plazas
    if plazas_total:
        toma.indicadores = {"parking_libres": libres_total}
        _poner(toma.indicadores, "parking_ocupacion", 100 * (1 - libres_total / plazas_total))
    return toma


def estado_trafico(bruto) -> int | None:
    """El estado de un tramo, de 0 (fluido) a 3 (cortado). El Ayuntamiento usa del 0 al 3 para la
    red principal y del 5 al 8 para los pasos inferiores, con el mismo significado; el 4 y el 9
    son «sin datos»."""
    n = _numero(bruto)
    if n is None:
        return None
    n = int(n)
    if 5 <= n <= 8:
        n -= 5
    return n if 0 <= n <= 3 else None


def tomar_trafico(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Estado del tráfico por tramos de calle: fluido, denso, congestionado o cortado."""
    toma = Toma(valores={"trafico": {}}, puntos={"trafico": {}})
    for e in pedir_geoportal(sesion, "Trafico/192", geometria=geometria):
        p = e.get("properties") or {}
        estado = estado_trafico(p.get("estado"))
        if p.get("idtramo") is None or estado is None:
            continue
        ident = str(p["idtramo"])
        toma.valores["trafico"][ident] = estado
        if geometria:
            linea = _linea(e)
            medio = linea[len(linea) // 2] if linea else (None, None)
            toma.puntos["trafico"][ident] = Punto(str(p.get("denominacion") or "").strip().rstrip("."), medio[0], medio[1], None, linea)
    estados = list(toma.valores["trafico"].values())
    if estados:
        abiertos = [x for x in estados if x < 3]
        toma.indicadores = {"trafico_denso": sum(1 for x in estados if x in (1, 2)), "trafico_cortado": sum(1 for x in estados if x == 3)}
        if abiertos:        # 0 = todo fluido, 100 = todo congestionado; los cortes no cuentan (son obras, no atascos)
            _poner(toma.indicadores, "trafico_indice", 100 * sum(abiertos) / (2 * len(abiertos)))
    return toma


def _tomar_aforos(sesion: requests.Session, servicio: str, serie: str, geometria: bool) -> Toma:
    toma = Toma(valores={serie: {}}, puntos={serie: {}})
    for e in pedir_geoportal(sesion, servicio, geometria=geometria, campos="idpm,ih"):
        p = e.get("properties") or {}
        ih = _numero(p.get("ih"))
        if p.get("idpm") is None or ih is None or ih < 0:
            continue
        ident = str(p["idpm"])
        toma.valores[serie][ident] = ih
        if geometria:
            lat, lon = _coordenadas(e)
            toma.puntos[serie][ident] = Punto(f"Punto de aforo {ident}", lat, lon)
    # La media por punto y no la suma: cada rato hay espiras que no informan, y la suma bailaría con ellas.
    _poner(toma.indicadores, serie, _media(list(toma.valores[serie].values())), 0)
    return toma


def tomar_aforos(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Espiras bajo el asfalto: vehículos por hora en más de mil puntos de la ciudad."""
    return _tomar_aforos(sesion, "Trafico/208", "aforo", geometria)


def tomar_aforos_bici(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Espiras del carril bici: bicis y patinetes por hora."""
    return _tomar_aforos(sesion, "Trafico/225", "aforo_bici", geometria)


CONTAMINANTES = ("no2", "pm10", "pm25", "o3")


def tomar_aire(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Estaciones de calidad del aire: NO2, partículas y ozono (microgramos por metro cúbico)."""
    toma = Toma(valores={c: {} for c in CONTAMINANTES}, puntos={c: {} for c in CONTAMINANTES})
    for e in pedir_geoportal(sesion, "MedioAmbiente/156", geometria=geometria):
        p = e.get("properties") or {}
        ident = str(p.get("fiwareid") or p.get("objectid") or "")
        if not ident:
            continue
        lat, lon = _coordenadas(e) if geometria else (None, None)
        for c in CONTAMINANTES:
            v = _numero(p.get(c))
            if v is None or v < 0:
                continue
            toma.valores[c][ident] = v
            if geometria:
                toma.puntos[c][ident] = Punto(str(p.get("nombre") or "").strip(), lat, lon)
    for c in CONTAMINANTES:
        _poner(toma.indicadores, f"aire_{c}", _media(list(toma.valores[c].values())))
    return toma


def tomar_meteo(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Estaciones meteorológicas municipales. Solo la media de la ciudad: es contexto para leer lo demás
    (un día de lluvia cambia el tráfico y las bicis)."""
    toma = Toma()
    campos = {"meteo_temperatura": "temperatur", "meteo_viento": "viento_vel", "meteo_lluvia": "precipitac"}
    leidos: dict[str, list[float]] = {k: [] for k in campos}
    for e in pedir_geoportal(sesion, "MedioAmbiente/157", geometria=False):
        p = e.get("properties") or {}
        for clave, campo in campos.items():
            v = _numero(p.get(campo))
            if v is not None and -30 < v < 400:
                leidos[clave].append(v)
    for clave, valores in leidos.items():
        _poner(toma.indicadores, clave, _media(valores))
    return toma


# --------------------------------------------------------------------------
# Lo que se mueve
# --------------------------------------------------------------------------

def tomar_aviones(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Aviones en vuelo alrededor de València (adsb.lol: receptores de aficionados de todo el mundo)."""
    lat, lon = CENTRO
    resp = sesion.get(f"{ADSB}/lat/{lat:.3f}/lon/{lon:.3f}/dist/{MILLAS_AVIONES}", timeout=12)
    resp.raise_for_status()
    aviones = []
    for a in resp.json().get("ac") or []:
        if a.get("lat") is None or a.get("lon") is None or not a.get("hex"):
            continue
        if (_numero(a.get("seen_pos")) or 0) > 60:      # posición de hace más de un minuto: ya no está ahí
            continue
        alt = a.get("alt_baro")
        metros = 0.0 if alt == "ground" else (round(alt * PIES) if isinstance(alt, (int, float)) else None)
        nombre = (a.get("flight") or "").strip() or a.get("r") or a["hex"]
        aviones.append(Objeto(str(a["hex"]), round(a["lat"], 5), round(a["lon"], 5), nombre, _numero(a.get("track")), metros))
    toma = Toma(objetos={"aviones": aviones})
    en_el_aire = [a for a in aviones if a.alt is None or a.alt > 0]
    toma.indicadores = {"aviones": len(en_el_aire),
                        # Por debajo de 3.000 m a esta distancia: despegando, aterrizando, o un helicóptero o avioneta.
                        "aviones_bajos": sum(1 for a in en_el_aire if a.alt is not None and a.alt < 3000)}
    return toma


def tomar_trenes(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Trenes de Cercanías: Renfe publica dónde va cada uno. Se guardan los del área de València."""
    resp = sesion.get(RENFE, timeout=20)
    resp.raise_for_status()
    oeste, sur, este, norte = CAJA_TRENES
    trenes = []
    for entidad in resp.json().get("entity") or []:
        v = entidad.get("vehicle") or {}
        pos = v.get("position") or {}
        lat, lon = _numero(pos.get("latitude")), _numero(pos.get("longitude"))
        if lat is None or lon is None or not (sur <= lat <= norte and oeste <= lon <= este):
            continue
        vehiculo = v.get("vehicle") or {}
        ident = str(vehiculo.get("id") or (v.get("trip") or {}).get("tripId") or "")
        if ident:
            trenes.append(Objeto(ident, round(lat, 5), round(lon, 5), str(vehiculo.get("label") or "").split("-PLATF")[0].strip() or ident))
    toma = Toma(objetos={"trenes": trenes})
    toma.indicadores = {"trenes": len(trenes)}
    return toma


FUENTES: tuple[Fuente, ...] = (
    Fuente("bicis", "Valenbisi", 120, tomar_bicis, origen="Ajuntament de València"),
    Fuente("parking", "Aparcamientos", 300, tomar_parking, origen="Ajuntament de València"),
    Fuente("trafico", "Estado del tráfico", 180, tomar_trafico, origen="Ajuntament de València"),
    Fuente("aforo", "Aforos de vehículos", 600, tomar_aforos, origen="Ajuntament de València"),
    Fuente("aforo_bici", "Aforos de bicis", 600, tomar_aforos_bici, origen="Ajuntament de València"),
    Fuente("aire", "Calidad del aire", 900, tomar_aire, origen="Ajuntament de València"),
    Fuente("meteo", "Meteorología", 900, tomar_meteo, origen="Ajuntament de València"),
    Fuente("aviones", "Aviones", 20, tomar_aviones, grupo="cielo", origen="adsb.lol"),
    Fuente("trenes", "Trenes de Cercanías", 30, tomar_trenes, grupo="vias", origen="Renfe"),
)

# Qué es cada indicador: su nombre para el visor, su unidad y la fuente de la que sale.
INDICADORES: dict[str, dict] = {
    "bicis_fuera": {"nombre": "Valenbisi: anclajes vacíos", "unidad": "%", "fuente": "bicis", "nota": "sube cuando hay más bicis rodando"},
    "bicis_ancladas": {"nombre": "Bicis ancladas", "unidad": "bicis", "fuente": "bicis"},
    "bicis_vacias": {"nombre": "Estaciones sin bicis", "unidad": "estaciones", "fuente": "bicis"},
    "bicis_llenas": {"nombre": "Estaciones sin huecos", "unidad": "estaciones", "fuente": "bicis"},
    "parking_ocupacion": {"nombre": "Aparcamientos ocupados", "unidad": "%", "fuente": "parking"},
    "parking_libres": {"nombre": "Plazas libres", "unidad": "plazas", "fuente": "parking"},
    "trafico_indice": {"nombre": "Tráfico", "unidad": "sobre 100", "fuente": "trafico", "nota": "0 es todo fluido y 100 todo congestionado"},
    "trafico_denso": {"nombre": "Tramos densos o congestionados", "unidad": "tramos", "fuente": "trafico"},
    "trafico_cortado": {"nombre": "Tramos cortados", "unidad": "tramos", "fuente": "trafico"},
    "aforo": {"nombre": "Vehículos por hora", "unidad": "por punto de aforo", "fuente": "aforo"},
    "aforo_bici": {"nombre": "Bicis por hora", "unidad": "por punto de aforo", "fuente": "aforo_bici"},
    "aire_no2": {"nombre": "NO₂", "unidad": "µg/m³", "fuente": "aire"},
    "aire_pm10": {"nombre": "Partículas PM10", "unidad": "µg/m³", "fuente": "aire"},
    "aire_pm25": {"nombre": "Partículas PM2,5", "unidad": "µg/m³", "fuente": "aire"},
    "aire_o3": {"nombre": "Ozono", "unidad": "µg/m³", "fuente": "aire"},
    "meteo_temperatura": {"nombre": "Temperatura", "unidad": "°C", "fuente": "meteo"},
    "meteo_viento": {"nombre": "Viento", "unidad": "m/s", "fuente": "meteo"},
    "meteo_lluvia": {"nombre": "Lluvia", "unidad": "mm", "fuente": "meteo"},
    "aviones": {"nombre": "Aviones en el aire", "unidad": "a menos de 75 km", "fuente": "aviones"},
    "aviones_bajos": {"nombre": "Aviones por debajo de 3.000 m", "unidad": "aviones", "fuente": "aviones"},
    "trenes": {"nombre": "Trenes de Cercanías circulando", "unidad": "trenes", "fuente": "trenes"},
}
# Las series de puntos fijos: de qué fuente sale cada una.
SERIES: dict[str, str] = {"bicis": "bicis", "parking": "parking", "trafico": "trafico", "aforo": "aforo", "aforo_bici": "aforo_bici",
                          **{c: "aire" for c in CONTAMINANTES}}
