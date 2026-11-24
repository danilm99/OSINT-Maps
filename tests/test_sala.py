"""La sala de control con una ciudad de juguete en disco: nueve barrios cuadrados, dos calles,
y lo que pide la pantalla de la sala."""

import json
import random
from datetime import datetime

import pytest

from osintmaps.pulso import cruce as C
from osintmaps.pulso import fichas, sala, servidor
from osintmaps.pulso.fuentes import Cita, Item, Punto, Toma

LETRAS = "ABCDEFGHI"
T0 = int(datetime(2026, 11, 18, 19, 0).timestamp()) // C.BIN * C.BIN       # un miércoles a las 19:00
LAT0, LON0, PASO = 39.46, -0.39, 0.01
CODIGOS = {b: f"0{1 + i // 3}{1 + i % 3}" for i, b in enumerate(LETRAS)}      # A -> 011, E -> 022...


def cuadrado(fila, col):
    a, b = LON0 + col * PASO, LAT0 + fila * PASO
    return {"type": "Polygon", "coordinates": [[[a, b], [a + PASO, b], [a + PASO, b + PASO], [a, b + PASO], [a, b]]]}


@pytest.fixture()
def pulso(tmp_path, monkeypatch):
    ciudad = tmp_path / "ciudad"
    ciudad.mkdir()
    barrios = [{"type": "Feature", "geometry": cuadrado(i // 3, i % 3),
                "properties": {"coddistbar": CODIGOS[b], "codbarrio": str(1 + i % 3), "coddistrit": str(1 + i // 3), "nombre": f"BARRI {b}"}}
               for i, b in enumerate(LETRAS)]
    distritos = [{"type": "Feature", "geometry": cuadrado(0, 0), "properties": {"coddistrit": str(d), "nombre": f"DISTRICTE {d}"}} for d in (1, 2, 3)]
    # Una calle que cruza la cuadrícula de oeste a este por el medio, con portales del 1 al 99 (impares a la izquierda).
    calles = [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[LON0, LAT0 + 1.5 * PASO], [LON0 + 3 * PASO, LAT0 + 1.5 * PASO]]},
               "properties": {"codvia": "1", "tipcalle": "CALLE", "nomcalle": "COLON", "lf_add": 1, "lt_add": 99, "rf_add": 2, "rt_add": 100}}]
    for nombre, feats in (("barrios", barrios), ("distritos", distritos), ("calles", calles)):
        (ciudad / f"{nombre}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    (ciudad / "vulnerabilidad.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": cuadrado(1, 1), "properties": {"codbar": 22, "ind_global": 3.5, "vul_global": "Vulnerabilidad Media"}}]}),
        encoding="utf-8")
    (ciudad / "quejas.csv").write_text("Fecha Entrada;Tema;Barrio Localización\n" + "".join(
        f"{d:02d}/11/2026;Contaminación acústica;22\n" for d in range(1, 11)) + "01/11/2026;Servicios de jardinería;22\n", encoding="utf-8")
    (ciudad / "accidentes.csv").write_text("FECHA;TIPO GRAVEDAD;UBICACIÓN;TIPO ACCIDENTE;UNIDADES_IMPLICADAS\n"
                                           "2026-11-01 10:00:00;CON HERIDOS LEVES;C/ COLON 51;ATROPELLO;TURISMO, PEATÓN\n", encoding="utf-8")
    monkeypatch.setattr(fichas.Fichas, "catastro", lambda self, lat, lon, sesion=None: {"rc": "5628402YJ2752H", "uso": "Residencial", "año": 1900})
    p = servidor.Pulso(tmp_path, recoger=False)
    yield p
    p.parar()


def preparar(p):
    """Seis semanas de lo normal y una afluencia en el barrio E (022) antes de un partido."""
    almacen, motor = p.almacen, p.sala.cruce
    azar = random.Random(3)
    filas = []
    for semana in range(1, 7):
        base = T0 - semana * C.SEMANA
        for slot in range(48):
            for b in list(CODIGOS.values()) + [C.CIUDAD]:
                filas.append(("bici_ocupacion", b, 96 + slot, base // C.SEMANA, 50 + azar.uniform(-2, 2), 0))
                filas.append(("parking", b, 96 + slot, base // C.SEMANA, 40 + azar.uniform(-2, 2), 0))
    almacen._bd.executemany("INSERT OR REPLACE INTO muestras VALUES (?,?,?,?,?,?)", filas)

    def toma(t, bicis_e=10, libres_e=60, items=(), agenda=()):
        centros = {CODIGOS[b]: (LAT0 + (i // 3 + 0.5) * PASO, LON0 + (i % 3 + 0.5) * PASO) for i, b in enumerate(LETRAS)}
        almacen.guardar_toma("bicis", t, Toma(valores={"bicis": {f"b{c}": (bicis_e if c == "022" else 10) for c in centros}},
                                              puntos={"bicis": {f"b{c}": Punto(f"Estación {c}", *centros[c], 20) for c in centros}}))
        almacen.guardar_toma("parking", t, Toma(valores={"parking": {f"p{c}": (libres_e if c == "022" else 60) for c in centros}},
                                                puntos={"parking": {f"p{c}": Punto(f"Parking {c}", *centros[c], 100) for c in centros}}))
        for f in ("prensa", "bluesky", "dgt", "aviones"):
            almacen.guardar_toma(f, t, Toma(items=[i for i in items if i.fuente == f], agenda=list(agenda) if f == "prensa" else []))

    partido = Cita("partido:9", "partido", "Valencia CF – Real Betis (Mestalla)", T0 + 3600, T0 + 10800, LAT0 + 1.5 * PASO, LON0 + 1.5 * PASO)
    toma(T0 - 1200, agenda=[partido])
    toma(T0 - 600)
    textos = [Item("prensa:a", "prensa", T0 - 100, "Ambiente de partido en la calle Colón", url="https://ejemplo.es/a", lat=LAT0 + 1.5 * PASO,
                   lon=LON0 + 1.2 * PASO, barrio="022", categoria="deporte", extra={"medio": "Las Provincias"}),
              Item("bluesky:b", "bluesky", T0 - 50, "Qué ambientazo en Colón", url="https://bsky.app/x", barrio="022", categoria="deporte")]
    toma(T0, bicis_e=19, libres_e=5, items=textos)
    motor.paso(T0)
    return motor


def test_estado_y_parte(pulso, monkeypatch):
    preparar(pulso)
    monkeypatch.setattr(sala.time, "time", lambda: T0 + 30)
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/estado", "")
    assert codigo == 200
    e = json.loads(cuerpo)
    assert e["hay"] and e["barrios"]["022"]["nivel"] > 3
    assert [s["tipo"] for s in e["sucesos"]] == ["concentracion"]
    assert e["sucesos"][0]["causa"]["tipo"] == "partido"
    assert e["nivel"]["clase"] in ("alta", "muy alta")
    assert any(a["tipo"] == "partido" for a in e["agenda"]["destacado"])
    assert {i["fuente"] for i in e["feed"]} == {"prensa", "bluesky"}
    assert "suceso en marcha" in e["parte"]["texto"].lower() or "sucesos en marcha" in e["parte"]["texto"].lower()


def test_en_la_web_no_van_los_textos_de_redes(pulso, monkeypatch):
    preparar(pulso)
    monkeypatch.setattr(sala.time, "time", lambda: T0 + 30)
    ficheros = pulso.sala.ficheros_web()
    assert set(ficheros) == set(sala.FICHEROS_WEB)
    web = json.loads(ficheros["sala.json"])
    assert web["publico"] and {i["fuente"] for i in web["feed"]} == {"prensa"}
    assert "Qué ambientazo" not in ficheros["sala.json"].decode("utf-8")
    barrios = json.loads(ficheros["sala-barrios.json"])
    assert len(barrios["features"]) == 9
    perfiles = json.loads(ficheros["sala-perfiles.json"])
    assert len(perfiles["rasgos"]["bici_ocupacion"]["L"]["022"]) == 48


def test_suceso_barrio_y_lugar(pulso, monkeypatch):
    motor = preparar(pulso)
    monkeypatch.setattr(sala.time, "time", lambda: T0 + 30)
    ev = motor.eventos(T0 - 3600, T0 + 1)[0]
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/evento", f"id={ev['id']}")
    assert codigo == 200
    d = json.loads(cuerpo)
    assert set(d["series"]) >= {"parking", "bici_ocupacion"}
    assert d["series"]["parking"]["valores"]["022"][-1][1] == 95.0
    assert d["series"]["parking"]["normal"]["022"], "debe traer lo normal para comparar"
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/barrio", "codigo=022")
    b = json.loads(cuerpo)
    assert codigo == 200 and b["nombre"] == "Barri E" and b["contexto"]["vulnerabilidad"]["ind_global"] == 3.5
    assert b["contexto"]["quejas"]["temas"][0] == ["Contaminación acústica", 10]
    assert len(b["sucesos"]) == 1 and b["items"]
    # Un punto de la calle Colón: la calle, el portal, el barrio, el accidente de esa dirección y el Catastro.
    pulso.sala.fichas.situar_accidentes()
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/lugar", f"lat={LAT0 + 1.5 * PASO + 0.00005}&lon={LON0 + 1.5 * PASO}")
    lugar = json.loads(cuerpo)
    assert codigo == 200, lugar
    assert lugar["barrio"] == "022" and lugar["calle"]["nombre"] == "Calle Colon" and lugar["calle"]["numero"] in (49, 51)
    assert lugar["catastro"]["rc"] == "5628402YJ2752H"
    assert len(lugar["accidentes"]) == 1 and lugar["accidentes"][0]["tipo"] == "Atropello"
    assert sala.atender(pulso.sala, "/vivo/sala/lugar", "lat=40.4&lon=-3.7")[0] == 400


def test_buscar_comparar_y_movilidad(pulso, monkeypatch):
    preparar(pulso)
    monkeypatch.setattr(sala.time, "time", lambda: T0 + 30)
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/items", f"q=Colón&desde={T0 - 3600}&hasta={T0 + 60}")
    assert codigo == 200 and len(json.loads(cuerpo)["items"]) == 2
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/comparar", "rasgo=bici_ocupacion&a=L&b=S")
    d = json.loads(cuerpo)
    assert codigo == 200 and len(d["a"]["valores"]["022"]) == 48 and d["b"]["valores"] == {}
    assert sala.atender(pulso.sala, "/vivo/sala/comparar", "rasgo=nada")[0] == 400
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/movilidad", "horas=1")
    m = json.loads(cuerpo)
    assert codigo == 200 and m["barrios"]["022"]["llegan"] == 9


def test_sin_mapa_contesta_igual(tmp_path):
    p = servidor.Pulso(tmp_path, recoger=False)
    codigo, cuerpo = sala.atender(p.sala, "/vivo/sala/estado", "")
    assert codigo == 200 and json.loads(cuerpo)["hay"] is False
    assert sala.atender(p.sala, "/vivo/sala/lugar", "lat=39.47&lon=-0.37")[0] == 400
    assert p.sala.ficheros_web() == {}
    p.parar()


def test_parte_por_reglas():
    tranquilo = sala.parte_por_reglas({"sucesos_activos": [], "ciudad_fuera_de_lo_normal": [], "hoy": ["21:00 Valencia CF – Betis"]})
    assert tranquilo.startswith("La ciudad está dentro de lo normal") and "Hoy: 21:00 Valencia CF" in tranquilo
    movido = sala.parte_por_reglas({"sucesos_activos": [{"titulo": "Afluencia en Mestalla", "desde": "19:00"}],
                                    "ciudad_fuera_de_lo_normal": [{"nombre": "Tráfico", "valor": 45.0, "unidad": "sobre 100", "normal": 30.0, "z": 3}]})
    assert "Un suceso en marcha: Afluencia en Mestalla (desde las 19:00)" in movido and "tráfico 45 sobre 100 (lo normal, 30)" in movido


def test_catastro_se_lee_venga_como_venga():
    rc = fichas.leer_rccoor({"Consulta_RCCOORResult": {"coordenadas": {"coord": [{"pc": {"pc1": "5628402", "pc2": "YJ2752H"},
                                                                                   "ldt": "CL CABALLEROS 2 VALENCIA (VALENCIA)"}]}}})
    assert rc == {"rc": "5628402YJ2752H", "direccion": "CL CABALLEROS 2 VALENCIA (VALENCIA)"}
    uno = fichas.leer_dnprc({"consulta_dnprcResult": {"bico": {"bi": {"idbi": {"cn": "UR"}, "debi": {"luso": "Residencial", "sfc": "120", "ant": "1965"}}}}})
    assert uno["uso"] == "Residencial" and uno["año"] == 1965 and uno["inmuebles"] == 1 and uno["clase"] == "urbano"
    varios = fichas.leer_dnprc({"consulta_dnprcResult": {"lrcdnp": {"rcdnp": [
        {"debi": {"luso": "Residencial", "sfc": "90", "ant": "1900"}}, {"debi": {"luso": "Comercial", "sfc": "60", "ant": "1900"}}]}}})
    assert varios["inmuebles"] == 2 and varios["usos"][0][0] in ("Residencial", "Comercial") and varios["superficie_total"] == 150
