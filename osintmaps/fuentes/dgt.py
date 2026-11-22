"""Cámaras de tráfico de la DGT (carreteras del Estado).

La DGT publica el inventario en DATEX II, un XML: posición, carretera, punto
kilométrico y la dirección de la imagen, que se renueva cada pocos minutos.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from ..red import pedir

URL = "https://nap.dgt.es/datex2/v3/dgt/DevicePublication/camaras_datex2_v36.xml"


def _texto(nodo: ET.Element, nombre: str) -> str | None:
    hallado = nodo.find(f".//{{*}}{nombre}")
    return hallado.text.strip() if hallado is not None and hallado.text else None


def parsear(xml: bytes) -> list[dict]:
    camaras = []
    for aparato in ET.fromstring(xml).findall(".//{*}device"):
        if (_texto(aparato, "typeOfDevice") or "camera") != "camera":
            continue
        try:
            lat, lon = float(_texto(aparato, "latitude")), float(_texto(aparato, "longitude"))
        except (TypeError, ValueError):
            continue
        carretera, pk = _texto(aparato, "roadName"), _texto(aparato, "kilometerPoint")
        provincia = (_texto(aparato, "province") or "").title()
        camara = {
            "id": f"dgt-{aparato.get('id')}", "lat": round(lat, 6), "lon": round(lon, 6),
            "nombre": " ".join(x for x in (carretera, f"km {pk}" if pk else None) if x) or "Cámara de la DGT",
        }
        for campo, valor in (("carretera", carretera), ("pk", pk), ("provincia", provincia),
                             ("destino", (_texto(aparato, "roadDestination") or "").title()),
                             ("imagen", _texto(aparato, "deviceUrl"))):
            if valor:
                camara[campo] = valor
        camaras.append(camara)
    return camaras


def buscar(sesion: requests.Session) -> list[dict]:
    return parsear(pedir(sesion, "GET", URL, timeout=120, reintentos=2).content)
