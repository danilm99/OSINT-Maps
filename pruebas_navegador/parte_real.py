"""El parte de la IA con los datos de verdad y el modelo de verdad, sin tocar el programa que está en marcha.

Copia el histórico (pulso.sqlite) y el mapa de la ciudad a una carpeta temporal, pone el cruce al día, saca
los hechos del parte y le pide el parte al modelo de Ollama varias veces: con la situación de ahora y con dos
inventadas encima (un suceso en marcha; el tráfico de toda la ciudad y el retraso de Cercanías por encima de
lo normal), para ver que no lee las cifras al revés ni le pone a una fuente lo que es de otra. Al lado, el
parte de reglas con los mismos hechos. Al acabar borra la copia.

    python parte_real.py [carpeta de datos] [--veces N]

Por defecto la carpeta de datos es la de OSINT-Maps en la carpeta del usuario, y dos partes por situación.
"""
import json, shutil, sqlite3, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from osintmaps.pulso import ia as IA_
from osintmaps.pulso.cruce import BIN
from osintmaps.pulso.sala import parte_por_reglas
from osintmaps.pulso.servidor import Pulso

argumentos = sys.argv[1:]
veces = 2
if "--veces" in argumentos:
    i = argumentos.index("--veces")
    veces = int(argumentos[i + 1])
    del argumentos[i:i + 2]
origen = Path(argumentos[0]) if argumentos else Path.home() / "OSINT-Maps" / "datos"
copia = Path(tempfile.mkdtemp(prefix="osintmaps-parte-"))
pulso = None
try:
    fuente = sqlite3.connect(f"file:{(origen / 'pulso.sqlite').as_posix()}?mode=ro", uri=True)
    destino = sqlite3.connect(copia / "pulso.sqlite")
    fuente.backup(destino)
    destino.close(); fuente.close()
    shutil.copytree(origen / "ciudad", copia / "ciudad")
    pulso = Pulso(copia, recoger=False, ia=False)
    sala = pulso.sala
    assert sala.cruce is not None, "sin mapa de barrios"
    ahora = int(time.time())
    t0 = time.time()
    sala.cruce.reconstruir(ahora - 3 * 3600, ahora // BIN * BIN, sucesos_desde=ahora - 3 * 3600)
    if not sala.cruce.estado.get("barrios"):
        sala.cruce.paso(ahora // BIN * BIN)
    print(f"cruce al día en {time.time() - t0:.1f} s", flush=True)
    d = sala.datos_del_parte()
    ia = IA_.IA(pulso.almacen, sala.cruce, sala.zonas)
    assert ia.disponible(), "Ollama no contesta o no tiene ningún modelo"
    situaciones = {
        "ahora": d,
        "con un suceso en marcha": d | {"sucesos_activos": [{
            "titulo": "Incidente en Russafa", "desde": time.strftime("%H:%M", time.localtime(ahora - 1500)), "puntuacion": 9.1,
            "resumen": "Dos helicópteros sobre Russafa y varias publicaciones que hablan de humo en la calle Sueca; "
                       "dos tramos de calle cortados cerca. Causa sin confirmar."}]},
        "con atasco y retrasos": d | {"ciudad_fuera_de_lo_normal": [
            {"nombre": "Tráfico", "valor": 38.0, "unidad": "sobre 100", "normal": 12.0, "z": 4.2, "nota": "0 es todo fluido y 100 todo congestionado"},
            {"nombre": "Retraso medio de Cercanías", "valor": 9.5, "unidad": "min", "normal": 1.5, "z": 3.4, "nota": None}]},
    }
    for nombre, datos in situaciones.items():
        print(f"\n== {nombre}\nhechos para el modelo:", json.dumps(IA_.hechos_del_parte(datos), ensure_ascii=False, indent=1))
        print("\nreglas:", parte_por_reglas(datos), flush=True)
        for _ in range(veces):
            ia.parte = None
            t0 = time.time()
            ia._escribir_parte(datos)
            print(f"\nIA ({ia.modelo}, {time.time() - t0:.1f} s):", ia.parte["texto"] if ia.parte else "(nada)", flush=True)
finally:
    if pulso is not None:
        pulso.almacen.cerrar()
    shutil.rmtree(copia, ignore_errors=True)
