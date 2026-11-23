"""Prueba: ¿se distingue tejado entero, edificio sin tejado y solar desde la ortofoto infrarroja?"""
import json
import cv2
import numpy as np

sitios = json.load(open("sitios.json"))
VERDAD = {"s00": "ruina parcial", "s01": "ruina + tejado", "s02": "tejados rotos, patios", "s03": "tejado (patios dentro)",
          "s04": "ruina parcial", "s05": "TEJADO ENTERO", "s06": "TEJADO", "s07": "TEJADO", "s08": "TEJADO",
          "s09": "SIN TEJADO casi todo", "s10": "SOLAR"}
print(f"{'':4}{'veg%':>6}{'sombra%':>8}{'liso%':>7}{'borde':>7}{'somb.fuera%':>12}{'dif.color':>10}   a ojo")
for s in sitios:
    k = s["k"]
    irg = cv2.cvtColor(cv2.imread(f"in/t_{k}_irg.jpg"), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    rgb = cv2.cvtColor(cv2.imread(f"in/t_{k}_rgb.jpg"), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    alto, ancho = irg.shape[:2]
    dentro = np.zeros((alto, ancho), np.uint8)
    for anillo in s["h"]:
        pts = np.array([[(x - 1000) / 2 + 200, (y - 1000) / 2 + 200] for x, y in anillo], np.int32)
        cv2.fillPoly(dentro, [pts], 1)
    dentro = dentro.astype(bool)
    if dentro.sum() < 50:
        print(k, "huella fuera del recorte"); continue
    nir, rojo = irg[..., 0], irg[..., 1]
    ndvi = (nir - rojo) / (nir + rojo + 1e-6)
    brillo = rgb.mean(-1)
    veg = ndvi > 0.12
    sombra = (brillo < 0.22) & ~veg
    # «Liso»: ni planta ni sombra y con poca variación alrededor (tejado o suelo desnudo).
    media = cv2.blur(brillo, (5, 5)); var = cv2.blur(brillo * brillo, (5, 5)) - media ** 2
    liso = ~veg & ~sombra & (np.sqrt(np.clip(var, 0, None)) < 0.035)
    # Bordes dentro de la huella (muros, vigas, escombros dan muchos).
    gx = cv2.Sobel(brillo, cv2.CV_32F, 1, 0); gy = cv2.Sobel(brillo, cv2.CV_32F, 0, 1)
    borde = np.hypot(gx, gy)
    # Anillo de 4,5 m por fuera: sombra arrojada (algo con altura) y color del entorno.
    nucleo = np.ones((31, 31), np.uint8)
    anillo_fuera = cv2.dilate(dentro.astype(np.uint8), nucleo).astype(bool) & ~dentro
    color_dentro = np.median(rgb[dentro & ~veg & ~sombra], axis=0) if (dentro & ~veg & ~sombra).sum() > 20 else np.zeros(3)
    color_fuera = np.median(rgb[anillo_fuera & ~veg & ~sombra], axis=0) if (anillo_fuera & ~veg & ~sombra).sum() > 20 else np.zeros(3)
    dif = float(np.abs(color_dentro - color_fuera).sum())
    f = lambda m, zona: 100 * (m & zona).sum() / zona.sum()
    print(f"{k:4}{f(veg, dentro):6.0f}{f(sombra, dentro):8.0f}{f(liso, dentro):7.0f}{borde[dentro].mean():7.2f}{f(sombra, anillo_fuera):12.0f}{dif:10.2f}   {VERDAD[k]}")
