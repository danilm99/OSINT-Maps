"""Encadena los pasos largos en un solo proceso que se puede dejar solo toda la noche.

    entrenar  ->  calibrar  ->  hojas para mirar  ->  detectar en todos los sitios (y empaquetar)

Cada paso es reanudable, así que si el ordenador se reinicia a medias basta con volver a lanzar
esto mismo: el entrenamiento sigue en la vuelta donde iba y el detector se salta los sitios hechos.

    python cadena.py --carpeta cache/_vision --datos datos --modelo lineas-v2 --vueltas 16 --lote 12

Con `--latido` se le da un programa que anota «sigo vivo» (el de la carpeta de trabajo de Claude):
se llama cada cinco minutos mientras el paso en curso siga escribiendo en su registro. Si un paso
se queda mudo media hora, se deja de llamar, para que quien vigile vea que algo va mal."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def latir(programa: str, vivo: dict, parar: threading.Event) -> None:
    """Cada cinco minutos, si el paso ha dicho algo en la última media hora, anota que la cadena sigue."""
    dicho = ""
    while not parar.wait(300):
        if time.time() - vivo["ultima"] > 1800:
            continue
        try:
            nota = [f"cadena: {vivo['paso']}"] if vivo["paso"] != dicho else []       # con nota solo al cambiar de paso
            subprocess.run([sys.executable, programa, *nota], timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            dicho = vivo["paso"]
        except Exception:
            pass


def paso(nombre: str, orden: list[str], vivo: dict, fin: str) -> bool:
    """Lanza un paso, copia lo que va diciendo y devuelve si acabó bien (salida 0 y su línea de fin)."""
    vivo.update(paso=nombre, ultima=time.time())
    print(f"=== {nombre}: {' '.join(orden[1:])}", flush=True)
    proceso = subprocess.Popen([sys.executable, *orden], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    acabado = False
    for linea in proceso.stdout:
        vivo["ultima"] = time.time()
        acabado = acabado or linea.startswith(fin)
        print(linea, end="", flush=True)
    codigo = proceso.wait()
    if codigo != 0 or not acabado:
        print(f"CADENA-FALLO en {nombre} (salida {codigo}, {'con' if acabado else 'sin'} línea de fin)", flush=True)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Entrenar, calibrar, hacer las hojas y pasar el detector, todo seguido.")
    ap.add_argument("--carpeta", default="cache/_vision"); ap.add_argument("--datos", default="datos")
    ap.add_argument("--modelo", default="lineas-v2"); ap.add_argument("--vueltas", type=int, default=16); ap.add_argument("--lote", type=int, default=12)
    ap.add_argument("--cuantos", type=int, default=0, help="detectar solo en los N primeros por nota (0: todos)")
    ap.add_argument("--hasta", choices=("entrenar", "calibrar", "ver", "detectar"), default="detectar", help="último paso que se hace")
    ap.add_argument("--latido", default="", help="programa al que llamar cada cinco minutos para anotar que esto sigue vivo")
    args = ap.parse_args()
    vivo = {"paso": "arranque", "ultima": time.time()}
    parar = threading.Event()
    if args.latido:
        threading.Thread(target=latir, args=(args.latido, vivo, parar), daemon=True).start()
    comun = ["--carpeta", args.carpeta]
    pasos = [
        ("entrenar", [str(AQUI / "entrenar.py"), *comun, "--nombre", args.modelo, "--vueltas", str(args.vueltas), "--lote", str(args.lote)], "FIN-ENTRENAR"),
        ("calibrar", [str(AQUI / "calibrar.py"), *comun, "--modelo", args.modelo], "FIN-CALIBRAR"),
        ("ver", [str(AQUI / "ver.py"), *comun, "--modelo", args.modelo, "--filas", "5"], "FIN-VER"),
        ("detectar", [str(AQUI / "detectar.py"), *comun, "--datos", args.datos, "--modelo", args.modelo, *(["--cuantos", str(args.cuantos)] if args.cuantos else [])], "FIN-DETECTAR"),
    ]
    bien = True
    for nombre, orden, fin in pasos:
        bien = paso(nombre, orden, vivo, fin)
        if not bien or nombre == args.hasta:
            break
    parar.set()
    if args.latido:                                   # un último apunte con cómo ha acabado
        try:
            subprocess.run([sys.executable, args.latido, f"cadena {'terminada' if bien else 'PARADA POR FALLO'} en el paso {vivo['paso']} (modelo {args.modelo})"], timeout=60)
        except Exception:
            pass
    print("FIN-CADENA" if bien else "CADENA-PARADA", flush=True)
    return 0 if bien else 1


if __name__ == "__main__":
    sys.exit(main())
