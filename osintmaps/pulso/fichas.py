"""Las fichas: lo que se sabe de un barrio o de un inmueble por las capas públicas, que no cambian
cada minuto (contexto.py las baja a `datos/ciudad/`).

- De un **barrio**: su índice de vulnerabilidad (equipamientos, demografía, economía), las quejas y
  sugerencias que se han hecho sobre él el último año, por tema, y los accidentes de tráfico.
- De un **punto** (un inmueble): la calle y el número más cercanos, si es patrimonio catalogado,
  si está en el registro municipal de edificios o solares a rehabilitar, si es vivienda protegida,
  si está en una zona acústicamente saturada, los monumentos de al lado, los accidentes de esa
  esquina y, preguntando al Catastro, la referencia catastral, el uso, la superficie y el año de
  construcción. Todo son datos de inmuebles y de calles: el Catastro no da titulares por esta vía.

Los accidentes vienen con la dirección escrita («C/ X cruce C/ Y», «AV NARANJOS 14»): se sitúan una
vez con el nomenclátor y se guardan situados, para no repetirlo cada vez.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import requests
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .contexto import CARPETA, leer_csv, leer_geojson

log = logging.getLogger("osintmaps.pulso")

CATASTRO_RC = "https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_RCCOOR"
CATASTRO_DATOS = "https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCallejero.svc/json/Consulta_DNPRC"
CATASTRO_FICHA = "https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCListaBienes.aspx?rc1={a}&rc2={b}"
FICHERO_ACCIDENTES = "accidentes_situados.json"
GRAVEDAD = {"SIN HERIDOS": 0, "CON HERIDOS LEVES": 1, "CON HERIDOS BAJA GRAVEDAD": 2, "CON HERIDOS GRAVES": 3, "CON FALLECIDOS": 4}
METRO = 1 / 111_000             # grados por metro (latitud; en longitud, aquí, son 1/86.000: se usa el mayor)


def _codigo_barrio(valor) -> str | None:
    """«21», 21 o «021» -> «021», como en la capa de barrios."""
    s = str(valor or "").strip()
    return s.zfill(3) if s.isdigit() else None


class _Capa:
    """Polígonos o puntos de una capa con su índice espacial."""

    def __init__(self, elementos: list[dict]):
        self.props, geoms = [], []
        for f in elementos:
            try:
                g = shape(f["geometry"])
            except Exception:  # noqa: BLE001
                continue
            if not g.is_valid:
                g = g.buffer(0)
            geoms.append(g)
            self.props.append(f.get("properties") or {})
        self.geoms = geoms
        self.arbol = STRtree(geoms) if geoms else None

    def cerca(self, lat: float, lon: float, metros: float) -> list[tuple[float, dict]]:
        """(distancia en metros, propiedades) de lo que está a menos de `metros` (0 si lo contiene)."""
        if self.arbol is None:
            return []
        p = Point(lon, lat)
        salida = []
        for i in self.arbol.query(p.buffer(metros * METRO * 1.3)):
            d = self.geoms[int(i)].distance(p) / METRO
            if d <= metros:
                salida.append((round(d), self.props[int(i)]))
        return sorted(salida, key=lambda x: x[0])


class Fichas:
    def __init__(self, datos: Path, zonas):
        self.datos = Path(datos)
        self.zonas = zonas
        self._capas: dict[str, _Capa] = {}
        self._barrios: dict[str, dict] | None = None
        self._accidentes: list | None = None
        self._arbol_accidentes = None
        self._catastro: dict[tuple, tuple[float, dict]] = {}
        self._candado = threading.RLock()

    def _capa(self, nombre: str) -> _Capa:
        with self._candado:
            if nombre not in self._capas:
                self._capas[nombre] = _Capa(leer_geojson(self.datos, nombre))
            return self._capas[nombre]

    def olvidar(self) -> None:
        """Tras bajar capas nuevas: se vuelven a leer la próxima vez."""
        with self._candado:
            self._capas.clear()
            self._barrios = None
            self._accidentes = None

    # ------------------------------------------------------------ accidentes

    def situar_accidentes(self, forzar: bool = False) -> int:
        """Sitúa los accidentes (una vez; luego solo si el CSV es más nuevo). Devuelve cuántos ha situado."""
        origen = self.datos / CARPETA / "accidentes.csv"
        destino = self.datos / CARPETA / FICHERO_ACCIDENTES
        if not origen.exists() or self.zonas is None or not self.zonas.hay:
            return 0
        if not forzar and destino.exists() and destino.stat().st_mtime >= origen.stat().st_mtime:
            return -1
        filas = []
        for r in leer_csv(self.datos, "accidentes"):
            ubicacion = next((v for k, v in r.items() if k and k.upper().startswith("UBICACI")), "") or ""
            try:
                t = int(datetime.fromisoformat((r.get("FECHA") or "").strip()).timestamp())
            except ValueError:
                continue
            lugares = self.zonas.buscar(ubicacion, max_lugares=1) if ubicacion else []
            precisos = [l for l in lugares if l.tipo in ("cruce", "direccion")]
            if not precisos:
                continue
            l = precisos[0]
            filas.append([t, l.lat, l.lon, l.barrio, GRAVEDAD.get((r.get("TIPO GRAVEDAD") or "").strip(), 0),
                          (r.get("TIPO ACCIDENTE") or "").strip().capitalize(), (r.get("UNIDADES_IMPLICADAS") or "").strip().lower(), ubicacion.strip()])
        temporal = destino.with_suffix(".parcial")
        temporal.write_text(json.dumps({"campos": ["t", "lat", "lon", "barrio", "gravedad", "tipo", "unidades", "ubicacion"], "filas": filas},
                                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporal.replace(destino)
        with self._candado:
            self._accidentes = None
        return len(filas)

    def accidentes(self) -> list:
        with self._candado:
            if self._accidentes is None:
                ruta = self.datos / CARPETA / FICHERO_ACCIDENTES
                self._accidentes = json.loads(ruta.read_text(encoding="utf-8"))["filas"] if ruta.exists() else []
                puntos = [Point(f[2], f[1]) for f in self._accidentes]
                self._arbol_accidentes = STRtree(puntos) if puntos else None
            return self._accidentes

    def accidentes_cerca(self, lat: float, lon: float, metros: float = 40) -> list[dict]:
        filas = self.accidentes()
        if self._arbol_accidentes is None:
            return []
        p = Point(lon, lat)
        salida = []
        for i in self._arbol_accidentes.query(p.buffer(metros * METRO * 1.3)):
            f = filas[int(i)]
            d = Point(f[2], f[1]).distance(p) / METRO
            if d <= metros:
                salida.append({"t": f[0], "gravedad": f[4], "tipo": f[5], "unidades": f[6], "ubicacion": f[7], "metros": round(d)})
        return sorted(salida, key=lambda x: -x["t"])

    # ------------------------------------------------------------ barrios

    def _por_barrio(self) -> dict[str, dict]:
        """Vulnerabilidad, quejas del último año por tema y accidentes por gravedad, de cada barrio."""
        with self._candado:
            if self._barrios is not None:
                return self._barrios
            salida: dict[str, dict] = defaultdict(dict)
            for f in leer_geojson(self.datos, "vulnerabilidad"):
                p = f.get("properties") or {}
                codigo = _codigo_barrio(p.get("codbar"))
                if codigo:
                    salida[codigo]["vulnerabilidad"] = {k: p.get(k) for k in ("ind_global", "vul_global", "ind_equip", "vul_equip", "ind_dem", "vul_dem",
                                                                              "ind_econom", "vul_econom")}
            hace_un_año = time.time() - 365 * 86400
            temas: dict[str, Counter] = defaultdict(Counter)
            for r in leer_csv(self.datos, "quejas"):
                codigo = _codigo_barrio(next((v for k, v in r.items() if k and k.startswith("Barrio Locali")), None))
                if not codigo:
                    continue
                try:
                    if datetime.strptime((r.get("Fecha Entrada") or "").strip(), "%d/%m/%Y").timestamp() < hace_un_año:
                        continue
                except ValueError:
                    continue
                temas[codigo][(r.get("Tema") or "Otros").strip()] += 1
            for codigo, c in temas.items():
                salida[codigo]["quejas"] = {"total": sum(c.values()), "temas": c.most_common(6)}
            gravedad: dict[str, Counter] = defaultdict(Counter)
            for f in self.accidentes():
                if f[0] >= hace_un_año and f[3]:
                    gravedad[f[3]][f[4]] += 1
            for codigo, c in gravedad.items():
                salida[codigo]["accidentes"] = {"total": sum(c.values()), "heridos": sum(n for g, n in c.items() if g >= 1),
                                                "graves": sum(n for g, n in c.items() if g >= 3)}
            self._barrios = dict(salida)
            return self._barrios

    def barrio(self, codigo: str) -> dict:
        return self._por_barrio().get(codigo, {})

    def todos_los_barrios(self) -> dict[str, dict]:
        return self._por_barrio()

    # ------------------------------------------------------------ un punto

    def punto(self, lat: float, lon: float, catastro: bool = True, sesion: requests.Session | None = None) -> dict:
        """Todo lo que se sabe de un punto de la ciudad."""
        ficha: dict = {"lat": round(lat, 6), "lon": round(lon, 6)}
        if self.zonas is not None and self.zonas.hay:
            ficha["barrio"] = self.zonas.barrio_de(lat, lon)
            ficha["barrio_nombre"] = self.zonas.nombre(ficha["barrio"])
            ficha["calle"] = self.zonas.calle_cercana(lat, lon)
        patrimonio = self._capa("patrimonio").cerca(lat, lon, 25)
        ficha["patrimonio"] = [{"metros": d, "codigo": p.get("codigo"), "nombre": p.get("denominaci"), "proteccion": p.get("grado_prot"),
                                "categoria": p.get("categoria"), "elemento": p.get("t_elemento"), "tramitacion": p.get("estado_tra")}
                               for d, p in patrimonio[:5]]
        registro = self._capa("registro_edificios").cerca(lat, lon, 15) + self._capa("registro_solares").cerca(lat, lon, 15)
        ficha["registro"] = [{"metros": d, "seccion": p.get("seccion"), "refcat": p.get("refcat"),
                              "direccion": f"{p.get('tipo_via') or ''} {p.get('emplazamie') or ''} {p.get('numero') or ''}".strip()}
                             for d, p in sorted(registro, key=lambda x: x[0])[:3]]
        ficha["vpp"] = [{"metros": d, "viviendas": p.get("numviviendas"), "tipo": p.get("tipovpp"), "regimen": p.get("regimencalifi"),
                         "promocion": p.get("tipopromo"), "uso": p.get("uso")} for d, p in self._capa("vpp").cerca(lat, lon, 10)[:2]]
        ficha["zas"] = [p.get("zona") for d, p in self._capa("zas").cerca(lat, lon, 0)]
        lugares = self._capa("monumentos").cerca(lat, lon, 120) + self._capa("recursos_turisticos").cerca(lat, lon, 120)
        ficha["cerca"] = [{"metros": d, "nombre": p.get("nombre")} for d, p in sorted(lugares, key=lambda x: x[0])[:6]]
        ficha["accidentes"] = self.accidentes_cerca(lat, lon, 40)[:40]
        if catastro:
            ficha["catastro"] = self.catastro(lat, lon, sesion)
        return ficha

    def catastro(self, lat: float, lon: float, sesion: requests.Session | None = None) -> dict:
        """La parcela catastral del punto y sus datos no protegidos (uso, superficie, año). Se guarda un día."""
        clave = (round(lat, 5), round(lon, 5))
        hecho = self._catastro.get(clave)
        if hecho and time.time() - hecho[0] < 86400:
            return hecho[1]
        sesion = sesion or requests.Session()
        try:
            r = sesion.get(CATASTRO_RC, params={"SRS": "EPSG:4326", "Coordenada_X": f"{lon:.6f}", "Coordenada_Y": f"{lat:.6f}"}, timeout=15)
            r.raise_for_status()
            datos = leer_rccoor(r.json())
            if datos.get("rc"):
                r2 = sesion.get(CATASTRO_DATOS, params={"RefCat": datos["rc"]}, timeout=20)
                r2.raise_for_status()
                datos.update(leer_dnprc(r2.json()))
                datos["enlace"] = CATASTRO_FICHA.format(a=datos["rc"][:7], b=datos["rc"][7:14])
        except Exception as exc:  # noqa: BLE001
            datos = {"error": f"{type(exc).__name__}: {exc}"[:200]}
        if len(self._catastro) > 500:
            self._catastro.clear()
        self._catastro[clave] = (time.time(), datos)
        return datos


def _buscar(obj, clave: str):
    """La primera aparición de `clave` en un JSON anidado (el Catastro cambia a veces la forma)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == clave.lower():
                return v
        for v in obj.values():
            r = _buscar(v, clave)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _buscar(v, clave)
            if r is not None:
                return r
    return None


def leer_rccoor(datos: dict) -> dict:
    """Respuesta de Consulta_RCCOOR -> {rc, direccion}."""
    pc = _buscar(datos, "pc") or {}
    rc = f"{pc.get('pc1') or ''}{pc.get('pc2') or ''}".strip()
    return {"rc": rc if len(rc) == 14 else None, "direccion": _buscar(datos, "ldt") or ""}


def leer_dnprc(datos: dict) -> dict:
    """Respuesta de Consulta_DNPRC -> uso, superficie y año de la parcela, y sus inmuebles si hay varios."""
    salida: dict = {}
    debi = _buscar(datos, "debi")
    if isinstance(debi, dict):
        salida.update({"uso": debi.get("luso"), "superficie": _numero(debi.get("sfc")), "año": _numero(debi.get("ant"))})
    lista = _buscar(datos, "lrcdnp")
    if isinstance(lista, dict):
        lista = lista.get("rcdnp")
    if isinstance(lista, list):
        inmuebles = []
        for x in lista[:400]:
            d = x.get("debi") or {}
            inmuebles.append({"uso": d.get("luso"), "superficie": _numero(d.get("sfc")), "año": _numero(d.get("ant"))})
        usos = Counter(i["uso"] for i in inmuebles if i["uso"])
        años = [i["año"] for i in inmuebles if i["año"]]
        salida.update({"inmuebles": len(lista), "usos": usos.most_common(), "año": min(años) if años else salida.get("año"),
                       "superficie_total": round(sum(i["superficie"] or 0 for i in inmuebles)) or None})
    elif "inmuebles" not in salida and salida:
        salida["inmuebles"] = 1
    clase = _buscar(datos, "cn")
    if clase:
        salida["clase"] = {"UR": "urbano", "RU": "rústico"}.get(clase, clase)
    return salida


def _numero(v):
    try:
        return float(v) if "." in str(v) else int(v)
    except (TypeError, ValueError):
        return None
