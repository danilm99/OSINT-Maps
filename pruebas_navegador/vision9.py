"""Lo visto desde el aire: el bloque de la ficha y las líneas detectadas sobre el mapa (2D y 3D).
Los datos (revision.json y vision/<id>.json) se escriben aquí mismo, en la carpeta que sirve el programa."""
exec(open("maps9.py", encoding="utf-8").read())
sitios = json.load(open(datos / "candidatos.geojson"))["features"]
ID0, ID1, ID2 = (s["properties"]["id"] for s in sitios[:3])
LON0, LAT0 = sitios[0]["geometry"]["coordinates"][:2]
REVISION = {"imagen": "0202_2025PVAL0015", "vuelo": "2025", "modelo": "lineas-v1", "hecho": "2026-11-23", "radio_m": 154,
            "fiabilidad": {"muro": {"precision": 61, "alcance": 48}, "valla": {"precision": 35, "alcance": 22}, "camino": {"precision": 80, "alcance": 71}},
            "sitios": {ID0: {"estado": "ruina_vegetacion", "altura_m": 5.13, "en_pie_pct": 62, "vegetacion_pct": 41, "cerrado_pct": 65, "accesos": 2, "largo_m": {"muro": 13400, "valla": 120, "camino": 510}},
                       ID1: {"estado": "solar", "altura_m": 0.2, "en_pie_pct": 3, "vegetacion_pct": 10, "cerrado_pct": 0, "accesos": 0}}}
LINEAS = {"imagen": "0202_2025PVAL0015", "modelo": "lineas-v1", "o": [LON0, LAT0], "l": [
    ["muro", 83, [-600, -400, 1200, 0, 0, 800, -1200, 0]],                 # tres lados de un cercado
    ["valla", 61, [-600, -400, 0, 800]],                                   # y el cuarto, de valla
    ["camino", 90, [-1500, -900, 700, 300, 400, 250]],
    ["acequia", 70, [0, 0, 100, 100]],                                     # una clase que el visor no conoce: se ignora
    ["senda", 55, [5, 5]]]}                                                # una línea de un solo punto: se ignora
(datos / "revision.json").write_text(json.dumps(REVISION), encoding="utf-8")
(datos / "vision").mkdir(exist_ok=True)
(datos / "vision" / f"{ID0}.json").write_text(json.dumps(LINEAS), encoding="utf-8")

errores = []
def comprobar(nombre, que, cierto):
    print(nombre, " bien " if cierto else " MAL  ", que)
    if not cierto: errores.append(f"{nombre}: {que}")
abrir = lambda pg, ident: (pg.evaluate(f"abrirFicha(candidatos.find((c) => c.id === '{ident}'), true); 0"), pg.wait_for_timeout(500))
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--enable-webgl"])
    for nombre, vp in (("escritorio", {"width": 1360, "height": 860}), ("movil", {"width": 390, "height": 800})):
        ctx = b.new_context(viewport=vp, has_touch=(nombre == "movil")); pg = ctx.new_page(); pg.route("**/*", ruta)
        pg.on("console", lambda m: errores.append(f"{nombre} {m.type}: {m.text[:300]}") if m.type in ("error", "warning") and "ERR_FAILED" not in m.text and "GPU stall" not in m.text and "GL Driver" not in m.text else None)
        pg.on("pageerror", lambda e: errores.append(f"{nombre} EXC: {e}"))
        pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(600)
        comprobar(nombre, "el resumen ha llegado", pg.evaluate("!!revisionAerea && Object.keys(revisionAerea.sitios).length") == 2)

        # --- la ficha de un sitio con todo
        abrir(pg, ID0)
        texto = pg.inner_text("#ficha .bloque.vision")
        comprobar(nombre, "bloque en la ficha, entre las notas y los enlaces", pg.evaluate("(() => { const h = [...document.getElementById('ficha').children]; const i = h.findIndex((x) => x.classList.contains('vision')); return h[i - 1].id === 'nota-personal' && h[i + 1].classList.contains('bloque'); })()"))
        comprobar(nombre, "título con el año de la foto", "Visto desde el aire (foto de 2025)" in texto)
        comprobar(nombre, "veredicto", pg.inner_text("#ficha .vision .veredicto") == "En pie, con vegetación dentro")
        comprobar(nombre, "en pie y altura con coma decimal", "62 % de la planta, árboles incluidos; altura, 5,1 m" in texto)
        comprobar(nombre, "vegetación, cierre y accesos", "41 %" in texto and "en 65 de cada 100 direcciones" in texto and "llegan 2 caminos o sendas a menos de 20 m" in texto)
        leyenda = pg.evaluate("[...document.querySelectorAll('#ficha .leyenda-vision li')].map((li) => li.textContent)")
        comprobar(nombre, f"leyenda con metros y miles: {leyenda}", leyenda == ["Muro, 13.400 m", "Valla, 120 m", "Camino, 510 m"])
        comprobar(nombre, "la muestra de la valla va a trazos y la del muro no", pg.evaluate("[...document.querySelectorAll('#ficha .leyenda-vision line')].map((l) => l.getAttribute('stroke-dasharray') || '')") == ["", "7 6", "13 7"])
        comprobar(nombre, "radio de lo detectado", "Detectado a 154 m a la redonda" in texto)
        comprobar(nombre, "cuánto fiarse, plegado, con las cifras", pg.evaluate("(() => { const d = document.querySelector('#ficha .fiar-vision'); return !d.open && d.textContent.includes('Muro: coinciden 61, encuentra 48.') && d.textContent.includes('primera criba'); })()"))
        # --- las líneas sobre el mapa
        comprobar(nombre, "encendido de serie", pg.get_attribute("#ver-vision", "aria-pressed") == "true")
        comprobar(nombre, "tres clases pintadas, cada una con su borde", pg.evaluate("capaVision.getLayers().length") == 6)
        puntos = pg.evaluate("lineasVision.map((l) => [l.clase, l.puntos.length, l.puntos[0].map((v) => +v.toFixed(6)), l.puntos[l.puntos.length - 1].map((v) => +v.toFixed(6))])")
        esperado = [["muro", 4, [round(LAT0 - 0.0004, 6), round(LON0 - 0.0006, 6)], [round(LAT0 + 0.0004, 6), round(LON0 - 0.0006, 6)]],
                    ["valla", 2, [round(LAT0 - 0.0004, 6), round(LON0 - 0.0006, 6)], [round(LAT0 + 0.0004, 6), round(LON0 - 0.0006, 6)]],
                    ["camino", 3, [round(LAT0 - 0.0009, 6), round(LON0 - 0.0015, 6)], [round(LAT0 - 0.00035, 6), round(LON0 - 0.0004, 6)]]]
        comprobar(nombre, f"líneas descifradas donde tocan (y sin la clase desconocida ni la de un punto): {puntos}", puntos == esperado)
        comprobar(nombre, "en su panel, sobre los contornos y sin recibir clics", pg.evaluate("(() => { const p = mapa.getPane('vision'); return p.style.zIndex === '360' && p.style.pointerEvents === 'none' && !!p.querySelector('canvas'); })()"))
        comprobar(nombre, "la capa de calidad del aire no comparte panel", pg.evaluate("!document.querySelector('.leaflet-vision-pane .leaflet-marker-icon')"))
        if nombre == "movil": pg.evaluate("typeof ponerHoja === 'function' && ponerHoja('media'); 0"); pg.wait_for_timeout(300)
        pg.screenshot(path=f"{nombre}-vision.png")
        pg.evaluate("document.querySelector('#ficha .bloque.vision').scrollIntoView({ block: 'start' }); 0"); pg.wait_for_timeout(200)
        pg.screenshot(path=f"{nombre}-vision-ficha.png")
        comprobar(nombre, "bajar por la ficha no mueve el mapa", pg.evaluate("mapa.getZoom()") >= 17)
        # --- apagar y encender
        pg.evaluate("document.getElementById('ver-vision').click()"); pg.wait_for_timeout(200)
        comprobar(nombre, "apagar quita las líneas y se recuerda", pg.evaluate("capaVision.getLayers().length === 0 && localStorage.getItem('osintmaps.vision.v1') === 'false' && document.getElementById('ver-vision').getAttribute('aria-pressed') === 'false'"))
        abrir(pg, ID1)
        comprobar(nombre, "apagado, otro sitio no pinta nada", pg.evaluate("capaVision.getLayers().length") == 0)
        abrir(pg, ID0)
        comprobar(nombre, "sigue apagado al volver", pg.evaluate("capaVision.getLayers().length === 0 && document.getElementById('ver-vision').getAttribute('aria-pressed') === 'false'"))
        pg.evaluate("document.getElementById('ver-vision').click()"); pg.wait_for_timeout(300)
        comprobar(nombre, "encender las vuelve a pintar", pg.evaluate("capaVision.getLayers().length") == 6)
        pedidas = pg.evaluate(f"performance.getEntriesByType('resource').filter((r) => r.name.includes('/datos/vision/{ID0}.json')).length")
        comprobar(nombre, f"las líneas de un sitio se piden una sola vez ({pedidas})", pedidas == 1)
        # --- un solar sin nada alrededor
        abrir(pg, ID1)
        texto = pg.inner_text("#ficha .bloque.vision")
        comprobar(nombre, "solar: veredicto y sin altura", pg.inner_text("#ficha .vision .veredicto") == "Sin nada en pie" and "3 % de la planta, árboles incluidos" in texto and "altura," not in texto)
        comprobar(nombre, "solar: sin cierre ni accesos, dicho con palabras", "no se ve ninguno alrededor" in texto and "no se ve ningún camino a menos de 20 m" in texto)
        comprobar(nombre, "sin líneas: se dice, y no hay botón ni leyenda", "No se ha detectado ningún camino, muro ni valla alrededor." in texto and pg.evaluate("!document.getElementById('ver-vision') && !document.querySelector('#ficha .leyenda-vision')"))
        comprobar(nombre, "el mapa se queda sin las líneas del anterior", pg.evaluate("capaVision.getLayers().length === 0 && lineasVision.length === 0"))
        # --- un sitio del que no se sabe nada
        abrir(pg, ID2)
        comprobar(nombre, "sin datos de ese sitio, el bloque no se ve", pg.evaluate("document.querySelector('#ficha .bloque.vision').hidden && capaVision.getLayers().length === 0"))
        # --- volver a la lista
        abrir(pg, ID0)
        comprobar(nombre, "de nuevo pintadas", pg.evaluate("capaVision.getLayers().length") == 6)
        pg.evaluate("volverALista(); 0"); pg.wait_for_timeout(200)
        comprobar(nombre, "al volver a la lista se quitan", pg.evaluate("capaVision.getLayers().length === 0 && visionDe === null"))
        # --- en la lista y en los filtros
        sub = pg.evaluate(f"[...document.querySelectorAll('#lista li')].slice(0, 40).map((li) => li.querySelector('.sub').textContent)")
        comprobar(nombre, "la lista dice lo que se ve desde el aire", sum("en pie, con vegetación" in s for s in sub) == 1 and sum("sin nada en pie" in s for s in sub) == 1)
        comprobar(nombre, "el filtro «Desde el aire» aparece", pg.evaluate("!document.getElementById('fila-vision').hidden"))
        todos = pg.evaluate("visibles.length")
        elegir = lambda v: (pg.evaluate(f"(() => {{ const s = document.getElementById('f-vision'); s.value = '{v}'; s.dispatchEvent(new Event('change')); }})()"), pg.wait_for_timeout(250))
        elegir("no-solar")
        comprobar(nombre, "ocultar lo derribado quita solo ese", pg.evaluate(f"visibles.length === {todos - 1} && !visibles.some((c) => c.id === '{ID1}') && enMapa.length === {todos - 1}"))
        comprobar(nombre, "y se dice en el resumen de filtros y se recuerda", "ocultar lo derribado" in pg.inner_text("#resumen-filtros") and pg.evaluate("JSON.parse(localStorage.getItem('osintmaps.vista.v1')).aire") == "no-solar")
        elegir("solar")
        comprobar(nombre, "solo lo derribado", pg.evaluate(f"visibles.length === 1 && visibles[0].id === '{ID1}'"))
        elegir("ruina")
        comprobar(nombre, "solo ruinas en pie", pg.evaluate(f"visibles.length === 1 && visibles[0].id === '{ID0}'"))
        elegir("tejado")
        comprobar(nombre, "solo con cubierta: ninguno, y se avisa", pg.evaluate("visibles.length === 0 && !document.getElementById('sin-coincidencias').hidden"))
        elegir("")
        comprobar(nombre, "sin filtro vuelven todos", pg.evaluate(f"visibles.length === {todos}"))
        # --- en 3D
        abrir(pg, ID0)
        pg.click("#boton-3d"); pg.wait_for_timeout(5000)
        pg.wait_for_function("en3D() && !!mapa3d && !!mapa3d.getSource('vision') && mapa3d.getSource('vision').serialize().data.features.length > 0", timeout=20000)
        comprobar(nombre, "en 3D", pg.evaluate("en3D()"))
        en3d = pg.evaluate("mapa3d.getSource('vision').serialize().data.features.map((f) => [f.properties.color, f.geometry.coordinates.length])")
        comprobar(nombre, f"las mismas líneas en la vista 3D, con su color: {en3d}", en3d == [["#ff7a33", 4], ["#ffd91a", 2], ["#ffffff", 3]])
        orden = pg.evaluate("mapa3d.getStyle().layers.map((l) => l.id)")
        comprobar(nombre, "en 3D van sobre la maqueta y bajo la ruta y los puntos", (("malla" not in orden) or orden.index("malla") < orden.index("vision-borde")) and orden.index("vision-borde") < orden.index("vision-linea") < orden.index("ruta-borde") < orden.index("puntos"))
        pg.wait_for_timeout(1500); pg.screenshot(path=f"{nombre}-vision-3d.png")
        pg.evaluate("volverALista(); 0")
        try: pg.wait_for_function("mapa3d.getSource('vision').serialize().data.features.length === 0", timeout=15000)
        except Exception: pass
        comprobar(nombre, "al cerrar la ficha se quitan también en 3D", pg.evaluate("mapa3d.getSource('vision').serialize().data.features.length") == 0)
        pg.evaluate("document.getElementById('boton-3d').click()"); pg.wait_for_timeout(400)
        ctx.close()

    # --- sin el resumen (lo normal hasta que se pasa el detector): ni bloque, ni errores, ni peticiones de líneas
    (datos / "revision.json").unlink()
    ctx = b.new_context(viewport={"width": 1360, "height": 860}); pg = ctx.new_page(); pg.route("**/*", ruta)
    pg.on("console", lambda m: errores.append(f"sin-resumen {m.type}: {m.text[:300]}") if m.type in ("error", "warning") and "ERR_FAILED" not in m.text else None)
    pg.on("pageerror", lambda e: errores.append(f"sin-resumen EXC: {e}"))
    pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(600)
    abrir(pg, ID0)
    comprobar("sin-resumen", "sin datos no hay filtro ni etiqueta en la lista", pg.evaluate("document.getElementById('fila-vision').hidden && ![...document.querySelectorAll('#lista .sub')].some((s) => /en pie/.test(s.textContent))"))
    comprobar("sin-resumen", "no hay bloque ni líneas, y nada se pide de más", pg.evaluate("revisionAerea === null && document.querySelector('#ficha .bloque.vision').hidden && capaVision.getLayers().length === 0 && !performance.getEntriesByType('resource').some((r) => r.name.includes('/datos/vision/'))"))
    ctx.close()
    b.close()
print("ERRORES:", errores or "ninguno")
