import functools, threading, sys, json, shutil, base64, re
import pathlib, zipfile
sys.path.insert(0, str(pathlib.Path.cwd().parent))            # el paquete se usa tal cual está en el repositorio
if not pathlib.Path("datos").exists(): zipfile.ZipFile("datos.zip").extractall(".")      # datos de prueba
from pathlib import Path
from osintmaps import cli
from osintmaps.fuentes import camaras as fc
from playwright.sync_api import sync_playwright
origen = Path("datos").resolve(); datos = Path("datos8").resolve()
shutil.rmtree(datos, ignore_errors=True); shutil.copytree(origen, datos)
def limpiar():
    for f in ("marcas.json", "marcadores.json"): (datos / f).unlink(missing_ok=True)
limpiar()
g = json.load(open(datos / "candidatos.geojson")); LON, LAT = g["features"][0]["geometry"]["coordinates"][:2]
(datos / "camaras.geojson").write_text(json.dumps(fc.geojson([{"id": "node/1", "lat": LAT + 0.0004, "lon": LON + 0.0004, "tipo": "camera", "direccion": "135"}])), encoding="utf-8")
for nombre, puntos in {"listaroja": [{"id": "listaroja-1", "nombre": "Torre de Prueba", "lat": LAT + 0.001, "lon": LON + 0.001, "resumen": "Villa (Valencia). Se cae.", "url": "https://listaroja.hispanianostra.org/ficha/x/"}],
                       "dgt": [{"id": "dgt-9", "nombre": "A-7 km 300", "lat": LAT - 0.001, "lon": LON + 0.001, "carretera": "A-7", "pk": "300", "imagen": "https://etraffic.dgt.es/camarasEtraffic/9.jpg"}],
                       "subastas": [{"id": "subasta-S1-1", "nombre": "Inmueble (Vivienda) en subasta", "lat": LAT - 0.001, "lon": LON - 0.001, "direccion": "Calle Mayor 1", "situado_por": "parcela", "url": "https://subastas.boe.es/detalleSubasta.php?idSub=S1", "valor_subasta": "50.000,00 €"}]}.items():
    (datos / f"capa-{nombre}.geojson").write_text(json.dumps(cli._geojson_de_puntos(puntos)), encoding="utf-8")
cli._Servidor.carpeta_datos = datos
srv = cli.ServidorMapa(("127.0.0.1", 8776), functools.partial(cli._Servidor, directory=str(cli.CARPETA_WEB)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
NM = Path("node_modules"); CORS = {"Access-Control-Allow-Origin": "*"}
import zlib, struct, random
def _png(ancho, alto, pixel):
    crudo = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(ancho)) for y in range(alto))
    trozo = lambda tipo, datos: struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)) + trozo(b"IDAT", zlib.compress(crudo)) + trozo(b"IEND", b"")
random.seed(3)
_manchas = [[random.choice([(96, 104, 84), (132, 124, 104), (74, 88, 70), (168, 160, 148), (110, 98, 86)]) for _ in range(8)] for _ in range(8)]
PNG = _png(64, 64, lambda x, y: _manchas[y // 8][x // 8])
def _png_transparente(lado=8):
    crudo = b"".join(b"\x00" + b"\x00\x00\x00\x00" * lado for _ in range(lado))
    trozo = lambda tipo, datos: struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 6, 0, 0, 0)) + trozo(b"IDAT", zlib.compress(crudo)) + trozo(b"IEND", b"")
PNG_HUECO = _png_transparente()
teselas = {}
OSM = {"elements": [
    {"type": "node", "id": 20, "lat": LAT + 0.0006, "lon": LON - 0.0006, "tags": {"man_made": "mast", "name": "Antena del Cerro", "operator": "Cellnex", "height": "40"}},
    {"type": "node", "id": 30, "lat": LAT + 0.0009, "lon": LON + 0.0002, "tags": {"man_made": "tower", "name": '<img src=x onerror="window.__xss=1">Torre'}},
    {"type": "way", "id": 21, "bounds": {"minlat": LAT - 0.0008, "minlon": LON - 0.001, "maxlat": LAT - 0.0006, "maxlon": LON + 0.001}, "geometry": [{"lat": LAT - 0.0008, "lon": LON - 0.001}, {"lat": LAT - 0.0006, "lon": LON + 0.001}], "tags": {"railway": "disused", "name": "Ramal viejo"}},
    {"type": "node", "id": 22, "lat": LAT + 0.0002, "lon": LON + 0.0009, "tags": {"man_made": "surveillance", "surveillance:type": "camera", "camera:type": "dome"}},
    {"type": "node", "id": 23, "lat": LAT + 0.0003, "lon": LON - 0.0002, "tags": {"highway": "street_lamp"}},
    {"type": "node", "id": 24, "lat": LAT + 0.01, "lon": LON, "tags": {"amenity": "police", "name": "Policía Local"}}]}
PARCHE = f"<gml:PolygonPatch><gml:exterior><gml:LinearRing><gml:posList>{LAT+0.0001} {LON+0.0001} {LAT+0.0001} {LON+0.0003} {LAT+0.0003} {LON+0.0003} {LAT+0.0001} {LON+0.0001}</gml:posList></gml:LinearRing></gml:exterior><gml:interior><gml:LinearRing><gml:posList>{LAT+0.00015} {LON+0.0002} {LAT+0.00015} {LON+0.00025} {LAT+0.0002} {LON+0.00025} {LAT+0.00015} {LON+0.0002}</gml:posList></gml:LinearRing></gml:interior></gml:PolygonPatch>"
SIN_DATOS = '<?xml version="1.0"?><ExceptionReport xmlns="http://www.opengis.net/ows/1.1"><Exception exceptionCode="OperationProcessingFailed"><ExceptionText><![CDATA[No records founded for BBOX and SRS provided]]></ExceptionText></Exception></ExceptionReport>'
FALLO_CATASTRO = SIN_DATOS.replace("No records founded for BBOX and SRS provided", "Internal error")
modo = {"wfs": "bien", "arcgis": "bien", "osm": "bien", "icv": "bien", "vlc": "bien"}
import time
PARCELAS = f'<?xml version="1.0"?><gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:cp="c">' + "".join(f'<gml:featureMember><cp:CadastralParcel><cp:areaValue>400</cp:areaValue><cp:nationalCadastralReference>46137A005{k:05d}</cp:nationalCadastralReference><gml:PolygonPatch><gml:exterior><gml:LinearRing><gml:posList>{LAT+0.0004*k} {LON-0.001} {LAT+0.0004*k} {LON+0.001} {LAT+0.0004*k+0.0003} {LON+0.001} {LAT+0.0004*k} {LON-0.001}</gml:posList></gml:LinearRing></gml:exterior></gml:PolygonPatch></cp:CadastralParcel></gml:featureMember>' for k in range(-3, 4)) + "</gml:FeatureCollection>"
BU = f'<?xml version="1.0"?><gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:bu="x" xmlns:base="b"><gml:featureMember><bu:Building><bu:conditionOfConstruction>ruin</bu:conditionOfConstruction><bu:beginning>1920-01-01T00:00:00</bu:beginning><bu:currentUse>3_industrial</bu:currentUse><bu:reference>0000001YJ0000A</bu:reference><bu:geometry><gml:Surface><gml:patches>{PARCHE}{PARCHE}</gml:patches></gml:Surface></bu:geometry><bu:OfficialArea><bu:value>850</bu:value></bu:OfficialArea></bu:Building></gml:featureMember></gml:FeatureCollection>'
vistos = {}
def ruta(route):
    u = route.request.url
    def js(d): return route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(d))
    if "unpkg.com/leaflet@" in u: return route.fulfill(path=str(NM / "leaflet/dist" / u.rsplit("/", 1)[-1]))
    if "unpkg.com/leaflet.markercluster@" in u: return route.fulfill(path=str(NM / "leaflet.markercluster/dist" / u.rsplit("/", 1)[-1]))
    if "127.0.0.1" in u: return route.continue_()
    # --- fotos aéreas ---
    if "terramapas.icv.gva.es" in u:
        teselas["icv"] = teselas.get("icv", 0) + 1; teselas["icv-ultima"] = u
        return route.fulfill(status=200, content_type="image/png", headers=CORS, body=PNG_HUECO if modo["icv"] == "fuera" else PNG)
    if "FotoAerea" in u:
        clave = "vlc-antigua" if "FotoAerea/FotoAerea_" in u else "vlc-export" if "/export" in u else "vlc"
        teselas[clave] = teselas.get(clave, 0) + 1; teselas[clave + "-ultima"] = u
        if modo["vlc"] == "fuera" and clave == "vlc": return route.fulfill(status=404, content_type="text/html", headers=CORS, body="no")
        return route.fulfill(status=200, content_type="image/png", headers=CORS, body=PNG)
    if "ign.es/wmts/pnoa-ma" in u: teselas["pnoa"] = teselas.get("pnoa", 0) + 1; teselas["pnoa-ultima"] = u
    if "ign.es/wms-inspire/pnoa-ma" in u: teselas["pnoa-wms"] = teselas.get("pnoa-wms", 0) + 1
    if "mt0.google" in u or "mt1.google" in u or "mt2.google" in u or "mt3.google" in u: teselas["google"] = teselas.get("google", 0) + 1
    for clave in ("interpreter", "wikipedia", "commons", "panoramax", "cartociudad", "RCCOOR", "DNPRC", "open-meteo", "nominatim", "earth-search", "wfsBU", "geoportal.valencia", "CPMRC"):
        if clave in u: vistos[clave] = vistos.get(clave, 0) + 1
    if "wfsCP" in u:
        vistos["wfsCP"] = vistos.get("wfsCP", 0) + 1
        return route.fulfill(status=200, content_type="text/xml", headers=CORS, body=PARCELAS)
    if "interpreter" in u:
        vistos["consulta"] = route.request.post_data
        servidor = u.split("/")[2]
        vistos[servidor] = vistos.get(servidor, 0) + 1
        if modo["osm"] == "primero-callado" and servidor == "overpass-api.de": return None      # ni contesta ni falla
        if "quarry" in (route.request.post_data or ""): return js({"remark": "runtime error: Query timed out in \"query\" at line 1 after 41 seconds.", "elements": OSM["elements"][:1]})
        return js(OSM)
    if "es.wikipedia.org" in u and "extracts" in u: return js({"query": {"pages": {"7": {"extract": "Texto del artículo."}}}})
    if "es.wikipedia.org" in u: return js({"query": {"pages": {"7": {"pageid": 7, "title": "Castillo de Prueba", "coordinates": [{"lat": LAT + 0.0015, "lon": LON}], "description": "castillo"}}}})
    if "commons.wikimedia.org" in u: return js({"query": {"pages": {"8": {"pageid": 8, "title": "File:Foto de prueba.jpg", "coordinates": [{"lat": LAT, "lon": LON + 0.0015}], "imageinfo": [{"mime": "image/jpeg", "url": "https://upload.wikimedia.org/a.jpg", "thumburl": "https://upload.wikimedia.org/thumb/a.jpg/1280px-a.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:a.jpg", "extmetadata": {"Artist": {"value": "<a>Ana</a>"}, "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}})
    if "panoramax" in u and "search" in u: return js({"features": [{"id": "p1", "geometry": {"type": "Point", "coordinates": [LON + 0.0002, LAT - 0.0002]}, "properties": {"datetime": "2024-05-01T10:00:00Z", "view:azimuth": 90, "license": "CC-BY-SA-4.0"}, "assets": {"hd": {"href": "https://panoramax.example/hd.jpg"}, "sd": {"href": "https://panoramax.example/sd.jpg"}, "thumb": {"href": "https://panoramax.example/t.jpg"}}}]})
    if "reverseGeocode" in u: return js({"address": "CALLE MAYOR", "portalNumber": 3, "postalCode": "46160", "muni": "Llíria"})
    if "Consulta_RCCOOR" in u:
        urbana = float(re.search(r"CoorY=([\d.]+)", u).group(1)) > LAT + 0.0015
        return js({"Consulta_RCCOORResult": {"coordenadas": {"coord": [{"pc": {"pc1": "5823501", "pc2": "YJ2752D"} if urbana else {"pc1": "46137A0", "pc2": "0500081"}, "ldt": "Polígono 5"}]}}})
    if "routing.openstreetmap.de" in u:
        vistos["ruta"] = u.split("/route/v1/")[1][:60]
        return js({"code": "Ok", "routes": [{"distance": 3850, "duration": 3079.8, "geometry": {"type": "LineString", "coordinates": [[LON - 0.0008, LAT - 0.0004], [LON, LAT + 0.0002], [LON + 0.0005, LAT + 0.0005]]}}]})
    if "rainviewer" in u and u.endswith(".json"): return js({"host": "https://tilecache.rainviewer.com", "radar": {"past": [{"time": 1, "path": "/v2/radar/abc"}]}})
    if "Consulta_DNPRC" in u: return js({"consulta_dnprcResult": {"bico": {"bi": {"debi": {"luso": "Industrial", "sfc": "850", "ant": "1920"}}}}})
    if "Consulta_CPMRC" in u: return js({"Consulta_CPMRCResult": {"coordenadas": {"coord": [{"geo": {"xcen": str(LON + 0.002), "ycen": str(LAT + 0.002)}, "ldt": "CL MAYOR 3 LLIRIA"}]}}})
    if "open-meteo" in u: return js({"elevation": 164, "current": {"temperature_2m": 18.4, "precipitation": 0, "cloud_cover": 20, "wind_speed_10m": 9}, "daily": {"sunrise": ["2026-11-22T07:52"], "sunset": ["2026-11-22T17:44"]}})
    if "nominatim" in u: return js([{"name": "Estación del Norte", "display_name": "Estación del Norte, València", "lat": str(LAT + 0.003), "lon": str(LON + 0.003), "boundingbox": [str(LAT + 0.0029), str(LAT + 0.0031), str(LON + 0.0029), str(LON + 0.0031)]}])
    if "earth-search" in u: return js({"features": [{"properties": {"datetime": "2026-10-28T10:50:00Z", "eo:cloud_cover": 3}, "assets": {"visual": {"href": "https://s2.example/TCI.tif"}}}]})
    if "wfsBU" in u and modo["wfs"] == "lento":
        time.sleep(1.2)
        return route.fulfill(status=200, content_type="text/xml", headers=CORS, body=SIN_DATOS)
    if "wfsBU" in u: return route.fulfill(status=200, content_type="text/xml", headers=CORS, body={"bien": BU, "vacio": SIN_DATOS, "fallo": FALLO_CATASTRO}[modo["wfs"]])
    if "geoportal.valencia" in u and modo["arcgis"] == "fallo": return js({"error": {"code": 400, "message": "Invalid or missing input parameters."}})
    if "geoportal.valencia" in u: return js({"features": [{"type": "Feature", "id": 5, "geometry": {"type": "Polygon", "coordinates": [[[LON - 0.0004, LAT + 0.0008], [LON - 0.0002, LAT + 0.0008], [LON - 0.0002, LAT + 0.001], [LON - 0.0004, LAT + 0.0008]]]}, "properties": {"objectid": 5, "direccion": "Solar de la calle Alta", "estado": "Solar"}}]}) if "/286/" in u else js({"features": []})
    if route.request.resource_type in ("image",): return route.fulfill(status=200, content_type="image/png", headers=CORS, body=PNG)
    if "google.com/maps" in u: return route.fulfill(status=200, content_type="text/html", body="<p>sv</p>")
    return route.abort()
errores = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for nombre, vp in (("escritorio", {"width": 1360, "height": 860}), ("movil", {"width": 390, "height": 800})):
        limpiar(); vistos.clear()
        ctx = b.new_context(viewport=vp, has_touch=(nombre == "movil")); pg = ctx.new_page(); pg.route("**/*", ruta)
        pg.on("console", lambda m: errores.append(f"{nombre} {m.text[:200]}") if m.type == "error" and "ERR_FAILED" not in m.text and "502" not in m.text and not (modo["vlc"] == "fuera" and "404" in m.text) else None)
        pg.on("pageerror", lambda e: errores.append(f"{nombre} EXC: {e}"))
        pg.on("response", lambda r: errores.append(f"{nombre} {r.status}: {r.url[:120]}") if r.status == 404 and "FotoAerea_2025/MapServer/tile" not in r.url else None)
        pg.on("request", lambda r: print("   >>> petición rara:", r.resource_type, r.url[:80], flush=True) if r.url.endswith("/null") else None)
        modo.update(wfs="bien", arcgis="bien")
        pg.emulate_media(color_scheme="light")
        pg.add_init_script("window.__vacioVisto = false; new MutationObserver(() => { const v = document.getElementById('vacio'); if (v && v.offsetParent) window.__vacioVisto = true; }).observe(document, {childList: true, subtree: true, attributes: true});")
        pg.goto("http://127.0.0.1:8776/#mapa=15/40.41000/-3.70000"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(900)
        print(nombre, "pantalla de «sin resultados» asomó al arrancar:", pg.evaluate("window.__vacioVisto"), "| arrancando quitado:", pg.evaluate("!document.getElementById('panel').classList.contains('arrancando')"), "| datos pedidos por adelantado:", pg.evaluate("!!window.OSINT_PRONTO"))
        print(nombre, "posición de la URL respetada:", pg.evaluate("mapa.getZoom() + ' ' + mapa.getCenter().lat.toFixed(2) + ',' + mapa.getCenter().lng.toFixed(2)"))
        plegar = lambda: (pg.evaluate("ponerHoja('minima')"), pg.wait_for_timeout(350)) if nombre == "movil" else None
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(500)
        def punto(la, lo):
            return pg.evaluate(f"(() => {{ const p = mapa.latLngToContainerPoint([{la}, {lo}]); const r = document.getElementById('mapa').getBoundingClientRect(); return [r.left + p.x, r.top + p.y]; }})()")
        print(nombre, "fondos:", pg.evaluate("document.getElementById('capa-fondo').options.length"), "| superpuestas:", pg.evaluate("document.querySelectorAll('#capas-superponer input').length"), "| capas de datos:", pg.evaluate("document.querySelectorAll('#capas-datos input').length"),
              "| fijas:", pg.evaluate("['listaroja','dgt','subastas'].map(c => estado[c].elementos.size).join(',')"))
        pg.evaluate("for (const id of ['antenas','tren','farolas','policia','wikipedia','commons','panoramax','edificios','solares','listaroja','dgt','subastas']) { const c = document.getElementById('dato-' + id); c.checked = true; c.dispatchEvent(new Event('change')); }")
        pg.wait_for_timeout(2200)
        print(nombre, "pedidos:", {k: v for k, v in vistos.items() if k != "consulta"})
        print(nombre, "consulta OSM (trozo):", (vistos.get("consulta") or "")[:150].replace("%22", '"'))
        pg.evaluate("document.getElementById('dato-bic').click(); document.getElementById('dato-energia').click(); document.getElementById('dato-industria').click()"); pg.wait_for_timeout(900)
        plegar(); pg.screenshot(path=f"{nombre}-simbolos.png")
        if nombre == "escritorio":
            pg.evaluate("document.getElementById('capas').open = true"); pg.wait_for_timeout(200); pg.screenshot(path="escritorio-capas-claro.png"); pg.evaluate("document.getElementById('capas').open = false")
        print(nombre, "símbolos en el panel:", pg.evaluate("document.querySelectorAll('#capas svg.simbolo').length"), "| sitio es símbolo:", pg.evaluate("candidatos[0].marcador instanceof Simbolo && candidatos[0].marcador.options.forma"), "| radio a zoom 17:", pg.evaluate("candidatos[0].marcador._radius"))
        print(nombre, "elementos:", pg.evaluate("JSON.stringify(Object.fromEntries(CAPAS.map(c => [c.id, estado[c.id].elementos.size]).filter(x => x[1])))"), "| cámaras:", pg.evaluate("camaras.size"), "| estado:", pg.inner_text("#estado-antenas"), "|", pg.evaluate("document.getElementById('aviso-capas').hidden"))
        plegar()
        # clic en un elemento (antena)
        x, y = punto(LAT + 0.0006, LON - 0.0006); pg.mouse.click(x, y); pg.wait_for_timeout(900)
        print(nombre, "ficha antena:", pg.inner_text("#ficha-elemento").replace("\n", " | ")[:520])
        pg.screenshot(path=f"{nombre}-elemento.png")
        # visor
        pg.click("#ficha-elemento .vistas button:nth-child(1)"); pg.wait_for_timeout(500)
        print(nombre, "visor ortofoto:", pg.inner_text("#visor .pestanas").replace("\n", " / "), "| años:", pg.locator("#visor .opciones button").count(), "| pie:", pg.inner_text("#visor .pie-foto")[:80])
        pg.click("#visor .pestanas button[data-modo=calle]"); pg.wait_for_timeout(700)
        print(nombre, "calle:", pg.locator("#visor iframe").count(), pg.inner_text("#visor .opciones").replace("\n", " / "))
        pg.click("#visor .pestanas button[data-modo=fotos]"); pg.wait_for_timeout(700)
        print(nombre, "fotos:", pg.locator("#visor .miniaturas button").count(), "|", pg.inner_text("#visor .pie-foto")[:90])
        pg.click("#visor .pestanas button[data-modo=satelite]"); pg.wait_for_timeout(700)
        print(nombre, "satélite:", pg.inner_text("#visor .opciones").replace("\n", " / "), "|", pg.inner_text("#visor .pie-foto")[:60])
        pg.screenshot(path=f"{nombre}-visor.png")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        print(nombre, "visor cerrado:", pg.locator("#visor").count() == 0, "| ficha sigue:", pg.evaluate("elementoAbierto !== null"))
        # menú contextual → ¿qué hay aquí?
        plegar()
        x, y = punto(LAT - 0.0003, LON - 0.0009); pg.mouse.click(x, y, button="right"); pg.wait_for_timeout(300)
        print(nombre, "menú:", pg.inner_text("#menu-mapa").replace("\n", " / ")[:160])
        pg.click("#menu-mapa button:nth-of-type(1)"); pg.wait_for_timeout(1500)
        print(nombre, "punto:", pg.inner_text("#ficha-elemento").replace("\n", " | ")[:900])
        # buscador
        pg.fill("#buscar-texto", "antena"); pg.wait_for_timeout(1300)
        print(nombre, "buscar 'antena':", pg.inner_text("#resultados-extra").replace("\n", " | ")[:200], "| ficha cerrada:", pg.evaluate("elementoAbierto === null"))
        pg.fill("#buscar-texto", "39.5, -0.4"); pg.wait_for_timeout(300)
        print(nombre, "coordenadas:", pg.inner_text("#resultados-extra").replace("\n", " | ")[:90])
        pg.fill("#buscar-texto", "5823501YJ2752D"); pg.wait_for_timeout(600)
        print(nombre, "refcat:", pg.inner_text("#resultados-extra").replace("\n", " | ")[:110])
        pg.click("#resultados-extra button"); pg.wait_for_timeout(600)
        pg.wait_for_timeout(500)
        print(nombre, "tras ir a la parcela:", pg.inner_text("#ficha-elemento h2"), "|", pg.evaluate("location.hash"), "| fachada de Catastro:", pg.locator("#ficha-elemento .portada.fachada").count())
        pg.fill("#buscar-texto", ""); pg.evaluate("document.activeElement.blur()"); pg.wait_for_timeout(500)
        # pestañas del panel
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(700)
        pg.evaluate("(esMovil() ? ponerHoja('media') : 0)")
        print(nombre, "pestañas:", pg.inner_text("#pestanas").replace("\n", " "), "| grupos de capas:", pg.evaluate("[...document.querySelectorAll('.grupo-de-capas')].map(g => g.querySelector('summary').innerText.replace(/\\n/g, ' ')).join(' / ')"))
        pg.click("#pestanas button[data-pestana=mapa]"); pg.wait_for_timeout(400)
        print(nombre, "en el mapa:", pg.inner_text("#lista-capas").replace("\n", " | ")[:260], "| sitios ocultos:", pg.evaluate("getComputedStyle(document.getElementById('lista')).display"))
        with pg.expect_download() as bajada: pg.click("#lista-capas .cabecera-lista button")
        g = json.load(open(bajada.value.path(), encoding="utf-8"))
        areas = [f for f in g["features"] if f["geometry"]["type"] in ("Polygon", "MultiPolygon")]
        print(nombre, "GeoJSON exportado:", bajada.value.suggested_filename, "|", len(g["features"]), "elementos |", sorted({f["geometry"]["type"] for f in g["features"]}),
              "| áreas con anillo cerrado y lon,lat:", bool(areas) and all((f["geometry"]["coordinates"][0][0] == f["geometry"]["coordinates"][0][-1]) and f["geometry"]["coordinates"][0][0][0] < 0 for f in areas if f["geometry"]["type"] == "Polygon"))
        pg.screenshot(path=f"{nombre}-en-el-mapa.png")
        pg.click("#lista-capas li:nth-child(3) button"); pg.wait_for_timeout(500)
        print(nombre, "desde la lista:", pg.inner_text("#ficha-elemento h2"), "| pestañas ocultas con ficha:", pg.evaluate("getComputedStyle(document.getElementById('pestanas')).display"))
        # ruta: origen con el menú, destino con el botón de la ficha
        plegar(); pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(300); x, y = punto(LAT - 0.0004, LON - 0.0008)
        print(nombre, "  bajo el punto:", x, y, pg.evaluate(f"(() => {{ const e = document.elementFromPoint({x}, {y}); return e ? e.tagName + '#' + e.id + '.' + String(e.className).slice(0, 40) : 'nada'; }})()"), "| hoja:", pg.evaluate("typeof hojaActual === 'function' ? hojaActual() + ' ' + document.getElementById('panel').className : ''"), "| centro:", pg.evaluate("mapa.getCenter().lat.toFixed(4) + ',' + mapa.getCenter().lng.toFixed(4) + ' z' + mapa.getZoom()"), flush=True)
        pg.mouse.click(x, y, button="right"); pg.wait_for_timeout(200)
        pg.click("#menu-mapa button:has-text('Ruta desde aquí')"); pg.wait_for_timeout(200)
        print(nombre, "ruta, solo origen:", pg.inner_text("#tarjeta-mapa").replace("\n", " | ")[:110])
        print(nombre, "  la ficha de la ruta pide el destino:", pg.evaluate("!document.getElementById('ficha-ruta').hidden"), "|", pg.evaluate("document.getElementById('ruta-cuerpo').textContent")[:60])
        pg.evaluate("(esMovil() ? ponerHoja('media') : 0)")
        pg.evaluate("abrirElemento([...estado.antenas.elementos.values()][0]); 0"); pg.wait_for_timeout(300)
        pg.click("#ficha-elemento .como-llegar"); pg.wait_for_timeout(2600)
        print(nombre, "ruta:", pg.evaluate("document.getElementById('tarjeta-mapa').innerText").replace("\n", " | "), "| pedida:", vistos.get("ruta"), "| trazos:", pg.evaluate("ruta.capa.getLayers().length"),
              "| modos:", pg.evaluate("[...document.querySelectorAll('.modos-ruta button')].map(b => b.innerText.replace(/\\n/g, ' ')).join(' / ')"))
        pg.click(".modos-ruta button[data-modo=coche]"); pg.wait_for_timeout(500)
        print(nombre, "en coche:", vistos.get("ruta", "")[:30], "|", pg.evaluate("document.getElementById('tarjeta-mapa').innerText").replace("\n", " | ")[:60])
        plegar(); pg.screenshot(path=f"{nombre}-ruta.png")
        pg.evaluate("quitarRuta(); 0"); pg.wait_for_timeout(200)
        print(nombre, "ruta quitada:", pg.evaluate("document.getElementById('tarjeta-mapa').hidden && ruta.capa.getLayers().length === 0 && document.getElementById('ficha-ruta').hidden"))
        # medir
        pg.evaluate("cerrarElemento()"); plegar()
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(300)
        x, y = punto(LAT - 0.0006, LON + 0.0006); pg.mouse.click(x, y, button="right"); pg.wait_for_timeout(200)
        pg.click("#menu-mapa button:has-text('Medir')"); pg.wait_for_timeout(200)
        for dla, dlo in ((-0.0006, 0.0012), (-0.0010, 0.0012)):
            x, y = punto(LAT + dla, LON + dlo); pg.mouse.click(x, y); pg.wait_for_timeout(150)
        print(nombre, "medida:", pg.inner_text("#tarjeta-mapa").replace("\n", " | "), "| marcador creado por error:", pg.evaluate("Object.keys(marcadores).length"))
        pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
        print(nombre, "medida terminada:", pg.inner_text("#tarjeta-mapa").replace("\n", " | "), "| midiendo:", pg.evaluate("midiendo"))
        pg.click("#tarjeta-mapa button:has-text('Quitar')"); pg.wait_for_timeout(150)
        # pedir un marcador mientras se mide: se deja de medir y el siguiente toque pone el marcador
        x, y = punto(LAT - 0.0006, LON + 0.0006); pg.mouse.click(x, y, button="right"); pg.wait_for_timeout(200)
        pg.click("#menu-mapa button:has-text('Medir')"); pg.wait_for_timeout(200)
        pg.click("#anadir"); pg.wait_for_timeout(150)
        x, y = punto(LAT - 0.0005, LON + 0.0003); pg.mouse.click(x, y); pg.wait_for_timeout(500)
        print(nombre, "marcador pedido mientras se medía:", pg.evaluate("JSON.stringify({midiendo, colocando, puntosDeMedida: medida.puntos.length, fichaDeMarcador: !document.getElementById('ficha-marcador').hidden})"))
        pg.click("#ficha-marcador button.peligro"); pg.click("#ficha-marcador button.peligro"); pg.wait_for_timeout(200)
        pg.evaluate("(esMovil() ? ponerHoja('media') : 0); ponerPestana('sitios')")
        # cámara → ficha general → guardar como marcador
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 18, {{animate: false}})"); pg.wait_for_timeout(600); plegar()
        x, y = punto(LAT + 0.0004, LON + 0.0004); pg.mouse.click(x, y); pg.wait_for_timeout(500)
        print(nombre, "cámara:", pg.inner_text("#ficha-elemento h2"), "|", pg.inner_text("#ficha-elemento .datos").replace("\n", " ")[:80])
        pg.click("#ficha-elemento .enlaces button:nth-child(1)"); pg.wait_for_timeout(500)
        print(nombre, "guardada:", pg.inner_text("#ficha-marcador h2"), "| elemento:", pg.evaluate("elementoAbierto"), "| nota:", pg.input_value("#nota-marcador")[:50])
        pg.evaluate("cerrarMarcador(); (esMovil() ? ponerHoja('media') : 0)"); pg.click("#pestanas button[data-pestana=marcadores]"); pg.wait_for_timeout(300)
        print(nombre, "lista de marcadores:", pg.inner_text("#lista-marcadores").replace("\n", " | ")[:140])
        pg.click("#lista-marcadores li button"); pg.wait_for_timeout(400)
        print(nombre, "marcador desde la lista:", pg.evaluate("marcadorAbierto !== null"))
        pg.evaluate("ponerPestana('sitios')")
        # sitio abandonado sigue abriendo su ficha
        pg.evaluate("cerrarMarcador()"); plegar()
        x, y = punto(LAT, LON); pg.mouse.click(x, y); pg.wait_for_timeout(500)
        print(nombre, "sitio:", pg.evaluate("!document.getElementById('ficha').hidden"), "| edificio/solar debajo no estorba")
        # con el visor abierto sobre la ficha de un sitio, los atajos de la ficha no actúan
        pg.click("#ficha .vistas button:nth-child(1)"); pg.wait_for_timeout(300)
        pg.keyboard.press("f"); pg.keyboard.press("x"); pg.keyboard.press("ArrowRight")
        for _ in range(40): pg.keyboard.press("Tab")
        print(nombre, "atajos con visor:", pg.evaluate("JSON.stringify({marca: (marcas[seleccion.id] || {}).estado || '', mismoSitio: seleccion.id === candidatos.find(c => c === seleccion).id, focoDentro: document.getElementById('visor').contains(document.activeElement)})"))
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        print(nombre, "foco al cerrar:", pg.evaluate("document.activeElement.textContent"), "| ficha sigue:", pg.evaluate("seleccion !== null"))
        pg.evaluate("volverALista()")
        # nombre con código dentro: se ve como texto y no se ejecuta
        pg.evaluate("(() => { const d = estado.antenas.dibujos.get('node/30'); d.openTooltip(); })()"); pg.wait_for_timeout(300)
        print(nombre, "rótulo hostil:", pg.evaluate("JSON.stringify({ejecutado: window.__xss === 1, imagenes: document.querySelectorAll('.leaflet-tooltip img').length, texto: (document.querySelector('.leaflet-tooltip') || {}).textContent})"))
        # buscar una cámara por lo que se sabe de ella
        pg.fill("#buscar-texto", "domo"); pg.wait_for_timeout(300)
        print(nombre, "buscar 'domo':", pg.inner_text("#resultados-extra").replace("\n", " | ")[:120])
        pg.fill("#buscar-texto", ""); pg.evaluate("document.activeElement.blur()"); pg.wait_for_timeout(500)
        # edificios: patio conservado y trozo repetido descartado; vacío y fallo de Catastro
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 18, {{animate: false}})"); pg.wait_for_timeout(1800)
        print(nombre, "edificio:", pg.evaluate("(() => { const e = [...estado.edificios.elementos.values()][0]; return e ? JSON.stringify({poligonos: e.anillos.length, anillos: e.anillos[0].length, nombre: e.nombre}) : 'ninguno'; })()"))
        for caso in ("vacio", "fallo"):
            modo["wfs"] = caso
            pg.evaluate("memoria.vaciar()"); pg.wait_for_timeout(100)
            pg.evaluate(f"vaciar(CAPA.edificios); mapa.setView([{LAT + 0.02}, {LON}], 18, {{animate: false}})"); pg.wait_for_timeout(1800)
            print(nombre, f"Catastro {caso}:", pg.evaluate("JSON.stringify({n: estado.edificios.elementos.size, error: estado.edificios.error, dadasPorCargadas: estado.edificios.teselas.size})"))
        # un servicio municipal que contesta con error, y Overpass que se queda sin tiempo
        modo["arcgis"] = "fallo"
        pg.evaluate(f"vaciar(CAPA.solares); document.getElementById('dato-canteras').click(); mapa.setView([{LAT + 0.2}, {LON}], 16, {{animate: false}})"); pg.wait_for_timeout(2500)
        print(nombre, "aviso de fallo:", pg.inner_text("#aviso-capas").replace("\n", " | "), "| fichas con fallo:", pg.evaluate("[...document.querySelectorAll('#tira-capas button.falla span')].map(s => s.textContent).join(', ')"))
        modo["arcgis"] = "bien"; pg.click("#aviso-capas button"); pg.wait_for_timeout(1500)
        print(nombre, "tras reintentar:", pg.evaluate("JSON.stringify({solares: estado.solares.error, canteras: estado.canteras.error, aviso: document.getElementById('aviso-capas').textContent})"))
        print(nombre, "ArcGIS con error:", pg.evaluate("JSON.stringify({error: estado.solares.error, dadasPorCargadas: estado.solares.teselas.size})"), "| Overpass sin tiempo:", pg.evaluate("JSON.stringify({error: estado.canteras.error, dadasPorCargadas: estado.canteras.teselas.size, otras: estado.antenas.error})"))
        pg.screenshot(path=f"{nombre}-final.png")

        # ===== memoria del navegador: lo ya bajado sale sin pedirlo otra vez =====
        modo.update(wfs="bien", arcgis="bien", osm="bien")
        pg.evaluate("if (capasActivas.has('canteras')) document.getElementById('dato-canteras').click(); memoria.vaciar()"); pg.wait_for_timeout(100)
        pg.reload(); pg.wait_for_selector("#lista li")
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(2600)
        antes = dict(vistos); n1 = pg.evaluate("JSON.stringify(Object.fromEntries(CAPAS.map(c => [c.id, estado[c.id].elementos.size]).filter(x => x[1])))")
        guardados = pg.evaluate("memoria.cuantos()")
        pg.reload(); pg.wait_for_selector("#lista li")
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(1500)
        n2 = pg.evaluate("JSON.stringify(Object.fromEntries(CAPAS.map(c => [c.id, estado[c.id].elementos.size]).filter(x => x[1])))")
        nuevos = {k: vistos.get(k, 0) - antes.get(k, 0) for k in ("interpreter", "wikipedia", "commons", "panoramax", "geoportal.valencia", "wfsBU") if vistos.get(k, 0) - antes.get(k, 0)}
        print(nombre, "memoria:", guardados, "trozos | mismos elementos tras recargar:", n1 == n2, "| peticiones nuevas a servicios:", nuevos or "ninguna", "| cámaras:", pg.evaluate("camaras.size"))
        # una zona nueva sí se pide, y lo guardado caduca
        pg.evaluate(f"mapa.setView([{LAT + 0.05}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(1500)
        print(nombre, "zona nueva pide:", {k: vistos.get(k, 0) - antes.get(k, 0) for k in ("interpreter", "wikipedia") if vistos.get(k, 0) - antes.get(k, 0)},
              "| caducado no vale:", pg.evaluate(f"memoria.leer([claveMemoria(CAPA.antenas, pasoDe(13), Math.floor({LAT} / pasoDe(13)) + ':' + Math.floor({LON} / pasoDe(13)))], 1).then(r => r[0] === null)"),
              "| vigente sí:", pg.evaluate(f"memoria.leer([claveMemoria(CAPA.antenas, pasoDe(13), Math.floor({LAT} / pasoDe(13)) + ':' + Math.floor({LON} / pasoDe(13)))], 7 * DIA).then(r => Array.isArray(r[0]) && r[0].length)"))
        # vaciar desde el panel de capas
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(600)
        pg.evaluate("document.getElementById('capas').open = true"); pg.wait_for_timeout(300)
        print(nombre, "panel memoria:", pg.inner_text("#memoria-estado")[:60])
        a0 = vistos.get("interpreter", 0)
        pg.evaluate("document.getElementById('memoria-vaciar').click()"); pg.wait_for_timeout(1800)
        print(nombre, "tras vaciar:", pg.inner_text("#memoria-estado")[:40], "| se vuelve a pedir:", vistos.get("interpreter", 0) > a0, "| elementos:", pg.evaluate("estado.antenas.elementos.size"))
        # buscar una capa por su nombre
        pg.fill("#buscar-capa", "farol"); pg.wait_for_timeout(150)
        print(nombre, "buscar capa 'farol':", pg.evaluate("[...document.querySelectorAll('#capas label.casilla')].filter(l => l.offsetParent).map(l => l.textContent.trim().slice(0, 30)).join(' / ')"), "| grupos visibles:", pg.evaluate("[...document.querySelectorAll('#capas details.grupo-de-capas')].filter(g => g.offsetParent).length"))
        if nombre == "escritorio": pg.screenshot(path="escritorio-buscar-capa.png")
        pg.fill("#buscar-capa", ""); pg.wait_for_timeout(150)
        print(nombre, "sin búsqueda vuelven:", pg.evaluate("[...document.querySelectorAll('#capas label.casilla')].filter(l => l.offsetParent).length > 10 && !document.getElementById('capas').classList.contains('buscando')"))
        pg.evaluate("document.getElementById('capas').open = false")

        # ===== tira de capas encendidas =====
        print(nombre, "tira:", pg.evaluate("[...document.querySelectorAll('#tira-capas button')].map(b => b.textContent.trim() + (b.getAttribute('aria-pressed') === 'true' ? '' : ' (oculta)')).join(' · ')"))
        pg.click("#tira-capas button:has-text('Antenas')"); pg.wait_for_timeout(300)
        print(nombre, "ocultar antenas desde la tira:", pg.evaluate("JSON.stringify({activa: capasActivas.has('antenas'), enMapa: mapa.hasLayer(estado.antenas.grupo), casilla: document.getElementById('dato-antenas').checked, ficha: document.querySelector('#tira-capas button[aria-pressed=false] span').textContent})"))
        pg.click("#tira-capas button:has-text('Antenas')"); pg.wait_for_timeout(600)
        print(nombre, "y volver a mostrarla:", pg.evaluate("JSON.stringify({activa: capasActivas.has('antenas'), enMapa: mapa.hasLayer(estado.antenas.grupo), n: estado.antenas.elementos.size})"))
        pg.click("#tira-capas button:has-text('Sitios')"); pg.wait_for_timeout(200)
        print(nombre, "ocultar sitios:", pg.evaluate("!mapa.hasLayer(grupo) && !document.getElementById('capa-sitios').checked"))
        pg.click("#tira-capas button:has-text('Sitios')"); pg.wait_for_timeout(200)
        plegar(); pg.screenshot(path=f"{nombre}-tira.png"); pg.evaluate("(esMovil() ? ponerHoja('media') : 0)")

        # ===== el mapa no se rehace al moverlo =====
        pg.evaluate("window.__rehechos = 0; const o = grupo.clearLayers.bind(grupo); grupo.clearLayers = function () { window.__rehechos++; return o(); }; document.getElementById('f-vista').checked = true; filtrar();")
        pg.evaluate(f"mapa.setView([{LAT + 0.004}, {LON + 0.004}], 16, {{animate: false}})"); pg.wait_for_timeout(500)
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(500)
        print(nombre, "puntos rehechos al mover (antes, uno por movimiento):", pg.evaluate("window.__rehechos"), "| lista sigue a la vista:", pg.evaluate("visibles.length < enMapa.length && visibles.length > 0"), "| resumen:", pg.evaluate("document.getElementById('resumen-filtros').textContent"))
        pg.evaluate("document.getElementById('f-nota').value = 60; filtrar()"); pg.wait_for_timeout(200)
        print(nombre, "al cambiar un filtro sí:", pg.evaluate("window.__rehechos"), "| en mapa:", pg.evaluate("enMapa.length + ' de ' + candidatos.length + ', capas en el grupo: ' + grupo.getLayers().length"))
        pg.evaluate("document.getElementById('f-nota').value = 40; document.getElementById('f-vista').checked = false; filtrar()")
        # rótulo de un sitio al pasar el ratón (uno solo para todos)
        if nombre == "escritorio":
            x, y = punto(LAT, LON); pg.mouse.move(x + 60, y + 60); pg.wait_for_timeout(120); pg.mouse.move(x + 2, y + 2); pg.wait_for_timeout(120); pg.mouse.move(x, y); pg.wait_for_timeout(300)
            print(nombre, "rótulo de sitio:", pg.evaluate("(document.querySelector('.leaflet-tooltip') || {}).textContent"))
            pg.mouse.move(x + 200, y + 200); pg.wait_for_timeout(200)

        # ===== asa del panel (ordenador) y atajo del buscador =====
        if nombre == "escritorio":
            x0 = punto(LAT, LON)[0]; ancho0 = pg.evaluate("document.getElementById('mapa').offsetWidth")
            pg.click("#asa-panel"); pg.wait_for_timeout(300)
            x1 = punto(LAT, LON)[0]
            print(nombre, "panel escondido:", pg.evaluate("getComputedStyle(document.getElementById('panel')).display"), "| mapa", ancho0, "->", pg.evaluate("document.getElementById('mapa').offsetWidth"), "| el punto no se mueve:", abs(x0 - x1) < 1.5, "| recordado:", pg.evaluate("localStorage.getItem('osintmaps.panel.v1')"))
            pg.screenshot(path="escritorio-sin-panel.png")
            pg.mouse.click(*punto(LAT, LON)); pg.wait_for_timeout(500)
            print(nombre, "al abrir un sitio vuelve el panel:", pg.evaluate("getComputedStyle(document.getElementById('panel')).display + ' ' + !document.getElementById('ficha').hidden"), "| punto en su sitio:", abs(punto(LAT, LON)[0] - x0) < 1.5)
            pg.evaluate("volverALista(); localStorage.removeItem('osintmaps.panel.v1')")
        pg.evaluate("document.activeElement.blur()"); pg.keyboard.press("/"); pg.wait_for_timeout(100)
        print(nombre, "«/» lleva al buscador:", pg.evaluate("document.activeElement.id"), "| no escribe la barra:", pg.input_value("#buscar-texto") == "")
        pg.evaluate("document.activeElement.blur()")

        # ===== parcelas: se dibujan una vez y se guardan =====
        v0 = vistos.get("wfsCP", 0)
        pg.evaluate("document.getElementById('capa-parcelas').checked = true; document.getElementById('capa-parcelas').dispatchEvent(new Event('change'))"); pg.wait_for_timeout(900)
        d1 = pg.evaluate("[refcatsDibujadas.size, capaParcelas.getLayers().length, teselasParcelas.size].join(',')")
        pg.evaluate(f"mapa.panBy([40, 30], {{animate: false}})"); pg.wait_for_timeout(400)
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(400)
        print(nombre, "parcelas dibujadas,capas,teselas:", d1, "-> tras mover:", pg.evaluate("[refcatsDibujadas.size, capaParcelas.getLayers().length].join(',')"), "| pedidas a Catastro:", vistos.get("wfsCP", 0) - v0, "| leyenda:", pg.inner_text("#leyenda").replace("\n", " | ")[:70])
        pg.evaluate("document.getElementById('capa-vallas').checked = true; document.getElementById('capa-vallas').dispatchEvent(new Event('change'))"); pg.wait_for_timeout(1200)
        print(nombre, "vallas y puertas:", pg.evaluate("JSON.stringify({vias: viasDibujadas.size, capas: capaVallas.getLayers().length, puntos: capaVallas.getLayers().filter(c => c instanceof Puntos).map(c => c._latlngs.length), lineas: capaVallas.getLayers().filter(c => c instanceof L.Polyline).length})"))
        plegar(); pg.wait_for_timeout(300); pg.screenshot(path=f"{nombre}-acceso.png"); pg.evaluate("(esMovil() ? ponerHoja('media') : 0)")
        # clic en una parcela: sigue abriendo su ficha aunque el dibujo vaya junto
        x, y = punto(LAT + 0.00127, LON + 0.0007); pg.mouse.click(x, y); pg.wait_for_timeout(700)
        print(nombre, "clic en parcela:", (pg.inner_text(".leaflet-popup-content") if pg.locator(".leaflet-popup-content").count() else "sin ficha").replace("\n", " | ")[:90])
        pg.evaluate("mapa.closePopup(); document.getElementById('capa-vallas').checked = false; document.getElementById('capa-vallas').dispatchEvent(new Event('change'))"); pg.wait_for_timeout(200)
        print(nombre, "vallas apagadas:", pg.evaluate("viasDibujadas.size + capaVallas.getLayers().length"))
        v1 = vistos.get("wfsCP", 0)
        pg.reload(); pg.wait_for_selector("#lista li"); pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(900)
        print(nombre, "parcelas tras recargar:", pg.evaluate("refcatsDibujadas.size"), "| peticiones nuevas a Catastro:", vistos.get("wfsCP", 0) - v1)
        pg.evaluate(f"mapa.setZoom(14, {{animate: false}}); 0"); pg.wait_for_timeout(300)
        print(nombre, "de lejos se quitan:", pg.evaluate("refcatsDibujadas.size + capaParcelas.getLayers().length"))
        pg.evaluate("document.getElementById('capa-parcelas').checked = false; document.getElementById('capa-parcelas').dispatchEvent(new Event('change'))")
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(500)

        # ===== peticiones que ya no hacen falta se tiran =====
        # (el retraso se pone en la propia página: así las peticiones esperan de verdad en paralelo)
        pg.evaluate("memoria.vaciar()"); pg.wait_for_timeout(100)
        pg.evaluate("window.__f = window.fetch; window.fetch = (u, o) => (String(u).includes('wfsBU') ? new Promise((r) => setTimeout(r, 1500)).then(() => window.__f(u, o)) : window.__f(u, o)); 0")
        b0 = vistos.get("wfsBU", 0)
        pg.evaluate(f"vaciar(CAPA.edificios); mapa.setView([{LAT + 0.1}, {LON}], 18, {{animate: false}}); 0"); pg.wait_for_timeout(450)
        zona1 = pg.evaluate("estado.edificios.cargando")
        pg.evaluate(f"mapa.setView([{LAT - 0.1}, {LON}], 18, {{animate: false}}); 0"); pg.wait_for_timeout(450)
        zona2 = pg.evaluate("teselasQueFaltan(CAPA.edificios).faltan.length + [...estado.edificios.teselas].length")
        pg.wait_for_function("!estado.edificios.cargando", timeout=30000)
        print(nombre, "edificios: trozos de la 1.ª zona:", zona1, "| pedidos de verdad en total:", vistos.get("wfsBU", 0) - b0, "(3 que ya iban en curso + los de la 2.ª zona) | error:", pg.evaluate("estado.edificios.error"), "| teselas dadas por cargadas:", pg.evaluate("estado.edificios.teselas.size"))
        pg.evaluate("window.fetch = window.__f; 0")

        # ===== Overpass: si el primer servidor se calla, a los 8 s se pregunta también al siguiente =====
        modo["osm"] = "primero-callado"
        pg.evaluate("servidorOSM = 0; memoria.vaciar()"); pg.wait_for_timeout(100)
        for k in ("overpass-api.de", "overpass.private.coffee"): vistos.pop(k, None)
        t0 = time.time()
        pg.evaluate(f"for (const id of ['antenas', 'tren', 'farolas', 'policia', 'canteras', 'industria', 'energia']) if (capasActivas.has(id)) document.getElementById('dato-' + id).click(); vaciar(CAPA.camaras); vaciar(CAPA.antenas); document.getElementById('dato-antenas').click(); mapa.setView([{LAT}, {LON}], 17, {{animate: false}})")
        pg.wait_for_function("estado.antenas.elementos.size > 0 && !estado.antenas.cargando", timeout=20000)
        print(nombre, f"Overpass con el primero callado: llegó en {time.time() - t0:.1f} s", "| servidor preferido ahora:", pg.evaluate("OVERPASS[servidorOSM]").split("/")[2], "| preguntas:", {k: vistos.get(k, 0) for k in ("overpass-api.de", "overpass.private.coffee")})
        modo["osm"] = "bien"
        pg.evaluate("servidorOSM = 0")
        for id_ in ("tren", "farolas", "policia"): pg.evaluate(f"if (!capasActivas.has('{id_}')) document.getElementById('dato-{id_}').click()")
        pg.wait_for_timeout(1200)

        # ===== calidad de imagen =====
        modo.update(icv="bien", vlc="bien"); import re as _re
        pg.evaluate("volverALista(); (esMovil() ? ponerHoja('media') : 0)")
        print(nombre, "fondos:", pg.evaluate("[...document.getElementById('capa-fondo').options].slice(0, 7).map(o => o.value).join(',')"), "| elegido:", pg.evaluate("document.getElementById('capa-fondo').value"), "| zoom máximo:", pg.evaluate("mapa.getMaxZoom()"), "| densidad:", pg.evaluate("DENSIDAD"))
        # en la provincia, de cerca: ICV; de lejos: PNOA
        teselas.clear(); pg.evaluate(f"mapa.setView([{LAT + 0.03}, {LON + 0.03}], 17, {{animate: false}}); 0"); pg.wait_for_timeout(900)
        cerca = {k: v for k, v in teselas.items() if not k.endswith("ultima")}
        teselas.clear(); pg.evaluate(f"mapa.setView([{LAT + 0.03}, {LON + 0.03}], 12, {{animate: false}}); 0"); pg.wait_for_timeout(900)
        print(nombre, "de cerca en la provincia:", cerca, "| de lejos:", {k: v for k, v in teselas.items() if not k.endswith("ultima")})
        # fuera de la zona del ICV (la tesela llega transparente): se pasa al PNOA
        modo["icv"] = "fuera"; teselas.clear(); pg.evaluate(f"mapa.setView([{LAT + 0.06}, {LON + 0.06}], 17, {{animate: false}}); 0"); pg.wait_for_timeout(1200)
        print(nombre, "ICV sin cobertura:", {k: v for k, v in teselas.items() if not k.endswith("ultima")}, "| teselas visibles con foto del PNOA:", pg.evaluate("[...document.querySelectorAll('#mapa .leaflet-tile-pane img.leaflet-tile')].filter(i => /pnoa-ma/.test(i.src)).length > 0"))
        modo["icv"] = "bien"
        # en València ciudad: la foto municipal; donde no llega, la del ICV
        teselas.clear(); pg.evaluate("mapa.setView([39.4699, -0.3763], 19, {animate: false}); 0"); pg.wait_for_timeout(1200)
        ciudad = {k: v for k, v in teselas.items() if not k.endswith("ultima")}; ultima = teselas.get("vlc-ultima", "")
        modo["vlc"] = "fuera"; teselas.clear(); pg.evaluate("mapa.setView([39.4799, -0.3763], 19, {animate: false}); 0"); pg.wait_for_timeout(1200)
        print(nombre, "en València ciudad:", ciudad, "| nivel pedido:", (_re.search(r"/tile/(\d+)/", ultima) or [0, "?"])[1], "| borde sin foto municipal:", {k: v for k, v in teselas.items() if not k.endswith("ultima")})
        modo["vlc"] = "bien"
        # foto antigua de la ciudad en la comparación
        teselas.clear(); pg.evaluate("ponerHistorica('ciudad-1980'); 0"); pg.wait_for_timeout(900)
        print(nombre, "comparar con 1980 (ciudad):", teselas.get("vlc-antigua", 0), "teselas |", (teselas.get("vlc-antigua-ultima") or "")[45:95], "| rótulo:", pg.inner_text("#cortina-etiqueta"), "| grupo en la lista:", pg.evaluate("document.querySelector('#capa-historica optgroup').label + ' ' + document.querySelectorAll('#capa-historica optgroup option').length"))
        pg.evaluate("ponerHistorica(''); 0")
        # ficha de un punto de la ciudad: la portada sale de la foto municipal
        teselas.clear(); pg.evaluate("abrirElemento(puntoDe(L.latLng(39.4699, -0.3763)), false); 0"); pg.wait_for_timeout(1200)
        print(nombre, "portada en la ciudad:", "municipal" if "FotoAerea_2025/MapServer/export" in pg.evaluate("document.querySelector('#ficha-elemento .portada img').src") else pg.evaluate("document.querySelector('#ficha-elemento .portada img').src")[:60], "| px pedidos:", (_re.search(r"size=(\d+)", teselas.get("vlc-export-ultima", "")) or [0, "?"])[1])
        # visor: la ortofoto es un mapa que se acerca; en la ciudad trae las fotos y planos municipales
        pg.click("#ficha-elemento .vistas button:nth-child(1)"); pg.wait_for_timeout(900)
        z0 = pg.evaluate("visor.mapa.getZoom()")
        print(nombre, "visor con mapa:", pg.locator("#visor .mapa-visor.leaflet-container").count(), "| zoom", z0, "| años:", pg.locator("#visor .opciones button").count(), "| con planos:", pg.locator("#visor .opciones button:has-text('Plano de 1738')").count(), "| pie:", pg.inner_text("#visor .pie-foto")[:95])
        teselas.clear(); pg.click("#visor .opciones button:has-text('1980 ciudad')"); pg.wait_for_timeout(900)
        print(nombre, "visor, 1980 ciudad:", teselas.get("vlc-antigua", 0), "teselas | pie:", pg.inner_text("#visor .pie-foto")[:40])
        pg.click("#visor .miniaturas button:has-text('Muy cerca')"); pg.wait_for_timeout(500)
        print(nombre, "visor, muy cerca: zoom", pg.evaluate("visor.mapa.getZoom()"), "| entero:", pg.evaluate("Number.isInteger(visor.mapa.getZoom())"))
        # visor: una foto se puede acercar, y al acercar se pide la versión grande
        pg.click("#visor .pestanas button[data-modo=fotos]"); pg.wait_for_timeout(900)
        antes = pg.evaluate("document.querySelector('#visor .lienzo img').src")
        caja = pg.evaluate("(() => { const r = document.querySelector('#visor .lienzo img').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        pg.mouse.move(caja[0], caja[1]); pg.mouse.wheel(0, -700); pg.wait_for_timeout(700)
        print(nombre, "foto ampliada:", pg.evaluate("document.querySelector('#visor .lienzo img').style.transform")[:48], "| pasa a la grande:", pg.evaluate("document.querySelector('#visor .lienzo img').src") != antes, pg.evaluate("document.querySelector('#visor .lienzo img').src")[-40:])
        pg.mouse.dblclick(caja[0], caja[1]); pg.wait_for_timeout(200)
        print(nombre, "doble clic vuelve:", pg.evaluate("document.querySelector('#visor .lienzo img').style.transform") == "")
        pg.click("#visor .pestanas button[data-modo=calle]"); pg.wait_for_timeout(900)
        pg.click("#visor .opciones button:has-text('360')"); pg.wait_for_timeout(300)
        print(nombre, "Panoramax 360:", pg.evaluate("document.querySelector('#visor iframe').src")[:48])
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        print(nombre, "visor cerrado sin restos:", pg.evaluate("visor === null && !document.querySelector('.mapa-visor')"))
        pg.evaluate("cerrarElemento()")
        # ajustes de la foto
        pg.evaluate("document.getElementById('capas').open = true; document.getElementById('ajustes-foto').open = true"); pg.wait_for_timeout(100)
        pg.evaluate("(() => { const b = document.getElementById('aj-brillo'); b.value = 130; b.dispatchEvent(new Event('input')); const e = document.getElementById('aj-enfoque'); e.checked = true; e.dispatchEvent(new Event('change')); })()"); pg.wait_for_timeout(200)
        print(nombre, "ajustes:", pg.evaluate("getComputedStyle(mapa.getPane('tilePane')).filter"), "| enfoque en tesela:", pg.evaluate("getComputedStyle(document.querySelector('#mapa .leaflet-tile-pane img.leaflet-tile')).filter"), "| rótulo:", pg.inner_text("#ajustes-foto summary"), "| doble detalle visible:", pg.evaluate("!document.getElementById('fila-nitidez').hidden"))
        if nombre == "escritorio": pg.screenshot(path="escritorio-ajustes.png")
        pg.evaluate("document.getElementById('capa-fondo').value = 'mtn'; document.getElementById('capa-fondo').dispatchEvent(new Event('change'))"); pg.wait_for_timeout(200)
        print(nombre, "en un mapa dibujado no se aplica:", pg.evaluate("getComputedStyle(mapa.getPane('tilePane')).filter"))
        pg.evaluate("document.getElementById('capa-fondo').value = 'google'; document.getElementById('capa-fondo').dispatchEvent(new Event('change'))"); pg.wait_for_timeout(600)
        print(nombre, "fondo Google:", teselas.get("google", 0) > 0, "| guardado:", pg.evaluate("localStorage.getItem('osintmaps.fondo.v2')"))
        pg.evaluate("document.getElementById('capa-fondo').value = 'auto'; document.getElementById('capa-fondo').dispatchEvent(new Event('change')); document.getElementById('aj-restablecer').click(); document.getElementById('capas').open = false")
        print(nombre, "restablecido:", pg.evaluate("getComputedStyle(mapa.getPane('tilePane')).filter + ' ' + document.documentElement.classList.contains('enfocar')"))
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}}); 0"); pg.wait_for_timeout(600)

        # modo oscuro: se cambia con el botón, se recuerda y no toca los colores del mapa
        antes = pg.evaluate("[document.documentElement.dataset.tema, getComputedStyle(document.getElementById('panel')).backgroundColor].join(' ')")
        pg.evaluate("volverALista()"); pg.evaluate("(esMovil() ? ponerHoja('media') : 0)")
        pg.click("#tema"); pg.wait_for_timeout(200)
        print(nombre, "tema:", antes, "->", pg.evaluate("[document.documentElement.dataset.tema, getComputedStyle(document.getElementById('panel')).backgroundColor, getComputedStyle(document.getElementById('buscar-texto')).color, JSON.parse(localStorage.getItem('osintmaps.tema.v1')), document.getElementById('tema').title].join(' | ')"))
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 17, {{animate: false}})"); pg.wait_for_timeout(700)
        pg.evaluate("abrirElemento([...estado.antenas.elementos.values()][0])"); pg.wait_for_timeout(700)
        pg.screenshot(path=f"{nombre}-oscuro.png")
        if nombre == "escritorio":
            pg.evaluate("cerrarElemento(); document.getElementById('capas').open = true"); pg.wait_for_timeout(300); pg.screenshot(path="escritorio-capas-oscuro.png")
        pg.reload(); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(300)
        print(nombre, "tras recargar sigue:", pg.evaluate("document.documentElement.dataset.tema"))
        pg.evaluate("localStorage.removeItem('osintmaps.tema.v1')")
        ctx.close()
    # ===== pantalla densa (un móvil o un portátil moderno): se pide el doble de detalle =====
    import re as _re
    modo.update(icv="bien", vlc="bien"); teselas.clear()
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2); pg = ctx.new_page(); pg.route("**/*", ruta)
    pg.on("pageerror", lambda e: errores.append(f"denso EXC: {e}"))
    pg.goto("http://127.0.0.1:8776/#mapa=18/39.46990/-0.37630"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(1500)
    u = teselas.get("vlc-ultima", "")
    print("denso: densidad", pg.evaluate("DENSIDAD"), "| nivel pedido a zoom 18:", (_re.search(r"/tile/(\d+)/", u) or [0, "?"])[1], "| tesela en pantalla:", pg.evaluate("document.querySelector('#mapa .leaflet-tile-pane img.leaflet-tile').offsetWidth"), "px | casilla visible:", pg.evaluate("!document.getElementById('fila-nitidez').hidden && document.getElementById('aj-nitidez').checked"))
    teselas.clear(); pg.evaluate("mapa.setZoom(22, {animate: false}); 0"); pg.wait_for_timeout(1200)
    print("denso: a zoom 22 se pide el nivel", (_re.search(r"/tile/(\d+)/", teselas.get("vlc-ultima", "")) or [0, "ninguno nuevo"])[1], "(el más detallado es el 21) | teselas:", {k: v for k, v in teselas.items() if not k.endswith("ultima")})
    pg.evaluate("mapa.setView([39.4699, -0.3763], 18, {animate: false}); ponerHistorica('PNOA2015'); 0"); pg.wait_for_timeout(1000)
    print("denso: foto antigua por WMS a", pg.evaluate("(/WIDTH=(\\d+)/i.exec(document.querySelector('.leaflet-historico-pane img.leaflet-tile').src) || [0, '?'])[1]"), "px por tesela de 256")
    pg.evaluate("ponerHistorica(''); document.getElementById('aj-nitidez').click(); 0"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(800)
    print("denso: al desmarcar el doble detalle:", pg.evaluate("DENSIDAD"), "| tesela:", pg.evaluate("document.querySelector('#mapa .leaflet-tile-pane img.leaflet-tile').offsetWidth"), "px")
    pg.evaluate("localStorage.removeItem('osintmaps.nitidez.v1')")
    ctx.close()
    b.close()
print("ERRORES:", errores or "ninguno")
