"""Fuente 4: cámaras de vigilancia de OpenStreetMap.

En OSM una cámara se marca con man_made=surveillance y, si quien la dibujó se
molestó, con más detalle: qué vigila, de qué tipo es, dónde va montada y hacia
dónde apunta. Es un dato colaborativo: que no haya cámara dibujada no significa
que no la haya.

No se mezcla con los sitios abandonados: va a su propio fichero y es otra capa
del mapa.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from ..red import CacheJSON, pedir
from .osm import SERVIDORES, zona_overpass

log = logging.getLogger(__name__)

# Campo propio -> etiqueta de OSM de la que sale.
CAMPOS = {
    "tipo": "surveillance:type",      # camera, ALPR (lector de matrículas)...
    "camara": "camera:type",          # fixed, panning, dome
    "vigila": "surveillance",         # public, outdoor
    "zona": "surveillance:zone",      # traffic, town, parking, building...
    "montaje": "camera:mount",        # wall, pole, street_lamp...
    "operador": "operator",
}


def construir_consulta(
    *, provincia: str | None = None, caja: tuple[float, float, float, float] | None = None, timeout: int = 300
) -> str:
    cabecera, zona = zona_overpass(provincia=provincia, caja=caja)
    return f'[out:json][timeout:{timeout}];\n{cabecera}nwr["man_made"="surveillance"]{zona};\nout tags center qt;\n'


def parsear(respuesta: dict) -> list[dict]:
    """Convierte la respuesta de Overpass en una lista de cámaras."""
    camaras = []
    for el in respuesta.get("elements", []):
        tags = el.get("tags") or {}
        # Las de interior y los vigilantes (personas) no interesan en un mapa de exteriores.
        if tags.get("surveillance") == "indoor" or tags.get("surveillance:type") == "guard":
            continue
        centro = el if el.get("type") == "node" else el.get("center") or {}
        lat, lon = centro.get("lat"), centro.get("lon")
        if lat is None or lon is None:
            continue
        camara = {"id": f"{el['type']}/{el['id']}", "lat": round(float(lat), 6), "lon": round(float(lon), 6)}
        for campo, etiqueta in CAMPOS.items():
            if tags.get(etiqueta):
                camara[campo] = str(tags[etiqueta])[:80]
        direccion = tags.get("camera:direction") or tags.get("direction")
        if direccion:
            camara["direccion"] = str(direccion)[:20]
        camaras.append(camara)
    return camaras


def buscar(
    sesion: requests.Session,
    carpeta_cache: Path,
    *,
    provincia: str | None = None,
    caja: tuple[float, float, float, float] | None = None,
    usar_cache: bool = True,
) -> list[dict]:
    consulta = construir_consulta(provincia=provincia, caja=caja)
    cache = CacheJSON(carpeta_cache, usar_cache)
    datos = cache.leer(consulta)
    if datos is None:
        ultimo: Exception | None = None
        for servidor in SERVIDORES:
            try:
                datos = pedir(sesion, "POST", servidor, data={"data": consulta}, timeout=360,
                              reintentos=2, espera=20).json()
                break
            except Exception as exc:  # noqa: BLE001 - se prueba el siguiente servidor
                ultimo = exc
                log.warning("Overpass %s falló: %s", servidor, exc)
        if datos is None:
            raise RuntimeError(f"Ningún servidor Overpass respondió: {ultimo}")
        if datos.get("remark"):
            log.warning("Aviso de Overpass: %s", datos["remark"])
        else:
            cache.guardar(consulta, datos)
    return parsear(datos)


def geojson(camaras: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": {k: v for k, v in c.items() if k not in ("lat", "lon")},
            }
            for c in camaras
        ],
    }
