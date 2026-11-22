"""Segunda pasada: caminos (franjas claras de tierra) y muros (trazos finos y rectos, sin planta)."""
import sys
import cv2
import numpy as np
from skimage.filters import apply_hysteresis_threshold, sato
from skimage.measure import label, regionprops
from skimage.morphology import skeletonize

M = 0.15
clave = sys.argv[1]
rgb = cv2.cvtColor(cv2.imread(f"in/{clave}_rgb.jpg"), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
irg = cv2.cvtColor(cv2.imread(f"in/{clave}_irg.jpg"), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
ndvi = (irg[..., 0] - irg[..., 1]) / (irg[..., 0] + irg[..., 1] + 1e-6)
planta = cv2.blur((ndvi > 0.10).astype(np.float32), (5, 5)) > 0.5
palido = rgb.min(-1)                      # la tierra pisada es clara en los tres colores
brillo = rgb.mean(-1)

# --- Caminos: franja clara de 1,5 a 4 m, sin planta, larga.
resp = sato(cv2.GaussianBlur(palido, (0, 0), 2), sigmas=[5, 8, 11], black_ridges=False)
resp[planta] = 0
m = apply_hysteresis_threshold(resp, np.percentile(resp, 93), np.percentile(resp, 97.5))
m &= palido > np.percentile(palido[~planta], 55)
hueso = skeletonize(m)
et = label(hueso, connectivity=2)
caminos = np.zeros_like(hueso)
largo_caminos = 0.0
for r in regionprops(et):
    if r.area * M >= 30:
        caminos[r.coords[:, 0], r.coords[:, 1]] = True
        largo_caminos += r.area * M
cerca_camino = cv2.dilate(caminos.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0   # 3 m a cada lado

# --- Muros: segmentos rectos (LSD) de 4 m o más, sin planta encima y lejos del borde de un camino.
gris = cv2.GaussianBlur((brillo * 255).astype(np.uint8), (0, 0), 1.0)
lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
seg = lsd.detect(gris)[0]
muros = []
for x1, y1, x2, y2 in (seg.reshape(-1, 4) if seg is not None else []):
    largo = float(np.hypot(x2 - x1, y2 - y1)) * M
    if largo < 4:
        continue
    n = int(largo / M)
    xs = np.clip(np.linspace(x1, x2, n).astype(int), 0, rgb.shape[1] - 1)
    ys = np.clip(np.linspace(y1, y2, n).astype(int), 0, rgb.shape[0] - 1)
    if planta[ys, xs].mean() > 0.3 or cerca_camino[ys, xs].mean() > 0.5:
        continue
    # Contraste a los dos lados del trazo: un muro o su sombra dan un escalón claro.
    dx, dy = (y2 - y1), -(x2 - x1); norma = np.hypot(dx, dy) + 1e-6; dx, dy = dx / norma * 4, dy / norma * 4
    a = brillo[np.clip((ys + dy).astype(int), 0, 1999), np.clip((xs + dx).astype(int), 0, 1999)]
    b = brillo[np.clip((ys - dy).astype(int), 0, 1999), np.clip((xs - dx).astype(int), 0, 1999)]
    if abs(float(a.mean() - b.mean())) < 0.07:
        continue
    muros.append((x1, y1, x2, y2, largo))
print(f"{clave}: caminos {largo_caminos:.0f} m; trazos rectos tipo muro {len(muros)} ({sum(m_[4] for m_ in muros):.0f} m)")

base = (rgb * 255).astype(np.uint8)
gris3 = cv2.cvtColor(cv2.cvtColor(base, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
lienzo = (gris3 * 0.55 + base * 0.25).astype(np.uint8)
lienzo[cv2.dilate(caminos.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0] = (255, 150, 0)
for x1, y1, x2, y2, _ in muros:
    cv2.line(lienzo, (int(x1), int(y1)), (int(x2), int(y2)), (255, 255, 0), 3, cv2.LINE_AA)
np.save(f"out/{clave}_lienzo.npy", lienzo)
x0, y0, x1, y1 = [int(v) for v in sys.argv[2:6]] if len(sys.argv) > 5 else (400, 400, 1600, 1600)
par = np.hstack([base[y0:y1, x0:x1], np.full((y1 - y0, 12, 3), 255, np.uint8), lienzo[y0:y1, x0:x1]])
cv2.imwrite(f"out/{clave}_par.jpg", cv2.cvtColor(par, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(par.shape)
