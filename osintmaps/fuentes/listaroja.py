"""Lista Roja del Patrimonio (Hispania Nostra): patrimonio en riesgo de desaparecer.

No tiene API. La portada de su web lleva dentro el mapa completo (unas 2.000
fichas de toda España, contando las de la Lista Verde y la Lista Negra) como código de Google Maps: de ahí se sacan el nombre,
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
        # El icono dice en cuál de las tres listas está: Roja (en riesgo), Verde
        # (salió de la Roja porque se recuperó) o Negra (se perdió).
        icono = _ICONO.search(resto)
        ficha["lista"] = {"hispania_icon1": "verde", "lista-negra": "negra"}.get(icono.group(1) if icono else "", "roja")
        fichas.append(ficha)
    return fichas


_META = re.compile(r'<meta property="og:(image|description)" content="([^"]*)"')
_FOTO = re.compile(r'(?:src|href)="(https://listaroja\.hispanianostra\.org/wp-content/uploads/[^"]+\.(?:jpe?g|png|webp))"', re.I)


def detalle(pagina: str) -> dict:
    """De la página de una ficha: su foto principal, su resumen y el resto de fotos."""
    metas = dict(_META.findall(pagina))
    fotos = []
    for foto in ([metas["image"]] if metas.get("image") else []) + _FOTO.findall(pagina):
        # Fuera los iconos y las miniaturas («-150x150»): solo fotos de la ficha.
        if foto not in fotos and "leaflet-maps-marker" not in foto and not re.search(r"-\d+x\d+\.\w+$", foto):
            fotos.append(foto)
    return {"imagen": fotos[0] if fotos else None, "descripcion": html.unescape(metas.get("description", "")).strip(), "imagenes": fotos[:12]}


def buscar(sesion: requests.Session) -> list[dict]:
    return parsear(pedir(sesion, "GET", URL, timeout=90, reintentos=2).text)
