import io

import pytest

from osintmaps.fuentes import catastro

from .conftest import FEED


def test_feed_extrae_municipios_con_url_y_caja():
    municipios = catastro.parsear_feed(FEED)
    assert [m.codigo for m in municipios] == ["46001", "46900"]
    villa = municipios[1]
    assert villa.nombre == "Villa De Prueba"
    # Los espacios dobles de la URL original se normalizan a uno.
    assert villa.url.endswith("/46900-VILLA DE PRUEBA/A.ES.SDGC.BU.46900.zip")
    assert villa.caja == pytest.approx((-0.75, 39.50, -0.55, 39.62))


def test_lectura_del_gml(gml_fh):
    deteriorados, en_uso, epsg = catastro.leer_gml(gml_fh)
    assert epsg == 25830
    assert len(en_uso) == 4                      # las cuatro casas en uso
    por_ref = {e.refcat: e for e in deteriorados}
    assert set(por_ref) == {"0000001YJ0000A", "0000002YJ0000B", "0000003YJ0000C", "0000004YJ0000D"}
    nave = por_ref["0000001YJ0000A"]
    assert (nave.estado, nave.uso, nave.anio) == ("ruina", "industrial", 1925)
    assert nave.geom.area == pytest.approx(50 * 40 - 10 * 10)   # se descuenta el patio
    assert por_ref["0000003YJ0000C"].estado == "deficiente"


@pytest.mark.parametrize("trozo", [1, 2, 3, 5, 7, 64, 4096])
def test_ampersand_suelto_se_arregla_sin_romper_entidades(trozo):
    original = b"<a>Perez & Hijos &amp; Cia &lt;x&gt; R&D&#233;</a>"

    class Lento(io.BytesIO):          # devuelve siempre trozos pequeños
        def read(self, n=-1):
            return super().read(trozo)

    flujo = catastro._FlujoSaneado(Lento(original))
    salida = b""
    while True:
        parte = flujo.read(1024)
        if not parte:
            break
        salida += parte
    assert salida == b"<a>Perez &amp; Hijos &amp; Cia &lt;x&gt; R&amp;D&#233;</a>"


def test_candidatos_agrupa_filtra_y_mide(gml_fh):
    deteriorados, en_uso, epsg = catastro.leer_gml(gml_fh)
    candidatos = catastro.crear_candidatos(deteriorados, en_uso, epsg, "Villa De Prueba")
    por_id = {c.id: c for c in candidatos}
    # La casa de 100 m² queda fuera; quedan la fábrica (2 naves) y el corral.
    assert set(por_id) == {"cat-0000001YJ0000A", "cat-0000004YJ0000D"}

    fabrica = por_id["cat-0000001YJ0000A"]
    assert fabrica.n_edificios == 2
    assert fabrica.superficie_m2 == pytest.approx(1900 + 400)
    assert (fabrica.categoria, fabrica.estado, fabrica.anio) == ("industrial", "ruina", 1925)
    assert fabrica.vecinos_150m == 0
    assert fabrica.refcats == ["0000001YJ0000A", "0000002YJ0000B"]   # la mayor primero
    # UTM 30N (700000, 4380000) cae en el interior de la provincia de Valencia.
    assert 39.5 < fabrica.lat < 39.6 and -0.72 < fabrica.lon < -0.62
    assert fabrica.huella.geom_type == "MultiPolygon"

    corral = por_id["cat-0000004YJ0000D"]
    assert (corral.categoria, corral.vecinos_150m) == ("agrario", 3)


def test_ruinas_en_un_casco_habitado_no_forman_conjunto():
    from shapely.geometry import box
    import numpy as np
    # Tres casas ruinosas de 80 m² en fila y una nave ruinosa de 600 m² al lado,
    # rodeadas de 60 casas en uso: típico casco antiguo.
    casas = [catastro.Edificio(f"C{i}", "ruina", "residencial", 1900, 80.0, box(i * 12, 0, i * 12 + 8, 10)) for i in range(3)]
    nave = catastro.Edificio("NAVE", "ruina", "industrial", 1950, 600.0, box(40, 0, 70, 20))
    en_uso = np.array([[x * 10.0, 40.0 + y * 10.0] for x in range(10) for y in range(6)])
    candidatos = catastro.crear_candidatos(casas + [nave], en_uso, 25830, "Pueblo")
    assert [c.id for c in candidatos] == ["cat-NAVE"]           # las casas sueltas no llegan al mínimo
    assert candidatos[0].n_edificios == 1 and candidatos[0].mayor_edificio_m2 == 600
    # Las mismas ruinas sin vecinos en uso sí son un conjunto (una aldea abandonada).
    aldea = catastro.crear_candidatos(casas + [nave], np.empty((0, 2)), 25830, "Pueblo")
    assert len(aldea) == 1 and aldea[0].n_edificios == 4 and aldea[0].vecinos_150m == 0


def test_un_grupo_enorme_se_trocea():
    from shapely.geometry import box
    # 40 edificios en fila, cada 20 m: 800 m de cadena -> no puede ser un único grupo.
    geoms = [box(i * 20, 0, i * 20 + 10, 10) for i in range(40)]
    grupos = catastro._grupos(geoms, distancia=25)
    assert len(grupos) > 1
    assert sorted(i for g in grupos for i in g) == list(range(40))


def test_leer_zip_elige_el_fichero_de_edificios(zip_municipio):
    deteriorados, en_uso, epsg = catastro.leer_zip(zip_municipio)
    assert len(deteriorados) == 4 and epsg == 25830


def test_buscar_sigue_si_un_municipio_falla(monkeypatch, zip_municipio, tmp_path):
    bueno = catastro.Municipio("46900", "Villa De Prueba", "http://x/46900.zip")
    malo = catastro.Municipio("46001", "Otro Pueblo", "http://x/46001.zip")

    def descarga_falsa(sesion, url, destino, **kw):
        if "46001" in url:
            raise OSError("sin conexión")
        return zip_municipio

    monkeypatch.setattr(catastro, "descargar", descarga_falsa)
    procesados = []
    candidatos = list(catastro.buscar(None, [malo, bueno], tmp_path, procesados=procesados))
    assert [m.codigo for m in procesados] == ["46900"]       # el que falló no cuenta como cubierto
    assert len(candidatos) == 2
    assert all(c.municipio == "Villa De Prueba" for c in candidatos)
