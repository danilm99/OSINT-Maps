"""Enseña al modelo a ver caminos, sendas, muros y vallas con las teselas de `preparar.py`.

Qué es el modelo. Una red de las que «colorean» imágenes (U-Net con un ResNet-34 ya entrenado con
fotos corrientes): entra un recorte de 512 x 512 con cuatro canales (rojo, verde, azul e
infrarrojo) y sale, para cada píxel y cada clase, cuánto cree que ahí hay eso (de 0 a 1).

Cómo aprende. Se le enseña un recorte, se compara lo que dice con lo que OSM tiene dibujado y se
le corrige un poco; así miles de veces. Dos cosas a tener en cuenta con estas etiquetas:
- OSM dibuja con uno o dos metros de error. Alrededor de lo fino (sendas, muros, vallas, setos,
  acequias) se deja una franja «de duda» donde no se le corrige ni para bien ni para mal.
- A OSM le falta mucho por dibujar. Lo que el modelo vea y OSM no tenga cuenta como error aunque
  sea verdad: la «precisión» que sale aquí es un suelo, no la cifra real.

Se guarda el mejor modelo en `modelos/lineas-v1.pt` y las cifras de cada vuelta en `lineas-v1.json`.

    python experimentos/vision/entrenar.py --carpeta cache/_vision --vueltas 24
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from preparar import CLASES, IMAGEN, no_dormir

FINAS = ("senda", "muro", "valla", "seto", "acequia")
PESO = {"camino": 2.0, "senda": 4.0, "carretera": 1.0, "muro": 5.0, "valla": 5.0, "seto": 4.0, "acequia": 4.0, "edificio": 1.0}
MEDIA = np.array([0.485, 0.456, 0.406, 0.5], np.float32)
DESV = np.array([0.229, 0.224, 0.225, 0.25], np.float32)
NUCLEO_DUDA = np.ones((15, 15), np.uint8)             # 7 píxeles a cada lado: un metro
NUCLEO_VIA = np.ones((41, 41), np.uint8)              # 20 píxeles a cada lado: tres metros
CIERRES = ("muro", "valla", "seto")
# Lo que OSM no tiene dibujado no prueba que no exista: de los cierres falta la mayoría. Marcar uno donde
# OSM no dice nada se castiga menos que en las demás clases; y menos aún en las teselas donde nadie ha
# dibujado ningún cierre (ahí lo normal es que no se haya mirado).
PESO_NO_CIERRE = {True: 0.7, False: 0.3}              # según la tesela tenga o no algún cierre dibujado


def leer_tesela(base: Path, i: int, j: int) -> np.ndarray:
    """Los cuatro canales (rojo, verde, azul, infrarrojo) entre 0 y 1."""
    rgb = cv2.imread(str(base / "teselas" / f"{i}_{j}_rgb.jpg"))[:, :, ::-1]
    irg = cv2.imread(str(base / "teselas" / f"{i}_{j}_irg.jpg"))[:, :, ::-1]
    return np.dstack([rgb, irg[:, :, 0]]).astype(np.float32) / 255.0


class Teselas(torch.utils.data.Dataset):
    def __init__(self, base: Path, claves: list, aumentar: bool):
        self.base, self.claves, self.aumentar = base, claves, aumentar

    def __len__(self) -> int:
        return len(self.claves)

    def __getitem__(self, k: int):
        i, j = self.claves[k]
        x = leer_tesela(self.base, i, j)
        bits = cv2.imread(str(self.base / "etiquetas" / f"{i}_{j}.png"), cv2.IMREAD_UNCHANGED)
        y = np.stack([(bits >> n) & 1 for n in range(len(CLASES))]).astype(np.float32)
        cuenta = np.ones_like(y)                       # cuánto pesa cada píxel al corregir: 0 en la franja de duda
        for n, clase in enumerate(CLASES):
            if clase in FINAS and y[n].any():
                cuenta[n][(cv2.dilate(y[n], NUCLEO_DUDA) > 0) & (y[n] == 0)] = 0
        # Caminos y sendas se parecen y en OSM las sendas vienen de trazas de GPS desviadas varios metros:
        # a tres metros de una, no se castiga marcar la otra; y la senda tiene esa misma franja de duda.
        ic, isd = CLASES.index("camino"), CLASES.index("senda")
        if y[isd].any():
            cerca = cv2.dilate(y[isd], NUCLEO_VIA) > 0
            cuenta[ic][cerca & (y[ic] == 0)] = 0
            cuenta[isd][cerca & (y[isd] == 0)] = 0
        if y[ic].any():
            cuenta[isd][(cv2.dilate(y[ic], NUCLEO_VIA) > 0) & (y[isd] == 0)] = 0
        hay_cierres = any(y[CLASES.index(c)].any() for c in CIERRES)
        for c in CIERRES:
            n = CLASES.index(c)
            cuenta[n][(y[n] == 0) & (cuenta[n] > 0)] = PESO_NO_CIERRE[hay_cierres]
        if self.aumentar:                              # la misma tesela girada, volteada o con otra luz es otro ejemplo
            giros = random.randrange(4)
            x, y, cuenta = np.rot90(x, giros, (0, 1)), np.rot90(y, giros, (1, 2)), np.rot90(cuenta, giros, (1, 2))
            if random.random() < 0.5:
                x, y, cuenta = x[:, ::-1], y[:, :, ::-1], cuenta[:, :, ::-1]
            x = np.clip((x - 0.5) * random.uniform(0.8, 1.25) + 0.5 + random.uniform(-0.08, 0.08), 0, 1)
        x = (x - MEDIA) / DESV
        return (torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1))), torch.from_numpy(np.ascontiguousarray(y)),
                torch.from_numpy(np.ascontiguousarray(cuenta)))


def crear_modelo(pesos: str | None = "imagenet"):
    """La red: una U-Net sobre ResNet-34. Para entrenar parte de lo aprendido con fotos corrientes (ImageNet);
    para usar un modelo ya entrenado no hace falta bajarse eso (pesos=None)."""
    import segmentation_models_pytorch as smp
    return smp.Unet("resnet34", encoder_weights=pesos, in_channels=4, classes=len(CLASES))


def perdida(salida, y, cuenta, peso):
    """Cuánto se equivoca: píxel a píxel (pesando más lo escaso) más el solape global por clase."""
    por_pixel = F.binary_cross_entropy_with_logits(salida, y, reduction="none") * cuenta * (1 + (peso - 1) * y)
    p, yy = torch.sigmoid(salida) * cuenta, y * cuenta
    solape = 1 - (2 * (p * yy).sum((0, 2, 3)) + 1) / (p.sum((0, 2, 3)) + yy.sum((0, 2, 3)) + 1)
    return por_pixel.sum() / cuenta.sum().clamp(min=1) + solape.mean()


@torch.no_grad()
def medir(modelo, datos, dispositivo) -> dict:
    """Aciertos con manga ancha: un píxel vale si lo de OSM está a menos de 1,2 m (lo fino) o 0,6 m (el resto)."""
    modelo.eval()
    n = len(CLASES)
    acierto_p, dicho, acierto_r, hay = (torch.zeros(n, device=dispositivo) for _ in range(4))
    for x, y, _ in datos:
        x, y = x.to(dispositivo), y.to(dispositivo)
        with torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
            p = (torch.sigmoid(modelo(x)) > 0.5).float()
        for c, clase in enumerate(CLASES):
            m = 8 if clase in FINAS else 4
            cerca_y = F.max_pool2d(y[:, c:c + 1], 2 * m + 1, 1, m)
            cerca_p = F.max_pool2d(p[:, c:c + 1], 2 * m + 1, 1, m)
            acierto_p[c] += (p[:, c:c + 1] * cerca_y).sum(); dicho[c] += p[:, c].sum()
            acierto_r[c] += (y[:, c:c + 1] * cerca_p).sum(); hay[c] += y[:, c].sum()
    salida = {}
    for c, clase in enumerate(CLASES):
        precision = float(acierto_p[c] / dicho[c].clamp(min=1)); alcance = float(acierto_r[c] / hay[c].clamp(min=1))
        salida[clase] = {"precision": round(precision, 3), "alcance": round(alcance, 3),
                         "f1": round(2 * precision * alcance / max(precision + alcance, 1e-6), 3), "pixeles": int(hay[c])}
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description="Entrena el detector de caminos, sendas, muros y vallas.")
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--vueltas", type=int, default=24)
    ap.add_argument("--lote", type=int, default=8); ap.add_argument("--nombre", default="lineas-v1")
    ap.add_argument("--prueba", action="store_true", help="64 teselas y una vuelta, para ver que todo funciona")
    ap.add_argument("--cpu", action="store_true", help="sin la gráfica (lento: solo para probar mientras está ocupada)")
    args = ap.parse_args()
    no_dormir()
    base = Path(args.carpeta)
    (base / "modelos").mkdir(exist_ok=True)
    claves = [tuple(t) for t in json.loads((base / "teselas.json").read_text(encoding="utf-8"))
              if (base / "teselas" / f"{t[0]}_{t[1]}_irg.jpg").exists() and (base / "etiquetas" / f"{t[0]}_{t[1]}.png").exists()]
    if args.prueba:
        claves, args.vueltas = claves[:64], 1
    # Se aparta una de cada diez manzanas de 600 m para medir: así no se examina con vecinos de lo ya visto.
    aparte = [c for c in claves if ((c[0] // 8) * 31 + (c[1] // 8) * 17) % 10 == 0]
    resto = [c for c in claves if c not in set(aparte)]
    dispositivo = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    print(f"teselas: {len(resto)} para aprender, {len(aparte)} para medir | {dispositivo}", flush=True)
    torch.backends.cudnn.benchmark = True
    cargar = dict(batch_size=args.lote, num_workers=4, pin_memory=True, persistent_workers=True)
    aprender = torch.utils.data.DataLoader(Teselas(base, resto, True), shuffle=True, drop_last=True, **cargar)
    examen = torch.utils.data.DataLoader(Teselas(base, aparte, False), shuffle=False, **cargar)
    modelo = crear_modelo().to(dispositivo)
    ajuste = torch.optim.AdamW(modelo.parameters(), lr=3e-4, weight_decay=1e-4)
    ritmo = torch.optim.lr_scheduler.OneCycleLR(ajuste, max_lr=6e-4, total_steps=args.vueltas * len(aprender), pct_start=0.15)
    escala = torch.amp.GradScaler("cuda", enabled=dispositivo.type == "cuda")
    peso = torch.tensor([PESO[c] for c in CLASES], device=dispositivo).view(1, -1, 1, 1)
    mejor, diario = -1.0, []
    for vuelta in range(1, args.vueltas + 1):
        modelo.train()
        t0, suma = time.time(), 0.0
        for x, y, cuenta in aprender:
            x, y, cuenta = x.to(dispositivo, non_blocking=True), y.to(dispositivo, non_blocking=True), cuenta.to(dispositivo, non_blocking=True)
            ajuste.zero_grad(set_to_none=True)
            with torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
                error = perdida(modelo(x), y, cuenta, peso)
            escala.scale(error).backward(); escala.step(ajuste); escala.update(); ritmo.step()
            suma += error.item()
        cifras = medir(modelo, examen, dispositivo)
        nota = float(np.mean([cifras[c]["f1"] for c in ("camino", "senda", "muro", "valla") if cifras[c]["pixeles"]] or [0]))
        diario.append({"vuelta": vuelta, "error": round(suma / max(len(aprender), 1), 4), "nota": round(nota, 4), "segundos": round(time.time() - t0), "clases": cifras})
        (base / "modelos" / f"{args.nombre}.json").write_text(json.dumps(diario, indent=1), encoding="utf-8")
        print(f"vuelta {vuelta}/{args.vueltas} error {suma / max(len(aprender), 1):.3f} nota {nota:.3f} ({time.time() - t0:.0f} s) | "
              + " ".join(f"{c}:{cifras[c]['precision']:.2f}/{cifras[c]['alcance']:.2f}" for c in ("camino", "senda", "muro", "valla", "seto")), flush=True)
        if nota > mejor:
            mejor = nota
            torch.save({"modelo": modelo.state_dict(), "clases": CLASES, "imagen": IMAGEN, "media": MEDIA.tolist(), "desv": DESV.tolist(),
                        "vuelta": vuelta, "cifras": cifras}, base / "modelos" / f"{args.nombre}.pt")
    print("FIN-ENTRENAR mejor nota", round(mejor, 4), flush=True)


if __name__ == "__main__":
    main()
