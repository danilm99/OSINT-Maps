"""Fuente 1: Catastro (servicio INSPIRE de edificios).

Catastro publica, por municipio, un ZIP con todos los edificios en formato GML
(un XML geográfico). Cada edificio lleva su contorno y, entre otros datos:

- conditionOfConstruction: "functional" (en uso), "declined" (deficiente) o
  "ruin" (ruinoso). Este campo es la base del buscador.
- currentUse: uso principal (residencial, industrial, agrario...).
- fecha de construcción y superficie construida.

Flujo: listar municipios de una provincia -> descargar cada ZIP -> leer el GML
-> quedarse con ruinosos y deficientes -> agrupar los que están pegados (una
fábrica o una aldea abandonada son muchos edificios) -> crear candidatos.

No cubre País Vasco ni Navarra, que tienen catastro propio.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon
from shapely.strtree import STRtree

from ..modelos import Candidato
from ..red import descargar, pedir

log = logging.getLogger(__name__)

BASE = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/"
URL_PROVINCIA = BASE + "{prov}/ES.SDGC.bu.atom_{prov}.xml"

ESTADOS = {"ruin": "ruina", "declined": "deficiente"}

USOS = {
    "1_residential": "residencial",
    "2_agriculture": "agrario",
    "3_industrial": "industrial",
    "4_1_office": "oficinas",
    "4_2_retail": "comercial",
    "4_3_publicServices": "equipamiento",
}

# Un "&" suelto (que no forma parte de &amp; &lt; etc.) rompe el XML. Catastro
# los deja a veces en los nombres, así que los arreglamos al vuelo.
_RE_AMP = re.compile(rb"&(?!(?:amp|lt|gt|quot|apos|#\d{1,7}|#x[0-9a-fA-F]{1,6});)")
_RE_ENTRADA = re.compile(r"<entry\b.*?</entry>", re.S | re.I)
_RE_ZIP = re.compile(r"(https?://[^\"<>]+?/A\.ES\.SDGC\.BU\.(\d{5})\.zip)", re.I)
_RE_POLIGONO = re.compile(r"<georss:polygon>([^<]+)</georss:polygon>", re.I)
_RE_TITULO = re.compile(r"<title>\s*\d{5}-(.*?)\s+buildings\s*</title>", re.I | re.S)
_RE_EPSG = re.compile(r"(\d{4,5})\s*$")


@dataclass
class Municipio:
    codigo: str                 # código de Catastro (5 cifras), NO es el del INE
    nombre: str
    url: str                    # dirección del ZIP de edificios
    caja: tuple[float, float, float, float] | None = None  # oeste, sur, este, norte


@dataclass
class Edificio:
    refcat: str
    estado: str                 # "ruina" o "deficiente"
    uso: str | None
    anio: int | None
    sup_construida: float | None
    geom: Polygon | MultiPolygon  # en metros (coordenadas UTM del municipio)


# --------------------------------------------------------------------------
# Listado de municipios
# --------------------------------------------------------------------------

def parsear_feed(texto: str) -> list[Municipio]:
    """Extrae los municipios del índice (feed ATOM) de una provincia."""
    municipios: dict[str, Municipio] = {}
    for entrada in _RE_ENTRADA.findall(texto):
        m = _RE_ZIP.search(entrada)
        if not m:
            continue
        # Algunas URL traen varios espacios seguidos por los acentos; se normalizan.
        url = re.sub(r" +", " ", html.unescape(m.group(1)))
        codigo = m.group(2)
        nombre = None
        carpeta = url.rsplit("/", 2)[-2]            # p. ej. "46900-VALENCIA"
        if carpeta.startswith(codigo + "-"):
            nombre = carpeta[len(codigo) + 1:]
        if not nombre:
            t = _RE_TITULO.search(entrada)
            nombre = html.unescape(t.group(1)) if t else codigo
        caja = None
        p = _RE_POLIGONO.search(entrada)
        if p:
            try:
                nums = [float(x) for x in p.group(1).split()]
                lats, lons = nums[0::2], nums[1::2]   # el feed da pares "lat lon"
                caja = (min(lons), min(lats), max(lons), max(lats))
            except ValueError:
                caja = None
        municipios[codigo] = Municipio(codigo, nombre.strip().title(), url, caja)
    return sorted(municipios.values(), key=lambda mu: mu.codigo)


def listar_municipios(sesion: requests.Session, provincia: str) -> list[Municipio]:
    """Descarga el índice de una provincia (código de 2 cifras, p. ej. "46")."""
    if not re.fullmatch(r"\d{2}", provincia):
        raise ValueError("El código de provincia son 2 cifras, p. ej. 46 para Valencia")
    resp = pedir(sesion, "GET", URL_PROVINCIA.format(prov=provincia))
    # El índice no siempre declara bien su codificación: probamos UTF-8 y, si no, Latin-1.
    try:
        texto = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        texto = resp.content.decode("iso-8859-1")
    municipios = parsear_feed(texto)
    if not municipios:
        raise RuntimeError(
            f"El índice de Catastro para la provincia {provincia} no contiene municipios. "
            "Puede que el código no exista o que el formato del servicio haya cambiado."
        )
    return municipios


# --------------------------------------------------------------------------
# Lectura del GML
# --------------------------------------------------------------------------

class _FlujoSaneado:
    """Envuelve un fichero y arregla los "&" sueltos mientras se va leyendo.

    Así no hay que cargar el GML entero en memoria (el de una capital ocupa
    cientos de MB).
    """

    def __init__(self, fh) -> None:
        self._fh = fh
        self._resto = b""

    def read(self, n: int = -1) -> bytes:
        tam = n if n and n > 0 else 1 << 16
        while True:
            trozo = self._fh.read(tam)
            datos = self._resto + trozo
            if not trozo:                       # fin de fichero
                self._resto = b""
                return _RE_AMP.sub(b"&amp;", datos)
            # Si hay un "&" cerca del final, puede ser una entidad partida entre
            # dos trozos: se deja para la siguiente lectura.
            corte = datos.rfind(b"&", max(0, len(datos) - 12))
            if corte != -1:
                self._resto, datos = datos[corte:], datos[:corte]
            else:
                self._resto = b""
            if datos:
                return _RE_AMP.sub(b"&amp;", datos)


def _local(etiqueta: str) -> str:
    """Nombre de una etiqueta XML sin el prefijo de espacio de nombres."""
    return etiqueta.rsplit("}", 1)[-1]


def _epsg(srs: str | None) -> int | None:
    m = _RE_EPSG.search(srs or "")
    return int(m.group(1)) if m else None


def _anillo(elem) -> np.ndarray | None:
    for e in elem.iter():
        if _local(e.tag) == "posList" and e.text:
            dim = int(e.get("srsDimension") or 2)
            coords = np.array(e.text.split(), dtype=float)
            if coords.size < 3 * dim or coords.size % dim:
                return None
            return coords.reshape(-1, dim)[:, :2]
    return None


def _geometria(edificio) -> Polygon | MultiPolygon | None:
    """Construye el polígono de un edificio a partir de sus anillos GML."""
    poligonos = []
    for e in edificio.iter():
        if _local(e.tag) not in ("PolygonPatch", "Polygon"):
            continue
        exterior, huecos = None, []
        for hijo in e:
            nombre = _local(hijo.tag)
            if nombre == "exterior":
                exterior = _anillo(hijo)
            elif nombre == "interior":
                hueco = _anillo(hijo)
                if hueco is not None:
                    huecos.append(hueco)
        if exterior is None:
            continue
        pol = Polygon(exterior, huecos)
        if not pol.is_valid:
            pol = shapely.make_valid(pol)
        if not pol.is_empty and pol.area > 0:
            poligonos.append(pol)
    if not poligonos:
        return None
    geom = poligonos[0] if len(poligonos) == 1 else shapely.union_all(poligonos)
    # make_valid puede devolver colecciones mixtas: nos quedamos con la parte poligonal.
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        partes = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
        if not partes:
            return None
        geom = shapely.union_all(partes)
    return geom


def leer_gml(fh) -> tuple[list[Edificio], np.ndarray, int | None]:
    """Lee un GML de edificios.

    Devuelve:
    - los edificios ruinosos o deficientes, con su contorno;
    - el centro (x, y) de cada edificio en uso, para medir luego el aislamiento;
    - el código EPSG del sistema de coordenadas del fichero.
    """
    deteriorados: list[Edificio] = []
    en_uso: list[tuple[float, float]] = []
    epsg: int | None = None

    # iterparse va entregando elementos según se cierran, sin cargar todo el árbol.
    for _, elem in ET.iterparse(_FlujoSaneado(fh), events=("end",)):
        nombre = _local(elem.tag)
        if nombre in ("featureMember", "member"):
            elem.clear()
            continue
        if nombre != "Building":
            continue

        estado = uso = refcat = fecha = area = None
        esquina_inf = esquina_sup = None
        for e in elem.iter():
            n = _local(e.tag)
            texto = (e.text or "").strip()
            if n == "conditionOfConstruction":
                estado = texto
            elif n == "currentUse":
                uso = texto or None
            elif n == "localId" and refcat is None:
                refcat = texto
            elif n == "beginning" and fecha is None:
                fecha = texto
            elif n == "value" and area is None:
                area = texto
            elif n == "lowerCorner" and esquina_inf is None:
                esquina_inf = texto
            elif n == "upperCorner" and esquina_sup is None:
                esquina_sup = texto
            elif epsg is None and n in ("Envelope", "Surface", "Polygon", "MultiSurface"):
                epsg = _epsg(e.get("srsName"))

        if estado in ESTADOS:
            geom = _geometria(elem)
            if geom is not None and refcat:
                deteriorados.append(Edificio(
                    refcat=refcat,
                    estado=ESTADOS[estado],
                    uso=USOS.get(uso or ""),
                    anio=_anio(fecha),
                    sup_construida=_numero(area),
                    geom=geom,
                ))
        elif esquina_inf and esquina_sup:
            try:
                x0, y0 = (float(v) for v in esquina_inf.split()[:2])
                x1, y1 = (float(v) for v in esquina_sup.split()[:2])
                en_uso.append(((x0 + x1) / 2, (y0 + y1) / 2))
            except ValueError:
                pass
        elem.clear()

    return deteriorados, np.array(en_uso, dtype=float).reshape(-1, 2), epsg


def _anio(fecha: str | None) -> int | None:
    try:
        anio = int((fecha or "")[:4])
    except ValueError:
        return None
    # Catastro usa años absurdos (0001, 1000...) cuando no conoce la fecha.
    return anio if 1200 <= anio <= 2100 else None


def _numero(texto: str | None) -> float | None:
    try:
        return float(texto) if texto else None
    except ValueError:
        return None


def leer_zip(ruta: Path) -> tuple[list[Edificio], np.ndarray, int | None]:
    """Abre el ZIP de un municipio y lee su fichero de edificios."""
    with zipfile.ZipFile(ruta) as zf:
        nombres = [n for n in zf.namelist() if n.lower().endswith(".building.gml")]
        if not nombres:
            raise RuntimeError(f"{ruta.name} no contiene un fichero .building.gml")
        with zf.open(nombres[0]) as fh:
            return leer_gml(fh)


# --------------------------------------------------------------------------
# Agrupación en conjuntos y creación de candidatos
# --------------------------------------------------------------------------

def _grupos(geoms: list, distancia: float, max_extension: float = 500.0) -> list[list[int]]:
    """Agrupa geometrías que están a menos de `distancia` metros entre sí.

    Usa "union-find": cada edificio empieza siendo su propio grupo y cada par
    de vecinos fusiona sus dos grupos. Un grupo que se extiende demasiado (un
    casco antiguo entero encadenado casa a casa) se trocea en una rejilla para
    que su centro siga significando algo.
    """
    padre = list(range(len(geoms)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    arbol = STRtree(geoms)   # índice espacial: evita comparar todos con todos
    a, b = arbol.query(geoms, predicate="dwithin", distance=distancia)
    for i, j in zip(a.tolist(), b.tolist()):
        ri, rj = raiz(i), raiz(j)
        if ri != rj:
            padre[ri] = rj

    por_raiz: dict[int, list[int]] = defaultdict(list)
    for i in range(len(geoms)):
        por_raiz[raiz(i)].append(i)

    salida: list[list[int]] = []
    for miembros in por_raiz.values():
        cajas = np.array([geoms[i].bounds for i in miembros])
        ancho = cajas[:, 2].max() - cajas[:, 0].min()
        alto = cajas[:, 3].max() - cajas[:, 1].min()
        if max(ancho, alto) <= max_extension:
            salida.append(miembros)
            continue
        celdas: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i in miembros:
            c = geoms[i].centroid
            celdas[(int(c.x // max_extension), int(c.y // max_extension))].append(i)
        salida.extend(celdas.values())
    return salida


def crear_candidatos(
    edificios: list[Edificio],
    en_uso: np.ndarray,
    epsg: int,
    municipio: str | None = None,
    *,
    dist_agrupar: float = 25.0,
    min_superficie: float = 150.0,
    radio_vecinos: float = 150.0,
    proporcion_minima: float = 0.5,
) -> list[Candidato]:
    """Convierte los edificios deteriorados de un municipio en candidatos.

    Un grupo de edificios deteriorados solo se trata como "conjunto" si es
    mayoría en su entorno (al menos la mitad de los edificios a 150 m). En el
    casco de un pueblo habitado hay decenas de casas en mal estado encadenadas
    entre otras en uso: eso no es un sitio abandonado. Ahí el grupo se deshace
    y solo sobreviven los edificios que son grandes por sí mismos.
    """
    if not edificios:
        return []
    geoms = [e.geom for e in edificios]
    areas = np.array([g.area for g in geoms])
    a_wgs84 = Transformer.from_crs(epsg, 4326, always_xy=True)
    arbol_uso = STRtree(shapely.points(en_uso)) if len(en_uso) else None

    def contar_vecinos(geom) -> int:
        if arbol_uso is None:
            return 0
        return int(len(arbol_uso.query(geom, predicate="dwithin", distance=radio_vecinos)))

    grupos: list[list[int]] = []
    for miembros in _grupos(geoms, dist_agrupar):
        if len(miembros) > 1:
            vecinos = contar_vecinos(shapely.union_all([geoms[i] for i in miembros]))
            if len(miembros) / (len(miembros) + vecinos) < proporcion_minima:
                # Entorno habitado: se quedan los edificios grandes, juntando solo los que se tocan.
                grandes = [i for i in miembros if areas[i] >= min_superficie]
                if grandes:
                    grupos += [[grandes[j] for j in g] for g in _grupos([geoms[i] for i in grandes], 2.0)]
                continue
        grupos.append(miembros)

    candidatos: list[Candidato] = []
    for miembros in grupos:
        total = float(areas[miembros].sum())
        if total < min_superficie:
            continue
        miembros = sorted(miembros, key=lambda i: -areas[i])
        conjunto = shapely.union_all([geoms[i] for i in miembros])

        # Estado y uso dominantes, ponderados por superficie.
        peso_estado: dict[str, float] = defaultdict(float)
        peso_uso: dict[str, float] = defaultdict(float)
        for i in miembros:
            peso_estado[edificios[i].estado] += areas[i]
            if edificios[i].uso:
                peso_uso[edificios[i].uso] += areas[i]
        estado = "ruina" if peso_estado["ruina"] >= total / 2 else "deficiente"
        categoria = max(peso_uso, key=peso_uso.get) if peso_uso else "otro"

        anios = [edificios[i].anio for i in miembros if edificios[i].anio]
        construida = [edificios[i].sup_construida for i in miembros if edificios[i].sup_construida]

        vecinos = contar_vecinos(conjunto)

        # Contorno para el mapa: simplificado, y si son muchos edificios, su envolvente.
        forma = conjunto.convex_hull if len(miembros) > 40 else conjunto.simplify(0.5)
        huella = shapely.transform(forma, lambda c: np.column_stack(a_wgs84.transform(c[:, 0], c[:, 1])))
        centro = conjunto.centroid
        if len(miembros) == 1 and not centro.within(conjunto):
            centro = conjunto.representative_point()   # edificio en U: el centroide cae fuera
        lon, lat = a_wgs84.transform(centro.x, centro.y)

        candidatos.append(Candidato(
            id=f"cat-{edificios[miembros[0]].refcat}",
            lat=round(lat, 6),
            lon=round(lon, 6),
            categoria=categoria,
            estado=estado,
            fuentes=["catastro"],
            superficie_m2=total,
            superficie_construida_m2=float(sum(construida)) if construida else None,
            mayor_edificio_m2=float(areas[miembros[0]]),
            n_edificios=len(miembros),
            anio=min(anios) if anios else None,
            vecinos_150m=vecinos,
            municipio=municipio,
            refcats=[edificios[i].refcat for i in miembros[:25]],
            huella=huella,
        ))
    return candidatos


# --------------------------------------------------------------------------
# Punto de entrada de la fuente
# --------------------------------------------------------------------------

def _cajas_se_tocan(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def buscar(
    sesion: requests.Session,
    municipios: list[Municipio],
    carpeta_cache: Path,
    *,
    min_superficie: float = 150.0,
    dist_agrupar: float = 25.0,
    caja: tuple[float, float, float, float] | None = None,
    aviso: Callable[[str], None] | None = None,
    procesados: list[Municipio] | None = None,
) -> Iterator[Candidato]:
    """Descarga y procesa cada municipio. Un fallo en uno no detiene el resto.

    Si se pasa la lista `procesados`, se le añaden los municipios leídos sin
    error: sirve para saber qué zona cubre realmente Catastro en esta ejecución.
    """
    total = len(municipios)
    for n, mun in enumerate(municipios, 1):
        if caja and mun.caja and not _cajas_se_tocan(caja, mun.caja):
            continue
        try:
            ruta = descargar(sesion, mun.url, carpeta_cache / f"{mun.codigo}.zip")
            edificios, en_uso, epsg = leer_zip(ruta)
            if epsg is None:
                raise RuntimeError("no se pudo determinar el sistema de coordenadas")
            encontrados = crear_candidatos(
                edificios, en_uso, epsg, mun.nombre,
                dist_agrupar=dist_agrupar, min_superficie=min_superficie,
            )
        except zipfile.BadZipFile:
            log.error("[%s %s] ZIP corrupto; bórralo de la caché y repite", mun.codigo, mun.nombre)
            continue
        except Exception as exc:  # noqa: BLE001 - queremos seguir con el resto
            log.error("[%s %s] no se pudo procesar: %s", mun.codigo, mun.nombre, exc)
            continue
        if procesados is not None:
            procesados.append(mun)
        if caja:
            encontrados = [c for c in encontrados
                           if caja[0] <= c.lon <= caja[2] and caja[1] <= c.lat <= caja[3]]
        if aviso:
            aviso(f"[{n}/{total}] {mun.nombre}: {len(edificios)} edificios deteriorados "
                  f"-> {len(encontrados)} candidatos")
        yield from encontrados
