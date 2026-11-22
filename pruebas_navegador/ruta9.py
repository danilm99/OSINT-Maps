exec(open("maps9.py", encoding="utf-8").read())
errores = []
solo = sys.argv[1] if len(sys.argv) > 1 else ""
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    for nombre, vp in (("escritorio", {"width": 1360, "height": 860}), ("movil", {"width": 390, "height": 800})):
        if solo and solo != nombre: continue
        vistos9.clear(); ESCENA.update(photon="bien", transitous="bien", osrm="bien")
        ctx = b.new_context(viewport=vp, has_touch=(nombre == "movil"), geolocation={"latitude": LAT - 0.0004, "longitude": LON - 0.0008, "accuracy": 12}, permissions=["geolocation"])
        pg = ctx.new_page(); pg.route("**/*", ruta)
        pg.on("console", lambda m: errores.append(f"{nombre} {m.text[:300]}") if m.type == "error" and "ERR_FAILED" not in m.text else None)
        pg.on("pageerror", lambda e: errores.append(f"{nombre} EXC: {e}"))
        pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(600)
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 16, {{animate: false}})"); pg.wait_for_timeout(400)
        if nombre == "movil":
            print("movil buscador sobre el mapa:", pg.evaluate("document.getElementById('buscador').parentElement.id"), "| hoja:", pg.evaluate("hojaActual()"),
                  "| alto mapa:", pg.evaluate("document.getElementById('mapa').getBoundingClientRect().height"), "| alto panel:", pg.evaluate("Math.round(document.getElementById('panel').getBoundingClientRect().height)"))
            pg.screenshot(path="movil-r0-inicio.png")
        # ruta hasta un punto: sale de «tu posición»
        pg.evaluate(f"rutaHasta(L.latLng({LAT + 0.0005}, {LON + 0.0005}), 'Farmacia del Carmen'); 0"); pg.wait_for_timeout(3200)
        print(nombre, "ficha de ruta visible:", pg.is_visible("#ficha-ruta"), "| origen:", pg.input_value("#ruta-origen"), "| destino:", pg.input_value("#ruta-destino"))
        print(nombre, "modos:", pg.evaluate("[...document.querySelectorAll('.modos-ruta button')].map(b => b.textContent.trim() + (b.getAttribute('aria-selected') === 'true' ? '*' : '')).join(' | ')"))
        print(nombre, "pedidos:", {k: v for k, v in vistos9.items() if k.startswith("osrm-") and k != "osrm-ultima" or k == "plan"}, "|", vistos9.get("osrm-ultima", "")[-150:])
        print(nombre, "opciones:", pg.evaluate("[...document.querySelectorAll('.opcion-ruta .cabeza')].map(c => c.innerText.replace(/\\n/g, ' / ')).join(' || ')"))
        print(nombre, "pasos:", pg.evaluate("[...document.querySelectorAll('.pasos-ruta > li > button')].map(c => c.innerText.replace(/\\n/g, ' / ')).join(' || ')"))
        print(nombre, "tarjeta:", pg.inner_text("#tarjeta-mapa").replace("\n", " / "), "| capas de la ruta:", pg.evaluate("ruta.capa.getLayers().length"), "| punto azul:", pg.evaluate("!!marcadorYo"))
        pg.screenshot(path=f"{nombre}-r1-ruta-pie.png")
        # elegir la alternativa
        pg.evaluate("document.querySelectorAll('.opcion-ruta .cabeza')[1].click()"); pg.wait_for_timeout(300)
        print(nombre, "alternativa:", pg.evaluate("document.querySelector('.opcion-ruta.elegida .cabeza').innerText.replace(/\\n/g, ' / ')"), "| pasos:", pg.evaluate("document.querySelectorAll('.pasos-ruta > li').length"))
        # coche
        pg.click(".modos-ruta button[data-modo=coche]"); pg.wait_for_timeout(500)
        print(nombre, "coche:", pg.evaluate("document.querySelector('.opcion-ruta.elegida .cabeza').innerText.replace(/\\n/g, ' / ')"), "| guardado:", pg.evaluate("leerLocal('osintmaps.modo-ruta.v1')"))
        # transporte público
        pg.click(".modos-ruta button[data-modo=publico]"); pg.wait_for_timeout(600)
        print(nombre, "transporte:", pg.evaluate("[...document.querySelectorAll('.opcion-ruta .cabeza')].map(c => c.innerText.replace(/\\n/g, ' / ')).join(' || ')"))
        print(nombre, "  tramos:", pg.evaluate("[...document.querySelectorAll('.pasos-ruta > li > button')].map(c => c.innerText.replace(/\\n/g, ' / ')).join(' || ')"))
        print(nombre, "  plan:", vistos9.get("plan-ultima", "")[-160:], "| líneas dibujadas:", pg.evaluate("ruta.capa.getLayers().length"), "| selector de hora:", pg.is_visible(".cuando-ruta select"))
        pg.screenshot(path=f"{nombre}-r2-transporte.png")
        pg.evaluate("document.querySelector('.pasos-ruta > li:nth-child(2) > button').click()"); pg.wait_for_timeout(300)
        print(nombre, "  paso marcado en el mapa:", pg.evaluate("mapa.hasLayer(ruta.marcaPaso)"), "| paradas intermedias:", pg.evaluate("document.querySelectorAll('.pasos-ruta details li').length"))
        pg.select_option(".cuando-ruta select", "llegar"); pg.wait_for_timeout(700)
        print(nombre, "  llegar a las:", "arriveBy=true" in vistos9.get("plan-ultima", ""), "| campo de hora:", pg.is_visible(".cuando-ruta input"))
        # sin transporte
        ESCENA["transitous"] = "vacio"; pg.select_option(".cuando-ruta select", "ahora"); pg.wait_for_timeout(700)
        print(nombre, "  sin viajes:", pg.inner_text("#ruta-cuerpo .pendiente")[:90]); ESCENA["transitous"] = "bien"
        # otra ficha encima: la ruta sigue y se puede volver
        pg.evaluate("abrirElemento(puntoDe(mapa.getCenter())); 0"); pg.wait_for_timeout(400)
        print(nombre, "otra ficha: ruta oculta", not pg.is_visible("#ficha-ruta"), "| tarjeta:", pg.inner_text("#tarjeta-mapa").replace("\n", " / ")[:110])
        pg.evaluate("[...document.querySelectorAll('#tarjeta-mapa button')].find(b => b.textContent === 'Ver la ruta').click()"); pg.wait_for_timeout(300)
        print(nombre, "  de vuelta:", pg.is_visible("#ficha-ruta"), "| elemento cerrado:", pg.evaluate("elementoAbierto === null"))
        # cambiar el origen escribiendo
        pg.click("#ruta-origen"); pg.wait_for_timeout(200)
        print(nombre, "sugerencias al entrar:", pg.evaluate("[...document.querySelectorAll('.sugerencias-ruta b')].map(b => b.textContent).join(' | ')"))
        pg.keyboard.type("farmacia", delay=20); pg.wait_for_timeout(800)
        print(nombre, "sugerencias:", pg.evaluate("[...document.querySelectorAll('.sugerencias-ruta b')].map(b => b.textContent).join(' | ')"))
        pg.evaluate("[...document.querySelectorAll('.sugerencias-ruta button')].find(b => b.textContent.includes('Calle de la Farmacia')).click()"); pg.wait_for_timeout(1200)
        print(nombre, "origen nuevo:", pg.input_value("#ruta-origen"), "|", vistos9.get("osrm-ultima", "").split("/")[-1][:50], "| yo:", pg.evaluate("!!ruta.origen.yo"))
        pg.click(".extremos-ruta .invertir"); pg.wait_for_timeout(900)
        print(nombre, "invertida:", pg.input_value("#ruta-origen"), "→", pg.input_value("#ruta-destino"))
        # elegir en el mapa
        pg.click("#ruta-destino"); pg.wait_for_timeout(200)
        pg.evaluate("[...document.querySelectorAll('.sugerencias-ruta button')].find(b => b.textContent.includes('Elegir en el mapa')).click()"); pg.wait_for_timeout(400)
        print(nombre, "eligiendo:", pg.evaluate("ruta.eligiendo"), "| tarjeta:", pg.inner_text("#tarjeta-mapa").replace("\n", " / ")[:70], "| hoja:", pg.evaluate("typeof hojaActual === 'function' ? hojaActual() : ''"))
        caja = pg.evaluate("(() => { const r = document.getElementById('mapa').getBoundingClientRect(); return [r.left + r.width / 2 + 30, r.top + r.height / 2 + 20]; })()")
        pg.mouse.click(*caja); pg.wait_for_timeout(1200)
        print(nombre, "destino elegido:", pg.input_value("#ruta-destino"), "| ficha:", pg.is_visible("#ficha-ruta"))
        # sin camino
        ESCENA["osrm"] = "sin-ruta"; pg.click(".modos-ruta button[data-modo=pie]"); pg.evaluate("calcularRuta(); 0"); pg.wait_for_timeout(900)
        print(nombre, "sin camino:", pg.inner_text("#ruta-cuerpo .pendiente")[:70], "| tarjeta:", pg.inner_text("#tarjeta-mapa").replace("\n", " / ")[:60]); ESCENA["osrm"] = "bien"
        # quitar
        pg.evaluate("[...document.querySelectorAll('#ficha-ruta .navegacion button')].find(b => b.textContent === 'Quitar la ruta').click()"); pg.wait_for_timeout(300)
        print(nombre, "quitada:", not pg.is_visible("#ficha-ruta"), not pg.is_visible("#tarjeta-mapa"), pg.evaluate("ruta.capa.getLayers().length"), "| lista:", pg.is_visible("#lista"))
        # menú contextual: desde aquí y hasta aquí
        pg.evaluate(f"rutaDesde(L.latLng({LAT - 0.0004}, {LON - 0.0008})); 0"); pg.wait_for_timeout(300)
        print(nombre, "desde aquí:", pg.input_value("#ruta-origen"), "| pide destino:", pg.inner_text("#ruta-cuerpo")[:60])
        pg.evaluate(f"rutaHasta(L.latLng({LAT + 0.0005}, {LON + 0.0005})); 0"); pg.wait_for_timeout(1500)
        print(nombre, "hasta aquí:", pg.evaluate("document.querySelector('.opcion-ruta.elegida .cabeza b').textContent"), "| modo recordado:", pg.evaluate("ruta.modo"))
        # seguir la posición: a mitad de camino queda menos
        pg.evaluate("quitarRuta(); 0")
        pg.evaluate(f"rutaHasta(L.latLng({LAT + 0.0005}, {LON + 0.0005}), 'Destino'); 0"); pg.wait_for_timeout(2500)
        ctx.set_geolocation({"latitude": LAT + 0.0002, "longitude": LON, "accuracy": 8}); pg.wait_for_timeout(1500)
        print(nombre, "en marcha:", pg.inner_text("#tarjeta-mapa").replace("\n", " / ")[:80], "| progreso:", pg.evaluate("JSON.stringify(ruta.progreso && { m: Math.round(ruta.progreso.metros), fuera: ruta.progreso.fuera })"))
        n = vistos9.get("osrm-foot", 0)
        ctx.set_geolocation({"latitude": LAT + 0.004, "longitude": LON - 0.004, "accuracy": 8}); pg.wait_for_timeout(1500)
        print(nombre, "fuera de ruta: recalcula", vistos9.get("osrm-foot", 0) > n, "|", vistos9.get("osrm-ultima", "").split("/")[-1][:24])
        pg.evaluate("quitarRuta(); 0"); pg.wait_for_timeout(200)
        if nombre == "movil":
            # la hoja
            pg.evaluate("ponerHoja('media')"); pg.wait_for_timeout(400)
            a = pg.evaluate("document.getElementById('asa-hoja').getBoundingClientRect().top")
            pg.evaluate("ponerHoja('alta')"); pg.wait_for_timeout(400)
            print("movil hoja alta:", pg.evaluate("Math.round(document.getElementById('panel').getBoundingClientRect().height)"), "| mapa:", pg.evaluate("Math.round(document.getElementById('mapa').getBoundingClientRect().height)"))
            pg.evaluate("ponerHoja('minima')"); pg.wait_for_timeout(400)
            print("movil hoja mínima:", pg.evaluate("Math.round(document.getElementById('panel').getBoundingClientRect().height)"), "| mapa:", pg.evaluate("Math.round(document.getElementById('mapa').getBoundingClientRect().height)"), "| tamaño que cree Leaflet:", pg.evaluate("mapa.getSize().y"))
            pg.screenshot(path="movil-r3-hoja-minima.png")
            # arrastrar el asa hacia arriba
            r = pg.evaluate("(() => { const r = document.getElementById('asa-hoja').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
            pg.mouse.move(*r); pg.mouse.down(); pg.mouse.move(r[0], r[1] - 150, steps=6); pg.mouse.move(r[0], r[1] - 330, steps=6); pg.mouse.up(); pg.wait_for_timeout(500)
            print("movil tras arrastrar:", pg.evaluate("hojaActual()"), pg.evaluate("Math.round(document.getElementById('panel').getBoundingClientRect().height)"))
            pg.click("#asa-hoja"); pg.wait_for_timeout(400); print("movil toque en el asa:", pg.evaluate("hojaActual()"))
            pg.click("#buscar-texto"); pg.wait_for_timeout(500)
            print("movil al buscar:", pg.evaluate("hojaActual()"), "| sugerencias:", pg.is_visible("#resultados-extra .categorias"))
            pg.screenshot(path="movil-r4-buscando.png")
            pg.keyboard.type("farmacia", delay=20); pg.wait_for_timeout(800)
            pg.evaluate("[...document.querySelectorAll('#resultados-extra button')].find(b => b.textContent.includes('Farmacia del Carmen')).click()"); pg.wait_for_timeout(900)
            print("movil al abrir el resultado:", pg.evaluate("hojaActual()"), "|", pg.inner_text("#ficha-elemento h2"))
            pg.screenshot(path="movil-r5-ficha.png")
            pg.click(".como-llegar"); pg.wait_for_timeout(2500)
            pg.screenshot(path="movil-r6-ruta.png")
            pg.evaluate("quitarRuta(); 0")
        ctx.close()
    b.close()
print("ERRORES:", errores or "ninguno")
