exec(open("maps9.py", encoding="utf-8").read())
errores = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1360, "height": 860}); pg = ctx.new_page(); pg.route("**/*", ruta)
    pedidas = []
    pg.on("request", lambda r: pedidas.append(r.url) if any(k in r.url for k in ("idee.es/wms-inspire/riesgos", "enaire", "waymarkedtrails", "openseamap", "gibs.earthdata", "/export?", "unidades-administrativas")) else None)
    pg.on("console", lambda m: errores.append(m.text[:300]) if m.type == "error" and "ERR_FAILED" not in m.text else None)
    pg.on("pageerror", lambda e: errores.append(f"EXC: {e}"))
    pg.goto("http://127.0.0.1:8779/"); pg.wait_for_selector("#lista li"); pg.wait_for_timeout(600)
    pg.evaluate("mapa.setView([39.4699, -0.3763], 15, {animate: false})"); pg.wait_for_timeout(400)
    print("superpuestas:", pg.evaluate("Object.keys(SUPERPUESTAS).length"), "| fondos:", pg.evaluate("document.getElementById('capa-fondo').options.length"), "| rótulo València:", pg.evaluate("[...document.querySelectorAll('#capas-superponer .grupo-capas')].map(x => x.textContent).join('|')"))
    for sid in ("inundable", "drones", "limites", "senderos", "ciclismo", "mar", "fuegos", "ruido", "pgou", "policia_zonas", "barrios", "censo", "zbe", "zas"):
        pg.evaluate(f"(() => {{ const c = document.getElementById('sup-{sid}'); c.checked = true; c.dispatchEvent(new Event('change')); }})()")
    pg.wait_for_timeout(1500)
    import collections
    por = collections.Counter(re.sub(r"https://([^/]+)/.*", r"\1", u) for u in pedidas)
    print("pedidas por servidor:", dict(por))
    print("ejemplo inundable:", next((u for u in pedidas if "riesgos" in u), "")[:330])
    print("ejemplo fuegos:", next((u for u in pedidas if "wms.cgi" in u), "")[:330])
    print("ejemplo arcgis:", next((u for u in pedidas if "/export?" in u and "Salud" in u), "")[:330])
    pg.evaluate("(() => { const s = document.getElementById('capa-fondo'); s.value = 'diario'; s.dispatchEvent(new Event('change')); })()"); pg.wait_for_timeout(700)
    print("satélite diario:", next((u for u in pedidas if "CorrectedReflectance" in u), "")[:200])
    pg.evaluate("(() => { const s = document.getElementById('capa-fondo'); s.value = 'auto'; s.dispatchEvent(new Event('change')); })()")
    # identificar en las zonas encendidas
    pg.evaluate("abrirElemento(puntoDe(L.latLng(39.4699, -0.3763))); 0"); pg.wait_for_timeout(1500)
    print("ficha del punto:", pg.evaluate("[...document.querySelectorAll('#ficha-elemento .bloque')].find(b => b.querySelector('h3') && b.querySelector('h3').textContent === 'Sobre este punto').innerText.replace(/\\n/g, ' | ')")[:900])
    print("identify:", vistos9.get("identify", "")[60:330])
    print("recordadas:", pg.evaluate("localStorage.getItem('osintmaps.superpuestas.v1')"))
    b.close()
print("ERRORES:", errores or "ninguno")
