exec(open("maps9.py", encoding="utf-8").read())
errores = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for nombre, vp in (("escritorio", {"width": 1360, "height": 860}), ("movil", {"width": 390, "height": 800})):
        vistos9.clear()
        ctx = b.new_context(viewport=vp, has_touch=(nombre == "movil")); pg = ctx.new_page(); pg.route("**/*", ruta)
        pg.on("console", lambda m: errores.append(f"{nombre} {m.text[:300]}") if m.type == "error" and "ERR_FAILED" not in m.text else None)
        pg.on("pageerror", lambda e: errores.append(f"{nombre} EXC: {e}"))
        pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(600)
        pg.evaluate(f"mapa.setView([{LAT}, {LON}], 16, {{animate: false}})"); pg.wait_for_timeout(400)
        # horarios
        print(nombre, "horarios:", pg.evaluate("""JSON.stringify([
          horarioOSM('Mo-Fr 09:00-14:00,17:00-20:30; Sa 09:30-14:00', new Date(2026, 10, 23, 10, 0)),
          horarioOSM('Mo-Fr 09:00-14:00,17:00-20:30; Sa 09:30-14:00', new Date(2026, 10, 23, 15, 0)).cambio,
          horarioOSM('Mo-Fr 09:00-14:00, Sa 10:00-13:00', new Date(2026, 10, 22, 12, 0)).cambio,
          horarioOSM('24/7').cambio, horarioOSM('Mo-Su 20:00-02:00', new Date(2026, 10, 23, 1, 0)).abierto, horarioOSM('Mo-Su 20:00-02:00', new Date(2026, 10, 23, 1, 0)).cambio,
          horarioOSM('Mo-Sa 08:00-24:00; Su 00:00-24:00', new Date(2026, 10, 21, 23, 0)).cambio, horarioOSM('Jun-Sep: Mo-Fr 10:00-20:00'), horarioOSM('sunrise-sunset'),
          horarioOSM('Mo-Fr 08:00-20:00; PH off', new Date(2026, 10, 28, 9, 0)).cambio, horarioOSM('Tu-Su 10:00-14:00', new Date(2026, 10, 23, 9, 0)).cambio])"""))
        # sugerencias con el campo vacío
        pg.click("#buscar-texto"); pg.wait_for_timeout(300)
        print(nombre, "sugerencias:", pg.evaluate("document.querySelectorAll('#resultados-extra .categorias button').length"), "| visible:", pg.is_visible("#resultados-extra"))
        pg.screenshot(path=f"{nombre}-b1-sugerencias.png")
        # escribir «farmacia»
        pg.keyboard.type("farmacia", delay=30); pg.wait_for_timeout(900)
        print(nombre, "farmacia:", pg.evaluate("[...document.querySelectorAll('#resultados-extra li')].map(l => l.className ? '[' + l.textContent + ']' : l.querySelector('b').textContent + ' | ' + l.querySelector('small').textContent + ' | ' + l.querySelector('em').textContent).join('\\n   ')"))
        print(nombre, "photon:", vistos9.get("photon"), "| carto:", vistos9.get("carto"), "| nominatim:", vistos.get("nominatim"), "| url:", vistos9.get("photon-ultima", "")[-110:])
        pg.screenshot(path=f"{nombre}-b2-farmacia.png")
        centro = pg.evaluate("mapa.getCenter().lat.toFixed(4) + ',' + mapa.getCenter().lng.toFixed(4)")
        pg.wait_for_timeout(1300)
        print(nombre, "tras la pausa: nominatim", vistos.get("nominatim"), "| el mapa no se movió:", centro == pg.evaluate("mapa.getCenter().lat.toFixed(4) + ',' + mapa.getCenter().lng.toFixed(4)"),
              "| filas:", pg.evaluate("document.querySelectorAll('#resultados-extra li button').length"))
        # abrir el lugar de Photon
        pg.evaluate("[...document.querySelectorAll('#resultados-extra button')].find(b => b.textContent.includes('Farmacia del Carmen')).click()"); pg.wait_for_timeout(900)
        print(nombre, "ficha:", pg.inner_text("#ficha-elemento h2"), "|", pg.inner_text("#ficha-elemento .lugar")[:60], "| negocio:", pg.inner_text("#ficha-elemento .negocio").replace("\n", " / ")[:230])
        print(nombre, "  osm-api:", vistos9.get("osm-api", "")[-40:], "| chincheta:", pg.evaluate("mapa.hasLayer(chinchetaLugar)"), "| centro:", pg.evaluate("mapa.getCenter().lat.toFixed(4)"), "| capa:", pg.evaluate("elementoAbierto.capa"),
              "| datos:", pg.inner_text("#ficha-elemento .datos").replace("\n", " ")[:160])
        pg.screenshot(path=f"{nombre}-b3-ficha-negocio.png")
        print(nombre, "  recientes:", pg.evaluate("JSON.stringify(recientes.map(r => r.nombre))"))
        # categoría: farmacias cerca
        pg.fill("#buscar-texto", ""); pg.click("#buscar-texto"); pg.keyboard.type("farma", delay=30); pg.wait_for_timeout(300)
        pg.evaluate("[...document.querySelectorAll('#resultados-extra button')].find(b => b.textContent.includes('cerca de aquí')).click()"); pg.wait_for_timeout(1200)
        print(nombre, "cerca:", pg.evaluate("[...document.querySelectorAll('#resultados-extra li')].map(l => l.className ? '[' + l.textContent + ']' : l.querySelector('b').textContent + ' | ' + l.querySelector('small').textContent + ' | ' + l.querySelector('em').textContent + ' | ' + l.querySelector('button').className).join('\\n   ')"))
        print(nombre, "  consulta:", (vistos9.get("cerca") or "")[:160], "| dibujados:", pg.evaluate("grupoCerca.getLayers().length"), "| campo:", pg.input_value("#buscar-texto"))
        pg.screenshot(path=f"{nombre}-b4-cerca.png")
        pg.evaluate("[...document.querySelectorAll('#resultados-extra li button')].find(b => b.textContent.includes('Farmacia Sur')).click()"); pg.wait_for_timeout(700)
        print(nombre, "  ficha de la lista:", pg.inner_text("#ficha-elemento h2"), "|", pg.inner_text("#ficha-elemento .negocio").replace("\n", " / ")[:120])
        pg.click("#ficha-elemento .navegacion button"); pg.wait_for_timeout(300)
        print(nombre, "  al volver sigue la lista:", pg.is_visible("#resultados-extra"), pg.evaluate("document.querySelectorAll('#resultados-extra li button').length"))
        pg.evaluate("[...document.querySelectorAll('#resultados-extra .acciones button')].find(b => b.textContent === 'Quitar').click()"); pg.wait_for_timeout(300)
        print(nombre, "  quitar:", pg.evaluate("grupoCerca.getLayers().length"), repr(pg.input_value("#buscar-texto")), "| resultados visibles:", pg.is_visible("#resultados-extra"))
        # dirección con portal y gasolineras por categoría (capa «api»)
        pg.fill("#buscar-texto", "calle colon 20"); pg.wait_for_timeout(900)
        print(nombre, "portal:", pg.evaluate("[...document.querySelectorAll('#resultados-extra li button')].map(b => b.querySelector('b').textContent + ' | ' + b.querySelector('small').textContent).join(' ;; ')"))
        pg.fill("#buscar-texto", "gasolinera"); pg.wait_for_timeout(300)
        pg.evaluate("[...document.querySelectorAll('#resultados-extra button')].find(b => b.textContent.includes('cerca de aquí')).click()"); pg.wait_for_timeout(1200)
        print(nombre, "gasolineras cerca:", pg.evaluate("[...document.querySelectorAll('#resultados-extra li button')].filter(b => b.querySelector('b')).slice(0, 6).map(b => b.querySelector('b').textContent + ' | ' + b.querySelector('em').textContent).join(' ;; ')"))
        pg.fill("#buscar-texto", "39.5, -0.4"); pg.wait_for_timeout(300)
        print(nombre, "coordenadas:", pg.evaluate("[...document.querySelectorAll('#resultados-extra li')].map(l => l.textContent).join(' ;; ')")[:120])
        pg.fill("#buscar-texto", ""); pg.wait_for_timeout(200)
        ctx.close()
    b.close()
print("ERRORES:", errores or "ninguno")
