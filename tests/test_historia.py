"""La historia en la prensa: qué se pregunta a Google Noticias, qué se guarda y cuándo se para."""

import json
from datetime import date

import pytest
import requests

from osintmaps import cli, historia
from osintmaps.modelos import Candidato


def rss(*noticias):
    items = "".join(f"<item><title>{t} - {m}</title><link>{u}</link><pubDate>{f}</pubDate><source url=\"https://x\">{m}</source></item>" for t, m, f, u in noticias)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'.encode("utf-8")


@pytest.mark.parametrize("nombre, distintivo", [
    ("Castell del Borró", True),            # «Borró» no es una palabra corriente
    ("Molino Barrioso", True),
    ("Bibioj", True),
    ("Antigua Estación de FEVE de Nazaret", True),
    ("Casa Alta", False),                    # solo palabras corrientes: de estas hay una en cada pueblo
    ("Casas de la Vereda", True),            # «vereda» sí cuenta
    ("Corral de los Santos", False),
    ("Casa de Mora", False),
    ("Molí Vell", False),                    # valenciano: «molino viejo»
    ("Mas de Sant Vicent", False),
    ("", False),
])
def test_un_nombre_es_distintivo_si_tiene_alguna_palabra_propia(nombre, distintivo):
    assert historia.es_distintivo(nombre) is distintivo


@pytest.mark.parametrize("titular, nombre, lo_nombra", [
    ("Ròtova inicia los trámites para recuperar el Castell del Borró", "Castell del Borró", True),
    ("Rótova recupera el castillo de Borró", "Castell del Borró", True),                 # castellano por valenciano y sin acentos
    ("Pueblos abandonados en Castellón: 8 aldeas sin habitantes", "Bibioj", False),
    ("La antigua estación de Nazaret, en ruinas", "Antigua Estación de FEVE de Nazaret", True),      # la mayoría de las palabras y una propia
    ("La estación antigua se cae", "Antigua Estación de FEVE de Nazaret", False),         # ninguna propia
    ("Galería: Casa Alta / AS/D", "Casa Alta", True),                                    # sin palabras propias hacen falta todas
    ("Una casa de alta costura", "Casa Alta", True),                                     # (y aun así se cuelan: por eso se pide además el municipio)
    ("La casa del pueblo", "Casa Alta", False),
    ("Cualquier cosa", "", False),
])
def test_un_titular_nombra_al_sitio(titular, nombre, lo_nombra):
    assert historia.nombra(titular, nombre) is lo_nombra


def test_se_busca_por_el_titulo_del_articulo_si_es_mas_corto():
    largo = "Estación de Ferrocarril de Ribarroja del Turia en la Línea Valencia -Liria"
    assert historia.nombre_de_busqueda(largo, "es:Estación de Ribarroja del Turia (Línea Valencia-Liria)") == "Estación de Ribarroja del Turia"
    assert historia.nombre_de_busqueda("Castell del Borró", "ca:Castell_de_Borró") == "Castell de Borró"
    assert historia.nombre_de_busqueda("  Molí   de Pobres ", None) == "Molí de Pobres"
    assert historia.nombre_de_busqueda("Castillo de Gestalgar", "es:Castillo de Gestalgar") == "Castillo de Gestalgar"      # igual de largo: el suyo
    assert historia.nombre_de_busqueda("Antigua Estación de FEVE de Nazaret", "es:La Estación") == "Antigua Estación de FEVE de Nazaret"      # un título corriente no sirve
    assert historia.nombre_de_busqueda("Poblado de Bibioj", "es:Bibioj") == "Poblado de Bibioj"                              # ni uno de una sola palabra


def test_la_consulta_lleva_nombre_y_municipio_entre_comillas():
    assert historia.consulta_de("Castell del Borró", "Ròtova") == '"Castell del Borró" "Ròtova"'
    assert historia.consulta_de("  Molino   de\tAbajo ") == '"Molino de Abajo"'
    assert historia.consulta_de('Casa "la Torre"', "Sagunt / Sagunto") == '"Casa la Torre" "Sagunt"'      # sin comillas dentro y con un solo nombre del municipio
    url = historia.direccion("Castell del Borró", "Ròtova")
    assert url.startswith("https://news.google.com/rss/search?q=%22Castell+del+Borr%C3%B3%22+%22R%C3%B2tova%22") and "hl=es" in url and "gl=ES" in url


def test_leer_rss_limpia_ordena_y_criba():
    canal = rss(("Fiestas de Ròtova", "Levante-EMV", "Sat, 01 Aug 2026 07:00:00 GMT", "https://news.google.com/rss/articles/2"),
                ("El Castell del Borró se restaura", "Cadena SER", "Mon, 29 Jun 2026 07:00:00 GMT", "https://news.google.com/rss/articles/1"),
                ("El Castell del Borró se restaura", "Cadena SER", "Mon, 29 Jun 2026 07:00:00 GMT", "https://news.google.com/rss/articles/1b"),      # repetida
                ("Visita al castillo de Borró", "Las Provincias", "Tue, 02 Jan 2024 07:00:00 GMT", "https://news.google.com/rss/articles/3"),
                ("Enlace sin cifrar", "Blog", "Tue, 02 Jan 2024 07:00:00 GMT", "http://example.com/x"),
                ("Sin fecha: el Borró", "Blog", "no es una fecha", "https://news.google.com/rss/articles/4"))
    noticias = historia.leer_rss(canal, "Castell del Borró")
    # Primero las que lo nombran, de la más nueva a la más vieja; luego las demás. El medio se quita del titular.
    assert [(n["titulo"], n["medio"], n["fecha"], n["nombra"]) for n in noticias] == [
        ("El Castell del Borró se restaura", "Cadena SER", "2026-06-29", True),
        ("Visita al castillo de Borró", "Las Provincias", "2024-01-02", True),
        ("Fiestas de Ròtova", "Levante-EMV", "2026-08-01", False),
        ("Sin fecha: el Borró", "Blog", "", False)]      # media palabra del nombre no basta para darlo por nombrado
    assert all(n["url"].startswith("https://") for n in noticias)
    # Con un nombre de palabras corrientes, lo que no lo nombra en el titular se descarta.
    comun = rss(("La Pobla del Duc cataloga sus bienes protegidos", "Levante-EMV", "Fri, 15 May 2026 07:00:00 GMT", "https://news.google.com/rss/articles/5"),
                ("La Casa Alta, a punto de caerse", "Las Provincias", "Fri, 15 May 2026 07:00:00 GMT", "https://news.google.com/rss/articles/6"))
    assert [n["titulo"] for n in historia.leer_rss(comun, "Casa Alta")] == ["La Casa Alta, a punto de caerse"]
    assert len(historia.leer_rss(rss(*[(f"El Borró, parte {k}", "Diario", "Fri, 15 May 2026 07:00:00 GMT", f"https://news.google.com/rss/articles/{k}") for k in range(20)]), "Castell del Borró")) == historia.MAX_NOTICIAS
    assert historia.leer_rss(b"<html>esto no es un canal", "Castell del Borró") == []


class Sesion:
    """Hace de internet: apunta lo que se le pide y contesta lo que se le haya dicho."""

    def __init__(self, canales=None, municipios=None, codigo=200):
        self.canales, self.municipios, self.codigo, self.pedidas = canales or {}, municipios or {}, codigo, []

    def _respuesta(self, codigo, cuerpo):
        r = requests.Response()
        r.status_code, r._content = codigo, cuerpo
        return r

    def get(self, url, **kw):
        self.pedidas.append(url)
        if self.codigo != 200:
            return self._respuesta(self.codigo, b"sorry")
        return self._respuesta(200, next((canal for trozo, canal in self.canales.items() if trozo in url), rss()))

    def request(self, metodo, url, **kw):      # Photon, a través de red.pedir
        self.pedidas.append(f"photon {kw['params']['lat']},{kw['params']['lon']}")
        municipio = self.municipios.get((kw["params"]["lat"], kw["params"]["lon"]))
        cuerpo = {"features": [{"properties": {"name": "Camino", "city": municipio}}] if municipio else []}
        return self._respuesta(200, json.dumps(cuerpo).encode("utf-8"))


def sitio(id_, nombre, nota, municipio=None, lat=39.5, lon=-0.5):
    return Candidato(id=id_, lat=lat, lon=lon, nombre=nombre, municipio=municipio, puntuacion=nota)


def test_buscar_noticias_para_si_google_lo_pide():
    with pytest.raises(historia.Bloqueado):
        historia.buscar_noticias(Sesion(codigo=429), "Castell del Borró", "Ròtova")
    with pytest.raises(requests.HTTPError):
        historia.buscar_noticias(Sesion(codigo=404), "Castell del Borró", "Ròtova")


def test_repasar_busca_por_orden_de_nota_y_se_puede_repetir(tmp_path):
    ruta, avisos, pausas = tmp_path / "historia.json", [], []
    candidatos = [sitio("a", "Casa Alta", 30), sitio("b", "Castell del Borró", 70, lat=38.9, lon=-0.2), sitio("c", None, 90),
                  sitio("d", "Molino Barrioso", 50, "Castielfabib"), sitio("e", "Corral de los Santos", 10, lat=39.7, lon=-0.6)]
    red = Sesion(canales={"Borr": rss(("El Castell del Borró se restaura", "Cadena SER", "Mon, 29 Jun 2026 07:00:00 GMT", "https://news.google.com/rss/articles/1"))},
                 municipios={(38.9, -0.2): "Ròtova", (39.7, -0.6): "Marines"})
    hoy = date(2026, 11, 23)
    r = historia.repasar(red, candidatos, ruta, pausa=5, decir=avisos.append, dormir=pausas.append, hoy=hoy)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    # El que no tiene nombre no se consulta; los demás, del de más nota al de menos.
    assert list(datos["sitios"]) == ["b", "d", "a", "e"] and r == {"consultados": 4, "con_noticias": 1, "guardados": 4, "pendientes": 0, "bloqueado": False}
    assert datos["fuente"] == historia.FUENTE and datos["generado"]
    assert datos["sitios"]["b"] == {"nombre": "Castell del Borró", "municipio": "Ròtova", "consulta": '"Castell del Borró" "Ròtova"', "consultado": "2026-11-23",
                                    "noticias": [{"titulo": "El Castell del Borró se restaura", "medio": "Cadena SER", "fecha": "2026-06-29", "url": "https://news.google.com/rss/articles/1", "nombra": True}]}
    # El municipio: el de Catastro si lo trae y, si no, el que diga Photon. Sin municipio y con un nombre corriente, ni se pregunta.
    assert datos["sitios"]["d"]["consulta"] == '"Molino Barrioso" "Castielfabib"' and datos["sitios"]["e"]["consulta"] == '"Corral de los Santos" "Marines"'
    assert datos["sitios"]["a"] == {"nombre": "Casa Alta", "municipio": "", "consulta": "", "consultado": "2026-11-23", "noticias": []}
    a_google = [u for u in red.pedidas if u.startswith("https://news.google.com/")]
    assert len(a_google) == 3 and pausas == [5, 5, 5]      # una pausa detrás de cada pregunta a Google
    assert not any("Casa+Alta" in u for u in a_google)

    # Repetir la orden no vuelve a preguntar lo reciente; pasado el plazo, sí.
    antes = len(red.pedidas)
    assert historia.repasar(red, candidatos, ruta, decir=avisos.append, dormir=pausas.append, hoy=date(2026, 12, 1))["consultados"] == 0 and len(red.pedidas) == antes
    assert historia.repasar(red, candidatos, ruta, decir=avisos.append, dormir=pausas.append, hoy=date(2027, 1, 15))["consultados"] == 4
    # El municipio ya averiguado no se vuelve a preguntar a Photon.
    assert sum(1 for u in red.pedidas[antes:] if u.startswith("photon")) == 1      # solo el de «Casa Alta», que sigue sin saberse
    # Un sitio que ya no está en la lista sale del fichero.
    historia.repasar(red, candidatos[1:], ruta, decir=avisos.append, dormir=pausas.append, hoy=date(2027, 1, 15))
    assert "a" not in json.loads(ruta.read_text(encoding="utf-8"))["sitios"]


def test_repasar_se_detiene_y_guarda_cuando_google_bloquea(tmp_path):
    ruta, avisos = tmp_path / "historia.json", []
    candidatos = [sitio("b", "Castell del Borró", 70, "Ròtova"), sitio("d", "Molino Barrioso", 50, "Castielfabib"), sitio("f", "Mas del Frare", 40, "Chelva")]
    candidatos[0].wikipedia = "ca:Castell de Borró"
    red = Sesion()
    hoy = date(2026, 11, 23)
    assert historia.repasar(red, candidatos, ruta, maximo=1, decir=avisos.append, dormir=lambda s: None, hoy=hoy) == {
        "consultados": 1, "con_noticias": 0, "guardados": 1, "pendientes": 2, "bloqueado": False}      # una tanda corta
    red.codigo = 429
    r = historia.repasar(red, candidatos, ruta, decir=avisos.append, dormir=lambda s: None, hoy=hoy)
    assert r["bloqueado"] and r["consultados"] == 0 and r["pendientes"] == 2
    assert sum(1 for u in red.pedidas if u.startswith("https://news.google.com/")) == 2      # tras el primer «demasiadas peticiones» no insiste
    assert any("se para aquí" in a for a in avisos)
    guardado = json.loads(ruta.read_text(encoding="utf-8"))["sitios"]
    assert list(guardado) == ["b"]      # lo que ya estaba sigue estando
    assert guardado["b"]["nombre"] == "Castell de Borró" and guardado["b"]["consulta"] == '"Castell de Borró" "Ròtova"'      # se buscó por el título del artículo, más corto
    # Un fichero estropeado no impide empezar de nuevo.
    ruta.write_text("{esto no es json", encoding="utf-8")
    red.codigo = 200
    assert historia.repasar(red, candidatos, ruta, decir=avisos.append, dormir=lambda s: None, hoy=hoy)["consultados"] == 3


def test_un_fallo_de_red_no_se_apunta_como_sin_noticias(tmp_path):
    ruta = tmp_path / "historia.json"

    class Cortada(Sesion):
        def get(self, url, **kw):
            self.pedidas.append(url)
            raise requests.ConnectionError("sin red")

    red = Cortada()
    r = historia.repasar(red, [sitio(str(k), f"Molino Barrioso {k}", 50 - k, "Chelva") for k in range(8)], ruta, decir=lambda t: None, dormir=lambda s: None)
    assert r["consultados"] == 0 and r["pendientes"] == 8 and len(red.pedidas) == 5      # al quinto fallo seguido lo deja
    assert json.loads(ruta.read_text(encoding="utf-8"))["sitios"] == {}


def test_la_orden_historia(tmp_path, monkeypatch, capsys):
    datos = tmp_path / "datos"
    datos.mkdir()
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.2, 38.9]}, "properties": {"id": "b", "nombre": "Castell del Borró", "municipio": "Ròtova", "puntuacion": 70}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-0.5, 39.5]}, "properties": {"id": "c", "nombre": None, "puntuacion": 90}}]}
    (datos / "candidatos.geojson").write_text(json.dumps(geo), encoding="utf-8")
    red = Sesion(canales={"Borr": rss(("El Castell del Borró se restaura", "Cadena SER", "Mon, 29 Jun 2026 07:00:00 GMT", "https://news.google.com/rss/articles/1"))})
    monkeypatch.setattr(cli, "nueva_sesion", lambda: red)
    assert cli.main(["historia", "--datos", str(datos), "--pausa", "0"]) == 0
    salida = capsys.readouterr().out
    assert "1 de 2 sitios tienen nombre" in salida and "Consultados ahora: 1. Con noticias: 1 de 1 guardados. Quedan por consultar: 0." in salida
    assert json.loads((datos / "historia.json").read_text(encoding="utf-8"))["sitios"]["b"]["noticias"][0]["medio"] == "Cadena SER"
    # Si Google bloquea, la orden lo dice con su código de salida.
    red.codigo = 429
    assert cli.main(["historia", "--datos", str(datos), "--pausa", "0", "--rehacer"]) == 3
    # Sin ningún nombre no hay nada que hacer.
    geo["features"] = geo["features"][1:]
    (datos / "candidatos.geojson").write_text(json.dumps(geo), encoding="utf-8")
    assert cli.main(["historia", "--datos", str(datos)]) == 0 and "Ningún sitio de la lista tiene nombre" in capsys.readouterr().out
