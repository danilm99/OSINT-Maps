"""El pulso dentro de «osintmaps servir»: lo pone en marcha y contesta a /vivo/pulso/...

    /vivo/pulso/estado      qué fuentes hay, cuándo contestó cada una, cuánto hay guardado
    /vivo/pulso/resumen     un trozo del histórico (ver resumen.py): ?desde=&hasta=&paso=&puntos=&rastros=
    /vivo/pulso/punto       la historia de un punto: ?serie=bicis&id=12&desde=&hasta=

La sala de control (sala.py) contesta a /vivo/sala/... con lo que monta encima de esto.

Las horas van en segundos desde 1970. Sin `desde` y `hasta` se dan las últimas 48 horas.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs

from . import FICHERO_HISTORICO, FICHERO_RESUMEN
from .almacen import Almacen
from .anomalias import Normales
from .catalogo import FUENTES, INDICADORES, SERIES
from .publicar import Publicador, repositorio_de
from .recolector import Recolector
from .resumen import crear_resumen, paso_para, resumen_para_la_web
from .sala import Sala

MAX_DIAS = 400                  # lo más que se deja pedir de una vez


class Pulso:
    """Junta las piezas: el histórico, el recolector y, si se pide, la publicación en la web."""

    def __init__(self, carpeta_datos: Path, *, recoger: bool = True, dias_valores: int = 90, dias_rastros: int = 30):
        self.carpeta_datos = Path(carpeta_datos)
        self.almacen = Almacen(self.carpeta_datos / FICHERO_HISTORICO)
        self.normales = Normales(self.almacen)
        self.recolector = Recolector(self.almacen, dias_valores=dias_valores, dias_rastros=dias_rastros) if recoger else None
        if self.recolector:
            self.recolector.normales = self.normales
        self.publicador: Publicador | None = None
        self._estado: tuple[float, dict] = (0.0, {})
        self._candado = threading.Lock()
        # La sala de control: barrios, cruce y sucesos. Sin recoger, solo consulta lo guardado.
        self.sala = Sala(self, recoger=recoger)

    @classmethod
    def si_hay(cls, carpeta_datos: Path) -> "Pulso | None":
        """Para consultar un histórico ya guardado sin recoger nada nuevo. None si no hay histórico."""
        return cls(carpeta_datos, recoger=False) if (Path(carpeta_datos) / FICHERO_HISTORICO).is_file() else None

    def arrancar(self) -> None:
        if self.recolector:
            self.recolector.arrancar()
            self.sala.arrancar()

    def publicar_cada(self, minutos: float, repo: str | None, carpeta_trabajo: Path, carpeta_programa: Path) -> Publicador:
        """Activa la publicación de los datos en la web. `repo` es la dirección del repositorio; si
        falta, la de la carpeta del programa."""
        self.publicador = Publicador(repo or repositorio_de(carpeta_programa), carpeta_trabajo, self._ficheros_web, minutos)
        self.publicador.arrancar()
        return self.publicador

    def _ficheros_web(self) -> dict[str, bytes]:
        contenido = resumen_para_la_web(self.almacen, self.normales, comparaciones=self.recolector.comparaciones if self.recolector else None)
        # También en la carpeta de datos: así «osintmaps publicar» y «osintmaps sitio» lo llevan.
        temporal = self.carpeta_datos / (FICHERO_RESUMEN + ".parcial")
        temporal.write_bytes(contenido)
        temporal.replace(self.carpeta_datos / FICHERO_RESUMEN)
        ficheros = {FICHERO_RESUMEN: contenido}
        try:
            for nombre, datos in self.sala.ficheros_web().items():
                ficheros[nombre] = datos
                (self.carpeta_datos / nombre).write_bytes(datos)
        except Exception:  # noqa: BLE001  (sin sala se publica al menos el pulso)
            import logging
            logging.getLogger("osintmaps.pulso").warning("No se han podido preparar los datos de la sala", exc_info=True)
        return ficheros

    def parar(self) -> None:
        if self.publicador:
            self.publicador.parar()
        self.sala.parar()
        if self.recolector:
            self.recolector.parar()
        self.almacen.cerrar()

    # ------------------------------------------------------------ respuestas

    def estado(self) -> dict:
        with self._candado:
            if time.monotonic() - self._estado[0] > 5:
                guardado = self.almacen.estado()
                marcha = self.recolector.estado() if self.recolector else {"en_marcha": False, "arrancado": None, "fuentes": [
                    {"id": f.id, "nombre": f.nombre, "cada": f.cada, "origen": f.origen, "fallos_seguidos": 0} for f in FUENTES]}
                for fuente in marcha["fuentes"]:
                    fuente.update(guardado["fuentes"].get(fuente["id"], {}))
                self._estado = (time.monotonic(), {
                    "hay": True, "ahora": guardado["ahora"], "desde": guardado["desde"], "bytes": guardado["bytes"], "sucesos": guardado["sucesos"],
                    "en_marcha": marcha["en_marcha"], "arrancado": marcha["arrancado"], "fuentes": marcha["fuentes"],
                    "publicacion": self.publicador.estado() if self.publicador else None,
                    "comparaciones": self.recolector.comparaciones if self.recolector else [],
                    "indicadores": {k: {"nombre": v["nombre"], "unidad": v["unidad"]} for k, v in INDICADORES.items()}})
            return self._estado[1]

    def resumen(self, q: dict[str, list[str]]) -> dict:
        ahora = int(time.time())
        hasta = min(_entero(q, "hasta", ahora), ahora)
        desde = _entero(q, "desde", hasta - 48 * 3600)
        if not 0 < hasta - desde <= MAX_DIAS * 86400:
            raise ValueError("rango no válido")
        paso = _entero(q, "paso", 0) or paso_para(hasta - desde, 300)
        if (hasta - desde) / paso > 2000:
            raise ValueError("demasiado detalle para ese rango")
        pedidas = (q.get("puntos") or [",".join(SERIES)])[0]
        series = tuple(s for s in pedidas.split(",") if s in SERIES)
        con_rastros = (q.get("rastros") or ["1"])[0] != "0"
        return crear_resumen(self.almacen, self.normales, desde=desde, hasta=hasta, paso=paso, series=series,
                             desde_rastros=None if con_rastros else hasta,
                             comparaciones=self.recolector.comparaciones if self.recolector and hasta >= ahora - 600 else None)

    def punto(self, q: dict[str, list[str]]) -> dict:
        serie, ident = (q.get("serie") or [""])[0], (q.get("id") or [""])[0][:80]
        if serie not in SERIES or not ident:
            raise ValueError("falta la serie o el punto")
        ahora = int(time.time())
        hasta = min(_entero(q, "hasta", ahora), ahora)
        desde = _entero(q, "desde", hasta - 7 * 86400)
        if not 0 < hasta - desde <= MAX_DIAS * 86400:
            raise ValueError("rango no válido")
        fuente = next(f for f in FUENTES if f.id == SERIES[serie])
        ficha = self.almacen.puntos(serie).get(ident, {})
        return {"serie": serie, "id": ident, "nombre": ficha.get("nombre", ""), "cap": ficha.get("cap"), "desde": desde, "hasta": hasta,
                "cambios": self.almacen.historia_de_punto(serie, ident, desde, hasta),
                "cobertura": self.almacen.cobertura(fuente.id, desde, hasta, max(3 * fuente.cada, 600))}


def _entero(q: dict[str, list[str]], clave: str, por_defecto: int) -> int:
    try:
        return int(float(q[clave][0]))
    except (KeyError, IndexError, ValueError):
        return por_defecto


def atender(pulso: "Pulso | None", ruta: str, consulta: str) -> tuple[int, bytes]:
    """Contesta a una dirección /vivo/pulso/...: (código HTTP, cuerpo en JSON)."""
    if pulso is None:
        # No es un error: el visor pregunta para saber si hay histórico, y aquí no lo hay.
        return (200, b'{"hay":false}') if ruta == "/vivo/pulso/estado" else (404, b'{"error":"sin pulso"}')
    q = parse_qs(consulta)
    try:
        if ruta == "/vivo/pulso/estado":
            datos = pulso.estado()
        elif ruta == "/vivo/pulso/resumen":
            datos = pulso.resumen(q)
        elif ruta == "/vivo/pulso/punto":
            datos = pulso.punto(q)
        else:
            return 404, b'{"error":"no existe"}'
    except ValueError as exc:
        return 400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
    return 200, json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
