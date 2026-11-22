"""Escritura de resultados.

- candidatos.geojson  puntos con todos los datos (lo que lee el visor web)
- huellas.geojson     contornos de los edificios (para pintarlos en el mapa)
- candidatos.csv      tabla para abrir en una hoja de cálculo
- candidatos.kml      para abrir en Google Earth y usar su histórico de imágenes
- resumen.json        cuándo y cómo se generó todo
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from shapely.geometry import mapping

from . import __version__
from .modelos import Candidato

ATRIBUCION = (
    "Dirección General del Catastro (edificios INSPIRE); © colaboradores de OpenStreetMap (ODbL); "
    "Wikidata (CC0); ortofotos PNOA CC BY 4.0 scne.es"
)

_COLUMNAS_CSV = ("puntuacion", "nombre", "categoria", "estado", "municipio", "lat", "lon",
                 "superficie_m2", "n_edificios", "anio", "vecinos_150m", "fuentes", "id",
                 "refcat", "google_maps")


def _redondear_coords(obj, decimales: int = 6):
    """Recorta decimales de un GeoJSON: 6 decimales son ~10 cm, de sobra."""
    if isinstance(obj, (list, tuple)):
        return [_redondear_coords(x, decimales) for x in obj]
    if isinstance(obj, float):
        return round(obj, decimales)
    return obj


def geojson_puntos(candidatos: list[Candidato]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c.lon, c.lat]},
                "properties": c.propiedades(),
            }
            for c in candidatos
        ],
    }


def geojson_huellas(candidatos: list[Candidato]) -> dict:
    features = []
    for c in candidatos:
        if c.huella is None or c.huella.is_empty:
            continue
        geometria = mapping(c.huella)
        geometria["coordinates"] = _redondear_coords(geometria["coordinates"])
        features.append({
            "type": "Feature",
            "geometry": geometria,
            "properties": {"id": c.id, "puntuacion": round(c.puntuacion, 1)},
        })
    return {"type": "FeatureCollection", "features": features}


def escribir_csv(candidatos: list[Candidato], ruta: Path) -> None:
    # utf-8-sig añade una marca al principio para que Excel reconozca los acentos.
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh, delimiter=";")
        escritor.writerow(_COLUMNAS_CSV)
        for c in candidatos:
            escritor.writerow([
                round(c.puntuacion, 1), c.nombre or "", c.categoria, c.estado or "",
                c.municipio or "", c.lat, c.lon,
                "" if c.superficie_m2 is None else round(c.superficie_m2),
                c.n_edificios, c.anio or "",
                "" if c.vecinos_150m is None else c.vecinos_150m,
                "+".join(c.fuentes), c.id, c.refcats[0] if c.refcats else "",
                c.enlaces.get("google_maps", ""),
            ])


def _color_kml(puntuacion: float) -> str:
    # KML escribe los colores como aabbggrr (alfa, azul, verde, rojo).
    if puntuacion >= 60:
        return "ff2b2bd9"   # rojo
    if puntuacion >= 50:
        return "ff1e90f0"   # naranja
    return "ff35d0e8"       # amarillo


def kml(candidatos: list[Candidato]) -> str:
    """Documento KML con una carpeta por categoría."""
    por_categoria: dict[str, list[Candidato]] = {}
    for c in candidatos:
        por_categoria.setdefault(c.categoria, []).append(c)

    partes = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
              "<name>OSINT Maps</name>"]
    for categoria in sorted(por_categoria):
        partes.append(f"<Folder><name>{escape(categoria)} ({len(por_categoria[categoria])})</name>")
        for c in por_categoria[categoria]:
            titulo = c.nombre or f"{c.categoria} · {c.municipio or 'sin municipio'}"
            lineas = [
                f"<b>Puntuación:</b> {c.puntuacion:.0f}",
                f"<b>Estado:</b> {escape(c.estado or '?')}",
                f"<b>Fuentes:</b> {escape(', '.join(c.fuentes))}",
            ]
            if c.superficie_m2:
                lineas.append(f"<b>Superficie:</b> {c.superficie_m2:.0f} m² ({c.n_edificios} edif.)")
            if c.anio:
                lineas.append(f"<b>Año:</b> {c.anio}")
            lineas += [f'<a href="{escape(url)}">{escape(nombre)}</a>'
                       for nombre, url in c.enlaces.items()]
            descripcion = "<br>".join(lineas).replace("]]>", "]]&gt;")
            partes.append(
                "<Placemark>"
                f"<name>{escape(f'{c.puntuacion:.0f} · {titulo}')}</name>"
                f"<description><![CDATA[{descripcion}]]></description>"
                f"<Style><IconStyle><color>{_color_kml(c.puntuacion)}</color></IconStyle></Style>"
                f"<Point><coordinates>{c.lon},{c.lat},0</coordinates></Point>"
                "</Placemark>"
            )
        partes.append("</Folder>")
    partes.append("</Document></kml>")
    return "\n".join(partes)


def escribir_todo(candidatos: list[Candidato], carpeta: Path, parametros: dict,
                  camaras: list[dict] | None = None) -> dict:
    """Escribe todos los ficheros de salida y devuelve el resumen.

    `camaras` es None si no se han buscado en esta ejecución: en ese caso se
    conserva el fichero de cámaras que hubiera de antes.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    if camaras is not None:
        from .fuentes.camaras import geojson as geojson_camaras
        (carpeta / "camaras.geojson").write_text(
            json.dumps(geojson_camaras(camaras), ensure_ascii=False), encoding="utf-8")
    (carpeta / "candidatos.geojson").write_text(
        json.dumps(geojson_puntos(candidatos), ensure_ascii=False), encoding="utf-8")
    (carpeta / "huellas.geojson").write_text(
        json.dumps(geojson_huellas(candidatos), ensure_ascii=False), encoding="utf-8")
    escribir_csv(candidatos, carpeta / "candidatos.csv")
    (carpeta / "candidatos.kml").write_text(kml(candidatos), encoding="utf-8")

    resumen = {
        "generado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "version": __version__,
        "parametros": parametros,
        "total": len(candidatos),
        "camaras": None if camaras is None else len(camaras),
        "por_categoria": dict(Counter(c.categoria for c in candidatos).most_common()),
        "por_fuente": dict(Counter(f for c in candidatos for f in c.fuentes).most_common()),
        "varias_fuentes": sum(1 for c in candidatos if len(set(c.fuentes)) > 1),
        "atribucion": ATRIBUCION,
    }
    (carpeta / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen
