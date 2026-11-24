"""El cruce con una ciudad de juguete: nueve barrios en cuadrícula, seis semanas de «lo normal» y
situaciones inventadas encima (un partido, la lluvia, un incendio, un helicóptero)."""

import random
import time
from datetime import datetime

import pytest

from osintmaps.pulso import cruce as C
from osintmaps.pulso.almacen import Almacen, semana_local
from osintmaps.pulso.fuentes import Cita, Item, Objeto, Punto, Toma

# Cuadrícula 3x3 de barrios de 0,01° alrededor de la plaza del Ayuntamiento. «E» es el del centro.
LETRAS = "ABCDEFGHI"
LAT0, LON0, PASO = 39.46, -0.39, 0.01


class ZonasDeJuguete:
    def __init__(self):
        self.barrios, self.vecinos = {}, {}
        for i, b in enumerate(LETRAS):
            fila, col = divmod(i, 3)
            self.barrios[b] = {"codigo": b, "nombre": f"Barrio {b}", "lat": LAT0 + (fila + 0.5) * PASO, "lon": LON0 + (col + 0.5) * PASO}
        for i, b in enumerate(LETRAS):
            fila, col = divmod(i, 3)
            self.vecinos[b] = {LETRAS[f * 3 + c] for f in range(fila - 1, fila + 2) for c in range(col - 1, col + 2)
                               if 0 <= f < 3 and 0 <= c < 3 and (f, c) != (fila, col)}

    hay = True

    def barrio_de(self, lat, lon):
        if lat is None or lon is None:
            return None
        fila, col = int((lat - LAT0) // PASO), int((lon - LON0) // PASO)
        return LETRAS[fila * 3 + col] if 0 <= fila < 3 and 0 <= col < 3 else None

    def nombre(self, codigo):
        return self.barrios.get(codigo, {}).get("nombre", "")


def centro(b):
    z = ZonasDeJuguete().barrios[b]
    return z["lat"], z["lon"]


# Un miércoles a las 19:00 (hora local), que no es festivo.
T0 = int(datetime(2026, 11, 18, 19, 0).timestamp()) // C.BIN * C.BIN


@pytest.fixture()
def ciudad():
    almacen = Almacen(":memory:")
    zonas = ZonasDeJuguete()
    motor = C.Cruce(almacen, zonas)
    # Seis semanas de lo normal para todo el miércoles: bicis al 50 %, aparcamientos al 40 %, con algo de ruido.
    azar = random.Random(7)
    filas = []
    for semana in range(1, 7):
        base = T0 - semana * C.SEMANA
        for slot in range(48):
            fr = 2 * 48 + slot          # miércoles
            for b in list(LETRAS) + [C.CIUDAD]:
                filas.append(("bici_ocupacion", b, fr, semana_local(base), 50 + azar.uniform(-2, 2), 0))
                filas.append(("parking", b, fr, semana_local(base), 40 + azar.uniform(-2, 2), 0))
    almacen._bd.executemany("INSERT OR REPLACE INTO muestras VALUES (?,?,?,?,?,?)", filas)
    return almacen, motor


def tomar(almacen, t, bicis=None, libres=None, items=(), agenda=(), helis=(), lluvia=None, fuentes=("bicis", "parking")):
    """Guarda una toma de cada fuente en `t`: bicis ancladas (de 20) y plazas libres (de 100) por barrio."""
    bicis = {b: 10 for b in LETRAS} | (bicis or {})
    libres = {b: 60 for b in LETRAS} | (libres or {})
    if "bicis" in fuentes:
        almacen.guardar_toma("bicis", t, Toma(valores={"bicis": {f"b{b}": v for b, v in bicis.items()}},
                                              puntos={"bicis": {f"b{b}": Punto(f"Estación {b}", *centro(b), 20) for b in LETRAS}}))
    if "parking" in fuentes:
        almacen.guardar_toma("parking", t, Toma(valores={"parking": {f"p{b}": v for b, v in libres.items()}},
                                                puntos={"parking": {f"p{b}": Punto(f"Parking {b}", *centro(b), 100) for b in LETRAS}}))
    almacen.guardar_toma("prensa", t, Toma(items=[i for i in items if i.fuente == "prensa"], agenda=list(agenda)))
    almacen.guardar_toma("bluesky", t, Toma(items=[i for i in items if i.fuente == "bluesky"]))
    almacen.guardar_toma("dgt", t, Toma())
    almacen.guardar_toma("aviones", t, Toma(objetos={"helicopteros": list(helis)}))
    if lluvia is not None:
        almacen.guardar_toma("meteo", t, Toma(indicadores={"meteo_lluvia": lluvia}))


def test_estadistica():
    z, normal = C.z_continuo(80, [50, 51, 49, 50, 52], suelo=5)
    assert normal == 50 and z > 3
    assert C.z_conteo(0, [], prior=0.1, r=2)[0] == 0
    # Dos textos urgentes donde casi nunca hay: raro. Dos publicaciones donde suele haber cinco: nada.
    assert C.z_conteo(2, [], prior=0.03, r=3)[0] > 3
    assert C.z_conteo(2, [5, 6, 4, 5], prior=0.15, r=2)[0] == 0
    # A rachas (r pequeño) es menos raro ver muchos que con Poisson.
    assert C.z_conteo(8, [2, 2, 2, 2], prior=2)[0] > C.z_conteo(8, [2, 2, 2, 2], prior=2, r=2)[0]


def test_franjas_y_tipos_de_dia():
    assert C.franja(int(datetime(2026, 11, 16, 0, 10).timestamp())) == 0           # lunes 0:10
    assert C.franja(int(datetime(2026, 11, 18, 19, 40).timestamp())) == 2 * 48 + 39
    assert C.tipo_dia(int(datetime(2026, 11, 21, 12).timestamp())) == "S"
    assert C.tipo_dia(int(datetime(2026, 12, 8, 12).timestamp())) == "D"            # la Inmaculada, festivo
    assert C.tipo_dia(int(datetime(2026, 11, 18, 12).timestamp())) == "L"


def test_un_partido_llena_un_barrio_y_se_explica(ciudad):
    almacen, motor = ciudad
    partido = Cita("partido:1", "partido", "Valencia CF – Real Betis (Mestalla)", T0 + 3600, T0 + 3600 + 7200, *centro("E"), fuente="TheSportsDB")
    tomar(almacen, T0 - 1200, agenda=[partido])
    tomar(almacen, T0 - 600)
    # En el barrio E se llenan a la vez las estaciones de bicis y el aparcamiento: dos fuentes distintas.
    tomar(almacen, T0, bicis={"E": 19}, libres={"E": 5})
    estado = motor.paso(T0)
    assert estado["barrios"]["E"]["nivel"] > 3
    assert "concentracion" in estado["barrios"]["E"]["tipos"]
    assert all(not estado["barrios"][b]["tipos"] for b in LETRAS if b != "E")
    activos = motor.eventos(T0 - 3600, T0)
    assert len(activos) == 1
    ev = activos[0]
    assert ev["tipo"] == "concentracion" and ev["barrios"] == ["E"]
    assert ev["causa"]["probable"]["tipo"] == "partido"
    assert ev["titulo"].startswith("Afluencia en Barrio E — Valencia CF")
    # Sigue igual diez minutos después: es el mismo suceso, más largo.
    tomar(almacen, T0 + 600, bicis={"E": 19}, libres={"E": 5})
    motor.paso(T0 + 600)
    assert [e["id"] for e in motor.eventos(T0 - 3600, T0 + 600)] == [ev["id"]]
    assert motor.evento(ev["id"])["fin"] == T0 + 600
    # Vuelve a lo normal: media hora después el suceso se cierra.
    for k in range(2, 7):
        tomar(almacen, T0 + k * 600)
        motor.paso(T0 + k * 600)
    cerrado = motor.evento(ev["id"])
    assert cerrado["estado"] == "cerrado" and cerrado["fin"] == T0 + 600


def test_valenbisi_sola_no_basta(ciudad):
    """Un camión que reparte bicis llena una estación: es una sola fuente, no hay suceso."""
    almacen, motor = ciudad
    tomar(almacen, T0 - 1200)
    tomar(almacen, T0 - 600)
    tomar(almacen, T0, bicis={"E": 20})
    estado = motor.paso(T0)
    assert estado["barrios"]["E"]["nivel"] > 3
    assert not estado["barrios"]["E"]["tipos"]
    assert motor.eventos(T0 - 3600, T0) == []


def test_la_lluvia_es_de_toda_la_ciudad(ciudad):
    """Llueve: las bicis se quedan ancladas en todos los barrios. No es un suceso de ningún barrio, es de la ciudad."""
    almacen, motor = ciudad
    tomar(almacen, T0 - 1200)
    tomar(almacen, T0 - 600, lluvia=3.2)
    todas = {b: 17 for b in LETRAS}
    tomar(almacen, T0, bicis=todas, libres={b: 45 for b in LETRAS}, lluvia=3.2)
    estado = motor.paso(T0)
    assert estado["desplazamiento"]["bici_ocupacion"] > 3
    assert all(not estado["barrios"][b]["tipos"] for b in LETRAS)
    eventos = motor.eventos(T0 - 3600, T0)
    assert len(eventos) == 1 and eventos[0]["tipo"] == "ciudad"
    assert eventos[0]["causa"]["probable"]["tipo"] == "lluvia"
    assert eventos[0]["titulo"].startswith("Toda la ciudad: valenbisi: anclajes con bici por encima de lo normal")


def test_dos_noticias_urgentes_en_un_barrio_son_un_incidente(ciudad):
    almacen, motor = ciudad
    tomar(almacen, T0 - 1200)
    tomar(almacen, T0 - 600)
    textos = [Item("prensa:1", "prensa", T0 - 300, "Incendio en un edificio de la calle Mayor", url="https://ejemplo.es/1", barrio="G",
                   categoria="emergencia", urgencia=2),
              Item("prensa:2", "prensa", T0 - 200, "Desalojan a los vecinos por el incendio de la calle Mayor", url="https://ejemplo.es/2",
                   barrio="G", categoria="emergencia", urgencia=2)]
    tomar(almacen, T0, items=textos)
    estado = motor.paso(T0)
    assert "incidente" in estado["barrios"]["G"]["tipos"]
    ev = motor.eventos(T0 - 3600, T0)[0]
    assert ev["tipo"] == "incidente" and ev["causa"]["probable"]["tipo"] == "texto"
    assert "Incendio" in ev["titulo"] or "incendio" in ev["titulo"]


def test_un_helicoptero_dando_vueltas_y_su_rastro(ciudad):
    almacen, motor = ciudad
    tomar(almacen, T0 - 1200)
    lat, lon = centro("C")
    # Cinco minutos a 300 m sobre el barrio C, una posición cada 30 s (en círculo).
    for i in range(11):
        t = T0 - 330 + i * 30
        tomar(almacen, t, helis=[Objeto("34abcd", lat + 0.001 * (i % 3), lon + 0.001 * (i % 2), "POLICIA", 90, 300)],
              fuentes=() if i < 10 else ("bicis", "parking"))
    estado = motor.paso(T0)
    assert estado["barrios"]["C"]["valores"]["helis"] >= 4
    assert "incidente" in estado["barrios"]["C"]["tipos"]
    # El mismo helicóptero a 3.000 m va de paso: no cuenta.
    assert C.ALTURA_HELIS < 3000


def test_reconstruir_lo_que_falta(ciudad):
    almacen, motor = ciudad
    for k in range(-6, 1):
        tomar(almacen, T0 + k * 600, bicis={"E": 19} if k == 0 else None, libres={"E": 5} if k == 0 else None)
    n = motor.reconstruir(T0 - 3600, T0, sucesos_desde=T0 - 600)
    assert n == 6
    assert motor.eventos(T0 - 3600, T0)[0]["barrios"] == ["E"]
    # Lo que ya está hecho no se repite.
    assert motor.reconstruir(T0 - 3600, T0, sucesos_desde=T0 - 600) == 0
    # Las muestras de las medias horas cerradas ya están para mañana.
    assert almacen._filas("SELECT COUNT(*) FROM muestras WHERE semana=?", (semana_local(T0),))[0][0] > 0


def test_perfiles_para_comparar_dias(ciudad):
    almacen, motor = ciudad
    perfil = motor.perfil("bici_ocupacion", "L")
    assert set(perfil) >= set(LETRAS) and all(v is not None and 45 < v < 55 for v in perfil["E"])
    assert motor.perfil("bici_ocupacion", "S") == {}


def test_dos_sucesos_juntos_no_se_mezclan(ciudad):
    """Una afluencia en E y, en el barrio de al lado, un incendio: son dos sucesos, cada uno con lo suyo."""
    almacen, motor = ciudad
    tomar(almacen, T0 - 1200)
    tomar(almacen, T0 - 600, bicis={"E": 19}, libres={"E": 5})
    motor.paso(T0 - 600)
    textos = [Item("prensa:1", "prensa", T0 - 300, "Incendio en un edificio", barrio="F", categoria="emergencia", urgencia=2),
              Item("prensa:2", "prensa", T0 - 200, "Desalojan un edificio por un incendio", barrio="F", categoria="emergencia", urgencia=2)]
    tomar(almacen, T0, bicis={"E": 19}, libres={"E": 5}, items=textos)
    motor.paso(T0)
    eventos = sorted((e["tipo"], tuple(e["barrios"]), e["inicio"]) for e in motor.eventos(T0 - 3600, T0))
    assert eventos == [("concentracion", ("E",), T0 - 1200), ("incidente", ("F",), T0 - 600)]


def test_lo_que_se_mueve_sigue_siendo_el_mismo_suceso(ciudad):
    """La afluencia pasa del barrio D al de al lado (E): es el mismo suceso, que ahora está en E."""
    almacen, motor = ciudad
    tomar(almacen, T0 - 1200)
    tomar(almacen, T0 - 600, bicis={"D": 19}, libres={"D": 5})
    motor.paso(T0 - 600)
    tomar(almacen, T0, bicis={"E": 19}, libres={"E": 5})
    motor.paso(T0)
    eventos = motor.eventos(T0 - 3600, T0)
    assert len(eventos) == 1
    # Ahora está sobre todo en E (D, de donde salen las bicis, puede seguir al lado con señales más flojas).
    assert eventos[0]["barrios"] == ["D", "E"] and eventos[0]["evidencias"]["ahora"][0] == "E"


def test_lo_normal_nunca_es_de_hoy(ciudad):
    """Con poco histórico, lo normal sale de otros días; nunca de hoy (lo que está pasando no es su propio normal)."""
    almacen, motor = ciudad
    hoy, fr = semana_local(T0 - 1), C.franja(T0 - 1)
    almacen._bd.executemany("INSERT INTO muestras VALUES (?,?,?,?,?,?)", [
        ("urgentes", "G", fr - 1, hoy, 2.0, 0),                  # hoy, media hora antes: el propio suceso
        ("urgentes", "G", fr - 48, hoy, 0.0, 0), ("urgentes", "G", fr - 49, hoy, 0.0, 0), ("urgentes", "G", fr - 47, hoy, 0.0, 0),   # ayer
        ("urgentes", "G", fr + 1, hoy - 1, 0.0, 0),              # la semana pasada, media hora después
        ("urgentes", "G", fr + 48, hoy, 5.0, 0),                 # mañana (al reconstruir): tampoco
    ])
    assert sorted(motor.muestras("urgentes", "G", T0)) == [0.0, 0.0, 0.0, 0.0]


def test_la_tabla_de_rasgos_vieja_se_rehace(tmp_path):
    """Los rasgos se ordenaban por rasgo y barrio; al abrir un histórico así, la tabla se rehace (se recalcula)."""
    import sqlite3
    ruta = tmp_path / "pulso.sqlite"
    b = sqlite3.connect(ruta)
    b.executescript("CREATE TABLE rasgos (rasgo TEXT NOT NULL, barrio TEXT NOT NULL, t INTEGER NOT NULL, v REAL NOT NULL, "
                    "PRIMARY KEY (rasgo, barrio, t)) WITHOUT ROWID; CREATE INDEX rasgos_por_hora ON rasgos (t); "
                    "INSERT INTO rasgos VALUES ('trafico', 'A', 1, 2.0);")
    b.commit(); b.close()
    a = Almacen(ruta)
    sql = a._filas("SELECT sql FROM sqlite_master WHERE name='rasgos'")[0][0]
    assert "PRIMARY KEY (t, rasgo, barrio)" in sql and a._filas("SELECT COUNT(*) FROM rasgos")[0][0] == 0
    assert not a._filas("SELECT 1 FROM sqlite_master WHERE name='rasgos_por_hora'")
    a.cerrar()
    assert "PRIMARY KEY (t, rasgo, barrio)" in Almacen(ruta)._filas("SELECT sql FROM sqlite_master WHERE name='rasgos'")[0][0]
