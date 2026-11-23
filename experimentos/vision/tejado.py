"""Un detector de «aquí hay tejado» que vale para las fotos de cualquier año. En pruebas.

El detector de líneas aprendió solo con la foto de 2025, y entre años no es comparable: un mismo tejado
entero le sale 0,8 unos años y 0,1 otros. Este aprende con todas a la vez. Las fotos son los recortes en
infrarrojo que `cambios.py medir --guardar-fotos` dejó en disco (50 cm por punto, de 2017 a 2025) y la
etiqueta, los contornos de Catastro: no hay que dibujar nada a mano.

    python tejado.py entrenar --carpeta cache/_vision --catastro cache/catastro --tandas godella:46137,betera:46072
    python tejado.py medir    --carpeta cache/_vision --catastro cache/catastro --municipios 46137 --todos --etiqueta godella

`medir` deja `cambios/tejados-<etiqueta>.json`: qué parte de cada contorno se ve como tejado, año a año.
`cambios.py puntuar` lo usa si existe.

Lo que la etiqueta tiene de malo, a sabiendas: Catastro va con retraso (derribos y obras nuevas), algunos
contornos están corridos y un tejado bajo un pino figura como tejado aunque no se vea. Son pocos frente
al total, y los que Catastro da por ruinosos o deficientes no cuentan ni a favor ni en contra."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import shapely
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cambios as K  # noqa: E402

LADO = 512
PASO = 0.5                       # metros por píxel de los recortes guardados
SIN_OPINION = 255                # píxeles que no cuentan al aprender


def origen_de(clave: str) -> tuple[float, float] | None:
    """Esquina de abajo a la izquierda del recorte de la rejilla con esa clave («i_j»). None para los recortes sueltos."""
    partes = clave.split("_")
    if len(partes) != 2 or not all(p.lstrip("-").isdigit() for p in partes):
        return None
    return int(partes[0]) * K.CELDA_M - K.MARGEN_M, int(partes[1]) * K.CELDA_M - K.MARGEN_M


def leer_recorte(ruta: Path) -> np.ndarray | None:
    """Un recorte guardado, en (infrarrojo, rojo, verde)."""
    img = cv2.imdecode(np.fromfile(ruta, np.uint8), cv2.IMREAD_COLOR)
    return None if img is None or img.shape[:2] != (LADO, LADO) else img[:, :, ::-1]


def normalizar(irg: np.ndarray) -> np.ndarray:
    """Cada recorte, a media cero y dispersión uno por canal: así da igual el color con que salió ese vuelo."""
    x = irg.astype(np.float32)
    return (x - x.mean((0, 1), keepdims=True)) / np.maximum(x.std((0, 1), keepdims=True), 1.0)


def pintar(geoms, x0: float, y0: float, valor: int, lienzo: np.ndarray) -> None:
    y1 = y0 + LADO * PASO
    for g in geoms:
        for parte in shapely.get_parts(g):
            a_px = lambda coords: np.column_stack([(np.asarray(coords)[:, 0] - x0) / PASO, (y1 - np.asarray(coords)[:, 1]) / PASO]).round().astype(np.int32)   # noqa: E731
            cv2.fillPoly(lienzo, [a_px(parte.exterior.coords)], valor)
            for hueco in parte.interiors:
                cv2.fillPoly(lienzo, [a_px(hueco.coords)], 0)


def etiqueta_de(arbol: STRtree, geoms: list, dudosos: np.ndarray, x0: float, y0: float) -> np.ndarray:
    """La etiqueta de un recorte: 1 donde Catastro tiene un edificio, 0 donde no, y «sin opinión» en el borde de cada
    contorno (el tejado baila un metro de un año a otro) y en los edificios que Catastro da por ruinosos o deficientes."""
    dentro = arbol.query(shapely.box(x0, y0, x0 + LADO * PASO, y0 + LADO * PASO))
    tejado = np.zeros((LADO, LADO), np.uint8)
    pintar([geoms[k] for k in dentro if not dudosos[k]], x0, y0, 1, tejado)
    duda = np.zeros((LADO, LADO), np.uint8)
    pintar([geoms[k] for k in dentro if dudosos[k]], x0, y0, 1, duda)
    nucleo = np.ones((3, 3), np.uint8)
    borde = (cv2.dilate(tejado, nucleo) > 0) & ~(cv2.erode(tejado, nucleo) > 0)
    etiqueta = tejado.copy()
    etiqueta[borde | (cv2.dilate(duda, nucleo) > 0)] = SIN_OPINION
    return etiqueta


def edificios_de(catastro: Path, municipio: str) -> tuple[list, np.ndarray]:
    """Lo que levanta del suelo de todos los edificios de un municipio, y cuáles da Catastro por ruinosos o deficientes."""
    ruta = catastro / f"{municipio}.zip"
    piezas = K.leer_piezas(ruta)
    geoms, dudosos = [], []
    for e in K.leer_edificios(ruta):
        geom = piezas[e["ref"]][0] if e["ref"] in piezas else e["geom"]
        if geom.geom_type in ("Polygon", "MultiPolygon") and not geom.is_empty:
            geoms.append(geom)
            dudosos.append(e["estado"] != "functional")
    return geoms, np.array(dudosos, bool)


def recortes_guardados(base: Path, etiqueta: str) -> list[tuple[int, str, Path]]:
    """(año, clave, fichero) de los recortes de la rejilla guardados de una tanda."""
    salida = []
    for carpeta in sorted((base / "cambios" / f"fotos-{etiqueta}").glob("*")):
        if carpeta.is_dir() and carpeta.name.isdigit():
            salida += [(int(carpeta.name), f.stem, f) for f in sorted(carpeta.glob("*.jpg")) if origen_de(f.stem)]
    return salida


def aparte(clave: str) -> bool:
    """Uno de cada diez recortes (los mismos todos los años) se aparta para examinar."""
    i, j = (int(p) for p in clave.split("_"))
    return (i * 31 + j * 17) % 10 == 0


def crear_modelo(pesos: str | None = "imagenet"):
    import segmentation_models_pytorch as smp
    return smp.Unet("resnet34", encoder_weights=pesos, in_channels=3, classes=1)


def cargar_modelo(base: Path, nombre: str, cpu: bool = False):
    import torch
    guardado = torch.load(base / "modelos" / f"{nombre}.pt", map_location="cpu", weights_only=False)
    dispositivo = torch.device("cuda" if torch.cuda.is_available() and not cpu else "cpu")
    modelo = crear_modelo(None)
    modelo.load_state_dict(guardado["modelo"])
    return modelo.to(dispositivo).eval(), dispositivo, guardado


class Recortes:
    """Los recortes y sus etiquetas tal como los pide el cargador de PyTorch. A nivel de módulo: en Windows cada obrero es
    un proceso aparte que tiene que poder importarla."""

    def __init__(self, lista, variar: bool):
        self.lista, self.variar = lista, variar

    def __len__(self) -> int:
        return len(self.lista)

    def __getitem__(self, k: int):
        import torch
        fichero, etiqueta, _ = self.lista[k]
        irg = leer_recorte(fichero)
        if irg is None:
            irg, etiqueta = np.zeros((LADO, LADO, 3), np.uint8), np.full((LADO, LADO), SIN_OPINION, np.uint8)
        x = irg.astype(np.float32)
        if self.variar:
            azar = np.random.default_rng()
            # Como si fuera otro vuelo: cada canal con otra ganancia y otro fondo, y otro contraste.
            x = np.clip(x * azar.uniform(0.75, 1.3, 3).astype(np.float32) + azar.uniform(-20, 20, 3).astype(np.float32), 0, 255)
            x = 255 * (x / 255) ** float(azar.uniform(0.75, 1.35))
            giros = int(azar.integers(4))
            x, etiqueta = np.rot90(x, giros), np.rot90(etiqueta, giros)
            if azar.random() < 0.5:
                x, etiqueta = x[:, ::-1], etiqueta[:, ::-1]
        x = normalizar(x)
        return torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1))), torch.from_numpy(np.ascontiguousarray(etiqueta))


def entrenar(args) -> None:
    import torch
    K.no_dormir()
    base = Path(args.carpeta)
    (base / "modelos").mkdir(exist_ok=True)
    muestras = []                                                      # (fichero, etiqueta del recorte, para examen)
    for tanda in args.tandas.split(","):
        etiqueta, municipio = tanda.split(":")
        geoms, dudosos = edificios_de(Path(args.catastro), municipio)
        arbol = STRtree(geoms)
        etiquetas = {}
        for anio, clave, fichero in recortes_guardados(base, etiqueta):
            if clave not in etiquetas:
                etiquetas[clave] = etiqueta_de(arbol, geoms, dudosos, *origen_de(clave))
            muestras.append((fichero, etiquetas[clave], aparte(clave)))
        print(f"{etiqueta}: {len(geoms)} edificios, {len(etiquetas)} recortes distintos", flush=True)
    de_aprender, de_examen = [m for m in muestras if not m[2]], [m for m in muestras if m[2]]
    print(f"{len(de_aprender)} recortes para aprender y {len(de_examen)} para examinar", flush=True)

    dispositivo = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    cargar = dict(batch_size=args.lote, num_workers=args.obreros, pin_memory=True, persistent_workers=args.obreros > 0)
    por_vuelta = min(args.por_vuelta or len(de_aprender), len(de_aprender))
    aprender = torch.utils.data.DataLoader(Recortes(de_aprender, True), drop_last=True,
                                           sampler=torch.utils.data.RandomSampler(de_aprender, replacement=False, num_samples=por_vuelta), **cargar)
    examen = torch.utils.data.DataLoader(Recortes(de_examen[:: max(1, len(de_examen) // args.examen)], False), shuffle=False, **cargar)
    modelo = crear_modelo(None if args.de_cero else "imagenet").to(dispositivo).to(memory_format=torch.channels_last)
    ajuste = torch.optim.AdamW(modelo.parameters(), lr=3e-4, weight_decay=1e-4)
    ritmo = torch.optim.lr_scheduler.OneCycleLR(ajuste, max_lr=6e-4, total_steps=args.vueltas * len(aprender), pct_start=0.15)
    escala = torch.amp.GradScaler("cuda", enabled=dispositivo.type == "cuda")

    def perdida(salida, y):
        cuenta = (y != SIN_OPINION).float()
        meta = (y == 1).float()
        llano = torch.nn.functional.binary_cross_entropy_with_logits(salida, meta, reduction="none")
        p = torch.sigmoid(salida) * cuenta
        dado = 1 - (2 * (p * meta).sum() + 1) / (p.sum() + (meta * cuenta).sum() + 1)
        return (llano * cuenta).sum() / cuenta.sum().clamp(min=1) + dado

    mejor = -1.0
    print(f"{dispositivo} | {args.vueltas} vueltas de {len(aprender)} lotes de {args.lote}", flush=True)
    for vuelta in range(1, args.vueltas + 1):
        modelo.train()
        t0, suma = time.time(), 0.0
        for n, (x, y) in enumerate(aprender, 1):
            x = x.to(dispositivo, non_blocking=True).contiguous(memory_format=torch.channels_last)
            y = y.to(dispositivo, non_blocking=True)
            with torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
                error = perdida(modelo(x)[:, 0].float(), y)
            ajuste.zero_grad(set_to_none=True)
            escala.scale(error).backward()
            escala.step(ajuste)
            escala.update()
            ritmo.step()
            suma += error.item()
            if n % 100 == 0:
                print(f"  vuelta {vuelta}: lote {n}/{len(aprender)}, pérdida {suma / n:.3f}, {time.time() - t0:.0f} s", flush=True)
        modelo.eval()
        ambos = uno = otro = 0
        with torch.no_grad(), torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
            for x, y in examen:
                y = y.to(dispositivo)
                dice = (modelo(x.to(dispositivo).contiguous(memory_format=torch.channels_last))[:, 0] > 0) & (y != SIN_OPINION)
                ambos += int((dice & (y == 1)).sum())
                uno += int(dice.sum())
                otro += int((y == 1).sum())
        acierto, alcance = ambos / max(uno, 1), ambos / max(otro, 1)
        nota = ambos / max(uno + otro - ambos, 1)
        print(f"vuelta {vuelta}: pérdida {suma / len(aprender):.3f}; de lo que marca es edificio el {100 * acierto:.0f} %, de los edificios marca el {100 * alcance:.0f} %, "
              f"solape {nota:.3f}; {time.time() - t0:.0f} s", flush=True)
        if nota > mejor:
            mejor = nota
            provisional = base / "modelos" / f"{args.nombre}.tmp"
            torch.save({"modelo": modelo.state_dict(), "vuelta": vuelta, "solape": nota, "tandas": args.tandas}, provisional)
            provisional.replace(base / "modelos" / f"{args.nombre}.pt")
    print("FIN-ENTRENAR", flush=True)


def interior(geom, x0: float, y0: float) -> tuple[slice, slice, np.ndarray] | None:
    """El interior de un contorno dentro de un recorte (igual que al medir la vegetación): dónde cae y qué píxeles son."""
    y1 = y0 + LADO * PASO
    bx0, by0, bx1, by1 = geom.bounds
    c0, c1 = max(int((bx0 - x0) / PASO) - 2, 0), min(int(math.ceil((bx1 - x0) / PASO)) + 2, LADO)
    f0, f1 = max(int((y1 - by1) / PASO) - 2, 0), min(int(math.ceil((y1 - by0) / PASO)) + 2, LADO)
    if c1 - c0 < 4 or f1 - f0 < 4:
        return None
    mascara = np.zeros((LADO, LADO), np.uint8)
    pintar([geom], x0, y0, 1, mascara)
    mascara = mascara[f0:f1, c0:c1]
    lejos = cv2.distanceTransform(mascara, cv2.DIST_L2, 3) * PASO
    medio_ancho = float(lejos.max())
    if medio_ancho < 2.0:
        return None
    dentro = lejos > min(2.0, max(0.5, 0.3 * medio_ancho))
    return (slice(f0, f1), slice(c0, c1), dentro) if dentro.sum() * PASO * PASO >= 10 else None


def medir(args) -> None:
    """Pasa el detector por los recortes guardados de una tanda y apunta, de cada edificio y año, qué parte se ve como tejado."""
    import torch
    K.no_dormir()
    base = Path(args.carpeta)
    modelo, dispositivo, guardado = cargar_modelo(base, args.nombre, args.cpu)
    universo = K.cargar_universo(args)
    recortes = K.recortes_de(universo)
    lugares = {}                                                       # clave → [(ref, dónde cae, qué píxeles)]
    for clave, (x0, y0, edificios) in recortes.items():
        lugares[clave] = [(e["ref"], hueco) for e in edificios if (hueco := interior(e["geom"], x0, y0)) is not None]
    carpeta = base / "cambios" / f"fotos-{args.etiqueta}"
    pendientes = [(int(c.name), f.stem, f) for c in sorted(carpeta.glob("*")) if c.is_dir() and c.name.isdigit() for f in sorted(c.glob("*.jpg")) if f.stem in lugares]
    print(f"modelo de la vuelta {guardado.get('vuelta')} (solape {guardado.get('solape', 0):.3f}); {len(pendientes)} recortes; {dispositivo}", flush=True)
    salida: dict[str, dict] = defaultdict(dict)
    t0 = time.time()
    with torch.no_grad(), torch.autocast("cuda", enabled=dispositivo.type == "cuda"):
        for k in range(0, len(pendientes), args.lote):
            lote = [(a, c, leer_recorte(f)) for a, c, f in pendientes[k:k + args.lote]]
            lote = [t for t in lote if t[2] is not None and t[2].std() >= 4]
            if not lote:
                continue
            x = torch.from_numpy(np.stack([normalizar(irg).transpose(2, 0, 1) for _, _, irg in lote])).to(dispositivo)
            prob = torch.sigmoid(modelo(x)[:, 0].float()).cpu().numpy()
            for (anio, clave, _), p in zip(lote, prob):
                for ref, (filas, columnas, dentro) in lugares[clave]:
                    salida[ref][str(anio)] = round(float((p[filas, columnas][dentro] > 0.5).mean()), 3)
            if (k // args.lote) % 50 == 49:
                print(f"  {k + len(lote)}/{len(pendientes)} recortes, {time.time() - t0:.0f} s", flush=True)
    (base / "cambios" / f"tejados-{args.etiqueta}.json").write_text(json.dumps(salida, separators=(",", ":")), encoding="utf-8")
    print(f"tejado mirado en {len(salida)} edificios en {time.time() - t0:.0f} s", flush=True)
    # Para saber si vale: cuánto tejado ve en los edificios que Catastro da por buenos y en los que no, y cuánto baila de un año a otro.
    estado = {e["ref"]: e["estado"] for e in universo}
    for nombre, quienes in (("buenos", [r for r in salida if estado.get(r) == "functional"]), ("ruinosos o deficientes", [r for r in salida if estado.get(r) in ("ruin", "declined")])):
        series = [np.array(list(salida[r].values())) for r in quienes if len(salida[r]) >= 5]
        if series:
            medianas = np.array([np.median(s) for s in series])
            print(f"  {nombre}: {len(series)} edificios; tejado visto (mediana de sus años): p10 {np.percentile(medianas, 10):.2f}, p50 {np.percentile(medianas, 50):.2f}, p90 {np.percentile(medianas, 90):.2f}; "
                  f"baile entre años (dispersión típica): {np.median([s.std() for s in series]):.3f}", flush=True)
    print("FIN-MEDIR-TEJADO", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Detector de tejado para fotos de cualquier año.")
    ap.add_argument("paso_a_dar", choices=("entrenar", "medir"))
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--catastro", default="cache/catastro")
    ap.add_argument("--nombre", default="tejado-v1"); ap.add_argument("--tandas", default="godella:46137,betera:46072", help="entrenar: etiqueta:municipio, separadas por comas")
    ap.add_argument("--vueltas", type=int, default=6); ap.add_argument("--lote", type=int, default=12); ap.add_argument("--obreros", type=int, default=6)
    ap.add_argument("--por-vuelta", type=int, default=4000, help="recortes que se ven en cada vuelta (0: todos)"); ap.add_argument("--examen", type=int, default=600, help="recortes del examen de cada vuelta")
    ap.add_argument("--cpu", action="store_true"); ap.add_argument("--de-cero", action="store_true", help="sin partir de lo aprendido con ImageNet")
    # Para medir: los mismos datos que definen la tanda en cambios.py.
    ap.add_argument("--municipios", default=""); ap.add_argument("--etiqueta", default="piloto"); ap.add_argument("--min-superficie", type=float, default=60.0)
    ap.add_argument("--max-vecinos", type=int, default=12); ap.add_argument("--todos", action="store_true")
    args = ap.parse_args()
    {"entrenar": entrenar, "medir": medir}[args.paso_a_dar](args)


if __name__ == "__main__":
    main()
