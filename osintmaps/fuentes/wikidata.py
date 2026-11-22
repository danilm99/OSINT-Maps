"""Fuente 3: Wikidata, consultado con SPARQL.

Wikidata es la base de datos estructurada que hay detrás de Wikipedia. Aquí
se usa para encontrar sitios con nombre propio y artículo: despoblados,
estaciones cerradas, minas, monasterios en ruinas...

Se piden los elementos con coordenadas dentro de una caja cuya "clase"
(propiedad P31, "instancia de") o cuyo "estado de uso" (P5817) suene a
abandonado. Se filtra por el texto de la etiqueta en inglés en vez de por
identificadores fijos, para no depender de una lista cerrada de clases.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import unquote

import requests

from ..geo import trocear_caja
from ..modelos import Candidato
from ..red import CacheJSON, pedir

log = logging.getLogger(__name__)

SERVIDOR = "https://query.wikidata.org/sparql"

_PATRON_CLASE = "ghost town|abandoned|ruin|disused|derelict|deserted|depopulated|uninhabited"
# "demolish|destroy" se pide a propósito: así llegan esas filas y el parser
# puede descartar el elemento entero (ver _RE_DESCARTE).
_PATRON_ESTADO = "abandon|ruin|disused|derelict|closed|decommission|demolish|destroy"
# Lo que ya no existe o nunca fue un sitio: se descarta aunque suene a abandonado.
_RE_DESCARTE = re.compile(r"demolish|destroyed|project|railway line|\broute\b|tram line|former municipality", re.I)

CONSULTA = """
SELECT ?item ?itemLabel ?coord ?claseEn ?estadoEn ?articulo WHERE {{
  SERVICE wikibase:box {{
    ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:cornerSouthWest "Point({oeste} {sur})"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point({este} {norte})"^^geo:wktLiteral .
  }}
  ?item wdt:P17 wd:Q29 .
  OPTIONAL {{ ?item wdt:P31 ?clase . ?clase rdfs:label ?claseEn . FILTER(LANG(?claseEn) = "en") }}
  OPTIONAL {{ ?item wdt:P5817 ?estado . ?estado rdfs:label ?estadoEn . FILTER(LANG(?estadoEn) = "en") }}
  OPTIONAL {{ ?articulo schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> . }}
  FILTER(
    REGEX(COALESCE(?claseEn, ""), "{patron_clase}", "i")
    || REGEX(COALESCE(?estadoEn, ""), "{patron_estado}", "i")
  )
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,ca,gl,eu,en" . }}
}}
"""

# (categoría, palabras que deben aparecer en la clase en inglés)
_CATEGORIAS = (
    ("despoblado", r"town|village|hamlet|settlement|municipality|depopulated|locality"),
    ("ferroviario", r"railway|station|train|tunnel"),
    ("mineria", r"\bmine\b|mining|quarry"),
    ("militar", r"military|bunker|barracks|fortification|\bfort\b|battery"),
    ("sanitario", r"hospital|sanatorium|asylum|leprosarium"),
    ("religioso", r"church|monastery|convent|chapel|hermitage|abbey"),
    ("industrial", r"factory|mill|power|plant|industrial|works|warehouse|kiln"),
    ("ocio_hosteleria", r"hotel|park|theatre|cinema|stadium|resort|spa"),
    ("educativo", r"school|college|university"),
    ("patrimonio", r"castle|tower|palace|ruin|monument|bridge"),
)
_RE_PUNTO = re.compile(r"Point\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)", re.I)


def _categoria(clases: set[str]) -> str:
    texto = " | ".join(sorted(clases)).lower()
    for categoria, patron in _CATEGORIAS:
        if re.search(patron, texto):
            return categoria
    return "otro"


def _estado(clases: set[str], estados: set[str]) -> str:
    texto = " | ".join(sorted(clases | estados)).lower()
    if "ruin" in texto or "demolished" in texto:
        return "ruina"
    if re.search(r"abandon|ghost|deserted|depopulated|uninhabited|derelict", texto):
        return "abandonado"
    return "en_desuso"


def parsear(respuestas: list[dict]) -> list[Candidato]:
    """Agrupa las filas por elemento (un elemento sale repetido por cada clase)."""
    items: dict[str, dict] = {}
    for respuesta in respuestas:
        for fila in respuesta.get("results", {}).get("bindings", []):
            qid = fila["item"]["value"].rsplit("/", 1)[-1]
            m = _RE_PUNTO.search(fila.get("coord", {}).get("value", ""))
            if not m:
                continue
            item = items.setdefault(qid, {
                "lon": float(m.group(1)), "lat": float(m.group(2)),
                "nombre": None, "clases": set(), "estados": set(), "articulo": None,
            })
            etiqueta = fila.get("itemLabel", {}).get("value")
            if etiqueta and etiqueta != qid:      # sin etiqueta, Wikidata devuelve el propio Q
                item["nombre"] = etiqueta
            if "claseEn" in fila:
                item["clases"].add(fila["claseEn"]["value"])
            if "estadoEn" in fila:
                item["estados"].add(fila["estadoEn"]["value"])
            if "articulo" in fila:
                titulo = unquote(fila["articulo"]["value"].rsplit("/wiki/", 1)[-1]).replace("_", " ")
                item["articulo"] = f"es:{titulo}"

    candidatos = []
    for qid, it in items.items():
        if _RE_DESCARTE.search(" | ".join(it["clases"] | it["estados"])):
            continue
        categoria = _categoria(it["clases"])
        candidatos.append(Candidato(
            id=f"wd-{qid}",
            lat=round(it["lat"], 6),
            lon=round(it["lon"], 6),
            nombre=it["nombre"],
            categoria=categoria,
            tipo_confirmado=categoria != "otro",
            estado=_estado(it["clases"], it["estados"]),
            fuentes=["wikidata"],
            wikidata=qid,
            wikipedia=it["articulo"],
            etiquetas={"wikidata:clase": ", ".join(sorted(it["clases"]))} if it["clases"] else {},
        ))
    return candidatos


def buscar(
    sesion: requests.Session,
    carpeta_cache: Path,
    caja: tuple[float, float, float, float],
    *,
    usar_cache: bool = True,
    paso: float = 0.5,
) -> list[Candidato]:
    """Consulta la caja troceada en teselas (el servidor corta a los 60 s)."""
    cache = CacheJSON(carpeta_cache, usar_cache)
    respuestas = []
    for oeste, sur, este, norte in trocear_caja(caja, paso):
        consulta = CONSULTA.format(
            oeste=f"{oeste:.5f}", sur=f"{sur:.5f}", este=f"{este:.5f}", norte=f"{norte:.5f}",
            patron_clase=_PATRON_CLASE, patron_estado=_PATRON_ESTADO,
        )
        datos = cache.leer(consulta)
        if datos is None:
            try:
                resp = pedir(sesion, "GET", SERVIDOR, params={"query": consulta, "format": "json"},
                             timeout=90, espera=10)
                datos = resp.json()
                cache.guardar(consulta, datos)
                time.sleep(1)   # cortesía con el servidor
            except Exception as exc:  # noqa: BLE001 - una tesela fallida no tumba el resto
                log.warning("Wikidata falló en la tesela %.2f,%.2f: %s", oeste, sur, exc)
                continue
        respuestas.append(datos)
    return parsear(respuestas)
