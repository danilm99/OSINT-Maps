"""El recolector: pregunta a cada fuente cada cierto tiempo y apunta lo que contesta.

Funciona mientras el programa está abierto. Cada grupo de fuentes va en su propio hilo (un
«hilo» es una tarea que corre a la vez que las demás), para que un servicio lento no retrase
a los otros: los aviones se piden cada veinte segundos aunque el geoportal tarde diez.

Si una fuente falla se apunta el fallo y se le deja más tiempo antes de volver a preguntar
(el doble cada vez, hasta un cuarto de hora), para no insistir a un servicio caído.
"""

from __future__ import annotations

import logging
import threading
import time

import requests

from ..red import nueva_sesion
from . import anomalias
from .almacen import Almacen
from .catalogo import FUENTES
from .fuentes import Fuente

log = logging.getLogger("osintmaps.pulso")

ESPERA_MAXIMA = 900             # segundos: lo más que se espera para reintentar una fuente caída
CADA_GEOMETRIA = 86400          # la posición de los puntos fijos se vuelve a pedir una vez al día
CADA_ANOMALIAS = 300
CADA_LIMPIEZA = 6 * 3600


class Recolector:
    def __init__(self, almacen: Almacen, fuentes: tuple[Fuente, ...] = FUENTES, *, sesion: requests.Session | None = None,
                 reloj=time.time, dias_valores: int = 90, dias_rastros: int = 30):
        self.almacen = almacen
        self.fuentes = fuentes
        self.sesion = sesion
        self.reloj = reloj
        self.dias_valores, self.dias_rastros = dias_valores, dias_rastros
        self.normales = anomalias.Normales(almacen)
        self.comparaciones: list[dict] = []         # lo último que ha dicho `anomalias.evaluar`
        self._parar = threading.Event()
        self._hilos: list[threading.Thread] = []
        self._fallos: dict[str, int] = {}
        self._proxima: dict[str, float] = {}
        self._geometria: dict[str, float] = {}      # cuándo se pidió por última vez con posiciones
        self._candado = threading.Lock()
        self.arrancado = 0.0

    # ------------------------------------------------------------ una toma

    def tomar(self, fuente: Fuente) -> bool:
        """Pregunta una vez a una fuente y guarda lo que conteste. Devuelve si ha ido bien."""
        t = int(self.reloj())
        con_geometria = t - self._geometria.get(fuente.id, 0) >= CADA_GEOMETRIA
        sesion = self.sesion or _sesion_del_hilo()
        try:
            toma = fuente.tomar(sesion, con_geometria)
            if not con_geometria and any(not self.almacen.conoce(serie, ident) for serie, valores in toma.valores.items() for ident in valores):
                # Ha aparecido un punto nuevo (una estación recién abierta): se repite con posiciones.
                toma, con_geometria = fuente.tomar(sesion, True), True
            if toma.n == 0 and not toma.indicadores:
                raise ValueError("respuesta vacía")
            self.almacen.guardar_toma(fuente.id, t, toma)
        except Exception as exc:  # noqa: BLE001  (un fallo de una fuente nunca debe parar el recolector)
            with self._candado:
                self._fallos[fuente.id] = self._fallos.get(fuente.id, 0) + 1
            mensaje = f"{type(exc).__name__}: {exc}"[:300]
            log.debug("Fuente %s: %s", fuente.id, mensaje)
            try:
                self.almacen.guardar_fallo(fuente.id, t, mensaje)
            except Exception:  # noqa: BLE001
                log.debug("No se pudo apuntar el fallo de %s", fuente.id)
            return False
        with self._candado:
            self._fallos[fuente.id] = 0
            if con_geometria:
                self._geometria[fuente.id] = t
        return True

    def espera(self, fuente: Fuente) -> float:
        """Segundos hasta la siguiente pregunta a esta fuente, según cuántas veces seguidas ha fallado."""
        fallos = self._fallos.get(fuente.id, 0)
        return min(fuente.cada * 2 ** min(fallos, 10), max(fuente.cada, ESPERA_MAXIMA)) if fallos else fuente.cada

    # ------------------------------------------------------------ en marcha

    def arrancar(self) -> None:
        """Pone en marcha un hilo por grupo de fuentes y otro para las tareas de fondo."""
        if self._hilos:
            return
        self.arrancado = self.reloj()
        self._parar.clear()
        grupos: dict[str, list[Fuente]] = {}
        for fuente in self.fuentes:
            grupos.setdefault(fuente.grupo, []).append(fuente)
        for grupo, fuentes in grupos.items():
            self._hilos.append(threading.Thread(target=self._bucle, args=(fuentes,), name=f"pulso-{grupo}", daemon=True))
        self._hilos.append(threading.Thread(target=self._fondo, name="pulso-fondo", daemon=True))
        for hilo in self._hilos:
            hilo.start()

    def parar(self) -> None:
        self._parar.set()
        for hilo in self._hilos:
            hilo.join(timeout=5)
        self._hilos = []

    def _bucle(self, fuentes: list[Fuente]) -> None:
        while not self._parar.is_set():
            ahora = time.monotonic()
            for fuente in fuentes:
                if self._parar.is_set():
                    return
                if ahora >= self._proxima.get(fuente.id, 0):
                    self.tomar(fuente)
                    self._proxima[fuente.id] = time.monotonic() + self.espera(fuente)
            self._parar.wait(1.0)

    def _fondo(self) -> None:
        """Cada cinco minutos compara con lo normal; de vez en cuando tira lo antiguo."""
        ultima_limpieza = 0.0
        self._parar.wait(60)            # que haya entrado algo antes de la primera comparación
        while not self._parar.is_set():
            try:
                self.comparaciones = anomalias.evaluar(self.almacen, self.normales, int(self.reloj()))
                if time.monotonic() - ultima_limpieza > CADA_LIMPIEZA:
                    self.almacen.limpiar(int(self.reloj()), self.dias_valores, self.dias_rastros)
                    ultima_limpieza = time.monotonic()
            except Exception:  # noqa: BLE001
                log.debug("Fallo en las tareas de fondo del pulso", exc_info=True)
            self._parar.wait(CADA_ANOMALIAS)

    def estado(self) -> dict:
        with self._candado:
            fallos = dict(self._fallos)
        return {"en_marcha": bool(self._hilos), "arrancado": int(self.arrancado) if self.arrancado else None,
                "fuentes": [{"id": f.id, "nombre": f.nombre, "cada": f.cada, "origen": f.origen, "fallos_seguidos": fallos.get(f.id, 0)} for f in self.fuentes]}


_local = threading.local()


def _sesion_del_hilo() -> requests.Session:
    """Cada hilo usa su propia sesión HTTP (reutiliza la conexión con cada servicio)."""
    if not hasattr(_local, "sesion"):
        _local.sesion = nueva_sesion()
    return _local.sesion
