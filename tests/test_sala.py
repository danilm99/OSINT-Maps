"""La sala de control con una ciudad de juguete en disco: nueve barrios cuadrados, dos calles,
y lo que pide la pantalla de la sala."""

import json
import random
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from osintmaps.pulso import cruce as C
from osintmaps.pulso.almacen import semana_local
from osintmaps.pulso import fichas, sala, servidor
from osintmaps.pulso import ia as IA_
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
                filas.append(("bici_ocupacion", b, 96 + slot, semana_local(base), 50 + azar.uniform(-2, 2), 0))
                filas.append(("parking", b, 96 + slot, semana_local(base), 40 + azar.uniform(-2, 2), 0))
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
    assert set(ficheros) == set(sala.FICHEROS_WEB) - {"sala-movilidad.json"}       # sin datos del MITMA no se sube ese
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


def test_catastro_con_respuestas_de_verdad():
    """Las respuestas tal como las da el Catastro (Mercado Central y un almacén de la calle Cádiz)."""
    rc = fichas.leer_rccoor({"Consulta_RCCOORResult": {"control": {"cucoor": 1}, "coordenadas": {"coord": [
        {"pc": {"pc1": "5629101", "pc2": "YJ2752H"}, "geo": {"xcen": "-0.37854", "ycen": "39.47437", "srs": "EPSG:4326"}, "ldt": "PZ MERCADO 30 VALENCIA (VALENCIA)"}]}}})
    assert rc == {"rc": "5629101YJ2752H", "direccion": "PZ MERCADO 30 VALENCIA (VALENCIA)"}
    error = fichas.leer_rccoor({"Consulta_RCCOORResult": {"control": {"cuerr": 1}, "lerr": [{"cod": "76", "des": "LA COORDENADA X OBLIGATORIA"}]}})
    assert error["rc"] is None and "COORDENADA" in error["error"]
    datos = fichas.leer_dnprc({"consulta_dnprcResult": {"control": {"cudnp": 1, "cucons": 1}, "bico": {"bi": {
        "idbi": {"cn": "UR", "rc": {"pc1": "6014930", "pc2": "YJ2761E", "car": "0001", "cc1": "F", "cc2": "D"}},
        "ldt": "CL CADIZ 52(A) 46006 VALENCIA (VALENCIA)", "debi": {"luso": "Industrial", "sfc": "390", "cpt": "100,000000", "ant": "1943"}},
        "finca": {"ldt": "CL CADIZ 52(A)  VALENCIA (VALENCIA)", "ltp": "Parcela construida sin división horizontal", "dff": {"ss": "400"},
                  "infgraf": {"igraf": "https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?del=46&mun=900&refcat=6014930YJ2761E"}},
        "lcons": [{"lcd": "ALMACEN", "dfcons": {"stl": "390"}, "dvcons": {"dtip": "INDUSTRIA NO FABRIL"}}]}}})
    assert datos["uso"] == "Industrial" and datos["año"] == 1943 and datos["superficie"] == 390 and datos["suelo"] == 400
    assert datos["parcela"].startswith("Parcela construida") and datos["construcciones"] == [["Almacen", 390]]
    assert datos["tipologia"] == "Industria no fabril" and datos["plano"].startswith("https://")
    pisos = fichas.leer_dnprc({"consulta_dnprcResult": {"lrcdnp": {"rcdnp": [
        {"rc": {"pc1": "5628402", "pc2": "YJ2752H", "car": "0001", "cc1": "X", "cc2": "Y"}, "dt": {}},
        {"rc": {"pc1": "5628402", "pc2": "YJ2752H", "car": "0002", "cc1": "Z", "cc2": "W"}, "dt": {}}]}}})
    assert pisos["inmuebles"] == 2 and pisos["primero"] == "5628402YJ2752H0001XY"


def test_movilidad_del_mitma(pulso):
    """Las líneas del MITMA se quedan en lo que toca a València y se juntan por hora, origen y destino."""
    from osintmaps.pulso import movilidad
    lineas = ["fecha|periodo|origen|destino|distancia|actividad_origen|actividad_destino|residencia|renta|edad|sexo|viajes|viajes_km\n",
              "20251013|08|4625001|4625002|2-10|casa|trabajo_estudio|46|10-15|25-45|mujer|120.5|600.1\n",
              "20251013|08|4625001|4625002|2-10|casa|trabajo_estudio|46|10-15|45-65|hombre|80.0|400.0\n",
              "20251013|08|4610201|4625001|10-50|casa|trabajo_estudio|46|10-15|25-45|mujer|300.0|9000.0\n",
              "20251013|08|28079|08019|>50|casa|otros|28|>15|25-45|mujer|999.0|462500.0\n",
              "20251013|21|4625002|4625001|2-10|otros|casa|46|10-15|25-45|mujer|50.0|200.0\n"]
    horas, total = movilidad.leer_dia(lineas)
    assert total == 550.5
    assert horas[8] == [["fuera", "4625001", 300.0], ["4625001", "4625002", 200.5]] and horas[21] == [["4625002", "4625001", 50.0]]
    ruta = pulso.carpeta_datos / "ciudad" / movilidad.FICHERO
    ruta.write_text(json.dumps({"zonas": {"4625001": {"distrito": "1"}, "4625002": {"distrito": "2"}, "fuera": {}},
                                "dias": {"2025-10-13": {"tipo": "L", "total": total, "horas": horas}}}), encoding="utf-8")
    codigo, cuerpo = sala.atender(pulso.sala, "/vivo/sala/flujos", "dia=2025-10-13")
    d = json.loads(cuerpo)
    assert codigo == 200 and d["dias"][0]["nombre"] == "lunes 13/10/2025" and d["dias"][0]["por_hora"][8] == 500
    assert d["dias"][0]["dentro"][8] == 200 and d["zonas"]["4625001"]["nombre"] == "Districte 1" and d["zonas"]["fuera"]["nombre"] == "Fuera de València"
    assert d["zonas"]["4625002"]["lat"] is not None
    assert "sala-movilidad.json" in pulso.sala.ficheros_web()


# ---------------------------------------------------------------- la IA local, contra un Ollama de mentira


class OllamaFalso:
    """Contesta como Ollama: /api/tags y /api/chat con la respuesta según el esquema que se pide."""

    def __init__(self, conoce_think: bool = True):
        self.pedidos: list[dict] = []
        falso = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, codigo, datos):
                cuerpo = json.dumps(datos).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def do_GET(self):
                self._json(200, {"models": [{"name": "llama3.1:8b"}, {"name": "qwen3:8b"}]})

            def do_POST(self):
                pedido = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                falso.pedidos.append(pedido)
                if "think" in pedido and not conoce_think:
                    self._json(400, {"error": "invalid option provided: think"})
                    return
                propiedades = pedido["format"]["properties"]
                texto = pedido["messages"][-1]["content"]
                if "categoria" in propiedades:
                    if "Rafelguaraf" in texto:
                        respuesta = {"categoria": "seguridad", "urgencia": 0, "de_valencia": False, "lugar": ""}
                    else:
                        respuesta = {"categoria": "emergencia", "urgencia": 3, "de_valencia": True, "lugar": "Calle Colón"}
                elif "resumen" in propiedades:
                    respuesta = {"resumen": "Afluencia de gente en el barrio antes del partido.", "confianza": "alta"}
                else:
                    respuesta = {"parte": "Un suceso en marcha: afluencia por el partido."}
                self._json(200, {"message": {"role": "assistant", "content": json.dumps(respuesta, ensure_ascii=False)}})

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def cerrar(self):
        self.servidor.shutdown()


@pytest.fixture()
def ollama():
    o = OllamaFalso()
    yield o
    o.cerrar()


def test_la_ia_lee_textos_resume_sucesos_y_escribe_el_parte(pulso, ollama, monkeypatch):
    motor = preparar(pulso)
    monkeypatch.setattr(IA_.time, "time", lambda: T0 + 30)
    monkeypatch.setattr(sala.time, "time", lambda: T0 + 30)
    pulso.almacen.guardar_toma("prensa", T0 + 10, Toma(items=[
        Item("prensa:x1", "prensa", T0 + 5, "Arde un piso en pleno centro", "Los bomberos trabajan en la zona"),
        Item("prensa:x2", "prensa", T0 + 6, "Rafelguaraf abre la plaza de agente de la Policía Local")]))
    ia = IA_.IA(pulso.almacen, motor, pulso.sala.zonas, url=ollama.url)
    assert ia.disponible() and ia.modelo == "qwen3:8b"           # el preferido, aunque haya otro antes
    assert ia._textos() >= 2
    filas = dict((f[0], f[1:]) for f in pulso.almacen._filas("SELECT id, categoria, urgencia, barrio, lugar, ia FROM items WHERE id LIKE 'prensa:x%'"))
    assert filas["prensa:x1"][:2] == ("emergencia", 3) and filas["prensa:x1"][2] == "022" and filas["prensa:x1"][4] == 1
    assert filas["prensa:x2"][0] == "fuera" and filas["prensa:x2"][2] is None
    # Lo que no es de aquí deja de contar en el cruce y sale del feed.
    assert all(i["id"] != "prensa:x2" for i in pulso.sala.estado()["feed"])
    pedido = ollama.pedidos[0]
    assert pedido["think"] is False and pedido["keep_alive"] == IA_.MANTENER and pedido["options"]["temperature"] <= 0.3
    assert "personas concretas" in pedido["messages"][0]["content"]
    ev = motor.eventos(T0 - 3600, T0 + 1)[0]
    ia.encargar_resumen(ev["id"])
    assert ia._un_suceso()
    assert motor.evento(ev["id"])["resumen"].startswith("Afluencia de gente")
    texto_suceso = ollama.pedidos[-1]["messages"][-1]["content"]
    assert "Valencia CF" in texto_suceso and "Barri E" in texto_suceso
    ia.preparar_parte = pulso.sala.datos_del_parte
    ia._escribir_parte()
    assert ia.parte["texto"].startswith("Un suceso en marcha") and ia.parte["modelo"] == "qwen3:8b"
    pulso.sala.ia = ia
    pulso.sala._cache.clear()
    assert pulso.sala.parte()["ia"]["texto"] == ia.parte["texto"]


def test_el_parte_de_la_ia_solo_lleva_cifras_con_sentido():
    """Al modelo no le llegan lecturas sueltas («tráfico 0 sobre 100» acababa en «tráfico muy bajo»): cada cifra dice
    qué es y frente a qué se compara, y la agenda dice si aún no ha empezado, sigue o ya acabó."""
    d = {"momento": "martes 24 de noviembre, 20:29", "sucesos_activos": [],
         "ciudad_fuera_de_lo_normal": [{"nombre": "Tráfico", "valor": 38.0, "unidad": "sobre 100", "normal": 12.0, "z": 4.2,
                                        "nota": "0 es todo fluido y 100 todo congestionado"}],
         "lluvia": None,
         "agenda_hoy": [{"que": "Valencia Basket vs Panathinaikos BC (Roig Arena)", "cuando": "a las 20:30, aún no ha empezado"}],
         "avisos": ["Aviso amarillo por viento (Litoral norte de Valencia)"], "incidencias_trafico": ["Incidencia", "Obras"],
         "barrios_destacados": [{"barrio": "Russafa", "nivel": 3.1, "senal": "Tráfico 50 (normal 20)"}],
         "conversacion_2h": {"noticias": 6, "publicaciones": 54, "temas": ["deporte"]}}
    puntos = IA_.puntos_del_parte(d)
    assert puntos == [
        "Tráfico por encima de lo normal para la hora: 38 sobre 100, cuando lo normal es 12 sobre 100; 0 es todo fluido y 100 todo congestionado.",
        "Hoy: Valencia Basket vs Panathinaikos BC (Roig Arena), a las 20:30, aún no ha empezado.",
        "En vigor: Aviso amarillo por viento (Litoral norte de Valencia).",
        "En las últimas dos horas se habla sobre todo de deporte."]
    # Ni cifras sin referencia (cuántas noticias, cuántas incidencias de carretera) ni lo que cambia cada diez minutos.
    tranquilo = IA_.puntos_del_parte(d | {"ciudad_fuera_de_lo_normal": [], "lluvia": "lloviendo (0,4 mm en la última lectura)"})
    assert tranquilo[0] == "La ciudad está dentro de lo normal para la hora." and "Está lloviendo (0,4 mm en la última lectura)." in tranquilo
    suceso = IA_.puntos_del_parte(d | {"ciudad_fuera_de_lo_normal": [], "sucesos_activos": [
        {"titulo": "Incendio en Russafa", "desde": "20:12", "resumen": "Dos helicópteros y publicaciones que hablan de humo."}]})
    assert suceso[0] == "Suceso en marcha desde las 20:12: Incendio en Russafa. Dos helicópteros y publicaciones que hablan de humo."
    assert not any("dentro de lo normal" in p for p in suceso)


def test_la_agenda_del_parte_dice_si_ya_ha_empezado():
    partido = {"desde": T0 + 3600, "hasta": T0 + 3600 + 8100}
    hora = time.strftime("%H:%M", time.localtime(T0 + 3600))
    assert sala._cuando(partido, T0) == f"a las {hora}, aún no ha empezado"
    assert sala._cuando(partido, T0 + 4000) == f"ya en marcha (empezó a las {hora})"
    assert sala._cuando(partido, T0 + 20000) == f"ya acabado (empezó a las {hora})"
    assert sala._cuando({"desde": T0 - 19 * 3600, "hasta": T0 + 5 * 3600}, T0) == "todo el día"
    assert sala._lluvia([{"clave": "meteo_temperatura", "valor": 15.6}, {"clave": "meteo_lluvia", "valor": 0.0}]) is None
    assert sala._lluvia([{"clave": "meteo_lluvia", "valor": 1.2}]) == "lloviendo (1,2 mm en la última lectura)"


def test_el_parte_de_la_ia_se_retira_cuando_cambia_la_situacion(pulso, ollama, monkeypatch):
    motor = preparar(pulso)
    reloj = [T0 + 30]
    monkeypatch.setattr(IA_.time, "time", lambda: reloj[0])
    ia = IA_.IA(pulso.almacen, motor, pulso.sala.zonas, url=ollama.url)
    assert ia.disponible()
    ia.preparar_parte = pulso.sala.datos_del_parte
    pulso.sala.ia = ia
    d = pulso.sala.datos_del_parte()
    assert ia._toca_parte(d, float("inf"))
    ia._escribir_parte(d)
    pedido = ollama.pedidos[-1]["messages"][-1]["content"]
    assert "Puntos:\n- " in pedido and "aún no ha empezado" in pedido and "Salidas de metro" not in pedido
    pulso.sala._cache.clear()
    assert pulso.sala.parte()["ia"]["texto"] == ia.parte["texto"] and "firma" not in pulso.sala.parte()["ia"]
    assert not ia._toca_parte(d, IA_.MIN_ENTRE_PARTES + 1)          # nada ha cambiado: hasta la media hora, no
    assert ia._toca_parte(d, IA_.CADA_PARTE + 1)
    # Empieza el partido: lo escrito («aún no ha empezado») ya no vale y queda el de reglas hasta que haya otro.
    reloj[0] = T0 + 3600 + 60
    pulso.sala._cache.clear()
    otro = pulso.sala.datos_del_parte()
    assert otro["agenda_hoy"][0]["cuando"].startswith("ya en marcha") and IA_.firma_del_parte(otro) != IA_.firma_del_parte(d)
    assert "ia" not in pulso.sala.parte() and pulso.sala.parte()["texto"]
    assert not ia._toca_parte(otro, 60) and ia._toca_parte(otro, IA_.MIN_ENTRE_PARTES + 1)
    ia._escribir_parte(otro)
    pulso.sala._cache.clear()
    assert pulso.sala.parte()["ia"]["texto"]


def test_el_primer_parte_no_espera_aunque_el_ordenador_acabe_de_encenderse(pulso, ollama, monkeypatch):
    preparar(pulso)
    monkeypatch.setattr(IA_.time, "time", lambda: T0 + 30)
    monkeypatch.setattr(IA_.time, "monotonic", lambda: 5.0)        # el reloj monótono cuenta desde que se encendió
    ia = IA_.IA(pulso.almacen, pulso.sala.cruce, pulso.sala.zonas, url=ollama.url)
    ia.preparar_parte = pulso.sala.datos_del_parte
    ia.arrancar()
    try:
        limite = time.perf_counter() + 10
        while ia.parte is None and time.perf_counter() < limite:
            time.sleep(0.05)
    finally:
        ia.parar()
    assert ia.parte and ia.hechos["partes"] == 1


def test_ollama_antiguo_sin_think_y_sin_ollama(pulso):
    viejo = OllamaFalso(conoce_think=False)
    try:
        ia = IA_.IA(pulso.almacen, pulso.sala.cruce, pulso.sala.zonas, url=viejo.url)
        assert ia.disponible()
        assert ia.chat("hola", IA_.ESQUEMA_PARTE)["parte"]
        assert "think" not in viejo.pedidos[-1] and "think" in viejo.pedidos[0]
    finally:
        viejo.cerrar()
    nadie = IA_.IA(pulso.almacen, pulso.sala.cruce, url="http://127.0.0.1:9")
    assert nadie.disponible() is False and nadie.estado()["disponible"] is False


def test_avisos_en_castellano_y_redes_de_aqui():
    from osintmaps.pulso import textos
    assert textos.aviso_en_castellano("Moderate coastalevent warning", "Moderate") == "Aviso amarillo por fenómenos costeros"
    assert textos.aviso_en_castellano("Severe wind warning", "Severe") == "Aviso naranja por viento"
    assert textos.aviso_en_castellano("Aviso raro", "") == "Aviso raro"
    posts = {"posts": [
        {"uri": "at://did:plc:a/app.bsky.feed.post/1", "record": {"text": "Óculos de Sol Valencia Premium", "langs": ["pt"], "createdAt": "2026-11-24T18:00:00Z"}},
        {"uri": "at://did:plc:b/app.bsky.feed.post/2", "record": {"text": "Cola enorme en el Mercado Central", "langs": ["es"], "createdAt": "2026-11-24T18:00:00Z"}},
        {"uri": "at://did:plc:c/app.bsky.feed.post/3", "record": {"text": "Bon dia, València", "createdAt": "2026-11-24T18:00:00Z"}}]}
    assert [i.texto for i in textos.leer_bluesky(posts)] == ["Cola enorme en el Mercado Central", "Bon dia, València"]
