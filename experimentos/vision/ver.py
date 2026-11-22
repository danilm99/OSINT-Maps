"""Enseña lo que marca el modelo junto a lo que dice OpenStreetMap, para juzgarlo a ojo.

Las cifras de entrenar.py comparan con OSM, y en OSM faltan muchos muros y vallas: un acierto del
modelo donde nadie ha dibujado nada cuenta como fallo. Mirando las fotos se ve qué pasa de verdad.

Deja hojas en cache/_vision/ver/: una por clase. Cada fila es una tesela que el modelo no vio al
entrenar: la foto, la foto con lo de OSM encima y la foto con lo que marca el modelo.

    python ver.py --carpeta cache/_vision --modelo lineas-v1 --cpu

Con --cpu no toca la gráfica (sirve mientras se entrena: lee el mejor modelo guardado hasta ahora)."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np

from entrenar import DESV, MEDIA, leer_tesela
from preparar import CLASES

# Los mismos colores que en el visor (rojo, verde, azul).
COLOR = {"camino": (255, 255, 255), "senda": (111, 214, 255), "muro": (255, 122, 51), "valla": (255, 217, 26), "seto": (99, 224, 140),
         "carretera": (150, 160, 190), "acequia": (60, 110, 255), "edificio": (229, 0, 125)}


def pintar(rgb: np.ndarray, capas: np.ndarray) -> np.ndarray:
    """La foto con cada clase encima en su color; de los edificios, solo el borde."""
    salida = rgb.astype(np.float32)
    for n, clase in enumerate(CLASES):
        m = capas[n] > 0
        if not m.any():
            continue
        if clase == "edificio":
            m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        salida[m] = 0.3 * salida[m] + 0.7 * np.array(COLOR[clase], np.float32)
    return salida.astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description="Hojas para comparar a ojo el modelo con OSM.")
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--modelo", default="lineas-v1")
    ap.add_argument("--clases", default="muro,valla,senda,camino"); ap.add_argument("--filas", type=int, default=4)
    ap.add_argument("--semilla", type=int, default=1); ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--umbral", type=float, default=0.5)
    args = ap.parse_args()
    import torch
    import segmentation_models_pytorch as smp
    base = Path(args.carpeta)
    destino = base / "ver"
    destino.mkdir(exist_ok=True)
    dispositivo = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    guardado = torch.load(base / "modelos" / f"{args.modelo}.pt", map_location="cpu", weights_only=False)
    modelo = smp.Unet("resnet34", encoder_weights=None, in_channels=4, classes=len(CLASES))
    modelo.load_state_dict(guardado["modelo"])
    modelo.to(dispositivo).eval()
    print(f"modelo de la vuelta {guardado.get('vuelta')} | {dispositivo}", flush=True)

    # Solo teselas que el entrenamiento aparta para medir (la misma cuenta que en entrenar.py).
    claves = [tuple(t) for t in json.loads((base / "teselas.json").read_text(encoding="utf-8"))
              if ((t[0] // 8) * 31 + (t[1] // 8) * 17) % 10 == 0 and (base / "etiquetas" / f"{t[0]}_{t[1]}.png").exists()]
    bits = {c: cv2.imread(str(base / "etiquetas" / f"{c[0]}_{c[1]}.png"), cv2.IMREAD_UNCHANGED) for c in claves}
    azar = random.Random(args.semilla)
    for clase in args.clases.split(","):
        n = CLASES.index(clase)
        con = [c for c in claves if int(((bits[c] >> n) & 1).sum()) >= 300]          # que la clase se vea en la tesela
        elegidas = azar.sample(con, min(args.filas, len(con)))
        filas = []
        for (i, j) in elegidas:
            x = leer_tesela(base, i, j)
            rgb = (x[:, :, :3] * 255).astype(np.uint8)
            osm = np.stack([(bits[(i, j)] >> k) & 1 for k in range(len(CLASES))])
            with torch.no_grad():
                entrada = torch.from_numpy(np.ascontiguousarray(((x - MEDIA) / DESV).transpose(2, 0, 1)))[None].to(dispositivo)
                prob = torch.sigmoid(modelo(entrada))[0].cpu().numpy()
            fila = np.hstack([rgb, pintar(rgb, osm), pintar(rgb, prob > args.umbral)])
            cv2.putText(fila, f"{i}_{j}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
            filas.append(fila)
            filas.append(np.zeros((6, fila.shape[1], 3), np.uint8))
        if not filas:
            print(clase, "sin teselas", flush=True)
            continue
        hoja = np.vstack(filas[:-1])
        cv2.imwrite(str(destino / f"{args.modelo}-{clase}.jpg"), hoja[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 86])
        print(clase, len(elegidas), "teselas de", len(con), "->", destino / f"{args.modelo}-{clase}.jpg", flush=True)
    print("FIN-VER", flush=True)


if __name__ == "__main__":
    main()
