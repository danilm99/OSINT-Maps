"""EXPERIMENTAL: avance de la vegetación con imágenes del satélite Sentinel-2.

Idea: en un sitio abandonado la vegetación va ganando terreno. El NDVI es un
índice (de -1 a 1) que mide cuánta vegetación hay en un píxel comparando la
luz roja con la infrarroja:

    NDVI = (infrarrojo - rojo) / (infrarrojo + rojo)

Para cada año se toma la imagen de verano con menos nubes, se calcula el NDVI
medio sobre el sitio y se ajusta una recta: si la pendiente es positiva, la
vegetación avanza.

Límites que conviene tener claros:
- Cada píxel mide 10 x 10 m: solo tiene sentido en sitios grandes (>= 1.000 m²).
- Una pendiente positiva también puede ser un jardín bien regado.
- Funciona contra el servicio real, pero la señal está sin calibrar: no se
  ha comprobado todavía cuánto ayuda a distinguir sitios abandonados.
- Es lento: alrededor de medio minuto por sitio.

Necesita `pip install "osintmaps[satelite]"` (rasterio).
Imágenes: catálogo abierto Earth Search (Element 84) sobre AWS.
"""

from __future__ import annotations

import datetime as dt
import logging
from concurrent.futures import ThreadPoolExecutor

import requests

from ..modelos import Candidato
from ..red import pedir

log = logging.getLogger(__name__)

STAC = "https://earth-search.aws.element84.com/v1/search"
COLECCION = "sentinel-2-l2a"
PRIMER_ANIO = 2017
SUPERFICIE_MINIMA = 1000.0


def pendiente(xs: list[float], ys: list[float]) -> float | None:
    """Pendiente de la recta de mínimos cuadrados (cuánto sube `y` por unidad de `x`)."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    denominador = sum((x - mx) ** 2 for x in xs)
    if denominador == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominador


def _mejor_escena(sesion: requests.Session, lat: float, lon: float, anio: int) -> dict | None:
    """La imagen de verano con menos nubes que cubre el punto."""
    cuerpo = {
        "collections": [COLECCION],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{anio}-06-15T00:00:00Z/{anio}-09-15T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": 15}},
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
        "limit": 1,
    }
    escenas = pedir(sesion, "POST", STAC, json=cuerpo, timeout=60).json().get("features", [])
    return escenas[0] if escenas else None


def _ndvi_medio(escena: dict, lat: float, lon: float, radio_m: float) -> float | None:
    import numpy as np
    import rasterio
    from rasterio.warp import transform
    from rasterio.windows import from_bounds

    # Desde 2022 las imágenes llevan sumado un desfase de 1000 que hay que quitar
    # para poder compararlas con las anteriores (salvo que el catálogo ya lo haya hecho).
    props = escena.get("properties", {})
    version = str(props.get("s2:processing_baseline", "0"))
    desfase = 1000.0 if version >= "04.00" and not props.get("earthsearch:boa_offset_applied", False) else 0.0

    medias = {}
    for banda in ("red", "nir"):
        url = escena["assets"][banda]["href"]
        # rasterio lee por HTTP solo el trozo necesario del fichero (formato COG).
        with rasterio.open(url) as src:
            xs, ys = transform("EPSG:4326", src.crs, [lon], [lat])
            ventana = from_bounds(xs[0] - radio_m, ys[0] - radio_m, xs[0] + radio_m, ys[0] + radio_m,
                                  src.transform)
            datos = src.read(1, window=ventana, boundless=True, fill_value=0).astype("float64")
        datos[datos == 0] = np.nan          # 0 = sin dato
        medias[banda] = datos - desfase
    rojo, nir = medias["red"], medias["nir"]
    if rojo.shape != nir.shape or rojo.size == 0:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (nir - rojo) / (nir + rojo)
    if np.all(np.isnan(ndvi)):
        return None
    return float(np.nanmean(ndvi))


def analizar(sesion: requests.Session, c: Candidato) -> dict:
    """Serie anual de NDVI y su pendiente para un candidato."""
    radio = max(15.0, min(150.0, ((c.superficie_m2 or SUPERFICIE_MINIMA) ** 0.5) / 2))

    def un_anio(anio: int) -> tuple[int, float | None]:
        try:
            escena = _mejor_escena(sesion, c.lat, c.lon, anio)
            return anio, None if escena is None else _ndvi_medio(escena, c.lat, c.lon, radio)
        except Exception as exc:  # noqa: BLE001
            log.warning("NDVI %s %d: %s", c.id, anio, exc)
            return anio, None

    anios = range(PRIMER_ANIO, dt.date.today().year + 1)
    with ThreadPoolExecutor(max_workers=5) as grupo:      # cada año es una descarga independiente
        resultados = list(grupo.map(un_anio, anios))
    serie = {anio: round(valor, 3) for anio, valor in resultados if valor is not None}
    resultado: dict = {"ndvi_serie": serie}
    p = pendiente([float(a) for a in serie], list(serie.values()))
    if p is not None:
        resultado["ndvi_pendiente"] = round(p, 4)
    return resultado


def enriquecer(sesion: requests.Session, candidatos: list[Candidato], top: int) -> int:
    """Analiza los `top` mejores candidatos con superficie suficiente."""
    try:
        import rasterio  # noqa: F401
    except ImportError as exc:
        raise RuntimeError('Falta rasterio. Instala con: pip install "osintmaps[satelite]"') from exc
    hechos = 0
    for c in candidatos:
        if hechos >= top:
            break
        if (c.superficie_m2 or 0) < SUPERFICIE_MINIMA:
            continue
        c.senales.update(analizar(sesion, c))
        hechos += 1
    return hechos
