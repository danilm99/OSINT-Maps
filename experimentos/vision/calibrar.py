"""Elige, para cada clase, a partir de qué probabilidad se da algo por detectado.

El modelo da para cada píxel una probabilidad entre 0 y 1. Cortar en 0,5 es lo habitual, pero con
lo fino y escaso (vallas, sendas) el modelo rara vez llega a tanto: un corte más bajo encuentra
más a cambio de equivocarse más. Aquí se prueban varios cortes en las teselas apartadas para medir
y se guarda, por clase, el que mejor equilibra las dos cosas.

    python calibrar.py --carpeta cache/_vision --modelo lineas-v1

Deja cache/_vision/modelos/<modelo>-umbrales.json: lo usan detectar.py (para decidir qué es una
línea) y la web (para decir cuánto acierta cada clase)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F

from entrenar import CIERRES, FINAS, Teselas, crear_modelo
from preparar import CLASES

CORTES = (0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7)


@torch.no_grad()
def probar_cortes(modelo, datos, dispositivo) -> dict:
    """Para cada clase y cada corte: precisión y alcance con la misma manga ancha que entrenar.medir()."""
    # Además de las clases del modelo se mide una inventada, «cierre»: muro, valla o seto, sin distinguir.
    # Desde arriba una tapia y una valla tupida se parecen; esto dice cuánto acierta en que ahí hay algo que cierra.
    nombres = CLASES + ["cierre"]
    de_cierre = [CLASES.index(c) for c in CIERRES]
    n, k = len(nombres), len(CORTES)
    acierto_p, dicho, acierto_r, hay = (torch.zeros((k, n), device=dispositivo) for _ in range(4))
    for x, y, _ in datos:
        x, y = x.to(dispositivo), y.to(dispositivo)
        with torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
            prob = torch.sigmoid(modelo(x)).float()
        prob = torch.cat([prob, prob[:, de_cierre].amax(1, keepdim=True)], 1)
        y = torch.cat([y, y[:, de_cierre].amax(1, keepdim=True)], 1)
        for c, clase in enumerate(nombres):
            m = 8 if clase in FINAS or clase == "cierre" else 4
            cerca_y = F.max_pool2d(y[:, c:c + 1], 2 * m + 1, 1, m)
            for t, corte in enumerate(CORTES):
                p = (prob[:, c:c + 1] > corte).float()
                cerca_p = F.max_pool2d(p, 2 * m + 1, 1, m)
                acierto_p[t, c] += (p * cerca_y).sum(); dicho[t, c] += p.sum()
                acierto_r[t, c] += (y[:, c:c + 1] * cerca_p).sum(); hay[t, c] += y[:, c].sum()
    salida = {}
    for c, clase in enumerate(nombres):
        filas = []
        for t, corte in enumerate(CORTES):
            precision = float(acierto_p[t, c] / dicho[t, c].clamp(min=1)); alcance = float(acierto_r[t, c] / hay[t, c].clamp(min=1))
            filas.append({"corte": corte, "precision": round(precision, 3), "alcance": round(alcance, 3),
                          "f1": round(2 * precision * alcance / max(precision + alcance, 1e-6), 3)})
        salida[clase] = filas
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description="Elige el corte de probabilidad de cada clase.")
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--modelo", default="lineas-v1")
    ap.add_argument("--minima-precision", type=float, default=0.0, help="no bajar el corte si la precisión cae de aquí")
    args = ap.parse_args()
    base = Path(args.carpeta)
    dispositivo = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    guardado = torch.load(base / "modelos" / f"{args.modelo}.pt", map_location="cpu", weights_only=False)
    modelo = crear_modelo(pesos=None)
    modelo.load_state_dict(guardado["modelo"])
    modelo.to(dispositivo).eval()
    claves = [tuple(t) for t in json.loads((base / "teselas.json").read_text(encoding="utf-8"))
              if ((t[0] // 8) * 31 + (t[1] // 8) * 17) % 10 == 0
              and (base / "teselas" / f"{t[0]}_{t[1]}_irg.jpg").exists() and (base / "etiquetas" / f"{t[0]}_{t[1]}.png").exists()]
    datos = torch.utils.data.DataLoader(Teselas(base, claves, False), batch_size=8, num_workers=4)
    print(f"{len(claves)} teselas apartadas | {dispositivo} | modelo de la vuelta {guardado.get('vuelta')}", flush=True)
    tabla = probar_cortes(modelo, datos, dispositivo)
    elegido = {}
    for clase, filas in tabla.items():
        validas = [f for f in filas if f["precision"] >= args.minima_precision] or filas
        mejor = max(validas, key=lambda f: f["f1"])
        elegido[clase] = mejor
        print(f"{clase:10s} corte {mejor['corte']:.2f}: precisión {mejor['precision']:.2f}, alcance {mejor['alcance']:.2f}, f1 {mejor['f1']:.2f}   | "
              + " ".join(f"{f['corte']:.2f}:{f['precision']:.2f}/{f['alcance']:.2f}" for f in filas), flush=True)
    (base / "modelos" / f"{args.modelo}-umbrales.json").write_text(json.dumps({"teselas": len(claves), "elegido": elegido, "tabla": tabla}, indent=1), encoding="utf-8")
    print("FIN-CALIBRAR", flush=True)


if __name__ == "__main__":
    main()
