"""El repaso por años (experimentos/vision/cambios.py): de las fotos de varios años a una lista de posibles abandonos.

Sin internet: las fotos se inventan (un tejado, un jardín, plantas que crecen dentro) y Catastro es un ZIP de mentira.
Hace falta opencv, que el paquete no instala: si no está, la prueba se salta."""
import io
import json
import sys
import types
import zipfile
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("shapely")
from shapely.geometry import box  # noqa: E402

from .conftest import CABECERA, X0, Y0, edificio  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experimentos" / "vision"))

SUELO, PLANTA, TEJADO, TEJA = (110, 105, 100), (200, 60, 80), (150, 140, 120), (190, 150, 95)      # en (infrarrojo, rojo, verde)


@pytest.fixture()
def K():
    import cambios
    return cambios


def _foto(K, x0, y0, edificios, lado=512, verde_a_la_izquierda=200):
    """Un recorte inventado: suelo, una franja de vegetación a la izquierda y los edificios que se pidan.

    Cada edificio es (contorno, color del tejado, parte del centro cubierta de plantas)."""
    img = np.zeros((lado, lado, 3), np.uint8)
    img[:] = SUELO
    img[:, :verde_a_la_izquierda] = PLANTA
    y1 = y0 + K.VENTANA_M
    for geom, color, plantas in edificios:
        bx0, by0, bx1, by1 = geom.bounds
        c0, c1, f0, f1 = int((bx0 - x0) / 0.5), int((bx1 - x0) / 0.5), int((y1 - by1) / 0.5), int((y1 - by0) / 0.5)
        img[f0:f1, c0:c1] = color
        if plantas:
            alto, ancho = f1 - f0, c1 - c0
            lado_p = int((plantas * alto * ancho) ** 0.5)
            a, b = f0 + (alto - lado_p) // 2, c0 + (ancho - lado_p) // 2
            img[a:a + lado_p, b:b + lado_p] = PLANTA
    ruido = np.random.default_rng(7).normal(0, 3, img.shape)
    return np.clip(img + ruido, 0, 255).astype(np.uint8)


def test_la_teja_no_cuenta_como_planta_y_las_plantas_si(K):
    casa = box(300, 300, 320, 316)
    limpia = K.medir_edificio(_foto(K, 200, 200, [(casa, TEJA, 0)]), casa, 200, 456, 0.5)
    con_plantas = K.medir_edificio(_foto(K, 200, 200, [(casa, TEJA, 0.3)]), casa, 200, 456, 0.5)
    alto = int((0.2 - K.NDVI_MIN) / K.NDVI_ANCHO)                   # tramos por encima de NDVI 0,2
    # La teja refleja mucho infrarrojo (NDVI 0,12 en esta foto inventada), pero es rojiza: nada de ella pasa por planta.
    assert sum(limpia["v"][alto:]) == 0 and sum(limpia["k"][alto:]) == 0
    assert 0.2 < sum(con_plantas["v"][alto:]) / con_plantas["n"] < 0.45
    assert sum(con_plantas["k"][alto:]) / sum(con_plantas["k"]) > 0.6       # en el centro, casi todo
    # Alrededor hay un tercio de vegetación (la franja de la izquierda), igual en las dos.
    assert sum(limpia["a"][alto:]) > 0 and limpia["a"] == pytest.approx(con_plantas["a"], abs=40)


def test_lo_estrecho_y_lo_liso_no_se_miden(K):
    foto = _foto(K, 200, 200, [])
    assert K.medir_edificio(foto, box(300, 300, 303, 340), 200, 456, 0.5) is None        # 3 m de ancho: no queda interior
    liso = np.full((512, 512, 3), 255, np.uint8)                                          # borde de un vuelo: todo blanco
    assert K.medir_edificio(liso, box(300, 300, 320, 316), 200, 456, 0.5) is None


def _series(K, casos):
    """Mide, año a año, un edificio por caso: (parte cubierta de plantas cada año, color del tejado)."""
    casa = box(300, 300, 320, 316)
    return {ref: {anio: K.medir_edificio(_foto(K, 200, 200, [(casa, color, v)]), casa, 200, 456, 0.5) for anio, v in zip(K.ANIOS, plantas)}
            for ref, (plantas, color) in casos.items()}


def test_de_las_series_a_la_nota(K):
    casos = {"sano": ([0] * 9, TEJA), "crece": ([0, 0, 0, .05, .1, .2, .3, .4, .5], TEJADO), "ruina": ([.5] * 9, TEJADO)}
    casos.update({f"n{k}": ([0] * 9, TEJA if k % 2 else TEJADO) for k in range(40)})
    series = _series(K, casos)
    cal = K.calibrar(series, {r for r in series if r != "ruina"})
    assert set(cal) == set(K.ANIOS)
    assert all(6 <= c["veg"] <= 11 for c in cal.values())            # el corte de vegetación sale entre NDVI 0,10 y 0,35
    rasgos = {ref: K.rasgos(serie, cal) for ref, serie in series.items()}
    assert rasgos["sano"]["veg"].max() == 0 and rasgos["ruina"]["nuc"].min() > 0.8
    assert rasgos["sano"]["alr"] == pytest.approx(np.full(9, 0.33), abs=0.05)
    finales = [K.resumen(r)[1] for ref, r in rasgos.items() if ref != "ruina"]
    normal = K.lo_normal(np.array([f["alr"] for f in finales]), np.array([f["nuc"] for f in finales]))
    assert K.juzgar(rasgos["sano"], normal) is None
    ruina, crece = K.juzgar(rasgos["ruina"], normal), K.juzgar(rasgos["crece"], normal)
    assert len(ruina["motivos"]) == 1 and "su entorno no explica" in ruina["motivos"][0]
    assert len(crece["motivos"]) == 2 and "le crece vegetación dentro: del 0 % en 2017-2019" in crece["motivos"][1]
    assert crece["nota"] > ruina["nota"] > 10
    assert crece["anios"] == list(K.ANIOS) and len(crece["nuc"]) == 9


def test_con_arbolado_alrededor_se_exige_mas(K):
    r = lambda dentro, fuera: {"anios": np.array(K.ANIOS[:len(dentro)]), "veg": np.array(dentro), "nuc": np.array(dentro), "alr": np.array(fuera),  # noqa: E731
                               "osc": np.zeros(len(dentro)), "rug": np.zeros(len(dentro))}
    azar = np.random.default_rng(0)
    entorno = azar.uniform(0, 1, 3000)
    normal = K.lo_normal(entorno, np.clip(azar.exponential(0.03, 3000) * (1 + 6 * entorno), 0, 1))
    assert list(normal[1]) == sorted(normal[1])                      # más verde fuera nunca baja el listón
    assert K.juzgar(r([.3] * 9, [.9] * 9), normal) is None           # un 30 % de copas en plena pinada es lo normal
    assert K.juzgar(r([.3] * 9, [.1] * 9), normal)["nota"] > 10      # el mismo 30 % sin árboles cerca no lo es
    crece = [0, 0, 0, .05, .1, .15, .2, .25, .3]
    assert K.juzgar(r(crece, [.95] * 9), normal) is None             # crecer un 25 % con todo arbolado alrededor: copas
    assert "le crece" in K.juzgar(r(crece, [.1] * 9), normal)["motivos"][-1]
    assert K.juzgar(r([0, .5, .6], [.1] * 3), normal) is not None and K.juzgar(r([0, .5], [.1] * 2), normal) is None       # con dos años no se dice nada


def test_la_maqueta_3d_corrige_la_nota(K):
    copas = {"nota": 40.0, "motivos": []}
    K.con_altura(copas, {"altura_mediana_m": 12.0, "altura_p90_m": 14.0, "pct_en_pie": 95}, 1)
    assert copas["nota"] == 12.0 and copas["copas"] and "copas de árboles" in copas["motivos"][0]
    caido = {"nota": 40.0, "motivos": []}
    K.con_altura(caido, {"altura_mediana_m": 0.2, "altura_p90_m": 1.0, "pct_en_pie": 5}, 2)
    assert caido["nota"] == 20.0 and caido["derribado"]
    a_medias = {"nota": 40.0, "motivos": []}
    K.con_altura(a_medias, {"altura_mediana_m": 2.6, "altura_p90_m": 4.0, "pct_en_pie": 40}, 1)
    assert a_medias["nota"] == 52.0 and "40 %" in a_medias["motivos"][0]
    sin_dato = {"nota": 40.0, "motivos": []}
    K.con_altura(sin_dato, None, 1)
    assert sin_dato == {"nota": 40.0, "motivos": []}


PIEZA = """  <gml:featureMember>
    <bu-ext2d:BuildingPart gml:id="ES.SDGC.BU.{ref}_part{n}">
      <bu-core2d:inspireId><base:Identifier><base:localId>{ref}_part{n}</base:localId><base:namespace>ES.SDGC.BU</base:namespace></base:Identifier></bu-core2d:inspireId>
      <bu-ext2d:geometry><bu-core2d:BuildingGeometry><bu-core2d:geometry>
         <gml:Surface gml:id="Surface_ES.SDGC.BU.{ref}_part{n}" srsName="urn:ogc:def:crs:EPSG::25830"><gml:patches><gml:PolygonPatch><gml:exterior><gml:LinearRing>
           <gml:posList srsDimension="2" count="5"> {x0} {y0} {x1} {y0} {x1} {y1} {x0} {y1} {x0} {y0}</gml:posList>
         </gml:LinearRing></gml:exterior></gml:PolygonPatch></gml:patches></gml:Surface>
      </bu-core2d:geometry></bu-core2d:BuildingGeometry></bu-ext2d:geometry>
      <bu-ext2d:numberOfFloorsAboveGround>{sobre}</bu-ext2d:numberOfFloorsAboveGround>
      <bu-ext2d:heightBelowGround uom="m">0</bu-ext2d:heightBelowGround>
      <bu-ext2d:numberOfFloorsBelowGround>{bajo}</bu-ext2d:numberOfFloorsBelowGround>
    </bu-ext2d:BuildingPart>
  </gml:featureMember>
"""


def _pieza(ref, n, dx, dy, ancho, alto, sobre, bajo=0):
    return PIEZA.format(ref=ref, n=n, x0=X0 + dx, y0=Y0 + dy, x1=X0 + dx + ancho, y1=Y0 + dy + alto, sobre=sobre, bajo=bajo)


@pytest.fixture()
def municipio(tmp_path):
    """Un municipio de mentira: una casa de campo con un sótano que asoma bajo el jardín, una nave que se llena de plantas,
    una ruina que Catastro ya conoce y cuarenta casas de pueblo apretadas."""
    edificios = [edificio("46999A00100001", 0, 0, 30, 20, uso="1_residential", anio=1950),          # rústica: la casa (20x20) más 10 m de sótano
                 edificio("000100200YJ00A", 400, 0, 24, 16, uso="3_industrial", anio=1970),           # diseminado: la nave
                 edificio("46999A00100002", 800, 0, 20, 16, estado="ruin", uso="2_agriculture", anio=1900)]
    piezas = [_pieza("46999A00100001", 1, 0, 0, 20, 20, 2), _pieza("46999A00100001", 2, 20, 0, 10, 20, 0, 1),
              _pieza("000100200YJ00A", 1, 400, 0, 24, 16, 1), _pieza("46999A00100002", 1, 800, 0, 20, 16, 1)]
    for k in range(40):                                                # el casco: casas de 10x10 cada 12 m
        ref = f"{1000 + k:07d}YJ0000X"
        edificios.append(edificio(ref, 2000 + 12 * (k % 8), 12 * (k // 8), 10, 10))
        piezas.append(_pieza(ref, 1, 2000 + 12 * (k % 8), 12 * (k // 8), 10, 10, 2))
    cache = tmp_path / "catastro"
    cache.mkdir()
    with zipfile.ZipFile(cache / "46999.zip", "w") as zf:
        zf.writestr("A.ES.SDGC.BU.46999.building.gml", (CABECERA + "".join(edificios) + "</gml:FeatureCollection>\n").encode("latin-1"))
        zf.writestr("A.ES.SDGC.BU.46999.buildingpart.gml", (CABECERA + "".join(piezas) + "</gml:FeatureCollection>\n").encode("latin-1"))
    return tmp_path


def _args(carpeta, **mas):
    base = dict(carpeta=str(carpeta / "vision"), catastro=str(carpeta / "catastro"), datos=str(carpeta / "datos"), municipios="46999", etiqueta="prueba",
                anios=",".join(str(a) for a in range(2017, 2026)), hilos=2, paso=0.5, min_superficie=60.0, max_vecinos=12, todos=False, guardar_fotos=False, rehacer=False,
                direcciones=0, alturas=0, cuantos=10, nota_minima=12.0, con_derribados=False)
    base.update(mas)
    return types.SimpleNamespace(**base)


def test_de_catastro_al_universo(K, municipio):
    args = _args(municipio)
    universo = {e["ref"]: e for e in K.cargar_universo(args)}
    # Fuera de casco: los dos de suelo rústico y el diseminado. Las casas del pueblo se quedan fuera (tienen decenas de vecinos).
    assert set(universo) == {"46999A00100001", "000100200YJ00A", "46999A00100002"}
    casa = universo["46999A00100001"]
    assert casa["area"] == 400 and casa["plantas"] == 2              # sin el sótano que asoma: solo lo que levanta del suelo
    assert casa["estado"] == "functional" and casa["uso"] == "residencial" and casa["anio"] == 1950 and casa["vecinos"] == 0
    assert universo["46999A00100002"]["estado"] == "ruin"
    assert len(K.cargar_universo(_args(municipio, todos=True))) == 43
    # La segunda vez sale del fichero guardado, con la misma geometría.
    otra = {e["ref"]: e for e in K.cargar_universo(args)}
    assert otra["46999A00100001"]["geom"].symmetric_difference(casa["geom"]).area < 1
    # Cada edificio va al recorte donde cae su centro, y cabe entero en él.
    recortes = K.recortes_de(list(universo.values()))
    assert sum(len(v[2]) for v in recortes.values()) == 3
    for x0, y0, dentro in recortes.values():
        for e in dentro:
            bx0, by0, bx1, by1 = e["geom"].bounds
            assert x0 < bx0 and bx1 < x0 + K.VENTANA_M and y0 < by0 and by1 < y0 + K.VENTANA_M


def test_medir_puntuar_y_la_capa_del_visor(K, municipio, monkeypatch, capsys):
    args = _args(municipio, todos=True)
    por_ref = {e["ref"]: e for e in K.cargar_universo(args)}
    pedidas = []

    def foto_falsa(sesion, anio, x0, y0, lado_px, copia=None):
        pedidas.append((anio, x0, y0))
        dentro = []
        for ref, e in por_ref.items():
            bx0, by0, bx1, by1 = e["geom"].bounds
            if x0 < bx0 and bx1 < x0 + K.VENTANA_M and y0 < by0 and by1 < y0 + K.VENTANA_M:
                plantas = {"000100200YJ00A": max(0.0, (anio - 2019) * 0.1), "46999A00100002": 0.5}.get(ref, 0.0)      # la nave se va llenando; la ruina ya lo estaba
                dentro.append((e["geom"], TEJA if ref[0] == "0" and ref != "000100200YJ00A" else TEJADO, plantas))
        return _foto(K, x0, y0, dentro, verde_a_la_izquierda=0)

    monkeypatch.setattr(K, "pedir", foto_falsa)
    K.medir(args)
    n_recortes = len(K.recortes_de(list(por_ref.values())))
    assert len(pedidas) == 9 * n_recortes
    assert "FIN-MEDIR" in capsys.readouterr().out
    K.medir(args)                                                     # relanzado: no vuelve a pedir nada
    assert len(pedidas) == 9 * n_recortes

    (municipio / "datos").mkdir()
    (municipio / "datos" / "candidatos.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    K.puntuar(args)
    dicho = capsys.readouterr().out
    assert "Catastro «ruin»: 1 edificios; con algún motivo, el 100.0 %" in dicho and "FIN-PUNTUAR" in dicho
    posibles = json.loads((municipio / "vision" / "cambios" / "posibles-prueba.json").read_text(encoding="utf-8"))
    assert [p["ref"] for p in posibles] == ["000100200YJ00A"]         # la nave; la ruina no, que Catastro ya la da por tal
    assert posibles[0]["uso"] == "industrial" and posibles[0]["plantas"] == 1 and len(posibles[0]["motivos"]) == 2
    todos = json.loads((municipio / "vision" / "cambios" / "todos-prueba.json").read_text(encoding="utf-8"))
    assert {t["ref"]: t["catastro"] for t in todos} == {"000100200YJ00A": "functional", "46999A00100002": "ruin"}

    # Lo que ya está en la lista de candidatos no es un hallazgo.
    (municipio / "datos" / "candidatos.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": {"id": "cat-x", "refcats": ["000100200YJ00A"]}}]}), encoding="utf-8")
    K.puntuar(args)
    assert json.loads((municipio / "vision" / "cambios" / "posibles-prueba.json").read_text(encoding="utf-8")) == []
    (municipio / "datos" / "candidatos.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    K.puntuar(args)

    K.capa(args)
    capa = json.loads((municipio / "datos" / "capa-posibles.geojson").read_text(encoding="utf-8"))
    (rasgo,) = capa["features"]
    p = rasgo["properties"]
    assert p["id"] == "posible/000100200YJ00A" and p["refcat"] == "000100200YJ00A" and p["superficie"] == 384 and p["nombre"] == "Edificio industrial de 384 m²"
    assert p["motivos"].startswith("Tiene vegetación dentro") and p["motivos"].endswith(".") and p["serie"].startswith("2017: 0 %") and "2025: " in p["serie"]
    assert p["url"].endswith("rc1=0001002&rc2=00YJ00A") and rasgo["geometry"]["type"] == "Point"
    lon, lat = rasgo["geometry"]["coordinates"]
    assert -1.0 < lon < 0.0 and 39.0 < lat < 40.0                    # UTM 30 (700.412, 4.380.008) pasado a grados
    # Con un listón más alto que su nota, se queda fuera del mapa.
    K.capa(_args(municipio, todos=True, nota_minima=posibles[0]["nota"] + 1))
    assert json.loads((municipio / "datos" / "capa-posibles.geojson").read_text(encoding="utf-8"))["features"] == []


def test_un_fallo_de_red_se_vuelve_a_pedir_y_un_ano_sin_foto_no(K, municipio, monkeypatch):
    args = _args(municipio)
    respuestas = {2017: "fuera", 2018: None}
    veces = []

    def foto_falsa(sesion, anio, x0, y0, lado_px, copia=None):
        veces.append(anio)
        return respuestas.get(anio, _foto(K, x0, y0, []))

    monkeypatch.setattr(K, "pedir", foto_falsa)
    K.medir(args)
    n = len(veces)
    K.medir(args)
    assert sorted(set(veces[n:])) == [2018]                           # solo se repite lo que falló por la red
    medidas = K.leer_medidas(municipio / "vision" / "cambios" / "medidas-prueba.jsonl")
    assert len(medidas) == 3 and all(sorted(serie) == list(range(2019, 2026)) for serie in medidas.values())      # ni el año sin foto ni el que falló


def test_con_el_tejado_de_cada_ano_manda_haberlo_perdido(K):
    r = lambda dentro, fuera: {"anios": np.array(K.ANIOS), "veg": np.array(dentro), "nuc": np.array(dentro), "alr": np.array(fuera),  # noqa: E731
                               "osc": np.zeros(9), "rug": np.zeros(9)}
    t = lambda visto: {str(a): v for a, v in zip(K.ANIOS, visto)}     # noqa: E731
    normal = ([0.05, 0.5, 0.9], [0.0, 0.15, 0.5])
    derribo = K.juzgar(r([0] * 9, [.02] * 9), normal, t([.9, .9, .9, 0, 0, 0, 0, 0, 0]))
    assert derribo["nota"] == 90.0 and derribo["motivos"] == ["tenía tejado y ya no se ve: del 90 % del contorno en 2017-2019 al 0 % en 2023-2025"]
    assert derribo["tej"] == [.9, .9, .9, 0, 0, 0, 0, 0, 0]
    invadido = K.juzgar(r([0, 0, 0, .1, .2, .4, .6, .7, .7], [.2] * 9), normal, t([.9, .9, .85, .8, .6, .4, .2, .1, .1]))
    assert len(invadido["motivos"]) == 2 and invadido["motivos"][1] == "y le ha entrado vegetación: del 0 % al 70 %" and invadido["nota"] > derribo["nota"]
    # Lo que la vegetación sola señalaba y con el tejado a la vista deja de serlo: una pizarra que parece planta, una copa que avanza.
    assert K.juzgar(r([.9] * 9, [.05] * 9), normal) is not None and K.juzgar(r([.9] * 9, [.05] * 9), normal, t([.95] * 9)) is None
    crece = [0, 0, 0, .1, .1, .2, .2, .3, .3]
    assert K.juzgar(r(crece, [.2] * 9), normal) is not None and K.juzgar(r(crece, [.2] * 9), normal, t([.9, .9, .9, .85, .85, .8, .8, .75, .7])) is None
    # Nunca se le vio tejado y tiene vegetación dentro: se apunta, con menos nota y diciendo las tres cosas que puede ser.
    nunca = K.juzgar(r([.6] * 9, [.2] * 9), normal, t([.05] * 9))
    assert 10 < nunca["nota"] < 40 and "contorno de Catastro corrido" in nunca["motivos"][0]
    # Con el tejado de solo un par de años no se puede comparar: se puntúa como si no lo hubiera.
    assert K.juzgar(r([.9] * 9, [.05] * 9), normal, {"2017": .9, "2025": .9})["motivos"][0].startswith("tiene vegetación dentro")


def test_las_etiquetas_del_detector_de_tejado():
    import tejado as T
    from shapely.strtree import STRtree
    assert T.origen_de("3_-2") == (3 * 224.0 - 16, -2 * 224.0 - 16) and T.origen_de("e_0892613YJ2709S") is None and T.origen_de("notas") is None
    assert sum(T.aparte(f"{i}_{j}") for i in range(30) for j in range(30)) == 90      # uno de cada diez recortes, por su sitio y no por su año
    casa, dudosa, estrecha = box(100, 100, 120, 116), box(150, 100, 160, 110), box(100, 150, 103, 190)
    geoms = [casa, dudosa, estrecha]
    etiqueta = T.etiqueta_de(STRtree(geoms), geoms, np.array([False, True, False]), 0.0, 0.0)
    y1 = T.LADO * T.PASO
    en = lambda x, y: int(etiqueta[int((y1 - y) / T.PASO), int(x / T.PASO)])      # noqa: E731
    assert en(110, 108) == 1 and en(60, 60) == 0                      # dentro de la casa y en el campo
    assert en(100.1, 108) == T.SIN_OPINION                            # el borde de un contorno no cuenta
    assert en(155, 105) == T.SIN_OPINION                              # ni el edificio que Catastro da por ruinoso
    assert set(np.unique(etiqueta)) == {0, 1, T.SIN_OPINION}
    filas, columnas, dentro = T.interior(casa, 0.0, 0.0)
    assert etiqueta[filas, columnas][dentro].tolist() == [1] * int(dentro.sum()) and 600 < dentro.sum() < 1280       # el interior, sin el margen
    assert T.interior(estrecha, 0.0, 0.0) is None and T.interior(box(5000, 5000, 5020, 5016), 0.0, 0.0) is None
    x = T.normalizar(np.random.default_rng(0).integers(0, 255, (64, 64, 3)).astype(np.uint8))
    assert x.dtype == np.float32 and np.allclose(x.mean((0, 1)), 0, atol=1e-4) and np.allclose(x.std((0, 1)), 1, atol=1e-3)
    assert np.isfinite(T.normalizar(np.full((8, 8, 3), 200, np.uint8))).all()         # un recorte liso no divide por cero


def test_el_detector_de_tejado_lee_los_recortes_guardados(tmp_path):
    import tejado as T
    carpeta = tmp_path / "cambios" / "fotos-prueba"
    for anio in (2017, 2025):
        (carpeta / str(anio)).mkdir(parents=True)
        cv2.imwrite(str(carpeta / str(anio) / "10_20.jpg"), np.full((512, 512, 3), (10, 20, 30), np.uint8))       # en disco va en azul, verde, rojo
        cv2.imwrite(str(carpeta / str(anio) / "e_0001YJ.jpg"), np.zeros((512, 512, 3), np.uint8))                # recorte suelto de un edificio grande
    (carpeta / "2017" / "9_9.jpg").write_bytes(b"roto")
    (carpeta / "notas").mkdir()
    guardados = T.recortes_guardados(tmp_path, "prueba")
    assert [(a, c) for a, c, _ in guardados] == [(2017, "10_20"), (2017, "9_9"), (2025, "10_20")]
    assert T.leer_recorte(guardados[0][2])[0, 0].tolist() == pytest.approx([30, 20, 10], abs=3)                  # (infrarrojo, rojo, verde)
    assert T.leer_recorte(guardados[1][2]) is None
