"""Todas las fuentes del pulso juntas: las de cifras (fuentes.py), las de textos (textos.py) y
las de agenda (agenda.py). Quien necesite la lista completa la toma de aquí."""

from __future__ import annotations

from . import agenda, fuentes, textos

FUENTES: tuple[fuentes.Fuente, ...] = fuentes.FUENTES + textos.FUENTES + agenda.FUENTES
INDICADORES: dict[str, dict] = {**fuentes.INDICADORES, **textos.INDICADORES, **agenda.INDICADORES}
SERIES: dict[str, str] = {**fuentes.SERIES, **agenda.SERIES}
POR_ID: dict[str, fuentes.Fuente] = {f.id: f for f in FUENTES}
