"""Peticiones HTTP con reintentos y caché en disco.

Todas las fuentes son servicios públicos gratuitos: nos identificamos con un
User-Agent propio, reintentamos con pausas y guardamos en caché lo descargado
para no repetir peticiones al relanzar el programa.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from . import __version__

log = logging.getLogger(__name__)

USER_AGENT = f"OSINT-Maps/{__version__} (https://github.com/danilm99/OSINT-Maps)"


def nueva_sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers["User-Agent"] = USER_AGENT
    return sesion


def pedir(
    sesion: requests.Session,
    metodo: str,
    url: str,
    *,
    reintentos: int = 3,
    espera: float = 5.0,
    timeout: float = 60.0,
    **kwargs: Any,
) -> requests.Response:
    """Hace una petición y reintenta si el servidor falla o está saturado."""
    ultimo_error: Exception | None = None
    for intento in range(1, reintentos + 1):
        try:
            resp = sesion.request(metodo, url, timeout=timeout, **kwargs)
            # 429 = demasiadas peticiones; 5xx = fallo del servidor. Merece reintento.
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            ultimo_error = exc
            codigo = getattr(getattr(exc, "response", None), "status_code", None)
            # Un 4xx que no sea 429 es error nuestro: reintentar no lo arregla.
            if codigo is not None and 400 <= codigo < 500 and codigo != 429:
                raise
            if intento < reintentos:
                pausa = espera * intento
                log.warning("Fallo en %s (%s). Reintento %d/%d en %.0f s",
                            url, exc, intento, reintentos - 1, pausa)
                time.sleep(pausa)
    assert ultimo_error is not None
    raise ultimo_error


def descargar(sesion: requests.Session, url: str, destino: Path, *, timeout: float = 120.0) -> Path:
    """Descarga un fichero grande a disco. Si ya existe, no lo vuelve a bajar."""
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".parcial")
    resp = pedir(sesion, "GET", url, timeout=timeout, stream=True)
    with open(temporal, "wb") as fh:
        for trozo in resp.iter_content(chunk_size=1 << 16):
            fh.write(trozo)
    temporal.replace(destino)  # solo aparece con su nombre final si se completó
    return destino


class CacheJSON:
    """Guarda respuestas JSON en disco, indexadas por una clave de texto."""

    def __init__(self, carpeta: Path, activa: bool = True) -> None:
        self.carpeta = carpeta
        self.activa = activa

    def _ruta(self, clave: str) -> Path:
        resumen = hashlib.sha1(clave.encode("utf-8")).hexdigest()[:20]
        return self.carpeta / f"{resumen}.json"

    def leer(self, clave: str) -> Any | None:
        ruta = self._ruta(clave)
        if not self.activa or not ruta.exists():
            return None
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def guardar(self, clave: str, datos: Any) -> None:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._ruta(clave).write_text(json.dumps(datos), encoding="utf-8")
