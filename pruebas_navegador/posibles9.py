"""El repaso por años en el visor: la capa opcional de posibles abandonos y los vuelos anuales del ICV
(2017 a 2024) en la tira de la ficha y en la comparación de fotos."""
exec(open("maps9.py", encoding="utf-8").read())
sitios = json.load(open(datos / "candidatos.geojson"))["features"]
ID0 = sitios[0]["properties"]["id"]
LON0, LAT0 = sitios[0]["geometry"]["coordinates"][:2]
CAPA_POSIBLES = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [LON0 + 0.002, LAT0 + 0.001]}, "properties": {
    "id": "posible/0892613YJ2709S", "nombre": "Av Almendros Los 18 Godella", "nota": 22.1, "motivos": "Le crece vegetación dentro: del 9 % en 2017-2019 al 50 % en 2023-2025.",
    "serie": "2017: 4 %, 2018: 9 %, 2025: 50 %", "direccion": "AV ALMENDROS LOS 18 GODELLA (VALENCIA)", "refcat": "0892613YJ2709S", "uso": "residencial", "anio": 1960,
    "superficie": 15700, "derribado": False, "url": "https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCListaBienes.aspx?rc1=0892613&rc2=YJ2709S"}}]}
fichero = datos / "capa-posibles.geojson"
fichero.unlink(missing_ok=True)

errores = []
def comprobar(nombre, que, cierto):
    print(nombre, " bien " if cierto else " MAL  ", que)
    if not cierto: errores.append(f"{nombre}: {que}")
with sync_playwright() as p:
    b = p.chromium.launch()
    for nombre, vp in (("escritorio", {"width": 1360, "height": 860}), ("movil", {"width": 390, "height": 800})):
        ctx = b.new_context(viewport=vp, has_touch=(nombre == "movil")); pg = ctx.new_page(); pg.route("**/*", ruta)
        pg.on("console", lambda m: errores.append(f"{nombre} {m.type}: {m.text[:300]}") if m.type in ("error", "warning") and "ERR_FAILED" not in m.text else None)
        pg.on("pageerror", lambda e: errores.append(f"{nombre} EXC: {e}"))

        # --- sin el fichero: la capa ni se enseña, y pedirla no da error
        fichero.unlink(missing_ok=True)
        pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(3600)
        comprobar(nombre, "sin datos, la casilla de posibles está escondida", pg.evaluate("document.getElementById('estado-posibles').parentElement.hidden"))
        comprobar(nombre, "las otras capas fijas siguen a la vista", pg.evaluate("!document.getElementById('estado-dgt').parentElement.hidden"))

        # --- con el fichero
        fichero.write_text(json.dumps(CAPA_POSIBLES), encoding="utf-8")
        pg.reload(); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(3600)
        comprobar(nombre, "con datos, aparece en «Abandono y patrimonio»", pg.evaluate("(() => { const f = document.getElementById('estado-posibles').parentElement; return !f.hidden && f.textContent.includes('Posibles abandonos (fotos de 2017 a 2025)') && f.closest('details').querySelector('summary').textContent.includes('Abandono y patrimonio'); })()"))
        pg.evaluate("conmutarCapa(CAPA.posibles, true); 0"); pg.wait_for_timeout(400)
        comprobar(nombre, "encendida, con su único elemento", pg.evaluate("estado.posibles.elementos.size") == 1 and pg.evaluate("document.getElementById('estado-posibles').textContent") == "1")
        pg.evaluate("abrirElemento([...estado.posibles.elementos.values()][0], true); 0"); pg.wait_for_timeout(500)
        texto = pg.inner_text("#ficha-elemento")
        comprobar(nombre, "la ficha lleva el sitio por título", pg.inner_text("#ficha-elemento h2") == "Av Almendros Los 18 Godella" and "Posible abandono" in texto)
        comprobar(nombre, "el porqué y la serie por años", "Le crece vegetación dentro: del 9 % en 2017-2019 al 50 % en 2023-2025." in texto and "2017: 4 %, 2018: 9 %, 2025: 50 %" in texto)
        comprobar(nombre, "dirección, referencia, uso, año y planta con miles", all(x in texto for x in ("AV ALMENDROS LOS 18 GODELLA (VALENCIA)", "0892613YJ2709S", "residencial", "1960", "15.700 m²")))
        comprobar(nombre, "avisa de que es una sospecha sin comprobar", "sospecha sacada de comparar fotos aéreas, sin comprobar" in texto and "copas de árboles" in texto)
        comprobar(nombre, "enlace a la ficha de Catastro", pg.evaluate("[...document.querySelectorAll('#ficha-elemento a')].some((a) => a.href.includes('sedecatastro.gob.es') && a.href.includes('rc1=0892613'))"))
        if nombre == "movil": pg.evaluate("typeof ponerHoja === 'function' && ponerHoja('alta'); 0"); pg.wait_for_timeout(300)
        pg.screenshot(path=f"{nombre}-posibles.png")
        pg.evaluate("cerrarElemento(); conmutarCapa(CAPA.posibles, false); 0"); pg.wait_for_timeout(200)

        # --- los vuelos anuales del ICV
        opciones = pg.evaluate("[...document.querySelectorAll('#capa-historica optgroup')].map((g) => [g.label, [...g.children].map((o) => o.value)])")
        comprobar(nombre, f"grupo propio en la lista de fotos antiguas: {opciones[0]}", opciones[0] == ["Comunitat Valenciana, año a año (ICV)", [f"icv-{a}" for a in range(2024, 2016, -1)]])
        comprobar(nombre, "fuera de la Comunitat no se ofrecen", pg.evaluate("vuelosDe(42.3, -3.7).every((v) => !v.nombre.startsWith('icv-')) && vuelosDe(42.3, -3.7).length === vuelos.length"))
        dentro = pg.evaluate(f"vuelosDe({LAT0}, {LON0}).map((v) => v.rotulo)")
        comprobar(nombre, f"dentro, los ocho años seguidos y sin repetir los nacionales de esos años: {dentro[:10]}", dentro[:8] == [str(a) for a in range(2024, 2016, -1)] and len(dentro) == len(set(dentro)) and "2015" in dentro)
        pg.evaluate(f"abrirFicha(candidatos.find((c) => c.id === '{ID0}'), true); 0"); pg.wait_for_timeout(900)
        tira = pg.evaluate("[...document.querySelectorAll('#tira button span')].map((s) => s.textContent)")
        comprobar(nombre, f"la tira de la ficha: hoy y luego año a año: {tira[:10]}", tira[:9] == ["Hoy"] + [str(a) for a in range(2024, 2016, -1)])
        pg.evaluate("[...document.querySelectorAll('#tira button')].find((b) => b.textContent === '2022').click(); 0"); pg.wait_for_timeout(400)
        foto = pg.evaluate("document.querySelector('#aereo img').src")
        comprobar(nombre, "la foto grande de 2022 sale del servicio de ese año", "terramapas.icv.gva.es/0202_2022CVAL0025?" in foto and "LAYERS=2022CVAL0025_RGB" in foto and "SRS=EPSG%3A4326" in foto)
        comprobar(nombre, "y se puede comparar con hoy", pg.inner_text("#comparar") == "Comparar 2022 con hoy en el mapa")
        pg.evaluate("document.getElementById('comparar').click(); 0"); pg.wait_for_timeout(900)
        comprobar(nombre, "al comparar, la capa del mapa es la de 2022 con cortina", pg.evaluate("document.getElementById('capa-historica').value") == "icv-2022" and pg.evaluate("document.getElementById('usar-cortina').checked") and pg.inner_text("#cortina-etiqueta") == "2022")
        comprobar(nombre, "sus teselas se piden al servicio de 2022", "0202_2022CVAL0025" in teselas.get("icv-ultima", "") and "2022CVAL0025_RGB" in teselas.get("icv-ultima", ""))
        pg.evaluate("ponerHistorica(''); 0"); pg.wait_for_timeout(200)
        ctx.close()
    b.close()
fichero.unlink(missing_ok=True)
print("ERRORES:", errores or "ninguno")
