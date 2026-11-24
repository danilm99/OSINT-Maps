"""Qué es lo normal a cada hora, y cuándo algo se sale de ello.

Una ciudad se repite por semanas: un martes a las ocho se parece al martes anterior a las
ocho mucho más que al domingo. Así que «lo normal» de un indicador en un momento es lo que
marcó a esa misma hora en las semanas anteriores (hasta ocho). Mientras no hay tres semanas
de histórico se usan los días anteriores del mismo tipo (laborable o fin de semana).

De esas muestras se toma la mediana (el valor del medio, que no se deja arrastrar por un día
raro) y cuánto suelen separarse de ella. Si lo de ahora se separa mucho más que eso, es una
anomalía. La medida es la «z robusta»: 0 es lo normal y a partir de 3,5 en valor absoluto se
considera fuera de lo normal.

Nada de esto dice *por qué*: un partido, una manifestación, lluvia o un sensor estropeado
dan la misma señal. Dice dónde mirar.
"""

from __future__ import annotations

import statistics
import threading
import time

from .almacen import Almacen

TRAMO = 1800                    # lo normal se calcula por medias horas
SEMANAS = 8
MIN_MUESTRAS = 4                # con menos días que estos no se opina
UMBRAL = 3.5
DIA, SEMANA = 86400, 7 * 86400

# Los indicadores que se vigilan. El tiempo no entra: que llueva no es una anomalía de la ciudad.
VIGILADOS = ("bicis_fuera", "parking_ocupacion", "trafico_indice", "trafico_cortado", "aforo", "aforo_bici",
             "aire_no2", "aire_pm25", "aviones_bajos", "trenes", "trenes_retraso", "helicopteros", "metro_salidas",
             "metro_sin_servicio", "ora_ocupacion")


def _laborable(t: int) -> bool:
    return time.localtime(t).tm_wday < 5


class Normales:
    """Calcula lo normal de cada indicador. Lee del histórico las medias por media hora de las
    últimas semanas y las recuerda unos minutos, para no releerlas con cada pregunta."""

    def __init__(self, almacen: Almacen, vida: float = 600.0):
        self.almacen = almacen
        self.vida = vida
        self._candado = threading.Lock()
        self._medias: dict[str, dict[int, float]] = {}
        self._leido = float("-inf")         # nunca leído
        self._rango = (0, 0)

    def _cargar(self, t: int) -> dict[str, dict[int, float]]:
        """Las medias por media hora de las semanas anteriores a `t`. Lo normal solo mira hacia atrás
        (como poco, al día anterior), así que lo leído vale aunque sigan entrando datos.

        Se lee de una vez desde nueve semanas antes de `t` hasta ahora: quien recorre un rato del
        pasado tramo a tramo (una gráfica) solo provoca una lectura."""
        desde = t - (SEMANAS + 1) * SEMANA
        with self._candado:
            if time.monotonic() - self._leido > self.vida or desde < self._rango[0] or t > self._rango[1]:
                self._rango = (desde - 3 * DIA, max(t, int(time.time())) + int(self.vida))
                self._medias = self.almacen.indicadores(*self._rango, TRAMO)
                self._leido = time.monotonic()
            return self._medias

    def muestras(self, clave: str, t: int) -> list[float]:
        """Lo que marcó el indicador a esta hora en semanas (o días) anteriores."""
        medias = self._cargar(t).get(clave, {})
        tramo = (t // TRAMO) * TRAMO
        semanales = [medias[tramo - k * SEMANA] for k in range(1, SEMANAS + 1) if tramo - k * SEMANA in medias]
        if len(semanales) >= 3:
            return semanales
        hoy = _laborable(t)
        diarias = [medias[tramo - d * DIA] for d in range(1, 15) if tramo - d * DIA in medias and _laborable(t - d * DIA) == hoy]
        return diarias if len(diarias) > len(semanales) else semanales

    def normal(self, clave: str, t: int) -> tuple[float, float, int] | None:
        """(mediana, dispersión, número de muestras) del indicador a esa hora, o None si no hay con qué comparar."""
        muestras = self.muestras(clave, t)
        if not muestras:
            return None
        mediana = statistics.median(muestras)
        dispersion = statistics.median(abs(x - mediana) for x in muestras)
        return mediana, dispersion, len(muestras)

    def z(self, clave: str, t: int, valor: float) -> dict | None:
        """Cuánto se separa `valor` de lo normal a esa hora."""
        base = self.normal(clave, t)
        if base is None:
            return None
        mediana, dispersion, n = base
        # Suelo para la dispersión: si el histórico es casi plano (siempre 2 tramos cortados), pasar a 3
        # no debe salir como algo extraordinario.
        dispersion = max(dispersion, 0.05 * abs(mediana), 0.5)
        return {"clave": clave, "valor": round(valor, 1), "normal": round(mediana, 1), "z": round(0.6745 * (valor - mediana) / dispersion, 1), "n": n}


def evaluar(almacen: Almacen, normales: Normales, t: int, claves: tuple[str, ...] = VIGILADOS, ventana: int = 900) -> list[dict]:
    """Compara cada indicador vigilado (su media del último cuarto de hora) con lo normal y apunta como
    suceso lo que se sale. Devuelve todas las comparaciones que ha podido hacer."""
    ahora = almacen.indicadores(t - ventana, t + 1, ventana * 2, claves)
    salida = []
    for clave in claves:
        valores = list(ahora.get(clave, {}).values())
        if not valores:
            continue
        valor = sum(valores) / len(valores)
        comparacion = normales.z(clave, t, valor)
        if comparacion is None:
            continue
        comparacion["anomalia"] = comparacion["n"] >= MIN_MUESTRAS and abs(comparacion["z"]) >= UMBRAL
        if comparacion["anomalia"]:
            almacen.guardar_suceso(clave, t, comparacion["valor"], comparacion["normal"], comparacion["z"])
        salida.append(comparacion)
    return salida
