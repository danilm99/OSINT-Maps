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


def fuera_de_casco(ref: str) -> bool:
    """Por la referencia: parcela rústica (46137A00500001) o «diseminado» (empieza por 00)."""
    return bool(re.match(r"^\d{5}[A-Z]\d{8}", ref)) or ref.startswith("00")


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
    nombre = base / f"universo-{'-'.join(municipios) or 'todo'}-{int(args.min_superficie)}{'-todos' if args.todos else f'-v{args.max_vecinos}'}.json"
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
        centros = np.array([[e["geom"].centroid.x, e["geom"].centroid.y] for e in edificios])
        cerca = vecinos(centros)
        for e, (cx, cy), n in zip(edificios, centros, cerca):
            if e["geom"].area < args.min_superficie:
                continue
            # Fuera de casco: en suelo rústico o diseminado, o con pocos vecinos (bordes de pueblo, naves sueltas).
            if args.todos or fuera_de_casco(e["ref"]) or n <= args.max_vecinos:
                universo.append({"ref": e["ref"], "muni": ruta.stem, "estado": e["estado"], "uso": e["uso"], "anio": e["anio"], "sup": e["sup"], "area": round(e["geom"].area),
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
    # respecto al contorno, distinto cada año. Cuanto mayor el edificio, más margen se le quita (de 0,5 a 2 m).
    quitar = min(2.0, max(0.5, 0.15 * math.sqrt(geom.area)))
    dentro = mascara
    for metros in (quitar, 0.5):
        lado = 2 * int(round(metros / paso)) + 1
        dentro = cv2.erode(mascara, np.ones((lado, lado), np.uint8)) if lado > 1 else mascara
        if dentro.sum() * paso * paso >= 10:
            break
    d = dentro > 0
    n = int(d.sum())
    if n * paso * paso < 10:
        return None
    trozo = irg[f0:f1, c0:c1].astype(np.float32) / 255
    if float(trozo[d].std()) < 0.004:                                 # liso del todo: borde de la foto de ese año
        return None
    nir, rojo, verde = trozo[..., 0], trozo[..., 1], trozo[..., 2]
    ndvi = (nir - rojo) / (nir + rojo + 1e-6)
    brillo = (rojo + verde) / 2
    grad = np.hypot(cv2.Sobel(brillo, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(brillo, cv2.CV_32F, 0, 1, ksize=3))

    def reparto(valores: np.ndarray) -> list[int]:
        return np.bincount(np.clip(((valores - NDVI_MIN) / NDVI_ANCHO).astype(np.int32), 0, N_NDVI - 1), minlength=N_NDVI).tolist()

    # El centro del edificio aparte: las copas de los árboles de al lado tapan los bordes, no el centro.
    lejos = cv2.distanceTransform(mascara, cv2.DIST_L2, 3)
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


def juzgar(r: dict[str, np.ndarray]) -> dict | None:
    """De la serie de un edificio a una nota de «va a menos» y el porqué. None si no hay nada que decir."""
    n = len(r["anios"])
    if n < 3:
        return None
    k = 3 if n >= 7 else 2 if n >= 4 else 1                           # principio y final: la mediana de varios años, que una foto rara no decida
    antes = {c: float(np.median(v[:k])) for c, v in r.items() if c != "anios"}
    ahora = {c: float(np.median(v[-k:])) for c, v in r.items() if c != "anios"}
    sube = {c: ahora[c] - antes[c] for c in antes}
    pct = lambda v: f"{round(100 * v)} %"                             # noqa: E731
    motivos, nota = [], 0.0
    if antes["nuc"] <= 0.15 and sube["nuc"] >= 0.12 and sube["veg"] >= 0.08:
        nota += 120 * sube["nuc"] + 40 * sube["veg"]
        motivos.append(f"le crece vegetación dentro: del {pct(antes['nuc'])} al {pct(ahora['nuc'])} en el centro")
    elif antes["veg"] <= 0.2 and sube["veg"] >= 0.15:
        nota += 50 * sube["veg"]
        motivos.append(f"la vegetación le gana terreno por los bordes: del {pct(antes['veg'])} al {pct(ahora['veg'])}")
    if sube["osc"] >= 0.15 and sube["rug"] >= 1.0:
        nota += 60 * sube["osc"] + 4 * min(sube["rug"], 5)
        motivos.append(f"la cubierta se ve más rota y con más sombra: del {pct(antes['osc'])} al {pct(ahora['osc'])} en sombra")
    if float(r["nuc"].min()) >= 0.3:
        nota += 30 * float(r["nuc"].mean())
        motivos.append(f"vegetación dentro todos los años (entre el {pct(r['nuc'].min())} y el {pct(r['nuc'].max())} del centro)")
    if not motivos:
        return None
    return {"nota": round(nota, 1), "motivos": motivos, "anios": r["anios"].tolist(), **{c: [round(float(x), 2) for x in r[c]] for c in ("veg", "nuc", "alr", "osc", "rug")}}


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
    ya = set()
    ruta_candidatos = Path(args.datos) / "candidatos.geojson"
    if ruta_candidatos.exists():                                      # lo que ya está en la lista no es un hallazgo
        for f in json.loads(ruta_candidatos.read_text(encoding="utf-8"))["features"]:
            ya.update(f["properties"].get("refcats") or [])
    salida, por_estado = [], defaultdict(list)
    for ref, serie in medidas.items():
        e = universo.get(ref)
        if e is None:
            continue
        j = juzgar(rasgos(serie, cal))
        por_estado[e["estado"]].append(j["nota"] if j else 0.0)
        if j is None:
            continue
        lon, lat = a_geo(e["x"], e["y"])
        salida.append({"ref": ref, "muni": e["muni"], "catastro": e["estado"], "en_lista": ref in ya, "uso": e["uso"], "anio": e["anio"], "area": e["area"], "vecinos": e["vecinos"],
                       "lon": round(lon, 6), "lat": round(lat, 6), **j})
    salida.sort(key=lambda s: -s["nota"])
    nuevos = [s for s in salida if s["catastro"] == "functional" and not s["en_lista"]]
    if args.direcciones:
        sesion = requests.Session()
        sesion.headers["User-Agent"] = AGENTE
        ruta_dir = base / "direcciones.json"
        sabidas = json.loads(ruta_dir.read_text(encoding="utf-8")) if ruta_dir.exists() else {}
        for s in nuevos[: args.direcciones]:
            if s["ref"] not in sabidas:
                sabidas[s["ref"]] = direccion(sesion, s["ref"])
                time.sleep(0.3)
            s["direccion"] = sabidas[s["ref"]]
        ruta_dir.write_text(json.dumps(sabidas, ensure_ascii=False, indent=0), encoding="utf-8")
    (base / f"posibles-{args.etiqueta}.json").write_text(json.dumps(nuevos, ensure_ascii=False, indent=0), encoding="utf-8")
    (base / f"todos-{args.etiqueta}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(medidas)} edificios medidos; {len(salida)} con algún motivo; {len(nuevos)} de ellos, edificios que Catastro da por buenos y no están en la lista")
    # Sirve de comprobación: los que Catastro ya da por ruinosos deberían sacar más nota que los que da por buenos.
    for estado, notas in sorted(por_estado.items(), key=lambda kv: str(kv[0])):
        v = np.array(notas)
        print(f"  Catastro «{estado}»: {len(v)} edificios; con algún motivo, el {100 * float((v > 0).mean()):.1f} %; con nota de 10 o más, el {100 * float((v >= 10).mean()):.1f} %")
    for s in nuevos[: args.cuantos]:
        print(f"  {s['nota']:6.1f} {s['ref']} {s['uso'] or '-':12s} {s['area']:5d} m2  {s['lat']},{s['lon']}  {s.get('direccion') or ''}  {'; '.join(s['motivos'])}")
    print("FIN-PUNTUAR", flush=True)


# --------------------------------------------------------------------------
# Hojas para mirar a ojo
# --------------------------------------------------------------------------

def hojas(args) -> None:
    """Cada fila es un edificio; cada columna, un año. El contorno de Catastro va en magenta."""
    base = Path(args.carpeta) / "cambios"
    posibles = json.loads((base / f"{args.lista}-{args.etiqueta}.json").read_text(encoding="utf-8"))
    if args.refs:
        quiero = args.refs.split(",")
        posibles = [p for p in posibles if p["ref"] in quiero]
    universo = {e["ref"]: e for e in cargar_universo(args)}
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
            sin_tildes = "; ".join(p["motivos"]).translate(str.maketrans("áéíóúñ", "aeioun")).encode("ascii", "replace").decode()
            cv2.putText(rotulo, sin_tildes[:175], (4, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            filas += [rotulo, fila]
        salida = destino / f"cambios-{args.etiqueta}-{args.lista}-{args.desde + n + 1:03d}.jpg"
        cv2.imencode(".jpg", np.vstack(filas), [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(salida)
        print(" ", salida, flush=True)
    print("FIN-HOJAS", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Posibles abandonos comparando las fotos de varios años.")
    ap.add_argument("paso_a_dar", choices=("medir", "puntuar", "hojas"))
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--catastro", default="cache/catastro"); ap.add_argument("--datos", default="datos")
    ap.add_argument("--municipios", default="", help="códigos de Catastro separados por comas (vacío: toda la provincia)")
    ap.add_argument("--etiqueta", default="piloto", help="nombre de esta tanda: va en los ficheros que se escriben")
    ap.add_argument("--anios", default=",".join(str(a) for a in ANIOS)); ap.add_argument("--hilos", type=int, default=12)
    ap.add_argument("--paso", type=float, default=0.5, help="metros por píxel al medir")
    ap.add_argument("--min-superficie", type=float, default=60.0, help="superficie mínima del contorno, en m²")
    ap.add_argument("--max-vecinos", type=int, default=12, help="con más edificios que estos a 150 m se considera casco urbano")
    ap.add_argument("--todos", action="store_true", help="también los de casco urbano")
    ap.add_argument("--guardar-fotos", action="store_true", help="guarda los recortes (solo para zonas de prueba: ocupan)")
    ap.add_argument("--direcciones", type=int, default=0, help="pide a Catastro la dirección de los primeros N")
    ap.add_argument("--cuantos", type=int, default=40); ap.add_argument("--desde", type=int, default=0); ap.add_argument("--filas", type=int, default=6)
    ap.add_argument("--lista", default="posibles", choices=("posibles", "todos")); ap.add_argument("--anios-hoja", default="2017,2019,2021,2023,2025"); ap.add_argument("--refs", default="")
    args = ap.parse_args()
    {"medir": medir, "puntuar": puntuar, "hojas": hojas}[args.paso_a_dar](args)


if __name__ == "__main__":
    main()
