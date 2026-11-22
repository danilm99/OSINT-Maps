"""Ejecuta «osintmaps buscar» completo con la red simulada."""

import csv
import json
import xml.etree.ElementTree as ET

import pytest

from osintmaps import cli
from osintmaps.fuentes import camaras, catastro, osm, wikidata

from .conftest import FEED
from .test_fuentes_abiertas import RESPUESTA_CAMARAS, RESPUESTA_OSM, _fila


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


def test_sin_zona_avisa(capsys):
    assert cli.main(["buscar"]) == 2
    assert "Indica una zona" in capsys.readouterr().out


def test_el_servidor_no_deja_salir_de_la_carpeta_de_datos(tmp_path):
    cli._Servidor.carpeta_datos = tmp_path
    ruta = cli._Servidor.translate_path(cli._Servidor.__new__(cli._Servidor), "/datos/../../etc/passwd")
    assert ruta == str(tmp_path / "passwd")


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


def test_paquete_autonomo(red_simulada, tmp_path, capsys):
    salida = tmp_path / "datos"
    cli.main(["buscar", "--municipios", "46900", "--salida", str(salida), "--cache", str(tmp_path / "cache")])
    # Un nombre malicioso en los datos no debe poder cerrar la etiqueta <script>.
    ruta = salida / "candidatos.geojson"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["features"][0]["properties"]["nombre"] = "</script><script>alert(1)</script>"
    ruta.write_text(json.dumps(datos), encoding="utf-8")

    assert cli.main(["paquete", "--datos", str(salida), "--min-puntuacion", "40"]) == 0
    html = (salida / "mapa.html").read_text(encoding="utf-8")
    assert "<!--DATOS_INCRUSTADOS-->" not in html
    assert "window.OSINT_DATOS=" in html and "window.OSINT_HUELLAS=" in html
    incrustadas = html.split("window.OSINT_CAMARAS=")[1].split(";</script>")[0].split(";window.")[0]
    assert len(json.loads(incrustadas.replace("<\\/", "</"))["features"]) == 2
    assert "</script><script>alert(1)" not in html
    incrustado = html.split("window.OSINT_DATOS=")[1].split(";window.OSINT_HUELLAS=")[0]
    assert len(json.loads(incrustado.replace("<\\/", "</"))["features"]) == 1     # solo el de nota >= 40
