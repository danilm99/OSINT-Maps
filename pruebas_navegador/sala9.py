"""La sala de control en un navegador de verdad, con una ciudad inventada y sin red.

Fabrica dieciséis barrios en cuadrícula alrededor de la plaza del Ayuntamiento, tres días de
datos con forma de ciudad (bicis, aparcamientos, tráfico, aforos, metro), cinco semanas de «lo
normal» y, encima, lo que la sala tiene que ver: una afluencia antes de un partido, un incendio
con un helicóptero dando vueltas, noticias, publicaciones e incidencias. Calcula el cruce como
lo haría el programa, abre la sala en Chrome sin ventana y comprueba cabecera, cifras, sucesos,
fichas (suceso, barrio, inmueble), comparar días, movilidad y la máquina del tiempo. Acaba con
`ERRORES: ninguno` o con la lista.

    python sala9.py escritorio    # con el programa detrás
    python sala9.py movil         # lo mismo en pantalla de móvil
    python sala9.py web           # la web publicada: sala.json, sin el programa

Deja capturas en capturas-sala/ (no se suben al repositorio).
"""
import functools, http.server, json, math, random, sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from osintmaps import cli
from osintmaps.pulso import cruce as C, fichas
from osintmaps.pulso.almacen import Almacen
from osintmaps.pulso.fuentes import Cita, Item, Objeto, Punto, Toma
from osintmaps.pulso.servidor import Pulso
from playwright.sync_api import sync_playwright

CAPTURAS = Path(__file__).resolve().parent / "capturas-sala"; CAPTURAS.mkdir(exist_ok=True)
CENTRO = (39.4699, -0.3763)
LADO = 0.012
NOMBRES = ["EL CARME", "LA SEU", "LA XEREA", "SANT FRANCESC", "RUSSAFA", "EL PLA DEL REMEI", "GRAN VIA", "EL BOTANIC",
           "LA ROQUETA", "EL MERCAT", "SANT ANTONI", "EXPOSICIO", "MESTALLA", "JAUME ROIG", "CIUTAT JARDI", "ARRANCAPINS"]
LAT0, LON0 = CENTRO[0] - 2 * LADO, CENTRO[1] - 2 * LADO


def celda(i):
    fila, col = divmod(i, 4)
    return LAT0 + fila * LADO, LON0 + col * LADO


def centro_de(i):
    a, b = celda(i)
    return a + LADO / 2, b + LADO / 2


def actividad(t):
    lt = time.localtime(t); h = lt.tm_hour + lt.tm_min / 60
    if lt.tm_wday < 5:
        return 0.12 + 0.75 * math.exp(-((h - 8.5) / 1.6) ** 2) + 0.65 * math.exp(-((h - 18.5) / 2.2) ** 2) + 0.3 * math.exp(-((h - 14) / 2) ** 2)
    return 0.1 + 0.5 * math.exp(-((h - 13) / 3) ** 2) + 0.35 * math.exp(-((h - 21) / 2.5) ** 2)


def normales(t, i):
    """Lo que marca cada rasgo un día normal en el barrio i a la hora t."""
    act = actividad(t)
    h = time.localtime(t).tm_hour
    return {"bici_ocupacion": 62 - 30 * act + (i % 3) * 3, "parking": 28 + 45 * act + (i % 4) * 2, "trafico": 8 + 38 * act,
            "aforo": 180 + 650 * act + i * 10, "metro": (8 if 6 <= h < 23 else 0) * (1 + (i % 2))}


def ciudad_en_disco(datos):
    c = datos / "ciudad"; c.mkdir(parents=True, exist_ok=True)
    feats = []
    for i, n in enumerate(NOMBRES):
        a, b = celda(i)
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[b, a], [b + LADO, a], [b + LADO, a + LADO], [b, a + LADO], [b, a]]]},
                      "properties": {"coddistbar": f"0{1 + i // 4}{1 + i % 4}", "codbarrio": str(1 + i % 4), "coddistrit": str(1 + i // 4), "nombre": n}})
    (c / "barrios.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    (c / "distritos.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": feats[0]["geometry"], "properties": {"coddistrit": str(d), "nombre": f"DISTRICTE {d}"}} for d in range(1, 5)]}), encoding="utf-8")
    calles = [("COLON", [[LON0, CENTRO[0]], [LON0 + 4 * LADO, CENTRO[0]]]), ("XATIVA", [[CENTRO[1], LAT0], [CENTRO[1], LAT0 + 4 * LADO]])]
    (c / "calles.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": g}, "properties": {"codvia": str(k), "tipcalle": "CALLE", "nomcalle": n,
                                                                                               "lf_add": 1, "lt_add": 199, "rf_add": 2, "rt_add": 200}}
        for k, (n, g) in enumerate(calles)]}), encoding="utf-8")
    (c / "vulnerabilidad.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": f["geometry"], "properties": {"codbar": int(f["properties"]["coddistbar"]), "ind_global": round(2 + (k % 5) * 0.6, 1),
                                                                     "vul_global": ["Vulnerabilidad Baja", "Vulnerabilidad Media", "Vulnerabilidad Alta"][k % 3],
                                                                     "vul_econom": "Vulnerabilidad Media", "vul_dem": "Vulnerabilidad Baja", "vul_equip": "Vulnerabilidad Baja"}}
        for k, f in enumerate(feats)]}), encoding="utf-8")
    (c / "quejas.csv").write_text("Fecha Entrada;Tema;Barrio Localización\n" + "".join(
        f"{1 + k % 28:02d}/11/2026;{['Servicios de limpieza en la vía pública', 'Contaminación acústica', 'Señalización viaria'][k % 3]};{int(feats[k % 16]['properties']['coddistbar'])}\n"
        for k in range(300)), encoding="utf-8")
    (c / "accidentes.csv").write_text("FECHA;TIPO GRAVEDAD;UBICACIÓN;TIPO ACCIDENTE;UNIDADES_IMPLICADAS\n" + "".join(
        f"2026-{1 + k % 10:02d}-{1 + k % 27:02d} 1{k % 10}:00:00;{['SIN HERIDOS', 'CON HERIDOS LEVES', 'CON HERIDOS GRAVES'][k % 3]};C/ COLON {1 + 2 * (k % 40)};"
        f"{['ALCANCE', 'ATROPELLO', 'COLISIÓN FRONTOLATERAL'][k % 3]};TURISMO, MOTOCICLETA\n" for k in range(80)), encoding="utf-8")
    (c / "patrimonio.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[CENTRO[1] - 0.0004, CENTRO[0] - 0.0003], [CENTRO[1] + 0.0004, CENTRO[0] - 0.0003],
                                                                             [CENTRO[1] + 0.0004, CENTRO[0] + 0.0003], [CENTRO[1] - 0.0004, CENTRO[0] + 0.0003],
                                                                             [CENTRO[1] - 0.0004, CENTRO[0] - 0.0003]]]},
         "properties": {"codigo": "E-1", "denominaci": "Edificio de prueba", "grado_prot": "BRL", "categoria": "Monumento de Interés Local", "t_elemento": "Edificio"}}]}),
        encoding="utf-8")


def simular(datos, dias=3, ahora=None):
    random.seed(11)
    datos.mkdir(parents=True, exist_ok=True)
    ciudad_en_disco(datos)
    (datos / "pulso.sqlite").unlink(missing_ok=True)
    a = Almacen(datos / "pulso.sqlite")
    ahora = int(ahora or time.time()) // C.BIN * C.BIN
    codigos = [f"0{1 + i // 4}{1 + i % 4}" for i in range(16)]
    MESTALLA, INCENDIO = 12, 5                      # el partido y el incendio
    # Cinco semanas de lo normal (las muestras de cada media hora), como si el programa llevara ese tiempo en marcha.
    filas = []
    lt = time.localtime(ahora)
    lunes = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))) - lt.tm_wday * 86400      # el lunes de esta semana, a las 0:00
    for semana in range(1, 6):
        for fr in range(336):
            t = lunes - semana * 7 * 86400 + fr * 1800 + 900
            for i, cod in enumerate(codigos):
                for r, v in normales(t, i).items():
                    filas.append((r, cod, C.franja(t), t // C.SEMANA, round(v + random.gauss(0, 1.2), 2), 0))
            for r in ("bici_ocupacion", "parking", "trafico", "aforo", "metro"):
                vals = [normales(t, i)[r] for i in range(16)]
                filas.append((r, C.CIUDAD, C.franja(t), t // C.SEMANA, round(sum(vals) / 16 if r != "metro" else sum(vals) / 16, 2), 0))
    a._bd.executemany("INSERT OR REPLACE INTO muestras VALUES (?,?,?,?,?,?)", filas)
    # Tres días de tomas cada diez minutos.
    est = {f"b{i}{k}": (i, centro_de(i)[0] + (k - 1) * 0.002, centro_de(i)[1] + (k - 1) * 0.002) for i in range(16) for k in range(3)}
    par = {f"p{i}": (i, *centro_de(i)) for i in range(16)}
    tra = {f"t{i}{k}": (i, centro_de(i)[0] + 0.003 * (k - 1.5), centro_de(i)[1]) for i in range(16) for k in range(4)}
    afo = {f"a{i}{k}": (i, centro_de(i)[0], centro_de(i)[1] + 0.003 * (k - 0.5)) for i in range(16) for k in range(2)}
    met = {f"m{i}": (i, *centro_de(i)) for i in range(0, 16, 2)}
    partido = Cita("partido:1", "partido", "Valencia CF – Real Betis (Mestalla)", ahora + 1800, ahora + 1800 + 7200, *centro_de(MESTALLA), fuente="TheSportsDB")
    obras = [Cita(f"obra:{k}", "obra", f"Obra — renovación de aceras {k}", ahora - 20 * 86400, ahora + 20 * 86400, centro_de(k)[0] + 0.001, centro_de(k)[1], fuente="Ajuntament")
             for k in range(0, 16, 3)]
    fiesta = Cita("festivo:x", "festejo", "Concierto en la plaza", ahora - 3600, ahora + 7200, *centro_de(1), fuente="Ajuntament")
    t = ahora - dias * 86400
    primero = True
    while t <= ahora:
        partido_ya = ahora - 5400 < t                      # hora y media antes del partido
        incendio_ya = ahora - 2400 < t
        g = primero
        bic, parq, traf, afor, metr = {}, {}, {}, {}, {}
        for ident, (i, la, lo) in est.items():
            occ = normales(t, i)["bici_ocupacion"] / 100
            if partido_ya and i == MESTALLA:
                occ = 0.97
            bic[ident] = max(0, min(20, round(20 * occ + random.gauss(0, 0.6))))
        for ident, (i, la, lo) in par.items():
            occ = normales(t, i)["parking"] / 100
            if partido_ya and i == MESTALLA:
                occ = 0.98
            parq[ident] = max(0, round(400 * (1 - occ) + random.gauss(0, 3)))
        for ident, (i, la, lo) in tra.items():
            nivel = normales(t, i)["trafico"] / 50
            if (partido_ya and i in (MESTALLA, MESTALLA + 1)) or (incendio_ya and i == INCENDIO):
                nivel = 1.9
            if incendio_ya and i == INCENDIO and ident.endswith("0"):
                traf[ident] = 3
                continue
            traf[ident] = 2 if random.random() < nivel - 1 else (1 if random.random() < min(1.0, nivel) else 0)
        for ident, (i, la, lo) in afo.items():
            v = normales(t, i)["aforo"]
            if incendio_ya and i == INCENDIO:
                v *= 0.35
            afor[ident] = round(v + random.gauss(0, 15))
        for ident, (i, la, lo) in met.items():
            metr[ident] = normales(t, i)["metro"]
        a.guardar_toma("bicis", t, Toma(valores={"bicis": bic}, puntos={"bicis": {k: Punto(f"Estación {k}", la, lo, 20) for k, (i, la, lo) in est.items()}} if g else {}))
        a.guardar_toma("parking", t, Toma(valores={"parking": parq}, puntos={"parking": {k: Punto(f"Parking {NOMBRES[i].title()}", la, lo, 400) for k, (i, la, lo) in par.items()}} if g else {},
                                          indicadores={"parking_ocupacion": round(100 * (1 - sum(parq.values()) / (400 * 16)), 1)}))
        a.guardar_toma("trafico", t, Toma(valores={"trafico": traf}, puntos={"trafico": {k: Punto(f"Tramo {k}", la, lo) for k, (i, la, lo) in tra.items()}} if g else {},
                                          indicadores={"trafico_indice": round(100 * sum(x for x in traf.values() if x < 3) / (2 * len(traf)), 1),
                                                       "trafico_cortado": sum(1 for x in traf.values() if x == 3)}))
        a.guardar_toma("aforo", t, Toma(valores={"aforo": afor}, puntos={"aforo": {k: Punto(f"Punto de aforo {k}", la, lo) for k, (i, la, lo) in afo.items()}} if g else {},
                                        indicadores={"aforo": round(sum(afor.values()) / len(afor))}))
        a.guardar_toma("metro", t, Toma(valores={"metro": metr}, puntos={"metro": {k: Punto(f"Metro {k}", la, lo) for k, (i, la, lo) in met.items()}} if g else {},
                                        indicadores={"metro_salidas": sum(metr.values()), "metro_sin_servicio": sum(1 for v in metr.values() if not v)}))
        a.guardar_toma("meteo", t, Toma(indicadores={"meteo_temperatura": 14 + 6 * actividad(t), "meteo_lluvia": 0.0}))
        a.guardar_toma("bicis", t + 1, Toma(indicadores={"bicis_fuera": round(100 - 100 * sum(bic.values()) / (20 * len(bic)), 1)}))
        textos, cielo, dgt = [], [], []
        if t == ahora - 4800:
            textos += [Item("prensa:p1", "prensa", t - 60, "Ambiente de partido en Mestalla: miles de aficionados en la avenida de Aragón", url="https://ejemplo.es/p1",
                            lat=centro_de(MESTALLA)[0], lon=centro_de(MESTALLA)[1], barrio=codigos[MESTALLA], categoria="deporte", extra={"medio": "Las Provincias"})]
        if partido_ya and t % 1800 == 0:
            textos += [Item(f"bluesky:m{t}", "bluesky", t - 30, "Qué ambientazo hay en Mestalla hoy", url="https://bsky.app/profile/x/post/y", barrio=codigos[MESTALLA], categoria="deporte")]
        if incendio_ya and t == ahora - 1800:
            for k, medio in enumerate(("Las Provincias", "Valencia Plaza")):
                textos.append(Item(f"prensa:f{k}", "prensa", t - 120 + k * 30, ["Incendio en un edificio de Russafa: los bomberos desalojan a los vecinos",
                                                                                 "Grave incendio en Russafa, varios desalojados"][k], url=f"https://ejemplo.es/f{k}",
                                   lat=centro_de(INCENDIO)[0], lon=centro_de(INCENDIO)[1], barrio=codigos[INCENDIO], categoria="emergencia", urgencia=3, extra={"medio": medio}))
        if incendio_ya:
            la, lo = centro_de(INCENDIO)
            for s in range(0, 600, 30):
                ang = (t + s) / 90
                a.guardar_toma("aviones", t - 600 + s, Toma(objetos={"helicopteros": [Objeto("34a1b2", round(la + 0.002 * math.sin(ang), 5), round(lo + 0.0025 * math.cos(ang), 5),
                                                                                                "POLICIA21", (ang * 57) % 360, 320)]}))
            dgt = [Item("dgt:1", "dgt", ahora - 2000, "Corte o restricción de carril en V-30", url="https://infocar.dgt.es/etraffic/", lat=centro_de(INCENDIO)[0] - 0.003,
                        lon=centro_de(INCENDIO)[1], barrio=codigos[INCENDIO], categoria="trafico", urgencia=1)]
        a.guardar_toma("prensa", t, Toma(items=[x for x in textos if x.fuente == "prensa"], agenda=[partido, fiesta, *obras] if g else []))
        a.guardar_toma("bluesky", t, Toma(items=[x for x in textos if x.fuente == "bluesky"]))
        a.guardar_toma("dgt", t, Toma(items=dgt))
        if not incendio_ya:
            a.guardar_toma("aviones", t, Toma(objetos={"aviones": []}, indicadores={"aviones": 12, "helicopteros": 0}))
        primero = False
        t += C.BIN
    a.cerrar()
    return ahora


modo = sys.argv[1] if len(sys.argv) > 1 else "escritorio"
AQUI = Path(__file__).resolve().parent; NM = AQUI / "node_modules"; errores = []
trabajo = Path(tempfile.mkdtemp(prefix="sala9-")); datos = trabajo / "datos"
t0 = time.time()
ahora = simular(datos)
fichas.Fichas.catastro = lambda self, lat, lon, sesion=None: {"rc": "5628402YJ2752H", "direccion": "CL DE PRUEBA 12 VALENCIA", "uso": "Residencial", "año": 1928,
                                                               "inmuebles": 14, "usos": [["Residencial", 12], ["Comercial", 2]], "superficie_total": 1840,
                                                               "enlace": "https://www1.sedecatastro.gob.es/"}
pulso = Pulso.si_hay(datos)
sala = pulso.sala
assert sala.cruce is not None, "la sala no ha cargado los barrios"
n = sala.cruce.reconstruir(ahora - 3 * 86400, ahora, sucesos_desde=ahora - 6 * 3600)
sala.fichas.situar_accidentes()
print(f"simulado y cruzado en {time.time() - t0:.1f} s ({n} intervalos)")
eventos = sala.cruce.eventos(ahora - 86400, ahora + 1)
print("sucesos:", [(e["tipo"], e["titulo"]) for e in eventos])
if not any(e["tipo"] == "concentracion" and "Mestalla" in (e["titulo"] or "") for e in eventos): errores.append("no sale la afluencia de Mestalla")
if not any(e["tipo"] == "incidente" for e in eventos): errores.append("no sale el incendio")

if modo == "web":
    for nombre, contenido in sala.ficheros_web().items():
        (datos / nombre).write_bytes(contenido)
    sitio = trabajo / "sitio"; print("copiados:", cli.crear_sitio(sitio, datos))
    class Mudo(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Mudo, directory=str(sitio)))
else:
    cli._Servidor.carpeta_datos = datos; cli._Servidor.pulso = pulso
    srv = cli.ServidorMapa(("127.0.0.1", 0), functools.partial(cli._Servidor, directory=str(cli.CARPETA_WEB)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/"


def ruta(route):
    u = route.request.url
    if "unpkg.com/leaflet@" in u: return route.fulfill(path=str(NM / "leaflet/dist" / u.rsplit("/", 1)[-1]))
    if "127.0.0.1" in u: return route.continue_()
    return route.abort()


with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: b = p.chromium.launch(channel="chrome")
    tam = {"width": 390, "height": 844} if modo == "movil" else {"width": 1600, "height": 960}
    ctx = b.new_context(viewport=tam, device_scale_factor=2 if modo == "movil" else 1, is_mobile=modo == "movil", has_touch=modo == "movil")
    pg = ctx.new_page(); pg.route("**/*", ruta)
    pg.on("console", lambda m: errores.append(f"consola: {m.text}") if m.type == "error" and "net::ERR_FAILED" not in m.text and "Failed to load resource" not in m.text else None)
    pg.on("pageerror", lambda e: errores.append(f"página: {e}"))
    pg.goto(base + "sala.html")
    pg.wait_for_function("window.OSINT_SALA && window.OSINT_SALA.estado() && document.querySelectorAll('.suceso').length > 0", timeout=20000)
    pg.wait_for_timeout(800)
    e = pg.evaluate("window.OSINT_SALA.estado()")
    print("nivel:", e["nivel"], "| sucesos:", len(e["sucesos"]), "| tejas:", pg.evaluate("document.querySelectorAll('.teja').length"),
          "| barrios en el mapa:", pg.evaluate("document.querySelectorAll('.leaflet-barrios-pane path').length"),
          "| marcas de suceso:", pg.evaluate("document.querySelectorAll('.icono-suceso').length"))
    if pg.evaluate("document.querySelectorAll('.leaflet-barrios-pane path').length") < 16: errores.append("faltan barrios en el mapa")
    if modo != "movil" and pg.evaluate("document.querySelectorAll('.teja').length") < 5: errores.append("pocas tejas de ciudad")
    if modo == "web":
        if "ambientazo" in pg.content(): errores.append("la web enseña texto de redes")
        if pg.evaluate("window.OSINT_SALA.servidor()"): errores.append("la web cree que hay servidor")
    pg.screenshot(path=str(CAPTURAS / f"{modo}-1.png"))
    if modo == "movil":
        pg.click("#pestanas button[data-vista=sucesos]"); pg.wait_for_timeout(300)
        pg.screenshot(path=str(CAPTURAS / f"{modo}-1b.png"))
    # El suceso del incendio: su ficha.
    pg.evaluate("(() => { const s = window.OSINT_SALA.estado().sucesos.find((x) => x.tipo === 'incidente') || window.OSINT_SALA.estado().sucesos[0]; window.OSINT_SALA.abrirSuceso(s.id); })()")
    pg.wait_for_function("!document.getElementById('ficha').hidden && document.querySelectorAll('#ficha section').length > 1", timeout=10000)
    pg.wait_for_timeout(900)
    secciones = pg.evaluate("[...document.querySelectorAll('#ficha h4')].map((h) => h.textContent)")
    print("ficha del suceso:", secciones)
    if modo != "web" and not any("Helicópteros" in s for s in secciones): errores.append("la ficha del incendio no trae el helicóptero")
    if modo != "web" and pg.evaluate("document.querySelectorAll('#ficha canvas').length") < 1: errores.append("la ficha del suceso no tiene gráficas")
    pg.screenshot(path=str(CAPTURAS / f"{modo}-2.png"))
    # Un barrio.
    pg.evaluate("window.OSINT_SALA.abrirBarrio('041')")
    pg.wait_for_function("document.querySelector('#ficha h3') && document.querySelector('#ficha h3').textContent.includes('Mestalla')", timeout=10000)
    pg.wait_for_timeout(600)
    print("ficha del barrio:", pg.evaluate("[...document.querySelectorAll('#ficha h4')].map((h) => h.textContent)"))
    pg.screenshot(path=str(CAPTURAS / f"{modo}-3.png"))
    # Un inmueble: clic derecho en el mapa (en el móvil, por la función).
    if modo == "movil":
        pg.evaluate(f"window.OSINT_SALA.abrirLugar({CENTRO[0] + 0.00005}, {CENTRO[1] + 0.0002})")
    else:
        pg.evaluate("window.OSINT_SALA.cerrarFicha()")
        caja = pg.evaluate("(() => { const r = document.getElementById('mapa').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        pt = pg.evaluate(f"window.mapa.latLngToContainerPoint([{CENTRO[0] + 0.00005}, {CENTRO[1] + 0.0002}])")
        pg.mouse.click(caja[0] + pt["x"], caja[1] + pt["y"], button="right")
    pg.wait_for_function("document.querySelector('#ficha .tipo') && document.querySelector('#ficha .tipo').textContent.includes('Inmueble')", timeout=10000)
    pg.wait_for_timeout(1200)
    lugar = pg.evaluate("[...document.querySelectorAll('#ficha h4')].map((h) => h.textContent)")
    print("ficha del inmueble:", pg.evaluate("document.querySelector('#ficha h3').textContent"), lugar)
    if modo != "web" and not any("Catastro" in s for s in lugar): errores.append("la ficha del inmueble no trae el Catastro")
    if modo != "web" and not any("Patrimonio" in s for s in lugar): errores.append("la ficha del inmueble no trae el patrimonio")
    pg.screenshot(path=str(CAPTURAS / f"{modo}-4.png"))
    # Comparar laborable y sábado.
    pg.evaluate("window.OSINT_SALA.abrirComparar()")
    pg.wait_for_function("window.OSINT_SALA.modo().tipo === 'comparar'", timeout=10000)
    pg.wait_for_timeout(600)
    print("comparar:", pg.evaluate("document.querySelector('#ficha .pie').textContent"))
    pg.screenshot(path=str(CAPTURAS / f"{modo}-5.png"))
    # Movilidad.
    pg.evaluate("window.OSINT_SALA.abrirMovilidad()")
    pg.wait_for_function("window.OSINT_SALA.modo().tipo === 'movilidad'", timeout=10000)
    pg.wait_for_timeout(700)
    pg.screenshot(path=str(CAPTURAS / f"{modo}-6.png"))
    pg.evaluate("window.OSINT_SALA.cerrarFicha()")
    # La máquina del tiempo.
    if modo != "movil":
        pg.click("#b-tiempo")
        pg.wait_for_function("!document.getElementById('pulso').hidden", timeout=10000)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(CAPTURAS / f"{modo}-7.png"))
    b.close()
print("ERRORES:", "ninguno" if not errores else "\n  " + "\n  ".join(errores))
