"""El resumen: un trozo del histórico en la forma que entiende el visor.

Es el mismo formato para las dos versiones:

- con el programa abierto, el visor pide el trozo que quiera (`/vivo/pulso/resumen`), de
  cualquier fecha y con el detalle que haga falta;
- en la web publicada no hay programa al que preguntar, así que se publica un fichero
  (`datos/pulso.json`) con las últimas 48 horas ya resumidas.

Todo va en rejillas regulares (un valor cada `paso` segundos desde `t0`) para que ocupe poco:
no hace falta repetir la hora en cada dato. Donde no hay dato (el programa estaba cerrado,
o la fuente no contestó) va `null`.
"""

from __future__ import annotations

import json
import time

from .almacen import Almacen
from .anomalias import Normales
from .fuentes import FUENTES, INDICADORES, SERIES, Fuente

VERSION = 1
PASOS = (60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400)


def paso_para(duracion: float, tramos: int) -> int:
    """El paso «redondo» más fino con el que `duracion` segundos caben en `tramos` trozos."""
    for paso in PASOS:
        if duracion / paso <= tramos:
            return paso
    return PASOS[-1]


def _numero(v: float | None, decimales: int = 1):
    """Para el JSON: sin decimales de más, y los enteros como enteros."""
    if v is None:
        return None
    r = round(v, decimales)
    return int(r) if r == int(r) else r


def simplificar(linea: list, tolerancia: float = 0.00005) -> list:
    """Quita de una línea los puntos que no cambian su forma (Douglas-Peucker). La tolerancia va en
    grados: 0,00005 son unos cinco metros, menos que el ancho de una calle."""
    if len(linea) <= 2:
        return linea
    (y1, x1), (y2, x2) = linea[0], linea[-1]
    dx, dy = x2 - x1, y2 - y1
    largo2 = dx * dx + dy * dy
    lejos, indice = 0.0, 0
    for i in range(1, len(linea) - 1):
        y, x = linea[i]
        if largo2:
            u = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / largo2))
            d = ((x - x1 - u * dx) ** 2 + (y - y1 - u * dy) ** 2) ** 0.5
        else:
            d = ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
        if d > lejos:
            lejos, indice = d, i
    if lejos <= tolerancia:
        return [linea[0], linea[-1]]
    return simplificar(linea[:indice + 1], tolerancia)[:-1] + simplificar(linea[indice:], tolerancia)


def _cubierto(ratos: list[list[int]], t: int, margen: float) -> bool:
    return any(a <= t <= b + margen for a, b in ratos)


def _indicadores(almacen: Almacen, normales: Normales | None, desde: int, hasta: int, paso: int) -> dict:
    t0 = (desde // paso) * paso
    n = (hasta - t0) // paso + 1
    medias = almacen.indicadores(t0, t0 + n * paso, paso)
    cada = {f.id: f.cada for f in FUENTES}
    claves = {}
    for clave, info in INDICADORES.items():
        serie = medias.get(clave)
        if not serie:
            continue
        decimales = 0 if info.get("entero") else 1
        valores = [_numero(serie.get(t0 + i * paso), decimales) for i in range(n)]
        # Si los tramos son más cortos que lo que tarda la fuente en dar otro dato (tramos de un minuto y una
        # fuente que contesta cada diez), entre dato y dato no hay un hueco: sigue valiendo el anterior. Se
        # arrastra hasta tres veces lo que tarda la fuente, igual que al decidir si un punto tiene dato.
        arrastre, ultimo, hace = int(3 * cada[info["fuente"]] // paso), None, 0
        for i, v in enumerate(valores):
            if v is not None:
                ultimo, hace = v, 0
            elif ultimo is not None and hace < arrastre:
                hace += 1
                valores[i] = ultimo
        entrada = dict(info, v=valores)
        if normales is not None:
            curva = []
            for i in range(n):
                base = normales.normal(clave, t0 + i * paso + paso // 2)
                curva.append(_numero(base[0], decimales) if base and base[2] >= 2 else None)
            if any(x is not None for x in curva):
                entrada["normal"] = curva
        claves[clave] = entrada
    return {"t0": t0, "paso": paso, "n": n, "claves": claves}


def _puntos(almacen: Almacen, serie: str, fuente: Fuente, desde: int, hasta: int, paso: int) -> dict | None:
    t0 = (desde // paso + 1) * paso
    instantes = list(range(t0, hasta + 1, paso))
    if not instantes:
        return None
    rejilla = almacen.valores_en_rejilla(serie, instantes)
    if not rejilla:
        return None
    # Un valor solo vale si la fuente estaba contestando por entonces: si no, es un hueco.
    # (Se perdonan dos tomas seguidas fallidas: lo de hace tres ya no se da por bueno.)
    margen = max(3 * fuente.cada, 600)
    ratos = almacen.cobertura(fuente.id, desde - int(margen), hasta, margen)
    validos = [_cubierto(ratos, t, margen) for t in instantes]
    if not any(validos):
        return None
    fichas = almacen.puntos(serie)
    ids = sorted((i for i in rejilla if i in fichas and fichas[i]["lat"] is not None), key=lambda x: (len(x), x))
    salida = {"t0": t0, "paso": paso, "n": len(instantes), "ids": ids,
              "nombre": [fichas[i]["nombre"] for i in ids],
              "lat": [fichas[i]["lat"] for i in ids], "lon": [fichas[i]["lon"] for i in ids],
              "v": [[_numero(v, 0) if ok else None for v, ok in zip(rejilla[i], validos)] for i in ids]}
    if any(fichas[i]["cap"] for i in ids):
        salida["cap"] = [_numero(fichas[i]["cap"], 0) for i in ids]
    if any(fichas[i]["geo"] for i in ids):
        salida["geo"] = [simplificar(fichas[i]["geo"]) if fichas[i]["geo"] else None for i in ids]
    return salida


def crear_resumen(almacen: Almacen, normales: Normales | None = None, *, desde: int, hasta: int, paso: int | None = None,
                  desde_puntos: int | None = None, pasos_puntos: dict[str, int] | None = None, series: tuple[str, ...] | None = None,
                  desde_rastros: int | None = None, cada_rastro: int | None = None, comparaciones: list[dict] | None = None) -> dict:
    """El resumen de [desde, hasta].

    - `paso`: segundos de cada tramo de los indicadores (si falta, el que deje unos 300 tramos).
    - `desde_puntos`, `pasos_puntos`, `series`: de qué rato, con qué detalle y de qué series se dan
      los valores punto a punto (son lo que más ocupa).
    - `desde_rastros`, `cada_rastro`: lo mismo para los rastros de aviones y trenes.
    """
    desde, hasta = int(desde), int(hasta)
    paso = paso or paso_para(hasta - desde, 300)
    fuentes = {f.id: f for f in FUENTES}
    salida: dict = {"v": VERSION, "generado": int(time.time()), "desde": desde, "hasta": hasta, "fuentes": {}}
    estado = almacen.estado()["fuentes"]
    for f in FUENTES:
        if f.id in estado:
            salida["fuentes"][f.id] = {"nombre": f.nombre, "origen": f.origen, "cada": f.cada, "ultima": estado[f.id]["ultima"],
                                       "cobertura": almacen.cobertura(f.id, desde, hasta, max(3 * f.cada, 600))}
    salida["indicadores"] = _indicadores(almacen, normales, desde, hasta, paso)

    desde_puntos = desde if desde_puntos is None else max(desde, int(desde_puntos))
    salida["puntos"] = {}
    for serie in series if series is not None else tuple(SERIES):
        paso_serie = (pasos_puntos or {}).get(serie) or paso_para(hasta - desde_puntos, 100)
        bloque = _puntos(almacen, serie, fuentes[SERIES[serie]], desde_puntos, hasta, paso_serie)
        if bloque:
            salida["puntos"][serie] = bloque

    desde_rastros = desde if desde_rastros is None else max(desde, int(desde_rastros))
    cada_rastro = cada_rastro or max(40, (hasta - desde_rastros) // 1500)
    salida["rastros"] = {}
    for tipo in ("aviones", "trenes"):
        objetos = almacen.rastros(tipo, desde_rastros, hasta, cada_rastro)
        if objetos:
            salida["rastros"][tipo] = [{"id": ident, "nombre": o["nombre"], "p": o["p"]} for ident, o in objetos.items() if len(o["p"]) > 1 or tipo == "trenes"]
    salida["sucesos"] = almacen.sucesos(desde, hasta)
    if comparaciones is not None:
        salida["ahora"] = comparaciones
    return salida


# Lo que se publica en la web: 48 horas de indicadores y 24 de puntos, con menos detalle en lo que más pesa.
HORAS_WEB, HORAS_PUNTOS_WEB, HORAS_RASTROS_WEB = 48, 24, 3
PASOS_WEB = {"bicis": 900, "parking": 900, "trafico": 900, "aforo": 3600, "aforo_bici": 3600, "no2": 3600, "pm10": 3600, "pm25": 3600, "o3": 3600}


def resumen_para_la_web(almacen: Almacen, normales: Normales | None = None, ahora: int | None = None, comparaciones: list[dict] | None = None) -> bytes:
    """El fichero `pulso.json` que se publica: lo último, en poco sitio."""
    ahora = int(ahora or time.time())
    resumen = crear_resumen(almacen, normales, desde=ahora - HORAS_WEB * 3600, hasta=ahora, paso=600,
                            desde_puntos=ahora - HORAS_PUNTOS_WEB * 3600, pasos_puntos=PASOS_WEB,
                            desde_rastros=ahora - HORAS_RASTROS_WEB * 3600, cada_rastro=40, comparaciones=comparaciones)
    resumen["publicado"] = True
    return json.dumps(resumen, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
