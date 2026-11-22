"""Prueba de la maqueta 3D con un servicio I3S simulado: dos niveles de detalle, un trozo de provincia que falla,
que los puntos y la ruta se ven encima, y encender y apagar."""
exec(open("maps9.py", encoding="utf-8").read())
import io, math, struct
from PIL import Image
ruta_9 = ruta
X0 = LON * 20037508.342789244 / 180; Y0 = math.log(math.tan(math.pi / 4 + math.radians(LAT) / 2)) * 6378137.0
def jpeg(color):
    b = io.BytesIO(); Image.new("RGB", (64, 64), color).save(b, "JPEG", quality=92); return b.getvalue()
def cuadrado(lado, alto):
    v = [(-lado, -lado, alto), (lado, -lado, alto), (lado, lado, alto), (-lado, -lado, alto), (lado, lado, alto), (-lado, lado, alto)]
    uv = [(0, 1), (1, 1), (1, 0), (0, 1), (1, 0), (0, 0)]
    return struct.pack("<II", 6, 1) + b"".join(struct.pack("<3f", *p) for p in v) + b"".join(struct.pack("<2f", *p) for p in uv) + struct.pack("<Q", 0) + struct.pack("<II", 0, 1)
Q = [0, 0, 0, 1]
NODOS = [
    {"index": 0, "obb": {"center": [X0, Y0, 0], "halfSize": [50000, 50000, 2000], "quaternion": Q}, "children": [1]},
    {"index": 1, "lodThreshold": 400000, "obb": {"center": [X0, Y0, 40], "halfSize": [400, 400, 30], "quaternion": Q}, "children": [2],
     "mesh": {"material": {"resource": 1}, "geometry": {"resource": 1, "vertexCount": 6}}},
    {"index": 2, "lodThreshold": 3000000, "obb": {"center": [X0, Y0, 40], "halfSize": [150, 150, 30], "quaternion": Q},
     "mesh": {"material": {"resource": 2}, "geometry": {"resource": 2, "vertexCount": 6}}},
]
GEOM = {"1": cuadrado(400, 0), "2": cuadrado(150, 5)}
FOTO = {"1": jpeg((20, 200, 40)), "2": jpeg((230, 20, 200))}
pedidos = {}
def ruta(route):
    u = route.request.url
    if "gvagis.icv.gva.es" in u:
        zona = re.search(r"Malla3D_(\w+)/", u).group(1); pedidos[zona] = pedidos.get(zona, 0) + 1
        if zona == "Sur": return route.fulfill(status=404, headers=CORS, body=b"no")
        if "/nodepages/" in u:
            nodos = NODOS if zona == "Centro" else [{"index": 0, "obb": {"center": [0, 0, 0], "halfSize": [1, 1, 1], "quaternion": Q}}]
            return route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps({"nodes": nodos}))
        m = re.search(r"/nodes/(\d+)/(geometries|textures)/0", u)
        if m and m.group(2) == "geometries": return route.fulfill(status=200, content_type="application/octet-stream", headers=CORS, body=GEOM[m.group(1)])
        if m: return route.fulfill(status=200, content_type="image/jpeg", headers=CORS, body=FOTO[m.group(1)])
        return route.fulfill(status=404, headers=CORS, body=b"")
    return ruta_9(route)

def color_en(pg, x, y):
    im = Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
    return im.getpixel((int(x), int(y)))
def parecido(c, d, tol=70): return all(abs(a - b) <= tol for a, b in zip(c, d))
VERDE, MAGENTA = (20, 200, 40), (230, 20, 200)
errores = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--enable-webgl"])
    for nombre, vp in (("escritorio", {"width": 1360, "height": 860}), ("movil", {"width": 390, "height": 800})):
        pedidos.clear()
        ctx = b.new_context(viewport=vp, has_touch=(nombre == "movil")); pg = ctx.new_page(); pg.route("**/*", ruta)
        def consola(m, nombre=nombre):
            if m.type in ("error", "warning") and not any(s in m.text for s in ("ERR_FAILED", "GPU stall", "GL Driver", "status of 404", "Automatic fallback to software")):
                errores.append(f"{nombre} {m.type}: {m.text[:300]}")
        pg.on("console", consola); pg.on("pageerror", lambda e, nombre=nombre: errores.append(f"{nombre} EXC: {e}"))
        pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(600)
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 16, {{animate: false}})"); pg.wait_for_timeout(400)
        print(nombre, "botón de la maqueta visible en 2D:", pg.is_visible("#boton-malla"))
        pg.click("#boton-3d"); pg.wait_for_timeout(6000)
        pg.evaluate(f"mapa3d.jumpTo({{ center: [{LON}, {LAT}], zoom: 15 }}); 0"); pg.wait_for_timeout(1500)     # la vista inicial depende de cuándo acabe de cargar la lista
        caja = pg.evaluate("(() => { const r = mapa3d.getCanvas().getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        def centro():
            p = pg.evaluate("(() => { const p = mapa3d.project(mapa3d.getCenter()); return [p.x, p.y]; })()")
            return caja[0] + p[0] + 70, caja[1] + p[1] + 34      # un poco al lado: en el centro justo hay un punto del mapa
        def esperar(cond, ms=9000):
            try: pg.wait_for_function(cond, timeout=ms); return True
            except Exception: return False
        esperar("malla && malla.estado().pintados > 0")
        cx, cy = centro()
        print(nombre, "en 3D:", pg.evaluate("en3D()"), "| capa:", pg.evaluate("!!mapa3d.getLayer('malla')"), "| botón:", pg.is_visible("#boton-malla"), pg.get_attribute("#boton-malla", "aria-pressed"),
              "| estado:", pg.evaluate("JSON.stringify(malla.estado())"), "| relieve x:", pg.evaluate("mapa3d.getTerrain().exaggeration"), "| zoom:", pg.evaluate("mapa3d.getZoom().toFixed(2)"))
        c = color_en(pg, cx, cy); print(nombre, "  centro a z15:", c, "→ nodo grande (verde):", parecido(c, VERDE))
        if not parecido(c, VERDE): errores.append(f"{nombre}: a z15 el centro no es verde: {c}")
        pg.evaluate("mapa3d.jumpTo({ zoom: 16.7 }); 0"); esperar("malla.estado().listos >= 2"); pg.wait_for_timeout(1200)
        cx, cy = centro(); c = color_en(pg, cx, cy); print(nombre, "  centro a z16.7:", c, "→ nodo fino (magenta):", parecido(c, MAGENTA), "| estado:", pg.evaluate("JSON.stringify(malla.estado())"))
        if not parecido(c, MAGENTA): errores.append(f"{nombre}: a z16.7 el centro no es magenta: {c}")
        print(nombre, "  prismas escondidos:", esperar("mapa3d.getLayoutProperty('edificios', 'visibility') === 'none'", 6000), pg.evaluate("mapa3d.getLayoutProperty('edificios', 'visibility')"), "| peticiones por zona:", dict(pedidos))
        # La ruta y sus extremos se tienen que ver encima de la maqueta
        pg.evaluate(f"rutaDesde(L.latLng({LAT - 0.0003}, {LON - 0.0006})); rutaHasta(L.latLng({LAT + 0.0004}, {LON + 0.0004}), 'Destino'); 0"); pg.wait_for_timeout(3500)
        pg.evaluate(f"mapa3d.jumpTo({{ center: [{LON}, {LAT}], zoom: 16.7 }}); 0"); pg.wait_for_timeout(2500)
        d = pg.evaluate(f"(() => {{ const p = mapa3d.project([{LON + 0.0004}, {LAT + 0.0004}]); return [p.x, p.y]; }})()")
        c = color_en(pg, d[0] + caja[0], d[1] + caja[1]); rojo = parecido(c, (217, 48, 37), 60)
        print(nombre, "  destino de la ruta encima de la maqueta:", c, rojo, "| tramos:", pg.evaluate("mapa3d.getSource('ruta').serialize().data.features.length"))
        if not rojo: errores.append(f"{nombre}: el extremo de la ruta no se ve sobre la maqueta: {c}")
        pg.evaluate("quitarRuta(); 0")
        # Apagar y encender
        pg.evaluate("document.getElementById('boton-malla').click()"); pg.wait_for_timeout(1500)
        cx, cy = centro(); c = color_en(pg, cx, cy)
        print(nombre, "  apagada: capa", pg.evaluate("!!mapa3d.getLayer('malla')"), "| centro:", c, "| botón:", pg.get_attribute("#boton-malla", "aria-pressed"), "| relieve x:", pg.evaluate("mapa3d.getTerrain().exaggeration"),
              "| guardado:", pg.evaluate("localStorage.getItem('osintmaps.malla.v1')"), "| prismas:", esperar("mapa3d.getLayoutProperty('edificios', 'visibility') === 'visible'", 4000))
        if parecido(c, MAGENTA) or parecido(c, VERDE): errores.append(f"{nombre}: apagada y se sigue viendo: {c}")
        pg.evaluate("document.getElementById('boton-malla').click()"); esperar("malla && malla.estado().pintados > 0"); pg.wait_for_timeout(1200)
        cx, cy = centro(); c = color_en(pg, cx, cy); print(nombre, "  encendida otra vez:", c, parecido(c, MAGENTA), "| aviso:", pg.inner_text("#aviso-3d")[:60] if pg.is_visible("#aviso-3d") else "")
        if not parecido(c, MAGENTA): errores.append(f"{nombre}: al volver a encender no sale: {c}")
        pg.screenshot(path=f"{nombre}-malla.png")
        pg.evaluate("document.getElementById('boton-3d').click()"); pg.wait_for_timeout(500)
        print(nombre, "de vuelta a 2D: botón de la maqueta visible:", pg.is_visible("#boton-malla"))
        ctx.close()
    b.close()
print("ERRORES:", errores or "ninguno")
