"""Fuente 2: OpenStreetMap, consultado con la API Overpass.

En OSM cada objeto lleva etiquetas clave=valor. Lo abandonado se marca de
varias formas, y hay que buscarlas todas:

- abandoned=yes / disused=yes / ruins=yes
- prefijos de "ciclo de vida": abandoned:building=factory, disused:railway=station,
  ruins:man_made=kiln...
- building=ruins, historic=ruins

OSM aporta lo que Catastro no tiene: nombre, tipo concreto (cuartel, estación,
sanatorio) y sitios que no son edificios (túneles, minas, despoblados).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import requests

from ..modelos import Candidato
from ..red import CacheJSON, pedir

log = logging.getLogger(__name__)

SERVIDORES = (
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# Código ISO 3166-2 de cada provincia (por código INE). OSM etiqueta con él
# los límites provinciales. En las comunidades de una sola provincia el límite
# puede llevar el código de la comunidad, así que se prueban los dos.
ISO_PROVINCIA: dict[str, tuple[str, ...]] = {
    "01": ("ES-VI",), "02": ("ES-AB",), "03": ("ES-A",), "04": ("ES-AL",), "05": ("ES-AV",),
    "06": ("ES-BA",), "07": ("ES-PM", "ES-IB"), "08": ("ES-B",), "09": ("ES-BU",), "10": ("ES-CC",),
    "11": ("ES-CA",), "12": ("ES-CS",), "13": ("ES-CR",), "14": ("ES-CO",), "15": ("ES-C",),
    "16": ("ES-CU",), "17": ("ES-GI",), "18": ("ES-GR",), "19": ("ES-GU",), "20": ("ES-SS",),
    "21": ("ES-H",), "22": ("ES-HU",), "23": ("ES-J",), "24": ("ES-LE",), "25": ("ES-L",),
    "26": ("ES-LO", "ES-RI"), "27": ("ES-LU",), "28": ("ES-M", "ES-MD"), "29": ("ES-MA",),
    "30": ("ES-MU", "ES-MC"), "31": ("ES-NA", "ES-NC"), "32": ("ES-OR",), "33": ("ES-O", "ES-AS"),
    "34": ("ES-P",), "35": ("ES-GC",), "36": ("ES-PO",), "37": ("ES-SA",), "38": ("ES-TF",),
    "39": ("ES-S", "ES-CB"), "40": ("ES-SG",), "41": ("ES-SE",), "42": ("ES-SO",), "43": ("ES-T",),
    "44": ("ES-TE",), "45": ("ES-TO",), "46": ("ES-V",), "47": ("ES-VA",), "48": ("ES-BI",),
    "49": ("ES-ZA",), "50": ("ES-Z",), "51": ("ES-CE",), "52": ("ES-ML",),
}

_RE_CICLO = re.compile(r"^(abandoned|disused|ruins):(.+)$")
_NO = {"no", "false", "0"}

# Claves que describen QUÉ es un objeto.
_CLAVES_TIPO = ("place", "military", "railway", "man_made", "industrial", "power", "landuse",
                "amenity", "healthcare", "tourism", "leisure", "historic", "building", "craft",
                "aeroway", "shop", "highway", "barrier", "natural", "waterway")

# Tipos que no interesan aunque estén marcados como abandonados.
_DESCARTE_CLAVE = {"highway", "barrier", "natural", "waterway", "shop"}
_DESCARTE_VALOR = {
    "power": {"line", "minor_line", "pole", "tower", "cable", "portal"},
    "man_made": {"pipeline", "pole", "mast", "surveillance", "cutline", "embankment", "dyke",
                 "flagpole", "street_cabinet"},
    "landuse": {"farmland", "orchard", "vineyard", "meadow", "forest", "grass", "allotments",
                "farmyard", "residential", "construction", "greenfield", "basin", "reservoir"},
    "railway": {"rail", "abandoned", "disused", "tram", "narrow_gauge", "level_crossing",
                "signal", "switch", "buffer_stop", "crossing", "platform", "siding"},
    "historic": {"archaeological_site", "memorial", "wayside_cross", "wayside_shrine",
                 "boundary_stone", "milestone"},
    "leisure": {"pitch", "playground", "park", "garden", "picnic_table"},
    "tourism": {"information", "viewpoint", "picnic_site", "artwork", "attraction", "museum", "yes"},
}
# De amenity solo se conservan los que suelen ser edificios con entidad.
_AMENITY_INTERES = {
    "hospital", "clinic", "school", "college", "university", "kindergarten", "prison", "cinema",
    "theatre", "nightclub", "casino", "place_of_worship", "monastery", "fuel", "police",
    "fire_station", "bus_station", "community_centre", "social_facility", "nursing_home",
    "swimming_pool", "public_bath", "courthouse", "townhall", "marketplace", "events_venue",
    "conference_centre", "research_institute", "crematorium",
}

# Reglas de categoría, en orden de prioridad: (categoría, clave, valores o None=cualquiera).
_REGLAS: tuple[tuple[str, str, set[str] | None], ...] = (
    ("despoblado", "place", None),
    ("militar", "military", None),
    ("militar", "building", {"bunker", "barracks", "military"}),
    ("militar", "historic", {"fort", "bunker", "battlefield"}),
    ("ferroviario", "railway", None),
    ("ferroviario", "building", {"train_station"}),
    # Una torre o un castillo catalogados como históricos son patrimonio, aunque
    # OSM los describa además como man_made=tower.
    ("patrimonio", "historic", {"tower", "castle", "city_gate", "citywalls", "manor", "palace", "building",
                                "aqueduct", "bridge", "tomb", "house", "farm", "ice_house", "yes"}),
    ("mineria", "man_made", {"mineshaft", "adit", "mine"}),
    ("mineria", "landuse", {"quarry"}),
    ("mineria", "historic", {"mine", "mine_shaft"}),
    ("mineria", "industrial", {"mine"}),
    ("industrial", "man_made", {"works", "chimney", "kiln", "silo", "water_tower", "tower",
                                "storage_tank", "gasometer", "lighthouse", "watermill", "windmill",
                                "wastewater_plant", "water_works", "crane", "bridge"}),
    ("industrial", "industrial", None),
    ("industrial", "power", None),
    ("industrial", "craft", None),
    ("industrial", "landuse", {"industrial", "brownfield", "landfill", "railway", "commercial"}),
    ("industrial", "building", {"industrial", "warehouse", "factory", "manufacture", "hangar"}),
    ("industrial", "aeroway", None),
    ("sanitario", "amenity", {"hospital", "clinic", "nursing_home", "social_facility"}),
    ("sanitario", "healthcare", None),
    ("sanitario", "building", {"hospital"}),
    ("educativo", "amenity", {"school", "college", "university", "kindergarten", "research_institute"}),
    ("educativo", "building", {"school", "university", "college"}),
    ("religioso", "amenity", {"place_of_worship", "monastery"}),
    ("religioso", "building", {"church", "chapel", "monastery", "convent", "cathedral", "religious"}),
    ("religioso", "historic", {"monastery", "church"}),
    ("ocio_hosteleria", "tourism", None),
    ("ocio_hosteleria", "leisure", None),
    ("ocio_hosteleria", "amenity", {"cinema", "theatre", "nightclub", "casino", "swimming_pool",
                                    "public_bath", "events_venue", "conference_centre"}),
    ("ocio_hosteleria", "building", {"hotel"}),
    ("equipamiento", "amenity", None),
    ("patrimonio", "historic", None),
    ("agrario", "building", {"farm_auxiliary", "barn", "cowshed", "stable", "sty", "greenhouse",
                             "shed", "hut", "slurry_tank"}),
    ("residencial", "building", {"residential", "house", "apartments", "farm", "detached",
                                 "semidetached_house", "terrace", "cabin", "bungalow", "dormitory"}),
)

_ETIQUETAS_UTILES = ("name", "old_name", "description", "note", "start_date", "end_date",
                     "operator", "website", "image", "wikimedia_commons", "heritage", "access")


def zona_overpass(
    *, provincia: str | None = None, caja: tuple[float, float, float, float] | None = None
) -> tuple[str, str]:
    """Trozos de consulta que delimitan la zona: (cabecera, filtro).

    Una caja se escribe como filtro "(sur,oeste,norte,este)". Una provincia
    necesita una cabecera que busque su límite administrativo y un filtro que
    lo use.
    """
    if caja:
        oeste, sur, este, norte = caja
        return "", f"({sur:.6f},{oeste:.6f},{norte:.6f},{este:.6f})"   # Overpass usa sur,oeste,norte,este
    if provincia:
        if provincia not in ISO_PROVINCIA:
            raise ValueError(f"Provincia desconocida: {provincia}")
        codigos = "|".join(ISO_PROVINCIA[provincia])
        return f'area["ISO3166-2"~"^({codigos})$"]["boundary"="administrative"]->.zona;\n', "(area.zona)"
    raise ValueError("Hace falta una provincia o una caja")


def construir_consulta(
    *,
    provincia: str | None = None,
    caja: tuple[float, float, float, float] | None = None,
    timeout: int = 900,
) -> str:
    """Escribe la consulta en Overpass QL para una provincia o una caja."""
    cabecera, zona = zona_overpass(provincia=provincia, caja=caja)

    filtros = (
        'nwr["abandoned"]["abandoned"!="no"]',
        'nwr["disused"]["disused"!="no"]',
        'nwr["ruins"]["ruins"!="no"]',
        'nwr[~"^(abandoned|disused|ruins):"~"."]',
        'nwr["building"="ruins"]',
        'nwr["historic"="ruins"]',
        'way["railway"~"^(abandoned|disused)$"]["tunnel"]',
        'way["railway"~"^(abandoned|disused)$"]["bridge"]',
    )
    cuerpo = "\n".join(f"  {f}{zona};" for f in filtros)
    # "out center" devuelve un punto central para vías y relaciones, sin toda su geometría.
    return f"[out:json][timeout:{timeout}][maxsize:1073741824];\n{cabecera}(\n{cuerpo}\n);\nout tags center qt;\n"


def _afirmativo(tags: dict[str, str], clave: str) -> bool:
    """True si la etiqueta existe y no vale "no"."""
    valor = tags.get(clave)
    return valor is not None and valor.lower() not in _NO


def clasificar(tags: dict[str, str]) -> tuple[str, str] | None:
    """Decide categoría y estado a partir de las etiquetas. None = no interesa."""
    # Tipos del objeto: los normales y los que llevan prefijo de ciclo de vida.
    tipos: dict[str, str] = {}
    prefijos: set[str] = set()
    for clave, valor in tags.items():
        m = _RE_CICLO.match(clave)
        if m and m.group(2) in _CLAVES_TIPO:
            prefijos.add(m.group(1))
            tipos.setdefault(m.group(2), valor)
    for clave in _CLAVES_TIPO:
        if clave in tags:
            tipos.setdefault(clave, tags[clave])

    # Estado: gana el más deteriorado.
    es_ruina = ("ruins" in prefijos or _afirmativo(tags, "ruins")
                or tags.get("building") == "ruins" or tags.get("historic") == "ruins")
    es_abandonado = ("abandoned" in prefijos or _afirmativo(tags, "abandoned")
                     or tags.get("railway") == "abandoned")
    es_desuso = ("disused" in prefijos or _afirmativo(tags, "disused")
                 or tags.get("railway") == "disused")
    if not (es_ruina or es_abandonado or es_desuso):
        return None
    estado = "ruina" if es_ruina else "abandonado" if es_abandonado else "en_desuso"

    # Túneles y puentes de vías muertas sí interesan, aunque la vía en sí no.
    es_via_muerta = (tags.get("railway") in ("abandoned", "disused")
                     or "abandoned:railway" in tags or "disused:railway" in tags)
    if es_via_muerta and (_afirmativo(tags, "tunnel") or _afirmativo(tags, "bridge")):
        # Si hoy es un camino o una vía verde, ya no está abandonado.
        return None if "highway" in tags else ("ferroviario", estado)

    # Se quitan los tipos sin interés. Los genéricos (building=yes, historic=ruins)
    # no descartan el objeto, pero tampoco sirven para decidir la categoría.
    utiles: dict[str, str] = {}
    hay_generico = False
    for clave, valor in tipos.items():
        if clave in ("building", "historic") and valor in ("ruins", "yes"):
            hay_generico = True
        elif clave in _DESCARTE_CLAVE or valor in _DESCARTE_VALOR.get(clave, ()):
            continue
        elif clave == "amenity" and valor not in _AMENITY_INTERES:
            continue
        else:
            utiles[clave] = valor
    # Un camino o un muro descartan el objeto; una etiqueta neutra (tourism=attraction) no.
    hay_descartado = any(clave in _DESCARTE_CLAVE for clave in tipos)
    if tipos and not utiles and (hay_descartado or not hay_generico):
        return None   # solo era un camino, un comercio cerrado, un resto de muralla...

    for categoria, clave, valores in _REGLAS:
        if clave in utiles and (valores is None or utiles[clave] in valores):
            return categoria, estado
    if tags.get("historic") == "ruins":
        return "patrimonio", estado
    return "otro", estado


# Valores de building=* que describen un sitio concreto. Los demás (yes, house,
# industrial, warehouse, barn...) son los que usa la importación de Catastro.
_EDIFICIO_CONCRETO = {
    "train_station", "church", "chapel", "monastery", "convent", "cathedral", "religious", "mosque",
    "synagogue", "hospital", "school", "university", "college", "hotel", "bunker", "barracks",
    "military", "factory", "manufacture", "hangar", "stadium", "prison", "castle", "tower",
}


def solo_edificio(tags: dict[str, str]) -> bool:
    """True si lo único que se sabe del objeto es que es un edificio.

    Muchos municipios tienen el Catastro importado a OSM: cada edificio ruinoso
    aparece como abandoned:building=... sin nombre ni más datos. Eso es un eco
    de Catastro, no una segunda fuente.
    """
    for clave in tags:
        m = _RE_CICLO.match(clave)
        base = m.group(2) if m else clave
        if base not in _CLAVES_TIPO:
            continue
        if base != "building" or tags[clave] in _EDIFICIO_CONCRETO:
            return False
    return True


def _nombre(tags: dict[str, str]) -> str | None:
    for clave in ("name", "name:es", "name:ca", "old_name", "abandoned:name", "disused:name",
                  "was:name", "alt_name", "loc_name", "official_name"):
        if tags.get(clave):
            return tags[clave]
    return None


def parsear(respuesta: dict) -> list[Candidato]:
    """Convierte la respuesta JSON de Overpass en candidatos."""
    candidatos: list[Candidato] = []
    for el in respuesta.get("elements", []):
        tags = el.get("tags") or {}
        centro = el if el.get("type") == "node" else el.get("center") or {}
        lat, lon = centro.get("lat"), centro.get("lon")
        if lat is None or lon is None:
            continue
        clasif = clasificar(tags)
        if clasif is None:
            continue
        categoria, estado = clasif
        nombre = _nombre(tags)
        generico = solo_edificio(tags)
        etiquetas = {k: v for k, v in tags.items()
                     if k in _ETIQUETAS_UTILES or k in _CLAVES_TIPO or _RE_CICLO.match(k)}
        candidatos.append(Candidato(
            id=f"osm-{el['type']}-{el['id']}",
            lat=round(float(lat), 6),
            lon=round(float(lon), 6),
            nombre=nombre,
            categoria=categoria,
            estado=estado,
            fuentes=["osm"],
            debil=generico and nombre is None and "wikidata" not in tags,
            tipo_confirmado=not generico and categoria != "otro",
            osm_ids=[f"{el['type']}/{el['id']}"],
            wikidata=tags.get("wikidata"),
            wikipedia=tags.get("wikipedia"),
            etiquetas=etiquetas,
        ))
    return candidatos


def buscar(
    sesion: requests.Session,
    carpeta_cache: Path,
    *,
    provincia: str | None = None,
    caja: tuple[float, float, float, float] | None = None,
    usar_cache: bool = True,
) -> list[Candidato]:
    """Lanza la consulta (probando varios servidores) y devuelve candidatos."""
    consulta = construir_consulta(provincia=provincia, caja=caja)
    cache = CacheJSON(carpeta_cache, usar_cache)
    datos = cache.leer(consulta)
    if datos is None:
        ultimo: Exception | None = None
        for servidor in SERVIDORES:
            try:
                resp = pedir(sesion, "POST", servidor, data={"data": consulta},
                             timeout=960, reintentos=2, espera=20)
                datos = resp.json()
                break
            except Exception as exc:  # noqa: BLE001 - se prueba el siguiente servidor
                ultimo = exc
                log.warning("Overpass %s falló: %s", servidor, exc)
        if datos is None:
            raise RuntimeError(f"Ningún servidor Overpass respondió: {ultimo}")
        # Overpass puede devolver 200 con un aviso de error dentro (p. ej. sin memoria).
        if datos.get("remark"):
            log.warning("Aviso de Overpass: %s", datos["remark"])
        else:
            cache.guardar(consulta, datos)
    return parsear(datos)
