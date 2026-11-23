"""Pruebas del pulso: fuentes, histórico, anomalías, resumen, publicación y servidor.

No tocan internet. Las respuestas de los servicios están copiadas, campo por campo, de
respuestas reales del geoportal de València, adsb.lol y Renfe (noviembre de 2026).
"""

from __future__ import annotations

import json
import subprocess
import time

import pytest

from osintmaps import cli
from osintmaps.pulso import anomalias, fuentes, publicar, resumen, servidor
from osintmaps.pulso.almacen import Almacen
from osintmaps.pulso.fuentes import Fuente, Objeto, Punto, Toma
from osintmaps.pulso.recolector import Recolector

T0 = 1_795_000_000 - 1_795_000_000 % 86400      # medianoche (hora universal) de un día de noviembre de 2026


# --------------------------------------------------------------------------
# Una red de mentira
# --------------------------------------------------------------------------

class _Respuesta:
    def __init__(self, datos, codigo=200):
        self._datos, self.status_code = datos, codigo

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Red:
    """Contesta como el geoportal (paginando), adsb.lol y Renfe. `capas` es {"Trafico/228": [elementos]}."""

    def __init__(self, capas=None, aviones=None, trenes=None, pagina=1000):
        self.capas, self.aviones, self.trenes, self.pagina = capas or {}, aviones, trenes, pagina
        self.pedidos = []

    def get(self, url, timeout=None, params=None):
        self.pedidos.append((url, dict(params or {})))
        if url.startswith(fuentes.ADSB):
            return _Respuesta({"ac": self.aviones or []})
        if url == fuentes.RENFE:
            return _Respuesta({"entity": self.trenes or []})
        tema, _, numero = url.removeprefix(fuentes.GEOPORTAL + "/").removesuffix("/query").split("/")
        todos = self.capas.get(f"{tema}/{numero}")
        if todos is None:
            return _Respuesta({"error": {"code": 400, "message": "Invalid or missing input parameters."}})
        desde, cuantos = params["resultOffset"], min(params["resultRecordCount"], self.pagina)
        trozo = todos[desde:desde + cuantos]
        if params["returnGeometry"] == "false":
            trozo = [dict(e, geometry=None) for e in trozo]
        cuerpo = {"type": "FeatureCollection", "features": trozo}
        if desde + cuantos < len(todos):
            cuerpo["exceededTransferLimit"] = True
        return _Respuesta(cuerpo)


def punto(lon, lat, **propiedades):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": propiedades}


def estacion(numero, bicis, huecos, total=None, abierta="T"):
    return punto(-0.38 + numero / 1000, 39.47 + numero / 1000, number=numero, address=f"Calle {numero}", open=abierta,
                 available=bicis, free=huecos, total=total if total is not None else bicis + huecos, updated_at="23/11/2026 21:40:13")


def tramo(ident, estado, nombre="AV. TRES CRUCES (De C./ Campos Crespo a Av. Gaspar Aguilar)."):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.40, 39.45], [-0.401, 39.4505], [-0.402, 39.451]]},
            "properties": {"gid": 2651, "denominacion": nombre, "estado": estado, "idtramo": ident}}


# --------------------------------------------------------------------------
# Fuentes
# --------------------------------------------------------------------------

def test_valenbisi_cuenta_las_bicis_y_sigue_pidiendo_si_quedan_mas():
    red = Red({"Trafico/228": [estacion(1, 1, 24), estacion(2, 3, 11, total=15), estacion(3, 0, 20), estacion(4, 10, 0), estacion(5, 9, 9, abierta="F")]}, pagina=2)
    toma = fuentes.tomar_bicis(red)
    assert toma.valores["bicis"] == {"1": 1, "2": 3, "3": 0, "4": 10}      # la cerrada no cuenta
    assert toma.puntos["bicis"]["2"] == Punto("Calle 2", 39.472, -0.378, 15)
    assert toma.indicadores["bicis_ancladas"] == 14 and toma.indicadores["bicis_vacias"] == 1 and toma.indicadores["bicis_llenas"] == 1
    assert toma.indicadores["bicis_fuera"] == round(100 * (1 - 14 / 70), 1)
    assert [p["resultOffset"] for _, p in red.pedidos] == [0, 2, 4]          # tres páginas de dos


def test_sin_posiciones_se_piden_solo_los_valores():
    red = Red({"Trafico/228": [estacion(1, 1, 24)]})
    toma = fuentes.tomar_bicis(red, False)
    assert toma.valores["bicis"] == {"1": 1} and toma.puntos["bicis"] == {}
    assert red.pedidos[0][1]["returnGeometry"] == "false"


def test_el_geoportal_contesta_200_tambien_cuando_falla():
    with pytest.raises(ValueError, match="sin elementos"):
        fuentes.tomar_bicis(Red({}))


def test_aparcamientos():
    red = Red({"Trafico/194": [punto(-0.364, 39.477, nombre="SEVERO OCHOA", id_aparcamiento=78, plazastota=371, plazaslibr=145),
                               punto(-0.371, 39.488, nombre="TIERNO GALVÁN", id_aparcamiento=79, plazastota=375, plazaslibr=79),
                               punto(-0.37, 39.48, nombre="SIN DATO", id_aparcamiento=80, plazastota=100, plazaslibr=None)]})
    toma = fuentes.tomar_parking(red)
    assert toma.valores["parking"] == {"78": 145, "79": 79}
    assert toma.puntos["parking"]["78"].nombre == "Severo Ochoa" and toma.puntos["parking"]["78"].cap == 371
    assert toma.indicadores == {"parking_libres": 224, "parking_ocupacion": round(100 * (1 - 224 / 746), 1)}


def test_el_estado_del_trafico_junta_las_dos_numeraciones():
    assert [fuentes.estado_trafico(x) for x in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, None, "")] == [0, 1, 2, 3, None, 0, 1, 2, 3, None, None, None]
    red = Red({"Trafico/192": [tramo(1, 0), tramo(2, 0), tramo(3, 2), tramo(4, 6), tramo(5, 3), tramo(6, 4)]})
    toma = fuentes.tomar_trafico(red)
    assert toma.valores["trafico"] == {"1": 0, "2": 0, "3": 2, "4": 1, "5": 3}
    ficha = toma.puntos["trafico"]["1"]
    assert ficha.geo == [[39.45, -0.4], [39.4505, -0.401], [39.451, -0.402]] and (ficha.lat, ficha.lon) == (39.4505, -0.401)
    assert not ficha.nombre.endswith(".")
    # Cuatro tramos abiertos con estados 0, 0, 2 y 1: tres de ocho puntos posibles. El cortado no cuenta como atasco.
    assert toma.indicadores == {"trafico_denso": 2, "trafico_cortado": 1, "trafico_indice": 37.5}


def test_aforos_media_por_punto_que_informa():
    red = Red({"Trafico/208": [punto(-0.33, 39.45, idpm=4507, ih=None), punto(-0.335, 39.4503, idpm=4509, ih=72), punto(-0.34, 39.46, idpm=4510, ih=128),
                               punto(-0.34, 39.46, idpm=4511, ih=-1)]})
    toma = fuentes.tomar_aforos(red)
    assert toma.valores["aforo"] == {"4509": 72, "4510": 128} and toma.indicadores == {"aforo": 100}
    assert red.pedidos[0][1]["outFields"] == "idpm,ih"


def test_aire_y_meteo():
    red = Red({"MedioAmbiente/156": [punto(-0.328, 39.467, objectid=12, nombre="Dr. Lluch", no2=49, o3=None, pm10=20, pm25=5, fiwareid="A08_DR_LLUCH_60m"),
                                     punto(-0.343, 39.458, objectid=13, nombre="Francia", no2=33, o3=26, pm10=10, pm25=3, fiwareid="A01_AVFRANCIA_60m")],
               "MedioAmbiente/157": [punto(-0.34, 39.45, temperatur=14.9, viento_vel=0.3, precipitac=0), punto(-0.33, 39.44, temperatur=16.7, viento_vel=0.9, precipitac=0)]})
    aire = fuentes.tomar_aire(red)
    assert aire.valores["no2"] == {"A08_DR_LLUCH_60m": 49, "A01_AVFRANCIA_60m": 33} and aire.valores["o3"] == {"A01_AVFRANCIA_60m": 26}
    assert aire.indicadores == {"aire_no2": 41, "aire_pm10": 15, "aire_pm25": 4, "aire_o3": 26}
    assert fuentes.tomar_meteo(red).indicadores == {"meteo_temperatura": 15.8, "meteo_viento": 0.6, "meteo_lluvia": 0}


def test_aviones_y_trenes():
    red = Red(aviones=[{"hex": "4cae5a", "flight": "RYR54XR ", "r": "EI-IJJ", "alt_baro": 37000, "track": 232.6, "lat": 39.227737, "lon": -0.921538, "seen_pos": 0.02},
                       {"hex": "344216", "flight": "", "r": "EC-LPR", "alt_baro": 2500, "lat": 39.5, "lon": -0.48, "seen_pos": 1},
                       {"hex": "aaaaaa", "alt_baro": "ground", "lat": 39.49, "lon": -0.47},
                       {"hex": "bbbbbb", "alt_baro": 9000, "lat": 39.6, "lon": -0.3, "seen_pos": 300},       # posición vieja
                       {"hex": "cccccc", "alt_baro": 9000}],                                                   # sin posición
              trenes=[{"id": "VP_C1-23573", "vehicle": {"trip": {"tripId": "3026L23573C1"}, "position": {"latitude": 37.57, "longitude": -5.80},
                                                         "vehicle": {"id": "23573", "label": "C1-23573"}}},     # Sevilla: fuera
                      {"id": "VP_C2-1", "vehicle": {"position": {"latitude": 39.46, "longitude": -0.38}, "vehicle": {"id": "24601", "label": "C2-24601-PLATF.(6)"}}}])
    aviones = fuentes.tomar_aviones(red)
    assert [(a.id, a.nombre, a.alt) for a in aviones.objetos["aviones"]] == [("4cae5a", "RYR54XR", round(37000 * 0.3048)), ("344216", "EC-LPR", 762), ("aaaaaa", "aaaaaa", 0.0)]
    assert aviones.indicadores == {"aviones": 2, "aviones_bajos": 1}
    trenes = fuentes.tomar_trenes(red)
    assert trenes.objetos["trenes"] == [Objeto("24601", 39.46, -0.38, "C2-24601")] and trenes.indicadores == {"trenes": 1}


def test_cada_indicador_y_cada_serie_tienen_su_fuente():
    ids = {f.id for f in fuentes.FUENTES}
    assert {info["fuente"] for info in fuentes.INDICADORES.values()} <= ids and set(fuentes.SERIES.values()) <= ids
    assert set(anomalias.VIGILADOS) <= set(fuentes.INDICADORES)


# --------------------------------------------------------------------------
# Histórico
# --------------------------------------------------------------------------

def _toma_bicis(valores, indicador=None, con_puntos=True):
    toma = Toma(valores={"bicis": dict(valores)})
    if con_puntos:
        toma.puntos = {"bicis": {i: Punto(f"Estación {i}", 39.47, -0.37, 20) for i in valores}}
    if indicador is not None:
        toma.indicadores = {"bicis_ancladas": indicador}
    return toma


def test_solo_se_guarda_lo_que_cambia_y_se_recupera_lo_que_marcaba(tmp_path):
    almacen = Almacen(tmp_path / "pulso.sqlite")
    almacen.guardar_toma("bicis", T0, _toma_bicis({"1": 5, "2": 9}, 14))
    almacen.guardar_toma("bicis", T0 + 120, _toma_bicis({"1": 5, "2": 8}, 13))
    almacen.guardar_toma("bicis", T0 + 240, _toma_bicis({"1": 6, "2": 8}, 14))
    assert almacen._filas("SELECT id, t, v FROM valores ORDER BY t, id") == [("1", T0, 5), ("2", T0, 9), ("2", T0 + 120, 8), ("1", T0 + 240, 6)]
    rejilla = almacen.valores_en_rejilla("bicis", [T0 - 60, T0, T0 + 119, T0 + 120, T0 + 300])
    assert rejilla == {"1": [None, 5, 5, 5, 6], "2": [None, 9, 9, 8, 8]}
    assert almacen.historia_de_punto("bicis", "2", T0 + 60, T0 + 300) == [(T0, 9), (T0 + 120, 8)]
    assert almacen.puntos("bicis")["1"] == {"nombre": "Estación 1", "lat": 39.47, "lon": -0.37, "cap": 20, "geo": None}
    assert almacen.conoce("bicis", "1") and not almacen.conoce("bicis", "99")
    almacen.cerrar()

    # Al volver a abrir no se recuerda lo último guardado: la primera toma se apunta entera, aunque no haya cambiado.
    almacen = Almacen(tmp_path / "pulso.sqlite")
    almacen.guardar_toma("bicis", T0 + 9000, _toma_bicis({"1": 6, "2": 8}, 14))
    assert almacen._filas("SELECT COUNT(*) FROM valores WHERE t=?", (T0 + 9000,)) == [(2,)]
    assert almacen.conoce("bicis", "2")


def test_la_cobertura_distingue_los_huecos():
    almacen = Almacen(":memory:")
    for t in (0, 120, 240, 3600, 3720):
        almacen.guardar_toma("bicis", T0 + t, _toma_bicis({"1": 5}))
    almacen.guardar_fallo("bicis", T0 + 360, "ConnectionError: sin red")
    assert almacen.cobertura("bicis", T0, T0 + 4000, 360) == [[T0, T0 + 240], [T0 + 3600, T0 + 3720]]
    assert almacen.cobertura("bicis", T0 + 200, T0 + 3650, 360) == [[T0 + 200, T0 + 240], [T0 + 3600, T0 + 3600]]
    assert almacen.cobertura("parking", T0, T0 + 4000, 360) == []
    estado = almacen.estado()["fuentes"]["bicis"]
    assert estado["ultima"] == T0 + 3720 and estado["tomas"] == 5 and estado["ok"]


def test_indicadores_por_tramos():
    almacen = Almacen(":memory:")
    for i, v in enumerate((10, 20, 30, 40)):
        almacen.guardar_toma("bicis", T0 + i * 300, _toma_bicis({"1": 1}, v))
    assert almacen.indicadores(T0, T0 + 1200, 600) == {"bicis_ancladas": {T0: 15, T0 + 600: 35}}
    assert almacen.indicadores(T0, T0 + 600, 600, ("parking_libres",)) == {}
    assert almacen.ultimo_indicador("bicis_ancladas", T0 + 700, 600) == (T0 + 600, 30)


def test_los_rastros_no_repiten_lo_que_no_se_mueve():
    almacen = Almacen(":memory:")
    for i in range(12):         # un tren parado seis minutos y un avión que avanza
        almacen.guardar_toma("x", T0 + i * 30, Toma(objetos={"trenes": [Objeto("24601", 39.46, -0.38, "C2-24601")],
                                                             "aviones": [Objeto("4cae5a", 39.2 + i / 100, -0.9, "RYR54XR", 232.6, 11278)]}))
    rastros = almacen.rastros("trenes", T0, T0 + 600)
    assert [p[0] - T0 for p in rastros["24601"]["p"]] == [0, 300]             # al llegar y a los cinco minutos
    avion = almacen.rastros("aviones", T0, T0 + 600)["4cae5a"]
    assert len(avion["p"]) == 12 and avion["nombre"] == "RYR54XR" and avion["p"][0] == [T0, 39.2, -0.9, 11278, 233]
    assert len(almacen.rastros("aviones", T0, T0 + 600, cada=60)["4cae5a"]["p"]) == 6


def test_un_suceso_largo_es_un_solo_suceso():
    almacen = Almacen(":memory:")
    almacen.guardar_suceso("trafico_indice", T0, 40, 20, 4.0)
    almacen.guardar_suceso("trafico_indice", T0 + 300, 55, 20, 7.0)     # sigue, y más fuerte
    almacen.guardar_suceso("trafico_indice", T0 + 600, 45, 20, 5.0)
    almacen.guardar_suceso("trafico_indice", T0 + 7200, 5, 20, -4.0)    # dos horas después y hacia el otro lado: otro
    assert almacen.sucesos(T0, T0 + 8000) == [
        {"clave": "trafico_indice", "desde": T0 + 7200, "hasta": T0 + 7200, "valor": 5, "normal": 20, "z": -4.0},
        {"clave": "trafico_indice", "desde": T0, "hasta": T0 + 600, "valor": 55, "normal": 20, "z": 7.0}]


def test_limpiar_tira_el_detalle_antiguo_y_conserva_los_indicadores():
    almacen = Almacen(":memory:")
    almacen.guardar_toma("bicis", T0, _toma_bicis({"1": 5}, 5))
    almacen.guardar_toma("x", T0, Toma(objetos={"trenes": [Objeto("1", 39.0, -0.3)]}))
    almacen.limpiar(T0 + 100 * 86400, dias_valores=90, dias_rastros=30)
    assert almacen._filas("SELECT COUNT(*) FROM valores") == [(0,)] and almacen._filas("SELECT COUNT(*) FROM rastros") == [(0,)]
    assert almacen._filas("SELECT COUNT(*) FROM indicadores") == [(1,)]


# --------------------------------------------------------------------------
# Lo normal y lo que se sale
# --------------------------------------------------------------------------

def _sembrar(almacen, clave, t, valores_por_semana):
    """Un valor del indicador a la misma hora de cada semana anterior a `t`."""
    for k, v in enumerate(valores_por_semana, start=1):
        almacen._bd.execute("INSERT INTO indicadores VALUES (?,?,?)", (clave, t - k * anomalias.SEMANA + 60, v))


def test_lo_normal_es_la_misma_hora_de_las_semanas_anteriores():
    almacen = Almacen(":memory:")
    ahora = T0 + 30 * 86400 + 8 * 3600
    _sembrar(almacen, "trafico_indice", ahora, [20, 22, 18, 21, 60])       # un día raro (60) no mueve la mediana
    normales = anomalias.Normales(almacen)
    mediana, dispersion, n = normales.normal("trafico_indice", ahora)
    assert (mediana, dispersion, n) == (21, 1, 5)
    assert normales.z("trafico_indice", ahora, 21)["z"] == 0
    fuerte = normales.z("trafico_indice", ahora, 45)
    assert fuerte["z"] > anomalias.UMBRAL and fuerte["normal"] == 21 and fuerte["n"] == 5
    assert normales.normal("trafico_indice", ahora + 6 * 3600) is None       # a otra hora no hay con qué comparar
    assert normales.z("parking_ocupacion", ahora, 50) is None


def test_con_poco_historico_se_comparan_dias_del_mismo_tipo():
    almacen = Almacen(":memory:")
    # Un miércoles a mediodía (hora local), para que los días de alrededor sean laborables seguro.
    ahora = int(time.mktime((2026, 11, 18, 12, 0, 0, 0, 0, -1)))
    for dias, v in ((1, 30), (2, 32), (5, 28), (6, 31), (3, 90), (4, 95)):     # 3 y 4 días antes son domingo y sábado
        almacen._bd.execute("INSERT INTO indicadores VALUES (?,?,?)", ("bicis_fuera", ahora - dias * 86400 + 60, v))
    muestras = anomalias.Normales(almacen).muestras("bicis_fuera", ahora)
    assert sorted(muestras) == [28, 30, 31, 32]


def test_evaluar_apunta_el_suceso_y_no_opina_sin_historico():
    almacen = Almacen(":memory:")
    ahora = T0 + 30 * 86400 + 8 * 3600
    _sembrar(almacen, "trafico_indice", ahora, [20, 22, 18, 21])
    _sembrar(almacen, "aforo", ahora, [300, 310])                               # solo dos semanas: no llega
    for clave, v in (("trafico_indice", 70), ("aforo", 900), ("trenes", 12)):
        almacen._bd.execute("INSERT INTO indicadores VALUES (?,?,?)", (clave, ahora - 120, v))
    comparaciones = {c["clave"]: c for c in anomalias.evaluar(almacen, anomalias.Normales(almacen), ahora)}
    assert comparaciones["trafico_indice"]["anomalia"] and not comparaciones["aforo"]["anomalia"] and "trenes" not in comparaciones
    assert [s["clave"] for s in almacen.sucesos(ahora - 10, ahora + 10)] == ["trafico_indice"]


# --------------------------------------------------------------------------
# Recolector
# --------------------------------------------------------------------------

def test_el_recolector_guarda_apunta_los_fallos_y_espera_mas_cada_vez():
    almacen, reloj, pedidos = Almacen(":memory:"), [T0], []

    def tomar(sesion, geometria):
        pedidos.append(geometria)
        if len(pedidos) in (3, 4):
            raise ConnectionError("sin red")
        return _toma_bicis({"1": len(pedidos)}, len(pedidos), con_puntos=geometria)

    fuente = Fuente("bicis", "Valenbisi", 120, tomar)
    recolector = Recolector(almacen, (fuente,), sesion=object(), reloj=lambda: reloj[0])
    resultados = []
    for _ in range(5):
        resultados.append((recolector.tomar(fuente), recolector.espera(fuente)))
        reloj[0] += 120
    assert resultados == [(True, 120), (True, 120), (False, 240), (False, 480), (True, 120)]
    assert pedidos == [True, False, False, False, False]                   # las posiciones, solo la primera vez
    assert almacen._filas("SELECT t - ?, ok, error FROM tomas ORDER BY t", (T0,)) == [
        (0, 1, None), (120, 1, None), (240, 0, "ConnectionError: sin red"), (360, 0, "ConnectionError: sin red"), (480, 1, None)]
    reloj[0] += 86400
    recolector.tomar(fuente)
    assert pedidos[-1] is True                                             # al día siguiente se vuelven a pedir


def test_un_punto_nuevo_hace_repetir_la_toma_con_posiciones():
    almacen, pedidos, estaciones = Almacen(":memory:"), [], {"1": 5}

    def tomar(sesion, geometria):
        pedidos.append(geometria)
        return _toma_bicis(estaciones, con_puntos=geometria)

    fuente = Fuente("bicis", "Valenbisi", 120, tomar)
    recolector = Recolector(almacen, (fuente,), sesion=object(), reloj=lambda: T0 + 120 * len(pedidos))
    recolector.tomar(fuente)
    estaciones["277"] = 12                                                  # abren una estación
    recolector.tomar(fuente)
    assert pedidos == [True, False, True] and almacen.puntos("bicis")["277"]["nombre"] == "Estación 277"


def test_una_respuesta_vacia_cuenta_como_fallo():
    almacen = Almacen(":memory:")
    fuente = Fuente("bicis", "Valenbisi", 120, lambda sesion, geometria: Toma(valores={"bicis": {}}))
    assert Recolector(almacen, (fuente,), sesion=object(), reloj=lambda: T0).tomar(fuente) is False
    assert almacen.cobertura("bicis", T0 - 10, T0 + 10, 360) == []


def test_el_recolector_arranca_y_para():
    almacen, visto = Almacen(":memory:"), []
    fuente = Fuente("bicis", "Valenbisi", 0.05, lambda sesion, geometria: visto.append(1) or _toma_bicis({"1": len(visto)}, len(visto)))
    recolector = Recolector(almacen, (fuente,), sesion=object())
    recolector.arrancar()
    limite = time.time() + 5
    while not visto and time.time() < limite:
        time.sleep(0.02)
    recolector.parar()
    assert visto and not recolector.estado()["en_marcha"]


# --------------------------------------------------------------------------
# Resumen
# --------------------------------------------------------------------------

def test_simplificar_quita_lo_que_no_cambia_la_forma():
    recta = [[39.45, -0.40], [39.4501, -0.4001], [39.4502, -0.4002], [39.46, -0.41]]
    assert resumen.simplificar(recta, 0.0005) == [recta[0], recta[-1]]
    esquina = [[39.45, -0.40], [39.45, -0.39], [39.46, -0.39]]
    assert resumen.simplificar(esquina) == esquina
    assert resumen.simplificar([[1, 1], [1, 1], [1, 1]]) == [[1, 1], [1, 1]]


def test_paso_para():
    assert resumen.paso_para(48 * 3600, 300) == 600 and resumen.paso_para(3600, 300) == 60 and resumen.paso_para(400 * 86400, 300) == 86400


def _historico_de_prueba():
    """Dos horas de datos, un hueco de tres y una hora más."""
    almacen = Almacen(":memory:")
    for i in list(range(0, 61)) + list(range(150, 181)):
        t = T0 + i * 120
        bicis = Toma(valores={"bicis": {"1": 5 + i % 3, "2": 10}}, indicadores={"bicis_ancladas": 15 + i % 3, "bicis_fuera": 60 - i % 3},
                     puntos={"bicis": {"1": Punto("Guillem de Castro", 39.48, -0.383, 25), "2": Punto("Museo", 39.4799, -0.3797, 15)}})
        almacen.guardar_toma("bicis", t, bicis)
        if i % 2 == 0:
            almacen.guardar_toma("trafico", t, Toma(valores={"trafico": {"522": i % 4 // 2}}, indicadores={"trafico_indice": 10.0 + i % 4},
                                                    puntos={"trafico": {"522": Punto("Av. Tres Cruces", 39.4505, -0.401, None,
                                                                                    [[39.45, -0.40], [39.4505, -0.401], [39.451, -0.402]])}}))
        almacen.guardar_toma("aviones", t, Toma(objetos={"aviones": [Objeto("4cae5a", 39.2 + i / 1000, -0.9, "RYR54XR", 232.6, 11278)]}, indicadores={"aviones": 1}))
    return almacen, T0 + 180 * 120


def test_el_resumen_lleva_rejillas_regulares_y_huecos_como_huecos():
    almacen, hasta = _historico_de_prueba()
    r = resumen.crear_resumen(almacen, desde=T0, hasta=hasta, paso=600, pasos_puntos={"bicis": 1800, "trafico": 1800})
    assert r["v"] == 1 and (r["desde"], r["hasta"]) == (T0, hasta)
    assert r["fuentes"]["bicis"]["cobertura"] == [[T0, T0 + 7200], [T0 + 18000, hasta]] and r["fuentes"]["bicis"]["origen"] == "Ajuntament de València"
    assert "parking" not in r["fuentes"]

    ind = r["indicadores"]
    assert (ind["t0"], ind["paso"], ind["n"]) == (T0, 600, 37)
    ancladas = ind["claves"]["bicis_ancladas"]
    assert ancladas["nombre"] == "Bicis ancladas" and len(ancladas["v"]) == 37
    assert ancladas["v"][0] == 16 and ancladas["v"][13:30] == [None] * 17 and ancladas["v"][30] is not None       # el hueco
    assert "normal" not in ancladas and "parking_libres" not in ind["claves"]

    bicis = r["puntos"]["bicis"]
    assert (bicis["t0"], bicis["paso"], bicis["n"]) == (T0, 1800, 13) and bicis["ids"] == ["1", "2"]      # acaba justo en «hasta»
    assert bicis["nombre"] == ["Guillem de Castro", "Museo"] and bicis["cap"] == [25, 15] and "geo" not in bicis
    assert bicis["v"][1] == [10, 10, 10, 10, 10, None, None, None, None, None, 10, 10, 10]     # en el hueco no se inventa nada
    assert r["puntos"]["trafico"]["geo"] == [[[39.45, -0.4], [39.451, -0.402]]]                  # la línea, simplificada

    aviones = r["rastros"]["aviones"]
    assert aviones[0]["id"] == "4cae5a" and aviones[0]["p"][0][:3] == [T0, 39.2, -0.9] and "trenes" not in r["rastros"]
    json.dumps(r)                                                                                # todo es serializable


def test_el_resumen_trae_lo_normal_cuando_hay_historico():
    almacen, hasta = _historico_de_prueba()
    for semana in (1, 2, 3):
        for i in range(0, 181, 5):
            almacen._bd.execute("INSERT INTO indicadores VALUES (?,?,?)", ("bicis_ancladas", T0 + i * 120 - semana * anomalias.SEMANA, 20))
    r = resumen.crear_resumen(almacen, anomalias.Normales(almacen), desde=T0, hasta=hasta, paso=600)
    assert set(r["indicadores"]["claves"]["bicis_ancladas"]["normal"]) == {20}
    assert "normal" not in r["indicadores"]["claves"]["bicis_fuera"]


def test_con_tramos_mas_cortos_que_la_fuente_no_salen_huecos_falsos():
    """Una fuente que contesta cada diez minutos, vista en tramos de dos: entre dato y dato vale el anterior."""
    almacen = Almacen(":memory:")
    for i in (0, 1, 2, 9):          # contesta a los 0, 10 y 20 minutos; luego calla hasta el minuto 90
        almacen.guardar_toma("aforo", T0 + i * 600, Toma(indicadores={"aforo": 100.4 + i, "aviones": 3.6}))
    r = resumen.crear_resumen(almacen, desde=T0, hasta=T0 + 5400, paso=120)
    aforo = r["indicadores"]["claves"]["aforo"]["v"]
    assert aforo[:5] == [100] * 5 and aforo[5:10] == [101] * 5 and aforo[10] == 102        # sin decimales: es un recuento
    assert aforo[10:26] == [102] * 16 and aforo[26:45] == [None] * 19 and aforo[45] == 109   # media hora después del último dato sí es un hueco
    # Los aviones se piden cada 20 segundos: un tramo de dos minutos sin dato ya es un hueco.
    assert r["indicadores"]["claves"]["aviones"]["v"][:3] == [4, None, None]


def test_recorrer_una_grafica_lee_el_historico_una_sola_vez():
    """Lo normal se pide tramo a tramo (cientos de veces por gráfica): no puede releer semanas de datos cada vez."""
    almacen, hasta = _historico_de_prueba()
    lecturas, original = [], almacen.indicadores
    almacen.indicadores = lambda *a, **k: lecturas.append(a) or original(*a, **k)
    normales = anomalias.Normales(almacen)
    for t in range(T0, hasta, 600):
        normales.normal("bicis_ancladas", t)
    assert len(lecturas) == 1
    normales.normal("bicis_ancladas", T0 - 30 * 86400)        # un rato muy anterior sí obliga a leer más atrás
    assert len(lecturas) == 2


def test_con_el_programa_recien_abierto_la_web_ya_lleva_los_puntos():
    """Dos minutos de datos y pasos de un cuarto de hora: el último instante tiene que caer en lo recogido."""
    almacen, ahora = Almacen(":memory:"), T0 + 37 * 60 + 13          # una hora cualquiera, no redonda
    for t in (ahora - 150, ahora - 30):
        almacen.guardar_toma("bicis", t, _toma_bicis({"1": 4, "2": 9}, 13))
    r = json.loads(resumen.resumen_para_la_web(almacen, ahora=ahora))
    bicis = r["puntos"]["bicis"]
    assert bicis["t0"] + (bicis["n"] - 1) * bicis["paso"] == ahora and [v[-1] for v in bicis["v"]] == [4, 9]
    assert all(v is None for fila in bicis["v"] for v in fila[:-1])                                   # lo de antes no se vio


def test_el_fichero_para_la_web_cabe_en_poco():
    almacen, hasta = _historico_de_prueba()
    bruto = resumen.resumen_para_la_web(almacen, ahora=hasta, comparaciones=[])
    r = json.loads(bruto)
    assert r["publicado"] is True and r["hasta"] - r["desde"] == 48 * 3600 and r["indicadores"]["paso"] == 600
    assert r["puntos"]["bicis"]["paso"] == 900 and r["ahora"] == []
    assert b'": ' not in bruto and b"0000000" not in bruto and len(bruto) < 20_000          # sin espacios ni decimales de sobra


# --------------------------------------------------------------------------
# Publicar solo los datos
# --------------------------------------------------------------------------

def _git(*orden, carpeta=None):
    return subprocess.run(["git", *orden], cwd=carpeta, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def web_publicada(tmp_path):
    """Un repositorio remoto con una web ya publicada con «osintmaps publicar»."""
    remoto = tmp_path / "remoto.git"
    _git("init", "-q", "--bare", str(remoto))
    datos = tmp_path / "datos"
    datos.mkdir()
    (datos / "candidatos.geojson").write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
    assert cli.main(["publicar", "--datos", str(datos), "--repo", str(remoto)]) == 0
    return remoto


def _en_la_web(remoto, ruta):
    return _git("--git-dir", str(remoto), "show", f"gh-pages:{ruta}")


def test_publicar_datos_cambia_solo_los_datos(web_publicada, tmp_path):
    antes = _git("--git-dir", str(web_publicada), "ls-tree", "-r", "gh-pages")
    trabajo = tmp_path / "cache" / "pulso-web"
    assert publicar.publicar_datos(str(web_publicada), {"pulso.json": b'{"v":1}'}, trabajo, ahora=T0) == "publicado"
    assert _en_la_web(web_publicada, "datos/pulso.json") == '{"v":1}'
    despues = _git("--git-dir", str(web_publicada), "ls-tree", "-r", "gh-pages")
    assert [linea for linea in despues.splitlines() if "pulso.json" not in linea] == antes.splitlines()       # el visor y lo demás, intactos
    assert _git("--git-dir", str(web_publicada), "rev-list", "--count", "gh-pages") == "1"                    # sigue siendo un solo commit
    mensaje = _git("--git-dir", str(web_publicada), "log", "-1", "--format=%s", "gh-pages")
    assert mensaje.startswith("Web publicada el ") and " · datos de las " in mensaje

    # Lo mismo otra vez no sube nada; algo distinto sí, y el mensaje no acumula coletillas.
    assert publicar.publicar_datos(str(web_publicada), {"pulso.json": b'{"v":1}'}, trabajo) == "sin cambios"
    assert publicar.publicar_datos(str(web_publicada), {"pulso.json": b'{"v":2}'}, trabajo) == "publicado"
    assert _en_la_web(web_publicada, "datos/pulso.json") == '{"v":2}'
    assert _git("--git-dir", str(web_publicada), "log", "-1", "--format=%s", "gh-pages").count("datos de las") == 1


def test_publicar_datos_no_pisa_una_web_recien_publicada(web_publicada, tmp_path, monkeypatch):
    """Si alguien publica la web entre que se baja y se sube, la subida se rechaza y la web nueva queda como estaba."""
    trabajo = tmp_path / "trabajo"
    original = publicar._git

    def git_con_carrera(*orden, carpeta, tiempo=180.0):
        if orden[0] == "push":          # justo antes de subir, otro publica la web entera
            datos = tmp_path / "datos"
            (datos / "candidatos.geojson").write_text('{"type": "FeatureCollection", "features": [], "nueva": true}', encoding="utf-8")
            assert cli.main(["publicar", "--datos", str(datos), "--repo", str(web_publicada)]) == 0
        return original(*orden, carpeta=carpeta, tiempo=tiempo)

    monkeypatch.setattr(publicar, "_git", git_con_carrera)
    with pytest.raises(RuntimeError, match="git push"):
        publicar.publicar_datos(str(web_publicada), {"pulso.json": b"{}"}, trabajo)
    assert '"nueva": true' in _en_la_web(web_publicada, "datos/candidatos.geojson")
    monkeypatch.setattr(publicar, "_git", original)
    assert publicar.publicar_datos(str(web_publicada), {"pulso.json": b"{}"}, trabajo) == "publicado"         # a la siguiente, entra
    assert '"nueva": true' in _en_la_web(web_publicada, "datos/candidatos.geojson")


def test_sin_web_publicada_se_avisa(tmp_path):
    remoto = tmp_path / "vacio.git"
    _git("init", "-q", "--bare", str(remoto))
    with pytest.raises(publicar.SinWeb):
        publicar.publicar_datos(str(remoto), {"pulso.json": b"{}"}, tmp_path / "trabajo")
    with pytest.raises(ValueError):
        publicar.publicar_datos(str(remoto), {"../fuera.json": b"{}"}, tmp_path / "trabajo2")


def test_el_publicador_apunta_como_ha_ido():
    llamadas = []

    def subir(repo, ficheros, trabajo):
        llamadas.append(ficheros)
        if len(llamadas) == 2:
            raise RuntimeError("git push: rejected")
        return "publicado"

    publicador = publicar.Publicador("https://usuario:secreto@github.com/u/r.git", None, lambda: {"pulso.json": b"12345"}, minutos=1, publicar=subir)
    assert publicador.minutos == publicar.MINUTOS_MINIMOS                    # nunca más seguido de lo que admite GitHub
    assert publicador.una_vez() == "publicado" and publicador.ultima["bytes"] == 5 and publicador.ultima["error"] is None
    cuando = publicador.ultima["cuando"]
    assert publicador.una_vez() == "fallo" and "rejected" in publicador.ultima["error"] and publicador.ultima["cuando"] == cuando
    assert "secreto" not in json.dumps(publicador.estado())


# --------------------------------------------------------------------------
# Dentro de «osintmaps servir»
# --------------------------------------------------------------------------

def test_sin_historico_el_visor_lo_sabe_sin_errores():
    assert servidor.atender(None, "/vivo/pulso/estado", "") == (200, b'{"hay":false}')
    assert servidor.atender(None, "/vivo/pulso/resumen", "")[0] == 404
    assert servidor.Pulso.si_hay("/no/existe") is None


def test_el_servidor_contesta_estado_resumen_y_punto(tmp_path, monkeypatch):
    import functools
    import threading

    import requests

    ahora = int(time.time())
    almacen = Almacen(tmp_path / "pulso.sqlite")
    for i in range(30):
        almacen.guardar_toma("bicis", ahora - 3600 + i * 120, _toma_bicis({"1": 5 + i % 3, "2": 10}, 15 + i % 3))
    almacen.cerrar()

    pulso = servidor.Pulso.si_hay(tmp_path)
    assert pulso is not None and pulso.recolector is None
    monkeypatch.setattr(cli._Servidor, "carpeta_datos", tmp_path)
    monkeypatch.setattr(cli._Servidor, "pulso", pulso)
    srv = cli.ServidorMapa(("127.0.0.1", 0), functools.partial(cli._Servidor, directory=str(cli.CARPETA_WEB)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        estado = requests.get(f"{base}/vivo/pulso/estado", timeout=5)
        assert estado.headers["Cache-Control"] == "no-store"
        estado = estado.json()
        assert estado["hay"] and not estado["en_marcha"] and estado["publicacion"] is None
        bicis = next(f for f in estado["fuentes"] if f["id"] == "bicis")
        assert bicis["tomas"] == 30 and bicis["ok"] and next(f for f in estado["fuentes"] if f["id"] == "trenes").get("tomas") is None

        r = requests.get(f"{base}/vivo/pulso/resumen?desde={ahora - 3600}&hasta={ahora}&paso=600&puntos=bicis&rastros=0", timeout=5).json()
        assert list(r["puntos"]) == ["bicis"] and r["indicadores"]["paso"] == 600 and r["rastros"] == {}
        por_defecto = requests.get(f"{base}/vivo/pulso/resumen", timeout=5)
        assert por_defecto.headers.get("Content-Encoding") == "gzip"                              # lo grande va comprimido
        por_defecto = por_defecto.json()
        assert por_defecto["hasta"] - por_defecto["desde"] == 48 * 3600

        p = requests.get(f"{base}/vivo/pulso/punto?serie=bicis&id=1&desde={ahora - 3600}&hasta={ahora}", timeout=5).json()
        assert p["nombre"] == "Estación 1" and p["cap"] == 20 and len(p["cambios"]) == 30 and len(p["cobertura"]) == 1

        assert requests.get(f"{base}/vivo/pulso/punto?serie=inventada&id=1", timeout=5).status_code == 400
        assert requests.get(f"{base}/vivo/pulso/resumen?desde={ahora}&hasta={ahora - 5}", timeout=5).status_code == 400
        assert requests.get(f"{base}/vivo/pulso/resumen?desde={ahora - 86400 * 30}&paso=60", timeout=5).status_code == 400
        assert requests.get(f"{base}/vivo/pulso/otra", timeout=5).status_code == 404
    finally:
        srv.shutdown()
        pulso.parar()


def test_servir_sin_pulso_no_recoge_nada(tmp_path):
    import argparse
    assert cli._arrancar_pulso(argparse.Namespace(datos=str(tmp_path), pulso=False)) is None
    assert not (tmp_path / "pulso.sqlite").exists()


def test_el_resumen_publicado_tambien_queda_en_la_carpeta_de_datos(tmp_path):
    pulso = servidor.Pulso(tmp_path, recoger=False)
    pulso.almacen.guardar_toma("bicis", int(time.time()) - 60, _toma_bicis({"1": 5}, 5))
    ficheros = pulso._ficheros_web()
    assert list(ficheros) == ["pulso.json"] and (tmp_path / "pulso.json").read_bytes() == ficheros["pulso.json"]
    assert json.loads(ficheros["pulso.json"])["indicadores"]["claves"]["bicis_ancladas"]["nombre"] == "Bicis ancladas"
    pulso.parar()
    assert "pulso.json" in cli.DATOS_DEL_SITIO
