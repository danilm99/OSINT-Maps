"""La historia de un sitio: el bloque de la ficha con lo que ya está en los datos, la búsqueda en Wikidata, Wikipedia,
Commons, topónimos (IGN, ICV, OpenStreetMap) y Catastro, las noticias guardadas y las del programa, y qué pasa cuando
una fuente no contesta. Todos los servicios van simulados."""
exec(open("maps9.py", encoding="utf-8").read())
from urllib.parse import urlparse, parse_qs
sitios = json.load(open(datos / "candidatos.geojson"))["features"]
def sitio_de(prueba): return next(f for f in sitios if prueba(f["properties"]))
CON_FICHA = sitios[0]["properties"]["id"]                                                             # sin nombre, con ficha de Wikidata (Q1), Catastro 1890
SIN_NADA = sitio_de(lambda p: not p.get("nombre") and not p.get("wikidata"))["properties"]["id"]      # ni nombre ni ficha
CON_NOMBRE = sitio_de(lambda p: p.get("nombre") == "Estación de Villar" and not p.get("wikidata"))["properties"]["id"]
NOTICIA = {"titulo": "El castillo de Prueba, en ruinas", "medio": "Diario de Prueba", "fecha": "2026-05-01", "url": "https://news.google.com/rss/articles/guardada", "nombra": True}
FLOJA = {"titulo": "Fiestas de Llíria", "medio": "Otro Diario", "fecha": "2025-08-15", "url": "https://news.google.com/rss/articles/floja", "nombra": False}
MALA = {"titulo": "Enlace sin cifrar", "medio": "Blog", "fecha": "2025-01-01", "url": "http://example.com/x", "nombra": True}
PRENSA = {"generado": "2026-11-20T10:00:00", "sitios": {CON_FICHA: {"nombre": "x", "municipio": "Llíria", "consulta": '"Castillo de Prueba" "Llíria"', "consultado": "2026-11-20", "noticias": [NOTICIA, FLOJA, MALA]},
                                                       SIN_NADA: {"consulta": '"Otro" "Llíria"', "consultado": "2026-11-20", "noticias": []}}}
(datos / "historia.json").write_text(json.dumps(PRENSA), encoding="utf-8")

ESCENA9 = {"wikidata": "bien", "ign": "bien"}
vistos_h = {}
def lit(v, idioma=None): return dict({"type": "literal", "value": str(v)}, **({"xml:lang": idioma} if idioma else {}))
def uri(v): return {"type": "uri", "value": v}
def fila(q, nombre, km, tipo=None, cat=None, es=None, ca=None, ficha=None, desc=None):
    d = {"item": uri(f"http://www.wikidata.org/entity/{q}"), "itemLabel": lit(nombre, "es"), "dist": lit(km)}
    for k, v in (("tipoLabel", tipo), ("catLabel", cat), ("itemDescription", desc)):
        if v: d[k] = lit(v, "es")
    for k, v in (("es", es), ("ca", ca), ("ficha", ficha)):
        if v: d[k] = uri(v)
    return d
CERCA = {"results": {"bindings": [
    fila("Q222", "Retablo cerámico de San Roque", 0.01, "retablo cerámico", "Bien de Relevancia Local", ficha="https://eduwp.edu.gva.es/patrimonio-cultural/ficha-inmueble.php?id=9"),
    fila("Q111", "Castillo de Prueba", 0.03, "castillo", "bien de interés cultural", es="https://es.wikipedia.org/wiki/Castillo_de_Prueba", desc="castillo de Llíria"),
    fila("Q111", "Castillo de Prueba", 0.03, "fortificación", "bien de interés cultural", es="https://es.wikipedia.org/wiki/Castillo_de_Prueba"),
    fila("Q444", "Estació de Villar", 0.12, "estación de ferrocarril", ca="https://ca.wikipedia.org/wiki/Estaci%C3%B3_de_Villar"),
    fila("Q888", "Fábrica de Harinas La Unión", 0.14, "fábrica"),
    fila("Q555", "Q555", 0.15, "edificio"),                                                    # sin nombre en ningún idioma: no se enseña
    fila("Q666", "Llíria", 0.2, "municipio de España", es="https://es.wikipedia.org/wiki/Liria"),      # el municipio no es «patrimonio cerca»
    fila("Q777", "Molino <b>raro</b>", 0.3, "molino", "Bien de Relevancia Local", ficha="http://sin-cifrar.example/ficha")]}}
def q_(i): return {"entity-type": "item", "id": i}
def t_(t, p): return {"time": t, "precision": p}
def snak(tipo, valor): return {"snaktype": "value", "datavalue": {"type": tipo, "value": valor}}
def claim(tipo, valor, rank="normal", cal=None): return dict({"mainsnak": snak(tipo, valor), "rank": rank}, **({"qualifiers": cal} if cal else {}))
ROTULOS = {"Q444": "Estación de Villar del Arzobispo", "Q888": "Harinera La Unión"}
def entidad(q):
    return {"id": q, "labels": {"es": {"value": ROTULOS.get(q, "Castillo de Prueba")}, "ca": {"value": "Castell de Prova"}}, "descriptions": {"es": {"value": "castillo de Llíria"}},
            "claims": {"P31": [claim("wikibase-entityid", q_("Q23413"))], "P1435": [claim("wikibase-entityid", q_("Q23712"), cal={"P580": [snak("time", t_("+1985-06-25T00:00:00Z", 9))]})],
                       "P571": [claim("time", t_("+1300-00-00T00:00:00Z", 7))], "P3999": [claim("time", t_("+2005-03-31T00:00:00Z", 11))], "P576": [claim("time", t_("+1999-00-00T00:00:00Z", 9), rank="deprecated")],
                       "P5817": [claim("wikibase-entityid", q_("Q11639308"))], "P5816": [claim("wikibase-entityid", q_("Q56557159"))], "P149": [claim("wikibase-entityid", q_("Q176483"))],
                       "P973": [claim("string", "https://eduwp.edu.gva.es/patrimonio-cultural/ficha-inmueble.php?id=1465"), claim("string", "http://sin-cifrar.example/")],
                       "P2473": [claim("string", "46.11.147-001")], "P4868": [claim("string", "castillo-de-prueba")], "P127": [claim("wikibase-entityid", q_("Q999"))],
                       "P1101": [claim("quantity", {"amount": "+3", "unit": "1"})],
                       "P793": [claim("wikibase-entityid", q_("Q168983"), cal={"P585": [snak("time", t_("+1936-08-00T00:00:00Z", 10))]})]},
            "sitelinks": {"eswiki": {"title": ROTULOS.get(q, "Castillo de Prueba") + (" (edificio)" if q in ROTULOS else "")}, "cawiki": {"title": "Castell de Prova"}, "commonswiki": {"title": "Category:Castillo de Prueba"}}}
NOMBRES_WD = {"Q23413": "castillo", "Q23712": "bien de interés cultural", "Q11639308": "abandonado", "Q56557159": "ruinas", "Q176483": "gótico", "Q168983": "incendio", "Q999": "Fulano de Tal"}
ARTICULO = ("El castillo de Prueba es una fortaleza de origen andalusí situada en un cerro sobre Llíria. " + "Fue reformado tras la conquista y perdió su función militar en el siglo XVIII. " * 9
            + "Esta frase ya no cabe en el recorte.")
def gml(lat, lon):
    return f'''<?xml version="1.0" encoding="UTF-8"?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:gn="http://inspire.ec.europa.eu/schemas/gn/4.0" xmlns:gmd="http://www.isotc211.org/2005/gmd">
<wfs:member><gn:NamedPlace><gn:geometry><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>{lat-0.002} {lon-0.002} {lat-0.002} {lon+0.002} {lat+0.002} {lon+0.002} {lat+0.002} {lon-0.002} {lat-0.002} {lon-0.002}</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></gn:geometry>
<gn:localType><gmd:LocalisedCharacterString>Partida</gmd:LocalisedCharacterString></gn:localType><gn:name><gn:GeographicalName><gn:spelling><gn:SpellingOfName><gn:text>el Brucar</gn:text></gn:SpellingOfName></gn:spelling></gn:GeographicalName></gn:name></gn:NamedPlace></wfs:member>
<wfs:member><gn:NamedPlace><gn:geometry><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>{lat-0.02} {lon-0.02} {lat-0.02} {lon+0.02} {lat+0.02} {lon+0.02} {lat+0.02} {lon-0.02} {lat-0.02} {lon-0.02}</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></gn:geometry>
<gn:localType><gmd:LocalisedCharacterString>Espai natural protegit</gmd:LocalisedCharacterString></gn:localType><gn:name><gn:GeographicalName><gn:spelling><gn:SpellingOfName><gn:text>Parc Natural de Prova</gn:text></gn:SpellingOfName></gn:spelling></gn:GeographicalName></gn:name></gn:NamedPlace></wfs:member>
<wfs:member><gn:NamedPlace><gn:geometry><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>{lat-0.05} {lon-0.05} {lat-0.05} {lon+0.05} {lat+0.05} {lon+0.05} {lat+0.05} {lon-0.05} {lat-0.05} {lon-0.05}</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></gn:geometry>
<gn:localType><gmd:LocalisedCharacterString>Capital de municipi</gmd:LocalisedCharacterString></gn:localType><gn:name><gn:GeographicalName><gn:spelling><gn:SpellingOfName><gn:text>Llíria</gn:text></gn:SpellingOfName></gn:spelling></gn:GeographicalName></gn:name></gn:NamedPlace></wfs:member>
<wfs:member><gn:NamedPlace><gn:geometry><gml:MultiCurve><gml:curveMember><gml:LineString><gml:posList>{lat+0.0005} {lon-0.003} {lat+0.0005} {lon+0.003}</gml:posList></gml:LineString></gml:curveMember></gml:MultiCurve></gn:geometry>
<gn:localType><gmd:LocalisedCharacterString>Camí, senda, altres carreteres</gmd:LocalisedCharacterString></gn:localType><gn:name><gn:GeographicalName><gn:spelling><gn:SpellingOfName><gn:text>Camí del Molí</gn:text></gn:SpellingOfName></gn:spelling></gn:GeographicalName></gn:name></gn:NamedPlace></wfs:member>
<wfs:member><gn:NamedPlace><gn:geometry><gml:Point><gml:pos>{lat+0.0009} {lon}</gml:pos></gml:Point></gn:geometry>
<gn:localType><gmd:LocalisedCharacterString>Corral</gmd:LocalisedCharacterString></gn:localType><gn:name><gn:GeographicalName><gn:spelling><gn:SpellingOfName><gn:text>Corral de Dalt</gn:text></gn:SpellingOfName></gn:spelling></gn:GeographicalName></gn:name></gn:NamedPlace></wfs:member>
<wfs:member><gn:NamedPlace><gn:geometry><gml:Point><gml:pos>{lat+0.00024} {lon}</gml:pos></gml:Point></gn:geometry>
<gn:localType><gmd:LocalisedCharacterString>Edifici</gmd:LocalisedCharacterString></gn:localType><gn:name><gn:GeographicalName><gn:spelling><gn:SpellingOfName><gn:text>Casillas de Marín</gn:text></gn:SpellingOfName></gn:spelling></gn:GeographicalName></gn:name></gn:NamedPlace></wfs:member>
</wfs:FeatureCollection>'''
ruta_maps = ruta
def ruta(route):
    u = route.request.url
    q = {k: v[0] for k, v in parse_qs(urlparse(u).query).items()}
    def js(d, estado=200): return route.fulfill(status=estado, content_type="application/json", headers=CORS, body=json.dumps(d))
    def cuenta(k): vistos_h[k] = vistos_h.get(k, 0) + 1; vistos_h[k + "-ultima"] = u
    if "/vivo/noticias" in u:
        cuenta("noticias")
        if ESCENA9.get("noticias") == "caido": return route.fulfill(status=502, body="")
        return js({"consulta": f'"{q["nombre"]}" "{q.get("municipio", "")}"', "noticias": [dict(NOTICIA, titulo=f"Hoy: {q['nombre']}", url="https://news.google.com/rss/articles/al-momento"), MALA]})
    if "query.wikidata.org/sparql" in u:
        cuenta("sparql")
        if ESCENA9["wikidata"] == "caido": return route.abort()
        return js(CERCA if ESCENA9["wikidata"] == "bien" else {"results": {"bindings": []}})
    if "wikidata.org/w/api.php" in u:
        cuenta("entidad" if "claims" in q.get("props", "") else "nombres")
        if "claims" in q.get("props", ""): return js({"entities": {q["ids"]: entidad(q["ids"])}})
        return js({"entities": {i: {"id": i, "labels": {"es": {"value": NOMBRES_WD[i]}}} for i in q["ids"].split("|") if i in NOMBRES_WD}})
    if "wikipedia.org/w/api.php" in u and "pageprops" in q.get("prop", ""):
        cuenta("articulo")
        return js({"query": {"pages": {"7": {"pageid": 7, "title": q["titles"], "extract": ARTICULO, "fullurl": "https://es.wikipedia.org/wiki/Castillo_de_Prueba", "pageprops": {"wikibase_item": "Q1"}}}}})
    if "commons.wikimedia.org" in u and "ggscoord" in q:
        cuenta("commons")
        def foto(k, fecha): return {"pageid": k, "title": f"File:Foto {k}.jpg", "imageinfo": [{"mime": "image/jpeg", "url": f"https://upload.wikimedia.org/{k}.jpg", "thumburl": f"https://upload.wikimedia.org/thumb/{k}.jpg/500px-{k}.jpg",
                                                                                               "descriptionurl": f"https://commons.wikimedia.org/wiki/File:Foto_{k}.jpg", "extmetadata": dict({"Artist": {"value": "<a>Ana</a>"}}, **({"DateTimeOriginal": {"value": fecha}} if fecha else {}))}]}
        return js({"query": {"pages": {"1": foto(1, "8 May 2022 (according to Exif data)"), "2": foto(2, None), "3": foto(3, "1979-06-01 10:00:00"), "4": {"pageid": 4, "title": "File:Plano.pdf", "imageinfo": [{"mime": "application/pdf", "url": "https://upload.wikimedia.org/p.pdf", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Plano.pdf"}]}}}})
    if "api-features.ign.es" in u:
        cuenta("ign")
        if ESCENA9["ign"] == "caido": return route.abort()
        o, s_, e, n = map(float, q["bbox"].split(","))
        lat, lon = (s_ + n) / 2, (o + e) / 2
        def lugar(nombre, tipo, dla, dlo): return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon + dlo, lat + dla]}, "properties": {"etiqueta": nombre, "tipo": tipo}}
        return js({"type": "FeatureCollection", "features": [lugar("Casillas de Marín", "Edificación", 0.00024, 0), lugar("Los Centenares", "Paraje", 0.0027, 0), lugar("Fuente del Palomo", "Hidrónimo puntual", 0, 0.002)]})
    if "catalogo.icv.gva.es" in u:
        cuenta("icv")
        s_, o, n, e = map(float, q["bbox"].split(",")[:4])
        return route.fulfill(status=200, content_type="text/xml", headers=CORS, body=gml((s_ + n) / 2, (o + e) / 2))
    if "photon.komoot.io/reverse" in u and q.get("limit") == "8":
        cuenta("photon")
        lat, lon = float(q["lat"]), float(q["lon"])
        return js({"features": [
            {"geometry": geo(lon + 0.001, lat), "properties": {"osm_type": "W", "osm_id": 1, "osm_key": "highway", "osm_value": "track", "name": "Camino de los Baños", "city": "Llíria / Liria", "county": "el Camp de Túria"}},
            {"geometry": geo(lon, lat + 0.0027), "properties": {"osm_type": "N", "osm_id": 2, "osm_key": "place", "osm_value": "locality", "name": "Los Centenares", "city": "Llíria / Liria", "county": "el Camp de Túria"}},
            {"geometry": geo(lon + 0.0001, lat), "properties": {"osm_type": "N", "osm_id": 3, "osm_key": "amenity", "osm_value": "bar", "name": "Bar Paco", "city": "Llíria / Liria"}},
            {"geometry": geo(lon, lat + 0.0004), "properties": {"osm_type": "N", "osm_id": 4, "osm_key": "amenity", "osm_value": "place_of_worship", "name": "Ermita de Prueba", "city": "Llíria / Liria"}}]})
    if "Consulta_DNPRC" in u:
        cuenta("catastro")
        return js({"consulta_dnprcResult": {"bico": {"bi": {"dt": {"nm": "LLIRIA", "locs": {"lors": {"lorus": {"npa": "PLA COLOM"}}}}, "ldt": "Polígono 39 Parcela 133 PLA COLOM. LLIRIA (VALENCIA)", "debi": {"luso": "Industrial", "sfc": "850", "ant": "1920"}},
                                                     "lcons": [{"lcd": "ALMACEN", "dfcons": {"stl": "40"}, "dvcons": {"dtip": "INDUSTRIA NO FABRIL"}}, {"lcd": "ALMACEN", "dfcons": {"stl": "15360"}, "dvcons": {"dtip": "INDUSTRIA NO FABRIL"}}, {"lcd": "VIVIENDA", "dfcons": {"stl": "90"}, "dvcons": {"dtip": "VIVIENDA UNIFAMILIAR"}}]}}})
    return ruta_maps(route)

errores = []
def comprobar(nombre, que, cierto):
    print(nombre, " bien " if cierto else " MAL  ", que)
    if not cierto: errores.append(f"{nombre}: {que}")
PEDIDAS = ("sparql", "entidad", "nombres", "articulo", "commons", "ign", "icv", "photon", "catastro", "noticias")
def pedidas(): return {k: vistos_h.get(k, 0) for k in PEDIDAS}
with sync_playwright() as p:
    b = p.chromium.launch()
    for nombre, vp in (("escritorio", {"width": 1360, "height": 860}), ("movil", {"width": 390, "height": 800})):
        ctx = b.new_context(viewport=vp, has_touch=(nombre == "movil")); pg = ctx.new_page(); pg.route("**/*", ruta)
        pg.on("console", lambda m: errores.append(f"{nombre} {m.type}: {m.text[:300]}") if m.type in ("error", "warning") and "ERR_FAILED" not in m.text and "502" not in m.text else None)
        pg.on("pageerror", lambda e: errores.append(f"{nombre} EXC: {e}"))
        vistos_h.clear(); ESCENA9.update(wikidata="bien", ign="bien"); ESCENA9.pop("noticias", None)
        pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(3200)
        def abrir(i): pg.evaluate(f"abrirFicha(candidatos.find((c) => c.id === '{i}'), true); 0"); pg.wait_for_timeout(500)
        def texto(): return pg.evaluate("document.querySelector('#ficha .historia').textContent")
        def buscar(): pg.click("#ficha .historia .boton-historia"); pg.wait_for_selector("#ficha .historia .pie-historia", timeout=15000); pg.wait_for_timeout(200)

        # --- 1. Antes de buscar: lo que ya está en los datos, sin tocar la red
        abrir(CON_FICHA)
        t = texto()
        comprobar(nombre, "el bloque está en la ficha, detrás de lo visto desde el aire", pg.evaluate("(() => { const h = document.querySelector('#ficha .historia'); return !!h && h.previousElementSibling.classList.contains('vision') && h.querySelector('h3').textContent === 'Historia'; })()"))
        comprobar(nombre, f"resumen con lo que consta: {t[8:150]!r}", "Catastro fecha la construcción en 1890." in t and "Hoy: consta como abandonado (Catastro, OpenStreetMap, Wikidata)." in t)
        comprobar(nombre, "la Lista Roja de al lado entra en el resumen", "Hispania Nostra tiene a " in t and "«Torre de Prueba» en su Lista Roja (en riesgo de perderse)" in t)
        comprobar(nombre, "la fecha de Catastro, con su aviso", pg.evaluate("[...document.querySelectorAll('#ficha .historia dl.cronologia dt')].map((d) => d.textContent + '|' + d.nextElementSibling.textContent).join('#')") == "1890|ConstrucciónCatastro: en edificios viejos suele ser un año aproximado")
        comprobar(nombre, "qué fue, por las etiquetas de OpenStreetMap", "Qué fue" in t and "industrial" in t)
        comprobar(nombre, "las noticias guardadas: la que lo nombra, la floja y fuera la del enlace sin cifrar",
                  pg.evaluate("[...document.querySelectorAll('#ficha .historia .noticias li')].map((li) => [li.className, li.querySelector('a').textContent, li.querySelector('a').href, li.querySelector('small').textContent].join('|'))")
                  == ["|El castillo de Prueba, en ruinas|https://news.google.com/rss/articles/guardada|Diario de Prueba, 1/5/2026", "floja|Fiestas de Llíria|https://news.google.com/rss/articles/floja|Otro Diario, 15/8/2025"])
        comprobar(nombre, "dice con qué se buscó y cuándo", 'Google Noticias, buscando "Castillo de Prueba" "Llíria" el 20/11/2026.' in t and "pueden no ir de este sitio" in t)
        comprobar(nombre, "todavía no se ha preguntado nada fuera", sum(pedidas().values()) == 0 and pg.locator("#ficha .historia .boton-historia").inner_text() == "Buscar su historia")
        comprobar(nombre, "los enlaces se abren en otra pestaña y sin dejar rastro", pg.evaluate("[...document.querySelectorAll('#ficha .historia a')].every((a) => a.target === '_blank' && a.rel === 'noopener noreferrer' && a.href.startsWith('https://'))"))

        # --- 2. La búsqueda de un sitio con ficha de Wikidata
        buscar()
        t = texto()
        comprobar(nombre, f"una petición a cada fuente: {pedidas()}", pedidas() == {"sparql": 1, "entidad": 1, "nombres": 1, "articulo": 1, "commons": 1, "ign": 1, "icv": 1, "photon": 1, "catastro": 1, "noticias": 1})
        comprobar(nombre, "pide la ficha que traía el sitio y los nombres de sus valores", "ids=Q1&" in vistos_h["entidad-ultima"] and "Q23712" in vistos_h["nombres-ultima"] and "Q999" not in vistos_h["nombres-ultima"])
        comprobar(nombre, "a Wikidata se le pregunta por lo que hay a 400 m del punto", "wikibase%3Aaround" in vistos_h["sparql-ultima"] and "radius%20%220.4%22" in vistos_h["sparql-ultima"] and f"Point({sitios[0]['geometry']['coordinates'][0]:.6f}%20" in vistos_h["sparql-ultima"])
        comprobar(nombre, "el nombre, de Wikidata, y el municipio", pg.evaluate("document.querySelector('#ficha .historia .resumen b').textContent") == "Castillo de Prueba" and "Castillo de Prueba, en Llíria." in t)
        comprobar(nombre, "origen, protección y cierre, cada uno con su fuente", "Se construyó en el siglo XIII (Wikidata)." in t and "Está protegido como bien de interés cultural." in t and "Cerró el 31 de marzo de 2005 (Wikidata)." in t)
        fechas = pg.evaluate("[...document.querySelectorAll('#ficha .historia dl.cronologia dt')].map((d) => d.textContent + '|' + d.nextElementSibling.firstChild.textContent)")
        comprobar(nombre, f"la cronología, en orden y sin lo retirado: {fechas}", fechas == ["siglo XIII|Construcción o fundación", "1890|Construcción", "agosto de 1936|Incendio", "1985|Protección: bien de interés cultural", "31 de marzo de 2005|Cierre"])
        datos_h = dict(pg.evaluate("[...document.querySelectorAll('#ficha .historia dl:not(.cronologia) dt')].map((d) => [d.textContent, d.nextElementSibling.textContent])"))
        comprobar(nombre, f"lo que consta: {list(datos_h)}", datos_h.get("Qué es") == "castillo" and datos_h.get("Estado de uso") == "abandonado" and datos_h.get("Conservación") == "ruinas" and datos_h.get("Estilo") == "gótico"
                  and datos_h.get("Plantas") == "3" and datos_h.get("Código en el inventario valenciano") == "46.11.147-001" and datos_h.get("Dirección en Catastro") == "Polígono 39 Parcela 133 PLA COLOM. LLIRIA (VALENCIA)"
                  and datos_h.get("Consta en Catastro") == "industria no fabril (15.400 m²), vivienda unifamiliar (90 m²)" and datos_h.get("Dentro de") == "Parc Natural de Prova")
        comprobar(nombre, "nada sobre propietarios, aunque Wikidata lo traiga", "Fulano" not in t and "Propiedad" not in t)
        cita = pg.evaluate("document.querySelector('#ficha .historia .cita').textContent")
        comprobar(nombre, f"el arranque del artículo, recortado en una frase entera ({len(cita)} letras)", cita.startswith("El castillo de Prueba es una fortaleza") and "ya no cabe" not in cita and "siglo XVIII.Wikipedia en castellano. Seguir leyendo" in cita and len(cita) < 540)
        enlaces = dict(pg.evaluate("[...document.querySelectorAll('#ficha .historia .enlaces a')].map((a) => [a.textContent, a.href])"))
        comprobar(nombre, "fichas y artículos", enlaces.get("Ficha de patrimonio de la Generalitat") == "https://eduwp.edu.gva.es/patrimonio-cultural/ficha-inmueble.php?id=1465" and enlaces.get("Ficha en la Lista Roja") == "https://listaroja.hispanianostra.org/ficha/castillo-de-prueba/"
                  and enlaces.get("Más fotos en Commons") == "https://commons.wikimedia.org/wiki/Category%3ACastillo_de_Prueba" and enlaces.get("Wikidata") == "https://www.wikidata.org/wiki/Q1"
                  and enlaces.get("Wikipedia en valenciano") == "https://ca.wikipedia.org/wiki/Castell_de_Prova" and not any("sin-cifrar" in v for v in enlaces.values()))
        comprobar(nombre, "las noticias recién buscadas sustituyen a las guardadas", pg.evaluate("[...document.querySelectorAll('#ficha .historia .noticias a')].map((a) => a.textContent)") == ["Hoy: Castillo de Prueba"]
                  and "nombre=Castillo+de+Prueba&municipio=Ll%C3%ADria" in vistos_h["noticias-ultima"])
        fotos = pg.evaluate("[...document.querySelectorAll('#ficha .historia .fotos.fechadas a')].map((a) => a.querySelector('span').textContent + '|' + a.href)")
        comprobar(nombre, f"fotos por año, las sin fecha al final y fuera lo que no es foto: {fotos}", fotos == ["1979|https://commons.wikimedia.org/wiki/File:Foto_3.jpg", "2022|https://commons.wikimedia.org/wiki/File:Foto_1.jpg", "sin fecha|https://commons.wikimedia.org/wiki/File:Foto_2.jpg"])
        alrededor = pg.evaluate("[...document.querySelectorAll('#ficha .historia .cerca li')].map((li) => li.textContent)")
        comprobar(nombre, f"alrededor: {alrededor}", alrededor[:4] == ["el Brucar partida, aquí mismo, ICV", "Casillas de Marín edificación, a 27 m, IGN, ICV", "Ermita de Prueba lugar de culto, a 44 m, OpenStreetMap", "Corral de Dalt corral, a 99 m, ICV"]
                  and not any("Bar Paco" in c or "Parc Natural" in c for c in alrededor)
                  and "Los Centenares paraje, a 300 m, OpenStreetMap, IGN" in alrededor and not any("Camí" in c or "Camino" in c for c in alrededor)
                  and "Retablo cerámico de San Roque retablo cerámico, Bien de Relevancia Local, a 10 m" in alrededor and "Estació de Villar estación de ferrocarril, a 120 m" in alrededor
                  and not any("Q555" in c or c.startswith("Llíria") for c in alrededor))
        comprobar(nombre, "un nombre con etiquetas HTML se enseña como texto y su ficha sin cifrar se cambia por la de Wikidata",
                  pg.evaluate("[...document.querySelectorAll('#ficha .historia .cerca a')].filter((a) => a.textContent === 'Molino <b>raro</b>').map((a) => a.href)") == ["https://www.wikidata.org/wiki/Q777"] and pg.evaluate("document.querySelector('#ficha .historia .cerca b b')") is None)
        fuera = dict(pg.evaluate("[...document.querySelectorAll('#ficha .historia h4')].filter((h) => h.textContent.startsWith('Seguir buscando'))[0].nextElementSibling.querySelectorAll('a').length && [...[...document.querySelectorAll('#ficha .historia h4')].filter((h) => h.textContent.startsWith('Seguir buscando'))[0].nextElementSibling.querySelectorAll('a')].map((a) => [a.textContent, a.href])"))
        comprobar(nombre, f"seguir buscando: {list(fuera)}", list(fuera) == ["Google Noticias", "Google", "Libros", "Prensa histórica", "Biblioteca Valenciana", "BOE", "DOGV", "Estudios (Dialnet)", "Europeana", "Internet Archive", "Historia de Llíria"]
                  and fuera["Prensa histórica"] == "https://prensahistorica.mcu.es/es/consulta/resultados_ocr.do?general_ocr=on&busq_general=%22Castillo%20de%20Prueba%22"
                  and fuera["Google Noticias"] == "https://news.google.com/search?q=%22Castillo%20de%20Prueba%22%20%22Ll%C3%ADria%22&hl=es&gl=ES&ceid=ES%3Aes" and "site%3Aboe.es" in fuera["BOE"])
        pie = pg.evaluate("document.querySelector('#ficha .historia .pie-historia').textContent")
        comprobar(nombre, f"dice dónde ha buscado: {pie!r}", pie.startswith("Buscado el ") and all(x in pie for x in ("OpenStreetMap", "IGN", "ICV", "Wikidata", "Commons", "Catastro", "Wikipedia", "Prensa")) and "No ha" not in pie and "Volver a buscar" in pie)
        if nombre == "movil": pg.evaluate("typeof ponerHoja === 'function' && ponerHoja('alta'); 0"); pg.wait_for_timeout(300)
        pg.evaluate("document.querySelector('#ficha .historia').scrollIntoView(); 0"); pg.wait_for_timeout(300)
        pg.screenshot(path=f"{nombre}-historia.png")
        pg.evaluate("[...document.querySelectorAll('#ficha .historia h4')].find((h) => h.textContent === 'En la prensa').scrollIntoView(); 0"); pg.wait_for_timeout(300)
        pg.screenshot(path=f"{nombre}-historia-2.png")

        # --- 3. Lo buscado se recuerda: al volver a la ficha y tras recargar la página, sin preguntar otra vez
        antes = pedidas()
        abrir(SIN_NADA); abrir(CON_FICHA)
        comprobar(nombre, "al volver a la ficha está lo encontrado, sin red", "Se construyó en el siglo XIII (Wikidata)." in texto() and pedidas() == antes)
        pg.reload(); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(2500)
        abrir(CON_FICHA); pg.wait_for_timeout(600)
        comprobar(nombre, "y tras recargar la página, también (guardado en el navegador)", "Se construyó en el siglo XIII (Wikidata)." in texto() and pedidas() == antes and pg.locator("#ficha .historia .pie-historia").count() == 1)
        pg.click("#ficha .historia .pie-historia button"); pg.wait_for_timeout(1200)
        comprobar(nombre, "«Volver a buscar» sí pregunta de nuevo", pedidas()["sparql"] == antes["sparql"] + 1 and "Se construyó en el siglo XIII (Wikidata)." in texto())
        pg.evaluate("[...document.querySelectorAll('#ficha .historia .sueltas button')].find((b) => b.textContent === 'ver su ficha').click(); 0"); pg.wait_for_timeout(500)
        comprobar(nombre, "desde la historia se salta a la ficha de la Lista Roja", pg.inner_text("#ficha-elemento h2") == "Torre de Prueba" and pg.evaluate("!!document.querySelector('#ficha-elemento .historia')"))
        pg.evaluate("cerrarElemento(); 0"); pg.wait_for_timeout(200)

        # --- 4. Un sitio sin nombre y sin ficha: el topónimo más cercano y lo que Wikidata tiene pegado, con sus avisos
        abrir(SIN_NADA)
        comprobar(nombre, "si el programa buscó y no hubo noticias, se dice", 'Google Noticias no da nada buscando "Otro" "Llíria" (20/11/2026).' in texto())
        buscar()
        t = texto()
        comprobar(nombre, f"sin nombre: {t[8:260]!r}", "No tiene nombre en los datos. El más cercano en el mapa es «Casillas de Marín» (edificación, a 27 m, IGN, ICV): puede ser el suyo." in t and "Está en «el Brucar», Llíria." in t)
        comprobar(nombre, "lo emparejado por cercanía va aparte y avisando", "Puede ser «Castillo de Prueba» (a 30 m)" in t and "Se ha emparejado solo por cercanía: comprueba que es el mismo sitio." in t
                  and "Se construyó en el siglo XIII" not in pg.evaluate("document.querySelector('#ficha .historia .resumen').textContent") and "siglo XIII" not in "".join(pg.evaluate("[...document.querySelectorAll('#ficha .historia dl.cronologia dt')].map((d) => d.textContent)")))
        comprobar(nombre, "un retablo a 10 m no se toma por el sitio", "ids=Q111&" in vistos_h["entidad-ultima"])
        comprobar(nombre, "el emparejado no se repite en la lista de alrededor", not any(c.startswith("Castillo de Prueba") for c in pg.evaluate("[...document.querySelectorAll('#ficha .historia .cerca li')].map((li) => li.textContent)")))
        comprobar(nombre, "no se dice cuándo se abandonó porque no consta", "Ninguna fuente consultada dice cuándo se abandonó" in t)
        comprobar(nombre, "avisa de que se busca por un nombre que puede no ser el suyo", "Seguir buscando «Castillo de Prueba»" in t and "El sitio no tiene nombre propio" in t)
        antes = pedidas()["noticias"]
        boton = pg.locator("#ficha .historia .boton-historia.secundario")
        comprobar(nombre, "sin nombre seguro no se buscan noticias solas: se ofrece el botón", boton.count() == 1 and boton.inner_text() == "Buscar noticias de «Castillo de Prueba»")
        boton.click(); pg.wait_for_timeout(600)
        comprobar(nombre, "el botón las trae", pedidas()["noticias"] == antes + 1 and pg.evaluate("[...document.querySelectorAll('#ficha .historia .noticias a')].map((a) => a.textContent)") == ["Hoy: Castillo de Prueba"])

        # --- 5. Un sitio con nombre: se empareja por el nombre aunque venga en valenciano
        abrir(CON_NOMBRE); buscar()
        t = texto()
        comprobar(nombre, "«Estación de Villar» = «Estació de Villar»", "ids=Q444&" in vistos_h["entidad-ultima"] and pg.evaluate("document.querySelector('#ficha .historia .resumen b').textContent") == "Estación de Villar" and "Puede ser" not in t)
        comprobar(nombre, "las noticias se buscan con su nombre y el municipio de Catastro", "nombre=Estaci%C3%B3n+de+Villar&municipio=Chiva" in vistos_h["noticias-ultima"])

        # --- 6. Fuentes que no contestan: se dice cuáles y el resto sigue
        ESCENA9.update(wikidata="caido", ign="caido", noticias="caido")
        otro = sitio_de(lambda p: p.get("nombre") == "Cuartel viejo" and not p.get("wikidata"))["properties"]["id"]
        abrir(otro); buscar()
        t = texto()
        comprobar(nombre, f"dice quién no ha contestado: {pg.evaluate('document.querySelector(`#ficha .historia .pie-historia`).textContent')!r}", "No han contestado: IGN, Wikidata y Prensa." in t and "Cuartel viejo, en Cheste." in t and "el Brucar" in t)
        comprobar(nombre, "sin el programa de noticias queda el botón para reintentar", pg.locator("#ficha .historia .boton-historia.secundario").inner_text() == "Buscar noticias de «Cuartel viejo»")
        ESCENA9.update(wikidata="bien", ign="bien"); ESCENA9.pop("noticias", None)

        # --- 7. En una web sin programa detrás no se piden noticias: quedan las guardadas y los enlaces
        pg.evaluate("conServidor = false; 0")
        antes = pedidas()["noticias"]
        otro2 = sitio_de(lambda p: p.get("nombre") == "Antigua fábrica de harinas")["properties"]["id"]
        abrir(otro2); buscar()
        comprobar(nombre, "sin programa no se llama a /vivo/noticias ni se ofrece el botón", pedidas()["noticias"] == antes and pg.locator("#ficha .historia .boton-historia.secundario").count() == 0)
        comprobar(nombre, "se busca por el nombre seguro más corto: aquí, el de su ficha, emparejada por el nombre", "ids=Q888&" in vistos_h["entidad-ultima"] and "Seguir buscando «Harinera La Unión»" in texto() and "Antigua fábrica de harinas, castillo, en Cheste." in texto())
        pg.evaluate("conServidor = true; 0")

        # --- 8. Cualquier punto del mapa y los elementos de otras capas
        pg.evaluate(f"abrirElemento(puntoDe(L.latLng({LAT + 0.01}, {LON + 0.01})), true); 0"); pg.wait_for_timeout(600)
        comprobar(nombre, "un punto cualquiera también tiene su bloque, sin nada hasta que se busca", "Aún no se ha buscado nada de este sitio" in pg.evaluate("document.querySelector('#ficha-elemento .historia').textContent"))
        pg.click("#ficha-elemento .historia .boton-historia"); pg.wait_for_selector("#ficha-elemento .historia .pie-historia", timeout=15000)
        t = pg.evaluate("document.querySelector('#ficha-elemento .historia').textContent")
        comprobar(nombre, "y al buscar dice qué hay en ese punto", "El más cercano en el mapa es «Casillas de Marín»" in t and "Dirección en Catastro" in t and "cuándo se abandonó" not in t)
        comprobar(nombre, "la referencia catastral del punto, que llega después de abrir la ficha, se usa en la búsqueda", "RefCat=" in vistos_h["catastro-ultima"])
        comprobar(nombre, "qué capas llevan historia", pg.evaluate("['posibles','listaroja','abandonado','historico','edificios','industria','wikipedia','punto','lugar'].every((c) => tieneHistoria({ capa: c })) && ['dgt','camaras','paradas','gasolineras','aviones','farolas','muros','commons','restaurantes'].every((c) => !tieneHistoria({ capa: c }))"))
        pg.evaluate("cerrarElemento(); 0"); pg.wait_for_timeout(200)

        # --- 9. Buscarla sola al abrir cada ficha, si se deja dicho
        otro3 = sitio_de(lambda p: p.get("nombre") == "Hotel Mirador" and not p.get("wikidata"))["properties"]["id"]
        abrir(otro3)
        antes = pedidas()["sparql"]
        pg.wait_for_timeout(1500)
        comprobar(nombre, "por defecto no busca sola", pedidas()["sparql"] == antes)
        pg.check("#ficha .historia .ajuste-historia input"); pg.wait_for_selector("#ficha .historia .pie-historia", timeout=15000)
        comprobar(nombre, "al marcar la casilla busca la de la ficha abierta y lo recuerda", pedidas()["sparql"] == antes + 1 and pg.evaluate("JSON.parse(localStorage.getItem('osintmaps.historia.v1')).sola") is True)
        otro4 = sitio_de(lambda p: p.get("nombre") == "Hotel Mirador" and p.get("wikidata") and p["id"] != CON_FICHA)["properties"]["id"]
        abrir(otro4); pg.wait_for_selector("#ficha .historia .pie-historia", timeout=15000)
        comprobar(nombre, "y la siguiente ficha se busca sola", pedidas()["sparql"] == antes + 2)
        pg.uncheck("#ficha .historia .ajuste-historia input")
        comprobar(nombre, "se puede quitar", pg.evaluate("JSON.parse(localStorage.getItem('osintmaps.historia.v1')).sola") is False)

        # --- 10. Modo oscuro: el bloque se lee
        pg.evaluate("document.documentElement.dataset.tema = 'oscuro'; document.querySelector('#ficha .historia').scrollIntoView(); 0"); pg.wait_for_timeout(300)
        pg.screenshot(path=f"{nombre}-historia-oscuro.png")
        ctx.close()
    b.close()
(datos / "historia.json").unlink(missing_ok=True)
print("ERRORES:", errores or "ninguno")
