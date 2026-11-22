"""La versión web estática (GitHub Pages): sin el programa detrás."""
import functools, http.server, json, shutil, sys, threading
import pathlib, zipfile
sys.path.insert(0, str(pathlib.Path.cwd().parent))            # el paquete se usa tal cual está en el repositorio
if not pathlib.Path("datos").exists(): zipfile.ZipFile("datos.zip").extractall(".")      # datos de prueba
from pathlib import Path
from osintmaps import cli
from playwright.sync_api import sync_playwright
datos = Path("datos-estatico").resolve(); shutil.rmtree(datos, ignore_errors=True); shutil.copytree("datos", datos)
for f in ("marcas.json",): (datos / f).unlink(missing_ok=True)
g = json.load(open(datos / "candidatos.geojson")); LON, LAT = g["features"][0]["geometry"]["coordinates"][:2]
(datos / "marcadores.json").write_text(json.dumps({"m-pc": {"lat": LAT + 0.0005, "lng": LON, "type": "spot", "note": "Publicado desde el PC", "created": 1795000000000, "updated": 1795000000000}}), encoding="utf-8")
(datos / "capa-dgt.geojson").write_text(json.dumps(cli._geojson_de_puntos([{"id": "dgt-9", "nombre": "A-7 km 300", "lat": LAT - 0.001, "lon": LON + 0.001, "imagen": "https://etraffic.dgt.es/camarasEtraffic/9.jpg"}])), encoding="utf-8")
sitio = Path("sitio-estatico").resolve(); shutil.rmtree(sitio, ignore_errors=True)
print("copiados:", cli.crear_sitio(sitio, datos, con_notas=True))
class Mudo(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8777), functools.partial(Mudo, directory=str(sitio)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
NM = Path("node_modules"); errores, posts = [], []
def ruta(route):
    u = route.request.url
    if "unpkg.com/leaflet@" in u: return route.fulfill(path=str(NM / "leaflet/dist" / u.rsplit("/", 1)[-1]))
    if "unpkg.com/leaflet.markercluster@" in u: return route.fulfill(path=str(NM / "leaflet.markercluster/dist" / u.rsplit("/", 1)[-1]))
    if "127.0.0.1" in u:
        if route.request.method == "POST": posts.append(u)
        return route.continue_()
    return route.abort()
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 800}, has_touch=True); pg = ctx.new_page(); pg.route("**/*", ruta)
    pg.on("pageerror", lambda e: errores.append(f"EXC: {e}"))
    pg.on("console", lambda m: errores.append(m.text[:160]) if m.type == "error" and "ERR_FAILED" not in m.text and "404" not in m.text and "501" not in m.text else None)
    pg.goto("http://127.0.0.1:8777/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(3200)
    print("sin servidor:", pg.evaluate("conServidor === false && document.documentElement.classList.contains('sin-servidor')"), "| sitios:", pg.evaluate("candidatos.length"), "| marcador publicado:", pg.evaluate("Object.values(marcadores).map(m => m.note).join(',')"),
          "| capa DGT:", pg.evaluate("estado.dgt.elementos.size"), "| manifiesto:", pg.evaluate("document.querySelector('link[rel=manifest]').href.split('/').pop()"))
    # anotar algo: se queda en el navegador, sin intentar guardarlo en ningún servidor
    pg.evaluate(f"nuevoMarcador(L.latLng({LAT}, {LON + 0.0006}), 'spot', 'Hecho en el móvil'); 0"); pg.wait_for_timeout(1200)
    print("marcador nuevo:", pg.evaluate("Object.values(marcadores).length"), "| envíos al servidor:", len(posts), "| aviso:", repr(pg.evaluate("document.getElementById('estado-marcas').textContent")))
    pg.reload(); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(1500)
    print("tras recargar siguen los dos:", sorted(pg.evaluate("Object.values(marcadores).map(m => m.note)")))
    # lo que necesita el programa del PC lo dice, sin romper nada
    pg.evaluate("document.getElementById('dato-aviones').click(); 0"); pg.wait_for_timeout(1200)
    print("aviones:", pg.evaluate("JSON.stringify({error: estado.aviones.error, mensaje: estado.aviones.mensaje})"), "| ficha:", pg.evaluate("document.querySelector('#tira-capas button.falla') ? document.querySelector('#tira-capas button.falla').title : ''")[:70])
    b.close()
print("ERRORES:", errores or "ninguno")
