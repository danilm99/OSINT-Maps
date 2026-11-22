"""Prepara el material para enseñar a un modelo a ver caminos, sendas, muros y vallas en la foto aérea.

La idea: OpenStreetMap ya tiene dibujados miles de caminos, muros y vallas de la provincia. Si se
recorta la foto aérea donde están y se pinta encima lo que OSM dice que hay, sale un cuaderno de
ejemplos («aquí hay una valla, aquí un camino») con el que un modelo aprende a reconocerlos en
sitios donde nadie los ha dibujado.

Pasos (cada uno se salta si ya está hecho):
  1. Bajar el extracto de OSM de la Comunitat Valenciana (Geofabrik, unos 130 MB).
  2. Leerlo y quedarse con lo que interesa, clasificado (`rasgos.npz`).
  3. Elegir teselas de 77 m de lado (512 píxeles a 15 cm) repartidas por clases (`teselas.json`).
  4. Bajar de cada una la foto en color y en infrarrojo (WMS del ICV, vuelo de 2025).
  5. Pintar para cada una la «etiqueta»: una imagen donde cada bit de cada píxel dice si ahí hay
     camino, senda, carretera, muro, valla, seto, acequia o edificio.

    python experimentos/vision/preparar.py --carpeta cache/_vision --datos datos --teselas 4000
"""
from __future__ import annotations

import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import requests
import shapely
from pyproj import Transformer

CLASES = ["camino", "senda", "carretera", "muro", "valla", "seto", "acequia", "edificio"]
ANCHO_M = {"camino": 3.0, "senda": 1.2, "carretera": 6.0, "muro": 0.9, "valla": 0.9, "seto": 1.5, "acequia": 1.5}
PIXEL, LADO = 0.15, 512                      # metros por píxel y píxeles de lado de cada tesela
TESELA_M = PIXEL * LADO
IMAGEN = "0202_2025PVAL0015"                 # la foto con la que se trabaja: si el ICV publica otra, cambia aquí
WMS = f"https://terramapas.icv.gva.es/{IMAGEN}"
CAPAS = {"rgb": "2025PVAL0015_RGB", "irg": "2025PVAL0015_IRG"}
PROVINCIA = (-1.5636, 38.6653, 0.0193, 40.2303)            # oeste, sur, este, norte
GEOFABRIK = "https://download.geofabrik.de/europe/spain/valencia-latest.osm.pbf"
SIN_ASFALTAR = {"unpaved", "ground", "dirt", "earth", "gravel", "fine_gravel", "compacted", "grass", "sand", "mud", "pebblestone"}
CARRETERAS = {"motorway": 12, "trunk": 12, "primary": 9, "secondary": 9, "tertiary": 7, "unclassified": 6, "residential": 6, "living_street": 5,
              "service": 4, "motorway_link": 7, "trunk_link": 7, "primary_link": 7, "secondary_link": 6, "tertiary_link": 6, "pedestrian": 5}


def no_dormir() -> None:
    """Pide a Windows que no suspenda el equipo mientras dure este proceso (no cambia ningún ajuste)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except Exception:                    # fuera de Windows no hace falta
        pass


def clase_de(t) -> tuple[str, float] | None:
    """Qué es una vía de OSM para este trabajo, y qué ancho pintarle (metros). None si no interesa."""
    if t.get("tunnel") in ("yes", "culvert", "building_passage") or t.get("covered") == "yes":
        return None                                                    # bajo tierra o bajo techo: no se ve
    b, h, w = t.get("barrier"), t.get("highway"), t.get("waterway")
    if b in ("wall", "retaining_wall", "city_wall"):
        return "muro", ANCHO_M["muro"]
    if b in ("fence", "wire_fence", "chain"):
        return "valla", ANCHO_M["valla"]
    if b == "hedge":
        return "seto", ANCHO_M["seto"]
    if h == "track" or (h in ("service", "unclassified") and t.get("surface") in SIN_ASFALTAR):
        return "camino", ANCHO_M["camino"]
    if h in ("path", "bridleway") or (h == "footway" and t.get("surface") in SIN_ASFALTAR):
        return "senda", ANCHO_M["senda"]
    if h in CARRETERAS:
        return "carretera", float(CARRETERAS[h])
    if w in ("ditch", "drain", "canal", "stream"):
        return "acequia", ANCHO_M["acequia"]
    if "building" in t and t.get("building") != "no":
        return "edificio", 0.0
    return None


def leer_osm(pbf: Path) -> dict:
    """Recorre el extracto y devuelve las vías que interesan, ya en metros (UTM 30)."""
    import osmium
    oeste, sur, este, norte = PROVINCIA
    clases, anchos, cuentas, lon, lat = [], [], [], [], []
    # Hay que leer también los nodos (son los que llevan las coordenadas); el filtro deja pasar solo lo etiquetado con esas claves.
    lector = osmium.FileProcessor(str(pbf)).with_locations().with_filter(osmium.filter.KeyFilter("barrier", "highway", "waterway", "building"))
    for via in lector:
        if not via.is_way():
            continue
        que = clase_de(via.tags)
        if que is None:
            continue
        puntos = [(n.lon, n.lat) for n in via.nodes if n.location.valid()]
        if len(puntos) < (4 if que[0] == "edificio" else 2) or not (oeste <= puntos[0][0] <= este and sur <= puntos[0][1] <= norte):
            continue
        if que[0] == "edificio" and puntos[0] != puntos[-1]:
            continue
        clases.append(CLASES.index(que[0])); anchos.append(que[1]); cuentas.append(len(puntos))
        lon.extend(p[0] for p in puntos); lat.extend(p[1] for p in puntos)
    x, y = Transformer.from_crs(4326, 25830, always_xy=True).transform(np.array(lon), np.array(lat))
    return {"clase": np.array(clases, np.uint8), "ancho": np.array(anchos, np.float32), "cuenta": np.array(cuentas, np.int32), "xy": np.column_stack([x, y])}


def elegir_teselas(rasgos: dict, cuantas: int, candidatos: Path | None, semilla: int = 7, parte_sitios: float = 0.1) -> list[tuple[int, int]]:
    """Reparte las teselas por clases: se cae sobre un punto de una vía de esa clase, elegida al azar."""
    azar = random.Random(semilla)
    reparto = {"valla": 0.27, "muro": 0.27, "senda": 0.14, "camino": 0.14, "seto": 0.04, "acequia": 0.04}
    inicio = np.concatenate([[0], np.cumsum(rasgos["cuenta"])[:-1]])
    elegidas: set[tuple[int, int]] = set()
    for nombre, parte in reparto.items():
        de_clase = np.flatnonzero(rasgos["clase"] == CLASES.index(nombre))
        if not len(de_clase):
            continue
        quiero, intentos = int(cuantas * parte), 0
        antes = len(elegidas)
        while len(elegidas) - antes < quiero and intentos < quiero * 20:
            intentos += 1
            k = int(de_clase[azar.randrange(len(de_clase))])
            x, y = rasgos["xy"][inicio[k] + azar.randrange(int(rasgos["cuenta"][k]))]
            elegidas.add((int(x // TESELA_M), int(y // TESELA_M)))
    if candidatos and candidatos.exists():          # y alrededor de los sitios del mapa, que es donde se va a usar
        sitios = json.loads(candidatos.read_text(encoding="utf-8"))["features"]
        azar.shuffle(sitios)
        a_utm = Transformer.from_crs(4326, 25830, always_xy=True).transform
        for s in sitios[: int(cuantas * parte_sitios)]:
            x, y = a_utm(*s["geometry"]["coordinates"][:2])
            elegidas.add((int(x // TESELA_M) + azar.choice((-1, 0, 1)), int(y // TESELA_M) + azar.choice((-1, 0, 1))))
    return sorted(elegidas)


def bajar(sesion: requests.Session, carpeta: Path, i: int, j: int) -> str:
    """Las dos fotos de una tesela. Devuelve «ya», «ok», «vacía» (fuera de la foto) o «fallo»."""
    caja = f"{i * TESELA_M:.2f},{j * TESELA_M:.2f},{(i + 1) * TESELA_M:.2f},{(j + 1) * TESELA_M:.2f}"
    destinos = {k: carpeta / f"{i}_{j}_{k}.jpg" for k in CAPAS}
    if (carpeta / f"{i}_{j}.vacia").exists():
        return "vacía"
    if all(d.exists() for d in destinos.values()):
        return "ya"
    for k, capa in CAPAS.items():
        if destinos[k].exists():
            continue
        for intento in range(3):
            try:
                r = sesion.get(WMS, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": capa, "STYLES": "", "CRS": "EPSG:25830",
                                            "BBOX": caja, "WIDTH": LADO, "HEIGHT": LADO, "FORMAT": "image/jpeg"}, timeout=60)
                if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                    break
            except requests.RequestException:
                pass
            time.sleep(2 + 3 * intento)
        else:
            return "fallo"
        if k == "rgb":
            img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None or img.std() < 4:                         # todo de un color: fuera de la foto
                (carpeta / f"{i}_{j}.vacia").write_bytes(b"")
                return "vacía"
        destinos[k].write_bytes(r.content)
    return "ok"


def pintar_etiquetas(rasgos: dict, teselas: list[tuple[int, int]], carpeta: Path) -> int:
    """Una imagen por tesela: el bit n de cada píxel dice si ahí hay algo de la clase n."""
    inicio = np.concatenate([[0], np.cumsum(rasgos["cuenta"])[:-1]])
    mias = set(teselas)
    por_tesela: dict[tuple[int, int], list[int]] = {}
    margen = 8.0
    for k in range(len(rasgos["clase"])):                   # a qué teselas elegidas toca cada vía (por su caja)
        p = rasgos["xy"][inicio[k]: inicio[k] + rasgos["cuenta"][k]]
        i0, i1 = int((p[:, 0].min() - margen) // TESELA_M), int((p[:, 0].max() + margen) // TESELA_M)
        j0, j1 = int((p[:, 1].min() - margen) // TESELA_M), int((p[:, 1].max() + margen) // TESELA_M)
        if (i1 - i0 + 1) * (j1 - j0 + 1) > 4000:
            continue                                         # algo larguísimo y mal cerrado: fuera
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                if (i, j) in mias:
                    por_tesela.setdefault((i, j), []).append(k)
    hechas = 0
    for (i, j) in teselas:
        destino = carpeta / f"{i}_{j}.png"
        if destino.exists():
            continue
        x0, y1 = i * TESELA_M, (j + 1) * TESELA_M
        planos = np.zeros((len(CLASES), LADO, LADO), np.uint8)
        for k in por_tesela.get((i, j), []):
            p = rasgos["xy"][inicio[k]: inicio[k] + rasgos["cuenta"][k]]
            # Recortar a la tesela (con margen) evita coordenadas enormes, que OpenCV no sabe pintar.
            geo = shapely.Polygon(p) if rasgos["clase"][k] == CLASES.index("edificio") else shapely.LineString(p)
            geo = shapely.clip_by_rect(geo, x0 - 20, y1 - TESELA_M - 20, x0 + TESELA_M + 20, y1 + 20)
            for parte in shapely.get_parts(geo):
                if parte.is_empty:
                    continue
                c = np.array(parte.exterior.coords if parte.geom_type == "Polygon" else parte.coords)
                px = np.column_stack([(c[:, 0] - x0) / PIXEL, (y1 - c[:, 1]) / PIXEL]).round().astype(np.int32)
                if parte.geom_type == "Polygon":
                    cv2.fillPoly(planos[rasgos["clase"][k]], [px], 1)
                elif len(px) >= 2:
                    cv2.polylines(planos[rasgos["clase"][k]], [px], False, 1, max(2, int(round(rasgos["ancho"][k] / PIXEL))))
        bits = np.zeros((LADO, LADO), np.uint8)
        for n in range(len(CLASES)):
            bits |= (planos[n] << n)
        cv2.imwrite(str(destino), bits)
        hechas += 1
    return hechas


def main() -> None:
    ap = argparse.ArgumentParser(description="Prepara teselas y etiquetas para entrenar el detector de caminos, muros y vallas.")
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--datos", default="datos")
    ap.add_argument("--teselas", type=int, default=4000); ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--pbf", default="", help="extracto de OSM ya bajado (si no, se baja de Geofabrik)")
    ap.add_argument("--ampliar", type=int, default=0, help="añadir unas N teselas más a las ya elegidas")
    ap.add_argument("--semilla", type=int, default=11, help="con --ampliar: otra semilla da otras teselas")
    ap.add_argument("--parte-sitios", type=float, default=0.1, help="con --ampliar: qué parte cae junto a los sitios del mapa")
    args = ap.parse_args()
    no_dormir()
    base = Path(args.carpeta)
    for sub in ("osm", "teselas", "etiquetas"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    sesion = requests.Session()
    sesion.headers["User-Agent"] = "osintmaps (uso personal; entrenamiento de un detector de caminos y vallas)"

    pbf = Path(args.pbf) if args.pbf else base / "osm" / "valencia-latest.osm.pbf"
    if not pbf.exists():
        print("1/5 Bajando el extracto de OSM…", flush=True)
        with sesion.get(GEOFABRIK, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(pbf.with_suffix(".parte"), "wb") as f:
                for trozo in r.iter_content(1 << 20):
                    f.write(trozo)
        pbf.with_suffix(".parte").rename(pbf)
    fichero = base / "osm" / "rasgos.npz"
    if not fichero.exists():
        print("2/5 Leyendo OSM…", flush=True)
        np.savez_compressed(fichero, **leer_osm(pbf))
    rasgos = dict(np.load(fichero))
    print("   vías por clase:", {c: int((rasgos["clase"] == n).sum()) for n, c in enumerate(CLASES)}, flush=True)

    lista = base / "teselas.json"
    if not lista.exists():
        lista.write_text(json.dumps(elegir_teselas(rasgos, args.teselas, Path(args.datos) / "candidatos.geojson")), encoding="utf-8")
    teselas = [tuple(t) for t in json.loads(lista.read_text(encoding="utf-8"))]
    if args.ampliar:
        # El recuadro de la provincia coge trozos de Alicante y Castellón que esta foto no cubre: una de cada
        # cuatro teselas de la primera tanda salió en blanco. En vez de afinar el recuadro, se piden más.
        ya = set(teselas)
        nuevas = [t for t in elegir_teselas(rasgos, args.ampliar, Path(args.datos) / "candidatos.geojson", args.semilla, args.parte_sitios) if t not in ya]
        teselas += nuevas
        lista.write_text(json.dumps(teselas), encoding="utf-8")
        print(f"   ampliación: {len(nuevas)} teselas nuevas", flush=True)
    print(f"3/5 {len(teselas)} teselas elegidas", flush=True)

    cuenta = {"ya": 0, "ok": 0, "vacía": 0, "fallo": 0}
    t0 = time.time()
    with ThreadPoolExecutor(args.hilos) as hilos:
        for n, estado in enumerate(hilos.map(lambda t: bajar(sesion, base / "teselas", *t), teselas), 1):
            cuenta[estado] += 1
            if n % 250 == 0:
                print(f"4/5 fotos: {n}/{len(teselas)} {cuenta} ({time.time() - t0:.0f} s)", flush=True)
    print(f"4/5 fotos: {cuenta}", flush=True)
    buenas = [t for t in teselas if (base / "teselas" / f"{t[0]}_{t[1]}_irg.jpg").exists()]
    print(f"5/5 etiquetas nuevas: {pintar_etiquetas(rasgos, buenas, base / 'etiquetas')} de {len(buenas)} teselas con foto", flush=True)
    print("FIN-PREPARAR", flush=True)


if __name__ == "__main__":
    main()
