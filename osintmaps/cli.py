"""Línea de órdenes de OSINT Maps.

    osintmaps municipios 46                 lista municipios de una provincia
    osintmaps buscar --provincia 46         ejecuta la búsqueda completa
    osintmaps capas --provincia 46          refresca las capas extra (Lista Roja, DGT, subastas)
    osintmaps miniaturas --top 50           baja ortofotos de los mejores
    osintmaps historia                      busca en la prensa los sitios con nombre
    osintmaps servir                        abre el mapa en el navegador
    osintmaps servir --pulso                además va guardando el histórico de la ciudad
    osintmaps paquete                       mapa en un solo HTML, para llevar
"""

from __future__ import annotations

import argparse
import functools
import gzip
import http.server
import io
import json
import logging
import sys
import tempfile
import threading
import time
import webbrowser
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, aviones, exportar, fusion, historia, osint, puntuacion
from .fuentes import camaras as fuente_camaras
from .fuentes import catastro, dgt, listaroja, osm, subastas, wikidata
from .geo import parsear_caja
from .modelos import Candidato
import requests

from .red import nueva_sesion

log = logging.getLogger("osintmaps")

CARPETA_WEB = Path(__file__).parent / "web"
MARGEN_CAJA = 0.005   # ~500 m de margen alrededor de la zona


def _decir(mensaje: str) -> None:
    print(mensaje, flush=True)


def _union_cajas(cajas: list[tuple[float, float, float, float]]):
    if not cajas:
        return None
    return (min(c[0] for c in cajas) - MARGEN_CAJA, min(c[1] for c in cajas) - MARGEN_CAJA,
            max(c[2] for c in cajas) + MARGEN_CAJA, max(c[3] for c in cajas) + MARGEN_CAJA)


def _caja_de_candidatos(candidatos: list[Candidato]):
    return _union_cajas([(c.lon, c.lat, c.lon, c.lat) for c in candidatos])


# --------------------------------------------------------------------------
# municipios
# --------------------------------------------------------------------------

# Capas extra: cada una va a datos/capa-<nombre>.geojson y el visor la enseña si existe.
CAPAS_EXTRA = ("listaroja", "dgt", "subastas")
# Capas que no baja «osintmaps capas», sino que saca un programa aparte, y que pueden no estar.
# «posibles» son edificios que parecen haber perdido el tejado (experimentos/vision/cambios.py): sospechas
# sin comprobar, que solo se publican si se pide.
CAPAS_OPCIONALES = ("posibles",)
CAPA_VACIA = '{"type":"FeatureCollection","features":[]}'


def _geojson_de_puntos(puntos: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
         "properties": {k: v for k, v in p.items() if k not in ("lat", "lon")}}
        for p in puntos]}


def descargar_capas(sesion, salida: Path, cache: Path, provincia: str | None, *,
                    usar_cache: bool = True, solo: tuple[str, ...] = CAPAS_EXTRA) -> dict[str, int]:
    """Descarga las capas extra. Una que falle se salta: conserva su fichero anterior."""
    fuentes = {
        "listaroja": ("Lista Roja del Patrimonio", lambda: listaroja.buscar(sesion)),
        "dgt": ("Cámaras de la DGT", lambda: dgt.buscar(sesion)),
    }
    if provincia:
        fuentes["subastas"] = ("Inmuebles en subasta (BOE)", lambda: subastas.buscar(
            sesion, cache / "subastas", provincia, usar_cache=usar_cache, avisar=_decir))
    salida.mkdir(parents=True, exist_ok=True)
    hechas: dict[str, int] = {}
    for nombre, (titulo, obtener) in fuentes.items():
        if nombre not in solo:
            continue
        try:
            puntos = obtener()
        except Exception as exc:  # noqa: BLE001
            log.error("%s falló y se continúa sin ella: %s", titulo, exc)
            continue
        (salida / f"capa-{nombre}.geojson").write_text(
            json.dumps(_geojson_de_puntos(puntos), ensure_ascii=False), encoding="utf-8")
        hechas[nombre] = len(puntos)
        _decir(f"{titulo}: {len(puntos)}.")
    return hechas


def cmd_capas(args: argparse.Namespace) -> int:
    solo = tuple(x.strip() for x in args.solo.split(",")) if args.solo else CAPAS_EXTRA
    desconocidas = set(solo) - set(CAPAS_EXTRA)
    if desconocidas:
        _decir(f"Capas desconocidas: {', '.join(sorted(desconocidas))}. Las que hay: {', '.join(CAPAS_EXTRA)}.")
        return 2
    if "subastas" in solo and not args.provincia:
        _decir("Sin --provincia no se buscan subastas (el resto de capas son de toda España).")
    hechas = descargar_capas(nueva_sesion(), Path(args.salida), Path(args.cache), args.provincia,
                             usar_cache=not args.refrescar, solo=solo)
    return 0 if hechas else 1


def cmd_municipios(args: argparse.Namespace) -> int:
    municipios = catastro.listar_municipios(nueva_sesion(), args.provincia)
    for m in municipios:
        _decir(f"{m.codigo}  {m.nombre}")
    _decir(f"\n{len(municipios)} municipios. El código es el de Catastro (no coincide con el del INE).")
    return 0


# --------------------------------------------------------------------------
# buscar
# --------------------------------------------------------------------------

def cmd_buscar(args: argparse.Namespace) -> int:
    caja = parsear_caja(args.caja) if args.caja else None
    codigos = [c.strip() for c in args.municipios.split(",") if c.strip()] if args.municipios else []
    if not (args.provincia or codigos or caja):
        _decir("Indica una zona: --provincia, --municipios o --caja.")
        return 2

    sesion = nueva_sesion()
    cache = Path(args.cache)
    usar_cache = not args.refrescar

    # 1) Qué municipios de Catastro entran.
    provincias = sorted({c[:2] for c in codigos} | ({args.provincia} if args.provincia else set()))
    municipios: list[catastro.Municipio] = []
    for prov in provincias:
        try:
            lista = catastro.listar_municipios(sesion, prov)
        except Exception as exc:  # noqa: BLE001
            log.error("No se pudo leer el índice de Catastro de la provincia %s: %s", prov, exc)
            continue
        if codigos:
            lista = [m for m in lista if m.codigo in codigos]
        municipios += lista
    if codigos:
        faltan = set(codigos) - {m.codigo for m in municipios}
        if faltan:
            _decir(f"Aviso: códigos no encontrados en Catastro: {', '.join(sorted(faltan))} "
                   "(usa «osintmaps municipios XX» para verlos).")
    caja_municipios = _union_cajas([m.caja for m in municipios if m.caja])

    # 2) Catastro.
    de_catastro: list[Candidato] = []
    procesados: list[catastro.Municipio] = []      # municipios que Catastro leyó sin error
    if args.sin_catastro:
        _decir("Catastro: omitido.")
    elif not municipios:
        _decir("Catastro: sin municipios que procesar (con solo --caja hay que añadir --provincia).")
    else:
        _decir(f"Catastro: {len(municipios)} municipios...")
        hechos = 0

        def avance(mensaje: str) -> None:
            # Con -v se ve cada municipio; sin -v, una línea cada 20 para saber que sigue vivo.
            nonlocal hechos
            hechos += 1
            if args.verbose or hechos % 20 == 0:
                _decir(mensaje)

        de_catastro = list(catastro.buscar(
            sesion, municipios, cache / "catastro",
            min_superficie=args.min_superficie, dist_agrupar=args.dist_agrupar,
            caja=caja, aviso=avance, procesados=procesados,
        ))
        if len(procesados) < len(municipios):
            _decir(f"Aviso: Catastro falló en {len(municipios) - len(procesados)} municipios; "
                   "ahí se conservan todos los edificios de OSM.")
        _decir(f"Catastro: {len(de_catastro)} candidatos.")

    zona = caja or caja_municipios or _caja_de_candidatos(de_catastro)

    # 3) OpenStreetMap.
    de_osm: list[Candidato] = []
    if args.sin_osm:
        _decir("OSM: omitido.")
    else:
        try:
            # Provincia entera: se usa su límite administrativo. Si no, una caja.
            por_provincia = bool(args.provincia) and not codigos and not caja
            if por_provincia:
                de_osm = osm.buscar(sesion, cache / "osm", provincia=args.provincia, usar_cache=usar_cache)
                if not de_osm and zona:
                    _decir("OSM: el límite provincial no devolvió nada; se repite por caja.")
                    por_provincia = False
            if not por_provincia:
                if zona is None:
                    raise RuntimeError("no hay zona definida (añade --caja)")
                de_osm = osm.buscar(sesion, cache / "osm", caja=zona, usar_cache=usar_cache)
            _decir(f"OSM: {len(de_osm)} candidatos.")
        except Exception as exc:  # noqa: BLE001
            log.error("OSM falló y se continúa sin él: %s", exc)

    # 3b) Cámaras de vigilancia de OSM: capa aparte, no se mezcla con los candidatos.
    camaras: list[dict] | None = None
    if args.sin_camaras:
        _decir("Cámaras: omitido.")
    else:
        try:
            if bool(args.provincia) and not codigos and not caja:
                camaras = fuente_camaras.buscar(sesion, cache / "osm", provincia=args.provincia, usar_cache=usar_cache)
            elif zona is not None:
                camaras = fuente_camaras.buscar(sesion, cache / "osm", caja=zona, usar_cache=usar_cache)
            if camaras is not None:
                _decir(f"Cámaras: {len(camaras)} en OpenStreetMap.")
        except Exception as exc:  # noqa: BLE001
            log.error("Las cámaras fallaron y se continúa sin ellas: %s", exc)

    # 4) Wikidata.
    de_wikidata: list[Candidato] = []
    if args.sin_wikidata:
        _decir("Wikidata: omitido.")
    elif zona is None:
        _decir("Wikidata: sin zona definida, omitido.")
    else:
        try:
            de_wikidata = wikidata.buscar(sesion, cache / "wikidata", zona, usar_cache=usar_cache)
            _decir(f"Wikidata: {len(de_wikidata)} candidatos.")
        except Exception as exc:  # noqa: BLE001
            log.error("Wikidata falló y se continúa sin él: %s", exc)

    # 5) Fusión, enlaces y nota.
    # Solo donde Catastro leyó el municipio se puede dar por hecho que un edificio
    # anónimo de OSM es un eco suyo. Un municipio sin caja conocida no se da por cubierto.
    cobertura = [m.caja for m in procesados if m.caja]
    candidatos = fusion.fusionar(de_catastro, de_osm + de_wikidata, cobertura=cobertura)
    if not candidatos:
        # No se escribe nada: así no se pisa un resultado anterior con uno vacío.
        _decir("\nNo se obtuvo ningún candidato. Si arriba hay errores de conexión, revisa la red; "
               "si no, prueba con una zona mayor o baja --min-superficie.")
        return 1
    for c in candidatos:
        c.enlaces = osint.enlaces(c)
    candidatos = puntuacion.puntuar_todos(candidatos)

    # 6) Extras opcionales sobre los mejores.
    if args.ndvi:
        from .imagen import sentinel
        try:
            hechos = sentinel.enriquecer(sesion, candidatos, args.ndvi)
            _decir(f"Sentinel-2: vegetación analizada en {hechos} candidatos.")
            candidatos = puntuacion.puntuar_todos(candidatos)
        except Exception as exc:  # noqa: BLE001
            log.error("Análisis Sentinel-2 omitido: %s", exc)
    if args.fotos:
        osint.enriquecer_con_fotos(sesion, candidatos, args.fotos)
        _decir(f"Commons: fotos buscadas para los {min(args.fotos, len(candidatos))} primeros.")

    if args.min_puntuacion:
        candidatos = [c for c in candidatos if c.puntuacion >= args.min_puntuacion]
    if args.limite:
        candidatos = candidatos[:args.limite]

    # 7) Salida.
    parametros = {k: v for k, v in vars(args).items() if k not in ("func", "orden")}
    resumen = exportar.escribir_todo(candidatos, Path(args.salida), parametros, camaras=camaras)
    if not args.sin_capas:
        provincia = args.provincia or (codigos[0][:2] if codigos else None)
        descargar_capas(sesion, Path(args.salida), cache, provincia, usar_cache=usar_cache)

    _decir(f"\n{resumen['total']} candidatos ({resumen['varias_fuentes']} confirmados por varias fuentes).")
    _decir("Por categoría: " + ", ".join(f"{k} {v}" for k, v in resumen["por_categoria"].items()))
    _decir("\nLos 10 primeros:")
    for c in candidatos[:10]:
        nombre = c.nombre or f"({c.categoria}, {c.municipio or 'sin municipio'})"
        _decir(f"  {c.puntuacion:5.1f}  {nombre}  {c.lat},{c.lon}")
    _decir(f"\nResultados en {Path(args.salida).resolve()}")
    _decir("Para ver el mapa: osintmaps servir")
    return 0


# --------------------------------------------------------------------------
# miniaturas
# --------------------------------------------------------------------------

def _cargar_candidatos(carpeta: Path) -> list[Candidato]:
    ruta = carpeta / "candidatos.geojson"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}. Ejecuta antes «osintmaps buscar».")
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    candidatos = []
    for f in datos["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        candidatos.append(Candidato(id=p["id"], lat=lat, lon=lon, nombre=p.get("nombre"),
                                    superficie_m2=p.get("superficie_m2"), municipio=p.get("municipio"),
                                    wikipedia=p.get("wikipedia"),
                                    puntuacion=p.get("puntuacion", 0)))
    return candidatos


def cmd_historia(args: argparse.Namespace) -> int:
    """Busca en Google Noticias los sitios con nombre y deja lo encontrado en datos/historia.json."""
    carpeta = Path(args.datos)
    candidatos = _cargar_candidatos(carpeta)
    con_nombre = sum(1 for c in candidatos if c.nombre)
    if not con_nombre:
        _decir("Ningún sitio de la lista tiene nombre: no hay nada que buscar en la prensa.")
        return 0
    _decir(f"{con_nombre} de {len(candidatos)} sitios tienen nombre. Se pregunta a Google Noticias uno a uno, "
           f"con {args.pausa:g} s de pausa (lo ya buscado en los últimos {args.dias} días no se repite).")
    r = historia.repasar(nueva_sesion(), candidatos, carpeta / historia.FICHERO, maximo=args.max, pausa=args.pausa,
                         dias=args.dias, rehacer=args.rehacer, decir=_decir)
    _decir(f"Consultados ahora: {r['consultados']}. Con noticias: {r['con_noticias']} de {r['guardados']} guardados. "
           f"Quedan por consultar: {r['pendientes']}.")
    _decir(f"Guardado en {(carpeta / historia.FICHERO).resolve()}. Se ve en la ficha de cada sitio, en «Historia»; "
           "para verlo desde la web, vuelve a publicarla.")
    return 3 if r["bloqueado"] else 0


def cmd_miniaturas(args: argparse.Namespace) -> int:
    from .imagen import pnoa
    candidatos = _cargar_candidatos(Path(args.datos))[:args.top]
    carpeta = Path(args.datos) / "miniaturas"
    capas = tuple(c.strip() for c in args.capas.split(",") if c.strip())
    n = pnoa.descargar_miniaturas(nueva_sesion(), candidatos, carpeta, capas=capas)
    _decir(f"{n} imágenes en {carpeta.resolve()}")
    return 0


# --------------------------------------------------------------------------
# servir
# --------------------------------------------------------------------------

MAX_MARCAS = 2 * 1024 * 1024   # tope de tamaño de marcas.json (2 MB)
_CANDADO_MARCAS = threading.Lock()


def _limpiar_marca(m: dict) -> dict:
    """Marca sobre un candidato. Una marca quitada se guarda vacía, no se borra:
    así el otro dispositivo se entera de que se quitó."""
    return {"estado": str(m.get("estado") or "")[:20], "nota": str(m.get("nota") or "")[:5000]}


def _limpiar_marcador(m: dict) -> dict | None:
    """Marcador propio puesto en el mapa. Uno borrado se conserva con deleted=true
    por el mismo motivo. Sin coordenadas válidas no se guarda."""
    try:
        lat, lng = float(m.get("lat")), float(m.get("lng"))
        creado = int(float(m.get("created") or 0))
    except (TypeError, ValueError, OverflowError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return {"type": str(m.get("type") or "spot")[:20], "lat": round(lat, 6), "lng": round(lng, 6),
            "note": str(m.get("note") or "")[:500], "created": creado, "deleted": bool(m.get("deleted"))}


# Ficheros de datos/ que el visor puede escribir, con la función que valida cada registro.
LIMPIADORES = {"marcas.json": _limpiar_marca, "marcadores.json": _limpiar_marcador}


# Última respuesta de aviones por zona: (momento, contenido). De una en una, para que dos
# peticiones simultáneas por la misma zona no salgan las dos a la red.
_AVIONES: OrderedDict[tuple, tuple[float, bytes]] = OrderedDict()
_CANDADO_AVIONES = threading.Lock()
_RELEVO: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
_CANDADO_RELEVO = threading.Lock()
_CANDADOS_RELEVO: dict[str, threading.Lock] = {}      # uno por clave, para la petición a la web de fuera
VIDA_AVIONES = 15.0      # segundos que se reutiliza una respuesta
# Si Google Noticias contesta «demasiadas peticiones», no se le vuelve a preguntar en un cuarto de hora.
_PAUSA_NOTICIAS = [0.0]  # hasta cuándo (reloj del sistema que nunca retrocede); en una lista para poder cambiarlo desde dentro
ESPERA_TRAS_BLOQUEO = 900.0
VIDA_NOTICIAS = 6 * 3600.0     # segundos que vale lo que contestó Google Noticias sobre un sitio
MAX_ZONAS_AVIONES = 32


# Ficheros que se sirven comprimidos, con su tipo.
TIPOS_COMPRIMIBLES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".geojson": "application/geo+json; charset=utf-8", ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json; charset=utf-8",
}
_COMPRIMIDOS: dict[str, tuple[int, int, bytes]] = {}      # ruta -> (fecha, tamaño, contenido comprimido)
_CANDADO_COMPRIMIDOS = threading.Lock()


def _comprimido(ruta: Path, info) -> bytes:
    """El fichero comprimido con gzip. Se comprime una vez y se guarda en memoria
    mientras el fichero no cambie (comprimir 6 MB cuesta unas décimas de segundo)."""
    clave = str(ruta)
    with _CANDADO_COMPRIMIDOS:
        guardado = _COMPRIMIDOS.get(clave)
        if guardado and guardado[:2] == (info.st_mtime_ns, info.st_size):
            return guardado[2]
    cuerpo = gzip.compress(ruta.read_bytes(), compresslevel=6)
    with _CANDADO_COMPRIMIDOS:
        _COMPRIMIDOS[clave] = (info.st_mtime_ns, info.st_size, cuerpo)
    return cuerpo


class _Servidor(http.server.SimpleHTTPRequestHandler):
    """Sirve el visor web y, bajo /datos/, la carpeta de resultados.

    Además guarda lo que el usuario anota en el visor (marcas sobre los
    candidatos en marcas.json, marcadores propios en marcadores.json), para que
    no dependa del navegador ni del dispositivo.
    """

    carpeta_datos: Path = Path("datos")
    pulso = None        # el histórico de la ciudad (osintmaps.pulso.servidor.Pulso), si lo hay

    def translate_path(self, path: str) -> str:
        limpio = path.split("?", 1)[0].split("#", 1)[0]
        if limpio.startswith(f"/datos/{CARPETA_VISION}/"):
            # La única subcarpeta que se sirve: las líneas detectadas alrededor de cada sitio.
            return str(self.carpeta_datos / CARPETA_VISION / Path(limpio).name)
        if limpio.startswith("/datos/"):
            # Solo el nombre del fichero: impide salirse de la carpeta con "../".
            return str(self.carpeta_datos / Path(limpio).name)
        return super().translate_path(path)

    def end_headers(self) -> None:
        # «no-cache» deja al navegador guardar el fichero, pero le obliga a preguntar cada vez
        # si ha cambiado (ver send_head). Lo que no debe guardarse nunca (respuestas en vivo,
        # lo que el usuario anota) marca _sin_guardar.
        self.send_header("Cache-Control", "no-store" if getattr(self, "_sin_guardar", False) else "no-cache")
        super().end_headers()

    def send_head(self):
        """Sirve los ficheros de texto comprimidos y sin repetir lo que el navegador ya tiene.

        Los datos son varios megas de JSON, que comprimido ocupa la sexta parte: en el
        ordenador da igual, pero desde el móvil por la wifi se nota. Además cada fichero
        lleva su fecha y una «etiqueta» (ETag) hecha con su fecha y su tamaño; el navegador
        las manda de vuelta al recargar y, si coinciden, se le contesta «304: no ha
        cambiado» sin volver a enviarlo.
        """
        self._sin_guardar = self._fichero_editable() is not None
        ruta = Path(self.translate_path(self.path))
        if ruta.is_dir() and urlparse(self.path).path.endswith("/"):
            ruta = ruta / "index.html"       # la portada
        if self._sin_guardar or ruta.suffix.lower() not in TIPOS_COMPRIMIBLES or not ruta.is_file():
            return super().send_head()
        try:
            info = ruta.stat()
        except OSError:
            return super().send_head()
        # Dos formas de preguntar «¿ha cambiado?»: por etiqueta o por fecha. Chrome solo usa la
        # etiqueta con servidores HTTP/1.1 y este contesta en HTTP/1.0, así que se atienden las dos.
        etiqueta = f'"{info.st_mtime_ns:x}-{info.st_size:x}"'
        fecha = self.date_time_string(info.st_mtime)
        la_tiene = self.headers.get("If-None-Match")
        if la_tiene == etiqueta or (la_tiene is None and self.headers.get("If-Modified-Since") == fecha):
            self.send_response(304)
            self.send_header("ETag", etiqueta)
            self.send_header("Last-Modified", fecha)
            self.end_headers()
            return None
        comprimir = "gzip" in self.headers.get("Accept-Encoding", "") and info.st_size >= 1024
        try:
            cuerpo = _comprimido(ruta, info) if comprimir else ruta.read_bytes()
        except OSError:
            self.send_error(404)
            return None
        self.send_response(200)
        self.send_header("Content-Type", TIPOS_COMPRIMIBLES[ruta.suffix.lower()])
        if comprimir:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("ETag", etiqueta)
        self.send_header("Last-Modified", fecha)
        self.end_headers()
        return io.BytesIO(cuerpo)

    def _responder_json(self, codigo: int, cuerpo: bytes) -> None:
        self._sin_guardar = True
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _fichero_editable(self) -> str | None:
        """Nombre del fichero que pide la URL, si es uno de los que el visor puede escribir."""
        nombre = self.path.split("?", 1)[0].removeprefix("/datos/")
        return nombre if nombre in LIMPIADORES else None

    def _aviones(self) -> None:
        """Aviones en vuelo cerca de un punto. Los servicios (adsb.fi, adsb.lol) no admiten que
        una página web les pregunte directamente, así que pregunta el servidor (por osintmaps.aviones,
        que reparte las peticiones y para si un servicio lo pide)."""
        try:
            q = parse_qs(urlparse(self.path).query)
            lat, lon = float(q["lat"][0]), float(q["lon"][0])
            millas = max(1, min(250, int(float(q.get("dist", ["60"])[0]))))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except (KeyError, ValueError, IndexError):
            self.send_error(400)
            return
        clave = (round(lat, 1), round(lon, 1), millas)
        with _CANDADO_AVIONES:
            ahora = time.monotonic()
            guardado = _AVIONES.get(clave)
            if not guardado or ahora - guardado[0] > VIDA_AVIONES:      # como mucho una consulta cada 15 s por zona
                try:
                    datos = aviones.pedir(lat, lon, millas)
                except Exception:  # noqa: BLE001
                    guardado = None
                else:
                    guardado = (time.monotonic(), json.dumps(datos, separators=(",", ":")).encode("utf-8"))
                    # Fuera las caducadas y, si aun así hay demasiadas zonas, la más antigua.
                    for vieja in [k for k, v in _AVIONES.items() if ahora - v[0] > VIDA_AVIONES]:
                        del _AVIONES[vieja]
                    _AVIONES[clave] = guardado
                    _AVIONES.move_to_end(clave)
                    while len(_AVIONES) > MAX_ZONAS_AVIONES:
                        _AVIONES.popitem(last=False)
        if guardado is None:
            self.send_error(502)
            return
        self._responder_json(200, guardado[1])

    def _relevo(self, clave: str, url: str, vida: float, convertir=None, al_fallar=None) -> None:
        """Devuelve como JSON lo que contesta un servicio que no deja que una página web le
        pregunte directamente. Guarda la respuesta `vida` segundos para no repetir la consulta.
        Si la petición falla y se da `al_fallar`, se le pasa el error (para que quien llama decida)."""
        # Dos candados. El general solo se coge un instante, para tocar la tabla de respuestas
        # guardadas. La petición a la web de fuera, que puede tardar 20 segundos, se hace con el
        # candado de su propia clave: dos peticiones de lo mismo no salen dos veces, y una ficha
        # lenta no deja esperando a los trenes ni a las demás fichas.
        with _CANDADO_RELEVO:
            candado = _CANDADOS_RELEVO.setdefault(clave, threading.Lock())
        with candado:
            with _CANDADO_RELEVO:
                guardado = _RELEVO.get(clave)
            if not guardado or time.monotonic() - guardado[0] > vida:
                try:
                    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 OSINT-Maps"})
                    resp.raise_for_status()
                    contenido = convertir(resp) if convertir else resp.content
                except Exception as exc:  # noqa: BLE001
                    guardado = None
                    if al_fallar:
                        al_fallar(exc)
                else:
                    guardado = (time.monotonic(), contenido)
                with _CANDADO_RELEVO:
                    if guardado is None:
                        if clave not in _RELEVO:
                            _CANDADOS_RELEVO.pop(clave, None)      # no se guardó nada: su candado tampoco
                    else:
                        _RELEVO[clave] = guardado
                        _RELEVO.move_to_end(clave)
                        while len(_RELEVO) > 300:
                            vieja, _ = _RELEVO.popitem(last=False)
                            _CANDADOS_RELEVO.pop(vieja, None)
        if guardado is None:
            self.send_error(502)
            return
        self._responder_json(200, guardado[1])

    def _ficha_externa(self) -> None:
        """Foto y descripción de una ficha de Hispania Nostra, sacadas de su página."""
        url = (parse_qs(urlparse(self.path).query).get("url") or [""])[0]
        if not url.startswith("https://listaroja.hispanianostra.org/") or len(url) > 300:
            self.send_error(400)
            return
        self._relevo(f"ficha:{url}", url, 86400, lambda resp: json.dumps(listaroja.detalle(resp.text)).encode("utf-8"))

    def _noticias(self) -> None:
        """Noticias de un sitio en Google Noticias, que solo contesta a programas. Lo mismo que
        hace «osintmaps historia», pero al momento y para el sitio que el visor tiene abierto."""
        q = parse_qs(urlparse(self.path).query)
        nombre = " ".join((q.get("nombre") or [""])[0].split())[:120]
        municipio = " ".join((q.get("municipio") or [""])[0].split())[:80]
        if len(nombre) < 3:
            self.send_error(400)
            return
        clave = f"noticias:{nombre}|{municipio}"
        with _CANDADO_RELEVO:
            guardada = _RELEVO.get(clave)
        fresca = guardada is not None and time.monotonic() - guardada[0] <= VIDA_NOTICIAS
        if not fresca and time.monotonic() < _PAUSA_NOTICIAS[0]:      # Google ha pedido parar hace poco: no se le insiste
            self.send_error(503)
            return

        def convertir(resp) -> bytes:
            return json.dumps({"consulta": historia.consulta_de(nombre, municipio),
                               "noticias": historia.leer_rss(resp.content, nombre, municipio)}, ensure_ascii=False).encode("utf-8")

        def al_fallar(exc: Exception) -> None:
            if getattr(getattr(exc, "response", None), "status_code", None) in (429, 503):
                _PAUSA_NOTICIAS[0] = time.monotonic() + ESPERA_TRAS_BLOQUEO

        self._relevo(clave, historia.direccion(nombre, municipio), VIDA_NOTICIAS, convertir, al_fallar)

    def _pulso(self, ruta: str) -> None:
        """El histórico de la ciudad. Un trozo grande son cientos de KB de cifras: va comprimido."""
        if ruta.startswith("/vivo/sala/"):
            from .pulso.sala import atender as atender_sala
            codigo, cuerpo = atender_sala(getattr(self.pulso, "sala", None), ruta, urlparse(self.path).query)
        else:
            from .pulso.servidor import atender
            codigo, cuerpo = atender(self.pulso, ruta, urlparse(self.path).query)
        comprimir = "gzip" in self.headers.get("Accept-Encoding", "") and len(cuerpo) >= 1024
        if comprimir:
            cuerpo = gzip.compress(cuerpo, compresslevel=5)
        self._sin_guardar = True
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if comprimir:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self) -> None:
        self._sin_guardar = False
        ruta = urlparse(self.path).path
        if ruta == "/vivo/hola":
            # Así sabe el visor que detrás está este programa y no una web estática: puede
            # guardar las notas en disco y pedir lo que una página sola no puede (aviones, trenes).
            self._responder_json(200, json.dumps({"osintmaps": __version__}).encode("utf-8"))
            return
        if ruta == "/vivo/aviones":
            self._aviones()
            return
        if ruta == "/vivo/trenes":
            self._relevo("trenes", "https://gtfsrt.renfe.com/vehicle_positions.json", 15)
            return
        if ruta == "/vivo/ficha":
            self._ficha_externa()
            return
        if ruta == "/vivo/noticias":
            self._noticias()
            return
        if ruta == "/vivo/sala/valorar":           # cambia datos: solo por POST
            self.send_error(405)
            return
        if ruta.startswith("/vivo/pulso/") or ruta.startswith("/vivo/sala/"):
            self._pulso(ruta)
            return
        # Si el fichero aún no existe se responde con un objeto vacío en vez de un
        # 404: así el visor sabe que puede guardar aquí.
        nombre = self._fichero_editable()
        if nombre and not (self.carpeta_datos / nombre).exists():
            self._responder_json(200, b"{}")
            return
        # Lo visto desde el aire es opcional y el visor lo pide siempre: si no está, un objeto
        # vacío en vez de un 404 (que saldría como error en la consola del navegador).
        if ruta in ("/datos/revision.json", f"/datos/{historia.FICHERO}") and not (self.carpeta_datos / Path(ruta).name).exists():
            self._responder_json(200, b"{}")
            return
        if ruta in {f"/datos/capa-{n}.geojson" for n in CAPAS_OPCIONALES} and not (self.carpeta_datos / Path(ruta).name).exists():
            self._responder_json(200, CAPA_VACIA.encode("utf-8"))
            return
        super().do_GET()

    def do_POST(self) -> None:
        """Incorpora al fichero los registros que han cambiado en un dispositivo.

        El visor manda solo lo que cambió, no su copia entera: así ordenador y
        móvil no se pisan aunque uno tenga datos viejos. Con un candado para que
        dos guardados simultáneos no se mezclen.
        """
        # Una página de otro sitio web no debe poder cambiar los datos: los
        # navegadores indican en "Origin" desde dónde se hace la petición.
        origen = self.headers.get("Origin")
        de_fuera = bool(origen) and urlparse(origen).netloc != self.headers.get("Host")
        if urlparse(self.path).path == "/vivo/sala/valorar":      # «confirmado» o «falso positivo» de un suceso de la sala
            if de_fuera:
                self.send_error(403)
            else:
                self._pulso("/vivo/sala/valorar")
            return
        nombre = self._fichero_editable()
        if nombre is None:
            self.send_error(405)
            return
        if de_fuera:
            self.send_error(403)
            return
        try:
            tam = int(self.headers.get("Content-Length", "0"))
            if not 0 < tam <= MAX_MARCAS:
                raise ValueError("tamaño no válido")
            cambios = json.loads(self.rfile.read(tam).decode("utf-8"))
            if not isinstance(cambios, dict):
                raise ValueError("se esperaba un objeto")
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return

        limpiar = LIMPIADORES[nombre]
        ruta = self.carpeta_datos / nombre
        with _CANDADO_MARCAS:
            try:
                guardado = json.loads(ruta.read_text(encoding="utf-8"))
                if not isinstance(guardado, dict):
                    guardado = {}
            except (OSError, ValueError):
                guardado = {}
            for clave, registro in cambios.items():
                limpio = limpiar(registro if isinstance(registro, dict) else {})
                if limpio is not None:
                    guardado[str(clave)[:200]] = limpio
            cuerpo = json.dumps(guardado, ensure_ascii=False, indent=1).encode("utf-8")
            if len(cuerpo) > MAX_MARCAS:
                self.send_error(413)
                return
            self.carpeta_datos.mkdir(parents=True, exist_ok=True)
            # Fichero temporal propio de esta petición y sustitución de una vez:
            # si algo falla a medias, el fichero bueno no se toca.
            with tempfile.NamedTemporaryFile("wb", dir=self.carpeta_datos, prefix="guardando-",
                                             suffix=".parcial", delete=False) as fh:
                fh.write(cuerpo)
            Path(fh.name).replace(ruta)
        self._responder_json(200, cuerpo)

    def log_message(self, formato: str, *args) -> None:  # silencio en la terminal
        pass


class ServidorMapa(http.server.ThreadingHTTPServer):
    """Servidor del mapa.

    El servidor de la biblioteca estándar solo deja 5 conexiones en espera; si
    llegan más de golpe (el navegador pide muchas cosas a la vez, o hay dos
    dispositivos), el sistema rechaza las sobrantes. Se amplía esa cola.
    """

    request_queue_size = 128
    daemon_threads = True


def _ip_local() -> str | None:
    """Dirección de este equipo en la red local (sin enviar nada a nadie)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))     # UDP no manda paquetes al conectar: solo elige la interfaz
            return s.getsockname()[0]
    except OSError:
        return None


def _arrancar_pulso(args: argparse.Namespace):
    """Pone en marcha el histórico de la ciudad si se ha pedido (--pulso); si no, pero ya hay uno
    guardado, lo abre solo para consultarlo."""
    from .pulso.servidor import Pulso
    carpeta = Path(args.datos).resolve()
    if not getattr(args, "pulso", False):
        if getattr(args, "publicar_datos", None) is not None:
            _decir("--publicar-datos solo hace algo junto con --pulso: sin él no hay datos nuevos que subir.")
        return Pulso.si_hay(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    pulso = Pulso(carpeta, dias_valores=args.guardar_dias, ia=not getattr(args, "sin_ia", False))
    pulso.arrancar()
    _decir("Pulso: guardando el histórico de la ciudad mientras esto esté abierto (datos/pulso.sqlite).")
    if args.publicar_datos is not None:
        try:
            publicador = pulso.publicar_cada(args.publicar_datos, args.repo, Path("cache") / "pulso-web", Path.cwd())
        except Exception as exc:  # noqa: BLE001  (sin git o sin repositorio: el mapa funciona igual, sin publicar)
            _decir(f"Pulso: no se publicará en la web ({exc}).")
        else:
            _decir(f"Pulso: la web recibirá los datos al minuto y medio de arrancar y luego cada {publicador.minutos:g} minutos.")
    return pulso


def cmd_servir(args: argparse.Namespace) -> int:
    _Servidor.carpeta_datos = Path(args.datos).resolve()
    _Servidor.pulso = _arrancar_pulso(args)
    manejador = functools.partial(_Servidor, directory=str(CARPETA_WEB))
    # Por defecto, 127.0.0.1: el mapa solo se ve desde este ordenador. Con --red
    # se abre a la red local para usarlo desde el móvil en la misma wifi.
    anfitrion = "0.0.0.0" if args.red else "127.0.0.1"
    with ServidorMapa((anfitrion, args.puerto), manejador) as servidor:
        url = f"http://127.0.0.1:{args.puerto}/"
        _decir(f"Mapa en {url}  (Ctrl+C para parar)")
        if _Servidor.pulso is not None:
            _decir(f"Sala de control en {url}sala.html")
        if getattr(args, "sala", False):
            url += "sala.html"
        if args.red:
            ip = _ip_local()
            _decir(f"Desde el móvil, en la misma wifi: http://{ip or 'IP-DE-ESTE-PC'}:{args.puerto}/")
            _decir("Aviso: mientras esté abierto, cualquiera en esa red puede ver el mapa y cambiar las marcas.")
        if not args.sin_navegador:
            webbrowser.open(url)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            _decir("\nParado.")
        finally:
            if _Servidor.pulso is not None:
                _Servidor.pulso.parar()
                _Servidor.pulso = None
    return 0


# --------------------------------------------------------------------------
# paquete
# --------------------------------------------------------------------------

def _json_para_script(datos) -> str:
    """JSON que se puede pegar dentro de <script> sin que nada lo cierre antes de tiempo."""
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    return (texto.replace("</", "<\\/").replace("<!--", "<\\!--")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def crear_paquete(carpeta_datos: Path, min_puntuacion: float = 0.0) -> str:
    """HTML autónomo: el visor con los datos dentro, para abrirlo sin servidor."""
    datos = json.loads((carpeta_datos / "candidatos.geojson").read_text(encoding="utf-8"))
    datos["features"] = [f for f in datos["features"] if f["properties"].get("puntuacion", 0) >= min_puntuacion]
    ids = {f["properties"]["id"] for f in datos["features"]}
    huellas = {"type": "FeatureCollection", "features": []}
    ruta_huellas = carpeta_datos / "huellas.geojson"
    if ruta_huellas.exists():
        todas = json.loads(ruta_huellas.read_text(encoding="utf-8"))
        huellas["features"] = [f for f in todas["features"] if f["properties"]["id"] in ids]
    pagina = (CARPETA_WEB / "index.html").read_text(encoding="utf-8")
    marca = "<!--DATOS_INCRUSTADOS-->"
    if marca not in pagina:
        raise RuntimeError("El visor no tiene el punto de inserción de datos")
    camaras = {"type": "FeatureCollection", "features": []}
    ruta_camaras = carpeta_datos / "camaras.geojson"
    if ruta_camaras.exists():
        camaras = json.loads(ruta_camaras.read_text(encoding="utf-8"))
    capas = {}
    for nombre in CAPAS_EXTRA:
        ruta = carpeta_datos / f"capa-{nombre}.geojson"
        if ruta.exists():
            capas[nombre] = json.loads(ruta.read_text(encoding="utf-8"))
    revision = None
    ruta_revision = carpeta_datos / "revision.json"
    if ruta_revision.exists():
        revision = json.loads(ruta_revision.read_text(encoding="utf-8"))
        revision["sitios"] = {k: v for k, v in revision.get("sitios", {}).items() if k in ids}
    prensa = None
    ruta_prensa = carpeta_datos / historia.FICHERO
    if ruta_prensa.exists():
        prensa = json.loads(ruta_prensa.read_text(encoding="utf-8"))
        prensa["sitios"] = {k: v for k, v in prensa.get("sitios", {}).items() if k in ids and v.get("noticias")}
    incrustado = ("<script>" + (f"window.OSINT_HISTORIA={_json_para_script(prensa)};" if prensa and prensa["sitios"] else "")
                  + (f"window.OSINT_REVISION={_json_para_script(revision)};" if revision else "")
                  + f"window.OSINT_DATOS={_json_para_script(datos)};"
                  f"window.OSINT_HUELLAS={_json_para_script(huellas)};"
                  f"window.OSINT_CAMARAS={_json_para_script(camaras)};"
                  f"window.OSINT_CAPAS={_json_para_script(capas)};</script>")
    pagina = pagina.replace(marca, incrustado, 1)
    # Los datos van dentro: sobra el trozo que los pide por adelantado al servidor.
    antes, hay, resto = pagina.partition("<!--PRONTO-->")
    if hay and "<!--/PRONTO-->" in resto:
        pagina = antes + resto.split("<!--/PRONTO-->", 1)[1]
    # El resto del programa del visor va en un fichero aparte: dentro también.
    for fichero in ("iconos.js", "capas.js", "herramientas.js", "rutas.js", "vision.js", "historia.js", "tresd.js", "pulso.js"):
        etiqueta = f'<script src="{fichero}"></script>'
        if etiqueta in pagina:
            codigo = (CARPETA_WEB / fichero).read_text(encoding="utf-8").replace("</script", "<\\/script")
            pagina = pagina.replace(etiqueta, f"<script>\n{codigo}\n</script>", 1)
    return pagina


# --------------------------------------------------------------------------
# sitio y publicar: la versión web, sin este ordenador
# --------------------------------------------------------------------------

# Lo que se copia de la carpeta de datos a la web. Las notas (marcas y marcadores propios) solo si se pide.
DATOS_DEL_SITIO = ("candidatos.geojson", "huellas.geojson", "camaras.geojson", *(f"capa-{n}.geojson" for n in CAPAS_EXTRA), "revision.json", historia.FICHERO, "pulso.json",
                   "sala.json", "sala-barrios.json", "sala-perfiles.json", "sala-movilidad.json", "sala-tramos.json")
# Lo que un programa aparte ha visto en la foto aérea alrededor de cada sitio (experimentos/vision):
# revision.json es el resumen y en esta subcarpeta va un fichero de líneas por sitio.
CARPETA_VISION = "vision"
NOTAS_DEL_SITIO = tuple(LIMPIADORES)


def crear_sitio(destino: Path, carpeta_datos: Path | None, con_notas: bool = False, con_posibles: bool = False) -> list[str]:
    """Deja en `destino` el visor como web estática: los ficheros del visor y, bajo datos/,
    los resultados. Vale para cualquier alojamiento de páginas (GitHub Pages, por ejemplo):
    no necesita ningún programa detrás. Devuelve los ficheros de datos que ha copiado."""
    import shutil

    destino.mkdir(parents=True, exist_ok=True)
    for fichero in CARPETA_WEB.iterdir():
        if fichero.is_file():
            shutil.copy2(fichero, destino / fichero.name)
    (destino / ".nojekyll").write_text("", encoding="utf-8")      # que GitHub no intente procesar la carpeta
    # Un alojamiento de páginas deja que el navegador se quede cada fichero unos minutos sin volver a
    # preguntar. Tras publicar una versión nueva, alguien podría recibir la página nueva con un
    # programa de la anterior. Para evitarlo, la página pide cada programa con una marca de su
    # contenido (capas.js?v=1a2b3c4d): si el contenido cambia, la dirección cambia y se baja de nuevo.
    import hashlib
    for html in sorted(destino.glob("*.html")):        # el visor y la sala de control
        pagina = html.read_text(encoding="utf-8")
        for guion in sorted(destino.glob("*.js")):
            etiqueta = f'<script src="{guion.name}"></script>'
            if etiqueta in pagina:
                marca = hashlib.sha256(guion.read_bytes()).hexdigest()[:10]
                pagina = pagina.replace(etiqueta, f'<script src="{guion.name}?v={marca}"></script>')
        html.write_text(pagina, encoding="utf-8")
    copiados = []
    if carpeta_datos is not None:
        (destino / "datos").mkdir(exist_ok=True)
        for nombre in DATOS_DEL_SITIO + (NOTAS_DEL_SITIO if con_notas else ()):
            origen = carpeta_datos / nombre
            if origen.is_file():
                shutil.copy2(origen, destino / "datos" / nombre)
                copiados.append(nombre)
        for capa in CAPAS_OPCIONALES:
            # El visor las pide siempre: van vacías salvo que se pida publicarlas, para que no den un 404.
            origen = carpeta_datos / f"capa-{capa}.geojson"
            if con_posibles and origen.is_file():
                shutil.copy2(origen, destino / "datos" / origen.name)
                copiados.append(origen.name)
            else:
                (destino / "datos" / origen.name).write_text(CAPA_VACIA, encoding="utf-8")
        lineas = sorted((carpeta_datos / CARPETA_VISION).glob("*.json")) if "revision.json" in copiados else []
        if "revision.json" not in copiados:
            # El visor lo pide siempre: vacío si no se ha pasado el detector, para que no dé un 404.
            (destino / "datos" / "revision.json").write_text("{}", encoding="utf-8")
        if historia.FICHERO not in copiados:
            # Lo mismo con las noticias: vacío si no se ha ejecutado «osintmaps historia».
            (destino / "datos" / historia.FICHERO).write_text("{}", encoding="utf-8")
        if lineas:
            (destino / "datos" / CARPETA_VISION).mkdir(exist_ok=True)
            for origen in lineas:
                shutil.copy2(origen, destino / "datos" / CARPETA_VISION / origen.name)
            copiados.append(f"{CARPETA_VISION}/ ({len(lineas)} sitios)")
    return copiados


def cmd_sitio(args: argparse.Namespace) -> int:
    destino = Path(args.salida)
    datos = None if args.sin_datos else Path(args.datos)
    copiados = crear_sitio(destino, datos, args.con_notas, args.con_posibles)
    _decir(f"Web estática en {destino.resolve()} ({len(copiados)} ficheros de datos: {', '.join(copiados) or 'ninguno'}).")
    _decir("Súbela a cualquier alojamiento de páginas, o usa «osintmaps publicar» para GitHub Pages.")
    return 0


def cmd_publicar(args: argparse.Namespace) -> int:
    """Publica la web en la rama gh-pages del repositorio de GitHub (la que usa GitHub Pages).

    La rama se rehace entera cada vez, con un solo commit: los datos pesan varios megas y así
    el repositorio no crece con cada publicación.
    """
    import subprocess

    def git(*orden: str, carpeta: Path | None = None) -> str:
        r = subprocess.run(["git", *orden], cwd=carpeta, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(orden[:2])} ha fallado: {(r.stderr or r.stdout).strip()[:300]}")
        return r.stdout.strip()

    repo = args.repo or git("remote", "get-url", "origin")
    datos = None if args.sin_datos else Path(args.datos)
    with tempfile.TemporaryDirectory(prefix="osintmaps-sitio-") as tmp:
        sitio = Path(tmp)
        copiados = crear_sitio(sitio, datos, args.con_notas, args.con_posibles)
        git("init", "-q", "-b", "gh-pages", carpeta=sitio)
        git("add", "-A", carpeta=sitio)
        git("-c", "user.name=OSINT Maps", "-c", "user.email=osintmaps@users.noreply.github.com", "commit", "-q", "-m",
            f"Web publicada el {time.strftime('%Y-%m-%d %H:%M')}", carpeta=sitio)
        git("push", "-q", "--force", repo, "gh-pages", carpeta=sitio)
    _decir(f"Publicado en la rama gh-pages de {repo} ({len(copiados)} ficheros de datos{', con tus notas' if args.con_notas else ''}).")
    _decir("La primera vez hay que activar GitHub Pages en el repositorio: Settings, Pages, Branch: gh-pages.")
    _decir("Una web en GitHub Pages la puede abrir cualquiera que tenga la dirección.")
    return 0


def cmd_paquete(args: argparse.Namespace) -> int:
    carpeta = Path(args.datos)
    if not (carpeta / "candidatos.geojson").exists():
        raise FileNotFoundError(f"No existe {carpeta / 'candidatos.geojson'}. Ejecuta antes «osintmaps buscar».")
    destino = Path(args.salida) if args.salida else carpeta / "mapa.html"
    destino.write_text(crear_paquete(carpeta, args.min_puntuacion), encoding="utf-8")
    _decir(f"Mapa autónomo en {destino.resolve()} ({destino.stat().st_size / 1e6:.1f} MB).")
    _decir("Ábrelo con doble clic o pásalo al móvil. Necesita internet para las ortofotos.")
    return 0


# --------------------------------------------------------------------------
# Definición de argumentos
# --------------------------------------------------------------------------

def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osintmaps",
        description="Mapa OSINT: sitios abandonados, cámaras y más capas de datos abiertos, en un visor web.",
    )
    parser.add_argument("--version", action="version", version=f"osintmaps {__version__}")
    sub = parser.add_subparsers(dest="orden", required=True)

    p = sub.add_parser("municipios", help="lista los municipios de una provincia y su código de Catastro")
    p.add_argument("provincia", help="código de provincia de 2 cifras (46 = Valencia)")
    p.set_defaults(func=cmd_municipios)

    p = sub.add_parser("buscar", help="ejecuta la búsqueda y genera los resultados")
    zona = p.add_argument_group("zona (al menos una)")
    zona.add_argument("--provincia", help="código de provincia de 2 cifras (46 = Valencia)")
    zona.add_argument("--municipios", help="códigos de Catastro separados por comas (ver «municipios»)")
    zona.add_argument("--caja", help="oeste,sur,este,norte en grados; recorta la zona")
    filtros = p.add_argument_group("filtros")
    filtros.add_argument("--min-superficie", type=float, default=150.0,
                         help="superficie mínima en planta de un conjunto de Catastro, m² (150)")
    filtros.add_argument("--dist-agrupar", type=float, default=25.0,
                         help="distancia para juntar edificios en un mismo conjunto, m (25)")
    filtros.add_argument("--min-puntuacion", type=float, default=0.0, help="descarta por debajo de esta nota")
    filtros.add_argument("--limite", type=int, default=0, help="se queda solo con los N mejores")
    fuentes = p.add_argument_group("fuentes")
    fuentes.add_argument("--sin-catastro", action="store_true")
    fuentes.add_argument("--sin-osm", action="store_true")
    fuentes.add_argument("--sin-wikidata", action="store_true")
    fuentes.add_argument("--sin-camaras", action="store_true", help="no descarga las cámaras de vigilancia de OSM")
    fuentes.add_argument("--sin-capas", action="store_true",
                         help="no descarga las capas extra (Lista Roja, cámaras DGT, subastas)")
    extras = p.add_argument_group("extras (sobre los N mejores)")
    extras.add_argument("--fotos", type=int, default=0, metavar="N",
                        help="busca fotos cercanas en Wikimedia Commons")
    extras.add_argument("--ndvi", type=int, default=0, metavar="N",
                        help="EXPERIMENTAL: avance de vegetación con Sentinel-2")
    p.add_argument("--salida", default="datos", help="carpeta de resultados (datos)")
    p.add_argument("--cache", default="cache", help="carpeta de descargas (cache)")
    p.add_argument("--refrescar", action="store_true", help="ignora la caché de OSM y Wikidata")
    p.add_argument("-v", "--verbose", action="store_true", help="muestra el avance municipio a municipio")
    p.set_defaults(func=cmd_buscar)

    p = sub.add_parser("capas", help="descarga solo las capas extra: Lista Roja, cámaras DGT y subastas")
    p.add_argument("--provincia", help="código de provincia de 2 cifras, para las subastas")
    p.add_argument("--solo", help=f"lista separada por comas: {', '.join(CAPAS_EXTRA)}")
    p.add_argument("--salida", default="datos", help="carpeta de resultados (datos)")
    p.add_argument("--cache", default="cache", help="carpeta de descargas (cache)")
    p.add_argument("--refrescar", action="store_true", help="vuelve a leer las subastas ya guardadas")
    p.set_defaults(func=cmd_capas)

    p = sub.add_parser("miniaturas", help="descarga ortofotos PNOA de los mejores candidatos")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--capas", default="actual,PNOA2006,AMS_1956-1957",
                   help="capas separadas por comas (actual o una del PNOA histórico)")
    p.add_argument("--datos", default="datos")
    p.set_defaults(func=cmd_miniaturas)

    p = sub.add_parser("historia", help="busca en la prensa (Google Noticias) los sitios con nombre")
    p.add_argument("--datos", default="datos", help="carpeta con los resultados")
    p.add_argument("--max", type=int, default=None, help="como mucho, tantos sitios en esta tanda (por defecto, todos los que falten)")
    p.add_argument("--pausa", type=float, default=5.0, help="segundos entre una pregunta y la siguiente")
    p.add_argument("--dias", type=int, default=30, help="no repetir lo consultado hace menos de estos días")
    p.add_argument("--rehacer", action="store_true", help="volver a consultar todos, aunque sean recientes")
    p.set_defaults(func=cmd_historia)

    p = sub.add_parser("servir", help="abre el mapa web con los resultados")
    p.add_argument("--puerto", type=int, default=8000)
    p.add_argument("--datos", default="datos")
    p.add_argument("--sin-navegador", action="store_true")
    p.add_argument("--red", action="store_true", help="lo abre a la red local, para usarlo desde el móvil")
    p.add_argument("--pulso", action="store_true",
                   help="va guardando el histórico de la ciudad (bicis, aparcamientos, tráfico, aire, aviones, trenes) mientras esté abierto")
    p.add_argument("--publicar-datos", type=float, nargs="?", const=15.0, default=None, metavar="MINUTOS",
                   help="con --pulso: sube a la web el resumen de las últimas horas al arrancar y cada MINUTOS (15 si no se dice; mínimo 10)")
    p.add_argument("--guardar-dias", type=int, default=90, help="con --pulso: días que se conserva el detalle punto a punto (90; 0 = siempre)")
    p.add_argument("--repo", default=None, help="con --publicar-datos: dirección del repositorio (por defecto, el «origin» de esta carpeta)")
    p.add_argument("--sala", action="store_true", help="abrir en el navegador la sala de control en vez del mapa")
    p.add_argument("--sin-ia", action="store_true",
                   help="con --pulso: no usar la IA local (Ollama) aunque esté instalada; la sala funciona igual, con reglas")
    p.set_defaults(func=cmd_servir)

    p = sub.add_parser("sitio", help="deja el mapa como web estática en una carpeta, para alojarla donde quieras")
    p.add_argument("--salida", default="sitio", help="carpeta donde dejar la web (por defecto: sitio)")
    p.add_argument("--datos", default="datos", help="carpeta con los resultados (por defecto: datos)")
    p.add_argument("--sin-datos", action="store_true", help="solo el visor, sin ningún resultado")
    p.add_argument("--con-notas", action="store_true", help="incluye también tus marcas y tus marcadores")
    p.add_argument("--con-posibles", action="store_true", help="incluye también la capa de edificios que han perdido el tejado (sospechas sin comprobar)")
    p.set_defaults(func=cmd_sitio)

    p = sub.add_parser("publicar", help="publica la web en GitHub Pages (rama gh-pages del repositorio)")
    p.add_argument("--datos", default="datos", help="carpeta con los resultados (por defecto: datos)")
    p.add_argument("--sin-datos", action="store_true", help="solo el visor, sin ningún resultado")
    p.add_argument("--con-notas", action="store_true", help="incluye también tus marcas y tus marcadores")
    p.add_argument("--con-posibles", action="store_true", help="incluye también la capa de edificios que han perdido el tejado (sospechas sin comprobar)")
    p.add_argument("--repo", default=None, help="dirección del repositorio (por defecto, el «origin» de esta carpeta)")
    p.set_defaults(func=cmd_publicar)

    p = sub.add_parser("paquete", help="crea un único HTML con el mapa y los datos dentro")
    p.add_argument("--datos", default="datos")
    p.add_argument("--salida", help="fichero de destino (por defecto, datos/mapa.html)")
    p.add_argument("--min-puntuacion", type=float, default=0.0, help="incluye solo candidatos desde esta nota")
    p.set_defaults(func=cmd_paquete)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = crear_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _decir("\nInterrumpido.")
        return 130
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        _decir(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
