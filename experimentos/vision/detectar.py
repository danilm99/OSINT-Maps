"""Pasa el modelo por los alrededores de cada candidato y guarda lo que ve.

Para cada sitio (por nota, de mayor a menor) se baja una ventana de 307 m de lado de la foto de
15 cm (color e infrarrojo), se pasa el modelo de `entrenar.py` y se guarda un JSON con:
- las líneas que ve (camino, senda, muro, valla, seto), ya como coordenadas;
- cuánto de cada cosa hay, cuántos accesos llegan al edificio y qué parte de su contorno queda
  cerrada por muros, vallas o setos;
- y, si el sitio tiene contorno de Catastro, la vegetación de dentro (infrarrojo), la altura que
  queda en pie (maqueta 3D del ICV) y el veredicto: solar, ruina o edificio con tejado.

Todo queda ligado a la foto usada (`IMAGEN`): mientras el ICV no publique otra, no hay que
rehacer nada. Se puede cortar y volver a lanzar: se salta los sitios ya hechos.

    python experimentos/vision/detectar.py --carpeta cache/_vision --datos datos
    python experimentos/vision/detectar.py --carpeta cache/_vision --datos datos --empaquetar
"""
from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import shape

from preparar import CAPAS, CLASES, IMAGEN, PIXEL, WMS, no_dormir

VENTANA = 2048                                   # píxeles de lado: 307 m
LINEALES = ("camino", "senda", "muro", "valla", "seto")
LARGO_MIN_M = {"camino": 12, "senda": 12, "muro": 5, "valla": 5, "seto": 6}
a_utm = Transformer.from_crs(4326, 25830, always_xy=True).transform
a_geo = Transformer.from_crs(25830, 4326, always_xy=True).transform


def pedir_foto(sesion: requests.Session, capa: str, x0: float, y0: float) -> np.ndarray | None:
    lado = VENTANA * PIXEL
    for intento in range(3):
        try:
            r = sesion.get(WMS, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": capa, "STYLES": "", "CRS": "EPSG:25830",
                                        "BBOX": f"{x0:.2f},{y0:.2f},{x0 + lado:.2f},{y0 + lado:.2f}", "WIDTH": VENTANA, "HEIGHT": VENTANA, "FORMAT": "image/jpeg"}, timeout=90)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    return img[:, :, ::-1]
        except requests.RequestException:
            pass
        time.sleep(2 + 4 * intento)
    return None


def trazar(mascara: np.ndarray, minimo_px: float) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """De una mancha a líneas: se adelgaza hasta un píxel de ancho y se siguen los trazos de cruce a cruce.
    De cada línea devuelve sus vértices (ya simplificados) y las filas y columnas de los píxeles por los que pasa."""
    from skimage.morphology import skeletonize
    hueso = skeletonize(mascara)
    _, grupo = cv2.connectedComponents(hueso.astype(np.uint8), connectivity=8)
    tamano = np.bincount(grupo.ravel())
    ys, xs = np.nonzero(hueso & (tamano[grupo] >= minimo_px))
    if not len(xs):
        return []
    alto, ancho = hueso.shape
    indice = -np.ones(hueso.shape, np.int32)
    indice[ys, xs] = np.arange(len(xs))
    vecinos: list[list[int]] = [[] for _ in range(len(xs))]
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                y2, x2 = ys + dy, xs + dx
                vale = (y2 >= 0) & (y2 < alto) & (x2 >= 0) & (x2 < ancho)
                otro = np.full(len(xs), -1, np.int32)
                otro[vale] = indice[y2[vale], x2[vale]]
                for a in np.flatnonzero(otro >= 0):
                    vecinos[a].append(int(otro[a]))
    hechas: set[tuple[int, int]] = set()
    trazos: list[list[int]] = []

    def andar(a: int, b: int) -> list[int]:
        ruta = [a, b]
        hechas.add((min(a, b), max(a, b)))
        while len(vecinos[b]) == 2:
            c = vecinos[b][0] if vecinos[b][1] == ruta[-2] else vecinos[b][1]
            if (min(b, c), max(b, c)) in hechas:
                break
            hechas.add((min(b, c), max(b, c)))
            ruta.append(c)
            b = c
        return ruta

    for a in range(len(xs)):                       # primero desde extremos y cruces…
        if len(vecinos[a]) != 2:
            for b in vecinos[a]:
                if (min(a, b), max(a, b)) not in hechas:
                    trazos.append(andar(a, b))
    for a in range(len(xs)):                       # …y luego los anillos cerrados, que no tienen ni lo uno ni lo otro
        if len(vecinos[a]) == 2 and (min(a, vecinos[a][0]), max(a, vecinos[a][0])) not in hechas:
            trazos.append(andar(a, vecinos[a][0]))
    salida = []
    for t in trazos:
        if len(t) < 5:
            continue
        puntos = np.column_stack([xs[t], ys[t]]).astype(np.float32)
        simple = cv2.approxPolyDP(puntos.reshape(-1, 1, 2), 1.5, False).reshape(-1, 2)
        if len(simple) >= 2:
            salida.append((simple, ys[t], xs[t]))
    return salida


def lineas_de(prob: np.ndarray, corte: dict) -> list[tuple[str, float, np.ndarray]]:
    """Las líneas que se ven en la ventana: (clase, confianza, vértices en píxeles de 30 cm).

    Las clases parecidas se trazan juntas y luego se decide qué es cada línea entera: si un muro saliese por
    un lado y una valla por otro, la misma tapia se partiría en trocitos de cada cosa.
    - Cierres (muro, valla, seto): la línea es de la clase que más se pasa de su corte a lo largo de ella.
    - Vías de tierra (camino, senda): fuera de donde manda la carretera. Es senda si lo dice el modelo o si
      la franja detectada es estrecha (menos de 1,8 m): en OSM las sendas vienen de trazas de GPS desviadas
      varios metros y el modelo apenas aprende a nombrarlas, pero sí las ve como un camino fino."""
    paso = PIXEL * 2
    n = {c: i for i, c in enumerate(CLASES)}
    sobra = {c: prob[n[c]] / corte[c] for c in CLASES}                   # más de 1: detectado
    salida = []
    cierres = ("muro", "valla", "seto")
    for vertices, ys, xs in trazar(np.maximum.reduce([sobra[c] for c in cierres]) > 1, min(LARGO_MIN_M[c] for c in cierres) / paso):
        clase = max(cierres, key=lambda c: float(sobra[c][ys, xs].mean()))
        salida.append((clase, float(prob[n[clase]][ys, xs].mean()), vertices))
    tierra = np.maximum(sobra["camino"], sobra["senda"])
    via = (tierra > 1) & (tierra >= sobra["carretera"])
    ancho_m = cv2.distanceTransform(via.astype(np.uint8), cv2.DIST_L2, 3) * 2 * paso        # ancho de la franja, medido en su eje
    for vertices, ys, xs in trazar(via, min(LARGO_MIN_M["camino"], LARGO_MIN_M["senda"]) / paso):
        es_senda = float(sobra["senda"][ys, xs].mean()) > float(sobra["camino"][ys, xs].mean()) or float(np.median(ancho_m[ys, xs])) < 1.8
        clase = "senda" if es_senda else "camino"
        salida.append((clase, float(np.maximum(prob[n["camino"]], prob[n["senda"]])[ys, xs].mean()), vertices))
    return salida


def medir_entorno(prob: np.ndarray, huella_px: np.ndarray | None, corte: dict) -> dict:
    """Cierre y accesos alrededor del contorno. `prob` es (clases, alto, ancho) a 30 cm; `huella_px`, su máscara."""
    n = {c: i for i, c in enumerate(CLASES)}
    if huella_px is None or not huella_px.any():
        return {}
    barrera = cv2.dilate(((prob[n["muro"]] > corte["muro"]) | (prob[n["valla"]] > corte["valla"]) | (prob[n["seto"]] > corte["seto"])).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    ys, xs = np.nonzero(huella_px)
    cy, cx, alto = ys.mean(), xs.mean(), prob.shape[1]
    pasos = np.arange(0, int(120 / (PIXEL * 2)))                    # hasta 120 m, de píxel en píxel
    tapados, rayos = 0, 48
    for k in range(rayos):                                            # 48 rayos desde el centro: ¿topan con una barrera al salir?
        ang = 2 * math.pi * k / rayos
        px = np.clip((cx + pasos * math.cos(ang)).round().astype(int), 0, alto - 1)
        py = np.clip((cy + pasos * math.sin(ang)).round().astype(int), 0, alto - 1)
        dentro = np.flatnonzero(huella_px[py, px])
        salida = dentro[-1] + 3 if len(dentro) else 0
        tapados += bool(barrera[py[salida:], px[salida:]].any())
    via = ((prob[n["camino"]] > corte["camino"]) | (prob[n["senda"]] > corte["senda"]) | (prob[n["carretera"]] > corte["carretera"])).astype(np.uint8)
    lejos = cv2.dilate(huella_px.astype(np.uint8), np.ones((133, 133), np.uint8))      # 20 m
    cerca = cv2.dilate(huella_px.astype(np.uint8), np.ones((53, 53), np.uint8))        # 8 m
    cuenta, _, datos, _ = cv2.connectedComponentsWithStats(via & lejos & (1 - cerca), connectivity=8)
    return {"cerrado_pct": round(100 * tapados / rayos), "accesos": int(sum(1 for k in range(1, cuenta) if datos[k, cv2.CC_STAT_AREA] >= 25))}


def medir_huella(rgb: np.ndarray, irg: np.ndarray, dentro: np.ndarray) -> dict:
    """Vegetación y superficie lisa dentro del contorno (imágenes a 30 cm, como en la prueba de noviembre)."""
    nir, rojo = irg[..., 0].astype(np.float32), irg[..., 1].astype(np.float32)
    brillo = rgb.astype(np.float32).mean(-1) / 255
    planta = (nir - rojo) / (nir + rojo + 1e-6) > 0.12
    sombra = (brillo < 0.22) & ~planta
    media = cv2.blur(brillo, (5, 5))
    rugoso = np.sqrt(np.clip(cv2.blur(brillo * brillo, (5, 5)) - media ** 2, 0, None))
    total = max(int(dentro.sum()), 1)
    return {"vegetacion_pct": round(100 * int((planta & dentro).sum()) / total), "liso_pct": round(100 * int((~planta & ~sombra & (rugoso < 0.035) & dentro).sum()) / total)}


def veredicto(m: dict) -> str | None:
    """La regla de la prueba de noviembre (ocho sitios): no está validada con más."""
    if m.get("en_pie_pct") is None or m.get("vegetacion_pct") is None:
        return None
    if m["en_pie_pct"] < 15:
        return "solar"
    if m["vegetacion_pct"] >= 30:
        return "ruina_vegetacion"
    if m["en_pie_pct"] >= 75 and m.get("liso_pct", 0) >= 50:
        return "tejado"
    return "ruina"


def bajar_sitio(sesion, mallas, sitio: dict, huella, con_altura: bool) -> dict:
    """Todo lo que es esperar a internet para un sitio: las dos fotos y la altura de la maqueta."""
    lon, lat = sitio["geometry"]["coordinates"][:2]
    x, y = a_utm(lon, lat)
    x0, y0 = round(x - VENTANA * PIXEL / 2, 2), round(y - VENTANA * PIXEL / 2, 2)
    salida = {"sitio": sitio, "x0": x0, "y0": y0, "rgb": pedir_foto(sesion, CAPAS["rgb"], x0, y0), "irg": pedir_foto(sesion, CAPAS["irg"], x0, y0), "altura": None}
    if con_altura and huella is not None:
        try:
            from malla import medir
            salida["altura"] = medir(mallas, huella, lat)
        except Exception:                         # la maqueta falla a ratos: el sitio sigue sin altura
            salida["altura"] = None
    return salida


def predecir(modelo, dispositivo, rgb: np.ndarray, irg: np.ndarray, media, desv):
    """Probabilidad por clase en toda la ventana, pasando el modelo por recortes de 512 que se solapan."""
    import torch
    x = (np.dstack([rgb, irg[:, :, 0]]).astype(np.float32) / 255 - media) / desv
    x = torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1))).to(dispositivo)
    suma = torch.zeros((len(CLASES), VENTANA, VENTANA), device=dispositivo)
    veces = torch.zeros((1, VENTANA, VENTANA), device=dispositivo)
    rampa = torch.minimum(torch.arange(1, 513, device=dispositivo), torch.arange(512, 0, -1, device=dispositivo)).float().clamp(max=64) / 64
    peso = (rampa[:, None] * rampa[None, :])[None]                 # los bordes de cada recorte cuentan menos
    pasos = sorted({*range(0, VENTANA - 512, 384), VENTANA - 512})    # el último recorte acaba justo en el borde
    esquinas = [(a, b) for a in pasos for b in pasos]
    with torch.no_grad(), torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
        for k in range(0, len(esquinas), 8):
            lote = esquinas[k:k + 8]
            p = torch.sigmoid(modelo(torch.stack([x[:, a:a + 512, b:b + 512] for a, b in lote]))).float()
            for (a, b), q in zip(lote, p):
                suma[:, a:a + 512, b:b + 512] += q * peso
                veces[:, a:a + 512, b:b + 512] += peso
    prob = suma / veces.clamp(min=1e-6)
    return torch.nn.functional.avg_pool2d(prob[None], 2)[0].cpu().numpy()          # a 30 cm: basta y va cuatro veces más rápido


def analizar(modelo, dispositivo, media, desv, bajado: dict, huella, nombre_modelo: str, corte: dict) -> dict | None:
    sitio, x0, y0 = bajado["sitio"], bajado["x0"], bajado["y0"]
    if bajado["rgb"] is None or bajado["irg"] is None or bajado["rgb"].std() < 4:
        return None
    prob = predecir(modelo, dispositivo, bajado["rgb"], bajado["irg"], media, desv)
    paso = PIXEL * 2
    y1 = y0 + VENTANA * PIXEL
    lineas, largos = [], {}
    for clase, confianza, puntos in lineas_de(prob, corte):
        ux, uy = x0 + (puntos[:, 0] + 0.5) * paso, y1 - (puntos[:, 1] + 0.5) * paso
        largo = float(np.hypot(np.diff(ux), np.diff(uy)).sum())
        if largo < 3:
            continue
        lo, la = a_geo(ux, uy)
        lineas.append({"c": clase, "p": round(confianza, 2), "g": [[round(float(a), 6), round(float(b), 6)] for a, b in zip(lo, la)]})
        largos[clase] = largos.get(clase, 0.0) + largo
    salida = {"id": sitio["properties"]["id"], "imagen": IMAGEN, "modelo": nombre_modelo, "fecha": time.strftime("%Y-%m-%d"),
              "centro": [round(float(c), 6) for c in sitio["geometry"]["coordinates"][:2]],
              "largo_m": {k: round(v) for k, v in largos.items()}, "lineas": lineas}
    if huella is not None:
        en_utm = shapely.transform(huella, lambda c: np.column_stack(a_utm(c[:, 0], c[:, 1])))
        mascara = np.zeros((VENTANA // 2, VENTANA // 2), np.uint8)
        for parte in shapely.get_parts(en_utm):
            px = np.column_stack([(np.array(parte.exterior.coords)[:, 0] - x0) / paso, (y1 - np.array(parte.exterior.coords)[:, 1]) / paso]).round().astype(np.int32)
            cv2.fillPoly(mascara, [px], 1)
        dentro = mascara > 0
        if dentro.sum() >= 20:
            medio = (VENTANA // 2, VENTANA // 2)
            salida.update(medir_huella(cv2.resize(bajado["rgb"], medio, interpolation=cv2.INTER_AREA), cv2.resize(bajado["irg"], medio, interpolation=cv2.INTER_AREA), dentro))
            salida.update(medir_entorno(prob, dentro, corte))
            if bajado["altura"]:
                salida.update({"altura_m": bajado["altura"]["altura_mediana_m"], "en_pie_pct": bajado["altura"]["pct_en_pie"]})
            salida["estado"] = veredicto(salida)
    return salida


def cortes_de(base: Path, modelo: str) -> dict:
    """A partir de qué probabilidad se da por detectada cada clase: lo que eligió calibrar.py, o 0,5."""
    corte = {c: 0.5 for c in CLASES}
    fichero = base / "modelos" / f"{modelo}-umbrales.json"
    if fichero.exists():
        corte.update({c: v["corte"] for c, v in json.loads(fichero.read_text(encoding="utf-8"))["elegido"].items() if c in corte})
    return corte


def compacto(r: dict) -> dict:
    """Las líneas de un sitio en poco sitio. Cada coordenada, en millonésimas de grado (unos 10 cm) contadas
    desde el centro del sitio; cada punto, como salto desde el anterior. Así casi todo son números de dos o
    tres cifras y el fichero pesa la cuarta parte que con las coordenadas enteras."""
    lon0, lat0 = r.get("centro") or (r["lineas"][0]["g"][0] if r["lineas"] else (0.0, 0.0))
    lineas = []
    for l in r["lineas"]:
        ex = ey = 0
        saltos = []
        for lon, lat in l["g"]:
            x, y = round((lon - lon0) * 1e6), round((lat - lat0) * 1e6)
            saltos += [x - ex, y - ey]
            ex, ey = x, y
        lineas.append([l["c"], round(l["p"] * 100), saltos])
    return {"imagen": r["imagen"], "modelo": r["modelo"], "o": [lon0, lat0], "l": lineas}


def empaquetar(base: Path, datos: Path) -> None:
    """Junta lo calculado en lo que publica la web: un resumen de todos y un fichero de líneas por sitio."""
    origen = base / "resultados" / IMAGEN
    destino = datos / "vision"
    destino.mkdir(parents=True, exist_ok=True)
    resumen, modelo, peso = {}, "", 0
    for f in sorted(origen.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        modelo = r.get("modelo", modelo)
        resumen[r["id"]] = {k: r[k] for k in ("estado", "altura_m", "en_pie_pct", "vegetacion_pct", "cerrado_pct", "accesos", "largo_m") if r.get(k) not in (None, {})}
        texto = json.dumps(compacto(r), separators=(",", ":"))
        peso += len(texto)
        (destino / f.name).write_text(texto, encoding="utf-8")
    # Lo que acertó el modelo en las teselas que no vio al entrenar: la web lo enseña junto a lo detectado.
    fiabilidad = {}
    cifras, calibrado = base / "modelos" / f"{modelo}.json", base / "modelos" / f"{modelo}-umbrales.json"
    if modelo and calibrado.exists():                                           # medido con el corte que de verdad se usa
        elegido = json.loads(calibrado.read_text(encoding="utf-8"))["elegido"]
        fiabilidad = {c: {"precision": round(100 * v["precision"]), "alcance": round(100 * v["alcance"])} for c, v in elegido.items() if c in LINEALES}
    elif modelo and cifras.exists():
        diario = json.loads(cifras.read_text(encoding="utf-8"))               # una entrada por vuelta de entrenamiento
        medido = max(diario, key=lambda d: d["nota"])["clases"] if diario else {}   # la vuelta que se guardó: la de mejor nota
        fiabilidad = {c: {"precision": round(100 * v["precision"]), "alcance": round(100 * v["alcance"])} for c, v in medido.items() if c in LINEALES and v.get("pixeles")}
    (datos / "revision.json").write_text(json.dumps({"imagen": IMAGEN, "vuelo": "2025", "modelo": modelo, "hecho": time.strftime("%Y-%m-%d"), "radio_m": round(VENTANA * PIXEL / 2),
                                                     "fiabilidad": fiabilidad, "sitios": resumen}, separators=(",", ":")), encoding="utf-8")
    print(f"empaquetados {len(resumen)} sitios en {datos / 'revision.json'} y {destino} ({peso / 1e6:.1f} MB de líneas)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pasa el detector por los alrededores de cada candidato.")
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--datos", default="datos")
    ap.add_argument("--modelo", default="lineas-v1"); ap.add_argument("--cuantos", type=int, default=0, help="solo los N primeros por nota")
    ap.add_argument("--hilos", type=int, default=4); ap.add_argument("--sin-altura", action="store_true")
    ap.add_argument("--empaquetar", action="store_true", help="solo juntar lo ya calculado en datos/")
    args = ap.parse_args()
    base, datos = Path(args.carpeta), Path(args.datos)
    if args.empaquetar:
        return empaquetar(base, datos)
    import torch
    import segmentation_models_pytorch as smp
    from malla import ZONAS, Malla
    no_dormir()
    destino = base / "resultados" / IMAGEN
    destino.mkdir(parents=True, exist_ok=True)
    guardado = torch.load(base / "modelos" / f"{args.modelo}.pt", map_location="cpu", weights_only=False)
    dispositivo = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    modelo = smp.Unet("resnet34", encoder_weights=None, in_channels=4, classes=len(CLASES))
    modelo.load_state_dict(guardado["modelo"])
    modelo.to(dispositivo).eval()
    media, desv = np.array(guardado["media"], np.float32), np.array(guardado["desv"], np.float32)
    corte = cortes_de(base, args.modelo)
    print("cortes:", corte, flush=True)
    sitios = json.loads((datos / "candidatos.geojson").read_text(encoding="utf-8"))["features"]
    sitios.sort(key=lambda s: -float(s["properties"].get("puntuacion") or 0))
    if args.cuantos:
        sitios = sitios[:args.cuantos]
    huellas = {f["properties"]["id"]: shape(f["geometry"]) for f in json.loads((datos / "huellas.geojson").read_text(encoding="utf-8"))["features"]}
    nombre = lambda s: destino / (s["properties"]["id"].replace("/", "_").replace(":", "_") + ".json")
    faltan = [s for s in sitios if not nombre(s).exists()]
    print(f"{len(sitios)} sitios, {len(faltan)} por hacer | {dispositivo}", flush=True)
    sesion = requests.Session()
    sesion.headers["User-Agent"] = "osintmaps (uso personal; revisión de candidatos)"
    mallas = {zona: Malla(sesion, zona) for zona in ZONAS}
    t0, hechos, fallos = time.time(), 0, 0
    with ThreadPoolExecutor(args.hilos) as hilos:
        for k in range(0, len(faltan), 12):
            tanda = faltan[k:k + 12]
            for bajado in hilos.map(lambda s: bajar_sitio(sesion, mallas, s, huellas.get(s["properties"]["id"]), not args.sin_altura), tanda):
                try:
                    r = analizar(modelo, dispositivo, media, desv, bajado, huellas.get(bajado["sitio"]["properties"]["id"]), args.modelo, corte)
                except Exception as e:                                  # un sitio raro no debe parar la noche
                    print("  fallo en", bajado["sitio"]["properties"]["id"], repr(e)[:200], flush=True)
                    r = None
                if r is None:
                    fallos += 1
                    continue
                nombre(bajado["sitio"]).write_text(json.dumps(r, separators=(",", ":")), encoding="utf-8")
                hechos += 1
            print(f"{hechos + fallos}/{len(faltan)} ({hechos} bien, {fallos} sin foto o con fallo) {time.time() - t0:.0f} s", flush=True)
    empaquetar(base, datos)
    print("FIN-DETECTAR", flush=True)


if __name__ == "__main__":
    main()
