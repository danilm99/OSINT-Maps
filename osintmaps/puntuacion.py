"""Puntuación de interés (0-100) de cada candidato.

La nota es una suma de factores sencillos. NO mide si se puede entrar ni si
merece la pena: solo ordena los candidatos para revisar primero los más
prometedores. Los pesos están ajustados mirando resultados reales de la
provincia de Valencia; cámbialos aquí según lo que veas en tu zona.

Factores y máximo de cada uno:

    estado       16   ruina/abandonado puntúa más que deficiente/en desuso
    tamano       20   superficie en planta, en escala logarítmica
    categoria    15   un sanatorio interesa más que un cobertizo agrícola
    fuentes      15   confirmado por 2 o 3 fuentes independientes
    aislamiento  12   pocos edificios en uso alrededor, o mayoría de ruinas
    conjunto      8   varios edificios deteriorados juntos
    identidad     5   tiene nombre y/o artículo
    antiguedad    4   construido hace mucho
    vegetacion    5   (opcional) la vegetación avanza según Sentinel-2
"""

from __future__ import annotations

import math

from .modelos import Candidato

PESO_ESTADO = {"ruina": 16, "abandonado": 16, "deficiente": 10, "en_desuso": 9}

PESO_CATEGORIA = {
    "despoblado": 15, "militar": 15, "sanitario": 15,
    "industrial": 14, "mineria": 14,
    "ferroviario": 13, "ocio_hosteleria": 13,
    "educativo": 12, "religioso": 12, "equipamiento": 12,
    "patrimonio": 8, "oficinas": 8,
    "comercial": 7,
    "residencial": 5, "otro": 4, "agrario": 2,
}

TAMANO_MAX = 20.0
SUPERFICIE_MIN = 100.0        # por debajo, 0 puntos
SUPERFICIE_TOPE = 50_000.0    # a partir de aquí, puntuación máxima
TAMANO_DESCONOCIDO = 7.0      # candidatos sin superficie (solo OSM/Wikidata)


def _tamano(superficie: float | None) -> float:
    if superficie is None:
        return TAMANO_DESCONOCIDO
    if superficie <= SUPERFICIE_MIN:
        return 0.0
    # Escala logarítmica: pasar de 100 a 1.000 m² cuenta lo mismo que de 1.000 a 10.000.
    fraccion = math.log10(superficie / SUPERFICIE_MIN) / math.log10(SUPERFICIE_TOPE / SUPERFICIE_MIN)
    return TAMANO_MAX * min(1.0, fraccion)


# Catastro llama "industrial" también a pajares y almacenes de pueblo. Si el
# tipo no lo confirma otra fuente, la categoría solo puntúa entera cuando el
# edificio principal tiene tamaño de nave.
EDIFICIO_DE_REFERENCIA = 400.0


def _categoria(c: Candidato) -> float:
    peso = float(PESO_CATEGORIA.get(c.categoria, 4))
    if c.tipo_confirmado or c.mayor_edificio_m2 is None:
        return peso
    return round(peso * min(1.0, max(0.3, c.mayor_edificio_m2 / EDIFICIO_DE_REFERENCIA)), 1)


def _aislamiento(vecinos: int | None, n_edificios: int) -> float:
    """Cuánto domina lo abandonado en su entorno.

    Puntúa tener pocos edificios en uso a 150 m. Una aldea en ruinas con un par
    de casas arregladas sigue puntuando: ahí cuenta la proporción.
    """
    if vecinos is None:
        return 5.0
    if vecinos == 0:
        base = 12.0
    elif vecinos <= 3:
        base = 10.0
    elif vecinos <= 10:
        base = 6.0
    elif vecinos <= 30:
        base = 3.0
    else:
        base = 0.0
    proporcion = n_edificios / (n_edificios + vecinos)
    if n_edificios >= 3 and proporcion >= 0.6:
        base = max(base, 9.0)
    elif n_edificios >= 3 and proporcion >= 0.4:
        base = max(base, 6.0)
    return base


def _conjunto(n: int) -> float:
    if n >= 15:
        return 8.0
    if n >= 5:
        return 6.0
    if n >= 2:
        return 3.0
    return 0.0


def _vegetacion(senales: dict) -> float:
    """Pendiente del NDVI (índice de vegetación) en unidades por año."""
    pendiente = senales.get("ndvi_pendiente")
    if pendiente is None:
        return 0.0
    if pendiente >= 0.02:
        return 5.0
    if pendiente >= 0.01:
        return 3.0
    return 0.0


def puntuar(c: Candidato) -> float:
    """Calcula la nota y deja el desglose guardado en el candidato."""
    desglose = {
        "estado": float(PESO_ESTADO.get(c.estado or "", 8)),
        "tamano": round(_tamano(c.superficie_m2), 1),
        "categoria": _categoria(c),
        "fuentes": {1: 0.0, 2: 10.0}.get(len(set(c.fuentes)), 15.0) if c.fuentes else 0.0,
        "aislamiento": _aislamiento(c.vecinos_150m, c.n_edificios),
        "conjunto": _conjunto(c.n_edificios),
        "identidad": (3.0 if c.nombre else 0.0) + (2.0 if (c.wikidata or c.wikipedia) else 0.0),
        "antiguedad": 4.0 if (c.anio and c.anio < 1940) else 2.0 if (c.anio and c.anio < 1975) else 0.0,
        "vegetacion": _vegetacion(c.senales),
    }
    c.desglose = {k: v for k, v in desglose.items() if v}
    c.puntuacion = min(100.0, sum(desglose.values()))
    return c.puntuacion


def puntuar_todos(candidatos: list[Candidato]) -> list[Candidato]:
    """Puntúa y devuelve la lista ordenada de mayor a menor nota."""
    for c in candidatos:
        puntuar(c)
    return sorted(candidatos, key=lambda c: (-c.puntuacion, c.id))
