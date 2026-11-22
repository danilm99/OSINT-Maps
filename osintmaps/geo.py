"""Utilidades geográficas pequeñas.

Las coordenadas geográficas (latitud/longitud) van en grados, y un grado no
mide lo mismo en todas partes. Para medir distancias en metros entre puntos
cercanos basta una proyección local: se toma un punto de referencia y se
convierte cada diferencia de grados a metros.
"""

from __future__ import annotations

import math

import numpy as np
import shapely

METROS_POR_GRADO = 111_320.0  # longitud aproximada de un grado de latitud


class ProyeccionLocal:
    """Convierte lon/lat a metros alrededor de un punto de referencia.

    El error es despreciable (menos del 1 %) para zonas del tamaño de una
    provincia, que es más que suficiente para decidir si dos cosas están a
    30 m una de otra.
    """

    def __init__(self, lat0: float, lon0: float) -> None:
        self.lat0 = lat0
        self.lon0 = lon0
        self.kx = METROS_POR_GRADO * math.cos(math.radians(lat0))
        self.ky = METROS_POR_GRADO

    def punto(self, lat: float, lon: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def geometria(self, geom):
        """Proyecta una geometría shapely dada en lon/lat."""
        def convertir(coords: np.ndarray) -> np.ndarray:
            salida = np.empty_like(coords, dtype=float)
            salida[:, 0] = (coords[:, 0] - self.lon0) * self.kx
            salida[:, 1] = (coords[:, 1] - self.lat0) * self.ky
            return salida
        return shapely.transform(geom, convertir)


def caja_alrededor(lat: float, lon: float, lado_m: float) -> tuple[float, float, float, float]:
    """Caja cuadrada (oeste, sur, este, norte) de `lado_m` metros centrada en un punto."""
    dlat = (lado_m / 2) / METROS_POR_GRADO
    dlon = (lado_m / 2) / (METROS_POR_GRADO * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def trocear_caja(
    caja: tuple[float, float, float, float], paso: float
) -> list[tuple[float, float, float, float]]:
    """Divide una caja (oeste, sur, este, norte) en teselas de `paso` grados como máximo."""
    oeste, sur, este, norte = caja
    nx = max(1, math.ceil((este - oeste) / paso))
    ny = max(1, math.ceil((norte - sur) / paso))
    dx, dy = (este - oeste) / nx, (norte - sur) / ny
    return [
        (oeste + i * dx, sur + j * dy, oeste + (i + 1) * dx, sur + (j + 1) * dy)
        for i in range(nx)
        for j in range(ny)
    ]


def parsear_caja(texto: str) -> tuple[float, float, float, float]:
    """Lee "oeste,sur,este,norte" y comprueba que tiene sentido."""
    try:
        oeste, sur, este, norte = (float(x) for x in texto.split(","))
    except ValueError as exc:
        raise ValueError("La caja debe ser: oeste,sur,este,norte (en grados)") from exc
    if not (-180 <= oeste < este <= 180 and -90 <= sur < norte <= 90):
        raise ValueError("Caja incoherente: revisa el orden oeste,sur,este,norte")
    return oeste, sur, este, norte
