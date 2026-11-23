"""El pulso en un navegador de verdad, con un histórico inventado y sin red.

Fabrica diez días de datos con forma de ciudad (dos puntas en laborable, un hueco de cuatro
horas con el programa cerrado, un «suceso» esta tarde), abre el visor en Chrome sin ventana y
comprueba la consola: línea de tiempo, indicadores, capas en el mapa, sucesos, fuentes,
reproducción y la ficha de un punto. Acaba con `ERRORES: ninguno` o con la lista.

    pip install playwright && playwright install chromium     (o tener Chrome instalado)
    npm install leaflet@1.9.4 leaflet.markercluster@1.5.3      (en esta carpeta)
    python pulso9.py escritorio    # con el programa detrás
    python pulso9.py movil         # lo mismo en pantalla de móvil
    python pulso9.py web           # la web publicada: pulso.json y lo de «ahora» pedido al geoportal (simulado)

Deja capturas en capturas-pulso/ (no se suben al repositorio).
"""
import functools, http.server, json, math, random, shutil, sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))            # el paquete, tal cual está en el repositorio
from osintmaps import cli
from osintmaps.pulso import anomalias
from osintmaps.pulso.almacen import Almacen
from osintmaps.pulso.fuentes import Objeto, Punto, Toma
from osintmaps.pulso.servidor import Pulso
from playwright.sync_api import sync_playwright

CAPTURAS = Path(__file__).resolve().parent / "capturas-pulso"; CAPTURAS.mkdir(exist_ok=True)


def simular(carpeta, dias=10, ahora=None, hueco=True):
    random.seed(7)
    carpeta = Path(carpeta); carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "pulso.sqlite").unlink(missing_ok=True)
    a = Almacen(carpeta / "pulso.sqlite")
    ahora = int(ahora or time.time())
    C = (39.4699, -0.3763)
    est = [(str(i + 1), C[0] + random.gauss(0, 0.018), C[1] + random.gauss(0, 0.022), random.choice([15, 20, 25, 30])) for i in range(70)]
    par = [(str(70 + i), C[0] + random.gauss(0, 0.014), C[1] + random.gauss(0, 0.018), random.choice([200, 371, 450, 800])) for i in range(18)]
    tra = []
    for i in range(90):
        y, x = C[0] + random.gauss(0, 0.02), C[1] + random.gauss(0, 0.025); ang = random.random() * math.pi
        tra.append((str(500 + i), [[round(y + math.sin(ang) * k * 0.0012, 5), round(x + math.cos(ang) * k * 0.0016 + (0.0003 if k == 2 else 0), 5)] for k in range(5)]))
    afo = [(str(4000 + i), C[0] + random.gauss(0, 0.022), C[1] + random.gauss(0, 0.028)) for i in range(160)]
    air = [(f"A{i}", C[0] + random.gauss(0, 0.02), C[1] + random.gauss(0, 0.025)) for i in range(6)]
    def actividad(t):        # 0..1: dos puntas en laborable, una a mediodía en fin de semana
        lt = time.localtime(t); h = lt.tm_hour + lt.tm_min / 60
        if lt.tm_wday < 5: return 0.12 + 0.75 * math.exp(-((h - 8.5) / 1.6) ** 2) + 0.65 * math.exp(-((h - 18.5) / 2.2) ** 2) + 0.3 * math.exp(-((h - 14) / 2) ** 2)
        return 0.1 + 0.5 * math.exp(-((h - 13) / 3) ** 2) + 0.35 * math.exp(-((h - 21) / 2.5) ** 2)
    t = ahora - dias * 86400
    t -= t % 120
    primero = True
    while t <= ahora:
        # un hueco de cuatro horas ayer por la noche: el programa estaba cerrado
        if hueco and ahora - 30 * 3600 < t < ahora - 26 * 3600: t += 120; primero = True; continue
        act = actividad(t)
        evento = 1.0 if ahora - 5 * 3600 < t < ahora - 3 * 3600 else 0.0      # algo pasa esta tarde
        act_e = min(1.3, act + 0.5 * evento)
        g = primero
        bic = {}
        for i, (ident, y, x, cap) in enumerate(est):
            centro = math.hypot(y - C[0], x - C[1]) < 0.012
            lleno = 0.5 + (0.35 if centro else -0.3) * (act_e - 0.3) + 0.08 * math.sin(i + t / 5000)
            bic[ident] = max(0, min(cap, round(cap * lleno + random.gauss(0, 0.6))))
        toma = Toma(valores={"bicis": bic}, puntos={"bicis": {i: Punto(f"Calle {i}", round(y, 6), round(x, 6), cap) for i, y, x, cap in est}} if g else {})
        anc, tot = sum(bic.values()), sum(e[3] for e in est)
        toma.indicadores = {"bicis_ancladas": anc, "bicis_fuera": round(100 * (1 - anc / tot), 1), "bicis_vacias": sum(v == 0 for v in bic.values()), "bicis_llenas": 0}
        a.guardar_toma("bicis", t, toma)
        if t % 300 == 0 or g:
            pv = {i: max(0, round(cap * (1 - min(0.99, 0.35 + 0.55 * act_e + 0.05 * math.sin(int(i)))))) for i, _, _, cap in par}
            lib, pl = sum(pv.values()), sum(p[3] for p in par)
            a.guardar_toma("parking", t, Toma(valores={"parking": pv}, puntos={"parking": {i: Punto(f"Aparcamiento {i}", round(y, 6), round(x, 6), cap) for i, y, x, cap in par}} if g else {},
                                              indicadores={"parking_libres": lib, "parking_ocupacion": round(100 * (1 - lib / pl), 1)}))
        if t % 180 == 0 or g:
            tv = {}
            for i, (ident, geo) in enumerate(tra):
                r = random.random()
                tv[ident] = 3 if i in (3, 40) else (2 if r < 0.25 * act_e ** 2 else 1 if r < 0.7 * act_e ** 1.5 else 0)
            ab = [v for v in tv.values() if v < 3]
            a.guardar_toma("trafico", t, Toma(valores={"trafico": tv}, puntos={"trafico": {i: Punto(f"Av. {i}", geo[2][0], geo[2][1], None, geo) for i, geo in tra}} if g else {},
                                              indicadores={"trafico_indice": round(100 * sum(ab) / (2 * len(ab)), 1), "trafico_denso": sum(v in (1, 2) for v in tv.values()), "trafico_cortado": 2}))
        if t % 600 == 0 or g:
            av = {i: round(max(5, 900 * act * (0.4 + 0.6 * abs(math.sin(int(i)))) + random.gauss(0, 15))) for i, _, _ in afo}
            a.guardar_toma("aforo", t, Toma(valores={"aforo": av}, puntos={"aforo": {i: Punto(f"Punto de aforo {i}", round(y, 6), round(x, 6)) for i, y, x in afo}} if g else {},
                                            indicadores={"aforo": round(sum(av.values()) / len(av))}))
            a.guardar_toma("aforo_bici", t, Toma(indicadores={"aforo_bici": round(180 * act + random.gauss(0, 4))}))
        if t % 900 == 0 or g:
            nv = {i: round(15 + 55 * act + random.gauss(0, 3)) for i, _, _ in air}
            a.guardar_toma("aire", t, Toma(valores={"no2": nv}, puntos={"no2": {i: Punto(f"Estación {i}", round(y, 6), round(x, 6)) for i, y, x in air}} if g else {},
                                           indicadores={"aire_no2": round(sum(nv.values()) / len(nv), 1), "aire_pm25": round(4 + 8 * act, 1)}))
            a.guardar_toma("meteo", t, Toma(indicadores={"meteo_temperatura": round(14 + 5 * math.sin((time.localtime(t).tm_hour - 9) / 24 * 2 * math.pi), 1), "meteo_lluvia": 0, "meteo_viento": 2.1}))
        # aviones y trenes: solo las últimas 6 horas (lo demás no se mira en la prueba)
        if t > ahora - 6 * 3600:
            for dt in range(0, 120, 20):
                tt = t + dt; objs = []
                for n in range(6):
                    fase = ((tt + n * 700) % 2400) / 2400
                    if fase > 0.55: continue
                    ang = n * 1.1
                    objs.append(Objeto(f"34{n:04x}", round(C[0] + 0.02 + math.sin(ang) * (0.6 - fase * 1.1), 5), round(C[1] - 0.09 + math.cos(ang) * (0.8 - fase * 1.45), 5), f"VLG{1200 + n}", (math.degrees(ang) + 180) % 360, round(9000 * (0.55 - fase) * 2) if fase < 0.5 else 0))
                a.guardar_toma("aviones", tt, Toma(objetos={"aviones": objs}, indicadores={"aviones": len(objs), "aviones_bajos": sum(o.alt < 3000 for o in objs)}))
            tr = [Objeto(f"2460{n}", round(C[0] - 0.01 + 0.25 * math.sin((t / 3000 + n) % 3.14), 5), round(C[1] - 0.02 - 0.1 * math.cos((t / 3000 + n) % 3.14), 5), f"C{n + 1}-2460{n}") for n in range(5)]
            a.guardar_toma("trenes", t, Toma(objetos={"trenes": tr}, indicadores={"trenes": len(tr) + (2 if act > 0.5 else 0)}))
        primero = False
        t += 120
    # lo que se sale de lo normal queda apuntado, como haría el recolector
    n = anomalias.Normales(a)
    for tt in range(ahora - 8 * 3600, ahora, 300): anomalias.evaluar(a, n, tt)
    comp = anomalias.evaluar(a, n, ahora)
    return a, comp


modo = sys.argv[1] if len(sys.argv) > 1 else "escritorio"
AQUI = Path(__file__).resolve().parent; NM = AQUI / "node_modules"; errores, pedidos_geo = [], []
trabajo = Path(tempfile.mkdtemp(prefix="pulso9-")); datos = trabajo / "datos"
simular(datos)[0].cerrar()
pulso = Pulso.si_hay(datos)
if modo == "web":
    (datos / "pulso.json").write_bytes(pulso._ficheros_web()["pulso.json"])
    sitio = trabajo / "sitio"; print("copiados:", cli.crear_sitio(sitio, datos))
    class Mudo(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Mudo, directory=str(sitio)))
else:
    cli._Servidor.carpeta_datos = datos; cli._Servidor.pulso = pulso
    srv = cli.ServidorMapa(("127.0.0.1", 0), functools.partial(cli._Servidor, directory=str(cli.CARPETA_WEB)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/"
resumen = json.loads(pulso._ficheros_web()["pulso.json"])
def ruta(route):
    u = route.request.url
    if "unpkg.com/leaflet@" in u: return route.fulfill(path=str(NM / "leaflet/dist" / u.rsplit("/", 1)[-1]))
    if "unpkg.com/leaflet.markercluster@" in u: return route.fulfill(path=str(NM / "leaflet.markercluster/dist" / u.rsplit("/", 1)[-1]))
    if "127.0.0.1" in u: return route.continue_()
    if "geoportal.valencia.es" in u and "/query" in u and "returnGeometry=false" in u:      # lo de «ahora» que pide la web
        pedidos_geo.append(u.split("MapServer/")[1].split("/")[0])
        b = resumen["puntos"]
        if "/228/" in u: f = [{"attributes": {"number": int(i), "available": 3, "free": 10, "total": 20, "open": "T"}} for i in b["bicis"]["ids"]]
        elif "/194/" in u: f = [{"attributes": {"id_aparcamiento": int(i), "plazaslibr": 10, "plazastota": 400}} for i in b["parking"]["ids"]]
        else: f = [{"attributes": {"idtramo": int(i), "estado": 2}} for i in b["trafico"]["ids"]]
        return route.fulfill(json={"features": f}, headers={"Access-Control-Allow-Origin": "*"})
    return route.abort()
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: b = p.chromium.launch(channel="chrome")
    movil = modo == "movil"
    ctx = b.new_context(viewport={"width": 390, "height": 800} if movil else {"width": 1440, "height": 900}, has_touch=movil, device_scale_factor=2 if movil else 1)
    pg = ctx.new_page(); pg.route("**/*", ruta)
    pg.on("pageerror", lambda e: errores.append(f"EXC: {e}"))
    pg.on("console", lambda m: errores.append(m.text[:200]) if m.type == "error" and "ERR_FAILED" not in m.text and "404" not in m.text and "501" not in m.text else None)
    pg.goto(base + "#mapa=13/39.4699/-0.3763"); pg.wait_for_selector("#boton-pulso"); pg.wait_for_timeout(1500)
    print("servidor:", pg.evaluate("conServidor"), "| botón:", pg.evaluate("getComputedStyle(document.getElementById('boton-pulso')).display"))
    pg.click("#boton-pulso"); pg.wait_for_function("window.OSINT_PULSO.estado().R !== null", timeout=15000); pg.wait_for_timeout(1200)
    e = pg.evaluate("(() => { const s = OSINT_PULSO.estado(); return { servidor: s.servidor, directo: s.enDirecto, capas: s.capas, atraso: Math.round(Date.now()/1000 - s.T), n: s.R.indicadores.n, vivo: s.vivoWeb && Object.keys(s.vivoWeb) } })()")
    print("estado:", e)
    print("modo:", pg.inner_text("#pulso .pz-modo"), "| reloj:", pg.inner_text("#pulso .pz-reloj"), "| tejas:", pg.evaluate("[...document.querySelectorAll('#pulso .pz-teja')].map(t => t.innerText.replace(/\\n/g, ' / '))")[:4])
    print("nota:", pg.inner_text("#pulso div.pz-nota")[:230])
    print("alto consola:", pg.evaluate("document.getElementById('pulso').offsetHeight"), "| fondo:", pg.evaluate("document.getElementById('capa-fondo').value"), "| piezas bicis:", pg.evaluate("document.querySelectorAll('.leaflet-pulso-pane canvas').length"))
    pg.screenshot(path=str(CAPTURAS / f"{modo}-1.png"))
    # arrastrar la línea de tiempo al 55 %: deja de estar en directo
    caja = pg.locator("#pulso canvas").bounding_box()
    pg.mouse.move(caja["x"] + caja["width"] * 0.9, caja["y"] + 20); pg.mouse.down(); pg.mouse.move(caja["x"] + caja["width"] * 0.905, caja["y"] + 20, steps=4); pg.mouse.up(); pg.wait_for_timeout(300)
    print("arrastrado:", pg.inner_text("#pulso .pz-modo"), pg.inner_text("#pulso .pz-reloj"), "| tejas fuera:", pg.evaluate("[...document.querySelectorAll('#pulso .pz-teja.pz-fuera small')].map(x => x.textContent)"))
    # encender todas las capas
    for nombre in ("Flujo de bicis", "Aparcamientos", "Aforos", "NO₂"):
        pg.click(f"#pulso button:text-is('{nombre}')")
    pg.wait_for_timeout(500)
    print("capas:", pg.evaluate("OSINT_PULSO.estado().capas"))
    pg.screenshot(path=str(CAPTURAS / f"{modo}-2.png"))
    # sucesos y fuentes
    pg.click("#pulso button:has-text('Sucesos')"); pg.wait_for_timeout(200)
    filas = pg.evaluate("[...document.querySelectorAll('#pulso .pz-lista button')].map(x => x.textContent)"); print("sucesos:", len(filas), filas[:2])
    if filas: pg.click("#pulso .pz-lista button >> nth=0"); pg.wait_for_timeout(300); print("  tras pulsar uno:", pg.inner_text("#pulso .pz-reloj"), "| indicador:", pg.evaluate("document.querySelector('#pulso .pz-teja[aria-pressed=true] small').textContent"))
    pg.click("#pulso button:text-is('Fuentes')"); pg.wait_for_timeout(700)
    print("fuentes:", pg.evaluate("[...document.querySelectorAll('#pulso .pz-lista span')].map(x => x.textContent)")[-4:])
    pg.screenshot(path=str(CAPTURAS / f"{modo}-3.png"))
    pg.click("#pulso button:text-is('Fuentes')")
    # reproducir un par de segundos
    antes = pg.evaluate("OSINT_PULSO.estado().T"); pg.click("#pulso button[title^='Reproducir']"); pg.wait_for_timeout(2000); pg.click("#pulso button[title^='Reproducir']")
    print("reproducido:", round((pg.evaluate("OSINT_PULSO.estado().T") - antes) / 60), "min en 2 s")
    # la ficha de un punto: una estación de bicis
    pos = pg.evaluate("(() => { const b = OSINT_PULSO.estado().R.puntos.parking; const p = mapa.latLngToContainerPoint([b.lat[0], b.lon[0]]); const r = document.getElementById('mapa').getBoundingClientRect(); return [p.x + r.left, p.y + r.top]; })()")
    pg.evaluate("(() => { const b = OSINT_PULSO.estado().R.puntos.parking; mapa.setView([b.lat[0], b.lon[0]], 15, {animate: false}); })()"); pg.wait_for_timeout(500)
    pos = pg.evaluate("(() => { const b = OSINT_PULSO.estado().R.puntos.parking; const p = mapa.latLngToContainerPoint([b.lat[0], b.lon[0]]); const r = document.getElementById('mapa').getBoundingClientRect(); return [p.x + r.left, p.y + r.top]; })()")
    pg.mouse.click(pos[0], pos[1]); pg.wait_for_timeout(900)
    print("ficha:", (pg.evaluate("document.querySelector('.pulso-ficha') ? document.querySelector('.pulso-ficha').innerText : null") or "NO SE ABRE").replace("\n", " / ")[:160])
    pg.screenshot(path=str(CAPTURAS / f"{modo}-4.png"))
    pg.evaluate("mapa.closePopup(); 0")
    if modo == "escritorio":
        pg.click("#pulso button:text-is('7 d')"); pg.wait_for_timeout(2500)
        print("7 d:", pg.evaluate("(() => { const R = OSINT_PULSO.estado().R; return [Math.round((R.hasta - R.desde) / 86400), R.indicadores.paso, R.puntos.bicis.paso, Object.keys(R.rastros).length] })()"))
        pg.screenshot(path=str(CAPTURAS / f"{modo}-5.png"))
    # AHORA y cerrar: vuelve el fondo y se quitan las capas
    pg.click("#pulso button:text-is('AHORA')"); pg.wait_for_timeout(300); print("ahora:", pg.inner_text("#pulso .pz-modo"))
    pg.click("#pulso button[title='Cerrar el pulso']"); pg.wait_for_timeout(300)
    print("cerrado:", pg.evaluate("[document.getElementById('pulso').hidden, OSINT_PULSO.estado().capas.length, document.getElementById('capa-fondo').value, document.getElementById('mapa-zona').classList.contains('con-pulso')]"), "| geoportal:", sorted(set(pedidos_geo)))
    b.close()
print("ERRORES:", errores or "ninguno")
shutil.rmtree(trabajo, ignore_errors=True)
sys.exit(1 if errores else 0)
