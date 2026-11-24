"""Cómo se mueve la ciudad un día cualquiera: los viajes entre distritos, hora a hora.

Sale del estudio de movilidad del Ministerio de Transportes (MITMA), hecho con datos de teléfonos
móviles. El Ministerio publica solo agregados: cuántos viajes hay de una zona a otra en cada hora,
nunca de quién. En València sus zonas son los 19 distritos municipales (4625001 a 4625019); lo de
fuera del municipio se junta aquí en una sola zona, «fuera».

Se bajan unos días sueltos (por defecto, un lunes, un sábado y un domingo de octubre de 2025), se
leen por partes sin descomprimirlos a disco y se guarda solo lo de València en
`datos/ciudad/movilidad.json`:

    {"zonas": {"4625001": {"distrito": "1"}, ..., "fuera": {}},
     "dias": {"2025-10-13": {"tipo": "L", "total": 1234567.0,
                             "horas": [[[origen, destino, viajes], ...] × 24]}}}
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

from .contexto import CARPETA

log = logging.getLogger("osintmaps.pulso")

BASE = "https://movilidad-opendata.mitma.es/estudios_basicos/por-distritos/viajes/ficheros-diarios"
FICHERO = "movilidad.json"
MUNICIPIO = "46250"
DIAS_POR_DEFECTO = (("2025-10-13", "L"), ("2025-10-18", "S"), ("2025-10-19", "D"))
FUERA = "fuera"


def url_del_dia(dia: str) -> str:
    return f"{BASE}/{dia[:7]}/{dia.replace('-', '')}_Viajes_distritos.csv.gz"


def leer_dia(lineas, municipio: str = MUNICIPIO) -> tuple[list[list], float]:
    """De las líneas del CSV del MITMA (separado por «|», con cabecera) -> (24 listas [origen, destino, viajes], total).
    Solo los viajes con origen o destino en el municipio; lo de fuera, como «fuera»."""
    lineas = iter(lineas)
    cabecera = next(lineas).strip().split("|")
    i_hora = cabecera.index("periodo") if "periodo" in cabecera else cabecera.index("hora")
    i_o, i_d, i_v = cabecera.index("origen"), cabecera.index("destino"), cabecera.index("viajes")
    suma: dict[tuple[int, str, str], float] = defaultdict(float)
    for linea in lineas:
        if municipio not in linea:            # casi todas las líneas: fuera sin partirlas
            continue
        c = linea.rstrip("\n").split("|")
        o, d = c[i_o], c[i_d]
        en_o, en_d = o.startswith(municipio), d.startswith(municipio)
        if not (en_o or en_d):
            continue
        try:
            suma[(int(c[i_hora]), o if en_o else FUERA, d if en_d else FUERA)] += float(c[i_v] or 0)
        except (ValueError, IndexError):
            continue
    horas: list[list] = [[] for _ in range(24)]
    for (h, o, d), v in suma.items():
        if 0 <= h < 24:
            horas[h].append([o, d, round(v, 1)])
    for h in horas:
        h.sort(key=lambda x: -x[2])
    return horas, round(sum(suma.values()), 1)


def importar(datos: Path, sesion: requests.Session, dias=DIAS_POR_DEFECTO, forzar: bool = False) -> dict[str, str]:
    """Baja y resume los días que falten. Devuelve qué ha pasado con cada uno."""
    ruta = Path(datos) / CARPETA / FICHERO
    hecho = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {"zonas": {}, "dias": {}}
    estado: dict[str, str] = {}
    for dia, tipo in dias:
        if dia in hecho["dias"] and not forzar:
            estado[dia] = "ya estaba"
            continue
        t0 = time.time()
        try:
            resp = sesion.get(url_del_dia(dia), stream=True, timeout=120)
            resp.raise_for_status()
            resp.raw.decode_content = False
            with gzip.GzipFile(fileobj=resp.raw) as comprimido:
                horas, total = leer_dia(io.TextIOWrapper(comprimido, encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            estado[dia] = f"fallo: {exc}"[:200]
            continue
        hecho["dias"][dia] = {"tipo": tipo, "total": total, "horas": horas, "fuente": "MITMA, estudio de movilidad con big data"}
        for h in horas:
            for o, d, _ in h:
                for z in (o, d):
                    if z not in hecho["zonas"]:
                        hecho["zonas"][z] = {"distrito": str(int(z[len(MUNICIPIO):]))} if z != FUERA else {}
        estado[dia] = f"{total:,.0f} viajes en {time.time() - t0:.0f} s".replace(",", ".")
        temporal = ruta.with_suffix(".parcial")
        temporal.write_text(json.dumps(hecho, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporal.replace(ruta)
    return estado


def leer(datos: Path) -> dict | None:
    ruta = Path(datos) / CARPETA / FICHERO
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def nombre_del_dia(dia: str) -> str:
    d = date.fromisoformat(dia)
    return f"{('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')[d.weekday()]} {d.day}/{d.month}/{d.year}"
