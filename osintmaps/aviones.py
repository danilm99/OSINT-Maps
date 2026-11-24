"""Aviones en vuelo alrededor de un punto, sin que nos bloqueen.

Hay varios servicios gratuitos que juntan lo que captan las antenas ADS-B de aficionados y
lo dan con el mismo formato (el de «readsb»). Aquí se pregunta a uno y, si no contesta o
pide que paremos, al siguiente:

- adsb.fi: límite publicado de una petición por segundo. Es el primero.
- adsb.lol: sin límite publicado («dinámico según la carga»); en la práctica corta a quien
  pregunta a menudo. Queda de reserva.

Lo usan el recolector del pulso (cada 30 segundos) y la capa de aviones del mapa en vivo
(como mucho una vez cada 15 segundos por zona), así que todas las peticiones pasan por aquí:

- Entre dos peticiones al mismo servicio pasan al menos `MIN_ENTRE` segundos, vengan de
  donde vengan.
- Si un servicio contesta 429 («demasiadas peticiones»), 403 o 503, no se le vuelve a
  preguntar en lo que diga su cabecera Retry-After o, si no dice nada, en diez minutos.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import requests

PROVEEDORES: tuple[tuple[str, str], ...] = (
    ("adsb.fi", "https://opendata.adsb.fi/api/v2/lat/{lat:.3f}/lon/{lon:.3f}/dist/{millas}"),
    ("adsb.lol", "https://api.adsb.lol/v2/lat/{lat:.3f}/lon/{lon:.3f}/dist/{millas}"),
)
MIN_ENTRE = 2.0             # segundos entre dos peticiones al mismo servicio
PAUSA_SI_PARAN = 600.0      # segundos sin preguntar a un servicio que ha pedido parar, si no dice cuánto
CODIGOS_DE_PARAR = (403, 429, 503)

_candados = {nombre: threading.Lock() for nombre, _ in PROVEEDORES}
_ultima: dict[str, float] = {}            # cuándo se le preguntó por última vez (reloj que no retrocede)
_pausado_hasta: dict[str, float] = {}


class SinServicio(RuntimeError):
    """Ningún servicio ha contestado: todos fallan o han pedido parar."""


def _segundos_de_pausa(resp) -> float:
    valor = (getattr(resp, "headers", None) or {}).get("Retry-After")
    try:
        return max(30.0, min(3600.0, float(valor)))
    except (TypeError, ValueError):
        return PAUSA_SI_PARAN


def estado() -> dict[str, float]:
    """Segundos que le quedan de pausa a cada servicio (solo los pausados)."""
    ahora = time.monotonic()
    return {nombre: round(hasta - ahora) for nombre, hasta in _pausado_hasta.items() if hasta > ahora}


def pedir(lat: float, lon: float, millas: int, get: Callable[..., requests.Response] | None = None, timeout: float = 12.0) -> dict:
    """Los aviones a menos de `millas` millas náuticas del punto, como {"ac": [...], "fuente": servicio}.

    `get` es la función que hace la petición (la de una sesión, por ejemplo); por defecto, requests.get."""
    get = get or requests.get
    errores = []
    for nombre, plantilla in PROVEEDORES:
        if _pausado_hasta.get(nombre, 0) > time.monotonic():
            errores.append(f"{nombre}: en pausa")
            continue
        with _candados[nombre]:
            espera = _ultima.get(nombre, 0) + MIN_ENTRE - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            _ultima[nombre] = time.monotonic()
            try:
                resp = get(plantilla.format(lat=lat, lon=lon, millas=millas), timeout=timeout)
            except Exception as exc:  # noqa: BLE001  (sin red, tiempo agotado: se prueba el siguiente)
                errores.append(f"{nombre}: {type(exc).__name__}")
                continue
        codigo = getattr(resp, "status_code", 200)
        if codigo in CODIGOS_DE_PARAR:
            _pausado_hasta[nombre] = time.monotonic() + _segundos_de_pausa(resp)
            errores.append(f"{nombre}: {codigo}")
            continue
        try:
            resp.raise_for_status()
            datos = resp.json()
        except Exception as exc:  # noqa: BLE001
            errores.append(f"{nombre}: {type(exc).__name__}")
            continue
        # adsb.lol los da en «ac» y adsb.fi en «aircraft»: se dejan siempre en «ac».
        lista = datos.get("ac") if datos.get("ac") is not None else datos.get("aircraft")
        if not isinstance(lista, list):
            errores.append(f"{nombre}: respuesta sin aviones")
            continue
        return {"ac": lista, "fuente": nombre}
    raise SinServicio("; ".join(errores) or "sin servicios")


def _olvidar() -> None:
    """Para las pruebas: como recién arrancado."""
    _ultima.clear()
    _pausado_hasta.clear()
