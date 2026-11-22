from shapely.geometry import box

from osintmaps import fusion, osint, puntuacion
from osintmaps.imagen import pnoa, sentinel
from osintmaps.modelos import Candidato


def _catastro(**kw):
    base = dict(id="cat-A", lat=39.5500, lon=-0.6700, categoria="industrial", estado="deficiente",
                fuentes=["catastro"], superficie_m2=2300, n_edificios=2, anio=1925, vecinos_150m=0,
                refcats=["0000001YJ0000A"],
                huella=box(-0.6703, 39.5498, -0.6697, 39.5502))    # ~50 x 45 m
    base.update(kw)
    return Candidato(**base)


def _punto(id, lat, lon, fuente, **kw):
    return Candidato(id=id, lat=lat, lon=lon, fuentes=[fuente], **kw)


def test_punto_dentro_del_contorno_se_incorpora_al_candidato_de_catastro():
    cat = _catastro()
    dentro = _punto("osm-node-1", 39.5500, -0.6700, "osm", nombre="Fábrica de Prueba",
                    categoria="industrial", estado="ruina", osm_ids=["node/1"])
    lejos = _punto("osm-node-2", 39.5600, -0.6700, "osm", categoria="militar", estado="abandonado")
    resultado = fusion.fusionar([cat], [dentro, lejos])
    assert len(resultado) == 2
    assert cat.fuentes == ["catastro", "osm"]
    assert cat.nombre == "Fábrica de Prueba"
    assert cat.estado == "ruina"                  # gana el estado más grave
    assert cat.osm_ids == ["node/1"]


def test_la_categoria_concreta_gana_a_la_generica():
    cat = _catastro(categoria="residencial")
    fusion.fusionar([cat], [_punto("osm-way-9", 39.5500, -0.6700, "osm", categoria="sanitario", estado="abandonado")])
    assert cat.categoria == "sanitario"


def test_el_tipo_descrito_por_osm_manda_sobre_el_uso_de_catastro():
    cat = _catastro(categoria="industrial")
    convento = _punto("osm-way-9", 39.5500, -0.6700, "osm", categoria="religioso", estado="ruina",
                      nombre="Convento", tipo_confirmado=True)
    fusion.fusionar([cat], [convento])
    assert (cat.categoria, cat.tipo_confirmado) == ("religioso", True)


def test_un_eco_de_catastro_en_osm_no_cuenta_como_confirmacion():
    cat = _catastro()
    eco = _punto("osm-way-5", 39.5500, -0.6700, "osm", categoria="residencial", estado="ruina",
                 osm_ids=["way/5"], debil=True)
    suelto = _punto("osm-way-6", 39.5600, -0.6700, "osm", estado="ruina", debil=True)
    cubierta = [(-0.70, 39.50, -0.60, 39.60)]           # caja del municipio que Catastro leyó bien
    con_catastro = fusion.fusionar([cat], [eco, suelto], cobertura=cubierta)
    assert con_catastro == [cat]
    assert cat.fuentes == ["catastro"] and cat.osm_ids == ["way/5"]     # queda el enlace, no la fuente
    assert (cat.categoria, cat.estado) == ("industrial", "deficiente")
    # Sin Catastro (p. ej. País Vasco), esos edificios sí son candidatos.
    assert len(fusion.fusionar([], [suelto])) == 1
    # Y también si Catastro funcionó en otro municipio pero no en el del edificio.
    otra_zona = [(-1.30, 40.00, -1.20, 40.10)]
    assert len(fusion.fusionar([cat], [suelto], cobertura=otra_zona)) == 2


def test_varios_edificios_de_osm_pegados_son_un_conjunto():
    casas = [_punto(f"osm-way-{i}", 39.6000 + i * 0.0002, -0.6000, "osm", estado="ruina", debil=True)
             for i in range(4)]                       # cada ~22 m
    resultado = fusion.fusionar([], casas)
    assert len(resultado) == 1 and resultado[0].n_edificios == 4


def test_puntos_cercanos_y_enlazados_por_wikidata_se_unen():
    a = _punto("osm-node-1", 39.6000, -0.6000, "osm", nombre="Estación Vieja", wikidata="Q5")
    b = _punto("wd-Q9", 39.6002, -0.6001, "wikidata", wikidata="Q9")           # a ~25 m de a
    c = _punto("wd-Q5", 39.6050, -0.6000, "wikidata", wikidata="Q5", wikipedia="es:Estación Vieja")  # a ~550 m
    d = _punto("wd-Q7", 39.7000, -0.6000, "wikidata", wikidata="Q7")           # lejos, aparte
    resultado = fusion.fusionar([], [a, b, c, d])
    assert len(resultado) == 2
    unido = next(x for x in resultado if x.id == "osm-node-1")     # manda el de OSM con nombre
    assert sorted(unido.fuentes) == ["osm", "wikidata"]
    assert unido.wikipedia == "es:Estación Vieja"


def test_fusion_sin_datos():
    assert fusion.fusionar([], []) == []


def test_la_nota_premia_lo_esperado_y_no_pasa_de_100():
    pequeno = _catastro(superficie_m2=160, n_edificios=1, vecinos_150m=60, categoria="agrario", anio=1990)
    grande = _catastro()
    assert puntuacion.puntuar(grande) > puntuacion.puntuar(pequeno)

    confirmado = _catastro(fuentes=["catastro", "osm", "wikidata"], nombre="X", wikidata="Q1", estado="ruina",
                           superficie_m2=80_000, n_edificios=30, categoria="sanitario",
                           senales={"ndvi_pendiente": 0.05})
    assert puntuacion.puntuar(confirmado) == 100
    assert confirmado.desglose["fuentes"] == 15

    ordenados = puntuacion.puntuar_todos([pequeno, confirmado, grande])
    assert [c.puntuacion for c in ordenados] == sorted((c.puntuacion for c in ordenados), reverse=True)


def test_industrial_sin_confirmar_puntua_segun_el_tamano_del_edificio():
    pajar = _catastro(mayor_edificio_m2=90)
    nave = _catastro(mayor_edificio_m2=1200)
    confirmado = _catastro(mayor_edificio_m2=90, tipo_confirmado=True)
    puntuacion.puntuar(pajar), puntuacion.puntuar(nave), puntuacion.puntuar(confirmado)
    assert pajar.desglose["categoria"] < nave.desglose["categoria"] == confirmado.desglose["categoria"] == 14


def test_aislamiento_valora_pocos_vecinos_o_mayoria_de_ruinas():
    aislado = puntuacion._aislamiento(0, 1)
    aldea_con_dos_casas_arregladas = puntuacion._aislamiento(12, 20)
    casco_urbano = puntuacion._aislamiento(400, 20)
    assert aislado > aldea_con_dos_casas_arregladas > casco_urbano == 0


def test_tamano_es_monotono():
    notas = [puntuacion._tamano(s) for s in (50, 100, 500, 5_000, 50_000, 500_000)]
    assert notas == sorted(notas) and notas[0] == 0 and notas[-1] == puntuacion.TAMANO_MAX


def test_enlaces_osint():
    c = _catastro(nombre="Fábrica de Prueba", municipio="Villa De Prueba", osm_ids=["way/7"],
                  wikidata="Q1", wikipedia="es:Fábrica de Prueba")
    e = osint.enlaces(c)
    assert e["catastro"].endswith("rc1=0000001&rc2=YJ0000A")
    assert e["osm"] == "https://www.openstreetmap.org/way/7"
    assert e["wikipedia"] == "https://es.wikipedia.org/wiki/F%C3%A1brica_de_Prueba"
    assert "viewpoint=39.550000,-0.670000" in e["street_view"]
    assert e["google_earth"] == "https://earth.google.com/web/search/39.550000,-0.670000"
    assert "busqueda" in e and all(u.startswith("https://") for u in e.values())
    # Sin nombre no hay nada que buscar en prensa.
    assert "busqueda" not in osint.enlaces(_catastro())


def test_url_de_ortofoto():
    actual = pnoa.url_imagen(39.55, -0.67, lado_m=300)
    assert actual.startswith("https://www.ign.es/wms-inspire/pnoa-ma?") and "OI.OrthoimageCoverage" in actual
    antigua = pnoa.url_imagen(39.55, -0.67, capa="AMS_1956-1957")
    assert antigua.startswith("https://www.ign.es/wms/pnoa-historico?") and "LAYERS=AMS_1956-1957" in antigua
    # La caja mide 300 m de alto: 300 / 111.320 m por grado.
    caja = [float(x) for x in actual.split("BBOX=")[1].split("&")[0].replace("%2C", ",").split(",")]
    assert abs((caja[3] - caja[1]) * 111_320 - 300) < 0.5
    assert caja[0] < -0.67 < caja[2]


def test_pendiente_del_ndvi():
    assert sentinel.pendiente([2017, 2018, 2019, 2020], [0.10, 0.12, 0.14, 0.16]) == \
        __import__("pytest").approx(0.02)
    assert sentinel.pendiente([2017, 2018], [0.1, 0.2]) is None      # muy pocos años
