"""Busca posibles abandonos comparando cada edificio consigo mismo a lo largo de varios años.

El buscador de siempre parte de lo que Catastro marca como ruinoso o deficiente. Esto mira los
demás: edificios que Catastro da por buenos y que en la foto aérea parecen ir a menos.

De dónde sale cada cosa:
- Los edificios y sus contornos, de los ZIP de Catastro que `osintmaps buscar` ya dejó en
  `cache/catastro` (uno por municipio).
- Las fotos, del ICV: publica una ortofoto por año de 2017 a 2024 (25 cm, toda la Comunitat)
  y la de 2025 (15 cm, la provincia), todas también en infrarrojo.

Qué se mide. Para cada edificio y cada año se recorta la foto en infrarrojo sobre su contorno y
se apunta cuánta vegetación hay dentro, cuánto hay en sombra y lo rugoso que se ve. Un tejado
entero da lo mismo un año tras otro. Uno que se hunde se llena de sombras y, a los pocos años,
de plantas. Las fotos de cada año salen con colores algo distintos, así que nada se compara en
bruto: de cada año se saca primero qué es «vegetación» y qué es «oscuro» en esa foto.

    python cambios.py medir   --carpeta cache/_vision --catastro cache/catastro --municipios 46137 --todos
    python cambios.py puntuar --carpeta cache/_vision --datos datos --municipios 46137 --todos
    python cambios.py hojas   --carpeta cache/_vision --municipios 46137 --todos --cuantos 24
    python cambios.py capa    --carpeta cache/_vision --datos datos

`medir` se puede cortar y relanzar: se salta lo ya medido. Guarda cifras, no fotos (salvo que
se pida con --guardar-fotos, que viene bien para una zona de prueba)."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # para leer Catastro con lo que ya trae el programa
from osintmaps.fuentes import catastro as C                            # noqa: E402

ANIOS = (2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
VENTANA_M = 256.0                # lado de cada recorte que se pide
MARGEN_M = 16.0                  # solape entre recortes vecinos
CELDA_M = VENTANA_M - 2 * MARGEN_M   # cada edificio se mide en el recorte donde cae su centro
ANILLO_M = 10.0                  # cuánto se mira alrededor del edificio
NDVI_MIN, NDVI_ANCHO, N_NDVI = -0.2, 0.05, 16     # la vegetación se guarda como reparto en 16 tramos de -0,2 a 0,6
N_BRILLO = 16                                      # y el brillo, en 16 tramos de 0 a 1
AGENTE = "osintmaps (uso personal; comparacion de anos)"             # sin tildes: el servidor del ICV falla con ellas
a_geo = Transformer.from_crs(25830, 4326, always_xy=True).transform


def servicio(anio: int) -> tuple[str, str]:
    """Dirección del WMS y nombre base de las capas de un año."""
    vuelo = f"{anio}PVAL0015" if anio == 2025 else f"{anio}CVAL0025"
    return f"https://terramapas.icv.gva.es/0202_{vuelo}", vuelo


def no_dormir() -> None:
    """Pide a Windows que no suspenda el equipo mientras dure este proceso (no cambia ningún ajuste)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except Exception:                    # fuera de Windows no hace falta
        pass


# --------------------------------------------------------------------------
# Los edificios
# --------------------------------------------------------------------------

def leer_edificios(ruta: Path) -> list[dict]:
    """Todos los edificios de un municipio (no solo los deteriorados), con su contorno en metros (UTM 30)."""
    salida, epsg = [], None
    with zipfile.ZipFile(ruta) as zf:
        gml = [n for n in zf.namelist() if n.lower().endswith(".building.gml")]
        if not gml:
            return salida
        with zf.open(gml[0]) as fh:
            for _, elem in ET.iterparse(C._FlujoSaneado(fh), events=("end",)):
                nombre = C._local(elem.tag)
                if nombre in ("featureMember", "member"):
                    elem.clear()
                    continue
                if nombre != "Building":
                    continue
                estado = uso = ref = fecha = area = None
                for e in elem.iter():
                    n, texto = C._local(e.tag), (e.text or "").strip()
                    if n == "conditionOfConstruction":
                        estado = texto
                    elif n == "currentUse":
                        uso = texto or None
                    elif n == "localId" and ref is None:
                        ref = texto
                    elif n == "beginning" and fecha is None:
                        fecha = texto
                    elif n == "value" and area is None:
                        area = texto
                    elif epsg is None and n in ("Envelope", "Surface", "Polygon", "MultiSurface"):
                        epsg = C._epsg(e.get("srsName"))
                geom = C._geometria(elem) if ref else None
                if geom is not None and not geom.is_empty:
                    salida.append({"ref": ref, "estado": estado, "uso": C.USOS.get(uso or ""), "anio": C._anio(fecha), "sup": C._numero(area), "geom": geom})
                elem.clear()
    if salida and epsg not in (None, 25830):                           # por si algún municipio viniera en otro huso
        a_30 = Transformer.from_crs(epsg, 25830, always_xy=True).transform
        for e in salida:
            e["geom"] = shapely.transform(e["geom"], lambda c: np.column_stack(a_30(c[:, 0], c[:, 1])))
    return salida


def leer_piezas(ruta: Path) -> dict[str, tuple]:
    """De cada edificio, lo que de verdad levanta del suelo: la unión de sus piezas con alguna planta sobre rasante, y cuántas plantas.

    El contorno «de edificio» de Catastro incluye sótanos que asoman bajo un jardín y cosas así; visto desde arriba eso no es tejado."""
    piezas: dict[str, list] = defaultdict(list)
    plantas: dict[str, int] = defaultdict(int)
    with zipfile.ZipFile(ruta) as zf:
        gml = [n for n in zf.namelist() if n.lower().endswith(".buildingpart.gml")]
        if not gml:
            return {}
        with zf.open(gml[0]) as fh:
            for _, elem in ET.iterparse(C._FlujoSaneado(fh), events=("end",)):
                nombre = C._local(elem.tag)
                if nombre in ("featureMember", "member"):
                    elem.clear()
                    continue
                if nombre != "BuildingPart":
                    continue
                ref = sobre = None
                for e in elem.iter():
                    n, texto = C._local(e.tag), (e.text or "").strip()
                    if n == "localId" and ref is None:
                        ref = texto.split("_")[0]
                    elif n == "numberOfFloorsAboveGround":
                        sobre = int(texto) if texto.isdigit() else None
                if ref and sobre:
                    geom = C._geometria(elem)
                    if geom is not None and not geom.is_empty:
                        piezas[ref].append(geom)
                        plantas[ref] = max(plantas[ref], sobre)
                elem.clear()
    return {ref: (shapely.union_all(g) if len(g) > 1 else g[0], plantas[ref]) for ref, g in piezas.items()}


def fuera_de_casco(ref: str) -> bool:
    """Por la forma de la referencia: parcela rústica (46137A00500001) o «diseminado» (001540100YJ18B).

    Las urbanas llevan siete caracteres y la hoja de plano detallado (0892613YJ2709S); las de diseminado, nueve y la hoja a
    escala 1:5.000, que es más corta (YJ18B)."""
    return bool(re.match(r"^\d{5}[A-Z]\d{8}$", ref) or re.match(r"^[0-9A-Z]{9}[A-Z]{2}\d{2}[A-Z]$", ref))


def vecinos(centros: np.ndarray, radio: float = 150.0) -> np.ndarray:
    """Cuántos otros edificios tiene cada uno a menos de `radio` metros (con una rejilla, que son muchos)."""
    celda = np.floor(centros / radio).astype(np.int64)
    por_celda: dict[tuple[int, int], list[int]] = defaultdict(list)
    for k, (i, j) in enumerate(celda):
        por_celda[(int(i), int(j))].append(k)
    cuenta = np.zeros(len(centros), np.int32)
    for (i, j), dentro in por_celda.items():
        cerca = [k for di in (-1, 0, 1) for dj in (-1, 0, 1) for k in por_celda.get((i + di, j + dj), ())]
        otros = centros[cerca]
        for k in dentro:
            cuenta[k] = int((np.hypot(otros[:, 0] - centros[k, 0], otros[:, 1] - centros[k, 1]) <= radio).sum()) - 1
    return cuenta


def cargar_universo(args) -> list[dict]:
    """Los edificios que se van a mirar. Se guarda en disco: leer los 266 municipios lleva unos minutos."""
    base = Path(args.carpeta) / "cambios"
    base.mkdir(parents=True, exist_ok=True)
    municipios = [m for m in (args.municipios or "").split(",") if m]
    nombre = base / f"universo2-{'-'.join(municipios) or 'todo'}-{int(args.min_superficie)}{'-todos' if args.todos else f'-v{args.max_vecinos}'}.json"
    if nombre.exists():
        universo = json.loads(nombre.read_text(encoding="utf-8"))
        for e in universo:
            e["geom"] = shape(e["geom"])
        return universo
    universo = []
    zips = sorted(Path(args.catastro).glob("*.zip"))
    for k, ruta in enumerate(zips):
        if municipios and ruta.stem not in municipios:
            continue
        edificios = leer_edificios(ruta)
        if not edificios:
            continue
        piezas = leer_piezas(ruta)
        for e in edificios:
            e["plantas"] = None
            if e["ref"] in piezas:
                geom, e["plantas"] = piezas[e["ref"]]
                if geom.geom_type in ("Polygon", "MultiPolygon") and geom.area >= 0.3 * e["geom"].area:
                    e["geom"] = geom
        centros = np.array([[e["geom"].centroid.x, e["geom"].centroid.y] for e in edificios])
        cerca = vecinos(centros)
        for e, (cx, cy), n in zip(edificios, centros, cerca):
            if e["geom"].area < args.min_superficie:
                continue
            # Fuera de casco: en suelo rústico o diseminado, o con pocos vecinos (bordes de pueblo, naves sueltas).
            if args.todos or fuera_de_casco(e["ref"]) or n <= args.max_vecinos:
                universo.append({"ref": e["ref"], "muni": ruta.stem, "estado": e["estado"], "uso": e["uso"], "anio": e["anio"], "sup": e["sup"], "plantas": e["plantas"], "area": round(e["geom"].area),
                                 "vecinos": int(n), "x": round(float(cx), 1), "y": round(float(cy), 1), "geom": e["geom"]})
        print(f"  {ruta.stem}: {len(edificios)} edificios; van {len(universo)} elegidos ({k + 1}/{len(zips)})", flush=True)
    nombre.write_text(json.dumps([{**e, "geom": mapping(shapely.set_precision(e["geom"], 0.1))} for e in universo], separators=(",", ":")), encoding="utf-8")
    return universo


# --------------------------------------------------------------------------
# Medir
# --------------------------------------------------------------------------

def pedir(sesion: requests.Session, anio: int, x0: float, y0: float, lado_px: int, copia: Path | None = None) -> np.ndarray | None | str:
    """Un recorte en infrarrojo (canales: infrarrojo, rojo, verde). "fuera" si ese año no cubre la zona; None si falla la red."""
    if copia is not None and copia.exists():
        img = cv2.imdecode(np.fromfile(copia, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            return img[:, :, ::-1]
    url, vuelo = servicio(anio)
    for intento in range(3):
        try:
            r = sesion.get(url, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": f"{vuelo}_IRG", "STYLES": "", "CRS": "EPSG:25830",
                                        "BBOX": f"{x0:.2f},{y0:.2f},{x0 + VENTANA_M:.2f},{y0 + VENTANA_M:.2f}", "WIDTH": lado_px, "HEIGHT": lado_px, "FORMAT": "image/jpeg"}, timeout=60)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    if img.std() < 4:                                  # todo de un color: ese vuelo no pasa por aquí
                        return "fuera"
                    if copia is not None:
                        copia.parent.mkdir(parents=True, exist_ok=True)
                        copia.write_bytes(r.content)
                    return img[:, :, ::-1]
        except requests.RequestException:
            pass
        time.sleep(1 + 3 * intento)
    return None


def medir_edificio(irg: np.ndarray, geom, x0: float, y1: float, paso: float) -> dict | None:
    """Las cifras de un edificio en un recorte. `irg` va en (infrarrojo, rojo, verde); (x0, y1) es su esquina de arriba a la izquierda."""
    alto, ancho = irg.shape[:2]
    bx0, by0, bx1, by1 = geom.bounds
    m = int(round(ANILLO_M / paso)) + 2
    c0, c1 = max(int((bx0 - x0) / paso) - m, 0), min(int(math.ceil((bx1 - x0) / paso)) + m, ancho)
    f0, f1 = max(int((y1 - by1) / paso) - m, 0), min(int(math.ceil((y1 - by0) / paso)) + m, alto)
    if c1 - c0 < 4 or f1 - f0 < 4:
        return None
    mascara = np.zeros((f1 - f0, c1 - c0), np.uint8)

    def a_px(coords) -> np.ndarray:
        xy = np.asarray(coords)
        return np.column_stack([(xy[:, 0] - x0) / paso - c0, (y1 - xy[:, 1]) / paso - f0]).round().astype(np.int32)

    for parte in shapely.get_parts(geom):
        cv2.fillPoly(mascara, [a_px(parte.exterior.coords)], 1)
        for hueco in parte.interiors:                                 # los patios no son edificio
            cv2.fillPoly(mascara, [a_px(hueco.coords)], 0)
    # Se mira solo el interior: las fotos no son verticales del todo y el tejado sale corrido uno o dos metros
    # respecto al contorno, distinto cada año. Cuanto más ancho el edificio, más margen se le quita (de 0,5 a 2 m);
    # con menos de 4 m de ancho no queda interior del que fiarse y no se mide.
    lejos = cv2.distanceTransform(mascara, cv2.DIST_L2, 3)
    medio_ancho = float(lejos.max()) * paso
    if medio_ancho < 2.0:
        return None
    d = lejos * paso > min(2.0, max(0.5, 0.3 * medio_ancho))
    n = int(d.sum())
    if n * paso * paso < 10:
        return None
    trozo = irg[f0:f1, c0:c1].astype(np.float32) / 255
    if float(trozo[d].std()) < 0.004:                                 # liso del todo: borde de la foto de ese año
        return None
    nir, rojo, verde = trozo[..., 0], trozo[..., 1], trozo[..., 2]
    ndvi = (nir - rojo) / (nir + rojo + 1e-6)
    ndvi[verde + 0.02 < 0.9 * rojo] = 0.0                             # lo rojizo no es planta: la teja también refleja mucho infrarrojo
    ndvi[nir - rojo < 0.06] = np.minimum(ndvi[nir - rojo < 0.06], 0.0)   # ni lo muy oscuro: en una pizarra en sombra el cociente se dispara con nada
    brillo = (rojo + verde) / 2
    grad = np.hypot(cv2.Sobel(brillo, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(brillo, cv2.CV_32F, 0, 1, ksize=3))

    def reparto(valores: np.ndarray) -> list[int]:
        return np.bincount(np.clip(((valores - NDVI_MIN) / NDVI_ANCHO).astype(np.int32), 0, N_NDVI - 1), minlength=N_NDVI).tolist()

    # El centro del edificio aparte: las copas de los árboles de al lado tapan los bordes, no el centro.
    nucleo = lejos >= 0.5 * float(lejos.max())
    seco = d & (ndvi < 0.15)                                          # el brillo se apunta solo de lo que no es planta (las plantas ya salen oscuras)
    lado_anillo, lado_pegado = 2 * int(round(ANILLO_M / paso)) + 1, 2 * int(round(2.0 / paso)) + 1
    anillo = (cv2.dilate(mascara, np.ones((lado_anillo, lado_anillo), np.uint8)) > 0) & ~(cv2.dilate(mascara, np.ones((lado_pegado, lado_pegado), np.uint8)) > 0)
    return {"n": n, "v": reparto(ndvi[d]), "k": reparto(ndvi[nucleo]), "a": reparto(ndvi[anillo]) if anillo.any() else [0] * N_NDVI,
            "b": np.bincount(np.clip((brillo[seco] * N_BRILLO).astype(np.int32), 0, N_BRILLO - 1), minlength=N_BRILLO).tolist(),
            "t": round(float(brillo[d].std()), 4), "g": round(float(grad[d].mean()), 4),
            "c": [round(float(nir[d].mean()), 3), round(float(rojo[d].mean()), 3), round(float(verde[d].mean()), 3)]}


def tarea(sesion, anio: int, clave: str, x0: float, y0: float, edificios: list[dict], paso: float, carpeta_fotos: Path | None) -> dict:
    """Un recorte de un año y las cifras de los edificios que caen en él."""
    lado_px = int(round(VENTANA_M / paso))
    irg = pedir(sesion, anio, x0, y0, lado_px, carpeta_fotos / str(anio) / f"{clave}.jpg" if carpeta_fotos else None)
    salida = {"a": anio, "c": clave, "e": {}}
    if irg is None:
        salida["fallo"] = True
    elif isinstance(irg, str):
        salida["fuera"] = True
    else:
        for e in edificios:
            cifras = medir_edificio(irg, e["geom"], x0, y0 + VENTANA_M, paso)
            if cifras:
                salida["e"][e["ref"]] = cifras
    return salida


def recortes_de(universo: list[dict]) -> dict[str, tuple[float, float, list[dict]]]:
    """Reparte los edificios en recortes: los que caben, en el de la rejilla; los muy grandes, en uno propio centrado en ellos."""
    recortes: dict[str, tuple[float, float, list[dict]]] = {}
    for e in universo:
        i, j = int(e["x"] // CELDA_M), int(e["y"] // CELDA_M)
        x0, y0 = i * CELDA_M - MARGEN_M, j * CELDA_M - MARGEN_M
        bx0, by0, bx1, by1 = e["geom"].bounds
        if bx0 - 3 < x0 or by0 - 3 < y0 or bx1 + 3 > x0 + VENTANA_M or by1 + 3 > y0 + VENTANA_M:
            recortes[f"e_{e['ref']}"] = (round(e["x"] - VENTANA_M / 2, 1), round(e["y"] - VENTANA_M / 2, 1), [e])
        else:
            recortes.setdefault(f"{i}_{j}", (x0, y0, []))[2].append(e)
    return recortes


def medir(args) -> None:
    no_dormir()
    base = Path(args.carpeta) / "cambios"
    universo = cargar_universo(args)
    anios = [int(a) for a in args.anios.split(",")]
    recortes = recortes_de(universo)
    registro = base / f"medidas-{args.etiqueta}.jsonl"
    hechas = set()
    if args.rehacer and registro.exists():
        registro.unlink()
    if registro.exists():
        with registro.open(encoding="utf-8") as fh:
            for linea in fh:
                try:
                    d = json.loads(linea)
                except ValueError:
                    continue
                if not d.get("fallo"):
                    hechas.add((d["a"], d["c"]))
    pendientes = [(a, c) for c in recortes for a in anios if (a, c) not in hechas]
    print(f"{len(universo)} edificios en {len(recortes)} recortes; {len(anios)} años; quedan {len(pendientes)} peticiones", flush=True)
    sesion = requests.Session()
    sesion.headers["User-Agent"] = AGENTE
    sesion.mount("https://", requests.adapters.HTTPAdapter(pool_connections=args.hilos, pool_maxsize=args.hilos))
    fotos = base / f"fotos-{args.etiqueta}" if args.guardar_fotos else None
    t0, hechos, fallos = time.time(), 0, 0
    with ThreadPoolExecutor(args.hilos) as hilos, registro.open("a", encoding="utf-8") as fh:
        for lote in range(0, len(pendientes), 2000):                   # por tandas, para no tener cien mil tareas en memoria
            futuros = [hilos.submit(tarea, sesion, a, c, recortes[c][0], recortes[c][1], recortes[c][2], args.paso, fotos) for a, c in pendientes[lote:lote + 2000]]
            for f in as_completed(futuros):
                d = f.result()
                fallos += bool(d.get("fallo"))
                fh.write(json.dumps(d, separators=(",", ":")) + "\n")
                hechos += 1
                if hechos % 100 == 0 or hechos == len(pendientes):
                    fh.flush()
                    va = time.time() - t0
                    print(f"{hechos}/{len(pendientes)} ({fallos} con fallo) {va:.0f} s; quedan unos {va / hechos * (len(pendientes) - hechos) / 60:.0f} min", flush=True)
    print("FIN-MEDIR", flush=True)


# --------------------------------------------------------------------------
# Puntuar
# --------------------------------------------------------------------------

def leer_medidas(ruta: Path) -> dict[str, dict[int, dict]]:
    """ref → año → cifras, de todo lo medido hasta ahora."""
    por_ref: dict[str, dict[int, dict]] = defaultdict(dict)
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            for ref, cifras in d.get("e", {}).items():
                por_ref[ref][d["a"]] = cifras
    return por_ref


def otsu(reparto: np.ndarray) -> int:
    """El tramo que mejor parte un reparto en dos montones (método de Otsu). Devuelve cuántos tramos quedan en el de abajo."""
    h = reparto.astype(float)
    centros = np.arange(len(h)) + 0.5
    peso, suma = h.cumsum(), (h * centros).cumsum()
    mejor, corte = -1.0, len(h) // 2
    for k in range(len(h) - 1):
        abajo, arriba = peso[k], peso[-1] - peso[k]
        if abajo <= 0 or arriba <= 0:
            continue
        separacion = abajo * arriba * (suma[k] / abajo - (suma[-1] - suma[k]) / arriba) ** 2
        if separacion > mejor:
            mejor, corte = separacion, k + 1
    return corte


def por_encima(reparto, corte: float) -> float:
    """Qué parte de un reparto queda por encima de `corte` (medido en tramos; reparte el tramo partido)."""
    h = np.asarray(reparto, float)
    total = h.sum()
    if total <= 0:
        return 0.0
    k = int(min(max(math.floor(corte), 0), len(h) - 1))
    return float((h[k + 1:].sum() + h[k] * (1 - min(max(corte - k, 0.0), 1.0))) / total)


def calibrar(medidas: dict[str, dict[int, dict]], buenos: set[str]) -> dict[int, dict]:
    """De cada año, con todos los edificios a la vez: dónde empieza la vegetación, qué es «oscuro» y lo rugoso que es lo normal."""
    junto: dict[int, dict] = defaultdict(lambda: {"a": np.zeros(N_NDVI), "b": np.zeros(N_BRILLO), "t": [], "g": []})
    for ref, serie in medidas.items():
        for anio, m in serie.items():
            j = junto[anio]
            j["a"] += np.asarray(m["a"], float) + np.asarray(m["v"], float)
            if ref in buenos:
                j["b"] += np.asarray(m["b"], float)
                j["t"].append(m["t"])
                j["g"].append(m["g"])
    salida = {}
    for anio, j in sorted(junto.items()):
        corte_veg = float(min(max(otsu(j["a"]), 6), 11))              # entre 0,10 y 0,35 de NDVI
        acumulado = j["b"].cumsum() / max(j["b"].sum(), 1)
        k = int(np.searchsorted(acumulado, 0.08))                      # oscuro: lo que queda por debajo del 8 % más oscuro de los tejados de ese año
        antes = acumulado[k - 1] if k else 0.0
        corte_osc = k + (0.08 - antes) / max(acumulado[k] - antes, 1e-9)
        t, g = np.array(j["t"] or [0.0]), np.array(j["g"] or [0.0])
        salida[anio] = {"veg": corte_veg, "osc": float(corte_osc),
                        "t": (float(np.median(t)), float(1.4826 * np.median(np.abs(t - np.median(t))) + 1e-6)),
                        "g": (float(np.median(g)), float(1.4826 * np.median(np.abs(g - np.median(g))) + 1e-6))}
    return salida


def rasgos(serie: dict[int, dict], cal: dict[int, dict]) -> dict[str, np.ndarray]:
    """La serie de un edificio ya comparable entre años: vegetación, vegetación en el centro y alrededor, sombra y rugosidad."""
    anios = sorted(a for a in serie if a in cal)
    r = {"anios": np.array(anios)}
    r["veg"] = np.array([por_encima(serie[a]["v"], cal[a]["veg"]) for a in anios])
    r["nuc"] = np.array([por_encima(serie[a]["k"], cal[a]["veg"]) for a in anios])
    r["alr"] = np.array([por_encima(serie[a]["a"], cal[a]["veg"]) for a in anios])
    r["osc"] = np.array([(1 - por_encima(serie[a]["b"], cal[a]["osc"])) * sum(serie[a]["b"]) / max(serie[a]["n"], 1) for a in anios])
    r["tex"] = np.array([(serie[a]["t"] - cal[a]["t"][0]) / cal[a]["t"][1] for a in anios])
    r["rug"] = np.array([(serie[a]["g"] - cal[a]["g"][0]) / cal[a]["g"][1] for a in anios])
    return r


TRAMOS_ENTORNO = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01)


def resumen(r: dict[str, np.ndarray]) -> tuple[dict, dict, int] | None:
    """Principio y final de la serie: la mediana de varios años, para que una foto rara no decida."""
    n = len(r["anios"])
    if n < 3:
        return None
    k = 3 if n >= 7 else 2 if n >= 4 else 1
    antes = {c: float(np.median(v[:k])) for c, v in r.items() if c != "anios"}
    ahora = {c: float(np.median(v[-k:])) for c, v in r.items() if c != "anios"}
    return antes, ahora, k


def lo_normal(entorno: np.ndarray, centro: np.ndarray) -> tuple[list[float], list[float]]:
    """Cuánta vegetación llegan a tener en el centro los edificios corrientes, según lo verde que es su entorno.

    Un tejado sano en mitad de una pinada tiene copas encima; el mismo verde en un tejado sin árboles cerca no es normal.
    Devuelve, por tramos de entorno, el valor que solo supera 1 de cada 20 edificios."""
    centros, topes = [], []
    for a, b in zip(TRAMOS_ENTORNO[:-1], TRAMOS_ENTORNO[1:]):
        m = (entorno >= a) & (entorno < b)
        if int(m.sum()) >= 30:
            centros.append((a + min(b, 1.0)) / 2)
            topes.append(float(np.percentile(centro[m], 95)))
    if not centros:
        return [0.0, 1.0], [0.1, 0.5]
    return centros, np.maximum.accumulate(topes).tolist()               # más verde fuera nunca baja el listón


def juzgar(r: dict[str, np.ndarray], normal: tuple[list[float], list[float]]) -> dict | None:
    """Sin detector de tejado: de la vegetación de un edificio a una nota y el porqué. None si no hay nada que decir.

    Dos motivos, que pueden darse juntos: tiene dentro más vegetación de la que explica su entorno (cómo está) y le ha ido
    creciendo en estos años (hacia dónde va). En las zonas de prueba acierta uno de cada ocho: es el recurso cuando no se
    ha pasado tejado.py, no el camino bueno."""
    partes = resumen(r)
    if partes is None:
        return None
    antes, ahora, k = partes
    sube = {c: ahora[c] - antes[c] for c in antes}
    anios = r["anios"].tolist()
    pct = lambda v: f"{round(100 * v)} %"                             # noqa: E731
    motivos, nota = [], 0.0
    tope = float(np.interp(ahora["alr"], *normal))
    exceso = ahora["nuc"] - tope
    if exceso >= 0.10 and ahora["nuc"] >= 0.15:
        nota += 100 * exceso
        motivos.append(f"tiene vegetación dentro que su entorno no explica: el {pct(ahora['nuc'])} del centro (con ese entorno, 19 de cada 20 edificios no pasan del {pct(tope)})")
    crece, cual = crecida(antes, ahora)
    if crece >= 0.12 and antes["nuc"] <= 0.25:
        suma = 100 * crece
        texto = f"le crece vegetación dentro: del {pct(antes[cual])} en {anios[0]}-{anios[k - 1]} al {pct(ahora[cual])} en {anios[-k]}-{anios[-1]}"
        if sube["osc"] >= 0.1 and sube["rug"] >= 1.0:
            suma += 10
            texto += ", y la cubierta se ve más rota"
        if sube["rug"] >= 2.0 and ahora["nuc"] < 0.4:                 # cubierta muy distinta y poca planta: suele ser obra nueva o reforma
            suma *= 0.4
            texto += " (aunque la cubierta ha cambiado tanto que puede ser una obra)"
        nota += suma
        motivos.append(texto)
    if not motivos:
        return None
    return {"clase": "vegetacion_sola", "nota": round(nota, 1), "motivos": motivos, **series_de(r)}


def crecida(antes: dict, ahora: dict) -> tuple[float, str]:
    """Cuánto ha subido la vegetación de dentro, ya descontado lo que cabe achacar a las copas de alrededor, y en qué medida se ve mejor."""
    # Con árboles cerca, las copas crecen y tapan tejado sin que pase nada: cuanto más verde hay fuera, más se exige dentro.
    descuento = 0.3 * antes["alr"]
    sube_centro, sube_todo = ahora["nuc"] - antes["nuc"], ahora["veg"] - antes["veg"]
    return max(sube_centro - descuento, sube_todo - descuento - 0.05), "nuc" if sube_centro >= sube_todo else "veg"


def series_de(r: dict[str, np.ndarray]) -> dict:
    return {"anios": r["anios"].tolist(), **{c: [round(float(x), 2) for x in r[c]] for c in ("veg", "nuc", "alr", "osc", "rug")}}


def sospecha(r: dict[str, np.ndarray], tejado: dict) -> dict | None:
    """Con el tejado que se ve cada año (de tejado.py): ¿lo tenía y ya no, o no se le ha visto nunca? None si no hay caso.

    Es solo la primera mitad: un tejado «perdido» puede ser una placa solar o una reforma, y uno «nunca visto», un contorno
    corrido. Lo decide la maqueta 3D en `sentenciar`."""
    partes = resumen(r)
    if partes is None:
        return None
    antes, ahora, k = partes
    anios = [a for a in r["anios"].tolist() if str(a) in tejado]
    if len(anios) < 2 * k:
        return None
    visto = [tejado[str(a)] for a in anios]
    tenia, queda = float(np.median(visto[:k])), float(np.median(visto[-k:]))
    crece, cual = crecida(antes, ahora)
    hechos = {"tenia": round(tenia, 2), "queda": round(queda, 2), "crece": round(crece, 2), "veg_antes": round(antes[cual], 2), "veg_ahora": round(ahora[cual], 2),
              "tej": [tejado.get(str(a)) for a in r["anios"].tolist()], **series_de(r)}
    if tenia >= 0.6 and queda <= 0.5 * tenia:
        con_tejado = [a for a, v in zip(anios, visto) if v > 0.5 * tenia]      # el último año en que aún se le veía y el primero en que ya no
        ultimo = max(con_tejado)
        despues = [a for a in anios if a > ultimo]
        return {"tipo": "perdio", "ultimo": ultimo, "sin": min(despues) if despues else None, **hechos}
    if max(visto) < 0.4 and max(tenia, queda) < 0.3:
        return {"tipo": "nunca", **hechos}
    return None


CLASES_POSIBLE = {"caido": "Ha perdido el tejado y queda en pie a medias", "ruina_vieja": "Sin tejado en ninguna foto y en pie solo a medias",
                  "vegetacion": "El tejado ha dejado de verse y dentro crece vegetación", "derribado": "Derribado", "sin_comprobar": "Ha dejado de verse el tejado (sin comprobar en 3D)",
                  "vegetacion_sola": "Vegetación dentro (sin detector de tejado)"}


def sentenciar(s: dict, altura: dict | None, plantas: int | None) -> dict | None:
    """La segunda mitad: lo que dice la maqueta 3D de 2025 de un edificio bajo sospecha. Devuelve la clase, la nota y los motivos,
    o None si la maqueta lo desmiente (sigue en pie y entero: placas solares, una reforma, un fallo del detector)."""
    pct = lambda v: f"{round(100 * v)} %"                             # noqa: E731
    copas = bool(altura and plantas and altura["altura_mediana_m"] > 3 * plantas + 4)
    if s["tipo"] == "perdio":
        cuando = f"entre {s['ultimo']} y {s['sin']}" if s["sin"] else f"después de {s['ultimo']}"
        base = f"tenía tejado ({pct(s['tenia'])} del contorno) y dejó de verse {cuando} (queda el {pct(s['queda'])})"
        if altura is None:
            return {"clase": "sin_comprobar", "nota": round(20 + 10 * (s["tenia"] - s["queda"]), 1), "motivos": [base, "no se ha podido comprobar con la maqueta 3D"]}
        if altura["pct_en_pie"] < 15:
            return {"clase": "derribado", "nota": round(40 + 10 * (s["tenia"] - s["queda"]), 1), "motivos": [base, "en la maqueta 3D de 2025 ya no levanta nada: derribado"]}
        if altura["pct_en_pie"] < 60 and not copas:
            return {"clase": "caido", "nota": round(80 + 20 * (s["tenia"] - s["queda"]), 1),
                    "motivos": [base, f"en la maqueta 3D de 2025 solo levanta del suelo el {altura['pct_en_pie']} % de la planta: caído a medias o en obras"]}
        if s["crece"] >= 0.2:
            nota = 30 + 40 * s["crece"]
            motivos = [base, f"le ha entrado vegetación: del {pct(s['veg_antes'])} al {pct(s['veg_ahora'])}"]
            if copas:
                nota *= 0.5
                motivos.append(f"en 3D lo que hay encima mide {altura['altura_mediana_m']:.0f} m y el edificio tiene {plantas} planta{'s' if plantas > 1 else ''}: pueden ser copas de árboles que lo tapan")
            else:
                motivos.append("en 3D sigue en pie")
            return {"clase": "vegetacion", "nota": round(nota, 1), "motivos": motivos}
        return None
    if altura is None or copas or not 15 <= altura["pct_en_pie"] < 60:
        return None
    return {"clase": "ruina_vieja", "nota": round(35 + 0.3 * (60 - altura["pct_en_pie"]) + 20 * max(s["veg_ahora"] - 0.2, 0), 1),
            "motivos": [f"en ninguna foto de 2017 a 2025 se le ve tejado (como mucho, el {pct(max(v for v in s['tej'] if v is not None))} del contorno)",
                        f"en la maqueta 3D de 2025 solo levanta del suelo el {altura['pct_en_pie']} % de la planta",
                        "puede ser una ruina vieja que Catastro da por buena, o un contorno mal puesto"]}


def direccion(sesion: requests.Session, ref: str) -> str | None:
    """La dirección que Catastro da para una referencia (servicio público, sin clave)."""
    try:
        j = sesion.get("https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_CPMRC",
                       params={"RefCat": ref[:14], "SRS": "EPSG:4326"}, timeout=20).json()
        coord = (((j.get("Consulta_CPMRCResult") or {}).get("coordenadas") or {}).get("coord") or [{}])[0]
        return coord.get("ldt") or None
    except (requests.RequestException, ValueError, AttributeError):
        return None


def puntuar(args) -> None:
    base = Path(args.carpeta) / "cambios"
    universo = {e["ref"]: e for e in cargar_universo(args)}
    medidas = leer_medidas(base / f"medidas-{args.etiqueta}.jsonl")
    buenos = {ref for ref, e in universo.items() if e["estado"] == "functional"}
    cal = calibrar(medidas, buenos)
    for anio, c in cal.items():
        print(f"  {anio}: vegetación desde NDVI {NDVI_MIN + NDVI_ANCHO * c['veg']:.2f}; oscuro por debajo de {c['osc'] / N_BRILLO:.2f}; rugosidad normal {c['g'][0]:.3f} (±{c['g'][1]:.3f})")
    series = {ref: rasgos(serie, cal) for ref, serie in medidas.items() if ref in universo}
    finales = {ref: resumen(r) for ref, r in series.items()}
    de_buenos = np.array([[f[1]["alr"], f[1]["nuc"]] for ref, f in finales.items() if f and ref in buenos]).reshape(-1, 2)
    normal = lo_normal(de_buenos[:, 0], de_buenos[:, 1])
    print("  lo normal en el centro según el entorno: " + "; ".join(f"{round(100 * a)} % fuera, hasta {round(100 * b)} % dentro" for a, b in zip(*normal)))
    ya = set()
    ruta_candidatos = Path(args.datos) / "candidatos.geojson"
    if ruta_candidatos.exists():                                      # lo que ya está en la lista no es un hallazgo
        for f in json.loads(ruta_candidatos.read_text(encoding="utf-8"))["features"]:
            ya.update(f["properties"].get("refcats") or [])
    ruta_tejados = base / f"tejados-{args.etiqueta}.json"
    tejados = json.loads(ruta_tejados.read_text(encoding="utf-8")) if ruta_tejados.exists() and not args.sin_tejados else {}
    print(f"  tejado visto año a año: {'de ' + str(len(tejados)) + ' edificios' if tejados else 'no hay (se puntúa solo con la vegetación)'}")
    sesion = requests.Session()
    sesion.headers["User-Agent"] = AGENTE

    def ficha(ref: str) -> dict:
        e = universo[ref]
        lon, lat = a_geo(e["x"], e["y"])
        return {"ref": ref, "muni": e["muni"], "catastro": e["estado"], "en_lista": ref in ya, "uso": e["uso"], "anio": e["anio"], "plantas": e.get("plantas"), "area": e["area"],
                "vecinos": e["vecinos"], "lon": round(lon, 6), "lat": round(lat, 6)}

    salida, por_estado = [], defaultdict(list)
    if tejados:
        # Primero, quién está bajo sospecha por el tejado; luego, la maqueta 3D de cada uno, que es la que decide.
        bajo_sospecha = {ref: s for ref, r in series.items() if ref in tejados and (s := sospecha(r, tejados[ref])) is not None}
        for ref in series:
            por_estado[universo[ref]["estado"]].append(bajo_sospecha[ref]["tipo"] if ref in bajo_sospecha else "")
        for estado, tipos in sorted(por_estado.items(), key=lambda kv: str(kv[0])):
            print(f"  Catastro «{estado}»: {len(tipos)} edificios; perdieron el tejado, {tipos.count('perdio')} ({100 * tipos.count('perdio') / len(tipos):.1f} %); "
                  f"nunca se les ve, {tipos.count('nunca')} ({100 * tipos.count('nunca') / len(tipos):.1f} %)")
        nuevos_refs = [ref for ref in bajo_sospecha if universo[ref]["estado"] == "functional" and ref not in ya]
        nuevos_refs.sort(key=lambda ref: (bajo_sospecha[ref]["tipo"] != "perdio", -(bajo_sospecha[ref]["tenia"] - bajo_sospecha[ref]["queda"]), -bajo_sospecha[ref]["veg_ahora"]))
        ruta_alt = base / f"alturas-{args.etiqueta}.json"
        sabidas = json.loads(ruta_alt.read_text(encoding="utf-8")) if ruta_alt.exists() else {}
        faltan = [ref for ref in nuevos_refs if ref not in sabidas][: args.alturas]
        if faltan:
            from malla import ZONAS, Malla, medir as medir_altura
            mallas = {zona: Malla(sesion, zona) for zona in ZONAS}
            a_grados = lambda c: np.column_stack(a_geo(c[:, 0], c[:, 1]))   # noqa: E731
            t0 = time.time()
            for n, ref in enumerate(faltan, 1):
                try:
                    lat = a_geo(universo[ref]["x"], universo[ref]["y"])[1]
                    sabidas[ref] = medir_altura(mallas, shapely.transform(universo[ref]["geom"], a_grados), lat)
                except Exception as e:                                # la maqueta falla a ratos: ese se queda sin comprobar
                    print("  sin altura", ref, repr(e)[:120], flush=True)
                if n % 25 == 0 or n == len(faltan):
                    ruta_alt.write_text(json.dumps(sabidas), encoding="utf-8")
                    print(f"  maqueta 3D: {n}/{len(faltan)}, {time.time() - t0:.0f} s", flush=True)
        sin_maqueta = sum(1 for ref in nuevos_refs if ref not in sabidas)
        print(f"  bajo sospecha y que Catastro da por buenos: {len(nuevos_refs)} ({sum(1 for r in nuevos_refs if bajo_sospecha[r]['tipo'] == 'perdio')} perdieron el tejado); "
              f"sin mirar en la maqueta 3D: {sin_maqueta}")
        for ref in nuevos_refs:
            s = bajo_sospecha[ref]
            if s["tipo"] == "nunca" and ref not in sabidas:           # sin maqueta no se puede decir nada de estos
                continue
            fallo = sentenciar(s, sabidas.get(ref), universo[ref].get("plantas"))
            if fallo:
                salida.append({**ficha(ref), **fallo, **{c: s[c] for c in ("tenia", "queda", "tej", "anios", "veg", "nuc", "alr")}, "altura": sabidas.get(ref)})
        salida.sort(key=lambda s: -s["nota"])
        nuevos = salida
        por_clase = defaultdict(int)
        for s in nuevos:
            por_clase[s["clase"]] += 1
        print("  en limpio: " + ("; ".join(f"{CLASES_POSIBLE[c].lower()}, {n}" for c, n in sorted(por_clase.items(), key=lambda kv: -kv[1])) or "nada"))
    else:
        for ref, r in series.items():
            j = juzgar(r, normal)
            por_estado[universo[ref]["estado"]].append(j["nota"] if j else 0.0)
            if j is not None:
                salida.append({**ficha(ref), **j})
        salida.sort(key=lambda s: -s["nota"])
        nuevos = [s for s in salida if s["catastro"] == "functional" and not s["en_lista"]]
        # Sirve de comprobación: los que Catastro ya da por ruinosos deberían salir marcados mucho más a menudo que los que da por buenos.
        for estado, notas in sorted(por_estado.items(), key=lambda kv: str(kv[0])):
            v = np.array(notas)
            print(f"  Catastro «{estado}»: {len(v)} edificios; con algún motivo, el {100 * float((v > 0).mean()):.1f} %; con nota de 10 o más, el {100 * float((v >= 10).mean()):.1f} %")
    if args.direcciones:
        ruta_dir = base / "direcciones.json"
        conocidas = json.loads(ruta_dir.read_text(encoding="utf-8")) if ruta_dir.exists() else {}
        for s in nuevos[: args.direcciones]:
            if s["ref"] not in conocidas:
                conocidas[s["ref"]] = direccion(sesion, s["ref"])
                time.sleep(0.3)
            s["direccion"] = conocidas[s["ref"]]
        ruta_dir.write_text(json.dumps(conocidas, ensure_ascii=False, indent=0), encoding="utf-8")
    (base / f"posibles-{args.etiqueta}.json").write_text(json.dumps(nuevos, ensure_ascii=False, indent=0), encoding="utf-8")
    (base / f"todos-{args.etiqueta}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(medidas)} edificios medidos; {len(nuevos)} posibles entre los que Catastro da por buenos y no están en la lista")
    for n, s in enumerate(nuevos[: args.cuantos]):
        print(f"  {n + 1:3d} {s['nota']:6.1f} {s['clase']:13s} {s['ref']} {s['uso'] or '-':12s} {s['area']:5d} m2  {s['lat']},{s['lon']}  {s.get('direccion') or ''}  {'; '.join(s['motivos'])}")
    print("FIN-PUNTUAR", flush=True)


def capa(args) -> None:
    """Deja los posibles de una o varias tandas en datos/capa-posibles.geojson, que el visor enseña como una capa más."""
    base = Path(args.carpeta) / "cambios"
    rasgos_geo, vistos = [], set()
    for etiqueta in args.etiqueta.split(","):
        for s in json.loads((base / f"posibles-{etiqueta}.json").read_text(encoding="utf-8")):
            if s["ref"] in vistos or s["nota"] < args.nota_minima or (s["clase"] == "derribado" and not args.con_derribados):
                continue
            vistos.add(s["ref"])
            sitio = (s.get("direccion") or "").split(" (")[0].strip().title()
            por_anio = lambda valores: ", ".join(f"{a}: {round(100 * v)} %" for a, v in zip(s["anios"], valores or []) if v is not None) or None   # noqa: E731
            rasgos_geo.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}, "properties": {
                "id": f"posible/{s['ref']}", "nombre": sitio or f"Edificio {s['uso'] or 'sin uso apuntado'} de {s['area']} m²", "nota": s["nota"],
                "clase": s["clase"], "parece": CLASES_POSIBLE[s["clase"]],
                "motivos": ". ".join(m[0].upper() + m[1:] for m in s["motivos"]) + ".",
                "tejado": por_anio(s.get("tej")), "serie": por_anio(s["nuc"]),
                "direccion": s.get("direccion"), "refcat": s["ref"], "uso": s["uso"], "anio": s["anio"], "superficie": s["area"],
                "url": f"https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCListaBienes.aspx?rc1={s['ref'][:7]}&rc2={s['ref'][7:14]}"}})
    rasgos_geo.sort(key=lambda f: -f["properties"]["nota"])
    salida = Path(args.datos) / "capa-posibles.geojson"
    salida.write_text(json.dumps({"type": "FeatureCollection", "features": rasgos_geo}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rasgos_geo)} posibles en {salida}")
    print("FIN-CAPA", flush=True)


# --------------------------------------------------------------------------
# ¿Hay tejado? El detector entrenado, año a año
# --------------------------------------------------------------------------

LADO_TEJADO = 512                # píxeles de la ventana que se le enseña al detector
PIXEL_TEJADO = 0.15              # metros por píxel con los que aprendió


def ventana_de(e: dict) -> tuple[float, float, float]:
    """Esquina de abajo a la izquierda y metros por píxel de la ventana de un edificio: centrada en él y, si es muy grande, más alejada."""
    bx0, by0, bx1, by1 = e["geom"].bounds
    pixel = max(PIXEL_TEJADO, 1.4 * max(bx1 - bx0, by1 - by0) / LADO_TEJADO)
    return e["x"] - LADO_TEJADO * pixel / 2, e["y"] - LADO_TEJADO * pixel / 2, pixel


def pedir_ventana(sesion: requests.Session, anio: int, capa: str, x0: float, y0: float, pixel: float, copia: Path) -> np.ndarray | None:
    """Una ventana de 512 píxeles de la foto de un año («RGB» o «IRG»), de disco si ya se bajó. None si no hay foto o falla la red."""
    if copia.exists():
        img = cv2.imdecode(np.fromfile(copia, np.uint8), cv2.IMREAD_COLOR)
        return None if img is None or img.std() < 4 else img[:, :, ::-1]
    url, vuelo = servicio(anio)
    lado = LADO_TEJADO * pixel
    for intento in range(3):
        try:
            r = sesion.get(url, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": f"{vuelo}_{capa}", "STYLES": "", "CRS": "EPSG:25830",
                                        "BBOX": f"{x0:.2f},{y0:.2f},{x0 + lado:.2f},{y0 + lado:.2f}", "WIDTH": LADO_TEJADO, "HEIGHT": LADO_TEJADO, "FORMAT": "image/jpeg"}, timeout=60)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    copia.parent.mkdir(parents=True, exist_ok=True)
                    copia.write_bytes(r.content)                       # también las lisas: así no se vuelven a pedir
                    return None if img.std() < 4 else img[:, :, ::-1]
        except requests.RequestException:
            pass
        time.sleep(1 + 3 * intento)
    return None


def mascara_interior(geom, x0: float, y0: float, pixel: float) -> np.ndarray:
    """El interior del contorno en la ventana (sin el metro de borde, que es donde más baila el tejado de un año a otro)."""
    y1 = y0 + LADO_TEJADO * pixel
    mascara = np.zeros((LADO_TEJADO, LADO_TEJADO), np.uint8)
    for parte in shapely.get_parts(geom):
        a_px = lambda coords: np.column_stack([(np.asarray(coords)[:, 0] - x0) / pixel, (y1 - np.asarray(coords)[:, 1]) / pixel]).round().astype(np.int32)   # noqa: E731
        cv2.fillPoly(mascara, [a_px(parte.exterior.coords)], 1)
        for hueco in parte.interiors:
            cv2.fillPoly(mascara, [a_px(hueco.coords)], 0)
    lejos = cv2.distanceTransform(mascara, cv2.DIST_L2, 3) * pixel
    dentro = lejos > min(1.0, 0.3 * float(lejos.max()))
    return dentro if dentro.sum() >= 50 else mascara > 0


def elegir_para_tejados(args, universo: dict[str, dict]) -> list[str]:
    """A quién se le mira el tejado: a los señalados, a los que Catastro da por malos y a una muestra de los demás, que sirve de vara de medir."""
    base = Path(args.carpeta) / "cambios"
    if args.refs:
        return [r for r in args.refs.split(",") if r in universo]
    elegidos = [s["ref"] for s in json.loads((base / f"todos-{args.etiqueta}.json").read_text(encoding="utf-8"))]
    elegidos += [ref for ref, e in universo.items() if e["estado"] in ("ruin", "declined") and ref not in elegidos]
    resto = sorted(ref for ref, e in universo.items() if e["estado"] == "functional" and ref not in set(elegidos))
    azar = np.random.default_rng(1)
    return elegidos + [resto[k] for k in azar.choice(len(resto), min(args.muestra, len(resto)), replace=False)]


def tejados(args) -> None:
    """Pasa el detector entrenado por la ventana de cada edificio en cada año y apunta qué parte de su contorno ve como tejado.

    El detector aprendió con la foto de 2025. Las de otros años salen con otros colores, así que antes se igualan, canal a canal,
    a la de 2025 (misma media y misma dispersión sobre los mismos sitios)."""
    import torch
    import segmentation_models_pytorch as smp
    from detectar import cortes_de
    from preparar import CLASES
    no_dormir()
    base = Path(args.carpeta) / "cambios"
    universo = {e["ref"]: e for e in cargar_universo(args)}
    refs = elegir_para_tejados(args, universo)
    anios = [int(a) for a in args.anios.split(",")]
    fotos = base / "ventanas"
    sesion = requests.Session()
    sesion.headers["User-Agent"] = AGENTE
    sesion.mount("https://", requests.adapters.HTTPAdapter(pool_connections=args.hilos, pool_maxsize=args.hilos))
    print(f"{len(refs)} edificios; {len(anios)} años; hasta {2 * len(refs) * len(anios)} fotos por bajar", flush=True)

    def bajar(ref: str, anio: int):
        x0, y0, pixel = ventana_de(universo[ref])
        rgb = pedir_ventana(sesion, anio, "RGB", x0, y0, pixel, fotos / ref / f"{anio}_rgb.jpg")
        irg = pedir_ventana(sesion, anio, "IRG", x0, y0, pixel, fotos / ref / f"{anio}_irg.jpg") if rgb is not None else None
        return None if irg is None else np.dstack([rgb, irg[:, :, 0]])

    t0 = time.time()
    with ThreadPoolExecutor(args.hilos) as hilos:
        cubos = dict(zip([(r, a) for r in refs for a in anios], hilos.map(lambda ra: bajar(*ra), [(r, a) for r in refs for a in anios])))
    cubos = {k: v for k, v in cubos.items() if v is not None}
    print(f"fotos listas: {len(cubos)} ventanas en {time.time() - t0:.0f} s", flush=True)

    # Igualar los colores de cada año a los de 2025, con los sitios que tienen foto en los dos.
    patron = max(anios)
    ajuste = {}
    for anio in anios:
        comunes = [r for r in refs if (r, anio) in cubos and (r, patron) in cubos][:400]
        if anio == patron or len(comunes) < 5:
            ajuste[anio] = (np.ones(4, np.float32), np.zeros(4, np.float32))
            continue
        suyo = np.concatenate([cubos[(r, anio)][::4, ::4].reshape(-1, 4) for r in comunes]).astype(np.float32)
        bueno = np.concatenate([cubos[(r, patron)][::4, ::4].reshape(-1, 4) for r in comunes]).astype(np.float32)
        gana = bueno.std(0) / np.maximum(suyo.std(0), 1e-3)
        ajuste[anio] = (gana, bueno.mean(0) - gana * suyo.mean(0))

    guardado = torch.load(Path(args.carpeta) / "modelos" / f"{args.modelo}.pt", map_location="cpu", weights_only=False)
    dispositivo = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    modelo = smp.Unet("resnet34", encoder_weights=None, in_channels=4, classes=len(CLASES))
    modelo.load_state_dict(guardado["modelo"])
    modelo.to(dispositivo).eval()
    media, desv = np.array(guardado["media"], np.float32), np.array(guardado["desv"], np.float32)
    corte = cortes_de(Path(args.carpeta), args.modelo)["edificio"]
    canal = CLASES.index("edificio")
    salida: dict[str, dict] = defaultdict(dict)
    claves = sorted(cubos)
    t0 = time.time()
    with torch.no_grad(), torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
        for k in range(0, len(claves), 16):
            lote = claves[k:k + 16]
            x = np.stack([(np.clip(cubos[c].astype(np.float32) * ajuste[c[1]][0] + ajuste[c[1]][1], 0, 255) / 255 - media) / desv for c in lote])
            prob = torch.sigmoid(modelo(torch.from_numpy(np.ascontiguousarray(x.transpose(0, 3, 1, 2))).to(dispositivo)))[:, canal].float().cpu().numpy()
            for (ref, anio), p in zip(lote, prob):
                x0, y0, pixel = ventana_de(universo[ref])
                dentro = mascara_interior(universo[ref]["geom"], x0, y0, pixel)
                salida[ref][str(anio)] = round(float((p[dentro] > corte).mean()), 3)
    (base / f"tejados-{args.etiqueta}.json").write_text(json.dumps(salida, separators=(",", ":")), encoding="utf-8")
    print(f"tejado mirado en {len(salida)} edificios ({len(claves)} ventanas) en {time.time() - t0:.0f} s con {dispositivo}", flush=True)
    for ref in refs[: args.cuantos]:
        if ref in salida:
            print(f"  {ref} {universo[ref]['estado'] or '-':10s} " + " ".join(f"{salida[ref].get(str(a), float('nan')):4.2f}" for a in anios), flush=True)
    print("FIN-TEJADOS", flush=True)


# --------------------------------------------------------------------------
# Hojas para mirar a ojo
# --------------------------------------------------------------------------

def hojas(args) -> None:
    """Cada fila es un edificio; cada columna, un año. El contorno de Catastro va en magenta."""
    base = Path(args.carpeta) / "cambios"
    posibles = json.loads((base / f"{args.lista}-{args.etiqueta}.json").read_text(encoding="utf-8"))
    universo = {e["ref"]: e for e in cargar_universo(args)}
    for ref in (args.refs.split(",") if args.refs else []):           # pedidos a mano que no están en la lista: se enseñan igual
        if ref in universo and all(p["ref"] != ref for p in posibles):
            e = universo[ref]
            lon, lat = a_geo(e["x"], e["y"])
            posibles.append({"ref": ref, "nota": 0, "uso": e["uso"], "area": e["area"], "lat": round(lat, 6), "lon": round(lon, 6), "motivos": [f"sin motivo; Catastro: {e['estado']}"]})
    if args.refs:
        quiero = args.refs.split(",")
        posibles = sorted((p for p in posibles if p["ref"] in quiero), key=lambda p: quiero.index(p["ref"]))
    anios = [int(a) for a in args.anios_hoja.split(",")]
    sesion = requests.Session()
    sesion.headers["User-Agent"] = AGENTE
    px = 256
    destino = Path(args.carpeta) / "ver"
    destino.mkdir(exist_ok=True)

    def recorte(anio: int, cx: float, cy: float, lado_m: float) -> np.ndarray:
        url, vuelo = servicio(anio)
        try:
            r = sesion.get(url, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": f"{vuelo}_RGB", "STYLES": "", "CRS": "EPSG:25830",
                                        "BBOX": f"{cx - lado_m / 2:.2f},{cy - lado_m / 2:.2f},{cx + lado_m / 2:.2f},{cy + lado_m / 2:.2f}", "WIDTH": px, "HEIGHT": px, "FORMAT": "image/jpeg"}, timeout=60)
            img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
            return img if img is not None else np.zeros((px, px, 3), np.uint8)
        except requests.RequestException:
            return np.zeros((px, px, 3), np.uint8)

    elegidos = posibles[args.desde: args.desde + args.cuantos]
    for n in range(0, len(elegidos), args.filas):
        filas = []
        for p in elegidos[n:n + args.filas]:
            e = universo[p["ref"]]
            bx0, by0, bx1, by1 = e["geom"].bounds
            lado_m = float(min(max(48.0, 2.2 * max(bx1 - bx0, by1 - by0)), 200.0))
            with ThreadPoolExecutor(len(anios)) as hilos:
                fotos = list(hilos.map(lambda a: recorte(a, e["x"], e["y"], lado_m), anios))
            for a, foto in zip(anios, fotos):
                for parte in shapely.get_parts(e["geom"]):
                    xy = np.asarray(parte.exterior.coords)
                    puntos = np.column_stack([(xy[:, 0] - (e["x"] - lado_m / 2)) / lado_m * px, ((e["y"] + lado_m / 2) - xy[:, 1]) / lado_m * px]).round().astype(np.int32)
                    cv2.polylines(foto, [puntos], True, (125, 0, 229), 1, cv2.LINE_AA)
                cv2.putText(foto, str(a), (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
            fila = np.hstack(fotos)
            rotulo = np.zeros((34, fila.shape[1], 3), np.uint8)
            cv2.putText(rotulo, f"{args.desde + len(filas) // 2 + n + 1}. {p['ref']}  nota {p['nota']}  {p['uso'] or ''} {p['area']} m2  {p['lat']},{p['lon']}  ({round(lado_m)} m)", (4, 13),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1, cv2.LINE_AA)
            sin_tildes = " | ".join(x for x in (p.get("direccion"), "; ".join(p["motivos"])) if x).translate(str.maketrans("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN")).encode("ascii", "replace").decode()
            cv2.putText(rotulo, sin_tildes[:175], (4, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            filas += [rotulo, fila]
        salida = destino / f"cambios-{args.etiqueta}-{args.nombre or args.lista}-{args.desde + n + 1:03d}.jpg"
        cv2.imencode(".jpg", np.vstack(filas), [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(salida)
        print(" ", salida, flush=True)
    print("FIN-HOJAS", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Posibles abandonos comparando las fotos de varios años.")
    ap.add_argument("paso_a_dar", choices=("medir", "puntuar", "tejados", "hojas", "capa"))
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--catastro", default="cache/catastro"); ap.add_argument("--datos", default="datos")
    ap.add_argument("--municipios", default="", help="códigos de Catastro separados por comas (vacío: toda la provincia)")
    ap.add_argument("--etiqueta", default="piloto", help="nombre de esta tanda: va en los ficheros que se escriben")
    ap.add_argument("--anios", default=",".join(str(a) for a in ANIOS)); ap.add_argument("--hilos", type=int, default=12)
    ap.add_argument("--paso", type=float, default=0.5, help="metros por píxel al medir")
    ap.add_argument("--min-superficie", type=float, default=60.0, help="superficie mínima del contorno, en m²")
    ap.add_argument("--max-vecinos", type=int, default=12, help="con más edificios que estos a 150 m se considera casco urbano")
    ap.add_argument("--todos", action="store_true", help="también los de casco urbano")
    ap.add_argument("--guardar-fotos", action="store_true", help="guarda los recortes (solo para zonas de prueba: ocupan)")
    ap.add_argument("--rehacer", action="store_true", help="vuelve a medir todo (si hay fotos guardadas, sin bajarlas otra vez)")
    ap.add_argument("--direcciones", type=int, default=0, help="pide a Catastro la dirección de los primeros N")
    ap.add_argument("--nota-minima", type=float, default=12.0, help="capa: nota a partir de la cual un posible entra en el mapa")
    ap.add_argument("--con-derribados", action="store_true", help="capa: incluir también los que la maqueta 3D da por derribados")
    ap.add_argument("--modelo", default="lineas-v1", help="tejados: el detector entrenado que se usa")
    ap.add_argument("--muestra", type=int, default=150, help="tejados: cuántos edificios corrientes mirar además, como referencia")
    ap.add_argument("--cpu", action="store_true", help="tejados: sin tarjeta gráfica")
    ap.add_argument("--sin-tejados", action="store_true", help="puntuar: no usar lo que haya dejado tejado.py")
    ap.add_argument("--alturas", type=int, default=300, help="puntuar: cuántos edificios bajo sospecha, como mucho, se miran de nuevas en la maqueta 3D de 2025")
    ap.add_argument("--cuantos", type=int, default=40); ap.add_argument("--desde", type=int, default=0); ap.add_argument("--filas", type=int, default=6)
    ap.add_argument("--lista", default="posibles", choices=("posibles", "todos")); ap.add_argument("--anios-hoja", default="2017,2019,2021,2023,2025"); ap.add_argument("--refs", default=""); ap.add_argument("--nombre", default="", help="nombre de las hojas")
    args = ap.parse_args()
    {"medir": medir, "puntuar": puntuar, "tejados": tejados, "hojas": hojas, "capa": capa}[args.paso_a_dar](args)


if __name__ == "__main__":
    main()
