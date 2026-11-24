"""La sala con los datos de verdad, en el ordenador, sin tocar el programa que está en marcha.

Copia el histórico (pulso.sqlite) a una carpeta aparte, pregunta una vez a cada fuente nueva y
lo sitúa como lo haría el recolector, calcula el cruce del histórico, prepara las fichas (con una
consulta real al Catastro) y sirve la sala en el puerto 8799. Si encuentra Chrome, hace capturas
en capturas-sala/ y se cierra; con «--abierta» se queda sirviendo hasta que se pare.

    python sala_real.py [carpeta de datos] [--abierta]

Por defecto la carpeta de datos es la de OSINT-Maps en la carpeta del usuario.
"""
import functools, json, os, shutil, sqlite3, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from osintmaps import cli
from osintmaps.red import nueva_sesion
from osintmaps.pulso import contexto
from osintmaps.pulso.catalogo import POR_ID
from osintmaps.pulso.sala import BASICO
from osintmaps.pulso.servidor import Pulso

AQUI = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
origen = Path(args[0]) if args else Path.home() / "OSINT-Maps" / "datos"
destino = AQUI / "datos-real"
CAPTURAS = AQUI / "capturas-sala"; CAPTURAS.mkdir(exist_ok=True)
PUERTO = 8799


def paso(texto):
    print(f"\n== {texto}", flush=True)


paso(f"Copia del histórico de {origen}")
destino.mkdir(exist_ok=True)
for viejo in destino.glob("pulso.sqlite*"):
    viejo.unlink()
fuente = sqlite3.connect(f"file:{(origen / 'pulso.sqlite').as_posix()}?mode=ro", uri=True)
copia = sqlite3.connect(destino / "pulso.sqlite")
fuente.backup(copia)
copia.close(); fuente.close()
print(f"{(destino / 'pulso.sqlite').stat().st_size / 1e6:.1f} MB")
ciudad = destino / "ciudad"
if not (ciudad / "barrios.geojson").exists():
    for otra in (AQUI.parent / "datos" / "ciudad", origen / "ciudad"):
        if (otra / "barrios.geojson").exists():
            shutil.copytree(otra, ciudad, dirs_exist_ok=True)
            break
sesion = nueva_sesion()
t0 = time.time()
print("contexto básico:", contexto.actualizar(destino, sesion, solo=BASICO) or "ya estaba", f"({time.time() - t0:.1f} s)")

pulso = Pulso(destino, recoger=True)          # el recolector se crea pero no se arranca: solo se usa para una toma de cada fuente
sala = pulso.sala
assert sala.zonas is not None, "sin barrios"
print(f"{len(sala.zonas.barrios)} barrios")

paso("Una toma de cada fuente nueva (situada y clasificada como en el recolector)")
rec = pulso.recolector
rec.zonas = sala.zonas
for ident in ("prensa", "bluesky", "mastodon", "meteoalarm", "dgt", "metro", "ora", "planificados", "partidos", "festivos", "ruido", "trenes"):
    t0 = time.time()
    bien = rec.tomar(POR_ID[ident])
    fila = pulso.almacen._filas("SELECT n, error FROM tomas WHERE fuente=? ORDER BY t DESC LIMIT 1", (ident,))
    print(f"{ident:13s} {'bien' if bien else 'FALLO':5s} {time.time() - t0:5.1f} s  n={fila[0][0] if fila else '-'}  {(fila[0][1] or '')[:120] if fila else ''}", flush=True)
for fuente_t, n, situados in pulso.almacen._filas("SELECT fuente, COUNT(*), SUM(barrio IS NOT NULL) FROM items GROUP BY fuente"):
    print(f"   textos de {fuente_t}: {n} ({situados} situados en un barrio)")
for ident, titulo, barrio, lugar, cat, urg in pulso.almacen._filas(
        "SELECT fuente, titulo, barrio, lugar, categoria, urgencia FROM items WHERE barrio IS NOT NULL ORDER BY t DESC LIMIT 12"):
    print(f"   [{ident}] {titulo[:70]!r} -> {sala.zonas.nombre(barrio)} / {lugar} · {cat} {urg}")
for tipo, n, situados in pulso.almacen._filas("SELECT tipo, COUNT(*), SUM(barrio IS NOT NULL OR lat IS NOT NULL) FROM agenda GROUP BY tipo ORDER BY 2 DESC LIMIT 12"):
    print(f"   agenda {tipo}: {n} ({situados} con sitio)")

paso("El cruce del histórico")
ahora = int(time.time())
primera = pulso.almacen._filas("SELECT MIN(t) FROM tomas WHERE ok=1")[0][0]
print(f"histórico desde {time.strftime('%d/%m %H:%M', time.localtime(primera))}")
t0 = time.time()
n = sala.cruce.reconstruir(primera, ahora // 600 * 600, sucesos_desde=ahora - 24 * 3600)
print(f"{n} intervalos en {time.time() - t0:.1f} s")
t0 = time.time()
sala.cruce.paso(ahora)
print(f"un paso: {time.time() - t0:.2f} s")
e = sala.cruce.estado
print("aprendiendo:", e.get("aprendiendo"), "| desplazamiento:", e.get("desplazamiento"))
barrios = sorted(((b, x) for b, x in e.get("barrios", {}).items() if b != "VLC"), key=lambda x: -x[1]["nivel"])
print("rasgos por barrio (uno cualquiera):", sorted(barrios[0][1]["valores"]) if barrios else "-")
for b, x in barrios[:8]:
    s = x["senales"][0] if x["senales"] else None
    print(f"   {sala.zonas.nombre(b):28s} nivel {x['nivel']:5.1f} {x['tipos']} {(s['rasgo'], s['valor'], s['normal'], s['z']) if s else ''}")
for ev in sala.cruce.eventos(ahora - 24 * 3600, ahora + 1):
    print(f"   SUCESO {ev['estado']:7s} {time.strftime('%H:%M', time.localtime(ev['inicio']))}-{time.strftime('%H:%M', time.localtime(ev['fin']))} "
          f"{ev['puntuacion']:5.1f} {ev['titulo']}")

paso("Fichas")
t0 = time.time()
print("resto del contexto:", contexto.actualizar(destino, sesion) or "ya estaba", f"({time.time() - t0:.1f} s)")
sala.fichas.olvidar()
t0 = time.time()
print("accidentes situados:", sala.fichas.situar_accidentes(), f"({time.time() - t0:.1f} s)")
t0 = time.time()
todos = sala.fichas.todos_los_barrios()
print(f"contexto de {len(todos)} barrios en {time.time() - t0:.1f} s; Russafa:", json.dumps(next((v for k, v in todos.items() if sala.zonas.nombre(k) == "Russafa"), {}), ensure_ascii=False)[:400])
for nombre, lat, lon in (("Plaza del Ayuntamiento", 39.46975, -0.37683), ("Lonja", 39.47437, -0.37854), ("Calle Sueca 20", 39.46163, -0.37393)):
    t0 = time.time()
    f = sala.lugar(lat, lon)
    print(f"   {nombre}: calle={f.get('calle')} barrio={f.get('barrio_nombre')} catastro={json.dumps(f.get('catastro'), ensure_ascii=False)[:300]} "
          f"patrimonio={[p['nombre'] for p in f['patrimonio']]} registro={len(f['registro'])} accidentes={len(f['accidentes'])} ({time.time() - t0:.1f} s)")

paso(f"Sala en http://127.0.0.1:{PUERTO}/sala.html")
for nombre, contenido in sala.ficheros_web().items():
    print(f"   {nombre}: {len(contenido) / 1000:.0f} KB")
cli._Servidor.carpeta_datos = destino
cli._Servidor.pulso = pulso
srv = cli.ServidorMapa(("127.0.0.1", PUERTO), functools.partial(cli._Servidor, directory=str(cli.CARPETA_WEB)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
chrome = next((c for c in (os.environ.get("CHROME", ""), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                           "/usr/bin/google-chrome") if c and Path(c).exists()), None)
if chrome:
    activos = [ev for ev in sala.cruce.eventos(ahora - 24 * 3600, ahora + 1)]
    russafa = next((c for c, b in sala.zonas.barrios.items() if b["nombre"] == "Russafa"), "")
    vistas = [("real-escritorio", "sala.html", "1600,960"), ("real-movil", "sala.html", "390,844"),
              ("real-lugar", "sala.html#lugar=39.47437,-0.37854", "1600,960"), ("real-comparar", "sala.html#comparar", "1600,960"),
              ("real-movilidad", "sala.html#movilidad", "1600,960"), ("real-barrio", f"sala.html#barrio={russafa}", "1600,960")]
    if activos:
        vistas.append(("real-suceso", f"sala.html#suceso={activos[0]['id']}", "1600,960"))
    for nombre, ruta, tam in vistas:
        salida = CAPTURAS / f"{nombre}.png"
        r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={tam}", "--virtual-time-budget=25000",
                            f"--user-data-dir={AQUI / '.chrome-sala'}", f"--screenshot={salida}", f"http://127.0.0.1:{PUERTO}/{ruta}"],
                           capture_output=True, text=True, timeout=120)
        print(f"   captura {salida.name}: {'bien' if salida.exists() else r.stderr[-300:]}")
if "--abierta" in sys.argv:
    print("Sirviendo; Ctrl+C para parar.", flush=True)
    try:
        while True:
            time.sleep(60)
            sala.cruce.paso()
    except KeyboardInterrupt:
        pass
srv.shutdown()
pulso.parar()
print("\nHECHO")
