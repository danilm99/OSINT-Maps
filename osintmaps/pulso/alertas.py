"""Alertas al móvil cuando un suceso merece la pena: un aviso por suceso, solo con confianza alta (o un posible
incidente con confianza media). Están apagadas hasta que se elige adónde mandarlas.

Se mandan por ntfy (https://ntfy.sh), un servicio de avisos que no pide cuenta: se elige un nombre de tema
difícil de adivinar, se instala la aplicación de ntfy en el móvil y se suscribe a ese tema. Para encenderlas,
un fichero `alertas.json` en la carpeta de datos:

    {"ntfy": "osintmaps-vlc-pon-aqui-algo-tuyo"}

(o la dirección entera, si es un servidor ntfy propio). Lo que sale es el titular del suceso, la hora, la
confianza y el enlace a la sala: lo mismo que ya se ve en la web, nada de personas ni de publicaciones de redes.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger("osintmaps.pulso")
FICHERO = "alertas.json"
ENVIADAS = "alertas-enviadas.json"
WEB = "https://danilm99.github.io/OSINT-Maps/sala.html"


def merece_alerta(suceso: dict) -> bool:
    """Confianza alta, o un posible incidente con confianza media; nunca lo marcado como falso positivo."""
    if suceso.get("estado") != "activo" or suceso.get("valoracion") == "falso":
        return False
    return suceso.get("confianza") == "alta" or (suceso.get("confianza") == "media" and suceso.get("tipo") == "incidente")


class Alertas:
    def __init__(self, carpeta: Path, sesion: requests.Session | None = None):
        self.carpeta = Path(carpeta)
        self.sesion = sesion or requests.Session()
        self._enviadas: dict[str, int] | None = None
        self.ultimo_error: str | None = None

    def destino(self) -> str | None:
        """La dirección de ntfy configurada, o None si las alertas están apagadas."""
        try:
            tema = (json.loads((self.carpeta / FICHERO).read_text(encoding="utf-8")).get("ntfy") or "").strip()
        except (OSError, ValueError, AttributeError):
            return None
        if not tema:
            return None
        return tema if tema.startswith("https://") else f"https://ntfy.sh/{tema}"

    def _leer_enviadas(self) -> dict[str, int]:
        if self._enviadas is None:
            try:
                self._enviadas = json.loads((self.carpeta / ENVIADAS).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._enviadas = {}
        return self._enviadas

    def avisar(self, sucesos: list[dict], ahora: int | None = None) -> list[str]:
        """Manda una alerta por cada suceso que la merece y aún no la tiene. Devuelve los ids avisados."""
        destino = self.destino()
        if not destino:
            return []
        ahora = int(ahora or time.time())
        enviadas = self._leer_enviadas()
        hechos = []
        for s in sucesos:
            if s["id"] in enviadas or not merece_alerta(s):
                continue
            cuerpo = f"Desde las {time.strftime('%H:%M', time.localtime(s['inicio']))}. Confianza {s.get('confianza')}."
            try:
                resp = self.sesion.post(destino, data=cuerpo.encode("utf-8"), timeout=15, headers={
                    "Title": (s.get("titulo") or "Suceso").encode("utf-8").decode("latin-1", "ignore") or "Suceso",
                    "Priority": "high" if s.get("tipo") == "incidente" else "default", "Tags": "rotating_light" if s.get("tipo") == "incidente" else "cityscape",
                    "Click": f"{WEB}#suceso={s['id']}"})
                resp.raise_for_status()
                self.ultimo_error = None
            except Exception as exc:  # noqa: BLE001 - una alerta que no sale no para la sala
                self.ultimo_error = str(exc)[:200]
                log.warning("Alertas: no se ha podido avisar (%s)", exc)
                continue
            enviadas[s["id"]] = ahora
            hechos.append(s["id"])
        if hechos:
            for ident in [i for i, t in enviadas.items() if t < ahora - 7 * 86400]:
                del enviadas[ident]
            try:
                (self.carpeta / ENVIADAS).write_text(json.dumps(enviadas), encoding="utf-8")
            except OSError:
                pass
        return hechos

    def estado(self) -> dict:
        return {"encendidas": self.destino() is not None, "error": self.ultimo_error, "enviadas": len(self._leer_enviadas())}
