"""Experimento: altura real de cada candidato con la malla 3D del ICV (vuelo de 2025).

El ICV sirve en abierto la malla fotogramétrica de toda la provincia de València como
cuatro capas I3S («Malla3D_Sur», «Centro», «Norte» y «Ademuz»). Cada capa es un árbol
de trozos: los de arriba cubren mucho terreno con poco detalle y las hojas son el
detalle máximo. Aquí se baja por el árbol hasta las hojas que tocan la huella de un
candidato, se leen sus triángulos y se convierten en una rejilla de alturas de medio
metro. Con eso se ve si en la huella de Catastro sigue habiendo algo con altura.

Solo necesita numpy, shapely, pyproj y requests. No forma parte del paquete todavía.

    python experimentos/vision/malla.py --primeros 20
    python experimentos/vision/malla.py --ids ID1 ID2
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import time
from pathlib import Path

import numpy as np
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import shape

SERVICIO = "https://gvagis.icv.gva.es/server/rest/services/Malla3D_{}/SceneServer/layers/0"
# Cada capa cubre una franja de la provincia. Límites sur y norte en metros de Web Mercator.
ZONAS = {"Sur": (4676308, 4743121), "Centro": (4738661, 4803741), "Norte": (4799290, 4863679), "Ademuz": (4858491, 4902610)}
NODOS_POR_PAGINA = 64
PASO_M = 0.5            # lado de cada celda de la rejilla, en metros de verdad
MARGEN_M = 25.0         # terreno alrededor de la huella que se usa para saber dónde está el suelo
ALTO_M = 2.5            # por encima de esto se considera que «hay algo en pie»

a_mercator = Transformer.from_crs(4326, 3857, always_xy=True).transform


class Malla:
    """Lee una capa I3S pidiendo solo las páginas del árbol y los trozos que hagan falta."""

    def __init__(self, sesion: requests.Session, zona: str):
        self.sesion = sesion
        self.url = SERVICIO.format(zona)
        self.paginas: dict[int, list] = {}

    def nodo(self, indice: int) -> dict:
        pagina = indice // NODOS_POR_PAGINA
        if pagina not in self.paginas:
            r = self.sesion.get(f"{self.url}/nodepages/{pagina}", params={"f": "json"}, timeout=40)
            r.raise_for_status()
            self.paginas[pagina] = r.json()["nodes"]
        return self.paginas[pagina][indice % NODOS_POR_PAGINA]

    def hojas(self, x0: float, y0: float, x1: float, y1: float) -> list[dict]:
        """Trozos de máximo detalle cuya esfera envolvente alcanza el rectángulo."""
        cx, cy, radio = (x0 + x1) / 2, (y0 + y1) / 2, math.hypot(x1 - x0, y1 - y0) / 2
        salida, pendientes = [], [0]
        while pendientes:
            n = self.nodo(pendientes.pop())
            c, h = n["obb"]["center"], n["obb"]["halfSize"]
            if math.hypot(c[0] - cx, c[1] - cy) > math.sqrt(h[0] ** 2 + h[1] ** 2 + h[2] ** 2) + radio:
                continue
            hijos = n.get("children") or []
            if hijos:
                pendientes.extend(hijos)
            elif n.get("mesh"):
                salida.append(n)
        return salida

    def triangulos(self, n: dict) -> np.ndarray:
        """Triángulos de un trozo, como (n, 3 vértices, x y z) en coordenadas de la capa."""
        recurso = n["mesh"]["geometry"]["resource"]
        r = self.sesion.get(f"{self.url}/nodes/{recurso}/geometries/0", timeout=40)
        r.raise_for_status()
        cuantos = struct.unpack("<I", r.content[:4])[0]          # cabecera: nº de vértices y de «features»
        relativos = np.frombuffer(r.content, "<f4", cuantos * 3, 8).reshape(-1, 3, 3)
        return relativos.astype(np.float64) + np.array(n["obb"]["center"])   # van referidos al centro del trozo

    def rejilla(self, x0: float, y0: float, x1: float, y1: float, paso: float) -> np.ndarray:
        """Cota más alta de la malla en cada celda del rectángulo (NaN donde no hay malla)."""
        nx, ny = int((x1 - x0) / paso), int((y1 - y0) / paso)
        z = np.full((ny, nx), np.nan, np.float32)
        for n in self.hojas(x0, y0, x1, y1):
            p = self.triangulos(n)
            toca = (p[:, :, 0].max(1) >= x0) & (p[:, :, 0].min(1) <= x1) & (p[:, :, 1].max(1) >= y0) & (p[:, :, 1].min(1) <= y1)
            for t in p[toca]:
                gx, gy = (t[:, 0] - x0) / paso, (t[:, 1] - y0) / paso
                i0, i1 = max(int(gx.min()), 0), min(int(gx.max()) + 1, nx - 1)
                j0, j1 = max(int(gy.min()), 0), min(int(gy.max()) + 1, ny - 1)
                if i1 < i0 or j1 < j0:
                    continue
                # Coordenadas baricéntricas: cuánto pesa cada vértice en cada celda que pisa el triángulo.
                xx, yy = np.meshgrid(np.arange(i0, i1 + 1) + 0.5, np.arange(j0, j1 + 1) + 0.5)
                den = (gy[1] - gy[2]) * (gx[0] - gx[2]) + (gx[2] - gx[1]) * (gy[0] - gy[2])
                if abs(den) < 1e-9:
                    continue
                w0 = ((gy[1] - gy[2]) * (xx - gx[2]) + (gx[2] - gx[1]) * (yy - gy[2])) / den
                w1 = ((gy[2] - gy[0]) * (xx - gx[2]) + (gx[0] - gx[2]) * (yy - gy[2])) / den
                w2 = 1 - w0 - w1
                dentro = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
                cota = w0 * t[0, 2] + w1 * t[1, 2] + w2 * t[2, 2]
                trozo = z[j0:j1 + 1, i0:i1 + 1]
                trozo[dentro] = np.fmax(trozo[dentro], cota[dentro])
        return z


def medir(mallas: dict[str, Malla], huella_4326, lat: float) -> dict | None:
    """Altura sobre el suelo dentro de una huella (geometría shapely en longitud y latitud)."""
    h = shapely.transform(huella_4326, lambda c: np.column_stack(a_mercator(c[:, 0], c[:, 1])))
    estira = 1 / math.cos(math.radians(lat))          # un metro real mide esto en Web Mercator
    m, paso = MARGEN_M * estira, PASO_M * estira
    bx0, by0, bx1, by1 = h.bounds
    x0, y0, x1, y1 = bx0 - m, by0 - m, bx1 + m, by1 + m
    z = None
    for zona, (sur, norte) in ZONAS.items():
        if sur <= (y0 + y1) / 2 <= norte:
            z = mallas[zona].rejilla(x0, y0, x1, y1, paso)
            if np.isfinite(z).mean() > 0.5:
                break
    if z is None or np.isfinite(z).mean() <= 0.5:
        return None
    ny, nx = z.shape
    gx, gy = np.meshgrid(x0 + (np.arange(nx) + 0.5) * paso, y0 + (np.arange(ny) + 0.5) * paso)
    dentro = shapely.contains_xy(h, gx, gy)
    alrededor = shapely.contains_xy(h.buffer(m * 0.9), gx, gy) & ~shapely.contains_xy(h.buffer(m * 0.2), gx, gy)
    if not np.isfinite(z[alrededor]).any() or not np.isfinite(z[dentro]).any():
        return None
    suelo = float(np.nanpercentile(z[alrededor], 15))
    alturas = z[dentro] - suelo
    alturas = alturas[np.isfinite(alturas)]
    return {"suelo_m": round(suelo, 1), "altura_mediana_m": round(float(np.median(alturas)), 1),
            "altura_p90_m": round(float(np.percentile(alturas, 90)), 1),
            "pct_en_pie": round(100 * float((alturas > ALTO_M).mean()))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--datos", default="datos", help="carpeta con candidatos.geojson y huellas.geojson")
    ap.add_argument("--primeros", type=int, default=10, help="cuántos candidatos, por nota")
    ap.add_argument("--ids", nargs="*", help="identificadores concretos")
    args = ap.parse_args()
    datos = Path(args.datos)
    candidatos = json.loads((datos / "candidatos.geojson").read_text(encoding="utf-8"))["features"]
    huellas = {f["properties"]["id"]: shape(f["geometry"]) for f in json.loads((datos / "huellas.geojson").read_text(encoding="utf-8"))["features"]}
    candidatos = [c for c in candidatos if c["properties"]["id"] in huellas]
    if args.ids:
        candidatos = [c for c in candidatos if c["properties"]["id"] in set(args.ids)]
    else:
        candidatos.sort(key=lambda c: -float(c["properties"].get("puntuacion") or 0))
        candidatos = candidatos[:args.primeros]
    sesion = requests.Session()
    sesion.headers["User-Agent"] = "osintmaps (experimento de alturas)"
    mallas = {zona: Malla(sesion, zona) for zona in ZONAS}
    print(f"{'nota':>5}  {'mediana':>7}  {'p90':>5}  {'% en pie':>8}  {'seg':>4}  nombre")
    for c in candidatos:
        p = c["properties"]
        lon, lat = c["geometry"]["coordinates"][:2]
        t0 = time.time()
        try:
            r = medir(mallas, huellas[p["id"]], lat)
        except requests.RequestException as e:
            print(f"{p.get('puntuacion', 0):5.1f}  fallo de red: {e}")
            continue
        nombre = (p.get("nombre") or f"{p.get('categoria')} en {p.get('municipio')}")[:40]
        if r is None:
            print(f"{p.get('puntuacion', 0):5.1f}  {'sin malla':>31}  {nombre}")
        else:
            print(f"{p.get('puntuacion', 0):5.1f}  {r['altura_mediana_m']:7.1f}  {r['altura_p90_m']:5.1f}  {r['pct_en_pie']:8d}  {time.time() - t0:4.1f}  {nombre}")


if __name__ == "__main__":
    main()
