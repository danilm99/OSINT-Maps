"""Estructura de datos común a todo el programa.

Cada fuente (Catastro, OSM, Wikidata) produce objetos `Candidato`. Después se
fusionan los que apuntan al mismo sitio y se les pone nota.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Categorías posibles de un candidato. El orden no importa.
CATEGORIAS = (
    "despoblado",       # pueblos, aldeas y masías deshabitadas
    "industrial",       # fábricas, naves, almacenes, centrales
    "mineria",          # minas, canteras, pozos
    "militar",          # cuarteles, búnkeres, baterías
    "ferroviario",      # estaciones, túneles, apeaderos
    "sanitario",        # hospitales, sanatorios
    "educativo",        # colegios, institutos
    "religioso",        # iglesias, conventos, ermitas
    "ocio_hosteleria",  # hoteles, discotecas, cines, parques acuáticos
    "equipamiento",     # edificios de servicios públicos (según Catastro)
    "patrimonio",       # castillos, torres y ruinas históricas
    "oficinas",
    "comercial",
    "residencial",
    "agrario",
    "otro",
)

# Estados, de más a menos deteriorado.
ESTADOS = ("ruina", "abandonado", "deficiente", "en_desuso")


@dataclass
class Candidato:
    """Un lugar que puede estar abandonado."""

    id: str
    lat: float
    lon: float
    nombre: str | None = None
    categoria: str = "otro"
    estado: str | None = None
    fuentes: list[str] = field(default_factory=list)

    # Datos físicos (los da sobre todo Catastro)
    superficie_m2: float | None = None             # huella en planta
    superficie_construida_m2: float | None = None  # suma de todas las plantas
    mayor_edificio_m2: float | None = None         # huella del edificio más grande
    n_edificios: int = 1
    anio: int | None = None
    vecinos_150m: int | None = None                # edificios en uso a menos de 150 m
    municipio: str | None = None

    # Identificadores en cada fuente
    refcats: list[str] = field(default_factory=list)   # referencias catastrales
    osm_ids: list[str] = field(default_factory=list)   # p. ej. "way/123456"
    wikidata: str | None = None                        # p. ej. "Q12345"
    wikipedia: str | None = None                       # p. ej. "es:Nombre del artículo"
    etiquetas: dict[str, str] = field(default_factory=dict)  # etiquetas OSM útiles

    # Geometría del contorno en WGS84 (objeto shapely). No va al GeoJSON de puntos.
    huella: Any = None

    # Datos internos de la fusión (no se exportan).
    # debil: objeto de OSM que solo dice "edificio abandonado", sin nombre ni tipo.
    #   Suele ser el propio Catastro importado a OSM, así que no confirma nada.
    # tipo_confirmado: la categoría viene de una fuente que describe el sitio
    #   (OSM con tipo concreto o Wikidata), no del uso genérico de Catastro.
    debil: bool = False
    tipo_confirmado: bool = False

    # Resultados de análisis posteriores
    senales: dict[str, Any] = field(default_factory=dict)
    fotos: list[dict[str, str]] = field(default_factory=list)
    enlaces: dict[str, str] = field(default_factory=dict)
    puntuacion: float = 0.0
    desglose: dict[str, float] = field(default_factory=dict)

    def propiedades(self) -> dict[str, Any]:
        """Diccionario plano para exportar (sin la geometría)."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "categoria": self.categoria,
            "estado": self.estado,
            "puntuacion": round(self.puntuacion, 1),
            "desglose": self.desglose,
            "fuentes": self.fuentes,
            "superficie_m2": _redondear(self.superficie_m2),
            "superficie_construida_m2": _redondear(self.superficie_construida_m2),
            "mayor_edificio_m2": _redondear(self.mayor_edificio_m2),
            "tipo_confirmado": self.tipo_confirmado,
            "n_edificios": self.n_edificios,
            "anio": self.anio,
            "vecinos_150m": self.vecinos_150m,
            "municipio": self.municipio,
            "refcats": self.refcats,
            "osm_ids": self.osm_ids,
            "wikidata": self.wikidata,
            "wikipedia": self.wikipedia,
            "etiquetas": self.etiquetas,
            "senales": self.senales,
            "fotos": self.fotos,
            "enlaces": self.enlaces,
        }


def _redondear(valor: float | None) -> int | None:
    return None if valor is None else int(round(valor))
