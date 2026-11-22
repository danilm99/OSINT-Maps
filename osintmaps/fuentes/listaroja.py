"""Lista Roja del Patrimonio (Hispania Nostra): patrimonio en riesgo de desaparecer.

No tiene API. La portada de su web lleva dentro el mapa completo (unas 2.000
fichas de toda España) como código de Google Maps: de ahí se sacan el nombre,
el resumen, el enlace a la ficha y la posición de cada una.
"""

from __future__ import annotations

import html
import re

import requests

from ..red import pedir

URL = "https://listaroja.hispanianostra.org/"

_FICHA = re.compile(
    r'var contentString_(\d+) = "(.*?)";\s*marker\[\1\] = new google\.maps\.Marker\(\{\s*'
    r"position: \{lat: (-?[\d.]+), lng: (-?[\d.]+)\}(.*?)\}\);",
    re.S,
)
_TITULO = re.compile(r"<h5>(.*?)</h5>", re.S)
_CUERPO = re.compile(r'class="info-content">(.*?)(?:<br|<a |</div>)', re.S)
_ENLACE = re.compile(r'href="(https://[^"]+)"')
_ICONO = re.compile(r"icon: '[^']*?([^/']+)\.png'")
_ETIQUETA = re.compile(r"<[^>]+>")


def _texto(trozo: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_ETIQUETA.sub(" ", trozo))).strip()


def parsear(pagina: str) -> list[dict]:
    fichas = []
    for numero, contenido, lat, lon, resto in _FICHA.findall(pagina):
        contenido = contenido.replace('\\"', '"').replace("\\/", "/").replace("\\'", "'").replace("\\n", " ")
        titulo = _TITULO.search(contenido)
        if not titulo:
            continue
        lat, lon = float(lat), float(lon)
        if not (27 <= lat <= 44.5 and -19 <= lon <= 5):      # fuera de España: ficha mal situada
            continue
        ficha = {"id": f"listaroja-{numero}", "nombre": _texto(titulo.group(1)), "lat": round(lat, 6), "lon": round(lon, 6)}
        cuerpo = _CUERPO.search(contenido)
        if cuerpo and _texto(cuerpo.group(1)):
            ficha["resumen"] = _texto(cuerpo.group(1))[:400]
        enlace = _ENLACE.search(contenido)
        if enlace:
            ficha["url"] = enlace.group(1)
        icono = _ICONO.search(resto)
        if icono:
            ficha["icono"] = icono.group(1)
        fichas.append(ficha)
    return fichas


def buscar(sesion: requests.Session) -> list[dict]:
    return parsear(pedir(sesion, "GET", URL, timeout=90, reintentos=2).text)
