"""Inmuebles en subasta pública (Portal de Subastas del BOE).

Es la única fuente abierta que dice que un inmueble concreto está en venta. No
tiene API: se lee la web, que es lenta y cambia de vez en cuando, así que cada
subasta se guarda en caché y un fallo en una no detiene las demás.

El portal no da coordenadas. Se sitúa cada bien por su referencia catastral
cuando la trae (exacto) y, si no, por su dirección (aproximado).
"""

from __future__ import annotations

import html
import logging
import re
import time
from pathlib import Path

import requests

from ..red import CacheJSON, pedir

log = logging.getLogger(__name__)

BASE = "https://subastas.boe.es"
URL_CPMRC = "https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_CPMRC"
URL_CARTOCIUDAD = "https://www.cartociudad.es/geocoder/api/geocoder/find"
# El portal rechaza a los clientes que no parecen un navegador.
CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Maps"}

_ID = re.compile(r"idSub=(SUB-[A-Za-z0-9-]+)")
_FILA = re.compile(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", re.S)
_BIEN = re.compile(r"<h4>(Bien \d+[^<]*)</h4>(.*?)(?=<h4>|</div>\s*</div>\s*</div>|$)", re.S)
_LOTE = re.compile(r"idLote=(\d+)")
_ETIQUETA = re.compile(r"<[^>]+>")
_REFCAT = re.compile(r"\b([0-9A-Z]{14})(?:[0-9A-Z]{6})?\b")


def _texto(trozo: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_ETIQUETA.sub(" ", trozo))).strip()


def _tabla(trozo: str) -> dict[str, str]:
    return {_texto(k): _texto(v) for k, v in _FILA.findall(trozo) if _texto(v)}


def ids_del_listado(pagina: str) -> list[str]:
    return list(dict.fromkeys(_ID.findall(pagina)))


def bienes_de_la_pagina(pagina: str) -> list[dict]:
    """Los bienes (inmuebles) descritos en la pestaña «Bienes» de una subasta o de un lote."""
    bienes = []
    for titulo, cuerpo in _BIEN.findall(pagina):
        datos = _tabla(cuerpo)
        if datos:
            bienes.append({"titulo": _texto(titulo), **datos})
    return bienes


def listar(sesion: requests.Session, provincia: str, estado: str = "EJ") -> list[str]:
    """Identificadores de las subastas de inmuebles de una provincia. EJ = celebrándose, PU = próxima apertura."""
    parametros = {
        "campo[2]": "SUBASTA.ESTADO.CODIGO", "dato[2]": estado, "campo[3]": "BIEN.TIPO", "dato[3]": "I",
        "campo[8]": "BIEN.COD_PROVINCIA", "dato[8]": provincia, "page_hits": "500",
        "sort_field[0]": "SUBASTA.FECHA_FIN", "sort_order[0]": "desc", "accion": "Buscar",
    }
    resp = pedir(sesion, "GET", f"{BASE}/subastas_ava.php", params=parametros, headers=CABECERAS, timeout=60, reintentos=2)
    return ids_del_listado(resp.text)


def _coordenadas(sesion: requests.Session, bien: dict) -> tuple[float, float, str] | None:
    refcat = _REFCAT.search(bien.get("Referencia catastral", ""))
    if refcat:
        try:
            datos = pedir(sesion, "GET", URL_CPMRC, params={"RefCat": refcat.group(1), "SRS": "EPSG:4326"},
                          timeout=30, reintentos=2).json()
            geo = datos["Consulta_CPMRCResult"]["coordenadas"]["coord"][0]["geo"]
            return float(geo["ycen"]), float(geo["xcen"]), "parcela"
        except Exception as exc:  # noqa: BLE001 - se intenta por la dirección
            log.debug("Catastro no situó %s: %s", refcat.group(1), exc)
    direccion, localidad = bien.get("Dirección"), bien.get("Localidad")
    if direccion and localidad:
        try:
            datos = pedir(sesion, "GET", URL_CARTOCIUDAD, params={"q": f"{direccion}, {localidad}"},
                          timeout=30, reintentos=2).json()
            if datos and datos.get("lat") and datos.get("lng"):
                # Solo vale si acertó al menos con la calle; un municipio entero no sitúa nada.
                if datos.get("type") in ("portal", "callejero", "toponimo", "Codpost") or datos.get("tip_via"):
                    return float(datos["lat"]), float(datos["lng"]), "portal" if datos.get("type") == "portal" else "calle"
        except Exception as exc:  # noqa: BLE001
            log.debug("CartoCiudad no situó «%s, %s»: %s", direccion, localidad, exc)
    return None


def detalle(sesion: requests.Session, identificador: str, pausa: float = 0.4) -> list[dict]:
    """Una subasta: sus datos generales y, por cada inmueble que se pudo situar, un punto."""
    def pagina(**extra) -> str:
        time.sleep(pausa)
        return pedir(sesion, "GET", f"{BASE}/detalleSubasta.php", params={"idSub": identificador, **extra},
                     headers=CABECERAS, timeout=60, reintentos=2).text

    general = _tabla(pagina(ver="1"))
    bienes_html = pagina(ver="3")
    bienes = bienes_de_la_pagina(bienes_html)
    for lote in list(dict.fromkeys(_LOTE.findall(bienes_html)))[:8]:
        if lote != "1" or not bienes:
            bienes += [dict(b, lote=lote) for b in bienes_de_la_pagina(pagina(ver="3", idLote=lote))]

    puntos, vistos = [], set()
    for numero, bien in enumerate(bienes, 1):
        clave = (bien.get("Referencia catastral"), bien.get("Dirección"), bien.get("Localidad"))
        if clave in vistos:
            continue
        vistos.add(clave)
        sitio = _coordenadas(sesion, bien)
        if not sitio:
            continue
        lat, lon, precision = sitio
        punto = {
            "id": f"subasta-{identificador}-{numero}", "lat": round(lat, 6), "lon": round(lon, 6),
            "nombre": f"{bien['titulo'].split(' - ', 1)[-1]} en subasta", "subasta": identificador,
            "url": f"{BASE}/detalleSubasta.php?idSub={identificador}", "situado_por": precision,
        }
        for campo, origen in (("direccion", "Dirección"), ("localidad", "Localidad"), ("refcat", "Referencia catastral"),
                              ("descripcion", "Descripción"), ("situacion_posesoria", "Situación posesoria"),
                              ("visitable", "Visitable"), ("vivienda_habitual", "Vivienda habitual"),
                              ("cargas", "Cargas"), ("inscripcion", "Inscripción registral")):
            if bien.get(origen):
                punto[campo] = bien[origen][:600]
        for campo, origen in (("fin", "Fecha de conclusión"), ("inicio", "Fecha de inicio"), ("valor_subasta", "Valor subasta"),
                              ("tasacion", "Tasación"), ("puja_minima", "Puja mínima"), ("deposito", "Importe del depósito"),
                              ("tipo_subasta", "Tipo de subasta"), ("cantidad_reclamada", "Cantidad reclamada")):
            if general.get(origen):
                punto[campo] = general[origen][:120]
        puntos.append(punto)
    return puntos


def buscar(sesion: requests.Session, carpeta_cache: Path, provincia: str, *, usar_cache: bool = True,
           avisar=lambda mensaje: None) -> list[dict]:
    cache = CacheJSON(carpeta_cache, usar_cache)
    ids = list(dict.fromkeys(listar(sesion, provincia, "EJ") + listar(sesion, provincia, "PU")))
    puntos: list[dict] = []
    for n, identificador in enumerate(ids, 1):
        guardado = cache.leer(identificador)
        if guardado is None:
            try:
                guardado = detalle(sesion, identificador)
                cache.guardar(identificador, guardado)
            except Exception as exc:  # noqa: BLE001 - una subasta ilegible no detiene el resto
                log.warning("Subasta %s omitida: %s", identificador, exc)
                continue
        puntos += guardado
        if n % 20 == 0:
            avisar(f"  subastas: {n}/{len(ids)}")
    return puntos
