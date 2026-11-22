"""OpenStreetMap y Wikidata."""

import pytest

from osintmaps.fuentes import camaras, dgt, listaroja, osm, subastas, wikidata


@pytest.mark.parametrize("tags, esperado", [
    ({"abandoned:building": "factory"}, ("industrial", "abandonado")),
    ({"abandoned:place": "village", "name": "X"}, ("despoblado", "abandonado")),
    ({"military": "barracks", "disused": "yes"}, ("militar", "en_desuso")),
    ({"amenity": "hospital", "abandoned": "yes", "building": "yes"}, ("sanitario", "abandonado")),
    ({"railway": "station", "disused": "yes"}, ("ferroviario", "en_desuso")),
    ({"railway": "abandoned", "tunnel": "yes"}, ("ferroviario", "abandonado")),
    ({"railway": "abandoned", "bridge": "yes", "highway": "cycleway"}, None),      # vía verde
    ({"man_made": "mineshaft", "disused": "yes"}, ("mineria", "en_desuso")),
    ({"tourism": "hotel", "abandoned": "yes"}, ("ocio_hosteleria", "abandonado")),
    ({"historic": "castle", "ruins": "yes"}, ("patrimonio", "ruina")),
    ({"historic": "ruins"}, ("patrimonio", "ruina")),
    ({"historic": "tower", "man_made": "tower", "building": "ruins"}, ("patrimonio", "ruina")),
    ({"historic": "watermill", "man_made": "watermill", "building": "ruins"}, ("industrial", "ruina")),
    ({"barrier": "city_wall", "historic": "ruins"}, None),   # resto de muralla: no es un sitio
    ({"tourism": "attraction", "historic": "ruins", "name": "Molino"}, ("patrimonio", "ruina")),
    ({"building": "house", "ruins": "yes"}, ("residencial", "ruina")),
    ({"building": "ruins"}, ("otro", "ruina")),
    ({"abandoned": "yes"}, ("otro", "abandonado")),
    # Lo que NO interesa:
    ({"abandoned": "yes", "highway": "track"}, None),       # un camino
    ({"disused:shop": "bakery"}, None),                     # un comercio cerrado
    ({"disused:amenity": "restaurant"}, None),
    ({"abandoned:railway": "rail"}, None),                  # vía sin túnel ni puente
    ({"power": "line", "disused": "yes"}, None),
    ({"ruins": "no", "building": "house"}, None),
    ({"building": "yes"}, None),                            # sin marca de abandono
])
def test_clasificar(tags, esperado):
    assert osm.clasificar(tags) == esperado


@pytest.mark.parametrize("tags, generico", [
    ({"abandoned:building": "industrial"}, True),            # así importa Catastro sus edificios
    ({"building": "yes", "disused:building": "house"}, True),
    ({"abandoned:building": "train_station"}, False),        # un tipo concreto sí describe el sitio
    ({"building": "church", "ruins": "yes"}, False),
    ({"building": "yes", "historic": "ruins"}, False),
])
def test_solo_edificio_distingue_el_eco_de_catastro(tags, generico):
    assert osm.solo_edificio(tags) is generico


def test_una_estacion_abandonada_sin_nombre_no_es_debil():
    respuesta = {"elements": [{"type": "way", "id": 9, "center": {"lat": 39.6, "lon": -0.6},
                               "tags": {"abandoned:building": "train_station"}}]}
    estacion = osm.parsear(respuesta)[0]
    assert (estacion.categoria, estacion.debil, estacion.tipo_confirmado) == ("ferroviario", False, True)


def test_la_consulta_de_wikidata_pide_tambien_lo_demolido():
    # Si la consulta no trae las filas de demolición, el parser no puede descartar el elemento.
    assert "demolish" in wikidata._PATRON_ESTADO and "destroy" in wikidata._PATRON_ESTADO
    respuesta = {"results": {"bindings": [
        _fila("Q444", "Convento", -0.72, 39.60, clase="monastery", estado="disused"),
        _fila("Q444", "Convento", -0.72, 39.60, clase="monastery", estado="demolished or destroyed building or structure"),
    ]}}
    assert wikidata.parsear([respuesta]) == []


def test_consulta_por_provincia_y_por_caja():
    por_provincia = osm.construir_consulta(provincia="46")
    assert 'area["ISO3166-2"~"^(ES-V)$"]' in por_provincia and "(area.zona)" in por_provincia
    # Comunidad uniprovincial: se aceptan el código de provincia y el de comunidad.
    assert "^(ES-M|ES-MD)$" in osm.construir_consulta(provincia="28")
    # Overpass ordena la caja como sur,oeste,norte,este.
    assert "(39.000000,-1.000000,40.000000,0.000000)" in osm.construir_consulta(caja=(-1, 39, 0, 40))
    with pytest.raises(ValueError):
        osm.construir_consulta(provincia="99")


def test_todas_las_provincias_tienen_codigo():
    assert sorted(osm.ISO_PROVINCIA) == [f"{n:02d}" for n in range(1, 53)]


RESPUESTA_OSM = {"elements": [
    {"type": "node", "id": 1, "lat": 39.5466, "lon": -0.6720,
     "tags": {"abandoned:man_made": "works", "name": "Fábrica de Prueba", "wikidata": "Q111"}},
    {"type": "way", "id": 2, "center": {"lat": 39.60, "lon": -0.60},
     "tags": {"building": "yes", "abandoned": "yes"}},
    {"type": "way", "id": 3, "center": {"lat": 39.61, "lon": -0.61}, "tags": {"disused:shop": "bakery"}},
    {"type": "relation", "id": 4, "tags": {"abandoned:place": "hamlet"}},   # sin centro: se ignora
]}


def test_parsear_osm():
    candidatos = osm.parsear(RESPUESTA_OSM)
    assert [c.id for c in candidatos] == ["osm-node-1", "osm-way-2"]
    fabrica = candidatos[0]
    assert (fabrica.nombre, fabrica.categoria, fabrica.wikidata) == ("Fábrica de Prueba", "industrial", "Q111")
    assert fabrica.osm_ids == ["node/1"]
    # La fábrica describe el sitio; el edificio sin nombre ni tipo es un posible eco de Catastro.
    assert (fabrica.debil, fabrica.tipo_confirmado) == (False, True)
    assert (candidatos[1].debil, candidatos[1].tipo_confirmado) == (True, False)


def _fila(qid, nombre, lon, lat, clase=None, estado=None, articulo=None):
    fila = {"item": {"value": f"http://www.wikidata.org/entity/{qid}"},
            "itemLabel": {"value": nombre}, "coord": {"value": f"Point({lon} {lat})"}}
    if clase:
        fila["claseEn"] = {"value": clase}
    if estado:
        fila["estadoEn"] = {"value": estado}
    if articulo:
        fila["articulo"] = {"value": articulo}
    return fila


def test_parsear_wikidata_agrupa_filas_del_mismo_elemento():
    respuesta = {"results": {"bindings": [
        _fila("Q111", "Fábrica de Prueba", -0.6721, 39.5466, clase="factory", estado="abandoned"),
        _fila("Q111", "Fábrica de Prueba", -0.6721, 39.5466, clase="industrial heritage site"),
        _fila("Q222", "Villar Viejo", -0.70, 39.58, clase="ghost town",
              articulo="https://es.wikipedia.org/wiki/Villar_Viejo_(despoblado)"),
        _fila("Q333", "Q333", -0.71, 39.59, clase="abandoned railway station"),
        # Lo demolido y lo que no es un sitio no entra.
        _fila("Q444", "Convento derribado", -0.72, 39.60, clase="monastery", estado="demolished or destroyed building or structure"),
        _fila("Q555", "Línea abandonada", -0.73, 39.61, clase="railway line", estado="abandoned"),
    ]}}
    por_id = {c.id: c for c in wikidata.parsear([respuesta])}
    assert set(por_id) == {"wd-Q111", "wd-Q222", "wd-Q333"}
    assert (por_id["wd-Q111"].categoria, por_id["wd-Q111"].estado) == ("industrial", "abandonado")
    assert por_id["wd-Q222"].categoria == "despoblado"
    assert por_id["wd-Q222"].wikipedia == "es:Villar Viejo (despoblado)"
    assert por_id["wd-Q333"].categoria == "ferroviario"
    assert por_id["wd-Q333"].nombre is None          # sin etiqueta, Wikidata repite el Q
    assert (por_id["wd-Q222"].lat, por_id["wd-Q222"].lon) == (39.58, -0.70)


# ---------- Cámaras de vigilancia ----------

RESPUESTA_CAMARAS = {"elements": [
    {"type": "node", "id": 501, "lat": 39.54661234567, "lon": -0.6721,
     "tags": {"man_made": "surveillance", "surveillance": "public", "surveillance:type": "camera",
              "camera:type": "dome", "surveillance:zone": "traffic", "camera:mount": "pole",
              "camera:direction": "135", "operator": "Ajuntament"}},
    {"type": "node", "id": 502, "lat": 39.5467, "lon": -0.6722,
     "tags": {"man_made": "surveillance", "surveillance": "indoor"}},                      # interior
    {"type": "way", "id": 503, "center": {"lat": 39.5470, "lon": -0.6730},
     "tags": {"man_made": "surveillance", "surveillance:type": "ALPR", "direction": "NE"}},
    {"type": "node", "id": 504, "lat": 39.5471, "lon": -0.6731,
     "tags": {"man_made": "surveillance", "surveillance:type": "guard"}},                  # un vigilante
    {"type": "relation", "id": 505, "tags": {"man_made": "surveillance"}},                 # sin posición
]}


def test_camaras_parsear():
    primera, segunda = camaras.parsear(RESPUESTA_CAMARAS)
    assert primera == {"id": "node/501", "lat": 39.546612, "lon": -0.6721, "tipo": "camera", "camara": "dome",
                       "vigila": "public", "zona": "traffic", "montaje": "pole", "operador": "Ajuntament",
                       "direccion": "135"}
    # Una vía se sitúa en su centro; la orientación puede venir en «direction».
    assert segunda == {"id": "way/503", "lat": 39.547, "lon": -0.673, "tipo": "ALPR", "direccion": "NE"}

    capa = camaras.geojson([primera, segunda])
    assert capa["features"][0]["geometry"] == {"type": "Point", "coordinates": [-0.6721, 39.546612]}
    assert "lat" not in capa["features"][0]["properties"] and capa["features"][1]["properties"]["tipo"] == "ALPR"


def test_camaras_consulta():
    por_provincia = camaras.construir_consulta(provincia="46")
    assert 'ES-V' in por_provincia and 'nwr["man_made"="surveillance"](area.' in por_provincia
    por_caja = camaras.construir_consulta(caja=(-0.7, 39.5, -0.6, 39.6))
    assert "area[" not in por_caja and "(39.500000,-0.700000,39.600000,-0.600000)" in por_caja
    assert "out tags center" in por_caja


def test_camaras_usa_la_cache_y_prueba_otro_servidor(monkeypatch, tmp_path):
    pedidos = []

    class Respuesta:
        def json(self):
            return RESPUESTA_CAMARAS

    def pedir(sesion, metodo, url, **kw):
        pedidos.append(url)
        if len(pedidos) == 1:
            raise ConnectionError("el primero no responde")
        return Respuesta()

    monkeypatch.setattr(camaras, "pedir", pedir)
    assert len(camaras.buscar(None, tmp_path, caja=(-0.7, 39.5, -0.6, 39.6))) == 2
    assert pedidos == list(osm.SERVIDORES[:2])
    assert len(camaras.buscar(None, tmp_path, caja=(-0.7, 39.5, -0.6, 39.6))) == 2     # de la caché
    assert len(pedidos) == 2


# ---------- Capas extra: Lista Roja, DGT y subastas ----------

PAGINA_LISTA_ROJA = """
<script> var marker = []; function initMap() {
var contentString_274 = "<div class=\\"info-window\\"> <h5>Torre de Prueba</h5> <div class=\\"info-content\\">Villa (Valencia) Se cae a trozos...<br><br><a href=\\"https:\\/\\/listaroja.hispanianostra.org\\/ficha\\/torre-de-prueba\\/\\" target=\\"_blank\\">Ver en detalle</a></div> </div>";
marker[274] = new google.maps.Marker({ position: {lat: 39.5466, lng: -0.6721}, map: map, zIndex: 0, icon: 'https://listaroja.hispanianostra.org/wp-content/uploads/hispania_icon1.png' });
infowindow[274] = new google.maps.InfoWindow({ content: contentString_274 });
var contentString_9 = "<div class=\\"info-window\\"> <h5>Mal situada</h5> <div class=\\"info-content\\">Fuera</div> </div>";
marker[9] = new google.maps.Marker({ position: {lat: 0.0, lng: 0.0}, map: map, icon: 'x/hispania_icon2.png' });
} </script>
"""

XML_DGT = b"""<?xml version="1.0" encoding="UTF-8"?>
<d2:payload xmlns:d2="http://levelC/schema/3/d2Payload" xmlns:ns2="http://levelC/schema/3/device" xmlns:loc="http://levelC/schema/3/locationReferencing" xmlns:lse="x" xmlns:fse="y">
 <ns2:device id="176130"><ns2:typeOfDevice>camera</ns2:typeOfDevice>
  <ns2:pointLocation><loc:roadName>A-7</loc:roadName><loc:roadDestination>ALICANTE</loc:roadDestination>
   <loc:latitude>39.4321</loc:latitude><loc:longitude>-0.4567</loc:longitude><lse:kilometerPoint>325.3</lse:kilometerPoint><lse:province>VALENCIA</lse:province></ns2:pointLocation>
  <fse:deviceUrl>https://etraffic.dgt.es/camarasEtraffic/176130.jpg</fse:deviceUrl></ns2:device>
 <ns2:device id="2"><ns2:typeOfDevice>camera</ns2:typeOfDevice><ns2:pointLocation><loc:roadName>N-340</loc:roadName></ns2:pointLocation></ns2:device>
</d2:payload>"""

LISTADO_BOE = '<a href="./detalleSubasta.php?idSub=SUB-JA-2026-1&amp;idBus=x">a</a> <a href="./detalleSubasta.php?idSub=SUB-JA-2026-1&amp;idBus=x">b</a> <a href="./detalleSubasta.php?idSub=SUB-AT-2026-26R2&amp;idBus=x">c</a>'
GENERAL_BOE = "<table><tr><th>Fecha de conclusi&#xF3;n</th><td>10-12-2026 18:00:00 CET (ISO: 2026-12-10T18:00:00+01:00)</td></tr><tr><th>Valor subasta</th><td>50.000,00 &#x20AC;</td></tr></table>"
BIENES_BOE = """<div id="idBloqueLote1"><div><h3>Datos del bien subastado</h3><div>
<h4>Bien 1 - Inmueble (Vivienda)</h4><table><tr><th>Descripci&#xF3;n</th><td>PISO</td></tr><tr><th>Referencia catastral</th><td>5823501YJ2752D0001AB</td></tr>
<tr><th>Direcci&#xF3;n</th><td>Plaza Mayor, 6</td></tr><tr><th>Localidad</th><td>CULLERA</td></tr><tr><th>Situaci&#xF3;n posesoria</th><td>No consta</td></tr></table></div>
<div><h4>Bien 2 - Inmueble (Garaje)</h4><table><tr><th>Direcci&#xF3;n</th><td>Calle Sin Sitio, 1</td></tr><tr><th>Localidad</th><td>CULLERA</td></tr></table></div></div></div>"""


def test_listaroja_parsear():
    fichas = listaroja.parsear(PAGINA_LISTA_ROJA)
    assert fichas == [{"id": "listaroja-274", "nombre": "Torre de Prueba", "lat": 39.5466, "lon": -0.6721,
                       "resumen": "Villa (Valencia) Se cae a trozos...",
                       "url": "https://listaroja.hispanianostra.org/ficha/torre-de-prueba/", "lista": "verde"}]


def test_dgt_parsear():
    assert dgt.parsear(XML_DGT) == [{"id": "dgt-176130", "lat": 39.4321, "lon": -0.4567, "nombre": "A-7 km 325.3", "carretera": "A-7",
                                     "pk": "325.3", "provincia": "Valencia", "destino": "Alicante",
                                     "imagen": "https://etraffic.dgt.es/camarasEtraffic/176130.jpg"}]


def red_subastas(monkeypatch):
    """Simula el portal del BOE, Catastro y CartoCiudad. Devuelve las direcciones pedidas."""
    pedidos = []

    class Respuesta:
        def __init__(self, texto="", datos=None):
            self.text, self._datos = texto, datos

        def json(self):
            return self._datos

    def pedir(sesion, metodo, url, **kw):
        q = kw.get("params") or {}
        pedidos.append((url.rsplit("/", 1)[-1], q.get("ver") or q.get("dato[2]") or q.get("RefCat") or q.get("q")))
        if url.endswith("subastas_ava.php"):
            return Respuesta(LISTADO_BOE if q["dato[2]"] == "EJ" else "")
        if url.endswith("detalleSubasta.php"):
            return Respuesta(GENERAL_BOE if q["ver"] == "1" else BIENES_BOE)
        if url.endswith("Consulta_CPMRC"):
            return Respuesta(datos={"Consulta_CPMRCResult": {"coordenadas": {"coord": [{"geo": {"xcen": "-0.2501", "ycen": "39.1601"}}]}}})
        return Respuesta(datos={"lat": 39.0, "lng": -0.3, "type": "Municipio"})      # CartoCiudad solo acierta el municipio

    monkeypatch.setattr(subastas, "pedir", pedir)
    monkeypatch.setattr(subastas.time, "sleep", lambda s: None)
    return pedidos


def test_subastas(monkeypatch, tmp_path):
    pedidos = red_subastas(monkeypatch)
    assert subastas.ids_del_listado(LISTADO_BOE) == ["SUB-JA-2026-1", "SUB-AT-2026-26R2"]
    assert [b["titulo"] for b in subastas.bienes_de_la_pagina(BIENES_BOE)] == ["Bien 1 - Inmueble (Vivienda)", "Bien 2 - Inmueble (Garaje)"]

    puntos = subastas.buscar(None, tmp_path, "46")
    # Dos subastas con los mismos bienes: de cada una se sitúa el que trae referencia catastral;
    # el garaje, del que CartoCiudad solo encuentra el municipio, se deja fuera.
    assert [p["id"] for p in puntos] == ["subasta-SUB-JA-2026-1-1", "subasta-SUB-AT-2026-26R2-1"]
    assert puntos[0] == {"id": "subasta-SUB-JA-2026-1-1", "lat": 39.1601, "lon": -0.2501, "nombre": "Inmueble (Vivienda) en subasta",
                         "subasta": "SUB-JA-2026-1", "url": "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-JA-2026-1",
                         "situado_por": "parcela", "direccion": "Plaza Mayor, 6", "localidad": "CULLERA",
                         "refcat": "5823501YJ2752D0001AB", "descripcion": "PISO", "situacion_posesoria": "No consta",
                         "fin": "10-12-2026 18:00:00 CET", "valor_subasta": "50.000,00 €"}
    # La segunda vez sale de la caché: solo se vuelve a pedir el listado.
    antes = len(pedidos)
    assert len(subastas.buscar(None, tmp_path, "46")) == 2
    assert len(pedidos) == antes + 2


def test_subastas_no_guarda_una_lectura_a_medias(monkeypatch, tmp_path):
    """Si Catastro no contesta, la subasta no se da por leída: se reintenta entera la próxima vez."""
    red_subastas(monkeypatch)
    simulada, catastro_caido = subastas.pedir, {"si": True}

    def pedir(sesion, metodo, url, **kw):
        if url.endswith("Consulta_CPMRC") and catastro_caido["si"]:
            raise ConnectionError("Catastro no responde")
        return simulada(sesion, metodo, url, **kw)

    monkeypatch.setattr(subastas, "pedir", pedir)
    assert subastas.buscar(None, tmp_path, "46") == []
    assert list(tmp_path.glob("*.json")) == []            # nada en la caché
    catastro_caido["si"] = False
    assert len(subastas.buscar(None, tmp_path, "46")) == 2
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_subastas_distingue_dato_malo_de_servicio_caido(monkeypatch):
    import requests

    class Rechazo:
        status_code = 400

    def rechaza(*a, **kw):
        raise requests.HTTPError("HTTP 400", response=Rechazo())

    monkeypatch.setattr(subastas, "pedir", rechaza)
    # Catastro rechaza la referencia y CartoCiudad la dirección: el bien no se puede situar, y eso sí es definitivo.
    assert subastas._coordenadas(None, {"Referencia catastral": "5823501YJ2752D0001AB", "Dirección": "x", "Localidad": "y"}) is None

    class Saturado:
        status_code = 503

    def saturado(*a, **kw):
        raise requests.HTTPError("HTTP 503", response=Saturado())

    monkeypatch.setattr(subastas, "pedir", saturado)
    with pytest.raises(subastas.ServicioCaido):
        subastas._coordenadas(None, {"Referencia catastral": "5823501YJ2752D0001AB"})
