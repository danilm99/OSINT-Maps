"""El paso de «lo que dice la red» a «líneas, cierre, accesos y ficheros para la web» (experimentos/vision/detectar.py).

Sin gráfica ni internet: la red, la foto y la maqueta 3D se sustituyen por inventos. Hace falta lo que usa
el experimento (opencv, scikit-image), que el paquete no instala: si no está, la prueba se salta."""
import json
import sys
import types
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("skimage")
pytest.importorskip("shapely")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experimentos" / "vision"))


@pytest.fixture()
def D():
    import detectar
    return detectar


def _lienzo(D, lado):
    from preparar import CLASES
    return np.zeros((len(CLASES), lado, lado), np.float32)


def _raya(prob, clase, a, b, ancho, p):
    from preparar import CLASES
    m = np.zeros(prob.shape[1:], np.uint8)
    cv2.line(m, a, b, 1, ancho)
    c = CLASES.index(clase)
    prob[c][m > 0] = np.maximum(prob[c][m > 0], p)


def _resumen(D, prob, corte):
    return [(c, round(float(np.hypot(np.diff(v[:, 0]), np.diff(v[:, 1])).sum()) * 0.3)) for c, _, v in D.lineas_de(prob, corte)]


def test_las_clases_parecidas_se_trazan_juntas(D):
    from preparar import CLASES
    corte = {c: 0.5 for c in CLASES}
    # Un cercado con tres lados de muro y uno de valla: dos líneas, partidas donde cambia.
    prob, c = _lienzo(D, 1024), 512
    for a, b in (((c - 80, c - 60), (c + 80, c - 60)), ((c + 80, c - 60), (c + 80, c + 60)), ((c + 80, c + 60), (c - 80, c + 60))):
        _raya(prob, "muro", a, b, 3, 0.9)
    _raya(prob, "valla", (c - 80, c + 60), (c - 80, c - 60), 3, 0.7)
    lineas = dict(_resumen(D, prob, corte))
    assert set(lineas) == {"muro", "valla"} and 125 < lineas["muro"] < 137 and 30 < lineas["valla"] < 40
    # Una tapia con dos metros donde la valla puntúa más: es ruido y no la parte.
    prob = _lienzo(D, 1024)
    _raya(prob, "muro", (100, 300), (500, 300), 3, 0.8); _raya(prob, "valla", (300, 300), (307, 300), 3, 0.95)
    assert _resumen(D, prob, corte) == [("muro", 119)]
    # Lo mismo si el tramo corto de otra cosa cae al principio de la línea, o al principio y al final.
    prob = _lienzo(D, 1024)
    _raya(prob, "muro", (100, 400), (500, 400), 3, 0.8); _raya(prob, "valla", (100, 400), (108, 400), 3, 0.95)
    assert _resumen(D, prob, corte) == [("muro", 119)]
    _raya(prob, "seto", (492, 400), (500, 400), 3, 0.95)
    assert _resumen(D, prob, corte) == [("muro", 119)]
    # Mitad muro y mitad valla, sesenta metros de cada: dos líneas.
    prob = _lienzo(D, 1024)
    _raya(prob, "muro", (100, 600), (300, 600), 3, 0.8); _raya(prob, "valla", (300, 600), (500, 600), 3, 0.8)
    assert _resumen(D, prob, corte) == [("muro", 60), ("valla", 59)]
    # Una valla floja solo sale si su corte es más bajo.
    prob = _lienzo(D, 1024)
    _raya(prob, "valla", (100, 300), (500, 300), 3, 0.4)
    assert _resumen(D, prob, corte) == [] and _resumen(D, prob, {**corte, "valla": 0.3}) == [("valla", 119)]
    # Vías: el camino ancho es camino, la franja fina es senda aunque el modelo la llame camino, y la carretera no sale.
    prob = _lienzo(D, 1024)
    _raya(prob, "camino", (100, 500), (900, 520), 11, 0.9); _raya(prob, "camino", (100, 700), (900, 720), 3, 0.7)
    _raya(prob, "carretera", (100, 900), (900, 900), 21, 0.95); _raya(prob, "camino", (100, 900), (900, 900), 9, 0.6)
    vias = _resumen(D, prob, corte)
    assert [c for c, _ in vias] == ["camino", "senda"] and all(238 <= largo <= 241 for _, largo in vias)


def test_el_veredicto(D):
    assert D.veredicto({"en_pie_pct": 3, "vegetacion_pct": 90}) == "solar"                      # nada levanta: da igual la maleza
    assert D.veredicto({"en_pie_pct": 92, "vegetacion_pct": 91}) == "vegetacion"                # lo que levanta son árboles
    assert D.veredicto({"en_pie_pct": 92, "vegetacion_pct": 34, "liso_pct": 40}) == "ruina_vegetacion"
    assert D.veredicto({"en_pie_pct": 100, "vegetacion_pct": 6, "liso_pct": 55}) == "tejado"
    assert D.veredicto({"en_pie_pct": 60, "vegetacion_pct": 6, "liso_pct": 55}) == "ruina"
    assert D.veredicto({"vegetacion_pct": 6}) is None and D.veredicto({"en_pie_pct": 60}) is None  # sin altura o sin foto, no se dice nada


def test_de_un_sitio_a_los_ficheros_de_la_web(D, tmp_path, monkeypatch):
    from preparar import CLASES, IMAGEN, PIXEL
    from shapely.geometry import Polygon
    V = D.VENTANA
    lon, lat = -0.9, 39.5
    x, y = D.a_utm(lon, lat)
    x0, y0 = round(x - V * PIXEL / 2, 2), round(y - V * PIXEL / 2, 2)
    huella = Polygon([D.a_geo(x + dx, y + dy) for dx, dy in ((-10, -7), (10, -7), (10, 7), (-10, 7))])
    # Un edificio de 20 x 14 m cercado por tres lados de muro y uno de valla, con un camino que llega hasta él.
    prob, c = _lienzo(D, V // 2), V // 4
    for a, b in (((c - 80, c - 60), (c + 80, c - 60)), ((c + 80, c - 60), (c + 80, c + 60)), ((c + 80, c + 60), (c - 80, c + 60))):
        _raya(prob, "muro", a, b, 3, 0.9)
    _raya(prob, "valla", (c - 80, c + 60), (c - 80, c - 60), 3, 0.6)
    _raya(prob, "camino", (0, c), (c - 50, c), 11, 0.9)
    monkeypatch.setattr(D, "predecir", lambda *a, **k: prob)
    azar = np.random.default_rng(1)
    rgb = np.clip(120 + azar.normal(0, 12, (V, V, 3)), 0, 255).astype(np.uint8)
    irg = np.clip(100 + azar.normal(0, 12, (V, V, 3)), 0, 255).astype(np.uint8)
    irg[V // 2 - 20:V // 2 + 20, V // 2 - 30:V // 2 + 30, 0] = 220             # un poco de vegetación dentro
    sitio = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {"id": "cat-PRUEBA1", "puntuacion": 50}}
    bajado = {"sitio": sitio, "x0": x0, "y0": y0, "rgb": rgb, "irg": irg, "altura": {"altura_mediana_m": 4.2, "pct_en_pie": 55}}
    corte = {k: 0.5 for k in CLASES}

    r = D.analizar(None, None, None, None, bajado, huella, "lineas-prueba", corte)
    assert r["largo_m"]["muro"] > 100 and 25 < r["largo_m"]["valla"] < 45 and r["largo_m"]["camino"] > 100
    assert r["cerrado_pct"] >= 90 and r["accesos"] == 1 and r["estado"] == "ruina" and r["altura_m"] == 4.2
    assert 10 < r["vegetacion_pct"] < 30 and r["centro"] == [lon, lat]
    sin_contorno = D.analizar(None, None, None, None, bajado, None, "lineas-prueba", corte)
    assert "estado" not in sin_contorno and "cerrado_pct" not in sin_contorno and sin_contorno["largo_m"] == r["largo_m"]
    assert D.analizar(None, None, None, None, {**bajado, "rgb": np.full((V, V, 3), 255, np.uint8)}, huella, "m", corte) is None   # fuera de la foto

    # Lo que se publica: un resumen y un fichero de líneas por sitio, en poco sitio y sin perder precisión.
    base, datos = tmp_path / "trabajo", tmp_path / "datos"
    (base / "resultados" / IMAGEN / "lineas-prueba").mkdir(parents=True)
    (base / "resultados" / IMAGEN / "lineas-prueba" / "cat-PRUEBA1.json").write_text(json.dumps(r), encoding="utf-8")
    (base / "modelos").mkdir()
    (base / "modelos" / "lineas-prueba-umbrales.json").write_text(json.dumps({"elegido": {
        "muro": {"corte": 0.4, "precision": 0.612, "alcance": 0.48, "f1": 0.5}, "cierre": {"corte": 0.4, "precision": 0.7, "alcance": 0.6, "f1": 0.6},
        "edificio": {"corte": 0.5, "precision": 0.9, "alcance": 0.9, "f1": 0.9}}}), encoding="utf-8")
    (datos / "vision").mkdir(parents=True)
    (datos / "vision" / "de-otra-pasada.json").write_text("{}", encoding="utf-8")
    D.empaquetar(base, datos, "lineas-prueba")
    revision = json.loads((datos / "revision.json").read_text(encoding="utf-8"))
    assert revision["imagen"] == IMAGEN and revision["modelo"] == "lineas-prueba" and revision["radio_m"] == 154
    assert revision["fiabilidad"] == {"muro": {"precision": 61, "alcance": 48}}          # solo las clases que se pintan
    assert revision["sitios"]["cat-PRUEBA1"]["estado"] == "ruina" and "lineas" not in revision["sitios"]["cat-PRUEBA1"]
    assert sorted(p.name for p in (datos / "vision").iterdir()) == ["cat-PRUEBA1.json"]
    assert D.cortes_de(base, "lineas-prueba")["muro"] == 0.4 and "cierre" not in D.cortes_de(base, "lineas-prueba")
    publicado = json.loads((datos / "vision" / "cat-PRUEBA1.json").read_text(encoding="utf-8"))
    lon0, lat0 = publicado["o"]
    for (clase, _, saltos), original in zip(publicado["l"], r["lineas"]):               # se descifra como en vision.js
        px = py = 0
        puntos = []
        for k in range(0, len(saltos), 2):
            px += saltos[k]; py += saltos[k + 1]
            puntos.append([round(lon0 + px / 1e6, 6), round(lat0 + py / 1e6, 6)])
        assert clase == original["c"] and puntos == original["g"]

    # Las fotos y la altura se piden una sola vez: la segunda pasada (otro modelo) no baja nada.
    class Respuesta:
        def __init__(self, img):
            self.status_code, self.headers, self.content = 200, {"Content-Type": "image/jpeg"}, cv2.imencode(".jpg", img)[1].tobytes()

    class Sesion:
        veces = 0

        def get(self, url, params=None, timeout=None):
            Sesion.veces += 1
            return Respuesta(rgb[:, :, ::-1] if "RGB" in params["LAYERS"] else irg[:, :, ::-1])

    medidas = []
    falsa = types.ModuleType("malla")
    falsa.medir = lambda mallas, h, lat: (medidas.append(1), {"altura_mediana_m": 3.3, "pct_en_pie": 40})[1]
    monkeypatch.setitem(sys.modules, "malla", falsa)
    for carpeta in (base / "ventanas" / IMAGEN, base / "alturas"):
        carpeta.mkdir(parents=True)
    D.bajar_sitio(Sesion(), {}, sitio, huella, base, True, True)
    otra = D.bajar_sitio(Sesion(), {}, sitio, huella, base, True, True)
    assert Sesion.veces == 2 and len(medidas) == 1
    assert otra["rgb"].shape == (V, V, 3) and otra["altura"]["pct_en_pie"] == 40
    assert sorted(p.name for p in (base / "ventanas" / IMAGEN).iterdir()) == ["cat-PRUEBA1_irg.jpg", "cat-PRUEBA1_rgb.jpg"]
    D.bajar_sitio(Sesion(), {}, sitio, huella, base, True, False)                       # sin guardar copia, vuelve a pedir
    assert Sesion.veces == 4
