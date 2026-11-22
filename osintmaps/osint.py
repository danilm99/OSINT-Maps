"""Capa OSINT: enlaces de verificación y fotos cercanas.

OSINT = investigación con fuentes abiertas. El programa no "investiga" solo:
prepara, para cada candidato, los enlaces que abrirías a mano para comprobar
si de verdad está abandonado (vista aérea, Street View, ficha catastral,
búsquedas de prensa) y, opcionalmente, busca fotos geolocalizadas en
Wikimedia Commons.

Todo apunta a LUGARES. No se consulta ni se guarda nada sobre propietarios.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, quote_plus

import requests

from .modelos import Candidato
from .red import pedir

log = logging.getLogger(__name__)

API_COMMONS = "https://commons.wikimedia.org/w/api.php"


def enlaces(c: Candidato) -> dict[str, str]:
    """Enlaces de verificación manual para un candidato."""
    lat, lon = f"{c.lat:.6f}", f"{c.lon:.6f}"
    e = {
        "google_maps": f"https://www.google.com/maps/@?api=1&map_action=map&center={lat},{lon}&zoom=19&basemap=satellite",
        "street_view": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}",
        # La forma /search/ es la que Google Earth abre bien: vuela al punto y deja una chincheta.
        "google_earth": f"https://earth.google.com/web/search/{lat},{lon}",
        "mapillary": f"https://www.mapillary.com/app/?lat={lat}&lng={lon}&z=17",
        "commons_cerca": f"https://commons.wikimedia.org/wiki/Special:Nearby#/coord/{lat},{lon}",
    }
    if c.refcats:
        rc = c.refcats[0]
        e["catastro"] = ("https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCListaBienes.aspx"
                         f"?rc1={rc[:7]}&rc2={rc[7:14]}")
        e["foto_fachada"] = ("https://ovc.catastro.meh.es/OVCServWeb/OVCWcfLibres/OVCFotoFachada.svc/"
                             f"RecuperarFotoFachadaGet?ReferenciaCatastral={rc}")
    if c.osm_ids:
        e["osm"] = f"https://www.openstreetmap.org/{c.osm_ids[0]}"
    if c.wikidata:
        e["wikidata"] = f"https://www.wikidata.org/wiki/{c.wikidata}"
    if c.wikipedia and ":" in c.wikipedia:
        idioma, titulo = c.wikipedia.split(":", 1)
        e["wikipedia"] = f"https://{idioma}.wikipedia.org/wiki/{quote(titulo.replace(' ', '_'))}"
    if c.nombre:
        # Con nombre propio ya se puede buscar historia y prensa.
        lugar = f' "{c.municipio}"' if c.municipio else ""
        consulta = f'"{c.nombre}"{lugar} abandonado OR ruinas OR cierre'
        e["busqueda"] = "https://www.google.com/search?q=" + quote_plus(consulta)
        e["noticias"] = "https://www.google.com/search?tbm=nws&q=" + quote_plus(f'"{c.nombre}"{lugar}')
    return e


def fotos_commons(sesion: requests.Session, c: Candidato, radio_m: int = 300, maximo: int = 6) -> list[dict[str, str]]:
    """Fotos de Wikimedia Commons geolocalizadas cerca del candidato."""
    resp = pedir(sesion, "GET", API_COMMONS, timeout=30, params={
        "action": "query", "format": "json", "generator": "geosearch",
        "ggscoord": f"{c.lat}|{c.lon}", "ggsradius": radio_m, "ggslimit": maximo,
        "ggsnamespace": 6,                       # espacio de nombres 6 = ficheros
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 320,
    })
    paginas = resp.json().get("query", {}).get("pages", {})
    fotos = []
    for pagina in paginas.values():
        info = (pagina.get("imageinfo") or [{}])[0]
        if info.get("thumburl"):
            fotos.append({
                "titulo": pagina.get("title", "").removeprefix("File:"),
                "miniatura": info["thumburl"],
                "pagina": info.get("descriptionurl", ""),
            })
    return fotos


def enriquecer_con_fotos(sesion: requests.Session, candidatos: list[Candidato], top: int) -> None:
    """Busca fotos para los `top` primeros candidatos (ya ordenados por nota).

    Cada consulta tarda en torno a un segundo, así que se lanzan unas pocas a
    la vez. Pocas a propósito: es un servicio gratuito y no hay que saturarlo.
    """
    def buscar(c: Candidato) -> None:
        try:
            c.fotos = fotos_commons(sesion, c)
        except Exception as exc:  # noqa: BLE001 - es un extra, no debe parar el proceso
            log.warning("Commons falló para %s: %s", c.id, exc)

    with ThreadPoolExecutor(max_workers=4) as grupo:
        list(grupo.map(buscar, candidatos[:top]))
