"""Enseña lo detectado en unos cuantos sitios sobre su foto, para comprobarlo a ojo.

Las hojas de `ver.py` comparan con OSM en teselas de entrenamiento; estas enseñan lo que de verdad
llega a la web: la ventana de cada candidato con sus líneas, su contorno y el veredicto. Usa las
fotos que `detectar.py` dejó guardadas, así que no baja nada.

    python ver_sitios.py --carpeta cache/_vision --datos datos --modelo lineas-v2 --cuantos 12

Deja `cache/_vision/ver/<modelo>-sitios-N.jpg`, con cuatro sitios por hoja. Con `--estado solar`
solo salen los de ese veredicto (para ver si la regla de «sin nada en pie» acierta)."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np
from pyproj import Transformer

from preparar import IMAGEN, PIXEL

VENTANA = 2048
LADO = 1024                                         # cada sitio se enseña a la mitad de resolución (30 cm)
COLOR = {"camino": (255, 255, 255), "senda": (111, 214, 255), "muro": (255, 122, 51), "valla": (255, 217, 26), "seto": (99, 224, 140)}
a_utm = Transformer.from_crs(4326, 25830, always_xy=True).transform


def pintar_sitio(foto: np.ndarray, r: dict, huella: list | None) -> np.ndarray:
    """La foto del sitio (rojo, verde, azul) con las líneas, el contorno y un rótulo con lo medido."""
    lienzo = cv2.resize(foto, (LADO, LADO), interpolation=cv2.INTER_AREA)
    x, y = a_utm(*r["centro"])
    x0, y1 = x - VENTANA * PIXEL / 2, y + VENTANA * PIXEL / 2
    escala = LADO / (VENTANA * PIXEL)                # píxeles de la hoja por metro

    def a_px(puntos) -> np.ndarray:
        ux, uy = a_utm(np.array([p[0] for p in puntos]), np.array([p[1] for p in puntos]))
        return np.column_stack([(ux - x0) * escala, (y1 - uy) * escala]).round().astype(np.int32)

    for anillo in huella or []:                      # el contorno de Catastro, en magenta
        cv2.polylines(lienzo, [a_px(anillo)], True, (229, 0, 125), 2, cv2.LINE_AA)
    for linea in r.get("lineas", []):
        puntos = a_px(linea["g"])
        cv2.polylines(lienzo, [puntos], False, (16, 24, 29), 5, cv2.LINE_AA)
        cv2.polylines(lienzo, [puntos], False, COLOR[linea["c"]], 2, cv2.LINE_AA)
    largos = r.get("largo_m", {})
    rotulos = [f"{r['id']}  {r.get('estado') or 'sin veredicto'}",
               " ".join(f"{k}={r[k]}" for k in ("en_pie_pct", "altura_m", "vegetacion_pct", "cerrado_pct", "accesos") if r.get(k) is not None),
               " ".join(f"{c}:{largos[c]}m" for c in COLOR if largos.get(c))]
    lienzo[:82] = (lienzo[:82] * 0.35).astype(np.uint8)          # una banda oscura para que el rótulo se lea sobre cualquier foto
    for n, texto in enumerate(rotulos):
        cv2.putText(lienzo, texto, (8, 24 + 24 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1, cv2.LINE_AA)
    return lienzo


def main() -> None:
    ap = argparse.ArgumentParser(description="Hojas con lo detectado en unos cuantos sitios.")
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--datos", default="datos"); ap.add_argument("--modelo", default="lineas-v2")
    ap.add_argument("--cuantos", type=int, default=12); ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--estado", default="", help="solo los sitios con ese veredicto (solar, ruina, ruina_vegetacion, tejado)")
    ap.add_argument("--ids", default="", help="estos sitios en concreto, separados por comas")
    args = ap.parse_args()
    base = Path(args.carpeta)
    destino = base / "ver"
    destino.mkdir(exist_ok=True)
    huellas = {}
    for f in json.loads((Path(args.datos) / "huellas.geojson").read_text(encoding="utf-8"))["features"]:
        g = f["geometry"]
        partes = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        huellas[f["properties"]["id"]] = [parte[0] for parte in partes]
    resultados = []
    for f in sorted((base / "resultados" / IMAGEN / args.modelo).glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        if (not args.estado or r.get("estado") == args.estado) and (base / "ventanas" / IMAGEN / f"{f.stem}_rgb.jpg").exists():
            resultados.append((f.stem, r))
    if args.ids:
        quiero = set(args.ids.split(","))
        elegidos = [x for x in resultados if x[1]["id"] in quiero]
    else:
        elegidos = random.Random(args.semilla).sample(resultados, min(args.cuantos, len(resultados)))
    print(f"{len(resultados)} sitios con foto y resultado; se enseñan {len(elegidos)}", flush=True)
    sufijo = f"-{args.estado}" if args.estado else ""
    for n in range(0, len(elegidos), 4):
        celdas = []
        for nombre, r in elegidos[n:n + 4]:
            foto = cv2.imdecode(np.fromfile(str(base / "ventanas" / IMAGEN / f"{nombre}_rgb.jpg"), np.uint8), cv2.IMREAD_COLOR)[:, :, ::-1]
            celdas.append(pintar_sitio(np.ascontiguousarray(foto), r, huellas.get(r["id"])))
        while len(celdas) < 4:
            celdas.append(np.zeros((LADO, LADO, 3), np.uint8))
        hoja = np.vstack([np.hstack(celdas[:2]), np.hstack(celdas[2:])])
        salida = destino / f"{args.modelo}-sitios{sufijo}-{n // 4 + 1}.jpg"
        cv2.imwrite(str(salida), hoja[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 84])
        print(" ", salida, [r["id"] for _, r in elegidos[n:n + 4]], flush=True)
    print("FIN-VER-SITIOS", flush=True)


if __name__ == "__main__":
    main()
