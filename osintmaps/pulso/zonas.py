"""Dónde cae cada cosa: barrios, vecinos y un nomenclátor para situar textos en el mapa.

Todo lo que se cruza se lleva a una unidad común, el **barrio** (88 en València, del
Ajuntament). Un punto se asigna al barrio que lo contiene; los barrios que se tocan son
«vecinos», y así un suceso que ocupa Algirós y Benimaclet sale como uno solo.

El **nomenclátor** busca en un texto (una noticia, una publicación, un accidente) nombres de
calles, barrios y lugares conocidos y devuelve dónde están. Las calles del Ajuntament están
en valenciano («Carrer del Canonge Tàrrega») y la prensa suele escribir en castellano («calle
Canónigo Tárrega»): se comparan quitando el tipo de vía, las partículas y los acentos, y con
una tabla de equivalencias de las palabras que más cambian (Sant/San, Pare/Padre...).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.strtree import STRtree

from .contexto import leer_geojson

# Lugares que la prensa nombra a menudo y que no salen como calle ni como barrio.
LUGARES_CONOCIDOS: dict[str, tuple[float, float]] = {
    "mestalla": (39.4746, -0.3583), "nou mestalla": (39.4930, -0.4005), "estadio ciutat de valencia": (39.4947, -0.3647),
    "ciutat de valencia": (39.4947, -0.3647), "roig arena": (39.4560, -0.3530),
    "ciudad de las artes y las ciencias": (39.4545, -0.3502), "ciutat de les arts i les ciencies": (39.4545, -0.3502),
    "hemisferic": (39.4560, -0.3540), "oceanografic": (39.4527, -0.3474), "palau de les arts": (39.4580, -0.3557),
    "museu de les ciencies": (39.4550, -0.3510), "agora": (39.4535, -0.3490),
    "plaza del ayuntamiento": (39.4699, -0.3763), "placa de l'ajuntament": (39.4699, -0.3763), "plaza de la reina": (39.4743, -0.3753),
    "plaza de la virgen": (39.4766, -0.3752), "estacion del norte": (39.4664, -0.3774), "estacio del nord": (39.4664, -0.3774),
    "joaquin sorolla": (39.4609, -0.3818), "mercado central": (39.4736, -0.3790), "mercat central": (39.4736, -0.3790),
    "lonja": (39.4744, -0.3786), "llotja": (39.4744, -0.3786), "catedral": (39.4755, -0.3753), "micalet": (39.4753, -0.3754),
    "torres de serranos": (39.4791, -0.3759), "torres de quart": (39.4757, -0.3838), "jardin del turia": (39.4760, -0.3700),
    "jardi del turia": (39.4760, -0.3700), "cauce del turia": (39.4760, -0.3700), "bioparc": (39.4787, -0.4108),
    "malvarrosa": (39.4810, -0.3245), "malva-rosa": (39.4810, -0.3245), "playa de las arenas": (39.4655, -0.3233),
    "la marina": (39.4610, -0.3260), "marina de valencia": (39.4610, -0.3260), "veles e vents": (39.4609, -0.3249),
    "puerto de valencia": (39.4430, -0.3170), "port de valencia": (39.4430, -0.3170),
    "hospital la fe": (39.4440, -0.3765), "hospital clinico": (39.4780, -0.3600), "hospital general": (39.4680, -0.4070),
    "hospital peset": (39.4580, -0.3880), "universitat politecnica": (39.4810, -0.3410), "upv": (39.4810, -0.3410),
    "campus de blasco ibanez": (39.4780, -0.3640), "campus de tarongers": (39.4780, -0.3440), "palau de la musica": (39.4643, -0.3633),
    "plaza de toros": (39.4660, -0.3760), "viveros": (39.4800, -0.3660), "jardines del real": (39.4800, -0.3660),
    "feria valencia": (39.5110, -0.4430), "nuevo centro": (39.4800, -0.3920), "bonaire": (39.4500, -0.5300),
    "la albufera": (39.3330, -0.3520), "el saler": (39.3800, -0.3260), "pinedo": (39.4240, -0.3330),
    "cabanyal": (39.4690, -0.3290), "cabanal": (39.4690, -0.3290), "russafa": (39.4620, -0.3740), "ruzafa": (39.4620, -0.3740),
    "benimaclet": (39.4860, -0.3600), "el carmen": (39.4780, -0.3810), "el carme": (39.4780, -0.3810), "barrio del carmen": (39.4780, -0.3810),
}

# Tipos de vía, en las dos lenguas y abreviados, que pueden ir delante del nombre de una calle.
TIPOS_VIA = (
    "calle", "carrer", "cl", "avenida", "avda", "av", "avinguda", "plaza", "pl", "placa", "paseo", "pg", "passeig",
    "camino", "cami", "ronda", "gran via", "bulevar", "boulevard", "travesia", "travessera", "pasaje", "passatge",
    "glorieta", "carretera", "ctra", "puente", "pont", "muelle", "moll", "senda", "pasarela", "jardin", "jardi",
)
PARTICULAS = {"de", "del", "la", "las", "los", "el", "els", "les", "d", "l", "i", "y", "en", "na", "dels", "al", "a"}
# Palabras que cambian entre valenciano y castellano en el nombre de las calles (se reducen a una forma).
EQUIVALENCIAS = {
    "sant": "san", "santa": "santa", "pare": "padre", "mare": "madre", "deu": "dios", "mestre": "maestro",
    "canonge": "canonigo", "arquebisbe": "arzobispo", "bisbe": "obispo", "germans": "hermanos", "comte": "conde",
    "duc": "duque", "rei": "rey", "riu": "rio", "port": "puerto", "pont": "puente", "cami": "camino", "placa": "plaza",
    "avinguda": "avenida", "passeig": "paseo", "carrer": "calle", "xativa": "jativa", "russafa": "ruzafa",
    "beat": "beato", "doctor": "doctor", "metge": "medico", "pintor": "pintor", "poeta": "poeta", "escultor": "escultor",
    "music": "musico", "general": "general", "pere": "pedro", "joan": "juan", "josep": "jose", "vicent": "vicente",
    "jaume": "jaime", "lluis": "luis", "miquel": "miguel", "francesc": "francisco", "antoni": "antonio", "jordi": "jorge",
    "marti": "martin", "tomas": "tomas", "nostra": "nuestra", "senyora": "senora", "verge": "virgen", "creu": "cruz",
    "mar": "mar", "nou": "nuevo", "nova": "nueva", "vell": "viejo", "vella": "vieja", "alt": "alto", "baix": "bajo",
    "ciutat": "ciudad", "universitat": "universidad", "facultat": "facultad", "esglesia": "iglesia", "convent": "convento",
    "baptista": "bautista", "gaspar": "gaspar", "salvador": "salvador", "mateu": "mateo", "bernat": "bernardo",
    "ramon": "ramon", "guillem": "guillermo", "berenguer": "berenguer", "arxiduc": "archiduque", "reina": "reina",
    "infanta": "infanta", "princep": "principe", "princesa": "princesa", "cavallers": "caballeros", "historiador": "historiador",
    "llibertat": "libertad", "pau": "paz", "mercat": "mercado", "plata": "plata", "fusters": "carpinteros",
}
# Nombres de barrio que son también palabras corrientes: solo cuentan si delante pone «barrio» o «barri».
BARRIOS_AMBIGUOS = {"la seu", "el mercat", "sant francesc", "la roqueta", "el pilar", "el botanic", "la petxina", "la raiosa",
                    "en corts", "malilla", "la fonteta", "la creu coberta", "sant marcel·li", "camí real", "la carrasca",
                    "els orriols", "torrefiel", "la llum", "la isla perdida", "la punta", "castellar-l'oliverar", "la vega baixa",
                    "el forn d'alcedo", "faitanar", "la torre", "pinedo", "el saler", "el palmar", "el perellonet", "carpesa",
                    "benifaraig", "borbotó", "massarrojos", "poble nou", "mauella", "tauladella", "rafalell-vistabella",
                    "nou moles", "soternes", "tres forques", "beteró", "la carrasca", "aiora", "albors", "l'amistat"}


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos, sin signos: «Plaça de l'Ajuntament» -> «placa de l ajuntament»."""
    t = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii").lower()
    t = t.replace("·", "").replace("l.l", "ll")
    return re.sub(r"[^a-z0-9/]+", " ", t).strip()


def clave_nombre(texto: str) -> str:
    """La forma con la que se comparan nombres de calle: sin tipo de vía ni partículas, y con las
    palabras que cambian entre lenguas reducidas a una forma."""
    palabras = normalizar(texto).replace("/", " ").split()
    while palabras and palabras[0] in _TIPOS_SUELTOS:        # el tipo de vía delante no cuenta
        palabras = palabras[1:]
    salida = [EQUIVALENCIAS.get(p, p) for p in palabras if p not in PARTICULAS]
    return " ".join(salida)


_TIPOS_SUELTOS = {"calle", "carrer", "cl", "c", "avenida", "avda", "av", "avinguda", "plaza", "pl", "placa", "paseo", "pg",
                  "passeig", "camino", "cami", "ronda", "bulevar", "boulevard", "travesia", "travessera", "pasaje", "passatge",
                  "glorieta", "carretera", "ctra", "senda", "pasarela", "muelle", "moll"}


@dataclass
class Lugar:
    nombre: str
    tipo: str                   # calle, direccion, cruce, barrio, lugar
    lat: float
    lon: float
    barrio: str | None = None
    confianza: float = 0.5      # 0..1
    texto: str = ""             # el trozo del texto que lo ha hecho saltar


class Zonas:
    """Barrios de València, sus vecinos y el nomenclátor. Se construye con los GeoJSON de `datos/ciudad`."""

    def __init__(self, datos: Path):
        self.datos = Path(datos)
        self.barrios: dict[str, dict] = {}
        geometrias, codigos = [], []
        for f in leer_geojson(self.datos, "barrios"):
            p = f.get("properties") or {}
            codigo = str(p.get("coddistbar") or "").strip()
            if not codigo:
                continue
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            c = g.representative_point()
            self.barrios[codigo] = {"codigo": codigo, "nombre": _bonito(p.get("nombre")), "distrito": str(p.get("coddistrit") or ""),
                                    "lat": round(c.y, 5), "lon": round(c.x, 5), "area_km2": None}
            geometrias.append(g)
            codigos.append(codigo)
        self._geom = dict(zip(codigos, geometrias))
        self._arbol = STRtree(geometrias) if geometrias else None
        self._codigos = codigos
        self.distritos = {str((f.get("properties") or {}).get("coddistrit")): _bonito((f.get("properties") or {}).get("nombre"))
                          for f in leer_geojson(self.datos, "distritos")}
        # Vecinos: barrios cuyos bordes se tocan (o casi: los polígonos del Ajuntament no siempre cierran del todo).
        self.vecinos: dict[str, set[str]] = {c: set() for c in codigos}
        if self._arbol is not None:
            for i, g in enumerate(geometrias):
                for j in self._arbol.query(g.buffer(0.0004)):
                    if j != i:
                        self.vecinos[codigos[i]].add(codigos[int(j)])
        self._calles: dict[str, list] | None = None
        self._indice_nombres: dict[str, tuple[str, str]] | None = None

    @property
    def hay(self) -> bool:
        return bool(self.barrios)

    @lru_cache(maxsize=200_000)
    def barrio_de(self, lat: float | None, lon: float | None) -> str | None:
        if self._arbol is None or lat is None or lon is None:
            return None
        p = Point(lon, lat)
        for i in self._arbol.query(p):
            if self._geom[self._codigos[int(i)]].contains(p):
                return self._codigos[int(i)]
        return None

    def nombre(self, codigo: str | None) -> str:
        return self.barrios.get(codigo or "", {}).get("nombre", "") if codigo else ""

    def geojson_barrios(self, precision: int = 5) -> dict:
        """Los barrios, para el visor: polígonos simplificados (unos 10 m) con código, nombre y distrito."""
        feats = []
        for codigo, g in self._geom.items():
            s = g.simplify(0.0001, preserve_topology=True)
            geo = json.loads(json.dumps(s.__geo_interface__), parse_float=lambda x: round(float(x), precision))
            b = self.barrios[codigo]
            feats.append({"type": "Feature", "geometry": geo, "properties": {"codigo": codigo, "nombre": b["nombre"], "distrito": b["distrito"],
                                                                              "distrito_nombre": self.distritos.get(b["distrito"], ""),
                                                                              "vecinos": sorted(self.vecinos.get(codigo, ()))}})
        return {"type": "FeatureCollection", "features": feats}

    # ------------------------------------------------------------ nomenclátor

    def _cargar_calles(self) -> None:
        """Calles agrupadas por nombre (una calle son muchos tramos) e índice de nombres buscables."""
        if self._calles is not None:
            return
        calles: dict[str, list] = {}
        nombres: dict[str, tuple[str, str]] = {}
        for f in leer_geojson(self.datos, "calles"):
            p = f.get("properties") or {}
            nombre = str(p.get("nomcalle") or "").strip()
            if not nombre or not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            clave = clave_nombre(nombre)
            if len(clave) < 3:
                continue
            calles.setdefault(clave, []).append((g, p))
            nombres.setdefault(clave, (f"{_bonito(p.get('tipcalle'))} {_bonito(nombre)}".strip(), "calle"))
        self._calles = calles
        self._indice_nombres = nombres

    def calle(self, nombre: str) -> list:
        self._cargar_calles()
        return self._calles.get(clave_nombre(nombre), []) if self._calles else []

    def centro_de_calle(self, nombre: str) -> tuple[float, float] | None:
        tramos = self.calle(nombre)
        if not tramos:
            return None
        lineas = [g for g, _ in tramos]
        punto = MultiLineString([ls for g in lineas for ls in (g.geoms if hasattr(g, "geoms") else [g])]).interpolate(0.5, normalized=True)
        return round(punto.y, 5), round(punto.x, 5)

    def direccion(self, nombre: str, numero: int | None) -> tuple[float, float] | None:
        """Una dirección con número: el tramo cuyo rango de portales lo contiene (izquierda o derecha)."""
        tramos = self.calle(nombre)
        if not tramos:
            return None
        if numero is not None:
            for g, p in tramos:
                for a, b in (("lf_add", "lt_add"), ("rf_add", "rt_add")):
                    x, y = p.get(a), p.get(b)
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)) and min(x, y) <= numero <= max(x, y) and (x % 2 == numero % 2 or y % 2 == numero % 2):
                        f = 0.5 if x == y else (numero - x) / (y - x)
                        punto = g.interpolate(max(0.0, min(1.0, f)), normalized=True)
                        return round(punto.y, 5), round(punto.x, 5)
        return self.centro_de_calle(nombre)

    def cruce(self, a: str, b: str, max_metros: float = 40.0) -> tuple[float, float] | None:
        """Donde se cruzan dos calles: el punto más cercano entre ellas, si están a menos de `max_metros`."""
        ta, tb = self.calle(a), self.calle(b)
        if not ta or not tb:
            return None
        ga = MultiLineString([ls for g, _ in ta for ls in (g.geoms if hasattr(g, "geoms") else [g])])
        gb = MultiLineString([ls for g, _ in tb for ls in (g.geoms if hasattr(g, "geoms") else [g])])
        if ga.distance(gb) * 111_000 > max_metros:
            return None
        from shapely.ops import nearest_points
        pa, pb = nearest_points(ga, gb)
        return round((pa.y + pb.y) / 2, 5), round((pa.x + pb.x) / 2, 5)

    def _lugares_fijos(self) -> dict[str, tuple[str, float, float, str]]:
        """Nombres de barrio, de estación de metro, de monumento y de lugares conocidos -> (nombre, lat, lon, tipo)."""
        if getattr(self, "_fijos", None) is not None:
            return self._fijos
        fijos: dict[str, tuple[str, float, float, str]] = {}
        for clave, (lat, lon) in LUGARES_CONOCIDOS.items():
            fijos[normalizar(clave)] = (clave.title(), lat, lon, "lugar")
        for capa, tipo in (("metro", "metro"), ("monumentos", "lugar"), ("recursos_turisticos", "lugar")):
            for f in leer_geojson(self.datos, capa):
                p, g = f.get("properties") or {}, f.get("geometry") or {}
                nombre = str(p.get("nombre") or "").strip()
                if not nombre or g.get("type") != "Point":
                    continue
                nombre = re.sub(r"^\d+\s*-\s*", "", nombre)
                clave = normalizar(nombre)
                if len(clave) >= 6:
                    fijos.setdefault(clave if tipo != "metro" else f"metro {clave}", (_bonito(nombre), g["coordinates"][1], g["coordinates"][0], tipo))
        for codigo, b in self.barrios.items():
            fijos[normalizar(b["nombre"])] = (b["nombre"], b["lat"], b["lon"], "barrio")
        self._fijos = fijos
        return fijos

    def buscar(self, texto: str, max_lugares: int = 5) -> list[Lugar]:
        """Los lugares de València que nombra un texto, del más preciso al menos."""
        if not texto:
            return []
        self._cargar_calles()
        # «C/ Colón» -> «calle colon»; el resto de barras, fuera.
        t = " " + re.sub(r"\s+", " ", re.sub(r"\bc\s*/\s*", "calle ", normalizar(texto)).replace("/", " ")) + " "
        hallados: list[Lugar] = []
        vistos: set[str] = set()
        # 1. Cruces y direcciones: «calle X con calle Y», «C/ X cruce C/ Y», «calle X, 23»
        patron_tipo = "|".join(re.escape(x) for x in sorted({normalizar(v) for v in TIPOS_VIA}, key=len, reverse=True))
        for m in re.finditer(rf" (?:{patron_tipo}) ((?:[a-z0-9]+ ){{1,6}})", t):
            fragmento = m.group(1).strip()
            mejor = self._mejor_calle(fragmento)
            if not mejor:
                continue
            clave_calle, usadas = mejor
            if clave_calle in vistos:
                continue
            despues = t[m.start(1) + len(" ".join(fragmento.split()[:usadas])):][:60]
            numero = re.match(r"\s*(?:n|num|numero)?\s*(\d{1,4})\b", despues)
            otra = re.match(rf"\s*(?:con|cruce|cruz|amb|esquina|y|i)\s+(?:(?:{patron_tipo})\s+)?((?:[a-z0-9]+ ){{1,6}})", despues + " ")
            punto, tipo, conf, nombre = None, "calle", 0.55, self._indice_nombres[clave_calle][0]
            if otra:
                mejor_b = self._mejor_calle(otra.group(1).strip())
                if mejor_b and mejor_b[0] != clave_calle:
                    punto = self.cruce(clave_calle, mejor_b[0])
                    if punto:
                        tipo, conf, nombre = "cruce", 0.9, f"{nombre} con {self._indice_nombres[mejor_b[0]][0]}"
            if punto is None and numero:
                punto = self.direccion(clave_calle, int(numero.group(1)))
                if punto:
                    tipo, conf, nombre = "direccion", 0.85, f"{nombre}, {numero.group(1)}"
            if punto is None:
                punto = self.centro_de_calle(clave_calle)
                # Una calle larga dice poco del sitio exacto: menos confianza cuanto más larga.
                largo = sum(g.length for g, _ in self.calle(clave_calle)) * 111
                conf = 0.6 if largo < 0.6 else 0.45 if largo < 2 else 0.3
            if punto:
                vistos.add(clave_calle)
                hallados.append(Lugar(nombre, tipo, punto[0], punto[1], self.barrio_de(punto[0], punto[1]), conf, m.group(0).strip()))
        # 2. Barrios, estaciones, monumentos y lugares conocidos, por su nombre completo.
        for clave, (nombre, lat, lon, tipo) in self._lugares_fijos().items():
            if len(clave) < 4 or f" {clave} " not in t:
                continue
            if tipo == "barrio" and clave in {normalizar(x) for x in BARRIOS_AMBIGUOS} and not re.search(rf" (?:barrio|barri|bo) (?:de |d )?{re.escape(clave)} ", t):
                continue
            if any(clave in normalizar(h.nombre) for h in hallados):
                continue
            conf = {"lugar": 0.75, "metro": 0.6, "barrio": 0.5}.get(tipo, 0.5)
            hallados.append(Lugar(nombre, tipo, lat, lon, self.barrio_de(lat, lon) if tipo != "barrio" else self._codigo_por_nombre(nombre), conf, clave))
        hallados.sort(key=lambda x: -x.confianza)
        return hallados[:max_lugares]

    def _codigo_por_nombre(self, nombre: str) -> str | None:
        n = normalizar(nombre)
        for codigo, b in self.barrios.items():
            if normalizar(b["nombre"]) == n:
                return codigo
        return None

    def _mejor_calle(self, fragmento: str) -> tuple[str, int] | None:
        """La calle cuyo nombre coincide con el principio más largo del fragmento: (clave, palabras usadas)."""
        palabras = fragmento.split()
        for n in range(min(6, len(palabras)), 0, -1):
            clave = clave_nombre(" ".join(palabras[:n]))
            if len(clave) >= 4 and clave in self._indice_nombres:
                return clave, n
        return None


def _bonito(texto) -> str:
    """«CANONGE TÀRREGA» -> «Canonge Tàrrega», respetando partículas en minúscula."""
    t = str(texto or "").strip()
    if not t or not t.isupper():
        return t
    palabras = t.lower().split()
    menores = {"de", "del", "la", "les", "els", "el", "i", "y", "d'", "l'", "dels", "al", "en", "na"}
    return " ".join(p if (i and p in menores) else p[:1].upper() + p[1:] for i, p in enumerate(palabras)).replace("L'", "l'").replace("D'", "d'")
