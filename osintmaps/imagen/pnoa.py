"""Ortofotos del IGN (PNOA): fotografía aérea oficial, gratuita y con histórico.

Un servicio WMS devuelve una imagen del trozo de mapa que se le pida en la
propia URL. Con eso se puede sacar, de cada candidato, la foto actual y la de
años anteriores (incluido el "vuelo americano" de 1956-57) para ver cómo ha
cambiado: tejados que desaparecen, vegetación que entra, etc.

Licencia de las imágenes: CC BY 4.0 scne.es (hay que citar la fuente).
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlencode

import requests

from ..geo import caja_alrededor
from ..modelos import Candidato
from ..red import descargar

log = logging.getLogger(__name__)

WMS_ACTUAL = "https://www.ign.es/wms-inspire/pnoa-ma"
CAPA_ACTUAL = "OI.OrthoimageCoverage"
WMS_HISTORICO = "https://www.ign.es/wms/pnoa-historico"

# Capas habituales del servicio histórico. Es una lista orientativa: la cobertura
# de cada año depende de la zona y el IGN añade capas nuevas. La lista real se
# obtiene pidiendo al servicio "?SERVICE=WMS&REQUEST=GetCapabilities" (el visor
# web lo hace solo).
CAPAS_HISTORICAS = (
    "AMS_1956-1957", "Interministerial_1973-1986", "Nacional_1981-1986", "OLISTAT", "SIGPAC",
    "PNOA2004", "PNOA2006", "PNOA2008", "PNOA2010", "PNOA2012", "PNOA2015", "PNOA2018",
)


def url_imagen(lat: float, lon: float, *, capa: str = "actual", lado_m: float = 300.0, px: int = 512) -> str:
    """URL de una imagen cuadrada de `lado_m` metros centrada en el punto."""
    oeste, sur, este, norte = caja_alrededor(lat, lon, lado_m)
    servicio, nombre_capa = (WMS_ACTUAL, CAPA_ACTUAL) if capa == "actual" else (WMS_HISTORICO, capa)
    parametros = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "LAYERS": nombre_capa, "STYLES": "", "FORMAT": "image/jpeg",
        "SRS": "EPSG:4326",                       # en WMS 1.1.1 la caja va como lon,lat
        "BBOX": f"{oeste:.6f},{sur:.6f},{este:.6f},{norte:.6f}",
        "WIDTH": px, "HEIGHT": px,
    }
    return f"{servicio}?{urlencode(parametros)}"


def descargar_miniaturas(
    sesion: requests.Session,
    candidatos: list[Candidato],
    carpeta: Path,
    *,
    capas: tuple[str, ...] = ("actual", "PNOA2006", "AMS_1956-1957"),
    lado_m: float | None = None,
) -> int:
    """Guarda en disco una imagen por candidato y capa. Devuelve cuántas bajó."""
    bajadas = 0
    for c in candidatos:
        # El encuadre se adapta al tamaño del sitio (mínimo 200 m de lado).
        lado = lado_m or max(200.0, 4 * (c.superficie_m2 or 2500) ** 0.5)
        for capa in capas:
            destino = carpeta / f"{c.id}_{capa}.jpg"
            try:
                descargar(sesion, url_imagen(c.lat, c.lon, capa=capa, lado_m=lado), destino, timeout=60)
                bajadas += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Sin imagen %s para %s: %s", capa, c.id, exc)
    return bajadas
