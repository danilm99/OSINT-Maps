"""Lo previsto: obras, ocupaciones de la vía pública, festejos, mudanzas, partidos y festivos.
Y lo que llega una vez al día: el ruido de los sonómetros de Russafa.

Lo previsto sirve para explicar lo que pasa: si el tráfico se dispara en una calle con una
obra que empezó ayer, o si Valenbisi se vacía alrededor de Mestalla dos horas antes de un
partido, no hace falta buscar más. El cruce (cruce.py) lo mira antes de dar algo por raro.
"""

from __future__ import annotations

import csv
import io
import time
from datetime import date, datetime, timedelta, timezone

import requests

from .fuentes import Cita, Fuente, Punto, Toma, _coordenadas, _linea, _numero, pedir_geoportal

# Capas del geoportal con cosas que ocupan la calle unas fechas: (capa, tipo).
PLANIFICADOS = (("Trafico/209", "ocupacion"), ("Trafico/235", "obra"), ("Trafico/233", "festejo"), ("Trafico/234", "mudanza"))

SPORTSDB = "https://www.thesportsdb.com/api/v1/json/123"
# Equipos que juegan en la ciudad: nombre en TheSportsDB -> (deporte, campo, lat, lon)
EQUIPOS = {
    "Valencia": ("Soccer", "Mestalla", 39.4746, -0.3583),
    "Levante": ("Soccer", "Ciutat de València", 39.4947, -0.3647),
    "Valencia Basket": ("Basketball", "Roig Arena", 39.4560, -0.3530),
}
# Recintos donde cabe mucha gente: (nombre, palabras que lo delatan en un titular, lat, lon, aforo aproximado).
# Los aforos son los que dan los propios recintos, redondeados; sirven para saber de qué tamaño es lo previsto.
RECINTOS = (
    ("Mestalla", ("mestalla",), 39.4746, -0.3583, 49000),
    ("Ciutat de València", ("ciutat de valència", "ciutat de valencia", "estadi ciutat"), 39.4947, -0.3647, 26000),
    ("Roig Arena", ("roig arena",), 39.4560, -0.3530, 15600),
    ("La Fonteta", ("fonteta",), 39.4577, -0.3577, 8500),
    ("Plaza de Toros", ("plaza de toros", "plaça de bous"), 39.4667, -0.3757, 10500),
    ("Palau de les Arts", ("palau de les arts", "les arts reina sofía"), 39.4578, -0.3559, 1400),
    ("Palau de la Música", ("palau de la música", "palau de la musica"), 39.4687, -0.3602, 1800),
    ("Feria Valencia", ("feria valencia", "fira valència"), 39.5030, -0.4270, 20000),
    ("Ciutat de les Arts i les Ciències", ("ciudad de las artes", "ciutat de les arts", "l'umbracle", "umbracle", "hemisfèric", "oceanogràfic"), 39.4548, -0.3505, 10000),
    ("La Marina", ("la marina de valència", "marina de valencia", "marina sur", "tinglado"), 39.4603, -0.3270, 15000),
    ("Plaza del Ayuntamiento", ("plaza del ayuntamiento", "plaça de l'ajuntament"), 39.4697, -0.3763, 20000),
)


def recinto_de(titulo: str | None, lat: float | None = None, lon: float | None = None) -> dict | None:
    """El recinto de algo previsto: por el nombre en el título o, si no, por estar a menos de unos 250 m."""
    t = (titulo or "").lower()
    for nombre, pistas, la, lo, aforo in RECINTOS:
        if any(p in t for p in pistas):
            return {"nombre": nombre, "lat": la, "lon": lo, "aforo": aforo}
    if lat is not None and lon is not None:
        for nombre, _, la, lo, aforo in RECINTOS:
            if abs(la - lat) < 0.0022 and abs(lo - lon) < 0.0029:
                return {"nombre": nombre, "lat": la, "lon": lo, "aforo": aforo}
    return None


RUIDO = ("https://datosbi.vlci.valencia.es/pentaho/plugin/cda/api/doQuery?path=/public/vlci/datosabiertos/"
         "calidadambiental_sonometros_ruzafa_diarios.cda&dataAccessId=sqlSonometrosRuzafaDaily&outputType=CSV&_TRUST_USER_=publicoda")
# Sonómetros de Russafa (Ajuntament): código -> dirección. La posición sale del nomenclátor.
SONOMETROS = {
    "T248652": "calle Sueca esquina calle Denia", "T248680": "calle Sueca, 32", "T248684": "calle Sueca, 61",
    "T248683": "calle Sueca, 2", "T248672": "calle Puerto Rico, 21", "T248679": "calle Matías Perelló esquina calle Doctor Sumsi",
    "T248661": "calle General Prim esquina calle Donoso Cortés", "T248676": "calle Salvador Abril esquina calle Maestro José Serrano",
    "T248669": "calle Doctor Serrano, 21", "T248682": "calle Cuba, 3", "T248670": "calle Carles Cervera esquina calle Reina Doña María",
    "T248678": "calle Carles Cervera, 34", "T251234": "calle Cura Femenía, 14", "T248677": "calle Vivons esquina calle Cádiz",
    "T248655": "calle Cádiz, 3", "T248671": "calle Cádiz, 16",
}


def _ms(v) -> int | None:
    n = _numero(v)
    return int(n / 1000) if n else None


def tomar_planificados(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Lo que ocupa la calle con fecha: obras, ocupaciones, festejos y mudanzas del geoportal."""
    citas, ok = [], 0
    for capa, tipo in PLANIFICADOS:
        try:
            elementos = pedir_geoportal(sesion, capa)
            ok += 1
        except Exception:  # noqa: BLE001
            continue
        for e in elementos:
            p = e.get("properties") or {}
            desde = _ms(p.get("fecha_inicio") or p.get("fecha_inicio_periodo") or p.get("fecha_ini") or p.get("fechainicio"))
            hasta = _ms(p.get("fecha_fin") or p.get("fecha_fin_periodo") or p.get("fechafin"))
            if not desde or not hasta or hasta < time.time() - 7 * 86400:
                continue
            lat, lon = _coordenadas(e)
            if lat is None:
                linea = _linea(e)
                if linea:
                    lat, lon = linea[len(linea) // 2]
            ident = p.get("id_incidencia") or p.get("objectid") or p.get("gid")
            clase = str(p.get("tipo_incidencia") or p.get("ocupacion") or "").strip().lower()
            descripcion = " · ".join(str(x).strip() for x in (p.get("desc_incidencia"), p.get("desc_calle"), p.get("tipo_afectacion"),
                                                               p.get("ocupacion"), p.get("descripcion"), p.get("nombre")) if x and str(x).strip())
            sub = f"{tipo}:{clase}" if clase and tipo == "ocupacion" else tipo
            titulo = {"ocupacion": "Ocupación de la vía", "obra": "Obra", "festejo": "Festejo", "mudanza": "Mudanza"}[tipo]
            if clase and tipo == "ocupacion":
                titulo = clase.capitalize()
            citas.append(Cita(f"{tipo}:{ident}", sub, f"{titulo}{' — ' + descripcion if descripcion else ''}"[:200], desde, hasta,
                              lat, lon, fuente="Ajuntament de València", extra={k: p.get(k) for k in ("estado", "tipo_afectacion") if p.get(k)}))
    if not ok:
        raise RuntimeError("el geoportal no ha contestado")
    return Toma(agenda=citas)


_IDS_EQUIPOS: dict[str, str] = {}


def _id_equipo(sesion: requests.Session, nombre: str, deporte: str) -> str | None:
    if nombre not in _IDS_EQUIPOS:
        resp = sesion.get(f"{SPORTSDB}/searchteams.php", params={"t": nombre}, timeout=20)
        resp.raise_for_status()
        for equipo in resp.json().get("teams") or []:
            if equipo.get("strSport") == deporte and equipo.get("strCountry") in ("Spain", "España", None) and equipo.get("strTeam") == nombre:
                _IDS_EQUIPOS[nombre] = str(equipo["idTeam"])
                break
        else:
            return None
    return _IDS_EQUIPOS[nombre]


def tomar_partidos(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Los partidos en casa de los equipos de la ciudad (TheSportsDB): llenan un barrio entero unas horas."""
    citas = []
    for nombre, (deporte, campo, lat, lon) in EQUIPOS.items():
        try:
            ident = _id_equipo(sesion, nombre, deporte)
            if not ident:
                continue
            eventos = []
            for ruta in ("eventsnext.php", "eventslast.php"):
                resp = sesion.get(f"{SPORTSDB}/{ruta}", params={"id": ident}, timeout=20)
                resp.raise_for_status()
                eventos.extend(resp.json().get("events") or resp.json().get("results") or [])
                time.sleep(1)
        except Exception:  # noqa: BLE001
            continue
        for ev in eventos:
            if ev.get("idHomeTeam") != ident and ev.get("strHomeTeam") != nombre:
                continue
            inicio = None
            if ev.get("strTimestamp"):
                try:
                    inicio = int(datetime.fromisoformat(ev["strTimestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp())
                except ValueError:
                    inicio = None
            if inicio is None and ev.get("dateEvent"):
                hora = (ev.get("strTime") or "18:00:00")[:8]
                inicio = int(datetime.fromisoformat(f"{ev['dateEvent']}T{hora}").replace(tzinfo=timezone.utc).timestamp())
            if not inicio:
                continue
            duracion = 2 * 3600 if deporte == "Soccer" else int(2.25 * 3600)
            citas.append(Cita(f"partido:{ev.get('idEvent')}", "partido", f"{ev.get('strEvent') or nombre} ({campo})", inicio, inicio + duracion,
                              lat, lon, fuente="TheSportsDB", url=f"https://www.thesportsdb.com/event/{ev.get('idEvent')}",
                              extra={"campo": campo, "competicion": ev.get("strLeague"), "resultado": f"{ev.get('intHomeScore') or ''}-{ev.get('intAwayScore') or ''}".strip("-")}))
    return Toma(agenda=citas)


def festivos(años: tuple[int, ...]) -> list[tuple[date, str, str]]:
    """(día, nombre, tipo) de los festivos de València: nacionales, autonómicos y locales; y las Fallas."""
    salida: list[tuple[date, str, str]] = []
    try:
        import holidays
        for a in años:
            for dia, nombre in sorted(holidays.Spain(subdiv="VC", years=a).items()):
                salida.append((dia, nombre, "festivo"))
    except ImportError:
        for a in años:
            for m, d, nombre in ((1, 1, "Año Nuevo"), (1, 6, "Epifanía del Señor"), (3, 19, "San José"), (5, 1, "Fiesta del Trabajo"),
                                 (6, 24, "San Juan"), (8, 15, "Asunción de la Virgen"), (10, 9, "Día de la Comunitat Valenciana"),
                                 (10, 12, "Fiesta Nacional de España"), (11, 1, "Todos los Santos"), (12, 6, "Día de la Constitución"),
                                 (12, 8, "Inmaculada Concepción"), (12, 25, "Navidad")):
                salida.append((date(a, m, d), nombre, "festivo"))
            pascua = _pascua(a)
            salida += [(pascua - timedelta(days=2), "Viernes Santo", "festivo"), (pascua + timedelta(days=1), "Lunes de Pascua", "festivo")]
    for a in años:
        pascua = _pascua(a)
        salida += [(date(a, 1, 22), "San Vicente Mártir (fiesta local)", "festivo"),
                   (pascua + timedelta(days=8), "San Vicente Ferrer (fiesta local)", "festivo")]
        salida += [(date(a, 3, d), "Fallas", "fiesta") for d in range(15, 20)]
    vistos, unicos = set(), []
    for dia, nombre, tipo in sorted(salida):
        if (dia, tipo) not in vistos:
            vistos.add((dia, tipo))
            unicos.append((dia, nombre, tipo))
    return unicos


def _pascua(a: int) -> date:
    """Domingo de Pascua (algoritmo de Meeus/Jones/Butcher)."""
    b, c = divmod(a, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * (a % 19) + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a % 19 + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(a, mes, dia + 1)


def es_festivo(dia: date) -> bool:
    return any(d == dia and tipo == "festivo" for d, _, tipo in _festivos_cache(dia.year))


_CACHE_FESTIVOS: dict[int, list] = {}


def _festivos_cache(año: int) -> list:
    if año not in _CACHE_FESTIVOS:
        _CACHE_FESTIVOS[año] = festivos((año,))
    return _CACHE_FESTIVOS[año]


def tomar_festivos(sesion: requests.Session, geometria: bool = True) -> Toma:
    hoy = date.today()
    citas = []
    for dia, nombre, tipo in festivos((hoy.year, hoy.year + 1)):
        inicio = int(datetime(dia.year, dia.month, dia.day).timestamp())
        citas.append(Cita(f"{tipo}:{dia.isoformat()}", tipo, nombre, inicio, inicio + 86400 - 1, fuente="calendario laboral"))
    return Toma(agenda=citas)


def leer_ruido(texto: str) -> dict[str, tuple[str, float | None, float | None]]:
    """Del CSV diario de un sonómetro: el último día -> (fecha, LAeq de día, LAeq de noche)."""
    filas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    if not filas:
        return {}
    ultima = max(filas, key=lambda f: f.get("dateobserved", ""))
    return {"ultimo": (ultima.get("dateobserved", "").strip('"'), _numero(ultima.get("laeq_d")), _numero(ultima.get("laeq_n")))}


def tomar_ruido(sesion: requests.Session, geometria: bool = True) -> Toma:
    """Ruido de ayer en las calles de ocio de Russafa: nivel medio de día y de noche (dB(A)) por sonómetro."""
    toma = Toma(valores={"ruido_noche": {}, "ruido_dia": {}}, puntos={"ruido_noche": {}, "ruido_dia": {}})
    fecha = None
    for codigo, direccion in SONOMETROS.items():
        try:
            resp = sesion.get(f"{RUIDO}&paramid={codigo}-daily", timeout=30)
            resp.raise_for_status()
            ultimo = leer_ruido(resp.text).get("ultimo")
        except Exception:  # noqa: BLE001
            continue
        if not ultimo:
            continue
        dia, de_dia, de_noche = ultimo
        fecha = max(fecha or dia, dia)
        if de_noche is not None:
            toma.valores["ruido_noche"][codigo] = de_noche
        if de_dia is not None:
            toma.valores["ruido_dia"][codigo] = de_dia
        if geometria:
            for serie in ("ruido_noche", "ruido_dia"):
                toma.puntos[serie][codigo] = Punto(direccion)        # la posición la pone el nomenclátor
        time.sleep(0.5)
    if not toma.valores["ruido_noche"]:
        raise RuntimeError("ningún sonómetro ha contestado")
    noches = list(toma.valores["ruido_noche"].values())
    toma.indicadores = {"ruido_noche": round(sum(noches) / len(noches), 1)}
    try:
        toma.momento = int(datetime.fromisoformat(fecha).replace(hour=23).timestamp())
    except (TypeError, ValueError):
        pass
    return toma


FUENTES: tuple[Fuente, ...] = (
    Fuente("planificados", "Obras, ocupaciones y festejos", 3 * 3600, tomar_planificados, grupo="agenda", origen="Ajuntament de València"),
    Fuente("partidos", "Partidos en casa", 12 * 3600, tomar_partidos, grupo="agenda", origen="TheSportsDB"),
    Fuente("festivos", "Festivos", 24 * 3600, tomar_festivos, grupo="agenda", origen="calendario laboral"),
    Fuente("ruido", "Sonómetros de Russafa", 6 * 3600, tomar_ruido, grupo="agenda", origen="Ajuntament de València"),
)
INDICADORES: dict[str, dict] = {
    "ruido_noche": {"nombre": "Ruido nocturno en Russafa (ayer)", "unidad": "dB(A)", "fuente": "ruido"},
}
SERIES: dict[str, str] = {"ruido_noche": "ruido", "ruido_dia": "ruido"}
