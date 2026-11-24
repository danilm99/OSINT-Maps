"""Ejecuta «osintmaps buscar» completo con la red simulada."""

import csv
import json
import xml.etree.ElementTree as ET

import pytest

from osintmaps import cli
from osintmaps.fuentes import camaras, catastro, dgt, listaroja, osm, wikidata

from .conftest import FEED
from .test_fuentes_abiertas import PAGINA_LISTA_ROJA, RESPUESTA_CAMARAS, RESPUESTA_OSM, XML_DGT, _fila, red_subastas


class Respuesta:
    def __init__(self, *, texto=None, datos=None):
        self.content = (texto or "").encode("utf-8")
        self._datos = datos

    def json(self):
        return self._datos


@pytest.fixture
def red_simulada(monkeypatch, zip_municipio):
    llamadas = {"osm": [], "camaras": [], "wikidata": 0}

    monkeypatch.setattr(catastro, "pedir", lambda sesion, metodo, url, **kw: Respuesta(texto=FEED))
    monkeypatch.setattr(catastro, "descargar", lambda sesion, url, destino, **kw: zip_municipio)

    def overpass(sesion, metodo, url, **kw):
        llamadas["osm"].append(kw["data"]["data"])
        return Respuesta(datos=RESPUESTA_OSM)

    def sparql(sesion, metodo, url, **kw):
        llamadas["wikidata"] += 1
        filas = [_fila("Q111", "Fábrica de Prueba", -0.6721, 39.5466, clase="factory", estado="abandoned")]
        return Respuesta(datos={"results": {"bindings": filas if llamadas["wikidata"] == 1 else []}})

    def overpass_camaras(sesion, metodo, url, **kw):
        llamadas["camaras"].append(kw["data"]["data"])
        return Respuesta(datos=RESPUESTA_CAMARAS)

    monkeypatch.setattr(osm, "pedir", overpass)
    monkeypatch.setattr(camaras, "pedir", overpass_camaras)
    # Capas extra: Lista Roja, cámaras de la DGT y subastas.
    monkeypatch.setattr(listaroja, "pedir", lambda *a, **kw: type("R", (), {"text": PAGINA_LISTA_ROJA})())
    monkeypatch.setattr(dgt, "pedir", lambda *a, **kw: type("R", (), {"content": XML_DGT})())
    llamadas["subastas"] = red_subastas(monkeypatch)
    monkeypatch.setattr(wikidata, "pedir", sparql)
    monkeypatch.setattr(wikidata.time, "sleep", lambda s: None)
    return llamadas


def test_buscar_un_municipio(red_simulada, tmp_path, capsys):
    salida = tmp_path / "datos"
    codigo = cli.main(["buscar", "--municipios", "46900", "--salida", str(salida),
                       "--cache", str(tmp_path / "cache")])
    assert codigo == 0

    # Con --municipios, OSM se consulta por la caja del municipio, no por provincia.
    assert "area[" not in red_simulada["osm"][0]

    geojson = json.loads((salida / "candidatos.geojson").read_text(encoding="utf-8"))
    por_id = {f["properties"]["id"]: f for f in geojson["features"]}
    # Fábrica (Catastro + OSM + Wikidata fundidos) y corral (Catastro). El edificio suelto de
    # OSM sin nombre ni tipo se descarta: donde hay Catastro no aporta nada.
    assert set(por_id) == {"cat-0000001YJ0000A", "cat-0000004YJ0000D"}

    fabrica = por_id["cat-0000001YJ0000A"]["properties"]
    assert sorted(fabrica["fuentes"]) == ["catastro", "osm", "wikidata"]
    assert fabrica["nombre"] == "Fábrica de Prueba"
    assert fabrica["wikidata"] == "Q111"
    assert fabrica["desglose"]["fuentes"] == 15
    assert geojson["features"][0]["properties"]["id"] == "cat-0000001YJ0000A"   # la mejor, primera
    assert fabrica["enlaces"]["catastro"].startswith("https://www1.sedecatastro.gob.es/")

    huellas = json.loads((salida / "huellas.geojson").read_text(encoding="utf-8"))
    assert {f["properties"]["id"] for f in huellas["features"]} == {"cat-0000001YJ0000A", "cat-0000004YJ0000D"}

    with open(salida / "candidatos.csv", encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))
    assert len(filas) == 2 and filas[0]["nombre"] == "Fábrica de Prueba"

    kml = ET.parse(salida / "candidatos.kml")           # debe ser XML bien formado
    assert len(kml.findall(".//{http://www.opengis.net/kml/2.2}Placemark")) == 2

    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["total"] == 2 and resumen["varias_fuentes"] == 1
    assert "2 candidatos" in capsys.readouterr().out


def test_buscar_provincia_usa_el_limite_provincial(red_simulada, tmp_path):
    codigo = cli.main(["buscar", "--provincia", "46", "--sin-wikidata", "--salida", str(tmp_path / "d"),
                       "--cache", str(tmp_path / "c")])
    assert codigo == 0
    assert 'area["ISO3166-2"~"^(ES-V)$"]' in red_simulada["osm"][0]


def test_una_fuente_caida_no_tumba_el_resto(red_simulada, monkeypatch, tmp_path):
    def roto(*a, **kw):
        raise RuntimeError("servidor caído")

    monkeypatch.setattr(osm, "pedir", roto)
    salida = tmp_path / "datos"
    assert cli.main(["buscar", "--municipios", "46900", "--salida", str(salida),
                     "--cache", str(tmp_path / "cache")]) == 0
    geojson = json.loads((salida / "candidatos.geojson").read_text(encoding="utf-8"))
    assert len(geojson["features"]) == 2      # solo lo de Catastro (uno confirmado por Wikidata)


def test_buscar_guarda_las_camaras_en_su_propia_capa(red_simulada, tmp_path):
    salida = tmp_path / "datos"
    cli.main(["buscar", "--municipios", "46900", "--salida", str(salida), "--cache", str(tmp_path / "cache")])
    assert "area[" not in red_simulada["camaras"][0]          # por la caja del municipio
    capa = json.loads((salida / "camaras.geojson").read_text(encoding="utf-8"))
    assert [f["properties"]["id"] for f in capa["features"]] == ["node/501", "way/503"]
    assert json.loads((salida / "resumen.json").read_text(encoding="utf-8"))["camaras"] == 2
    # Las cámaras no se cuelan entre los sitios abandonados.
    sitios = json.loads((salida / "candidatos.geojson").read_text(encoding="utf-8"))
    assert all("surveillance" not in json.dumps(f) for f in sitios["features"])

    # Con --provincia sola se piden por el límite provincial; con --sin-camaras no se piden.
    cli.main(["buscar", "--provincia", "46", "--salida", str(salida), "--cache", str(tmp_path / "cache")])
    assert '(area.zona)' in red_simulada["camaras"][-1]
    pedidas = len(red_simulada["camaras"])
    cli.main(["buscar", "--municipios", "46900", "--sin-camaras", "--salida", str(tmp_path / "otra"),
              "--cache", str(tmp_path / "cache2")])
    assert len(red_simulada["camaras"]) == pedidas
    assert not (tmp_path / "otra" / "camaras.geojson").exists()


def test_las_camaras_caidas_no_tumban_la_busqueda(red_simulada, monkeypatch, tmp_path):
    def roto(*a, **kw):
        raise ConnectionError("sin red")

    monkeypatch.setattr(camaras, "pedir", roto)
    salida = tmp_path / "datos"
    assert cli.main(["buscar", "--municipios", "46900", "--salida", str(salida), "--cache", str(tmp_path / "cache")]) == 0
    assert (salida / "candidatos.geojson").exists() and not (salida / "camaras.geojson").exists()


def test_buscar_descarga_las_capas_extra(red_simulada, monkeypatch, tmp_path):
    salida = tmp_path / "datos"
    cli.main(["buscar", "--municipios", "46900", "--salida", str(salida), "--cache", str(tmp_path / "cache")])
    leer = lambda nombre: json.loads((salida / f"capa-{nombre}.geojson").read_text(encoding="utf-8"))["features"]
    assert [f["properties"]["nombre"] for f in leer("listaroja")] == ["Torre de Prueba"]
    assert leer("dgt")[0]["properties"]["imagen"].endswith("176130.jpg")
    assert len(leer("subastas")) == 2 and leer("subastas")[0]["geometry"]["coordinates"] == [-0.2501, 39.1601]

    # «capas» las refresca sin repetir la búsqueda; una fuente caída conserva su fichero.
    def roto(*a, **kw):
        raise ConnectionError("sin red")

    monkeypatch.setattr(dgt, "pedir", roto)
    (salida / "capa-listaroja.geojson").unlink()
    assert cli.main(["capas", "--provincia", "46", "--salida", str(salida), "--cache", str(tmp_path / "cache")]) == 0
    assert len(leer("listaroja")) == 1 and len(leer("dgt")) == 1
    assert cli.main(["capas", "--solo", "inventada", "--salida", str(salida)]) == 2

    # Con --sin-capas no se tocan.
    otra = tmp_path / "otra"
    cli.main(["buscar", "--municipios", "46900", "--sin-capas", "--sin-camaras", "--salida", str(otra), "--cache", str(tmp_path / "cache")])
    assert not list(otra.glob("capa-*.geojson"))


def test_sin_zona_avisa(capsys):
    assert cli.main(["buscar"]) == 2
    assert "Indica una zona" in capsys.readouterr().out


def test_el_servidor_no_deja_salir_de_la_carpeta_de_datos(tmp_path):
    cli._Servidor.carpeta_datos = tmp_path
    ruta = cli._Servidor.translate_path(cli._Servidor.__new__(cli._Servidor), "/datos/../../etc/passwd")
    assert ruta == str(tmp_path / "passwd")
    # La única subcarpeta que se sirve es la de las líneas detectadas en la foto aérea; tampoco deja salirse.
    traducir = lambda camino: cli._Servidor.translate_path(cli._Servidor.__new__(cli._Servidor), camino)
    assert traducir("/datos/vision/cat-1.json?x=1") == str(tmp_path / "vision" / "cat-1.json")
    assert traducir("/datos/vision/../../etc/passwd") == str(tmp_path / "vision" / "passwd")
    assert traducir("/datos/otra/cat-1.json") == str(tmp_path / "cat-1.json")


def test_sin_resultados_no_pisa_los_datos_anteriores(red_simulada, monkeypatch, tmp_path, capsys):
    def roto(*a, **kw):
        raise RuntimeError("sin red")

    for modulo in (catastro, osm, wikidata):
        monkeypatch.setattr(modulo, "pedir", roto)
    salida = tmp_path / "datos"
    salida.mkdir()
    (salida / "candidatos.geojson").write_text("anterior", encoding="utf-8")
    assert cli.main(["buscar", "--provincia", "46", "--salida", str(salida), "--cache", str(tmp_path / "c")]) == 1
    assert (salida / "candidatos.geojson").read_text(encoding="utf-8") == "anterior"
    assert "No se obtuvo ningún candidato" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Servidor del mapa y paquete autónomo
# --------------------------------------------------------------------------

@pytest.fixture
def servidor(tmp_path):
    import functools
    import threading

    cli._Servidor.carpeta_datos = tmp_path
    srv = cli.ServidorMapa(("127.0.0.1", 0), functools.partial(cli._Servidor, directory=str(cli.CARPETA_WEB)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    srv.shutdown()


def test_el_servidor_incorpora_solo_las_marcas_que_cambian(servidor):
    import requests
    url, carpeta = servidor
    assert requests.get(f"{url}/").text.startswith("<!DOCTYPE html>")
    # Sin marcas todavía: objeto vacío, no un 404.
    assert requests.get(f"{url}/datos/marcas.json").json() == {}

    # El ordenador marca A; el móvil, que no sabe nada de A, marca B. Deben quedar las dos.
    a = {"cat-A": {"estado": "favorito", "nota": "entrada por el río"}}
    b = {"cat-B": {"estado": "visitado", "nota": ""}}
    assert requests.post(f"{url}/datos/marcas.json", json=a).json() == a
    assert requests.post(f"{url}/datos/marcas.json", json=b).json() == {**a, **b}
    assert json.loads((carpeta / "marcas.json").read_text(encoding="utf-8")) == {**a, **b}

    # Quitar una marca la deja vacía (no la borra), para que el otro dispositivo se entere.
    requests.post(f"{url}/datos/marcas.json", json={"cat-A": {"estado": "", "nota": ""}})
    assert requests.get(f"{url}/datos/marcas.json").json() == {"cat-A": {"estado": "", "nota": ""}, **b}


def test_el_servidor_comprime_y_no_repite_lo_que_el_navegador_ya_tiene(servidor):
    import gzip
    import http.client
    import requests
    url, carpeta = servidor
    contenido = json.dumps({"type": "FeatureCollection", "features": [{"n": k, "texto": "abandonado " * 20} for k in range(200)]})
    (carpeta / "candidatos.geojson").write_text(contenido, encoding="utf-8")

    # Con http.client se ve lo que viaja de verdad (requests lo descomprime sin avisar).
    def pedir(ruta, cabeceras):
        conexion = http.client.HTTPConnection(url.removeprefix("http://"), timeout=10)
        conexion.request("GET", ruta, headers=cabeceras)
        r = conexion.getresponse()
        cuerpo = r.read()
        conexion.close()
        return r, cuerpo

    r, cuerpo = pedir("/datos/candidatos.geojson", {"Accept-Encoding": "gzip"})
    assert r.status == 200 and r.getheader("Content-Encoding") == "gzip"
    assert len(cuerpo) < len(contenido) / 5 and gzip.decompress(cuerpo).decode("utf-8") == contenido
    assert r.getheader("Cache-Control") == "no-cache" and int(r.getheader("Content-Length")) == len(cuerpo)
    etiqueta = r.getheader("ETag")
    assert etiqueta

    # Quien no admite compresión lo recibe tal cual.
    r, cuerpo = pedir("/datos/candidatos.geojson", {})
    assert r.status == 200 and r.getheader("Content-Encoding") is None and cuerpo.decode("utf-8") == contenido

    # Si el navegador ya lo tiene y no ha cambiado: 304 y nada más.
    r, cuerpo = pedir("/datos/candidatos.geojson", {"Accept-Encoding": "gzip", "If-None-Match": etiqueta})
    assert r.status == 304 and cuerpo == b""

    # Chrome, con un servidor HTTP/1.0 como este, pregunta por fecha en vez de por etiqueta.
    fecha = pedir("/datos/candidatos.geojson", {})[0].getheader("Last-Modified")
    assert fecha
    r, cuerpo = pedir("/datos/candidatos.geojson", {"Accept-Encoding": "gzip", "If-Modified-Since": fecha})
    assert r.status == 304 and cuerpo == b""
    r, _ = pedir("/datos/candidatos.geojson", {"Accept-Encoding": "gzip", "If-Modified-Since": "Thu, 01 Jan 2015 00:00:00 GMT"})
    assert r.status == 200

    # Al repetir la búsqueda el fichero cambia: se manda el nuevo, con otra etiqueta.
    (carpeta / "candidatos.geojson").write_text(contenido + " ", encoding="utf-8")
    r, cuerpo = pedir("/datos/candidatos.geojson", {"Accept-Encoding": "gzip", "If-None-Match": etiqueta})
    assert r.status == 200 and r.getheader("ETag") != etiqueta and gzip.decompress(cuerpo).decode("utf-8") == contenido + " "

    # La portada y el programa del visor también van comprimidos.
    for ruta in ("/", "/capas.js"):
        r, cuerpo = pedir(ruta, {"Accept-Encoding": "gzip"})
        assert r.status == 200 and r.getheader("Content-Encoding") == "gzip" and r.getheader("ETag"), ruta
    assert gzip.decompress(pedir("/", {"Accept-Encoding": "gzip"})[1]).startswith(b"<!DOCTYPE html>")

    # Lo que el usuario anota y lo que llega en vivo no se guarda nunca en el navegador.
    requests.post(f"{url}/datos/marcas.json", json={"cat-A": {"estado": "favorito", "nota": ""}})
    r, _ = pedir("/datos/marcas.json", {"Accept-Encoding": "gzip"})
    assert r.status == 200 and r.getheader("Cache-Control") == "no-store" and r.getheader("ETag") is None
    r, _ = pedir("/datos/marcadores.json", {})      # aún no existe: objeto vacío
    assert r.status == 200 and r.getheader("Cache-Control") == "no-store"
    # Un fichero que no existe sigue siendo un 404.
    assert pedir("/datos/no-existe.geojson", {"Accept-Encoding": "gzip"})[0].status == 404


def test_guardados_simultaneos_no_se_pisan(servidor):
    import requests
    from concurrent.futures import ThreadPoolExecutor
    url, carpeta = servidor

    def guardar(i):
        return requests.post(f"{url}/datos/marcas.json", json={f"cat-{i}": {"estado": "favorito", "nota": str(i)}}).status_code

    # 32 conexiones de golpe: más de las que el servidor estándar deja en espera.
    with ThreadPoolExecutor(32) as grupo:
        assert set(grupo.map(guardar, range(60))) == {200}
    guardado = json.loads((carpeta / "marcas.json").read_text(encoding="utf-8"))
    assert len(guardado) == 60
    assert list(carpeta.glob("*.parcial")) == []          # no quedan temporales


def test_el_servidor_rechaza_escrituras_que_no_son_marcas(servidor):
    import requests
    url, carpeta = servidor
    assert requests.post(f"{url}/datos/candidatos.geojson", json={}).status_code == 405
    assert requests.post(f"{url}/datos/marcas.json", data=b"no es json").status_code == 400
    assert requests.post(f"{url}/datos/marcas.json", json=["lista"]).status_code == 400
    assert requests.post(f"{url}/datos/marcas.json", data=b"x" * (cli.MAX_MARCAS + 1)).status_code == 400
    # Una página de otro sitio web no puede cambiar las marcas.
    ajeno = requests.post(f"{url}/datos/marcas.json", json={"x": {"estado": "favorito"}},
                          headers={"Origin": "https://sitio-ajeno.example"})
    assert ajeno.status_code == 403
    assert not (carpeta / "marcas.json").exists()
    # La propia página (mismo origen) sí.
    propio = requests.post(f"{url}/datos/marcas.json", json={"x": {"estado": "favorito"}}, headers={"Origin": url})
    assert propio.status_code == 200


def test_el_servidor_guarda_los_marcadores_propios(servidor):
    import requests
    url, carpeta = servidor
    assert requests.get(f"{url}/datos/marcadores.json").json() == {}

    spot = {"type": "spot", "lat": 39.4699123456, "lng": -0.3763, "note": "muro largo", "created": 1763800000000}
    guardado = requests.post(f"{url}/datos/marcadores.json", json={"m1": spot}).json()
    assert guardado == {"m1": {"type": "spot", "lat": 39.469912, "lng": -0.3763, "note": "muro largo",
                               "created": 1763800000000, "deleted": False}}
    # Otro dispositivo añade el suyo sin conocer el primero; y uno sin coordenadas válidas se ignora.
    requests.post(f"{url}/datos/marcadores.json", json={
        "m2": {"type": "camera", "lat": 39.47, "lng": -0.37, "note": "x" * 900},
        "malo": {"type": "spot", "lat": "norte", "lng": 0},
        "lejos": {"type": "spot", "lat": 91, "lng": 0},
    })
    en_disco = json.loads((carpeta / "marcadores.json").read_text(encoding="utf-8"))
    assert set(en_disco) == {"m1", "m2"} and len(en_disco["m2"]["note"]) == 500

    # Borrar deja el registro marcado (no lo quita), para que el otro dispositivo se entere.
    requests.post(f"{url}/datos/marcadores.json", json={"m1": {**spot, "deleted": True}})
    assert requests.get(f"{url}/datos/marcadores.json").json()["m1"]["deleted"] is True
    # Las marcas de los sitios van en su fichero, sin mezclarse.
    assert requests.get(f"{url}/datos/marcas.json").json() == {}


def test_el_servidor_pide_los_aviones_una_vez_por_zona(servidor, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import requests
    url, _ = servidor
    salidas, candado = [], threading.Lock()

    class Respuesta:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"aircraft": []}

    pedir_de_verdad = requests.get

    def a_la_red(direccion, **kw):
        if "adsb." not in direccion:
            return pedir_de_verdad(direccion, **kw)
        with candado:
            salidas.append(direccion)
        time.sleep(0.15)
        if "/lat/10.000/" in direccion:
            raise ConnectionError("sin red")
        return Respuesta()

    cli._AVIONES.clear()
    cli.aviones._olvidar()
    monkeypatch.setattr(cli.aviones, "MIN_ENTRE", 0)
    monkeypatch.setattr(cli.requests, "get", a_la_red)
    pedir = lambda lat: pedir_de_verdad(f"{url}/vivo/aviones?lat={lat}&lon=-0.37&dist=40", timeout=10)

    # Seis peticiones a la vez por la misma zona: una sola sale a la red.
    with ThreadPoolExecutor(6) as grupo:
        respuestas = list(grupo.map(pedir, [39.47] * 6))
    assert {r.status_code for r in respuestas} == {200} and respuestas[0].json() == {"ac": [], "fuente": "adsb.fi"}
    assert len(salidas) == 1
    # Otra zona no borra la primera: al volver a ella no se pregunta de nuevo.
    assert pedir(41.0).status_code == 200 and pedir(39.47).status_code == 200
    assert len(salidas) == 2
    # Si el servicio falla se dice, y no se guarda nada; los parámetros malos se rechazan.
    assert pedir(10.0).status_code == 502 and len(salidas) == 4          # probó los dos servicios
    assert pedir_de_verdad(f"{url}/vivo/aviones?lat=norte&lon=0", timeout=10).status_code == 400
    assert len(cli._AVIONES) == 2


def test_el_servidor_hace_de_relevo_de_trenes_y_fichas(servidor, monkeypatch):
    import requests
    url, _ = servidor
    pedidas = []

    class Respuesta:
        def __init__(self, texto):
            self.text, self.content = texto, texto.encode("utf-8")

        def raise_for_status(self):
            pass

    pedir_de_verdad = requests.get

    def a_la_red(direccion, **kw):
        if "127.0.0.1" in direccion:
            return pedir_de_verdad(direccion, **kw)
        pedidas.append(direccion)
        if "renfe" in direccion:
            return Respuesta('{"entity": [{"vehicle": {"position": {"latitude": 39.46, "longitude": -0.37}}}]}')
        if "/ficha/caida/" in direccion:
            raise ConnectionError("sin red")
        return Respuesta('<meta property="og:image" content="https://listaroja.hispanianostra.org/wp-content/uploads/2026/06/torre.jpeg">'
                         '<meta property="og:description" content="Torre &amp; muralla">'
                         '<img src="https://listaroja.hispanianostra.org/wp-content/uploads/2026/06/torre-150x150.jpeg">'
                         '<a href="https://listaroja.hispanianostra.org/wp-content/uploads/2026/06/patio.jpg">foto</a>')

    cli._RELEVO.clear()
    monkeypatch.setattr(cli.requests, "get", a_la_red)
    # Trenes: se pasa tal cual lo que publica Renfe y no se repite la consulta en unos segundos.
    assert pedir_de_verdad(f"{url}/vivo/trenes", timeout=10).json()["entity"][0]["vehicle"]["position"]["latitude"] == 39.46
    pedir_de_verdad(f"{url}/vivo/trenes", timeout=10)
    assert len(pedidas) == 1

    # Ficha de Hispania Nostra: foto principal, resumen y resto de fotos, sin miniaturas.
    ficha = "https://listaroja.hispanianostra.org/ficha/torre/"
    datos = pedir_de_verdad(f"{url}/vivo/ficha", params={"url": ficha}, timeout=10).json()
    assert datos == {"imagen": "https://listaroja.hispanianostra.org/wp-content/uploads/2026/06/torre.jpeg", "descripcion": "Torre & muralla",
                     "imagenes": ["https://listaroja.hispanianostra.org/wp-content/uploads/2026/06/torre.jpeg",
                                  "https://listaroja.hispanianostra.org/wp-content/uploads/2026/06/patio.jpg"]}
    # Solo se pregunta a esa web: cualquier otra dirección se rechaza sin salir a la red.
    antes = len(pedidas)
    assert pedir_de_verdad(f"{url}/vivo/ficha", params={"url": "https://example.com/ficha/"}, timeout=10).status_code == 400
    assert pedir_de_verdad(f"{url}/vivo/ficha", params={"url": "http://listaroja.hispanianostra.org/ficha/x/"}, timeout=10).status_code == 400
    assert len(pedidas) == antes
    assert pedir_de_verdad(f"{url}/vivo/ficha", params={"url": "https://listaroja.hispanianostra.org/ficha/caida/"}, timeout=10).status_code == 502


def test_una_ficha_lenta_no_deja_esperando_a_los_trenes(servidor, monkeypatch):
    import threading
    import time

    import requests
    url, _ = servidor
    pedidas, soltar = [], threading.Event()

    class Respuesta:
        def __init__(self, texto):
            self.text, self.content = texto, texto.encode("utf-8")

        def raise_for_status(self):
            pass

    pedir_de_verdad = requests.get

    def a_la_red(direccion, **kw):
        if "127.0.0.1" in direccion:
            return pedir_de_verdad(direccion, **kw)
        pedidas.append(direccion)
        if "renfe" in direccion:
            return Respuesta('{"entity": []}')
        soltar.wait(10)      # la web de la ficha tarda en contestar
        return Respuesta('<meta property="og:description" content="Torre">')

    cli._RELEVO.clear()
    cli._CANDADOS_RELEVO.clear()
    monkeypatch.setattr(cli.requests, "get", a_la_red)
    ficha = "https://listaroja.hispanianostra.org/ficha/lenta/"
    respuestas = []
    hilos = [threading.Thread(target=lambda: respuestas.append(pedir_de_verdad(f"{url}/vivo/ficha", params={"url": ficha}, timeout=15).json())) for _ in range(2)]
    for h in hilos:
        h.start()
    time.sleep(0.3)      # las dos peticiones de la ficha ya están dentro, esperando a la web

    # Mientras tanto los trenes contestan enseguida.
    t0 = time.monotonic()
    assert pedir_de_verdad(f"{url}/vivo/trenes", timeout=5).json() == {"entity": []}
    assert time.monotonic() - t0 < 2

    soltar.set()
    for h in hilos:
        h.join(15)
    assert [r["descripcion"] for r in respuestas] == ["Torre", "Torre"]
    # Y la misma ficha pedida dos veces a la vez solo sale una vez a la red.
    assert len([p for p in pedidas if "lenta" in p]) == 1


def test_el_servidor_da_vacio_lo_visto_desde_el_aire_si_no_esta(servidor):
    import requests
    base, carpeta = servidor
    assert requests.get(f"{base}/datos/revision.json", timeout=5).json() == {}
    (carpeta / "revision.json").write_text('{"sitios": {"cat-1": {"estado": "solar"}}}', encoding="utf-8")
    (carpeta / "vision").mkdir()
    (carpeta / "vision" / "cat-1.json").write_text('{"o": [0, 0], "l": []}', encoding="utf-8")
    assert requests.get(f"{base}/datos/revision.json", timeout=5).json()["sitios"]["cat-1"]["estado"] == "solar"
    assert requests.get(f"{base}/datos/vision/cat-1.json", timeout=5).json() == {"o": [0, 0], "l": []}
    assert requests.get(f"{base}/datos/vision/no-existe.json", timeout=5).status_code == 404


def test_el_servidor_da_vacia_la_capa_de_posibles_si_no_esta(servidor):
    import requests
    base, carpeta = servidor
    # El visor la pide siempre; las capas de «osintmaps capas», en cambio, sí dan 404 mientras no se bajen.
    assert requests.get(f"{base}/datos/capa-posibles.geojson", timeout=5).json() == {"type": "FeatureCollection", "features": []}
    assert requests.get(f"{base}/datos/capa-no-existe.geojson", timeout=5).status_code == 404
    capa = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.4, 39.5]}, "properties": {"id": "posible/1"}}]}
    (carpeta / "capa-posibles.geojson").write_text(json.dumps(capa), encoding="utf-8")
    assert requests.get(f"{base}/datos/capa-posibles.geojson", timeout=5).json() == capa


def test_el_servidor_da_vacias_las_noticias_si_no_se_han_buscado(servidor):
    import requests
    base, carpeta = servidor
    assert requests.get(f"{base}/datos/historia.json", timeout=5).json() == {}
    (carpeta / "historia.json").write_text('{"sitios": {"cat-1": {"noticias": []}}}', encoding="utf-8")
    assert requests.get(f"{base}/datos/historia.json", timeout=5).json() == {"sitios": {"cat-1": {"noticias": []}}}


RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>"Castell del Borró" "Ròtova" - Google Noticias</title>
<item><title>Ròtova inicia los trámites para recuperar el Castell del Borró - Cadena SER</title><link>https://news.google.com/rss/articles/uno?oc=5</link>
<pubDate>Mon, 29 Jun 2026 07:00:00 GMT</pubDate><source url="https://cadenaser.com">Cadena SER</source></item>
<item><title>Fiestas de Ròtova: programa completo - Levante-EMV</title><link>https://news.google.com/rss/articles/tres?oc=5</link>
<pubDate>Sat, 08 Aug 2026 07:00:00 GMT</pubDate><source url="https://www.levante-emv.com">Levante-EMV</source></item>
<item><title>El patrimonio de Ròtova, en riesgo - Levante-EMV</title><link>https://news.google.com/rss/articles/dos?oc=5</link>
<pubDate>Sat, 01 Aug 2026 07:00:00 GMT</pubDate><source url="https://www.levante-emv.com">Levante-EMV</source></item></channel></rss>"""


def test_el_servidor_busca_noticias_y_no_insiste_si_google_pide_parar(servidor, monkeypatch):
    import requests
    url, _ = servidor
    pedidas = []
    estado = {"codigo": 200}

    class Respuesta:
        def __init__(self, codigo, texto):
            self.status_code, self.text, self.content = codigo, texto, texto.encode("utf-8")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    pedir_de_verdad = requests.get

    def a_la_red(direccion, **kw):
        if "127.0.0.1" in direccion:
            return pedir_de_verdad(direccion, **kw)
        pedidas.append(direccion)
        return Respuesta(estado["codigo"], RSS if estado["codigo"] == 200 else "sorry")

    cli._RELEVO.clear()
    cli._PAUSA_NOTICIAS[0] = 0.0
    monkeypatch.setattr(cli.requests, "get", a_la_red)
    datos = pedir_de_verdad(f"{url}/vivo/noticias", params={"nombre": "Castell del Borró", "municipio": "Ròtova"}, timeout=10).json()
    assert datos["consulta"] == '"Castell del Borró" "Ròtova"'
    assert [(n["titulo"], n["medio"], n["fecha"], n["nombra"]) for n in datos["noticias"]] == [
        ("Ròtova inicia los trámites para recuperar el Castell del Borró", "Cadena SER", "2026-06-29", True),
        ("El patrimonio de Ròtova, en riesgo", "Levante-EMV", "2026-08-01", False)]      # la de las fiestas no dice nada del sitio: fuera
    assert all(n["url"].startswith("https://news.google.com/") for n in datos["noticias"])
    # Solo se pregunta a Google Noticias, con el nombre y el municipio entre comillas, y la respuesta se guarda unas horas.
    assert len(pedidas) == 1 and pedidas[0].startswith("https://news.google.com/rss/search?q=%22Castell+del+Borr%C3%B3%22+%22R%C3%B2tova%22")
    pedir_de_verdad(f"{url}/vivo/noticias", params={"nombre": "Castell del Borró", "municipio": "Ròtova"}, timeout=10)
    assert len(pedidas) == 1
    # Sin nombre no hay búsqueda.
    assert pedir_de_verdad(f"{url}/vivo/noticias", params={"nombre": "ab"}, timeout=10).status_code == 400
    assert len(pedidas) == 1
    # Si Google contesta «demasiadas peticiones», se devuelve el fallo y durante un rato ni se le pregunta.
    estado["codigo"] = 429
    assert pedir_de_verdad(f"{url}/vivo/noticias", params={"nombre": "Molino de Abajo", "municipio": "Chelva"}, timeout=10).status_code == 502
    assert len(pedidas) == 2
    estado["codigo"] = 200
    assert pedir_de_verdad(f"{url}/vivo/noticias", params={"nombre": "Otro Molino", "municipio": "Chelva"}, timeout=10).status_code == 503
    assert len(pedidas) == 2
    # Lo que ya estaba guardado se sigue sirviendo mientras dura la pausa; pasada, se vuelve a preguntar.
    assert pedir_de_verdad(f"{url}/vivo/noticias", params={"nombre": "Castell del Borró", "municipio": "Ròtova"}, timeout=10).json()["noticias"][0]["medio"] == "Cadena SER"
    assert len(pedidas) == 2
    cli._PAUSA_NOTICIAS[0] = 0.0
    assert pedir_de_verdad(f"{url}/vivo/noticias", params={"nombre": "Otro Molino", "municipio": "Chelva"}, timeout=10).status_code == 200
    assert len(pedidas) == 3


def test_el_servidor_se_identifica(servidor):
    import requests
    url, _ = servidor
    r = requests.get(f"{url}/vivo/hola", timeout=10)
    assert r.json() == {"osintmaps": cli.__version__} and r.headers["Cache-Control"] == "no-store"


def test_sitio_estatico(tmp_path, capsys):
    datos = tmp_path / "datos"
    datos.mkdir()
    for nombre in ("candidatos.geojson", "huellas.geojson", "camaras.geojson", "capa-dgt.geojson", "marcas.json", "marcadores.json", "otra-cosa.txt"):
        (datos / nombre).write_text("{}", encoding="utf-8")

    # Por defecto, los resultados sí y las notas personales no.
    sitio = tmp_path / "sitio"
    assert cli.main(["sitio", "--salida", str(sitio), "--datos", str(datos)]) == 0
    assert {f.name for f in sitio.iterdir()} >= {"index.html", "capas.js", "iconos.js", "herramientas.js", "rutas.js", "vision.js", "historia.js", "tresd.js", "pulso.js", "sw.js", "manifest.webmanifest", "icono-192.png", ".nojekyll", "datos"}
    # Cada programa se pide con la marca de su contenido: una versión nueva no se mezcla con ficheros viejos del navegador.
    import hashlib, re
    pagina_sitio = (sitio / "index.html").read_text(encoding="utf-8")
    marcas = dict(re.findall(r'<script src="(\w+\.js)\?v=([0-9a-f]{10})"></script>', pagina_sitio))
    assert set(marcas) == {"iconos.js", "capas.js", "herramientas.js", "rutas.js", "vision.js", "historia.js", "tresd.js", "pulso.js"}
    assert all(hashlib.sha256((sitio / nombre).read_bytes()).hexdigest()[:10] == marca for nombre, marca in marcas.items())
    assert '<script src="capas.js"></script>' in (cli.CARPETA_WEB / "index.html").read_text(encoding="utf-8")      # el original no se toca
    assert sorted(f.name for f in (sitio / "datos").iterdir()) == ["camaras.geojson", "candidatos.geojson", "capa-dgt.geojson", "capa-posibles.geojson", "historia.json", "huellas.geojson", "revision.json"]
    assert (sitio / "datos" / "revision.json").read_text(encoding="utf-8") == "{}"      # lo visto desde el aire: vacío si no se ha calculado
    assert (sitio / "datos" / "historia.json").read_text(encoding="utf-8") == "{}"      # las noticias: vacías si no se han buscado
    assert json.loads((sitio / "datos" / "capa-posibles.geojson").read_text(encoding="utf-8"))["features"] == []
    assert json.loads((sitio / "manifest.webmanifest").read_text(encoding="utf-8"))["start_url"] == "."      # relativo: vale en una subcarpeta
    assert "ninguno" not in capsys.readouterr().out

    con_notas = tmp_path / "con-notas"
    cli.main(["sitio", "--salida", str(con_notas), "--datos", str(datos), "--con-notas"])
    assert {"marcas.json", "marcadores.json"} <= {f.name for f in (con_notas / "datos").iterdir()}

    # Los posibles abandonos son sospechas sin comprobar: aunque estén calculados, a la web solo van si se pide.
    posibles = '{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[-0.4,39.5]},"properties":{"id":"posible/1"}}]}'
    (datos / "capa-posibles.geojson").write_text(posibles, encoding="utf-8")
    sin_posibles, con_posibles = tmp_path / "sin-posibles", tmp_path / "con-posibles"
    cli.main(["sitio", "--salida", str(sin_posibles), "--datos", str(datos)])
    assert json.loads((sin_posibles / "datos" / "capa-posibles.geojson").read_text(encoding="utf-8"))["features"] == []
    capsys.readouterr()
    cli.main(["sitio", "--salida", str(con_posibles), "--datos", str(datos), "--con-posibles"])
    assert (con_posibles / "datos" / "capa-posibles.geojson").read_text(encoding="utf-8") == posibles
    assert "capa-posibles.geojson" in capsys.readouterr().out
    (datos / "capa-posibles.geojson").unlink()

    # Lo visto desde el aire: el resumen y, con él, la carpeta de líneas (un fichero por sitio). Sin resumen, la carpeta no va.
    (datos / "vision").mkdir()
    (datos / "vision" / "cat-1.json").write_text('{"o":[0,0],"l":[]}', encoding="utf-8")
    (datos / "vision" / "notas.txt").write_text("no es de la web", encoding="utf-8")
    sin_resumen = tmp_path / "sin-resumen"
    cli.main(["sitio", "--salida", str(sin_resumen), "--datos", str(datos)])
    assert not (sin_resumen / "datos" / "vision").exists()
    (datos / "revision.json").write_text('{"sitios":{"cat-1":{"estado":"solar"}}}', encoding="utf-8")
    capsys.readouterr()
    con_vision = tmp_path / "con-vision"
    cli.main(["sitio", "--salida", str(con_vision), "--datos", str(datos)])
    assert (con_vision / "datos" / "revision.json").exists()
    assert [f.name for f in (con_vision / "datos" / "vision").iterdir()] == ["cat-1.json"]
    assert "vision/ (1 sitios)" in capsys.readouterr().out

    # Las noticias que buscó «osintmaps historia» viajan con la web.
    prensa = '{"sitios":{"cat-1":{"consulta":"\\"Molino\\"","noticias":[{"titulo":"El molino","url":"https://news.google.com/rss/articles/x"}]}}}'
    (datos / "historia.json").write_text(prensa, encoding="utf-8")
    con_prensa = tmp_path / "con-prensa"
    cli.main(["sitio", "--salida", str(con_prensa), "--datos", str(datos)])
    assert (con_prensa / "datos" / "historia.json").read_text(encoding="utf-8") == prensa

    solo_visor = tmp_path / "solo-visor"
    cli.main(["sitio", "--salida", str(solo_visor), "--sin-datos"])
    assert not (solo_visor / "datos").exists() and (solo_visor / "index.html").exists()


def test_publicar_en_la_rama_de_paginas(tmp_path, capsys):
    import subprocess
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remoto)], check=True)
    datos = tmp_path / "datos"
    datos.mkdir()
    (datos / "candidatos.geojson").write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
    (datos / "marcadores.json").write_text('{"m1": {"lat": 1, "lng": 2}}', encoding="utf-8")

    assert cli.main(["publicar", "--datos", str(datos), "--repo", str(remoto)]) == 0
    listado = subprocess.run(["git", "--git-dir", str(remoto), "ls-tree", "-r", "--name-only", "gh-pages"], capture_output=True, text=True, check=True).stdout.split()
    assert {"index.html", "sw.js", ".nojekyll", "datos/candidatos.geojson"} <= set(listado) and "datos/marcadores.json" not in listado

    # Publicar otra vez rehace la rama: sigue habiendo un solo commit. Con --con-notas van también las notas.
    assert cli.main(["publicar", "--datos", str(datos), "--repo", str(remoto), "--con-notas"]) == 0
    assert subprocess.run(["git", "--git-dir", str(remoto), "rev-list", "--count", "gh-pages"], capture_output=True, text=True, check=True).stdout.strip() == "1"
    listado = subprocess.run(["git", "--git-dir", str(remoto), "ls-tree", "-r", "--name-only", "gh-pages"], capture_output=True, text=True, check=True).stdout.split()
    assert "datos/marcadores.json" in listado


def test_paquete_autonomo(red_simulada, tmp_path, capsys):
    salida = tmp_path / "datos"
    cli.main(["buscar", "--municipios", "46900", "--salida", str(salida), "--cache", str(tmp_path / "cache")])
    # Un nombre malicioso en los datos no debe poder cerrar la etiqueta <script>.
    ruta = salida / "candidatos.geojson"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["features"][0]["properties"]["nombre"] = "</script><script>alert(1)</script>"
    ruta.write_text(json.dumps(datos), encoding="utf-8")

    dentro = next(f["properties"]["id"] for f in datos["features"] if f["properties"]["puntuacion"] >= 40)
    (salida / "revision.json").write_text(json.dumps({"vuelo": "2025", "sitios": {dentro: {"estado": "solar"}, "no-va": {"estado": "ruina"}}}), encoding="utf-8")
    noticia = {"titulo": "La fábrica, en ruinas", "medio": "Diario", "fecha": "2026-05-01", "url": "https://news.google.com/rss/articles/x", "nombra": True}
    (salida / "historia.json").write_text(json.dumps({"sitios": {dentro: {"consulta": '"Fábrica"', "noticias": [noticia]}, "no-va": {"noticias": [noticia]},
                                                                 "sin-noticias": {"noticias": []}}}), encoding="utf-8")

    assert cli.main(["paquete", "--datos", str(salida), "--min-puntuacion", "40"]) == 0
    html = (salida / "mapa.html").read_text(encoding="utf-8")
    assert "<!--DATOS_INCRUSTADOS-->" not in html
    revision = json.loads(html.split("window.OSINT_REVISION=")[1].split(";window.OSINT_DATOS=")[0].replace("<\\/", "</"))
    assert list(revision["sitios"]) == [dentro]                                 # lo visto desde el aire, solo de los sitios que van
    assert '<script src="vision.js">' not in html and "function bloqueVision" in html
    assert html.index("function calcularRuta") < html.index("function bloqueVision") < html.index("function entrar3D")
    prensa = json.loads(html.split("window.OSINT_HISTORIA=")[1].split(";window.OSINT_REVISION=")[0].replace("<\\/", "</"))
    assert prensa["sitios"] == {dentro: {"consulta": '"Fábrica"', "noticias": [noticia]}}      # las noticias, solo de los sitios que van y que tienen alguna
    assert '<script src="historia.js">' not in html and html.index("function bloqueVision") < html.index("function bloqueHistoria") < html.index("function entrar3D")
    assert "OSINT_PRONTO = {}" not in html and "<!--PRONTO-->" not in html      # con los datos dentro no hay nada que pedir por adelantado
    assert "window.OSINT_DATOS=" in html and "window.OSINT_HUELLAS=" in html
    incrustadas = html.split("window.OSINT_CAMARAS=")[1].split(";</script>")[0].split(";window.")[0]
    capas = json.loads(html.split("window.OSINT_CAPAS=")[1].split(";</script>")[0].replace("<\\/", "</"))
    assert set(capas) == {"listaroja", "dgt", "subastas"}
    # El resto del programa del visor también va dentro: no queda ningún fichero suelto por cargar.
    assert '<script src="capas.js">' not in html and "function abrirElemento" in html
    assert '<script src="iconos.js">' not in html and "const Simbolo = L.CircleMarker.extend" in html
    assert '<script src="herramientas.js">' not in html and "function medirDesde" in html
    assert '<script src="rutas.js">' not in html and "function calcularRuta" in html            # cómo llegar
    assert '<script src="tresd.js">' not in html and "function entrar3D" in html               # la vista en 3D
    assert html.index("function medirDesde") < html.index("function calcularRuta") < html.index("function entrar3D")      # en el orden en que se necesitan
    assert html.index("const Simbolo") < html.index("function abrirElemento")      # los iconos, antes que quien los usa
    assert len(json.loads(incrustadas.replace("<\\/", "</"))["features"]) == 2
    assert "</script><script>alert(1)" not in html
    incrustado = html.split("window.OSINT_DATOS=")[1].split(";window.OSINT_HUELLAS=")[0]
    assert len(json.loads(incrustado.replace("<\\/", "</"))["features"]) == 1     # solo el de nota >= 40
