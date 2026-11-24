"""El histórico del pulso: un fichero SQLite en la carpeta de datos.

SQLite viene con Python y es un único fichero: no hay que instalar ni arrancar nada.

Qué se guarda:

- `valores`: lo que marca cada punto fijo, **solo cuando cambia**. Una estación de Valenbisi
  que lleva dos horas con 7 bicis ocupa una fila, no sesenta. Para saber qué marcaba a una
  hora se busca el último cambio anterior.
- `tomas`: cada vez que se ha preguntado a una fuente y si contestó. Es lo que permite
  distinguir «seguía en 7» de «el programa estaba cerrado y no se sabe».
- `indicadores`: las cifras de toda la ciudad, una por toma.
- `rastros`: por dónde ha ido cada avión y cada tren.
- `puntos`: dónde está y cómo se llama cada punto fijo.
- `sucesos`: cuándo un indicador se ha salido de lo normal.

Todas las horas son segundos desde 1970 (hora universal), como números enteros.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .fuentes import Objeto, Punto

ESQUEMA = """
CREATE TABLE IF NOT EXISTS puntos (serie TEXT NOT NULL, id TEXT NOT NULL, nombre TEXT, lat REAL, lon REAL, cap REAL, geo TEXT, visto INTEGER,
    PRIMARY KEY (serie, id)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS valores (serie TEXT NOT NULL, id TEXT NOT NULL, t INTEGER NOT NULL, v REAL,
    PRIMARY KEY (serie, id, t)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS indicadores (clave TEXT NOT NULL, t INTEGER NOT NULL, v REAL NOT NULL,
    PRIMARY KEY (clave, t)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS rastros (tipo TEXT NOT NULL, id TEXT NOT NULL, t INTEGER NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, rumbo REAL, alt REAL, nombre TEXT,
    PRIMARY KEY (tipo, id, t)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS rastros_por_hora ON rastros (tipo, t);
CREATE TABLE IF NOT EXISTS tomas (fuente TEXT NOT NULL, t INTEGER NOT NULL, ok INTEGER NOT NULL, n INTEGER, error TEXT,
    PRIMARY KEY (fuente, t)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS sucesos (clave TEXT NOT NULL, desde INTEGER NOT NULL, hasta INTEGER NOT NULL, valor REAL, normal REAL, z REAL,
    PRIMARY KEY (clave, desde)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, fuente TEXT NOT NULL, t INTEGER NOT NULL, titulo TEXT, texto TEXT, url TEXT,
    lat REAL, lon REAL, barrio TEXT, lugar TEXT, categoria TEXT, urgencia INTEGER, idioma TEXT, extra TEXT, visto INTEGER, ia INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS items_por_hora ON items (t);
CREATE INDEX IF NOT EXISTS items_por_barrio ON items (barrio, t);
CREATE TABLE IF NOT EXISTS agenda (id TEXT PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT, desde INTEGER NOT NULL, hasta INTEGER NOT NULL,
    lat REAL, lon REAL, barrio TEXT, fuente TEXT, url TEXT, extra TEXT, visto INTEGER);
CREATE INDEX IF NOT EXISTS agenda_por_fecha ON agenda (hasta, desde);
CREATE TABLE IF NOT EXISTS rasgos (rasgo TEXT NOT NULL, barrio TEXT NOT NULL, t INTEGER NOT NULL, v REAL NOT NULL,
    PRIMARY KEY (rasgo, barrio, t)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS rasgos_por_hora ON rasgos (t);
CREATE TABLE IF NOT EXISTS muestras (rasgo TEXT NOT NULL, barrio TEXT NOT NULL, franja INTEGER NOT NULL, semana INTEGER NOT NULL, v REAL NOT NULL,
    festivo INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (rasgo, barrio, franja, semana)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS eventos (id TEXT PRIMARY KEY, tipo TEXT, estado TEXT, inicio INTEGER, fin INTEGER, pico INTEGER, puntuacion REAL,
    lat REAL, lon REAL, barrios TEXT, titulo TEXT, resumen TEXT, causa TEXT, evidencias TEXT, actualizado INTEGER);
CREATE INDEX IF NOT EXISTS eventos_por_fecha ON eventos (fin, inicio);
"""


class Almacen:
    """Lee y escribe el histórico. Varios hilos pueden usar el mismo objeto a la vez."""

    def __init__(self, ruta: Path | str):
        self.ruta = str(ruta)
        if self.ruta != ":memory:":
            Path(self.ruta).parent.mkdir(parents=True, exist_ok=True)
        # Una sola conexión para todo, protegida por un candado: las consultas son de milisegundos.
        self._bd = sqlite3.connect(self.ruta, check_same_thread=False, isolation_level=None)
        self._candado = threading.RLock()
        with self._candado:
            if self.ruta != ":memory:":
                # WAL: se puede leer el fichero (hacer una copia, mirarlo con otro programa) mientras se escribe.
                self._bd.execute("PRAGMA journal_mode=WAL")
                self._bd.execute("PRAGMA synchronous=NORMAL")
            self._bd.executescript(ESQUEMA)
        # Lo último guardado de cada punto, para no repetirlo. Arranca vacío: tras abrir el programa la
        # primera toma se guarda entera, y así lo de después de un hueco no depende de lo de antes.
        self._ultimo: dict[tuple[str, str], float] = {}
        self._ultimo_objeto: dict[tuple[str, str], tuple[float, float, int]] = {}
        self._puntos_vistos: dict[tuple[str, str], tuple] = {}

    def cerrar(self) -> None:
        with self._candado:
            self._bd.close()

    # ---------------------------------------------------------------- escribir

    def guardar_toma(self, fuente: str, t: int, toma) -> None:
        """Apunta lo que ha visto una fuente en el momento `t`. Si la toma dice que sus datos son de otro
        momento (el ruido de ayer), los valores y los indicadores van con ese momento; la toma, con `t`."""
        t_toma = t
        t = int(getattr(toma, "momento", None) or t)
        with self._candado:
            try:
                with self._transaccion():
                    for serie, puntos in toma.puntos.items():
                        self._guardar_puntos(serie, puntos, t)
                    for serie, valores in toma.valores.items():
                        nuevos = [(serie, ident, t, v) for ident, v in valores.items() if self._ultimo.get((serie, ident)) != v]
                        self._bd.executemany("INSERT OR REPLACE INTO valores VALUES (?,?,?,?)", nuevos)
                        for _, ident, _, v in nuevos:
                            self._ultimo[(serie, ident)] = v
                    self._bd.executemany("INSERT OR REPLACE INTO indicadores VALUES (?,?,?)", [(clave, t, v) for clave, v in toma.indicadores.items()])
                    for tipo, objetos in toma.objetos.items():
                        self._guardar_objetos(tipo, objetos, t)
                    if getattr(toma, "items", None):
                        self._guardar_items(toma.items, t)
                    if getattr(toma, "agenda", None):
                        self._guardar_agenda(toma.agenda, t)
                    self._bd.execute("INSERT OR REPLACE INTO tomas VALUES (?,?,1,?,NULL)", (fuente, t_toma, toma.n))
            except Exception:
                # No se ha guardado nada de esta toma: lo que se recordaba como «ya guardado» deja de valer.
                self._ultimo.clear()
                self._ultimo_objeto.clear()
                self._puntos_vistos.clear()
                raise

    def _guardar_items(self, items, t: int) -> None:
        """Los textos se guardan una vez: si vuelven a llegar (un RSS los repite durante días) no se tocan,
        para no pisar lo que la IA haya afinado."""
        filas = [(it.id, it.fuente, int(it.t), it.titulo, it.texto, it.url, it.lat, it.lon, it.barrio, it.lugar, it.categoria,
                  int(it.urgencia or 0), it.idioma, json.dumps(it.extra, ensure_ascii=False, separators=(",", ":")) if it.extra else None, t)
                 for it in items]
        # Si ya estaba, solo se apunta que se ha vuelto a ver (una incidencia de la DGT sigue activa mientras sale).
        self._bd.executemany("INSERT INTO items (id, fuente, t, titulo, texto, url, lat, lon, barrio, lugar, categoria, urgencia, idioma, extra, visto) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET visto=excluded.visto", filas)

    def _guardar_agenda(self, citas, t: int) -> None:
        """Lo previsto se reescribe cada vez: una obra puede alargarse o cambiar de estado."""
        filas = [(c.id, c.tipo, c.titulo, int(c.desde), int(c.hasta), c.lat, c.lon, c.barrio, c.fuente, c.url,
                  json.dumps(c.extra, ensure_ascii=False, separators=(",", ":")) if c.extra else None, t) for c in citas]
        self._bd.executemany("INSERT OR REPLACE INTO agenda VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", filas)

    def conoce(self, serie: str, ident: str) -> bool:
        """¿Está ya apuntado dónde queda este punto?"""
        with self._candado:
            if (serie, ident) in self._puntos_vistos:
                return True
            return self._bd.execute("SELECT 1 FROM puntos WHERE serie=? AND id=?", (serie, ident)).fetchone() is not None

    def guardar_fallo(self, fuente: str, t: int, error: str) -> None:
        with self._candado:
            self._bd.execute("INSERT OR REPLACE INTO tomas VALUES (?,?,0,0,?)", (fuente, t, error[:300]))

    def _guardar_puntos(self, serie: str, puntos: dict[str, Punto], t: int) -> None:
        filas = []
        for ident, p in puntos.items():
            huella = (p.nombre, p.lat, p.lon, p.cap, len(p.geo) if p.geo else 0)
            if self._puntos_vistos.get((serie, ident)) == huella:
                continue
            self._puntos_vistos[(serie, ident)] = huella
            filas.append((serie, ident, p.nombre, p.lat, p.lon, p.cap, json.dumps(p.geo, separators=(",", ":")) if p.geo else None, t))
        self._bd.executemany("INSERT OR REPLACE INTO puntos VALUES (?,?,?,?,?,?,?,?)", filas)

    def _guardar_objetos(self, tipo: str, objetos: list[Objeto], t: int) -> None:
        """Un tren parado en una estación no añade una fila cada medio minuto: se apunta cuando se mueve
        y, aunque no se mueva, cada cinco minutos, para saber que seguía ahí."""
        filas = []
        for o in objetos:
            antes = self._ultimo_objeto.get((tipo, o.id))
            if antes and antes[0] == o.lat and antes[1] == o.lon and t - antes[2] < 300:
                continue
            self._ultimo_objeto[(tipo, o.id)] = (o.lat, o.lon, t)
            filas.append((tipo, o.id, t, o.lat, o.lon, o.rumbo, o.alt, o.nombre))
        self._bd.executemany("INSERT OR REPLACE INTO rastros VALUES (?,?,?,?,?,?,?,?)", filas)
        if len(self._ultimo_objeto) > 5000:      # los que ya se fueron
            self._ultimo_objeto = {k: v for k, v in self._ultimo_objeto.items() if t - v[2] < 3600}

    def guardar_suceso(self, clave: str, t: int, valor: float, normal: float, z: float, margen: int = 1800) -> None:
        """Apunta que un indicador está fuera de lo normal. Si ya lo estaba hace poco, alarga ese suceso
        en vez de abrir otro: un atasco de dos horas es un suceso, no cuarenta."""
        with self._candado:
            abierto = self._bd.execute("SELECT desde, z FROM sucesos WHERE clave=? AND hasta>=? AND (z>0)=(?>0) ORDER BY desde DESC LIMIT 1",
                                       (clave, t - margen, z)).fetchone()
            if abierto:
                # Se queda con el momento más extremo, que es lo que interesa enseñar.
                if abs(z) > abs(abierto[1]):
                    self._bd.execute("UPDATE sucesos SET hasta=?, valor=?, normal=?, z=? WHERE clave=? AND desde=?", (t, valor, normal, z, clave, abierto[0]))
                else:
                    self._bd.execute("UPDATE sucesos SET hasta=? WHERE clave=? AND desde=?", (t, clave, abierto[0]))
            else:
                self._bd.execute("INSERT OR REPLACE INTO sucesos VALUES (?,?,?,?,?,?)", (clave, t, t, valor, normal, z))

    def limpiar(self, ahora: int, dias_valores: int, dias_rastros: int) -> None:
        """Tira lo antiguo de las tablas que crecen. Los indicadores y los sucesos se quedan siempre:
        ocupan poco y son los que dicen qué es lo normal."""
        with self._candado:
            if dias_valores > 0:
                self._bd.execute("DELETE FROM valores WHERE t<?", (ahora - dias_valores * 86400,))
            if dias_rastros > 0:
                self._bd.execute("DELETE FROM rastros WHERE t<?", (ahora - dias_rastros * 86400,))
            self._bd.execute("DELETE FROM tomas WHERE t<? AND ok=0", (ahora - 30 * 86400,))
            # El texto de las redes se guarda 30 días; los titulares de prensa y los avisos, siempre.
            self._bd.execute("UPDATE items SET texto=NULL WHERE t<? AND fuente IN ('bluesky','mastodon') AND texto IS NOT NULL", (ahora - 30 * 86400,))
            self._bd.execute("DELETE FROM rasgos WHERE t<?", (ahora - 45 * 86400,))
            self._bd.execute("DELETE FROM muestras WHERE semana<?", (ahora // (7 * 86400) - 26,))

    def _transaccion(self):
        return _Transaccion(self._bd)

    # ---------------------------------------------------------------- leer

    def _filas(self, consulta: str, parametros: tuple = ()) -> list[tuple]:
        with self._candado:
            return self._bd.execute(consulta, parametros).fetchall()

    def cobertura(self, fuente: str, desde: int, hasta: int, salto: float) -> list[list[int]]:
        """Los ratos de [desde, hasta] en que la fuente estuvo contestando: [[inicio, fin], ...].
        Dos tomas seguidas separadas por más de `salto` segundos parten el rato en dos."""
        ratos: list[list[int]] = []
        for (t,) in self._filas("SELECT t FROM tomas WHERE fuente=? AND ok=1 AND t BETWEEN ? AND ? ORDER BY t", (fuente, desde - int(salto), hasta)):
            if ratos and t - ratos[-1][1] <= salto:
                ratos[-1][1] = t
            else:
                ratos.append([t, t])
        return [[max(a, desde), b] for a, b in ratos if b >= desde]

    def indicadores(self, desde: int, hasta: int, paso: int, claves: tuple[str, ...] | None = None) -> dict[str, dict[int, float]]:
        """La media de cada indicador en cada tramo de `paso` segundos: clave -> {inicio del tramo: media}."""
        filtro = f" AND clave IN ({','.join('?' * len(claves))})" if claves else ""
        salida: dict[str, dict[int, float]] = {}
        for clave, tramo, media in self._filas(
                f"SELECT clave, (t/?)*?, AVG(v) FROM indicadores WHERE t>=? AND t<?{filtro} GROUP BY clave, t/?",
                (paso, paso, desde, hasta, *(claves or ()), paso)):
            salida.setdefault(clave, {})[tramo] = media
        return salida

    def ultimo_indicador(self, clave: str, hasta: int, margen: int) -> tuple[int, float] | None:
        fila = self._filas("SELECT t, v FROM indicadores WHERE clave=? AND t<=? AND t>=? ORDER BY t DESC LIMIT 1", (clave, hasta, hasta - margen))
        return fila[0] if fila else None

    def puntos(self, serie: str) -> dict[str, dict]:
        return {ident: {"nombre": nombre or "", "lat": lat, "lon": lon, "cap": cap, "geo": json.loads(geo) if geo else None}
                for ident, nombre, lat, lon, cap, geo in self._filas("SELECT id, nombre, lat, lon, cap, geo FROM puntos WHERE serie=?", (serie,))}

    def valores_en_rejilla(self, serie: str, instantes: list[int], ids: list[str] | None = None) -> dict[str, list[float | None]]:
        """Lo que marcaba cada punto de la serie en cada uno de los `instantes` (ordenados): el último
        cambio anterior. No mira si la fuente estaba contestando; eso se decide con `cobertura`.

        Se pregunta punto a punto: la tabla está ordenada por punto y hora, así que cada consulta va
        directa a sus filas aunque haya millones."""
        if not instantes:
            return {}
        desde, hasta = instantes[0], instantes[-1]
        salida: dict[str, list[float | None]] = {}
        with self._candado:
            if ids is None:
                ids = [fila[0] for fila in self._bd.execute("SELECT id FROM puntos WHERE serie=?", (serie,))]
            for ident in ids:
                antes = self._bd.execute("SELECT v FROM valores WHERE serie=? AND id=? AND t<=? ORDER BY t DESC LIMIT 1", (serie, ident, desde)).fetchone()
                cambios = self._bd.execute("SELECT t, v FROM valores WHERE serie=? AND id=? AND t>? AND t<=? ORDER BY t", (serie, ident, desde, hasta)).fetchall()
                if antes is None and not cambios:
                    continue
                actual, i, fila = (antes[0] if antes else None), 0, []
                for instante in instantes:
                    while i < len(cambios) and cambios[i][0] <= instante:
                        actual = cambios[i][1]
                        i += 1
                    fila.append(actual)
                salida[ident] = fila
        return salida

    def cambios(self, serie: str, desde: int, hasta: int) -> dict[str, list[tuple[int, float]]]:
        """Todos los cambios de los puntos de una serie entre `desde` y `hasta`, con el valor que tenía cada uno
        justo antes de empezar (con t=desde): {id: [(t, v), ...]}."""
        salida: dict[str, list[tuple[int, float]]] = {}
        with self._candado:
            ids = [f[0] for f in self._bd.execute("SELECT id FROM puntos WHERE serie=?", (serie,))]
            for ident in ids:
                antes = self._bd.execute("SELECT v FROM valores WHERE serie=? AND id=? AND t<=? ORDER BY t DESC LIMIT 1", (serie, ident, desde)).fetchone()
                filas = self._bd.execute("SELECT t, v FROM valores WHERE serie=? AND id=? AND t>? AND t<=? ORDER BY t", (serie, ident, desde, hasta)).fetchall()
                if antes is None and not filas:
                    continue
                salida[ident] = ([(desde, antes[0])] if antes else []) + filas
        return salida

    def ultima_toma(self, fuente: str, hasta: int) -> int | None:
        fila = self._filas("SELECT MAX(t) FROM tomas WHERE fuente=? AND ok=1 AND t<=?", (fuente, hasta))
        return fila[0][0] if fila else None

    def historia_de_punto(self, serie: str, ident: str, desde: int, hasta: int) -> list[tuple[int, float]]:
        """Los cambios de un punto, con el valor que tenía al empezar."""
        antes = self._filas("SELECT t, v FROM valores WHERE serie=? AND id=? AND t<=? ORDER BY t DESC LIMIT 1", (serie, ident, desde))
        return antes + self._filas("SELECT t, v FROM valores WHERE serie=? AND id=? AND t>? AND t<=? ORDER BY t", (serie, ident, desde, hasta))

    def rastros(self, tipo: str, desde: int, hasta: int, cada: int = 0) -> dict[str, dict]:
        """Por dónde ha ido cada objeto: id -> {nombre, p: [[t, lat, lon, alt, rumbo], ...]}.
        Con `cada`, como mucho un punto por objeto cada tantos segundos."""
        salida: dict[str, dict] = {}
        for ident, t, lat, lon, rumbo, alt, nombre in self._filas(
                "SELECT id, t, lat, lon, rumbo, alt, nombre FROM rastros WHERE tipo=? AND t>=? AND t<=? ORDER BY id, t", (tipo, desde, hasta)):
            objeto = salida.setdefault(ident, {"nombre": nombre or ident, "p": []})
            if cada and objeto["p"] and t - objeto["p"][-1][0] < cada:
                continue
            objeto["p"].append([t, round(lat, 5), round(lon, 5), None if alt is None else round(alt), None if rumbo is None else round(rumbo)])
            if nombre:
                objeto["nombre"] = nombre
        return salida

    def sucesos(self, desde: int, hasta: int) -> list[dict]:
        return [{"clave": clave, "desde": a, "hasta": b, "valor": valor, "normal": normal, "z": round(z, 1)}
                for clave, a, b, valor, normal, z in self._filas(
                    "SELECT clave, desde, hasta, valor, normal, z FROM sucesos WHERE hasta>=? AND desde<=? ORDER BY desde DESC", (desde, hasta))]

    def estado(self) -> dict:
        """Cuánto hay guardado y cuándo fue la última toma de cada fuente."""
        ahora = int(time.time())
        fuentes = {}
        for fuente, ultima, buenas, primera in self._filas("SELECT fuente, MAX(t), SUM(ok), MIN(t) FROM tomas GROUP BY fuente"):
            fila = self._filas("SELECT t, ok, n, error FROM tomas WHERE fuente=? ORDER BY t DESC LIMIT 1", (fuente,))[0]
            fuentes[fuente] = {"ultima": ultima, "primera": primera, "tomas": buenas or 0, "ok": bool(fila[1]), "n": fila[2], "error": fila[3]}
        sucesos = self._filas("SELECT COUNT(*) FROM sucesos")[0][0]
        desde = self._filas("SELECT MIN(t) FROM indicadores")[0][0]
        tam = Path(self.ruta).stat().st_size if self.ruta != ":memory:" and Path(self.ruta).exists() else 0
        return {"ahora": ahora, "desde": desde, "fuentes": fuentes, "sucesos": sucesos, "bytes": tam}


class _Transaccion:
    """Todo lo de una toma se guarda de una vez, o no se guarda nada."""

    def __init__(self, bd: sqlite3.Connection):
        self.bd = bd

    def __enter__(self):
        self.bd.execute("BEGIN")

    def __exit__(self, tipo, *_):
        self.bd.execute("ROLLBACK" if tipo else "COMMIT")
        return False
