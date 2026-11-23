"""Sube a la web solo los datos, sin tocar el visor.

`osintmaps publicar` rehace la web entera (visor y datos). Esto es otra cosa: coge la web
tal como está publicada, cambia los ficheros de datos que se le pasan y la vuelve a subir.
Así se puede actualizar cada cuarto de hora sin que importe qué versión del visor hay
publicada ni quién la publicó.

La web vive en la rama `gh-pages` del repositorio, que tiene siempre un único commit (una
«foto» de la carpeta). Aquí se baja esa foto, se cambian los ficheros y se sube otra foto
en su lugar. Si entre la bajada y la subida alguien ha publicado otra cosa, la subida se
rechaza sola y se deja para la siguiente vuelta: nunca se pisa una publicación ajena.

GitHub rehace la página con cada subida y pide no pasar de unas diez por hora; por eso hay
un mínimo de diez minutos entre dos subidas.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("osintmaps.pulso")

RAMA = "gh-pages"
MINUTOS_MINIMOS = 10
_SUFIJO = re.compile(r" · datos de las \d{1,2}:\d{2}( del \d{4}-\d{2}-\d{2})?$")


class SinWeb(RuntimeError):
    """Todavía no hay web publicada: no hay dónde poner los datos."""


def _git(*orden: str, carpeta: Path, tiempo: float = 180.0) -> str:
    # GIT_TERMINAL_PROMPT=0: si git necesitara pedir usuario y contraseña, que falle en vez de quedarse
    # esperando una respuesta que nadie va a dar (esto corre en segundo plano).
    # LC_ALL=C: los mensajes de git en inglés, para reconocerlos esté el sistema en el idioma que esté.
    entorno = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C", LANGUAGE="en")
    r = subprocess.run(["git", *orden], cwd=carpeta, capture_output=True, text=True, encoding="utf-8", errors="replace", env=entorno, timeout=tiempo)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(orden[:2])}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def repositorio_de(carpeta: Path) -> str:
    """La dirección del repositorio («origin») de la carpeta del programa."""
    return _git("remote", "get-url", "origin", carpeta=carpeta)


def publicar_datos(repo: str, ficheros: dict[str, bytes], trabajo: Path, ahora: float | None = None) -> str:
    """Cambia en la web publicada los ficheros de `datos/` que se pasan (nombre -> contenido).

    `trabajo` es una carpeta donde se guarda una copia de la web entre una vez y la siguiente,
    para no bajarla entera cada vez. Devuelve «publicado» o «sin cambios».
    """
    for nombre in ficheros:
        if Path(nombre).name != nombre or nombre.startswith("."):
            raise ValueError(f"nombre de fichero no válido: {nombre}")
    trabajo.mkdir(parents=True, exist_ok=True)
    if not (trabajo / ".git").exists():
        _git("init", "-q", carpeta=trabajo)
    try:
        _git("fetch", "-q", "--depth", "1", repo, RAMA, carpeta=trabajo)
    except RuntimeError as exc:
        if "couldn't find remote ref" in str(exc):
            raise SinWeb("Aún no hay web publicada. Publícala una vez con «osintmaps publicar».") from exc
        raise
    base = _git("rev-parse", "FETCH_HEAD", carpeta=trabajo)
    _git("checkout", "-q", "--force", "--detach", base, carpeta=trabajo)
    _git("clean", "-fdq", carpeta=trabajo)

    (trabajo / "datos").mkdir(exist_ok=True)
    for nombre, contenido in ficheros.items():
        (trabajo / "datos" / nombre).write_bytes(contenido)
    _git("add", "-A", "datos", carpeta=trabajo)
    if not _git("status", "--porcelain", carpeta=trabajo):
        return "sin cambios"

    # El mensaje del commit dice cuándo se publicó la web; se le añade (o se le cambia) de cuándo son los datos.
    momento = time.localtime(ahora or time.time())
    mensaje = _SUFIJO.sub("", _git("log", "-1", "--format=%s", carpeta=trabajo)) + f" · datos de las {time.strftime('%H:%M del %Y-%m-%d', momento)}"
    _git("-c", "user.name=OSINT Maps", "-c", "user.email=osintmaps@users.noreply.github.com",
         "commit", "-q", "--amend", "-m", mensaje, carpeta=trabajo)
    # «--force-with-lease» sube solo si la rama sigue como estaba al bajarla.
    _git("push", "-q", f"--force-with-lease={RAMA}:{base}", repo, f"HEAD:{RAMA}", carpeta=trabajo)
    return "publicado"


class Publicador:
    """Publica los datos al arrancar y luego cada cierto tiempo, en segundo plano."""

    def __init__(self, repo: str, trabajo: Path, preparar: Callable[[], dict[str, bytes]], minutos: float = 15, espera_inicial: float = 90,
                 publicar: Callable[..., str] = publicar_datos):
        self.repo, self.trabajo, self.preparar = repo, trabajo, preparar
        self.minutos = max(float(minutos), MINUTOS_MINIMOS)
        self.espera_inicial = espera_inicial
        self._publicar = publicar
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self.ultima: dict = {"cuando": None, "resultado": None, "error": None, "bytes": 0}
        self.veces = 0

    def una_vez(self) -> str:
        """Prepara los ficheros y los sube. Apunta cómo ha ido; no lanza errores."""
        try:
            ficheros = self.preparar()
            resultado = self._publicar(self.repo, ficheros, self.trabajo)
            self.ultima = {"cuando": int(time.time()), "resultado": resultado, "error": None, "bytes": sum(len(c) for c in ficheros.values())}
            self.veces += 1
            if self.veces % 24 == 0:
                self._ordenar()
        except Exception as exc:  # noqa: BLE001  (sin red, sin permiso, otra publicación a la vez: se reintenta a la siguiente)
            resultado = "fallo"
            self.ultima = dict(self.ultima, resultado="fallo", error=str(exc)[:300], intento=int(time.time()))
            log.debug("No se pudo publicar el pulso: %s", exc)
        return resultado

    def _ordenar(self) -> None:
        """Cada subida deja en la copia de trabajo la foto anterior, que ya no sirve: de vez en cuando se tiran."""
        try:
            _git("reflog", "expire", "--expire=now", "--all", carpeta=self.trabajo)
            _git("gc", "-q", "--prune=now", carpeta=self.trabajo)
        except Exception:  # noqa: BLE001
            pass

    def arrancar(self) -> None:
        if self._hilo:
            return
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, name="pulso-publicar", daemon=True)
        self._hilo.start()

    def parar(self) -> None:
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout=5)
        self._hilo = None

    def _bucle(self) -> None:
        # La primera, al poco de arrancar: lo justo para que hayan entrado las primeras tomas.
        if self._parar.wait(self.espera_inicial):
            return
        while not self._parar.is_set():
            self.una_vez()
            self._parar.wait(self.minutos * 60)

    def estado(self) -> dict:
        return dict(self.ultima, cada_minutos=self.minutos, en_marcha=self._hilo is not None, repo=re.sub(r"//[^/@]*@", "//", self.repo))
