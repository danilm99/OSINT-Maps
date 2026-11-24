"""El contexto de la ciudad: capas que cambian poco y que sirven para cruzar lo demás.

Se bajan del geoportal y del portal de datos abiertos del Ajuntament de València a
`datos/ciudad/` (un GeoJSON por capa) y se vuelven a bajar cuando tienen más de unos días:

- barrios y distritos: la unidad del cruce (todo lo que pasa se lleva a su barrio);
- ejes de calle: el nomenclátor para situar en el mapa lo que dicen noticias y publicaciones;
- estaciones de metro, monumentos y recursos turísticos: más nombres de lugares;
- vulnerabilidad por barrio, población por manzana, quejas y sugerencias, accidentes de tráfico:
  el contexto social de cada barrio;
- catálogo de patrimonio, libros de registro de edificios y solares, vivienda protegida, zonas
  acústicamente saturadas: para la ficha de cada inmueble.

Nada de esto identifica a personas: son capas públicas de equipamientos, calles y estadísticas.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import time
from pathlib import Path

import requests

from .fuentes import pedir_geoportal

log = logging.getLogger("osintmaps.pulso")

CARPETA = "ciudad"
CKAN = "https://opendata.vlci.valencia.es/api/3/action/package_show?id="

# nombre -> (capa del geoportal, campos que se guardan, días que vale)
CAPAS: dict[str, tuple[str, tuple[str, ...], int]] = {
    "barrios": ("UrbanismoEInfraestructuras/224", ("coddistbar", "codbarrio", "coddistrit", "nombre"), 90),
    "distritos": ("UrbanismoEInfraestructuras/225", ("coddistrit", "nombre"), 90),
    "secciones": ("UrbanismoEInfraestructuras/210", ("coddistsecc", "coddistrit", "codsecc"), 90),
    "calles": ("UrbanismoEInfraestructuras/223", ("codvia", "tipcalle", "nomcalle", "lf_add", "lt_add", "rf_add", "rt_add"), 60),
    "metro": ("Trafico/221", ("codigo", "nombre", "linea"), 30),
    "monumentos": ("Turismo/202", ("nombre",), 90),
    "recursos_turisticos": ("Turismo/226", ("nombre",), 90),
    "patrimonio": ("UrbanismoEInfraestructuras/322", ("codigo", "denominaci", "grado_prot", "categoria", "t_elemento", "estado_tra"), 60),
    "registro_edificios": ("UrbanismoEInfraestructuras/294", ("refcat", "seccion", "nombarrio", "tipo_via", "emplazamie", "numero"), 30),
    "registro_solares": ("UrbanismoEInfraestructuras/286", ("refcat", "seccion", "nombarrio", "tipo_via", "emplazamie", "numero"), 30),
    "vpp": ("UrbanismoEInfraestructuras/227", ("idparcela", "numviviendas", "tipovpp", "regimencalifi", "tipopromo", "uso"), 60),
    "zas": ("SociedadBienestar/5", ("zona",), 90),
    "manzanas": ("UrbanismoEInfraestructuras/215", ("*",), 90),
}
# Conjuntos del portal de datos abiertos (CKAN): nombre -> (identificador, días que vale)
TABLAS: dict[str, tuple[str, int]] = {
    "vulnerabilidad": ("vulnerabilidad-por-barrios", 90),
    "quejas": ("total-castellano", 7),
    "accidentes": ("siniestros-de-trafico-2022-2025", 30),
}
MAX_BYTES_TABLA = 80_000_000


def carpeta(datos: Path) -> Path:
    c = Path(datos) / CARPETA
    c.mkdir(parents=True, exist_ok=True)
    return c


def _vieja(ruta: Path, dias: float) -> bool:
    return not ruta.exists() or time.time() - ruta.stat().st_mtime > dias * 86400


def _escribir(ruta: Path, contenido: bytes) -> None:
    temporal = ruta.with_suffix(ruta.suffix + ".parcial")
    temporal.write_bytes(contenido)
    temporal.replace(ruta)


def bajar_capa(sesion: requests.Session, nombre: str, ruta: Path) -> int:
    servicio, campos, _ = CAPAS[nombre]
    elementos = pedir_geoportal(sesion, servicio, campos=",".join(campos), timeout=60)
    limpios = []
    for e in elementos:
        if not e.get("geometry"):
            continue
        p = e.get("properties") or {}
        if campos != ("*",):
            p = {k: p.get(k) for k in campos}
        limpios.append({"type": "Feature", "geometry": e["geometry"], "properties": p})
    _escribir(ruta, json.dumps({"type": "FeatureCollection", "features": limpios}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return len(limpios)


def _recurso(sesion: requests.Session, identificador: str, formatos: tuple[str, ...]) -> str | None:
    recursos = sesion.get(CKAN + identificador, timeout=30).json()["result"]["resources"]
    for formato in formatos:
        for r in recursos:
            if (r.get("format") or "").upper() == formato:
                return r["url"]
    return None


def bajar_tabla(sesion: requests.Session, nombre: str, ruta: Path) -> int:
    identificador, _ = TABLAS[nombre]
    url = _recurso(sesion, identificador, ("GEOJSON", "CSV") if nombre == "vulnerabilidad" else ("CSV",))
    if not url:
        raise ValueError(f"sin recurso descargable en {identificador}")
    resp = sesion.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    contenido = bytearray()
    for trozo in resp.iter_content(1 << 16):
        contenido += trozo
        if len(contenido) > MAX_BYTES_TABLA:
            raise ValueError(f"{nombre}: demasiado grande")
    contenido = bytes(contenido)
    _escribir(ruta, contenido)
    return contenido.count(b"\n")


def actualizar(datos: Path, sesion: requests.Session, solo: tuple[str, ...] | None = None, forzar: bool = False) -> dict[str, str]:
    """Baja lo que falte o haya caducado. Devuelve, por capa, qué ha pasado (para el registro)."""
    destino = carpeta(datos)
    hecho: dict[str, str] = {}
    for nombre, (_, _, dias) in CAPAS.items():
        if solo and nombre not in solo:
            continue
        ruta = destino / f"{nombre}.geojson"
        if not forzar and not _vieja(ruta, dias):
            continue
        try:
            hecho[nombre] = f"{bajar_capa(sesion, nombre, ruta)} elementos"
        except Exception as exc:  # noqa: BLE001  (una capa que falla no impide las demás)
            hecho[nombre] = f"fallo: {exc}"[:200]
    for nombre, (_, dias) in TABLAS.items():
        if solo and nombre not in solo:
            continue
        ruta = destino / (f"{nombre}.geojson" if nombre == "vulnerabilidad" else f"{nombre}.csv")
        if not forzar and not _vieja(ruta, dias):
            continue
        try:
            hecho[nombre] = f"{bajar_tabla(sesion, nombre, ruta)} líneas"
        except Exception as exc:  # noqa: BLE001
            hecho[nombre] = f"fallo: {exc}"[:200]
    return hecho


def leer_geojson(datos: Path, nombre: str) -> list[dict]:
    ruta = Path(datos) / CARPETA / f"{nombre}.geojson"
    if not ruta.exists():
        return []
    return json.loads(ruta.read_text(encoding="utf-8")).get("features") or []


def leer_csv(datos: Path, nombre: str) -> list[dict]:
    """Las tablas del portal vienen en UTF-8 o en Latin-1 y separadas por «;» o «,»: se prueban ambas cosas."""
    ruta = Path(datos) / CARPETA / f"{nombre}.csv"
    if not ruta.exists():
        return []
    bruto = ruta.read_bytes()
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")
    primera = texto.split("\n", 1)[0]
    separador = ";" if primera.count(";") >= primera.count(",") else ","
    return list(csv.DictReader(io.StringIO(texto), delimiter=separador))
