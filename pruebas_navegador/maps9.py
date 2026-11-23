"""Pruebas de lo nuevo: buscador tipo Maps, rutas, capas del día a día, 3D y hoja del móvil.
Reutiliza el servidor y los servicios simulados de foto8.py (todo lo anterior a «errores = []»)."""
import sys, json, re, time
fuente = open("foto8.py", encoding="utf-8").read().split("\nerrores = []")[0].replace("8776", "8779").replace('"datos8"', '"datos9"')
exec(fuente)
ruta_vieja = ruta
vistos9 = {}
ESCENA = {"photon": "bien", "transitous": "bien", "osrm": "bien"}
def geo(lon, lat): return {"type": "Point", "coordinates": [lon, lat]}
PHOTON = {"features": [
    {"geometry": geo(LON + 0.004, LAT + 0.004), "properties": {"osm_type": "N", "osm_id": 501, "osm_key": "amenity", "osm_value": "pharmacy", "type": "house", "name": "Farmacia del Carmen", "street": "Calle Mayor", "housenumber": "12", "city": "Llíria", "postcode": "46160", "countrycode": "ES"}},
    {"geometry": geo(LON + 0.01, LAT - 0.004), "properties": {"osm_type": "W", "osm_id": 502, "osm_key": "highway", "osm_value": "residential", "type": "street", "name": "Calle de la Farmacia", "city": "Llíria", "countrycode": "ES", "extent": [LON + 0.009, LAT - 0.0035, LON + 0.011, LAT - 0.0045]}},
]}
CARTO = [{"address": "CALLE COLÓN 20, València", "type": "portal", "portalNumber": 20, "muni": "València", "province": "València/Valencia", "lat": LAT + 0.006, "lng": LON + 0.006, "id": "10.46.250_462500024128"}]
NODO = {"elements": [{"type": "node", "id": 501, "lat": LAT + 0.004, "lon": LON + 0.004, "tags": {"amenity": "pharmacy", "name": "Farmacia del Carmen", "opening_hours": "Mo-Fr 09:00-14:00,17:00-20:30; Sa 09:30-14:00", "phone": "+34 961 234 567", "website": "https://farmacia.example/", "addr:street": "Calle Mayor", "addr:housenumber": "12", "wheelchair": "yes"}}]}
def cerca(route):
    cuerpo = route.request.post_data or ""
    return {"elements": [
        {"type": "node", "id": 601, "lat": LAT + 0.002, "lon": LON + 0.001, "tags": {"amenity": "pharmacy", "name": "Farmacia Norte", "opening_hours": "24/7"}},
        {"type": "way", "id": 602, "center": {"lat": LAT - 0.003, "lon": LON - 0.002}, "tags": {"amenity": "pharmacy", "name": "Farmacia Sur", "opening_hours": "Mo-Fr 09:00-14:00"}},
        {"type": "node", "id": 603, "lat": LAT + 0.0005, "lon": LON + 0.0005, "tags": {"amenity": "pharmacy"}}]}
def pasos(n=3):
    return [{"maneuver": {"type": "depart", "modifier": "left", "location": [LON - 0.0008, LAT - 0.0004]}, "name": "Calle Mayor", "distance": 120, "duration": 90, "mode": "walking"},
            {"maneuver": {"type": "turn", "modifier": "right", "location": [LON, LAT + 0.0002]}, "name": "Avenida del Cid", "ref": "CV-35", "distance": 3500, "duration": 2800, "mode": "walking"},
            {"maneuver": {"type": "roundabout", "modifier": "right", "exit": 2, "location": [LON + 0.0003, LAT + 0.0003]}, "name": "Carrer Nou", "distance": 200, "duration": 150, "mode": "walking"},
            {"maneuver": {"type": "arrive", "modifier": "right", "location": [LON + 0.0005, LAT + 0.0005]}, "name": "Carrer Nou", "distance": 0, "duration": 0, "mode": "walking"}]
def osrm(u):
    perfil = u.split("/route/v1/")[1].split("/")[0]
    vistos9["osrm-" + perfil] = vistos9.get("osrm-" + perfil, 0) + 1; vistos9["osrm-ultima"] = u
    if ESCENA["osrm"] == "sin-ruta": return {"code": "NoRoute", "routes": []}
    k = {"foot": 1, "bike": 0.3, "driving": 0.12}[perfil]
    g1 = {"type": "LineString", "coordinates": [[LON - 0.0008, LAT - 0.0004], [LON, LAT + 0.0002], [LON + 0.0005, LAT + 0.0005]]}
    g2 = {"type": "LineString", "coordinates": [[LON - 0.0008, LAT - 0.0004], [LON - 0.0006, LAT + 0.0006], [LON + 0.0005, LAT + 0.0005]]}
    return {"code": "Ok", "routes": [{"distance": 3850, "duration": 3079.8 * k, "geometry": g1, "legs": [{"steps": pasos(), "summary": "Avenida del Cid"}]},
                                     {"distance": 4400, "duration": 3500 * k, "geometry": g2, "legs": [{"steps": pasos()[:1] + pasos()[-1:], "summary": "Calle Mayor"}]}]}
def codifica(puntos, precision=7):
    f = 10 ** precision; salida = []; ant = [0, 0]
    for la, lo in puntos:
        for i, v in enumerate((round(la * f), round(lo * f))):
            d = v - ant[i]; ant[i] = v
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20: salida.append(chr((0x20 | (d & 0x1f)) + 63)); d >>= 5
            salida.append(chr(d + 63))
    return "".join(salida)
def plan(u):
    vistos9["plan"] = vistos9.get("plan", 0) + 1; vistos9["plan-ultima"] = u
    if ESCENA["transitous"] == "vacio": return {"itineraries": [], "direct": []}
    t0 = "2026-11-22T17:40:00Z"
    def tramo(modo, a, b, ini, fin, **k):
        d = {"mode": modo, "from": {"name": a[0], "lat": a[1], "lon": a[2], "departure": ini}, "to": {"name": b[0], "lat": b[1], "lon": b[2], "arrival": fin}, "startTime": ini, "endTime": fin,
             "duration": k.pop("dur"), "legGeometry": {"points": codifica([(a[1], a[2]), (b[1], b[2])]), "precision": 7, "length": 2}}
        d.update(k); return d
    A = ("START", LAT - 0.0004, LON - 0.0008); P1 = ("Plaça Major", LAT, LON - 0.0004); P2 = ("Estació del Nord", LAT + 0.0004, LON + 0.0003); B = ("END", LAT + 0.0005, LON + 0.0005)
    it1 = {"duration": 1860, "startTime": t0, "endTime": "2026-11-22T18:11:00Z", "transfers": 0, "legs": [
        tramo("WALK", A, P1, t0, "2026-11-22T17:48:00Z", dur=480, distance=420),
        tramo("SUBWAY", P1, P2, "2026-11-22T17:48:00Z", "2026-11-22T17:56:00Z", dur=480, routeShortName="7", routeColor="82cee6", routeTextColor="000000", headsign="Marítim", agencyName="Metrovalencia", realTime=True,
              intermediateStops=[{"name": "Xàtiva", "lat": LAT + 0.0002, "lon": LON, "arrival": "2026-11-22T17:51:00Z", "departure": "2026-11-22T17:51:30Z"}]),
        tramo("WALK", P2, B, "2026-11-22T17:56:00Z", "2026-11-22T18:11:00Z", dur=900, distance=800)]}
    it2 = {"duration": 2400, "startTime": "2026-11-22T17:50:00Z", "endTime": "2026-11-22T18:30:00Z", "transfers": 1, "legs": [
        tramo("WALK", A, P1, "2026-11-22T17:50:00Z", "2026-11-22T17:55:00Z", dur=300, distance=300),
        tramo("BUS", P1, P2, "2026-11-22T17:55:00Z", "2026-11-22T18:10:00Z", dur=900, routeShortName="9", headsign="La Torre", agencyName="EMT València", realTime=False),
        tramo("TRAM", P2, B, "2026-11-22T18:14:00Z", "2026-11-22T18:30:00Z", dur=960, routeShortName="6", routeColor="8884bf", headsign="Tossal del Rei", agencyName="Metrovalencia")]}
    return {"itineraries": [it1, it2], "direct": []}
def punto(k, dla, dlo, **p): return {"type": "Feature", "id": k, "geometry": geo(LON + dlo, LAT + dla), "properties": dict(objectid=k, **p)}
VLC = {
    "228": [punto(1, 0.0006, 0.0006, name="001_PLAZA", number=1, address="Plaza Mayor 1", open="T", available=0, free=20, total=20, updated_at="22/11/2026 18:35:15", update_jcd="1795368885000"),
            punto(2, -0.0006, 0.0003, name="002_X", number=2, address="Calle X", open="T", available=9, free=6, total=15)],
    "194": [punto(3, 0.0009, -0.0009, nombre="CENTRO", plazastota=371, plazaslibr=12, ultima_mod=1795368896000)],
    "192": [{"type": "Feature", "id": 4, "geometry": {"type": "LineString", "coordinates": [[LON - 0.001, LAT + 0.0011], [LON + 0.001, LAT + 0.0012]]}, "properties": {"gid": 4, "denominacion": "MARIA CRISTINA", "estado": 2}}],
    "221": [punto(5, 0.0003, -0.0007, nombre="Pl. Espanya", linea="1,2", proximas_llegadas="https://geoportal.valencia.es/geoportal-services/api/v1/salidas-metro.html?estacion=24")],
    "220": [punto(6, 0.0004, -0.0008, denominacion="SANT ISIDRE", lineas="1,3,7", idparada=28, idboca=94)],
    "235": [{"type": "Feature", "id": 7, "geometry": {"type": "LineString", "coordinates": [[LON - 0.0003, LAT - 0.0011], [LON + 0.0003, LAT - 0.0012]]}, "properties": {"objectid": 7, "fecha_inicio_periodo": 1735772400000, "fecha_fin_periodo": 1796079540000, "estado": "Valido_p", "ocupacion": "ACERA"}}],
}
PNG_LLANO = _png(64, 64, lambda x, y: (128, 0, 40 if (x // 16 + y // 16) % 2 else 0))      # relieve casi llano: 0 m, con escalones de centímetros
def ruta(route):
    u = route.request.url
    def js(d, estado=200): return route.fulfill(status=estado, content_type="application/json", headers=CORS, body=json.dumps(d))
    if "unpkg.com/maplibre-gl@" in u: return route.fulfill(path=str(NM / "maplibre-gl/dist" / u.rsplit("/", 1)[-1]))
    if "photon.komoot.io/reverse" in u:
        vistos9["photon-cerca"] = u
        if ESCENA["photon"] != "cerca": return js({"features": []})
        return js({"features": [
            {"geometry": geo(LON + 0.001, LAT + 0.002), "properties": {"osm_type": "N", "osm_id": 601, "osm_key": "amenity", "osm_value": "pharmacy", "type": "house", "name": "Farmacia Norte", "street": "Calle Alta", "housenumber": "3", "city": "Llíria"}},
            {"geometry": geo(LON + 0.003, LAT + 0.003), "properties": {"osm_type": "N", "osm_id": 699, "osm_key": "amenity", "osm_value": "pharmacy", "type": "house", "street": "Calle Lejana", "city": "Llíria"}}]})
    if "photon.komoot.io" in u:
        vistos9["photon"] = vistos9.get("photon", 0) + 1; vistos9["photon-ultima"] = u
        if ESCENA["photon"] == "caido": return route.abort()
        return js(PHOTON if "farmacia" in u.lower() else {"features": []})
    if "geocoder/candidates" in u:
        vistos9["carto"] = vistos9.get("carto", 0) + 1
        return js(CARTO if "colon" in u.lower() or "col%C3%B3n" in u.lower() else [])
    if "api.openstreetmap.org/api/0.6" in u: vistos9["osm-api"] = u; return js(NODO)
    if "api.transitous.org" in u and "/plan" in u: return js(plan(u))
    if "api.transitous.org" in u and "/map/stops" in u:
        vistos9["paradas"] = u
        return js([{"name": "Plaça Major", "stopId": "es-EMT_1", "lat": LAT + 0.0007, "lon": LON + 0.0007, "stopCode": "1044", "modes": ["BUS"]}, {"name": "Estació", "stopId": "es-FGV_2", "lat": LAT - 0.0007, "lon": LON + 0.0007, "modes": ["SUBWAY"]}])
    if "api.transitous.org" in u and "/stoptimes" in u:
        vistos9["salidas"] = u
        return js({"stopTimes": [{"place": {"name": "Plaça Major", "departure": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 240))}, "mode": "BUS", "realTime": True, "headsign": "La Torre", "routeShortName": "9", "routeColor": "e2001a", "routeTextColor": "ffffff"},
                                 {"place": {"name": "Plaça Major", "departure": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 5400))}, "mode": "BUS", "realTime": False, "headsign": "Campanar", "routeShortName": "N1"}]})
    if "routing.openstreetmap.de" in u: return js(osrm(u))
    if "minetur.gob.es" in u:
        vistos9["combustible"] = vistos9.get("combustible", 0) + 1
        return js({"Fecha": "22/11/2026 18:36:42", "ListaEESSPrecio": [
            {"IDEESS": "1", "Rótulo": "REPSOL", "Latitud": str(LAT + 0.001).replace(".", ","), "Longitud (WGS84)": str(LON + 0.001).replace(".", ","), "Precio Gasolina 95 E5": "1,459", "Precio Gasoleo A": "1,399", "Horario": "L-D: 24H", "Dirección": "CV-35 KM 20", "Localidad": "LLIRIA", "Tipo Venta": "P"},
            {"IDEESS": "2", "Rótulo": "BALLENOIL", "Latitud": str(LAT - 0.001).replace(".", ","), "Longitud (WGS84)": str(LON - 0.001).replace(".", ","), "Precio Gasolina 95 E5": "1,299", "Precio Gasoleo A": "1,249", "Horario": "L-D: 24H", "Dirección": "CALLE X", "Localidad": "LLIRIA", "Tipo Venta": "P"},
            {"IDEESS": "3", "Rótulo": "CARA", "Latitud": str(LAT - 0.0015).replace(".", ","), "Longitud (WGS84)": str(LON + 0.0015).replace(".", ","), "Precio Gasolina 95 E5": "1,699", "Precio Gasoleo A": "", "Horario": "L-V: 06:00-22:00", "Dirección": "CALLE Y", "Localidad": "LLIRIA", "Tipo Venta": "P"}]})
    if "seismicportal" in u: vistos9["terremotos"] = u; return js({"features": [{"id": "t1", "properties": {"unid": "20261122_0000111", "lat": LAT + 0.02, "lon": LON + 0.02, "mag": 3.4, "magtype": "ml", "depth": 11.6, "time": "2026-11-22T15:44:55.18Z", "flynn_region": "SPAIN", "auth": "IGN"}}]})
    if "sensor.community" in u: return js([{"location": {"id": 9, "latitude": str(LAT + 0.001), "longitude": str(LON - 0.001), "indoor": 0}, "timestamp": "2026-11-22 17:00:00", "sensordatavalues": [{"value_type": "P1", "value": "18.2"}, {"value_type": "P2", "value": "7.4"}]}])
    if "air-quality-api" in u: return js({"current": {"european_aqi": 24, "pm10": 6.8, "pm2_5": 3.5, "nitrogen_dioxide": 10.2, "ozone": 67, "uv_index": 0}})
    if "reverseGeocode" in u: return js({"address": "CALLE MAYOR", "portalNumber": 3, "postalCode": "46160", "muni": "Llíria", "province": "València/Valencia", "provinceCode": "46"})
    if "interpreter" in u and "around" in (route.request.post_data or ""):
        vistos9["cerca"] = route.request.post_data
        if ESCENA.get("overpass") == "lento": time.sleep(1.5)
        if ESCENA.get("overpass") == "caido": return route.abort()
        return js(cerca(route))
    if "tiles.openfreemap.org/planet" in u and not u.endswith(".pbf"): return js({"tilejson": "3.0.0", "tiles": ["https://tiles.openfreemap.org/planet/20261101/{z}/{x}/{y}.pbf"], "minzoom": 0, "maxzoom": 14, "vector_layers": [{"id": "building"}]})
    if "tiles.openfreemap.org" in u: return route.fulfill(status=204, headers=CORS, body=b"")
    if "elevation-tiles-prod" in u or "mapterhorn" in u: vistos9["relieve"] = vistos9.get("relieve", 0) + 1; return route.fulfill(status=200, content_type="image/png", headers=CORS, body=PNG_LLANO)
    if "geoportal.valencia" in u and "/query" in u:
        capa = re.search(r"MapServer/(\d+)/query", u).group(1)
        vistos9["vlc-" + capa] = vistos9.get("vlc-" + capa, 0) + 1
        if capa in VLC: return js({"features": VLC[capa]})
    if "geoportal.valencia" in u and "/identify" in u:
        vistos9["identify"] = u
        return js({"results": [{"layerId": 231, "layerName": "PGOU - Calificaciones", "attributes": {"califi": "CHP", "uso": "REB", "categoria": "Conjunto Histórico Protegido"}}]})
    return ruta_vieja(route)
