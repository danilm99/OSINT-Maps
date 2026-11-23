"use strict";
/* OSINT Maps: capas de datos, ficha general, buscador, menú del botón derecho y
   visor de imágenes. Se carga después del programa de index.html y usa lo que
   este define (mapa, fondos, el, $, marcadores, candidatos...).

   Cómo está organizado:
   1. Mapas de fondo y superposiciones (imágenes que se ponen encima).
   2. Capas de datos: cada una sabe pedir sus elementos para un trozo de mapa.
   3. Ficha de un elemento o de un punto cualquiera.
   4. Visor a pantalla completa: ortofotos por años, calle, fotos, satélite.
   5. Menú del botón derecho, buscador y dirección de la página. */

/* ====================== 1. Fondos y superposiciones ====================== */
const VALENCIA = "https://geoportal.valencia.es/server/rest/services/OPENDATA";      // datos abiertos del Ayuntamiento de València
/* Las imágenes de satélite «del día» tardan unas horas en estar enteras: se pide la de hace día y medio. */
const DIA_SATELITE = new Date(Date.now() - 36 * 3600000).toISOString().slice(0, 10);
const wmts = (base, capa, formato) =>
  `${base}?layer=${capa}&style=default&tilematrixset=GoogleMapsCompatible&Service=WMTS&Request=GetTile&Version=1.0.0` +
  `&Format=image/${formato}&TileMatrix={z}&TileCol={x}&TileRow={y}`;

const PROVINCIA = [[VALENCIA_PROVINCIA.s, VALENCIA_PROVINCIA.o], [VALENCIA_PROVINCIA.n, VALENCIA_PROVINCIA.e]];
const FONDOS_NUEVOS = {
  // Más fotos aéreas (el tercer dato las coloca arriba en la lista, junto a las otras fotos).
  icv: ["Provincia de València, primavera de 2025 (ICV, 15 cm)", wmsFoto(WMS_ICV, "2025PVAL0015_RGB", { bounds: PROVINCIA, attribution: "ICV CC BY 4.0" }), "foto"],
  icv_ir: ["Infrarrojo de 2025 (ICV): la vegetación sale en rojo", wmsFoto(WMS_ICV, "2025PVAL0015_IRG", { bounds: PROVINCIA, attribution: "ICV CC BY 4.0" }), "foto"],
  google: ["Satélite de Google (otra fecha, no oficial)", teselasFoto("https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", 21, { subdomains: "0123", attribution: "Imágenes © Google" }), "foto"],
  esri: ["Satélite de Esri (otra fecha)", teselasFoto("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", 19, { attribution: "Esri, Maxar, Earthstar Geographics" }), "foto"],
  diario: [`Satélite de ayer, el planeta entero (VIIRS del ${DIA_SATELITE.split("-").reverse().join("/")}, 250 m)`, L.tileLayer(`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/${DIA_SATELITE}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
    { maxZoom: ZOOM_MAX, maxNativeZoom: 9, attribution: "NASA GIBS, VIIRS NOAA-20" }), "foto"],
  // Mapas sobrios para que lo que resalte sean los símbolos. (Los de CARTO se probaron y ahora piden clave.)
  gris_oscuro: ["Mapa oscuro (Esri)", L.featureGroup(["Base", "Reference"].map((parte) => L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_${parte}/MapServer/tile/{z}/{y}/{x}`,
    { maxZoom: ZOOM_MAX, maxNativeZoom: 16, attribution: "Esri, HERE, Garmin, OpenStreetMap" })))],
  gris_claro: ["Mapa claro (Esri)", L.featureGroup(["Base", "Reference"].map((parte) => L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_${parte}/MapServer/tile/{z}/{y}/{x}`,
    { maxZoom: ZOOM_MAX, maxNativeZoom: 16, attribution: "Esri, HERE, Garmin, OpenStreetMap" })))],
  noche: ["Luces de noche desde satélite (2016)", L.tileLayer("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png",
    { maxZoom: ZOOM_MAX, maxNativeZoom: 8, attribution: "NASA Black Marble" })],
  s2: ["Satélite Sentinel-2 sin nubes (2023, 10 m)", L.tileLayer("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg",
    { maxZoom: ZOOM_MAX, maxNativeZoom: 14, attribution: "Sentinel-2 cloudless 2023, EOX (datos Copernicus)" })],
  base: ["Callejero (IGN)", L.tileLayer(wmts("https://www.ign.es/wmts/ign-base", "IGNBaseTodo", "jpeg"), { maxZoom: ZOOM_MAX, maxNativeZoom: 18, attribution: "IGN CC BY 4.0 ign.es" })],
  lidar: ["Relieve LiDAR: edificios y arbolado", L.tileLayer(wmts("https://wmts-mapa-lidar.idee.es/lidar", "EL.GridCoverageDSM", "png"), { maxZoom: ZOOM_MAX, maxNativeZoom: 17, attribution: "LiDAR-PNOA CC BY 4.0 scne.es" })],
  relieve: ["Relieve del terreno", L.tileLayer(wmts("https://servicios.idee.es/wmts/mdt", "Relieve", "jpeg"), { maxZoom: ZOOM_MAX, maxNativeZoom: 15, attribution: "IGN CC BY 4.0 ign.es" })],
  mtn50: ["Mapa de 1915-1960 (MTN50, 1.ª edición)", L.tileLayer(wmts("https://www.ign.es/wmts/primera-edicion-mtn", "mtn50-edicion1", "jpeg"), { maxZoom: ZOOM_MAX, maxNativeZoom: 15, attribution: "IGN CC BY 4.0 ign.es" })],
  catastrones: ["Minutas de 1870-1950 (catastrones)", L.tileLayer(wmts("https://www.ign.es/wmts/primera-edicion-mtn", "catastrones", "jpeg"), { maxZoom: ZOOM_MAX, maxNativeZoom: 15, attribution: "IGN CC BY 4.0 ign.es" })],
};
for (const [id, [nombre, capa, foto]] of Object.entries(FONDOS_NUEVOS)) {
  fondos[id] = capa;
  $("capa-fondo").insertBefore(el("option", { value: id, textContent: nombre }), foto ? $("capa-fondo").querySelector("[value=mtn]") : null);
}

mapa.createPane("superpuesto").style.zIndex = 260;
mapa.getPane("superpuesto").style.pointerEvents = "none";
const SUPERPUESTAS = {
  rotulos: ["Calles y nombres sobre la foto", L.tileLayer(wmts("https://www.ign.es/wmts/ign-base", "IGNBaseOrto", "png"), { pane: "superpuesto", maxZoom: ZOOM_MAX, maxNativeZoom: 18, crossOrigin: "anonymous" })],
  tren: ["Red ferroviaria (OpenRailwayMap)", L.tileLayer("https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", { pane: "superpuesto", maxZoom: ZOOM_MAX, maxNativeZoom: 19, attribution: "OpenRailwayMap CC BY-SA" })],
  antiguo: ["Mapa de 1915-1960, translúcido", L.tileLayer(wmts("https://www.ign.es/wmts/primera-edicion-mtn", "mtn50-edicion1", "jpeg"), { pane: "superpuesto", opacity: 0.6, maxZoom: ZOOM_MAX, maxNativeZoom: 15 })],
  sombras: ["Relieve LiDAR, translúcido", L.tileLayer(wmts("https://wmts-mapa-lidar.idee.es/lidar", "EL.GridCoverageDSM", "png"), { pane: "superpuesto", opacity: 0.55, maxZoom: ZOOM_MAX, maxNativeZoom: 17 })],
};
/* Lluvia: la última imagen del radar. La dirección de las teselas cambia cada diez minutos,
   así que se pregunta cuál es la vigente al encender la capa y luego cada cinco minutos. */
{
  const lluvia = L.layerGroup();
  let reloj = null;
  const actualizar = () => fetch("https://api.rainviewer.com/public/weather-maps.json").then((r) => r.json()).then((j) => {
    const ultima = ((j.radar || {}).past || []).slice(-1)[0];
    if (!ultima || !mapa.hasLayer(lluvia)) return;
    lluvia.clearLayers();
    L.tileLayer(`${j.host}${ultima.path}/256/{z}/{x}/{y}/2/1_1.png`, { pane: "superpuesto", opacity: 0.7, maxZoom: ZOOM_MAX, maxNativeZoom: 7, attribution: "RainViewer" }).addTo(lluvia);
  }).catch(() => { /* sin radar: la capa se queda vacía */ });
  lluvia.on("add", () => { actualizar(); clearInterval(reloj); reloj = setInterval(actualizar, 300000); });
  lluvia.on("remove", () => { clearInterval(reloj); lluvia.clearLayers(); });
  SUPERPUESTAS.lluvia = ["Lluvia ahora (radar)", lluvia];
}
/* Más imágenes para poner encima. Las de servicios WMS se piden por teselas, como cualquier otra. */
const wmsEncima = (url, capas, opciones) => L.tileLayer.wms(url, Object.assign({ layers: capas, format: "image/png", transparent: true, version: "1.1.1", pane: "superpuesto", maxZoom: ZOOM_MAX }, opciones));
/* Una capa de un servidor ArcGIS (el geoportal de València) que pinta el propio servidor: se le pide la imagen de
   cada tesela. Sirve para lo que son zonas grandes o miles de polígonos: calificaciones del suelo, mapas de ruido.
   Además sabe contestar «¿qué hay en este punto?»: lo usa la ficha de un punto (identificarEnSuperpuestas). */
const TeselasArcgis = L.TileLayer.extend({
  getTileUrl(c) {
    const lado = (2 * MEDIO_MUNDO) / 2 ** c.z, px = DENSIDAD === 2 ? 512 : 256;
    const caja = [-MEDIO_MUNDO + c.x * lado, MEDIO_MUNDO - (c.y + 1) * lado, -MEDIO_MUNDO + (c.x + 1) * lado, MEDIO_MUNDO - c.y * lado];
    return `${this.options.servicio}/export?bbox=${caja.join(",")}&bboxSR=3857&imageSR=3857&size=${px},${px}&dpi=${px === 512 ? 192 : 96}&format=png32&transparent=true&layers=show:${this.options.capas}&f=image`;
  },
});
const arcgisPintado = (tema, capas, opciones) => new TeselasArcgis("", Object.assign({ servicio: `${VALENCIA}/${tema}/MapServer`, capas, pane: "superpuesto", opacity: 0.6, maxZoom: ZOOM_MAX, minZoom: 11,
  bounds: [[VALENCIA_CIUDAD.s, VALENCIA_CIUDAD.o], [VALENCIA_CIUDAD.n, VALENCIA_CIUDAD.e]], attribution: "Ajuntament de València" }, opciones));
Object.assign(SUPERPUESTAS, {
  inundable: ["Zonas inundables: ríos (cada 100 y 500 años) y temporales de mar", wmsEncima("https://servicios.idee.es/wms-inspire/riesgos-naturales/inundaciones", "NZ.Flood.FluvialT500,NZ.Flood.FluvialT100,NZ.Flood.MarinaT100",
    { opacity: 0.55, attribution: "SNCZI (MITECO)" })],
  drones: ["Zonas con restricciones para drones (ENAIRE)", wmsEncima("https://servais.enaire.es/insignia/services/NSF_SRV/SRV_UAS_ZG_V1/MapServer/WMSServer", "0,1,2", { opacity: 0.5, attribution: "ENAIRE" })],
  limites: ["Límites de municipios y provincias", wmsEncima("https://www.ign.es/wms-inspire/unidades-administrativas", "AU.AdministrativeBoundary", { attribution: "IGN CC BY 4.0" })],
  senderos: ["Senderos señalizados (Waymarked Trails)", L.tileLayer("https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png", { pane: "superpuesto", maxZoom: ZOOM_MAX, maxNativeZoom: 17, attribution: "waymarkedtrails.org CC BY-SA" })],
  ciclismo: ["Rutas ciclistas señalizadas (Waymarked Trails)", L.tileLayer("https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png", { pane: "superpuesto", maxZoom: ZOOM_MAX, maxNativeZoom: 17, attribution: "waymarkedtrails.org CC BY-SA" })],
  mar: ["Balizas, faros y señales del mar (OpenSeaMap)", L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", { pane: "superpuesto", maxZoom: ZOOM_MAX, maxNativeZoom: 18, attribution: "OpenSeaMap CC BY-SA" })],
  fuegos: [`Focos de calor vistos desde satélite el ${DIA_SATELITE.split("-").reverse().join("/")}: incendios y quemas`, wmsEncima("https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
    "VIIRS_NOAA20_Thermal_Anomalies_375m_All,VIIRS_SNPP_Thermal_Anomalies_375m_All", { time: DIA_SATELITE, attribution: "NASA GIBS, VIIRS" })],
  ruido: ["València: mapa de ruido (24 h)", arcgisPintado("Salud", "144")],
  pgou: ["València: calificación urbanística (PGOU)", arcgisPintado("UrbanismoEInfraestructuras", "231", { minZoom: 13 })],
  policia_zonas: ["València: distritos y barrios policiales", arcgisPintado("UrbanismoEInfraestructuras", "266,267")],
  barrios: ["València: distritos y barrios", arcgisPintado("UrbanismoEInfraestructuras", "225,224")],
  censo: ["València: secciones censales", arcgisPintado("UrbanismoEInfraestructuras", "210", { minZoom: 13 })],
  zbe: ["València: zona de bajas emisiones y de prioridad residencial", arcgisPintado("Trafico", "240,1")],
  zas: ["València: zonas acústicamente saturadas", arcgisPintado("SociedadBienestar", "5")],
});
/* Lo que dicen de un punto las superposiciones de València que estén encendidas. */
function identificarEnSuperpuestas(e, dl, sigue) {
  for (const [nombre, capa] of Object.values(SUPERPUESTAS)) {
    if (!(capa instanceof TeselasArcgis) || !mapa.hasLayer(capa)) continue;
    const dd = el("dd", { className: "pendiente", textContent: "consultando…" }), d = 0.0005;
    dl.append(el("dt", { textContent: nombre.replace(/^València: /, "").replace(/ \(.*$/, "").replace(/^./, (x) => x.toUpperCase()) }), dd);
    pedirJ(`${capa.options.servicio}/identify?geometry=${e.lon},${e.lat}&geometryType=esriGeometryPoint&sr=4326&layers=all:${capa.options.capas}&tolerance=2` +
      `&mapExtent=${e.lon - d},${e.lat - d},${e.lon + d},${e.lat + d}&imageDisplay=400,400,96&returnGeometry=false&f=json`, null, 15000).then((j) => {
      if (!sigue()) return;
      const textos = (j.results || []).map((r) => Object.entries(r.attributes || {}).filter(([k, v]) => !CAMPOS_FUERA.test(k) && !/^(objectid|shape|fid|gid|cod|id)\b/i.test(k) && limpio(v) && !/^(null|polygon|polyline|point)$/i.test(String(v))).slice(0, 5)
        .map(([k, v]) => `${CAMPO_BONITO[k.toLowerCase()] || k.toLowerCase().replace(/_/g, " ")}: ${limpio(v)}`).join(", ")).filter(Boolean);
      dd.className = textos.length ? "" : "pendiente";
      dd.textContent = textos.length ? textos.join(" · ").slice(0, 420) : "nada en este punto";
    }).catch(() => { if (sigue()) { dd.className = "pendiente"; dd.textContent = "sin respuesta"; } });
  }
}
// El servicio del IGN devuelve de vez en cuando una tesela entera de un solo color (un azul liso): se oculta.
SUPERPUESTAS.rotulos[1].on("tileload", (ev) => { if (esImagenLisa(ev.tile)) ev.tile.style.visibility = "hidden"; });
{
  const guardadas = leerLocal("osintmaps.superpuestas.v1", ["rotulos"]) || [];
  const recordar = () => guardarLocal("osintmaps.superpuestas.v1", Object.keys(SUPERPUESTAS).filter((id) => $(`sup-${id}`).checked));
  let deValencia = false;
  for (const [id, [nombre, capa]] of Object.entries(SUPERPUESTAS)) {
    const casilla = el("input", { id: `sup-${id}`, type: "checkbox", checked: guardadas.includes(id) });
    casilla.addEventListener("change", () => { casilla.checked ? capa.addTo(mapa) : mapa.removeLayer(capa); recordar(); });
    if (casilla.checked) capa.addTo(mapa);
    // Las de València van juntas al final, con su rótulo.
    if (/^València: /.test(nombre) && !deValencia) { deValencia = true; $("capas-superponer").append(el("div", { className: "grupo-capas", textContent: "Zonas de València (las pinta su geoportal)" })); }
    $("capas-superponer").append(el("label", { className: "casilla" }, casilla, " " + nombre.replace(/^València: /, "").replace(/^./, (x) => x.toUpperCase())));
  }
  // El fondo de la última vez (index.html ya puso el suyo si era uno de los que define él).
  const elegido = fondos[fondoGuardado] ? fondoGuardado : "auto";
  $("capa-fondo").value = elegido;
  if (fondoActual !== fondos[elegido]) $("capa-fondo").dispatchEvent(new Event("change"));
  $("capa-fondo").addEventListener("change", (e) => guardarLocal("osintmaps.fondo.v2", e.target.value));
}

/* ====================== 2. Capas de datos ====================== */
const metros = (a, b) => mapa.distance([a.lat, a.lon], [b.lat, b.lon]);
const limpio = (t) => String(t == null ? "" : t).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
const fechaCorta = (t) => { const d = new Date(t); return Number.isNaN(+d) ? String(t || "") : d.toLocaleDateString("es-ES"); };
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
/* Petición con plazo. El plazo cubre también la lectura del cuerpo: un servidor que
   manda las cabeceras y luego se queda callado no debe dejar la cola bloqueada. */
function pedir(url, opciones, espera = 30000, como = "json") {
  const corte = new AbortController(), reloj = setTimeout(() => corte.abort(), espera);
  return fetch(url, Object.assign({ signal: corte.signal }, opciones || {}))
    .then((r) => (r.ok ? r[como]() : Promise.reject(new Error(r.status)))).finally(() => clearTimeout(reloj));
}
const pedirJ = (url, opciones, espera) => pedir(url, opciones, espera, "json");
const pedirTexto = (url, opciones, espera) => pedir(url, opciones, espera, "text");

/* Las consultas a OpenStreetMap se hacen con overpass(), que está en index.html. */

/* Nombres en castellano de las etiquetas de OSM que más salen. */
const ETIQUETA_OSM = {
  name: "Nombre", operator: "Operador", owner: "Propietario", "addr:street": "Calle", "addr:housenumber": "Número", "addr:city": "Localidad",
  start_date: "Desde", end_date: "Hasta", height: "Altura (m)", "building:levels": "Plantas", access: "Acceso", description: "Descripción",
  website: "Web", wikipedia: "Wikipedia", wikidata: "Wikidata", ref: "Referencia", voltage: "Tensión (V)", "tower:type": "Tipo de torre",
  railway: "Ferrocarril", power: "Energía", man_made: "Construcción", military: "Militar", historic: "Histórico", barrier: "Barrera",
  bridge: "Puente", tunnel: "Túnel", landuse: "Uso del suelo", building: "Edificio", abandoned: "Abandonado", disused: "En desuso",
  ruins: "Ruinas", heritage: "Protección", opening_hours: "Horario", lit: "Iluminado", surface: "Firme", material: "Material",
  artwork_type: "Tipo de obra", artist_name: "Artista", maxspeed: "Límite (km/h)", tourism: "Turismo", natural: "Natural", waterway: "Cauce",
  "lamp_type": "Tipo de lámpara", "light:colour": "Color de la luz", electrified: "Electrificado", gauge: "Ancho de vía (mm)", usage: "Uso", service: "Servicio",
  amenity: "Tipo", shop: "Tienda", leisure: "Ocio", sport: "Deporte", cuisine: "Cocina", brand: "Marca", phone: "Teléfono", "contact:phone": "Teléfono", email: "Correo",
  "contact:email": "Correo", "contact:website": "Web", "addr:postcode": "Código postal", level: "Planta", wheelchair: "Accesible en silla de ruedas", internet_access: "Internet",
  takeaway: "Para llevar", delivery: "Reparto a domicilio", outdoor_seating: "Terraza", "diet:vegetarian": "Opciones vegetarianas", "diet:vegan": "Opciones veganas", smoking: "Fumadores",
  stars: "Estrellas", rooms: "Habitaciones", capacity: "Plazas", fee: "De pago", charge: "Precio", parking: "Tipo de aparcamiento", covered: "Cubierto", bicycle_parking: "Tipo de aparcabicis",
  "socket:type2": "Tomas tipo 2", "socket:type2_combo": "Tomas CCS", "socket:chademo": "Tomas CHAdeMO", "fuel:diesel": "Diésel", "fuel:octane_95": "Gasolina 95", "fuel:lpg": "GLP",
  self_service: "Autoservicio", "payment:cash": "Admite efectivo", "payment:credit_cards": "Admite tarjeta", changing_table: "Cambiador de bebés", drinking_water: "Agua potable",
  "toilets:wheelchair": "Aseo adaptado", religion: "Religión", denomination: "Confesión", ele: "Altitud (m)", network: "Red", advertising: "Soporte", animated: "Animado", sides: "Caras",
  species: "Especie", "species:es": "Especie", denotation: "Distinción", aeroway: "Aviación", iata: "Código IATA", icao: "Código OACI", emergency: "Emergencias", office: "Oficina",
  telecom: "Telecomunicaciones", street_cabinet: "Armario de", manhole: "Registro de", check_date: "Comprobado el",
};
const VALOR_OSM = {
  yes: "sí", no: "no", private: "privado", permissive: "tolerado", customers: "clientes", rail: "vía en servicio", disused: "en desuso",
  abandoned: "abandonado", razed: "desmantelado", station: "estación", halt: "apeadero", yard: "playa de vías", siding: "apartadero",
  substation: "subestación", plant: "central", generator: "generador", transformer: "transformador", tower: "torre", mast: "mástil",
  line: "línea", minor_line: "línea menor", wall: "muro", retaining_wall: "muro de contención", noise_barrier: "pantalla acústica",
  city_wall: "muralla", fence: "valla", bunker: "búnker", barracks: "cuartel", ruins: "ruinas", works: "fábrica", chimney: "chimenea",
  silo: "silo", storage_tank: "depósito", water_tower: "depósito elevado", quarry: "cantera", mineshaft: "pozo de mina", adit: "bocamina",
  brownfield: "descampado", construction: "en obras", greenfield: "suelo sin urbanizar", viewpoint: "mirador", artwork: "obra de arte",
  graffiti: "grafiti", mural: "mural", street_art: "arte urbano", streetart: "arte urbano", painting: "pintura", cave_entrance: "cueva",
  dam: "presa", weir: "azud", water_works: "potabilizadora", wastewater_plant: "depuradora", pumping_station: "estación de bombeo",
  reservoir_covered: "depósito cubierto", water_tank: "depósito", speed_camera: "radar de velocidad",
  viaduct: "viaducto", aqueduct: "acueducto", police: "policía", communications_tower: "torre de comunicaciones", industrial: "industrial",
  castle: "castillo", fort: "fuerte", monument: "monumento", memorial: "memorial", archaeological_site: "yacimiento", church: "iglesia",
  farm: "masía o granja", manor: "casa señorial", mine: "mina", tram: "tranvía", subway: "metro", light_rail: "metro ligero", narrow_gauge: "vía estrecha",
};
/* Lo de cada día: comercios, servicios, transporte y aire libre. */
Object.assign(VALOR_OSM, {
  restaurant: "restaurante", food_court: "zona de restaurantes", cafe: "cafetería", bar: "bar", pub: "pub", biergarten: "cervecería al aire libre", fast_food: "comida rápida",
  ice_cream: "heladería", nightclub: "discoteca", supermarket: "supermercado", convenience: "tienda de alimentación", greengrocer: "frutería", butcher: "carnicería", seafood: "pescadería",
  deli: "charcutería", frozen_food: "congelados", health_food: "herbolario", cheese: "quesería", bakery: "panadería", pastry: "pastelería", confectionery: "confitería", beverages: "bebidas",
  alcohol: "licorería", wine: "vinoteca", mall: "centro comercial", department_store: "grandes almacenes", marketplace: "mercado", paint: "tienda de pinturas", art: "bellas artes",
  craft: "manualidades", doityourself: "bricolaje", hardware: "ferretería", trade: "almacén de construcción", tobacco: "estanco", newsagent: "prensa", kiosk: "quiosco", lottery: "lotería",
  clothes: "ropa", shoes: "zapatería", hairdresser: "peluquería", beauty: "estética", optician: "óptica", chemist: "droguería", florist: "floristería", bicycle: "tienda de bicis",
  car: "concesionario", car_repair: "taller", tyres: "neumáticos", motorcycle_repair: "taller de motos", mobile_phone: "telefonía", electronics: "electrónica", computer: "informática",
  books: "librería", stationery: "papelería", toys: "juguetería", furniture: "muebles", jewelry: "joyería", gift: "regalos", sports: "deportes", laundry: "lavandería",
  dry_cleaning: "tintorería", pet: "tienda de animales", travel_agency: "agencia de viajes", copyshop: "copistería", variety_store: "bazar", second_hand: "segunda mano",
  tattoo: "tatuajes", estate_agent: "inmobiliaria", funeral_directors: "funeraria", vacant: "local vacío", pharmacy: "farmacia", hospital: "hospital", clinic: "centro de salud",
  doctors: "consulta médica", dentist: "dentista", veterinary: "veterinario", bank: "banco", atm: "cajero", bureau_de_change: "cambio de moneda", post_office: "oficina de correos",
  post_box: "buzón", parcel_locker: "taquilla de paquetes", townhall: "ayuntamiento", courthouse: "juzgado", community_centre: "centro cívico", government: "oficina pública",
  diplomatic: "embajada o consulado", fire_station: "parque de bomberos", ambulance_station: "base de ambulancias", lifeguard: "puesto de socorro", defibrillator: "desfibrilador",
  phone: "teléfono de emergencia", school: "colegio", university: "universidad", college: "centro de estudios", kindergarten: "escuela infantil", library: "biblioteca",
  music_school: "escuela de música", language_school: "academia de idiomas", driving_school: "autoescuela", toilets: "aseos", shower: "duchas", drinking_water: "fuente de agua potable",
  water_point: "toma de agua", recycling: "punto de reciclaje", waste_disposal: "contenedor", place_of_worship: "lugar de culto", prison: "prisión", hotel: "hotel", hostel: "albergue",
  guest_house: "pensión", motel: "motel", apartment: "apartamento turístico", chalet: "casa rural", museum: "museo", gallery: "galería de arte", attraction: "atracción",
  theme_park: "parque de atracciones", zoo: "zoológico", aquarium: "acuario", theatre: "teatro", cinema: "cine", arts_centre: "centro cultural", sports_centre: "polideportivo",
  stadium: "estadio", fitness_centre: "gimnasio", fitness_station: "aparatos de gimnasia", water_park: "parque acuático", ice_rink: "pista de hielo", playground: "parque infantil",
  dog_park: "zona para perros", park: "parque", garden: "jardín", nature_reserve: "reserva natural", pitch: "pista deportiva", swimming_pool: "piscina", peak: "cima", volcano: "volcán",
  saddle: "collado", beach: "playa", spring: "manantial", hot_spring: "fuente termal", waterfall: "cascada", tree: "árbol", camp_site: "camping", caravan_site: "área de autocaravanas",
  picnic_site: "merendero", alpine_hut: "refugio de montaña", wilderness_hut: "refugio libre", bus_station: "estación de autobuses", tram_stop: "parada de tranvía",
  bus_stop: "parada de autobús", taxi: "parada de taxi", bicycle_rental: "bicis de alquiler", "kick-scooter_rental": "patinetes de alquiler", bicycle_parking: "aparcabicis",
  fuel: "gasolinera", charging_station: "punto de recarga", parking: "aparcamiento", parking_entrance: "entrada de aparcamiento", motorcycle_parking: "aparcamiento de motos",
  car_wash: "lavadero de coches", vehicle_inspection: "ITV", car_rental: "alquiler de coches", aerodrome: "aeródromo", helipad: "helipuerto", heliport: "helipuerto",
  marina: "puerto deportivo", ferry_terminal: "terminal de ferri", lighthouse: "faro", cycleway: "carril bici", steps: "escaleras", elevator: "ascensor", lift_gate: "barrera levadiza",
  swing_gate: "barrera batiente", sliding_gate: "puerta corredera", turnstile: "torno", "full-height_turnstile": "torno de cuerpo entero", border_control: "control fronterizo",
  toll_booth: "peaje", sally_port: "esclusa de seguridad", gate: "puerta", bollard: "bolardo", data_center: "centro de datos", exchange: "central telefónica",
  central_office: "central telefónica", street_cabinet: "armario de calle", manhole: "tapa de registro", billboard: "valla publicitaria", column: "columna publicitaria",
  poster_box: "mupi", totem: "tótem publicitario", screen: "pantalla publicitaria", board: "tablón", farm_auxiliary: "nave agrícola", barn: "granero", cowshed: "establo", sty: "pocilga",
  stable: "cuadra", greenhouse: "invernadero", slurry_tank: "balsa de purines", farmyard: "corral", greenhouse_horticulture: "invernaderos", wlan: "wifi", limited: "con limitaciones",
  designated: "reservado", underground: "subterráneo", "multi-storey": "en altura", surface: "en superficie", street_side: "en la calle", lane: "en la calzada", only: "solo eso",
  train_station: "estación de tren", apartments: "edificio de viviendas", commercial: "edificio comercial", retail: "local comercial", office: "oficinas", public: "edificio público",
  wall_loops: "de rueda", stands: "de horquilla", rack: "de barra", shed: "cubierto", christian: "cristiana", muslim: "musulmana", jewish: "judía", catholic: "católica",
});
/* Algunas palabras significan otra cosa según la etiqueta en la que van. */
const VALOR_POR_CLAVE = {
  highway: { residential: "calle", living_street: "calle residencial", pedestrian: "calle peatonal", primary: "avenida o carretera principal", secondary: "calle o carretera", tertiary: "calle",
    unclassified: "calle o camino", footway: "paso peatonal", path: "sendero", track: "camino", motorway: "autopista", trunk: "autovía", service: "vía de servicio", square: "plaza",
    bus_stop: "parada de autobús", steps: "escaleras", cycleway: "carril bici" },
  place: { house: "portal", street: "calle", locality: "paraje", district: "distrito", city: "ciudad", town: "ciudad", village: "pueblo", hamlet: "aldea", suburb: "barrio",
    neighbourhood: "barrio", quarter: "barrio", borough: "distrito", county: "comarca", state: "comunidad autónoma", country: "país", island: "isla", square: "plaza", other: "lugar" },
  building: { yes: "edificio", house: "casa", residential: "edificio de viviendas", industrial: "nave industrial", warehouse: "almacén", church: "iglesia", farm: "masía o granja" },
  landuse: { residential: "zona residencial", industrial: "polígono industrial", commercial: "zona comercial", retail: "zona comercial", farmland: "campo de cultivo", forest: "bosque" },
  railway: { station: "estación de tren", halt: "apeadero", tram_stop: "parada de tranvía", subway_entrance: "boca de metro" },
};
const valorOSM = (v, clave) => String(v).split(";").map((x) => { const u = x.trim(); return (VALOR_POR_CLAVE[clave] || {})[u] || VALOR_OSM[u] || u.replace(/_/g, " "); }).join(", ");
/* Qué es algo, por sus etiquetas: «Farmacia», «Calle peatonal». Las claves van de la más concreta a la más general. */
const CLAVES_DE_TIPO = ["amenity", "shop", "tourism", "leisure", "railway", "public_transport", "aeroway", "emergency", "advertising", "barrier", "telecom", "man_made", "historic",
  "natural", "waterway", "office", "highway", "place", "building", "landuse"];
function tipoDeEtiquetas(t) {
  for (const k of CLAVES_DE_TIPO) {
    const v = t[k], nombre = v && ((VALOR_POR_CLAVE[k] || {})[v] || VALOR_OSM[v]);
    if (nombre && nombre !== "sí") return nombre.replace(/^./, (x) => x.toUpperCase());
  }
  return "";
}
const tituloOSM = (t, ...claves) => { for (const c of claves) if (t[c]) return valorOSM(t[c], c).replace(/^./, (x) => x.toUpperCase()); return ""; };

/* --- Capas a partir de etiquetas de OpenStreetMap ---
   Una capa de OpenStreetMap se describe por sus etiquetas. Cada condición es un objeto
   { clave: "valor|otro" }: `true` vale por «cualquier valor» y un valor que empieza por «~» se busca
   dentro del texto (sirve para listas como «skateboard;bmx»). Dentro de una condición han de
   cumplirse todas las claves, y basta con que se cumpla una condición. De ahí salen la pregunta
   para el servidor (ql) y la prueba de si un elemento es de la capa (es). */
function deOSM(condiciones, consulta = "nwr") {
  const expresion = (v) => (v === true ? null : v[0] === "~" ? new RegExp(v.slice(1)) : new RegExp(`^(${v})$`));
  const pruebas = condiciones.map((c) => Object.entries(c).map(([k, v]) => [k, expresion(v)]));
  const filtro = ([k, v]) => (v === true ? `["${k}"]` : v[0] === "~" ? `["${k}"~"${v.slice(1)}"]` : v.includes("|") ? `["${k}"~"^(${v})$"]` : `["${k}"="${v}"]`);
  return {
    ql: condiciones.map((c) => consulta + Object.entries(c).map(filtro).join("")),
    es: (t) => pruebas.some((pares) => pares.every(([k, re]) => (re ? re.test(t[k] || "") : !!t[k]))),
  };
}
/* id, grupo, nombre de la capa, nombre de uno de sus elementos, color, zoom mínimo, condiciones y lo demás
   (`buscar`: las palabras con las que el buscador ofrece «… cerca de aquí»). */
const capaOSM = (id, grupo, nombre, uno, color, zoom, condiciones, extra = {}) =>
  Object.assign({ id, grupo, nombre, uno, color, zoom, tipo: "osm", titulo: () => uno, condiciones }, deOSM(condiciones, extra.consulta), extra);

const CAPAS_VIGILANCIA_MAS = [
  capaOSM("barreras", "Vigilancia", "Barreras, tornos y controles de paso", "Barrera o control de paso", "#9f1239", 16,
    [{ barrier: "lift_gate|swing_gate|sliding_gate|turnstile|full-height_turnstile|border_control|toll_booth|sally_port" }], { consulta: "node", buscar: "barrera barreras torno control de acceso" }),
  capaOSM("prisiones", "Vigilancia", "Prisiones y centros de internamiento", "Centro penitenciario", "#450a0a", 9, [{ amenity: "prison" }], { icono: "cerraduras", buscar: "prision carcel penitenciario" }),
];
const CAPAS_INFRA_MAS = [
  capaOSM("telecom", "Infraestructura", "Centros de datos y armarios de calle", "Instalación de telecomunicaciones", "#0e7490", 16,
    [{ telecom: "data_center|exchange|central_office" }, { building: "data_center" }, { man_made: "street_cabinet" }], { icono: "datos", buscar: "centro de datos armario telefonica" }),
  capaOSM("tapas", "Infraestructura", "Tapas de registro y alcantarillas", "Tapa de registro", "#57534e", 18, [{ man_made: "manhole" }, { manhole: true }], { consulta: "node", tamano: 0.62, buscar: "alcantarilla tapa registro" }),
  capaOSM("granjas", "Infraestructura", "Granjas, establos e invernaderos", "Construcción agraria", "#a16207", 15,
    [{ building: "farm|farm_auxiliary|barn|cowshed|sty|stable|greenhouse|silo|slurry_tank" }, { landuse: "farmyard|greenhouse_horticulture" }], { buscar: "granja establo invernadero" }),
];
const CAPAS_CALLE_MAS = [
  capaOSM("publicidad", "A pie de calle", "Publicidad: vallas, mupis y pantallas", "Soporte publicitario", "#f43f5e", 16, [{ advertising: true }], { buscar: "valla publicitaria mupi cartel publicidad pantalla" }),
  capaOSM("skate", "A pie de calle", "Skateparks y parkour", "Pista de skate", "#db2777", 13, [{ sport: "~skateboard|bmx|parkour|roller_skating" }], { buscar: "skate skatepark parkour patinaje" }),
  capaOSM("escaleras", "A pie de calle", "Escaleras y ascensores", "Escalera", "#a8a29e", 17, [{ highway: "steps|elevator" }], { lineas: true, color_linea: "#e7e5e4", trazo: "3 5", buscar: "escaleras ascensor" }),
];

/* --- Como en un mapa de calle: transporte, comer, comprar, servicios, ocio y aire libre --- */
const CAPAS_DIARIO = [
  // Transporte
  { id: "paradas", grupo: "Transporte", nombre: "Paradas de bus, metro y tren (con próximas salidas)", uno: "Parada", color: "#1d4ed8", zoom: 15, tipo: "api", pedir: pedirParadas, vida: 7,
    buscar: "parada paradas autobus bus metro tranvia emt marquesina" },
  capaOSM("estaciones", "Transporte", "Estaciones de tren, metro y autobús", "Estación", "#1e40af", 11,
    [{ railway: "station|halt|tram_stop" }, { public_transport: "station" }, { amenity: "bus_station" }], { icono: "tren_ruta", buscar: "estacion estaciones tren renfe cercanias ave" }),
  capaOSM("taxis", "Transporte", "Paradas de taxi", "Parada de taxi", "#ca8a04", 14, [{ amenity: "taxi" }], { buscar: "taxi taxis" }),
  capaOSM("bicis", "Transporte", "Bicis y patinetes de alquiler", "Bicis de alquiler", "#16a34a", 14, [{ amenity: "bicycle_rental|kick-scooter_rental" }], { buscar: "bici bicis valenbisi bicicleta alquiler patinete" }),
  capaOSM("aparcabicis", "Transporte", "Aparcamientos de bicis", "Aparcabicis", "#4d7c0f", 16, [{ amenity: "bicycle_parking" }], { tamano: 0.75, buscar: "aparcabicis aparcar bici" }),
  capaOSM("carrilbici", "Transporte", "Carriles bici", "Carril bici", "#16a34a", 14, [{ highway: "cycleway" }], { consulta: "way", lineas: true, color_linea: "#4ade80", icono: "bicis", buscar: "carril bici ciclovia" }),
  { id: "gasolineras", grupo: "Transporte", nombre: "Gasolineras con el precio de hoy (España)", uno: "Gasolinera", color: "#b45309", zoom: 11, tipo: "api", pedir: pedirGasolineras, vida: 0.2,
    buscar: "gasolinera gasolineras gasolina diesel gasoil gasoleo combustible repostar" },
  capaOSM("recarga", "Transporte", "Puntos de recarga eléctrica", "Punto de recarga", "#059669", 13, [{ amenity: "charging_station" }], { buscar: "cargador cargadores recarga electrico electrolinera" }),
  capaOSM("aparcamientos", "Transporte", "Aparcamientos", "Aparcamiento", "#2563eb", 15, [{ amenity: "parking|parking_entrance|motorcycle_parking" }], { buscar: "parking aparcamiento aparcamientos aparcar garaje" }),
  capaOSM("talleres", "Transporte", "Talleres, ITV, neumáticos y lavaderos", "Taller", "#64748b", 15,
    [{ shop: "car_repair|tyres|motorcycle_repair" }, { amenity: "car_wash|vehicle_inspection|car_rental" }], { buscar: "taller talleres neumaticos lavadero itv mecanico alquiler de coches" }),
  capaOSM("aeropuertos", "Transporte", "Aeropuertos, aeródromos y helipuertos", "Aeródromo", "#334155", 9, [{ aeroway: "aerodrome|helipad|heliport" }], { buscar: "aeropuerto aerodromo helipuerto" }),
  capaOSM("puertos", "Transporte", "Puertos, embarcaderos y faros", "Puerto", "#0c4a6e", 11,
    [{ leisure: "marina" }, { amenity: "ferry_terminal" }, { man_made: "lighthouse" }, { harbour: "yes" }], { buscar: "puerto marina ferry faro embarcadero" }),
  // Comer y beber
  capaOSM("restaurantes", "Comer y beber", "Restaurantes", "Restaurante", "#ea580c", 16, [{ amenity: "restaurant|food_court" }], { buscar: "restaurante restaurantes comer cenar comida almorzar" }),
  capaOSM("bares", "Comer y beber", "Bares", "Bar", "#c2410c", 16, [{ amenity: "bar|pub|biergarten" }], { buscar: "bar bares cerveza pub cañas tapas" }),
  capaOSM("cafes", "Comer y beber", "Cafeterías", "Cafetería", "#92400e", 16, [{ amenity: "cafe" }], { buscar: "cafe cafeteria cafeterias cafes desayuno desayunar" }),
  capaOSM("comida_rapida", "Comer y beber", "Comida rápida y heladerías", "Comida rápida", "#d97706", 16, [{ amenity: "fast_food|ice_cream" }], { buscar: "hamburguesa hamburgueseria pizza pizzeria kebab bocadillo heladeria helado comida rapida" }),
  capaOSM("copas", "Comer y beber", "Discotecas y salas", "Discoteca", "#9d174d", 14, [{ amenity: "nightclub" }], { buscar: "discoteca discotecas club sala" }),
  // Compras
  capaOSM("supermercados", "Compras", "Supermercados y alimentación", "Tienda de alimentación", "#7c3aed", 15,
    [{ shop: "supermarket|convenience|greengrocer|butcher|seafood|deli|frozen_food|health_food|cheese|beverages|alcohol|wine" }],
    { buscar: "supermercado supermercados mercadona consum lidl aldi carrefour dia compra fruteria carniceria pescaderia alimentacion" }),
  capaOSM("panaderias", "Compras", "Panaderías y pastelerías", "Panadería", "#a16207", 16, [{ shop: "bakery|pastry|confectionery" }], { buscar: "panaderia pan horno pasteleria" }),
  capaOSM("mercados", "Compras", "Mercados y centros comerciales", "Centro comercial", "#6d28d9", 13, [{ amenity: "marketplace" }, { shop: "mall|department_store" }], { buscar: "mercado mercados centro comercial corte ingles" }),
  capaOSM("pintura", "Compras", "Pintura, bellas artes y ferretería", "Tienda de pintura o ferretería", "#be185d", 15, [{ shop: "paint|art|craft|doityourself|hardware|trade" }],
    { icono: "spray", buscar: "pintura spray sprays ferreteria bricolaje bellas artes rotuladores leroy" }),
  capaOSM("estancos", "Compras", "Estancos y quioscos", "Estanco o quiosco", "#a21caf", 16, [{ shop: "tobacco|newsagent|kiosk|lottery" }], { buscar: "estanco tabaco quiosco prensa loteria" }),
  capaOSM("tiendas", "Compras", "Todas las tiendas", "Tienda", "#8b5cf6", 17, [{ shop: true }], { tamano: 0.85, buscar: "tienda tiendas comercio" }),
  // Servicios
  capaOSM("farmacias", "Servicios", "Farmacias", "Farmacia", "#16a34a", 14, [{ amenity: "pharmacy" }], { buscar: "farmacia farmacias" }),
  capaOSM("salud", "Servicios", "Hospitales, centros de salud y médicos", "Centro sanitario", "#dc2626", 13, [{ amenity: "hospital|clinic|doctors|dentist" }],
    { icono: "hospitales", buscar: "hospital hospitales urgencias centro de salud ambulatorio medico dentista clinica" }),
  capaOSM("veterinarios", "Servicios", "Veterinarios", "Veterinario", "#0d9488", 14, [{ amenity: "veterinary" }], { buscar: "veterinario veterinarios veterinaria" }),
  capaOSM("bancos", "Servicios", "Bancos y cajeros", "Banco o cajero", "#0f766e", 15, [{ amenity: "bank|atm|bureau_de_change" }], { icono: "cajeros", buscar: "banco bancos cajero cajeros sacar dinero" }),
  capaOSM("correos", "Servicios", "Correos, buzones y taquillas de paquetes", "Correos o taquilla", "#ca8a04", 15, [{ amenity: "post_office|post_box|parcel_locker" }], { buscar: "correos buzon paquete paquetes taquilla locker" }),
  capaOSM("administracion", "Servicios", "Ayuntamientos, juzgados y oficinas públicas", "Oficina pública", "#475569", 13,
    [{ amenity: "townhall|courthouse|community_centre" }, { office: "government|diplomatic" }], { icono: "ayuntamientos", buscar: "ayuntamiento juzgado juzgados embajada consulado hacienda seguridad social oficina" }),
  capaOSM("emergencias", "Servicios", "Bomberos, ambulancias y desfibriladores", "Punto de emergencias", "#b91c1c", 14,
    [{ amenity: "fire_station" }, { emergency: "ambulance_station|lifeguard|defibrillator|phone" }], { buscar: "bomberos ambulancia desfibrilador socorrista" }),
  capaOSM("educacion", "Servicios", "Colegios, universidades y bibliotecas", "Centro educativo", "#0369a1", 15,
    [{ amenity: "school|university|college|kindergarten|library|music_school|language_school|driving_school" }], { icono: "colegios", buscar: "colegio instituto universidad biblioteca guarderia autoescuela academia" }),
  capaOSM("aseos", "Servicios", "Aseos y duchas", "Aseos", "#0891b2", 15, [{ amenity: "toilets|shower" }], { buscar: "aseo aseos baño baños wc lavabo ducha" }),
  capaOSM("fuentes", "Servicios", "Fuentes de agua potable", "Fuente", "#0ea5e9", 15, [{ amenity: "drinking_water|water_point" }], { buscar: "fuente fuentes agua potable beber" }),
  capaOSM("reciclaje", "Servicios", "Contenedores y puntos limpios", "Punto de reciclaje", "#65a30d", 16, [{ amenity: "recycling|waste_disposal" }], { buscar: "contenedor contenedores reciclaje punto limpio ecoparque basura" }),
  capaOSM("culto", "Servicios", "Lugares de culto", "Lugar de culto", "#78716c", 14, [{ amenity: "place_of_worship" }], { buscar: "iglesia iglesias mezquita sinagoga templo parroquia" }),
  capaOSM("wifi", "Servicios", "Wifi abierto o para clientes", "Sitio con wifi", "#0284c7", 16, [{ internet_access: "wlan|yes" }], { buscar: "wifi internet" }),
  // Ocio, cultura y alojamiento
  capaOSM("hoteles", "Ocio, cultura y alojamiento", "Hoteles y alojamientos", "Alojamiento", "#be123c", 14, [{ tourism: "hotel|hostel|guest_house|motel|apartment|chalet" }],
    { buscar: "hotel hoteles hostal albergue alojamiento dormir pension apartamento" }),
  capaOSM("cultura", "Ocio, cultura y alojamiento", "Museos, cines, teatros y atracciones", "Sitio de cultura u ocio", "#7e22ce", 13,
    [{ tourism: "museum|gallery|attraction|theme_park|zoo|aquarium" }, { amenity: "theatre|cinema|arts_centre" }], { icono: "museos", buscar: "museo museos cine cines teatro galeria exposicion zoo atraccion" }),
  capaOSM("deporte", "Ocio, cultura y alojamiento", "Polideportivos, gimnasios y estadios", "Instalación deportiva", "#15803d", 14,
    [{ leisure: "sports_centre|stadium|fitness_centre|fitness_station|water_park|ice_rink" }], { buscar: "gimnasio gimnasios polideportivo estadio deporte crossfit" }),
  capaOSM("juegos", "Ocio, cultura y alojamiento", "Parques infantiles y zonas para perros", "Zona de juegos", "#e879a6", 16, [{ leisure: "playground|dog_park" }], { buscar: "parque infantil columpios pipican perros" }),
  // Naturaleza y aire libre
  capaOSM("parques", "Naturaleza y aire libre", "Parques, jardines y reservas", "Parque", "#15803d", 14, [{ leisure: "park|garden|nature_reserve" }], { buscar: "parque parques jardin jardines" }),
  capaOSM("picos", "Naturaleza y aire libre", "Picos y collados", "Cima", "#57534e", 11, [{ natural: "peak|volcano|saddle" }], { consulta: "node", buscar: "pico cima montaña collado" }),
  capaOSM("playas", "Naturaleza y aire libre", "Playas", "Playa", "#d97706", 11, [{ natural: "beach" }], { buscar: "playa playas cala" }),
  capaOSM("manantiales", "Naturaleza y aire libre", "Manantiales y cascadas", "Manantial", "#0284c7", 13, [{ natural: "spring|hot_spring" }, { waterway: "waterfall" }], { buscar: "manantial cascada nacimiento salto de agua" }),
  capaOSM("acampada", "Naturaleza y aire libre", "Camping, refugios y áreas recreativas", "Área de acampada o refugio", "#166534", 12,
    [{ tourism: "camp_site|caravan_site|picnic_site|alpine_hut|wilderness_hut" }], { icono: "camping", buscar: "camping acampada refugio picnic merendero area recreativa" }),
  capaOSM("arboles", "Naturaleza y aire libre", "Árboles singulares", "Árbol singular", "#4d7c0f", 13, [{ natural: "tree", denotation: true }, { natural: "tree", name: true }], { consulta: "node", buscar: "arbol monumental" }),
];

/* --- València: lo que publica el Ayuntamiento (geoportal de datos abiertos) ---
   `servicios` son «Tema/número» del geoportal; `ajuste` retoca cada elemento (su nombre, su color). */
const vlc = (id, grupo, nombre, color, zoom, servicios, extra = {}) => {
  const urls = servicios.map((s) => `${VALENCIA}/${s.split("/")[0]}/MapServer/${s.split("/")[1]}`), traer = arcgis(urls, extra.ajuste);
  // Lo que cambia cada pocos minutos no se guarda: se vuelve a pedir lo que se ve, cada tanto.
  return Object.assign({ id, grupo, nombre, color, zoom }, extra.cada ? { tipo: "vivo", alMover: true, pedir: () => traer(cajaDeLaVista()) } : { tipo: "api", pedir: traer }, extra);
};
const SEMAFORO = ["#16a34a", "#d97706", "#dc2626", "#111827"];      // de bien a mal
const ESTADO_TRAFICO = ["fluido", "denso", "congestionado", "cortado", "sin datos"];
const numero = (v) => (v == null || v === "" || Number.isNaN(+v) ? null : +v);
const CAPAS_VALENCIA = [
  // Movilidad
  vlc("valenbisi", "València: movilidad", "Valenbisi: bicis libres ahora", "#16a34a", 13, ["Trafico/228"], { icono: "bicis", cada: 60000, buscar: "valenbisi", ajuste: (e) => {
    const bicis = numero(e.p.available), huecos = numero(e.p.free);
    e.nombre = `${bicis ?? "?"} bicis y ${huecos ?? "?"} huecos: ${limpio(e.p.address) || "Valenbisi"}`;
    e.color = e.p.open === "F" ? "#6b7280" : SEMAFORO[bicis === 0 ? 2 : bicis <= 3 ? 1 : 0];
  } }),
  vlc("parkings_vlc", "València: movilidad", "Aparcamientos: plazas libres ahora", "#2563eb", 12, ["Trafico/194"], { icono: "aparcamientos", cada: 120000, ajuste: (e) => {
    const libres = numero(e.p.plazaslibr), total = numero(e.p.plazastota);
    e.nombre = `${limpio(e.p.nombre) || "Aparcamiento"}: ${libres != null ? `${miles(libres)} plazas libres` : "sin dato"}${total ? ` de ${miles(total)}` : ""}`;
    e.color = libres == null ? "#6b7280" : SEMAFORO[libres === 0 ? 2 : total && libres / total < 0.1 ? 1 : 0];
  } }),
  vlc("trafico_vlc", "València: movilidad", "Estado del tráfico ahora", "#16a34a", 12, ["Trafico/192"], { icono: "trafico", cada: 180000, buscar: "trafico atasco atascos", ajuste: (e) => {
    const n = numero(e.p.estado), k = n == null ? 4 : n >= 5 && n <= 8 ? n - 5 : n > 3 ? 4 : n;
    e.nombre = `${limpio(e.p.denominacion) || "Tramo"}: ${ESTADO_TRAFICO[k]}`;
    e.color = k === 4 ? "#9ca3af" : SEMAFORO[k];
    e.datos = [["Estado", ESTADO_TRAFICO[k]], ["Tramo", e.p.denominacion]];
  } }),
  vlc("fgv", "València: movilidad", "Metro y tranvía: estaciones y bocas", "#b91c1c", 13, ["Trafico/221", "Trafico/220"], { icono: "metro", ajuste: (e) => {
    e.nombre = `${limpio(e.p.nombre || e.p.denominacion)}${e.p.linea || e.p.lineas ? ` (líneas ${e.p.linea || e.p.lineas})` : ""}`;
    if (e.p.idboca != null) { e.nombre = `Boca de metro: ${e.nombre}`; e.color = "#f87171"; }
  } }),
  vlc("emt", "València: movilidad", "Paradas de la EMT", "#b91c1c", 15, ["Trafico/226"], { icono: "paradas", tamano: 0.85, ajuste: (e) => { e.nombre = `${limpio(e.p.denominacion)}${e.p.lineas ? `: líneas ${e.p.lineas}` : ""}`; } }),
  vlc("taxis_vlc", "València: movilidad", "Paradas de taxi", "#ca8a04", 13, ["Trafico/185"], { icono: "taxis", ajuste: (e) => { e.nombre = `Parada de taxi: ${limpio(e.p.calle)}${e.p.numplazas ? ` (${e.p.numplazas} plazas)` : ""}`; } }),
  vlc("carril_vlc", "València: movilidad", "Carril bici oficial", "#22c55e", 13, ["Trafico/189"], { icono: "bicis", ajuste: (e) => { e.nombre = "Carril bici"; } }),
  vlc("aparcabicis_vlc", "València: movilidad", "Aparcabicis", "#4d7c0f", 16, ["Trafico/206"], { icono: "aparcabicis", tamano: 0.7, ajuste: (e) => { e.nombre = `Aparcabicis${e.p.numplazas ? ` de ${e.p.numplazas} plazas` : ""}`; } }),
  vlc("recarga_vlc", "València: movilidad", "Recarga de vehículos eléctricos", "#059669", 12, ["Trafico/183", "UrbanismoEInfraestructuras/288"], { icono: "recarga", ajuste: (e) => { e.nombre = `Punto de recarga${e.nombre ? `: ${e.nombre}` : ""}`; } }),
  vlc("ora", "València: movilidad", "Zona azul, naranja y verde (ORA)", "#2563eb", 17, ["Trafico/205"], { icono: "aparcamientos", ajuste: (e) => {
    e.nombre = `Aparcamiento regulado${e.p.color ? `: zona ${String(e.p.color).toLowerCase()}` : ""}`;
    e.color = { azul: "#2563eb", naranja: "#ea580c", verde: "#16a34a", blanco: "#e5e7eb" }[sinAcentos(e.p.color)] || "#2563eb";
  } }),
  vlc("reservado_vlc", "València: movilidad", "Plazas reservadas: movilidad reducida, motos y carga", "#0369a1", 16, ["Trafico/207", "Trafico/195", "Trafico/178"], { icono: "accesible", tamano: 0.75 }),
  vlc("obras_vlc", "València: movilidad", "Obras, cortes y ocupaciones de la calle", "#ea580c", 13, ["Trafico/235", "Trafico/209", "Trafico/233", "Trafico/234"], { icono: "obras", buscar: "obras cortes", ajuste: (e) => {
    e.nombre = limpio(e.p.desc_incidencia) || `${e.p.tipo_incidencia ? limpio(e.p.tipo_incidencia).toLowerCase().replace(/^./, (x) => x.toUpperCase()) : "Ocupación de la vía"}${e.p.ocupacion ? `: ${limpio(e.p.ocupacion).toLowerCase()}` : ""}`;
  } }),
  vlc("bolardos", "València: movilidad", "Bolardos retráctiles", "#7c2d12", 14, ["Trafico/215"], { icono: "barreras", ajuste: (e) => { e.nombre = `Bolardo retráctil: ${limpio(e.p.calle)} ${limpio(e.p.numerocall)}`.trim(); } }),
  vlc("semaforos", "València: movilidad", "Semáforos (cruces regulados)", "#65a30d", 15, ["Trafico/182"], { tamano: 0.75, ajuste: (e) => { e.nombre = `Semáforo: ${limpio(e.p.descripcion)}`; } }),
  vlc("espiras", "València: movilidad", "Aforos de tráfico y de bicis (espiras)", "#0e7490", 15, ["Trafico/208", "Trafico/225"], { tamano: 0.75, vida: 0.02, ajuste: (e) => {
    const ih = numero(e.p.ih);
    e.nombre = ih != null && ih >= 0 ? `Aforo: ${miles(ih)} vehículos por hora` : "Punto de aforo";
  } }),
  vlc("paneles", "València: movilidad", "Paneles informativos de tráfico", "#a16207", 13, ["Trafico/187"], { icono: "pantallas", ajuste: (e) => { e.nombre = `Panel: ${limpio(e.p.descrip)}`; } }),
  vlc("vados", "València: movilidad", "Vados (entradas de garaje)", "#78716c", 17, ["Trafico/179"], { icono: "puertas", tamano: 0.7, ajuste: (e) => { e.nombre = `Vado ${limpio(e.p.numplaca)}${e.p.numplazas ? `: ${e.p.numplazas} plazas` : ""}`; } }),
  // Ciudad
  vlc("aire_vlc", "València: ciudad", "Calidad del aire ahora (estaciones)", "#0891b2", 10, ["MedioAmbiente/156"], { icono: "aire", cada: 600000, buscar: "calidad del aire contaminacion", ajuste: (e) => {
    const c = limpio(e.p.calidad_am);
    e.nombre = `${limpio(e.p.nombre)}: aire ${c ? c.toLowerCase() : "sin dato"}`;
    e.color = /muy desfav|extrem/i.test(c) ? "#7f1d1d" : /desfav/i.test(c) ? "#dc2626" : /regular/i.test(c) ? "#d97706" : /buena/i.test(c) ? "#16a34a" : "#6b7280";
  } }),
  vlc("meteo_vlc", "València: ciudad", "Estaciones meteorológicas ahora", "#0284c7", 10, ["MedioAmbiente/157"], { icono: "meteo", cada: 600000, ajuste: (e) => {
    e.nombre = `${limpio(e.p.nombre)}${numero(e.p.temperatur) != null ? `: ${String(e.p.temperatur).replace(".", ",")} °C` : ""}`;
  } }),
  vlc("ruido_vlc", "València: ciudad", "Sonómetros", "#7c3aed", 12, ["MedioAmbiente/160", "MedioAmbiente/161"], { icono: "ruido" }),
  vlc("fuentes_vlc", "València: ciudad", "Fuentes de agua", "#0ea5e9", 15, ["MedioAmbiente/158"], { icono: "fuentes", tamano: 0.8, ajuste: (e) => { e.nombre = `Fuente: ${limpio(e.p.calle)}`; if (urlSegura(String(e.p.foto || "").replace(/^http:/, "https:"))) e.imagen = String(e.p.foto).replace(/^http:/, "https:"); } }),
  vlc("aseos_vlc", "València: ciudad", "Aseos y urinarios públicos", "#0891b2", 13, ["MedioAmbiente/167", "Turismo/217"], { icono: "aseos", ajuste: (e) => { e.nombre = `Aseo público: ${limpio(e.p.jardin || e.p.direccion)}`; } }),
  vlc("jardines_vlc", "València: ciudad", "Jardines y espacios verdes", "#15803d", 14, ["MedioAmbiente/8"], { icono: "parques" }),
  vlc("arbolado", "València: ciudad", "Arbolado: los 158.000 árboles, uno a uno", "#4d7c0f", 18, ["MedioAmbiente/151"], { icono: "arboles", tamano: 0.6, ajuste: (e) => { e.nombre = limpio(e.p.nom_comu_c || e.p.nom_botanico) || "Árbol"; } }),
  vlc("arboles_vlc", "València: ciudad", "Arbolado protegido", "#166534", 13, ["MedioAmbiente/152"], { icono: "arboles" }),
  vlc("contenedores", "València: ciudad", "Contenedores (residuos, vidrio, ropa, aceite y pilas)", "#65a30d", 18, ["MedioAmbiente/0", "MedioAmbiente/168", "MedioAmbiente/164", "MedioAmbiente/153", "MedioAmbiente/159"],
    { icono: "reciclaje", tamano: 0.6, ajuste: (e) => { e.nombre = `Contenedor${e.p.tipo ? ` de ${limpio(e.p.tipo).toLowerCase()}` : ""}`; } }),
  vlc("juegos_vlc", "València: ciudad", "Juegos infantiles y zonas caninas", "#e879a6", 15, ["MedioAmbiente/166", "MedioAmbiente/163"], { icono: "juegos", tamano: 0.8 }),
  vlc("wifi_vlc", "València: ciudad", "Wifi municipal", "#0284c7", 13, ["Turismo/200"], { icono: "wifi", ajuste: (e) => { e.nombre = `Wifi: ${limpio(e.p.descripcion)}`; } }),
  vlc("monumentos_vlc", "València: ciudad", "Monumentos y recursos turísticos", "#a97142", 13, ["Turismo/202", "Turismo/226"], { icono: "historico", forma: "rombo" }),
  vlc("arqueologia", "València: ciudad", "Excavaciones e intervenciones arqueológicas", "#92400e", 14, ["Turismo/228"], { forma: "rombo", buscar: "arqueologia excavacion", ajuste: (e) => {
    e.nombre = `${limpio(e.p.tipo_intervencion) || "Intervención arqueológica"}: ${limpio(e.p.acronimo || e.p.direccion)}`;
  } }),
  vlc("fallas", "València: ciudad", "Fallas: monumentos y carpas", "#f97316", 13, ["Turismo/215", "Turismo/0", "Turismo/205"], { icono: "fiesta", buscar: "falla fallas", ajuste: (e) => { if (e.p.seccion) e.nombre = `Falla ${e.nombre} (sección ${e.p.seccion})`; } }),
  vlc("hidrantes", "València: ciudad", "Hidrantes e hitos de bomberos", "#dc2626", 16, ["UrbanismoEInfraestructuras/222", "Trafico/239"], { tamano: 0.75, ajuste: (e) => { e.nombre = e.p.codigo ? `Hidrante ${e.p.codigo}` : "Hito de bomberos"; } }),
  vlc("mupis", "València: ciudad", "Mupis, columnas y mobiliario informativo", "#f43f5e", 15, ["UrbanismoEInfraestructuras/3", "UrbanismoEInfraestructuras/285"], { icono: "publicidad", tamano: 0.8, ajuste: (e) => {
    e.nombre = e.p.nummupi != null ? `Mupi n.º ${e.p.nummupi}: ${limpio(e.p.emplazamiento)}` : `${limpio(e.p.tipo) || "Soporte"} ${limpio(e.p.uso).toLowerCase()}: ${limpio(e.p.tipnomcalle)} ${limpio(e.p.numportal)}`.trim();
  } }),
  vlc("quioscos_vlc", "València: ciudad", "Quioscos de prensa, flores y ONCE", "#a21caf", 15, ["UrbanismoEInfraestructuras/219", "UrbanismoEInfraestructuras/220", "SociedadBienestar/3"], { icono: "quioscos", tamano: 0.8 }),
  vlc("vpp", "València: ciudad", "Vivienda de protección pública", "#0f766e", 13, ["UrbanismoEInfraestructuras/227"], { ajuste: (e) => { e.nombre = `Vivienda protegida${e.p.numviviendas ? `: ${e.p.numviviendas} viviendas` : ""}${e.p.uso ? ` en ${limpio(e.p.uso).toLowerCase()}` : ""}`; } }),
  vlc("equipamientos", "València: ciudad", "Equipamientos municipales", "#475569", 15, ["SociedadBienestar/1"], { icono: "ayuntamientos", tamano: 0.8, ajuste: (e) => { e.nombre = limpio(e.p.equipamien) || e.nombre; } }),
];

/* Cada capa: nombre, color, zoom desde el que se carga y de dónde salen los datos.
   - tipo "osm": `ql` son las búsquedas en OpenStreetMap y `es` decide si un elemento es de la capa.
   - tipo "api": `pedir(caja)` devuelve los elementos de ese trozo de mapa.
   - tipo "fija": se lee entera de datos/capa-<id>.geojson (la descarga «osintmaps capas»). */
const CAPAS = [
  // --- Vigilancia ---
  { id: "camaras", oculta: true, nombre: "Cámaras (OpenStreetMap)", color: "#d90429", zoom: 13, tipo: "osm", ql: ['nwr["man_made"="surveillance"]'],
    es: (t) => t.man_made === "surveillance", activa: () => $("capa-camaras").checked },
  { id: "dgt", grupo: "Vigilancia", nombre: "Cámaras de tráfico (DGT)", color: "#9d0208", zoom: 0, tipo: "fija",
    filas: (e) => [["Carretera", e.p.carretera], ["Punto kilométrico", e.p.pk], ["Provincia", e.p.provincia], ["Sentido", e.p.destino]], vivo: true },
  { id: "camvlc", grupo: "Vigilancia", nombre: "Cámaras de tráfico (València)", color: "#ff5a5f", zoom: 12, tipo: "api", pedir: arcgis([`${VALENCIA}/Trafico/MapServer/190`]) },
  { id: "policia", grupo: "Vigilancia", nombre: "Policía y seguridad", color: "#1d4ed8", zoom: 12, tipo: "osm",
    ql: ['nwr["amenity"="police"]', 'nwr["office"="security"]'], es: (t) => t.amenity === "police" || t.office === "security", titulo: () => "Policía" },
  { id: "radares", grupo: "Vigilancia", nombre: "Radares de velocidad", color: "#be123c", zoom: 11, tipo: "osm",
    ql: ['node["highway"="speed_camera"]'], es: (t) => t.highway === "speed_camera", titulo: () => "Radar de velocidad" },
  ...CAPAS_VIGILANCIA_MAS,
  // --- Abandono y patrimonio ---
  { id: "listaroja", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Lista Roja del Patrimonio", color: "#b3001b", zoom: 0, tipo: "fija",
    color_de: (p) => ({ verde: "#2f9e44", negra: "#111111" }[p.lista] || "#b3001b"),
    filas: (e) => [["Lista", { roja: "Roja: en riesgo de perderse", verde: "Verde: estaba en la Roja y se ha recuperado", negra: "Negra: se ha perdido" }[e.p.lista]], ["Resumen", e.p.resumen]] },
  { id: "subastas", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Inmuebles en subasta (BOE)", color: "#7b2ff7", zoom: 0, tipo: "fija",
    filas: (e) => [["Dirección", e.p.direccion], ["Localidad", e.p.localidad], ["Termina", e.p.fin], ["Valor de subasta", e.p.valor_subasta], ["Tasación", e.p.tasacion],
      ["Puja mínima", e.p.puja_minima], ["Depósito", e.p.deposito], ["Situación posesoria", e.p.situacion_posesoria], ["Visitable", e.p.visitable],
      ["Vivienda habitual", e.p.vivienda_habitual], ["Referencia catastral", e.p.refcat], ["Descripción", e.p.descripcion], ["Cargas", e.p.cargas],
      ["Situado por", { parcela: "la parcela catastral (exacto)", portal: "el portal (bastante exacto)", calle: "la calle (aproximado)" }[e.p.situado_por]], ["Subasta", e.p.subasta]] },
  /* Sale de experimentos/vision/cambios.py, no de «osintmaps capas»: si el fichero no está, la capa ni se enseña. */
  { id: "posibles", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Posibles abandonos (fotos de 2017 a 2025)", uno: "Posible abandono", color: "#ff7a00", zoom: 0, tipo: "fija", opcional: true,
    color_de: (p) => ({ derribado: "#8d99ae", vegetacion: "#2f9e44" }[p.clase] || "#ff7a00"),
    filas: (e) => [["Qué parece", e.p.parece], ["Por qué sale", e.p.motivos], ["Tejado a la vista, año a año", e.p.tejado], ["Vegetación dentro, año a año", e.p.serie], ["Dirección", e.p.direccion], ["Referencia catastral", e.p.refcat], ["Uso", e.p.uso],
      ["Construido en", e.p.anio], ["Planta", e.p.superficie ? `${miles(e.p.superficie)} m²` : null], ["Catastro lo da por", "en uso"],
      ["Cuánto fiarse", "Es una sospecha sacada de comparar fotos aéreas y la maqueta 3D, sin comprobar sobre el terreno. Puede ser una obra, un derribo o un contorno de Catastro mal puesto. Mira la foto por años antes de darla por buena."]] },
  { id: "abandonado", pesada: true, forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Abandonado o en ruinas (OSM, al momento)", color: "#c026d3", zoom: 13, tipo: "osm",
    ql: ['nwr["abandoned"="yes"]', 'nwr["disused"="yes"]', 'nwr["ruins"="yes"]', 'nwr["building"="ruins"]', 'nwr["historic"="ruins"]', 'nwr[~"^abandoned:"~"."]'],
    es: (t) => t.abandoned === "yes" || t.disused === "yes" || t.ruins === "yes" || t.building === "ruins" || t.historic === "ruins" || Object.keys(t).some((k) => k.startsWith("abandoned:")),
    titulo: (t) => tituloOSM(t, "historic", "building", "man_made", "amenity") || "Abandonado" },
  { id: "descampados", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Descampados y obras (OSM)", color: "#b45309", zoom: 14, tipo: "osm",
    ql: ['nwr["landuse"~"^(brownfield|construction|greenfield)$"]', 'nwr["building"="construction"]'],
    es: (t) => /^(brownfield|construction|greenfield)$/.test(t.landuse || "") || t.building === "construction",
    titulo: (t) => tituloOSM(t, "landuse") || "Edificio en obras" },
  { id: "solares", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Solares y edificios a rehabilitar (València)", color: "#a16207", zoom: 13, tipo: "api",
    pedir: arcgis([`${VALENCIA}/UrbanismoEInfraestructuras/MapServer/286`, `${VALENCIA}/UrbanismoEInfraestructuras/MapServer/294`]) },
  { id: "bic", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Patrimonio protegido BIC y BRL (València)", color: "#6d28d9", zoom: 13, tipo: "api",
    pedir: arcgis([`${VALENCIA}/UrbanismoEInfraestructuras/MapServer/277`, `${VALENCIA}/UrbanismoEInfraestructuras/MapServer/278`]) },
  { id: "refugios", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Refugios antiaéreos y patrimonio industrial (València)", color: "#5b4636", zoom: 12, tipo: "api",
    pedir: arcgis([`${VALENCIA}/Turismo/MapServer/229`, `${VALENCIA}/Turismo/MapServer/218`]) },
  { id: "militar", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Militar y búnkeres", color: "#4d5d2a", zoom: 12, tipo: "osm",
    ql: ['nwr["military"]', 'nwr["building"="bunker"]', 'nwr["historic"~"^(fort|bunker|battlefield)$"]'],
    es: (t) => !!t.military || t.building === "bunker" || /^(fort|bunker|battlefield)$/.test(t.historic || ""), titulo: (t) => tituloOSM(t, "military", "historic", "building") },
  { id: "historico", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Lugares históricos (OSM)", color: "#a97142", zoom: 14, tipo: "osm",
    ql: ['nwr["historic"]'], es: (t) => !!t.historic, titulo: (t) => tituloOSM(t, "historic") },
  // --- Infraestructura ---
  { id: "tren", grupo: "Infraestructura", nombre: "Ferrocarril: vías, cocheras y estaciones", color: "#111827", zoom: 13, tipo: "osm", lineas: true,
    ql: ['way["railway"~"^(rail|disused|abandoned|razed|siding|yard|tram|light_rail|subway|narrow_gauge)$"]', 'nwr["railway"~"^(station|halt|depot|roundhouse|turntable|signal_box)$"]', 'nwr["landuse"="railway"]'],
    es: (t) => !!t.railway || t.landuse === "railway", titulo: (t) => tituloOSM(t, "railway") || "Terreno ferroviario",
    color_de: (t) => (/^(disused|abandoned|razed)$/.test(t.railway || "") ? "#e5007d" : null), color_linea: "#f8fafc" },
  { id: "tuneles", grupo: "Infraestructura", nombre: "Túneles y puentes", color: "#0e7490", zoom: 15, tipo: "osm", lineas: true,
    ql: ['way["tunnel"~"^(yes|flooded|passage|building_passage)$"]', 'way["bridge"~"^(yes|viaduct|aqueduct|cantilever|movable|trestle)$"]', 'way["man_made"="bridge"]'],
    es: (t) => (!!t.tunnel && t.tunnel !== "no") || (!!t.bridge && t.bridge !== "no") || t.man_made === "bridge",
    titulo: (t) => (t.tunnel && t.tunnel !== "no" ? "Túnel" : "Puente") + (t.railway ? " ferroviario" : t.highway ? " de carretera" : ""),
    color_de: (t) => (t.tunnel && t.tunnel !== "no" ? "#0e7490" : "#7dd3fc") },
  { id: "muros", grupo: "Infraestructura", nombre: "Muros y pantallas acústicas", color: "#94a3b8", zoom: 16, tipo: "osm", lineas: true,
    ql: ['way["barrier"~"^(wall|retaining_wall|city_wall)$"]', 'way["wall"="noise_barrier"]', 'way["barrier"="noise_barrier"]'],
    es: (t) => /^(wall|retaining_wall|city_wall|noise_barrier)$/.test(t.barrier || "") || t.wall === "noise_barrier", titulo: (t) => tituloOSM(t, "wall", "barrier"), color_linea: "#cbd5e1", trazo: "7 6" },
  { id: "energia", grupo: "Infraestructura", nombre: "Energía: subestaciones, centrales y líneas", color: "#1e3a8a", zoom: 13, tipo: "osm", lineas: true,
    ql: ['nwr["power"~"^(substation|plant|generator|transformer)$"]', 'way["power"~"^(line|minor_line)$"]'],
    es: (t) => /^(substation|plant|generator|transformer|line|minor_line)$/.test(t.power || ""), titulo: (t) => tituloOSM(t, "power"), color_linea: "#fbbf24" },
  { id: "antenas", grupo: "Infraestructura", nombre: "Antenas, mástiles y torres", color: "#0369a1", zoom: 13, tipo: "osm",
    ql: ['nwr["man_made"~"^(mast|tower|communications_tower|antenna)$"]', 'nwr["telecom"]'],
    es: (t) => /^(mast|tower|communications_tower|antenna)$/.test(t.man_made || "") || !!t.telecom, titulo: (t) => tituloOSM(t, "tower:type", "man_made", "telecom") },
  { id: "industria", grupo: "Infraestructura", nombre: "Industria: fábricas, chimeneas, silos, depósitos", color: "#475569", zoom: 14, tipo: "osm",
    ql: ['nwr["man_made"~"^(works|chimney|silo|storage_tank|water_tower|gasometer|kiln|crane|cooling_tower)$"]', 'nwr["landuse"="industrial"]["name"]', 'nwr["building"~"^(industrial|warehouse|hangar)$"]["name"]'],
    es: (t) => /^(works|chimney|silo|storage_tank|water_tower|gasometer|kiln|crane|cooling_tower)$/.test(t.man_made || "") || ((t.landuse === "industrial" || /^(industrial|warehouse|hangar)$/.test(t.building || "")) && !!t.name),
    titulo: (t) => tituloOSM(t, "man_made", "building", "landuse") },
  { id: "canteras", grupo: "Infraestructura", nombre: "Canteras, minas y cuevas", color: "#78350f", zoom: 12, tipo: "osm",
    ql: ['nwr["landuse"="quarry"]', 'nwr["man_made"~"^(adit|mineshaft)$"]', 'nwr["historic"="mine"]', 'nwr["natural"="cave_entrance"]'],
    es: (t) => t.landuse === "quarry" || /^(adit|mineshaft)$/.test(t.man_made || "") || t.historic === "mine" || t.natural === "cave_entrance",
    titulo: (t) => tituloOSM(t, "man_made", "historic", "natural", "landuse") },
  { id: "agua", grupo: "Infraestructura", nombre: "Agua: depósitos, presas y depuradoras", color: "#0284c7", zoom: 13, tipo: "osm",
    ql: ['nwr["man_made"~"^(water_tower|reservoir_covered|water_works|wastewater_plant|pumping_station|water_tank)$"]', 'nwr["waterway"~"^(dam|weir)$"]'],
    es: (t) => /^(water_tower|reservoir_covered|water_works|wastewater_plant|pumping_station|water_tank)$/.test(t.man_made || "") || /^(dam|weir)$/.test(t.waterway || ""),
    titulo: (t) => tituloOSM(t, "man_made", "waterway") },
  { id: "farolas", tamano: 0.62, grupo: "Infraestructura", nombre: "Farolas (qué está iluminado)", color: "#facc15", zoom: 17, tipo: "osm",
    ql: ['node["highway"="street_lamp"]'], es: (t) => t.highway === "street_lamp", titulo: () => "Farola" },
  ...CAPAS_INFRA_MAS,
  // --- A pie de calle ---
  { id: "arte", grupo: "A pie de calle", nombre: "Arte urbano y murales", color: "#ec4899", zoom: 13, tipo: "osm",
    ql: ['nwr["tourism"="artwork"]["artwork_type"~"^(graffiti|mural|street_art|streetart|painting)$"]'],
    es: (t) => t.tourism === "artwork" && /^(graffiti|mural|street_art|streetart|painting)$/.test(t.artwork_type || ""), titulo: (t) => tituloOSM(t, "artwork_type") },
  { id: "miradores", grupo: "A pie de calle", nombre: "Miradores", color: "#15803d", zoom: 12, tipo: "osm",
    ql: ['nwr["tourism"="viewpoint"]'], es: (t) => t.tourism === "viewpoint", titulo: () => "Mirador" },
  ...CAPAS_CALLE_MAS,
  ...CAPAS_DIARIO,
  ...CAPAS_VALENCIA,
  // --- Fotos y artículos ---
  { id: "wikipedia", grupo: "Fotos y artículos", nombre: "Artículos de Wikipedia", color: "#f5f5f5", zoom: 13, tipo: "api", pedir: pedirWikipedia, vida: 7 },
  { id: "commons", tamano: 0.8, grupo: "Fotos y artículos", nombre: "Fotos de Wikimedia Commons", color: "#0891b2", zoom: 15, tipo: "api", pedir: pedirCommons, vida: 7 },
  { id: "panoramax", tamano: 0.7, grupo: "Fotos y artículos", nombre: "Fotos a pie de calle (Panoramax)", color: "#0d9488", zoom: 16, tipo: "api", pedir: pedirPanoramax },
  // --- Catastro ---
  { id: "edificios", grupo: "Catastro", nombre: "Edificios: estado, año y uso", color: "#60a5fa", zoom: 18, tipo: "api", pedir: pedirEdificios, paso: 0.002, porTesela: true, vida: 60 },
  // --- En vivo ---
  { id: "aviones", grupo: "En vivo", nombre: "Aviones en vuelo", color: "#facc15", zoom: 7, tipo: "vivo", pedir: pedirAviones, cada: 10000 },
  { id: "trenes", grupo: "En vivo", nombre: "Trenes de Cercanías (Renfe)", color: "#fde047", zoom: 8, tipo: "vivo", pedir: pedirTrenes, cada: 20000 },
  { id: "terremotos", grupo: "En vivo", nombre: "Terremotos del último mes", color: "#dc2626", zoom: 3, tipo: "vivo", alMover: true, pedir: pedirTerremotos, cada: 600000, buscar: "terremoto terremotos sismo" },
  { id: "aire", grupo: "En vivo", nombre: "Aire: sensores de partículas de vecinos", color: "#0891b2", zoom: 10, tipo: "vivo", alMover: true, pedir: pedirSensoresAire, cada: 300000 },
];
const CAPA = Object.fromEntries(CAPAS.map((c) => [c.id, c]));
/* Nombre corto de cada capa, para la tira de capas encendidas y los avisos. */
const CORTO = { camaras: "Cámaras", dgt: "DGT", camvlc: "Tráfico València", policia: "Policía", radares: "Radares", listaroja: "Lista Roja", subastas: "Subastas", posibles: "Posibles",
  abandonado: "Abandonado", descampados: "Descampados", solares: "Solares", bic: "BIC y BRL", refugios: "Refugios", militar: "Militar", historico: "Histórico",
  tren: "Ferrocarril", tuneles: "Túneles y puentes", muros: "Muros", energia: "Energía", antenas: "Antenas", industria: "Industria", canteras: "Canteras",
  agua: "Agua", farolas: "Farolas", arte: "Arte urbano", miradores: "Miradores", wikipedia: "Wikipedia", commons: "Commons", panoramax: "Panoramax",
  edificios: "Edificios", aviones: "Aviones", trenes: "Trenes" };
const corto = (capa) => CORTO[capa.id] || (CORTO[capa.id] = capa.nombre.split(/[:,(]| y | con /)[0].trim());
const enumerar = (nombres, tope = 3) => (nombres.length <= tope ? nombres.join(", ") : `${nombres.slice(0, tope).join(", ")} y ${nombres.length - tope} más`);
const CAPA_PUNTO = { id: "punto", nombre: "Punto del mapa", color: "#17242e" };
/* El símbolo de un elemento, como SVG: el mismo que lleva en el mapa. */
const simboloDe = (capa, color, lado = 22) => simboloSVG(capa.icono || capa.id, color || capa.color, capa.forma, lado);
const pasoDe = (z) => (z >= 17 ? 0.005 : z >= 16 ? 0.01 : z >= 15 ? 0.02 : z >= 14 ? 0.04 : z >= 13 ? 0.08 : 0.16);

/* Estado de cada capa: qué trozos del mapa ya se han pedido y qué elementos tiene. */
const estado = {};
for (const c of CAPAS) estado[c.id] = { activa: false, teselas: new Set(), elementos: new Map(), dibujos: new Map(), grupo: L.layerGroup(), cargando: 0, error: false, sinDatos: false };
const capasActivas = new Set(leerLocal("osintmaps.capas-datos.v1", []) || []);

/* --- De dónde sale cada capa "api" --- */
function arcgis(servicios, ajuste) {
  return (caja) => Promise.all(servicios.map((url) =>
    pedirJ(`${url}/query?where=1%3D1&geometry=${caja.o},${caja.s},${caja.e},${caja.n}&geometryType=esriGeometryEnvelope&inSR=4326` +
           "&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2000&f=geojson")
      .then((g) => {
        // Este servidor contesta «200 OK» también cuando falla, con el error dentro: si se diera
        // por bueno, ese trozo de mapa quedaría como cargado y vacío para siempre.
        if (g.error || !Array.isArray(g.features)) throw new Error("arcgis");
        const elementos = g.features.map((f) => elementoGeoJSON(f, url.split("/").slice(-3).join("-"))).filter(Boolean);
        if (ajuste) for (const e of elementos) ajuste(e);
        return elementos;
      }))).then((listas) => listas.flat());
}
/* Las áreas se guardan como lista de polígonos, y cada polígono como lista de anillos:
   el primero es el contorno y los demás, huecos (un patio, un claro). */
function centroDe(anillos) {
  const fuera = anillos.map((poligono) => poligono[0]).flat();
  return [fuera.reduce((s, q) => s + q[0], 0) / fuera.length, fuera.reduce((s, q) => s + q[1], 0) / fuera.length];
}
const CAMPOS_NOMBRE = ["nombre", "nom", "denominacion", "denominaci", "descripcio", "descripcion", "titulo", "name", "direccion", "adreca", "emplazamiento", "situacion", "texto"];
const CAMPOS_FUERA = /^(objectid|fid|shape.*|x|y|gid|globalid|st_.*|angulo|anggra|created_.*|last_edited_.*|fiwareid|update_jcd|[xy]coord|coor[xy]|linkid|cod(via|distbar|distrit|barrio|distrito|municipal)|id(clase|subclase)|gis\..*|simbolo)$/i;
/* Las fechas llegan como milisegundos desde 1970: se reconocen por el nombre del campo y por el tamaño del número. */
const esFechaCruda = (k, v) => /fecha|date|f_|ultima|carg|update|inicio|fin$/i.test(k) && /^-?\d{11,13}$/.test(String(v));
const valorDeCampo = (k, v) => (esFechaCruda(k, v) ? new Date(+v).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: /00:00:00/.test(new Date(+v).toTimeString()) ? undefined : "short" }) : /^https:\/\//.test(v) ? v : limpio(v).slice(0, 500));
const CAMPO_BONITO = { idcamara: "Cámara n.º", tipocamara: "Tipo", descripcio: "Descripción", adreca: "Dirección", direccion: "Dirección", denominaci: "Nombre",
  nom: "Nombre", nombre: "Nombre", tipus: "Tipo", tipo: "Tipo", estat: "Estado", estado: "Estado", districte: "Distrito", distrito: "Distrito", barri: "Barrio", barrio: "Barrio",
  superficie: "Superficie", refcat: "Referencia catastral", any: "Año", data: "Fecha", fecha: "Fecha", observacio: "Observaciones", observaciones: "Observaciones",
  calle: "Calle", numplazas: "Plazas", plazastota: "Plazas en total", plazaslibr: "Plazas libres", ocupacion: "Ocupación", lineas: "Líneas", linea: "Líneas", available: "Bicis libres",
  free: "Huecos libres", total: "Anclajes", address: "Dirección", updated_at: "Actualizado", open: "Abierta", ticket: "Admite pago con tarjeta", number: "Estación n.º", numpol: "Número",
  numportal: "Número", telefono: "Teléfono", horarios: "Horario", sitioweb: "Web", correoelectronico: "Correo", emplazamiento: "Emplazamiento", modelo: "Modelo",
  fecha_inicio: "Empieza", fecha_fin: "Termina", fecha_inicio_periodo: "Empieza", fecha_fin_periodo: "Termina", fecha_carg: "Medido", fecha_actualizacion: "Actualizado", ultima_mod: "Actualizado",
  desc_calle: "Calle", tipo_afectacion: "Afecta a", tipo_incidencia: "Motivo", desc_incidencia: "Descripción", no2: "NO₂ (µg/m³)", so2: "SO₂ (µg/m³)", o3: "Ozono (µg/m³)", co: "CO (mg/m³)",
  pm10: "PM10 (µg/m³)", pm25: "PM2,5 (µg/m³)", calidad_am: "Calidad del aire", tipozona: "Zona", tipoemisio: "Lo que mide", parametros: "Parámetros", temperatur: "Temperatura (°C)",
  humedad_re: "Humedad (%)", viento_vel: "Viento (m/s)", viento_dir: "Viento (dirección, °)", presion_ba: "Presión (hPa)", precipitac: "Lluvia (mm)", ih: "Vehículos por hora",
  nom_botanico: "Nombre botánico", nom_comu_c: "Nombre común", nom_comu_v: "Nom comú", altura: "Altura (m)", perimetro: "Perímetro (m)", estado_gral: "Estado", lugar: "Lugar",
  numviviendas: "Viviendas", regimencalifi: "Régimen", tipopromo: "Promoción", uso: "Uso", resultados: "Resultados", proyecto: "Proyecto", cronologia: "Cronología", director: "Dirección",
  seccion: "Sección", fallera: "Fallera mayor", presidente: "Presidente", artista: "Artista", lema: "Lema", anyo_fundacion: "Fundada en", codigo: "Código", jardin: "Jardín",
  equipamien: "Equipamiento", clase: "Clase", numplaca: "Placa", optica: "Óptica", descrip: "Descripción", localizaci: "Localización", mediciones: "Mediciones", proximas_llegadas: "Próximas llegadas" };
function elementoGeoJSON(f, prefijo) {
  const g = f.geometry, p = f.properties || {};
  if (!g) return null;
  const e = { id: `${prefijo}/${f.id != null ? f.id : p.objectid || p.id || Math.random().toString(36).slice(2)}`, p };
  if (g.type === "Point") [e.lon, e.lat] = g.coordinates;
  else if (g.type === "LineString" || g.type === "MultiLineString") {
    e.linea = (g.type === "LineString" ? g.coordinates : g.coordinates.flat()).map(([x, y]) => [y, x]);
    [e.lat, e.lon] = e.linea[Math.floor(e.linea.length / 2)];
  } else if (g.type === "Polygon" || g.type === "MultiPolygon") {
    e.anillos = (g.type === "Polygon" ? [g.coordinates] : g.coordinates).map((pol) => pol.map((anillo) => anillo.map(([x, y]) => [y, x]))).filter((pol) => pol.length && pol[0].length >= 3);
    if (!e.anillos.length) return null;
    [e.lat, e.lon] = centroDe(e.anillos);
  } else return null;
  if (!Number.isFinite(e.lat) || !Number.isFinite(e.lon)) return null;
  const clave = Object.keys(p).find((k) => CAMPOS_NOMBRE.includes(k.toLowerCase()) && limpio(p[k]));
  e.nombre = clave ? limpio(p[clave]).slice(0, 120) : "";
  e.datos = Object.entries(p).filter(([k, v]) => !CAMPOS_FUERA.test(k) && limpio(v) && typeof v !== "object" && k !== "proximes_llegadas")
    .map(([k, v]) => [CAMPO_BONITO[k.toLowerCase()] || k.replace(/_/g, " ").replace(/^./, (x) => x.toUpperCase()), valorDeCampo(k, typeof v === "string" ? v.replace(/^http:\/\/(www\.emtvalencia\.es|mapas\.valencia\.es)/, "https://$1") : v)]);
  // Las cámaras municipales traen su página con la imagen en directo.
  const web = Object.values(p).find((v) => typeof v === "string" && /^https:\/\/camaras\.valencia\.es\//.test(v));
  if (web) e.marco = web;
  return e;
}

/* Wikipedia y Commons entregan los datos de una lista de páginas por tandas:
   hay que seguir pidiendo mientras la respuesta diga «continue» y juntar los trozos. */
async function consultaWiki(sitio, parametros, tandas = 5) {
  const paginas = {};
  let sigue = {};
  for (let k = 0; k < tandas; k++) {
    const j = await pedirJ(`https://${sitio}/w/api.php?${new URLSearchParams(Object.assign({ action: "query", format: "json", origin: "*" }, parametros, sigue))}`);
    for (const [id, p] of Object.entries((j.query || {}).pages || {})) paginas[id] = Object.assign(paginas[id] || {}, p);
    if (!j.continue) break;
    sigue = j.continue;
  }
  return Object.values(paginas);
}
function pedirWikipedia(caja) {
  return consultaWiki("es.wikipedia.org", { generator: "geosearch", ggsbbox: `${caja.n}|${caja.o}|${caja.s}|${caja.e}`, ggslimit: "200",
    prop: "coordinates|pageimages|description", piprop: "thumbnail", pithumbsize: "960", colimit: "max", pilimit: "max" }).then((paginas) => paginas.filter((p) => p.coordinates).map((p) => ({
    id: `wikipedia/${p.pageid}`, lat: p.coordinates[0].lat, lon: p.coordinates[0].lon, nombre: p.title, imagen: (p.thumbnail || {}).source,
    url: `https://es.wikipedia.org/?curid=${p.pageid}`, pagina: p.pageid, datos: p.description ? [["Qué es", p.description]] : [] })));
}
function fotoCommons(p) {
  const i = (p.imageinfo || [])[0];
  if (!i || !/^image\//.test(i.mime || "image/")) return null;
  const m = i.extmetadata || {}, c = (p.coordinates || [])[0];
  // Al acercar en el visor se pide una versión mayor: el original, o la miniatura de 3840 px si el original es enorme.
  const grande = i.thumburl && i.width > 3840 ? i.thumburl.replace(/\/\d+px-/, "/3840px-") : i.url;
  return { id: `commons/${p.pageid}`, lat: c && c.lat, lon: c && c.lon, nombre: p.title.replace(/^File:/, "").replace(/\.[a-z]+$/i, ""), imagen: i.thumburl || i.url, grande,
    original: i.url, url: i.descriptionurl, autor: limpio((m.Artist || {}).value).slice(0, 80), licencia: limpio((m.LicenseShortName || {}).value),
    fecha: limpio((m.DateTimeOriginal || {}).value).slice(0, 10) };
}
// Wikimedia solo sirve las miniaturas en unos anchos fijos (250, 500, 960, 1280, 1920...).
const PEDIDO_COMMONS = { generator: "geosearch", ggsnamespace: "6", prop: "imageinfo|coordinates", iiprop: "url|extmetadata|mime|size", colimit: "max",
  iiurlwidth: "1280", iiextmetadatafilter: "Artist|LicenseShortName|DateTimeOriginal" };
function pedirCommons(caja) {
  return consultaWiki("commons.wikimedia.org", Object.assign({ ggsbbox: `${caja.n}|${caja.o}|${caja.s}|${caja.e}`, ggslimit: "200" }, PEDIDO_COMMONS))
    .then((paginas) => paginas.map(fotoCommons).filter((f) => f && f.lat != null)
    .map((f) => Object.assign(f, { datos: [["Autor", f.autor], ["Fecha", f.fecha], ["Licencia", f.licencia]] })));
}
function fotoPanoramax(f) {
  const p = f.properties || {}, a = f.assets || {};
  if (!f.geometry || !a.sd) return null;
  const esfera = ((p["pers:interior_orientation"] || {}).field_of_view || 0) >= 360;
  return { id: `panoramax/${f.id}`, lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], nombre: `Foto a pie de calle del ${fechaCorta(p.datetime)}`,
    imagen: a.sd.href, original: (a.hd || a.sd).href, miniatura: (a.thumb || a.sd).href, fecha: (p.datetime || "").slice(0, 10), rumbo: p["view:azimuth"],
    url: `https://api.panoramax.xyz/#focus=pic&pic=${f.id}`, licencia: p.license || "",
    datos: [["Fecha", fechaCorta(p.datetime)], ["Mira hacia", p["view:azimuth"] != null ? `${Math.round(p["view:azimuth"])}°` : ""], ["Tipo", esfera ? "Panorámica de 360°" : "Foto normal"], ["Licencia", p.license]] };
}
function pedirPanoramax(caja) {
  return pedirJ(`https://api.panoramax.xyz/api/search?bbox=${caja.o},${caja.s},${caja.e},${caja.n}&limit=500`)
    .then((j) => (j.features || []).map(fotoPanoramax).filter(Boolean));
}

/* --- Transporte público: paradas y próximas salidas (Transitous, horarios abiertos de medio mundo) --- */
const TRANSITOUS = "https://api.transitous.org/api/v1";
const MODO_TRANSPORTE = { BUS: "autobús", COACH: "autocar", TRAM: "tranvía", SUBWAY: "metro", METRO: "metro", RAIL: "tren", REGIONAL_RAIL: "tren regional", REGIONAL_FAST_RAIL: "tren regional",
  LONG_DISTANCE: "larga distancia", HIGHSPEED_RAIL: "alta velocidad", NIGHT_RAIL: "tren nocturno", SUBURBAN: "cercanías", FERRY: "ferri", AIRPLANE: "avión", FUNICULAR: "funicular",
  CABLE_CAR: "teleférico", AERIAL_LIFT: "teleférico", WALK: "a pie", BIKE: "bici", CAR: "coche", RENTAL: "alquiler", ODM: "a demanda", OTHER: "otro" };
const modoTransporte = (m) => MODO_TRANSPORTE[m] || String(m || "").toLowerCase().replace(/_/g, " ");
const esSobreRailes = (m) => /RAIL|SUBWAY|METRO|TRAM|SUBURBAN|LONG_DISTANCE|FUNICULAR/.test(m || "");
function pedirParadas(caja) {
  // (el servicio pide la esquina de abajo a la derecha y la de arriba a la izquierda)
  return pedirJ(`${TRANSITOUS}/map/stops?min=${caja.s},${caja.e}&max=${caja.n},${caja.o}`, null, 25000).then((lista) => (Array.isArray(lista) ? lista : []).filter((p) => p.stopId && Number.isFinite(p.lat) && Number.isFinite(p.lon)).map((p) => {
    const modos = p.modes || [];
    return { id: `parada/${p.stopId}`, parada: p.stopId, lat: p.lat, lon: p.lon, nombre: p.name || "Parada", color: modos.some(esSobreRailes) ? "#b91c1c" : null,
      datos: [["Medio", [...new Set(modos.map(modoTransporte))].join(", ")], ["Código de parada", p.stopCode], ["Situación", p.description]] };
  }));
}
/* La hora de un paso, como la diría alguien en la parada: «ya», «4 min» o «18:42». */
function horaDePaso(iso, ahora = Date.now()) {
  const t = new Date(iso), min = Math.round((t - ahora) / 60000);
  if (Number.isNaN(+t)) return "";
  return min <= 0 && min > -2 ? "ya" : min > 0 && min < 60 ? `${min} min` : t.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}
/* El distintivo de una línea, con sus colores oficiales si los trae. */
function chapaDeLinea(nombre, color, texto, modo) {
  const fondo = /^[0-9a-f]{6}$/i.test(color || "") ? `#${color}` : esSobreRailes(modo) ? "#b91c1c" : "#1d4ed8";
  const chapa = el("span", { className: "linea", textContent: nombre || modoTransporte(modo) });
  chapa.style.background = fondo;
  chapa.style.color = /^[0-9a-f]{6}$/i.test(texto || "") && texto.toLowerCase() !== (color || "").toLowerCase() ? `#${texto}` : colorSobre(fondo);
  return chapa;
}
function salidasDeParada(e, destino) {
  destino.replaceChildren(el("p", { className: "pendiente", textContent: "Consultando los próximos pasos…" }));
  pedirJ(`${TRANSITOUS}/stoptimes?stopId=${encodeURIComponent(e.parada)}&n=14`, null, 20000).then((j) => {
    if (elementoAbierto !== e) return;
    const pasos = (j.stopTimes || []).filter((s) => (s.place || {}).departure || (s.place || {}).arrival).slice(0, 14);
    if (!pasos.length) { destino.replaceChildren(el("p", { className: "pendiente", textContent: "No hay pasos previstos en las próximas horas." })); return; }
    const lista = el("ul", { className: "salidas" });
    for (const s of pasos) {
      const hora = s.place.departure || s.place.arrival;
      lista.append(el("li", {}, chapaDeLinea(s.routeShortName, s.routeColor, s.routeTextColor, s.mode), el("span", { className: "destino", textContent: s.headsign || s.tripTo && s.tripTo.name || "" }),
        el("b", { textContent: horaDePaso(hora), title: new Date(hora).toLocaleString("es-ES") }), el("small", { textContent: s.realTime ? "en directo" : "según horario" })));
    }
    const otra = el("button", { type: "button", textContent: "Actualizar" });
    otra.addEventListener("click", () => salidasDeParada(e, destino));
    destino.replaceChildren(lista, el("div", { className: "enlaces" }, otra));
  }).catch(() => { if (elementoAbierto === e) destino.replaceChildren(el("p", { className: "pendiente", textContent: "El servicio de horarios no ha respondido." })); });
}

/* --- Gasolineras: los precios que las estaciones comunican cada día al Ministerio ---
   El servicio los da por provincias: primero se averigua en cuál cae el trozo de mapa. */
const CARBURANTES = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/FiltroProvincia/";
const provinciaDeTrozo = new Map(), gasolinerasDeProvincia = new Map();
function provinciaDe(lat, lon) {
  const clave = `${lat.toFixed(1)},${lon.toFixed(1)}`;
  if (!provinciaDeTrozo.has(clave)) {
    provinciaDeTrozo.set(clave, pedirJ(`https://www.cartociudad.es/geocoder/api/geocoder/reverseGeocode?lon=${lon}&lat=${lat}`, null, 15000)
      .then((j) => (j && j.provinceCode ? String(j.provinceCode).padStart(2, "0") : null), () => { provinciaDeTrozo.delete(clave); return "fallo"; }));
  }
  return provinciaDeTrozo.get(clave);
}
const decimal = (t) => { const n = parseFloat(String(t == null ? "" : t).replace(",", ".")); return Number.isFinite(n) ? n : null; };
const euros = (n) => (n ? `${n.toFixed(3).replace(".", ",")} €` : "");
function gasolinerasDe(provincia) {
  if (!gasolinerasDeProvincia.has(provincia)) {
    gasolinerasDeProvincia.set(provincia, pedirJ(CARBURANTES + provincia, null, 45000).then((j) => {
      const precio = (g, campo) => { const n = decimal(g[campo]); return n > 0 ? n : null; };
      const lista = (j.ListaEESSPrecio || []).map((g) => ({ g, lat: decimal(g.Latitud), lon: decimal(g["Longitud (WGS84)"]), g95: precio(g, "Precio Gasolina 95 E5"), diesel: precio(g, "Precio Gasoleo A") }))
        .filter((x) => x.lat != null && x.lon != null);
      // Por tercios de precio dentro de la provincia: verde lo barato, rojo lo caro.
      const cortes = (campo) => { const v = lista.map((x) => x[campo]).filter(Boolean).sort((a, b) => a - b); return v.length > 2 ? [v[Math.floor(v.length / 3)], v[Math.floor((2 * v.length) / 3)]] : null; };
      const c95 = cortes("g95"), cDiesel = cortes("diesel");
      return lista.map(({ g, lat, lon, g95, diesel }) => {
        const [valor, c] = g95 ? [g95, c95] : [diesel, cDiesel];
        return { id: `gasolinera/${g.IDEESS}`, lat, lon, color: !valor || !c ? "#6b7280" : valor <= c[0] ? "#15803d" : valor <= c[1] ? "#b45309" : "#b91c1c",
          nombre: `${limpio(g["Rótulo"]) || "Gasolinera"}${g95 ? ` · 95: ${euros(g95)}` : ""}${diesel ? ` · diésel: ${euros(diesel)}` : ""}`,
          datos: [["Gasolina 95", euros(g95)], ["Gasolina 98", euros(precio(g, "Precio Gasolina 98 E5"))], ["Gasóleo A", euros(diesel)], ["Gasóleo premium", euros(precio(g, "Precio Gasoleo Premium"))],
            ["GLP", euros(precio(g, "Precio Gases licuados del petróleo"))], ["Horario", limpio(g.Horario)], ["Dirección", [limpio(g["Dirección"]), limpio(g.Localidad)].filter(Boolean).join(", ")],
            ["Venta", { P: "al público", R: "restringida (cooperativa o flota)" }[g["Tipo Venta"]] || ""], ["Precios del", limpio(j.Fecha)],
            ["Comparado con la provincia", !valor || !c ? "" : valor <= c[0] ? "de las baratas" : valor <= c[1] ? "precio medio" : "de las caras"]] };
      });
    }).catch((err) => { gasolinerasDeProvincia.delete(provincia); throw err; }));
  }
  return gasolinerasDeProvincia.get(provincia);
}
function pedirGasolineras(caja) {
  const puntos = [[(caja.s + caja.n) / 2, (caja.o + caja.e) / 2], [caja.s, caja.o], [caja.n, caja.e]];
  return Promise.all(puntos.map(([la, lo]) => provinciaDe(la, lo))).then((codigos) => {
    if (codigos.every((c) => c === "fallo")) throw new Error("sin provincia");
    return Promise.all([...new Set(codigos.filter((c) => c && c !== "fallo"))].map(gasolinerasDe));
  }).then((listas) => listas.flat().filter((g) => g.lat >= caja.s && g.lat < caja.n && g.lon >= caja.o && g.lon < caja.e));
}

/* --- Terremotos del último mes (EMSC, que reúne los de los institutos de cada país) --- */
function pedirTerremotos() {
  const b = mapa.getBounds().pad(0.3), z = mapa.getZoom(), acota = (v, tope) => Math.max(-tope, Math.min(tope, v)).toFixed(2);
  const url = `https://www.seismicportal.eu/fdsnws/event/1/query?format=json&limit=400&start=${new Date(Date.now() - 30 * DIA).toISOString().slice(0, 19)}` +
    `&minmag=${z >= 8 ? 1 : z >= 6 ? 2 : z >= 4 ? 3.5 : 4.5}&minlat=${acota(b.getSouth(), 90)}&maxlat=${acota(b.getNorth(), 90)}&minlon=${acota(b.getWest(), 180)}&maxlon=${acota(b.getEast(), 180)}`;
  // (cuando no hay ninguno, el servicio contesta sin cuerpo)
  return pedirTexto(url, null, 25000).then((texto) => ((texto.trim() ? JSON.parse(texto) : {}).features || []).map((f) => {
    const p = f.properties || {}, m = +p.mag || 0;
    return { id: `terremoto/${p.unid || f.id}`, lat: +p.lat, lon: +p.lon, tamano: m >= 5 ? 1.5 : m >= 4 ? 1.25 : m >= 3 ? 1 : 0.75,
      color: m >= 5 ? "#7f1d1d" : m >= 4 ? "#dc2626" : m >= 3 ? "#ea580c" : m >= 2 ? "#d97706" : "#ca8a04",
      nombre: `Terremoto de magnitud ${m.toFixed(1).replace(".", ",")}: ${limpio(p.flynn_region).toLowerCase().replace(/(^|\s)\S/g, (x) => x.toUpperCase())}`,
      url: p.unid ? `https://www.seismicportal.eu/eventdetails.html?unid=${encodeURIComponent(p.unid)}` : null,
      datos: [["Magnitud", `${m.toFixed(1).replace(".", ",")} (${p.magtype || ""})`], ["Profundidad", p.depth != null ? `${Math.abs(+p.depth).toFixed(0)} km` : ""], ["Cuándo", p.time ? new Date(p.time).toLocaleString("es-ES") : ""],
        ["Zona", limpio(p.flynn_region)], ["Lo comunica", p.auth]] };
  }).filter((e) => Number.isFinite(e.lat) && Number.isFinite(e.lon)));
}

/* --- Aire: sensores de vecinos (sensor.community), que miden las partículas en la calle --- */
function pedirSensoresAire() {
  const c = mapa.getCenter(), km = Math.min(60, Math.max(2, mapa.distance(c, mapa.getBounds().getNorthEast()) / 1000));
  return pedirJ(`https://data.sensor.community/airrohr/v1/filter/area=${c.lat.toFixed(4)},${c.lng.toFixed(4)},${km.toFixed(1)}`, null, 25000).then((lista) => {
    const sitios = new Map();
    for (const x of Array.isArray(lista) ? lista : []) {
      const l = x.location || {}, lat = +l.latitude, lon = +l.longitude;
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || +l.indoor === 1) continue;
      const s = sitios.get(l.id) || { lat, lon, valores: {}, hora: x.timestamp };
      for (const v of x.sensordatavalues || []) if (Number.isFinite(+v.value)) s.valores[v.value_type] = +v.value;
      sitios.set(l.id, s);
    }
    const dato = (v, unidad, cifras = 0) => (v == null ? "" : `${v.toFixed(cifras).replace(".", ",")} ${unidad}`);
    return [...sitios].filter(([, s]) => s.valores.P2 != null || s.valores.P1 != null).map(([id, s]) => {
      const fina = s.valores.P2, gruesa = s.valores.P1, ref = fina != null ? fina : gruesa / 2;
      return { id: `aire/${id}`, lat: s.lat, lon: s.lon, tamano: 0.8, color: ref <= 10 ? "#16a34a" : ref <= 25 ? "#ca8a04" : ref <= 50 ? "#ea580c" : "#b91c1c",
        nombre: `Partículas finas (PM2,5): ${dato(fina, "µg/m³") || "sin dato"}`,
        datos: [["PM2,5 (partículas finas)", dato(fina, "µg/m³", 1)], ["PM10", dato(gruesa, "µg/m³", 1)], ["Temperatura", dato(s.valores.temperature, "°C", 1)], ["Humedad", dato(s.valores.humidity, "%")],
          ["Medido", s.hora ? `${s.hora} (hora universal)` : ""], ["Referencia", "la OMS recomienda no pasar de 15 µg/m³ de PM2,5 de media diaria"]] };
    });
  });
}

const ESTADO_EDIFICIO = { ruin: ["En ruina", "#e5007d"], declined: ["Deficiente", "#f08a00"], functional: ["En uso", "#60a5fa"] };
const USO_EDIFICIO = { "1_residential": "Residencial", "2_agriculture": "Agrario", "3_industrial": "Industrial", "4_1_office": "Oficinas", "4_2_retail": "Comercial", "4_3_publicServices": "Equipamiento o servicio público" };
function pedirEdificios(caja, sigue) {
  const url = `https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx?service=wfs&version=2&request=getfeature&Typenames=BU.BUILDING&SRSname=EPSG::4326&bbox=${caja.s},${caja.o},${caja.n},${caja.e}`;
  return new Promise((resolver, rechazar) => encolarCatastro(() => pedirTexto(url, null, 60000).then((xml) => {
    // Catastro contesta «200 OK» con un informe de error dentro. Donde no hay nada (el mar)
    // el informe dice «No records»: eso es un vacío de verdad; cualquier otro es un fallo.
    if (/ExceptionReport/.test(xml.slice(0, 600))) { if (/No records/i.test(xml)) return []; throw new Error("catastro"); }
    const doc = new DOMParser().parseFromString(xml, "text/xml"), salida = [];
    if (doc.getElementsByTagName("parsererror").length) throw new Error("xml");
    for (const nodo of doc.getElementsByTagNameNS("*", "Building")) {
      const texto = (nombre) => { const e = nodo.getElementsByTagNameNS("*", nombre)[0]; return e ? e.textContent.trim() : ""; };
      const refcat = texto("reference") || texto("localId");
      // Cada trozo del edificio trae su contorno y, si tiene patios, sus huecos. El servicio
      // repite a veces el mismo trozo: se queda uno solo.
      const anillos = [], vistos = new Set();
      for (const exterior of nodo.getElementsByTagNameNS("*", "exterior")) {
        const trozo = exterior.parentNode, poligono = [];
        for (const lista of trozo.getElementsByTagNameNS("*", "posList")) {
          const v = lista.textContent.trim().split(/\s+/).map(Number), anillo = [];
          for (let i = 0; i + 1 < v.length; i += 2) if (Number.isFinite(v[i]) && Number.isFinite(v[i + 1])) anillo.push([v[i], v[i + 1]]);
          if (anillo.length >= 3) poligono.push(anillo);
        }
        const huella = poligono.length ? poligono[0].slice(0, 4).join(";") : "";
        if (!poligono.length || vistos.has(huella)) continue;
        vistos.add(huella);
        anillos.push(poligono);
      }
      if (!refcat || !anillos.length) continue;
      const [latC, lonC] = centroDe(anillos), est = texto("conditionOfConstruction"), anio = (texto("beginning") || "").slice(0, 4), uso = USO_EDIFICIO[texto("currentUse")] || "";
      const sup = nodo.getElementsByTagNameNS("*", "OfficialArea")[0];
      const m2 = sup ? +(sup.getElementsByTagNameNS("*", "value")[0] || {}).textContent : 0;
      salida.push({ id: `edificio/${refcat}`, refcat, anillos, estado_edificio: est, superficie: m2 || 400, lat: latC, lon: lonC,
        nombre: `Edificio ${uso ? uso.toLowerCase() : ""}${anio && anio !== "0001" ? ` de ${anio}` : ""}`.replace(/\s+/g, " ").trim(),
        datos: [["Estado", (ESTADO_EDIFICIO[est] || [est])[0]], ["Año de construcción", anio === "0001" ? "" : anio], ["Uso", uso], ["Superficie construida", m2 ? `${miles(m2)} m²` : ""],
          ["Viviendas", texto("numberOfDwellings")], ["Inmuebles", texto("numberOfBuildingUnits")], ["Referencia catastral", refcat]] });
    }
    return salida;
  }).then(resolver, rechazar), { sigue, alDescartar: () => rechazar(new Error("descartada")) }));
}
/* Lo que es en directo y viene de servicios que no dejan que una página les pregunte: solo si
   detrás está el programa del ordenador, que pregunta por ella. */
const relevo = (ruta) => hayServidor.then((si) => (si ? pedirJ(ruta, null, 15000) : Promise.reject(new Error("solo con «osintmaps servir»"))));
function pedirAviones() {
  const c = mapa.getCenter(), b = mapa.getBounds();
  const millas = Math.min(120, Math.max(5, Math.round(mapa.distance(c, b.getNorthEast()) / 1852)));
  return relevo(`vivo/aviones?lat=${c.lat.toFixed(3)}&lon=${c.lng.toFixed(3)}&dist=${millas}`).then((j) => (j.ac || []).filter((a) => a.lat != null && a.lon != null).map((a) => ({
    id: `avion/${a.hex}`, lat: a.lat, lon: a.lon, nombre: (a.flight || "").trim() || a.r || a.hex, rumbo: a.track, url: `https://globe.adsb.lol/?icao=${a.hex}`,
    datos: [["Vuelo", (a.flight || "").trim()], ["Matrícula", a.r], ["Modelo", a.t], ["Altitud", typeof a.alt_baro === "number" ? `${miles(a.alt_baro * 0.3048)} m` : a.alt_baro === "ground" ? "en tierra" : ""],
      ["Velocidad", a.gs != null ? `${miles(a.gs * 1.852)} km/h` : ""], ["Rumbo", a.track != null ? `${Math.round(a.track)}°` : ""], ["Código transpondedor", a.squawk], ["Identificador", a.hex]] })));
}

/* Trenes de Cercanías: Renfe publica dónde va cada uno. Llegan los de toda España; se enseñan los de la vista. */
const ESTADO_TREN = { STOPPED_AT: "parado en", INCOMING_AT: "llegando a", IN_TRANSIT_TO: "en camino a" };
function pedirTrenes() {
  const vista = mapa.getBounds().pad(0.2);
  return relevo("vivo/trenes").then((j) => (j.entity || []).map((x) => x.vehicle || {}).filter((v) => v.position && vista.contains([v.position.latitude, v.position.longitude])).map((v) => {
    const etiqueta = ((v.vehicle || {}).label || "").trim(), linea = (/^(C\d+\w?)/.exec(etiqueta) || /-(C\d+\w?)-/.exec((v.vehicle || {}).id || "") || [])[1] || "";
    return { id: `tren/${(v.vehicle || {}).id || (v.trip || {}).tripId}`, lat: v.position.latitude, lon: v.position.longitude, nombre: etiqueta || `Tren ${(v.trip || {}).tripId || ""}`.trim(),
      datos: [["Línea", linea], ["Tren", etiqueta], ["Situación", ESTADO_TREN[v.currentStatus] ? `${ESTADO_TREN[v.currentStatus]} la parada ${v.stopId || ""}`.trim() : ""],
        ["Visto a las", v.timestamp ? new Date(v.timestamp * 1000).toLocaleTimeString("es-ES") : ""], ["Viaje", (v.trip || {}).tripId]] };
  }));
}

/* --- Elementos de OpenStreetMap --- */
function elementoOSM(e, capa) {
  const t = e.tags || {};
  const el0 = { id: `${e.type}/${e.id}`, etiquetas: t, url: `https://www.openstreetmap.org/${e.type}/${e.id}` };
  if (e.type === "node") { el0.lat = e.lat; el0.lon = e.lon; }
  else if (e.bounds) {
    el0.lat = (e.bounds.minlat + e.bounds.maxlat) / 2; el0.lon = (e.bounds.minlon + e.bounds.maxlon) / 2;
    const g = e.type === "way" ? e.geometry : null;
    if (g && g.length > 1) {
      const cerrada = g[0].lat === g[g.length - 1].lat && g[0].lon === g[g.length - 1].lon;
      if (cerrada && g.length > 3) el0.anillos = [[g.map((p) => [p.lat, p.lon])]];
      else if (capa.lineas) { el0.linea = g.map((p) => [p.lat, p.lon]); [el0.lat, el0.lon] = el0.linea[Math.floor(el0.linea.length / 2)]; }
    }
  } else if (e.center) { el0.lat = e.center.lat; el0.lon = e.center.lon; }      // (las búsquedas «cerca de aquí» piden solo el centro)
  else return null;
  if (el0.lat == null) return null;
  el0.nombre = t.name || t["name:es"] || t["name:ca"] || (capa.uno ? t.brand || t.operator || tipoDeEtiquetas(t) : "") || (capa.titulo ? capa.titulo(t) : "") || capa.nombre;
  if (capa.color_de) el0.color = capa.color_de(t);
  return el0;
}
function filasOSM(t) {
  const filas = [];
  for (const [k, nombre] of Object.entries(ETIQUETA_OSM)) if (t[k] && k !== "name" && k !== "opening_hours") filas.push([nombre, /^(website|contact:website|wikipedia|wikidata|phone|contact:phone|email|contact:email|ref|brand|operator|addr:.*)$/.test(k) ? t[k] : valorOSM(t[k], k)]);
  return filas;
}

/* --- Dibujo --- */
function dibujar(capa, e) {
  const color = e.color || capa.color;
  const ficha = () => simbolo([e.lat, e.lon], { icono: capa.icono || capa.id, fondo: color, forma: capa.forma, tamano: e.tamano || capa.tamano,
    giro: capa.id === "aviones" && e.rumbo != null ? e.rumbo - 45 : 0 });      // el dibujo del avión mira al nordeste
  let d;
  if (e.linea) {
    // Una línea lleva debajo otra más ancha y oscura, para que se vea igual sobre una foto clara que sobre una oscura.
    d = L.featureGroup([L.polyline(e.linea, { color: "#17242e", weight: 6.5, opacity: 0.6 }),
      L.polyline(e.linea, { color: e.color || capa.color_linea || capa.color, weight: 3.2, opacity: 1, dashArray: capa.trazo || null })]);
  }
  else if (e.anillos && capa.id === "edificios") d = L.polygon(e.anillos, { color: (ESTADO_EDIFICIO[e.estado_edificio] || [0, "#60a5fa"])[1], weight: 1.5, fillOpacity: e.estado_edificio === "functional" ? 0.12 : 0.45 });
  else if (e.anillos && mapa.getZoom() >= 15) {
    // De cerca, un área se ve con su contorno y con su símbolo en el centro.
    const contorno = L.polygon(e.anillos, { color, weight: 2, fillOpacity: 0.22 });
    d = L.featureGroup([contorno, ficha()]);
    d.contorno = contorno;
  } else d = ficha();
  // (midiendo, o eligiendo en el mapa un extremo de la ruta, el toque es para eso: sigue hasta el mapa)
  d.on("click", (ev) => { if (midiendo || (typeof ruta === "object" && ruta.eligiendo)) return; L.DomEvent.stopPropagation(ev); abrirElemento(e); });
  // El nombre viene de fuera (OpenStreetMap, ayuntamientos...): Leaflet trata una cadena como
  // HTML, así que se le da un nodo de texto, que no puede traer código dentro.
  if (e.nombre) d.bindTooltip(() => el("span", { textContent: e.nombre }), { direction: "top", offset: [0, -8] });
  return d;
}
/* Las áreas van al fondo para no tapar los puntos; su símbolo, no. */
function alFondo(d) { if (d.contorno) d.contorno.bringToBack(); else if (d instanceof L.Polygon) d.bringToBack(); }
function incorporar(capa, elementos) {
  const est = estado[capa.id];
  if (capa.id === "camaras") {       // las cámaras tienen su propio dibujo, con el abanico de orientación
    anadirCamaras(elementos.map((e) => { const t = e.etiquetas; return { id: e.id, lat: e.lat, lon: e.lon, tipo: t["surveillance:type"], camara: t["camera:type"], vigila: t.surveillance,
      zona: t["surveillance:zone"], montaje: t["camera:mount"], direccion: t["camera:direction"] || t.direction, operador: t.operator }; })
      .filter((c) => c.vigila !== "indoor" && c.tipo !== "guard"));
    return;
  }
  for (const e of elementos) {
    if (!e || est.elementos.has(e.id)) continue;
    e.capa = capa.id;
    est.elementos.set(e.id, e);
    const d = dibujar(capa, e);
    est.dibujos.set(e.id, d);
    d.addTo(est.grupo);
    if (e.anillos) alFondo(d);
  }
}
function vaciar(capa) {
  const est = estado[capa.id];
  est.grupo.clearLayers(); est.elementos.clear(); est.dibujos.clear(); est.teselas.clear();
}

/* --- Carga según lo que se ve --- */
const estaActiva = (capa) => (capa.activa ? capa.activa() : capasActivas.has(capa.id));
function teselasQueFaltan(capa) {
  const paso = capa.paso || pasoDe(capa.zoom), b = mapa.getBounds(), faltan = [], est = estado[capa.id];
  for (let i = Math.floor(b.getSouth() / paso); i <= Math.floor(b.getNorth() / paso); i++)
    for (let j = Math.floor(b.getWest() / paso); j <= Math.floor(b.getEast() / paso); j++)
      if (!est.teselas.has(`${i}:${j}`)) faltan.push([i, j]);
  return { faltan, paso };
}
function cajaDeLaVista(margen = 0.1) {
  const b = mapa.getBounds().pad(margen);
  return { s: +b.getSouth().toFixed(5), o: +b.getWest().toFixed(5), n: +b.getNorth().toFixed(5), e: +b.getEast().toFixed(5) };
}
const cajaDe = (teselas, paso) => {
  const is = teselas.map((t) => t[0]), js = teselas.map((t) => t[1]);
  return { s: +(Math.min(...is) * paso).toFixed(6), n: +((Math.max(...is) + 1) * paso).toFixed(6), o: +(Math.min(...js) * paso).toFixed(6), e: +((Math.max(...js) + 1) * paso).toFixed(6) };
};
/* Todas las teselas del rectángulo, no solo las que faltaban: es lo que de verdad se pide. */
function teselasDeCaja(caja, paso) {
  const lista = [];
  for (let i = Math.round(caja.s / paso); i < Math.round(caja.n / paso); i++) for (let j = Math.round(caja.o / paso); j < Math.round(caja.e / paso); j++) lista.push(`${i}:${j}`);
  return lista;
}

/* --- Memoria: lo que ya se bajó de una capa, guardado por trozos de mapa (ver «memoria» en index.html) --- */
const vidaDe = (capa) => (capa.vida || (capa.tipo === "osm" ? 7 : 3)) * DIA;      // días que vale lo guardado
const claveMemoria = (capa, paso, tesela) => `capa|${capa.id}|${paso}|${tesela}`;
/* Las teselas que pisa un elemento: un punto, la suya; una línea o un área, todas las que toca. */
function teselasDeElemento(e, paso) {
  let s = e.lat, n = e.lat, o = e.lon, x = e.lon;
  const puntos = e.linea || (e.anillos ? e.anillos.map((poligono) => poligono[0]).flat() : null);
  if (puntos) for (const [la, lo] of puntos) { if (la < s) s = la; if (la > n) n = la; if (lo < o) o = lo; if (lo > x) x = lo; }
  const lista = [];
  if ((n - s) / paso > 40 || (x - o) / paso > 40) return lista;      // algo descomunal: no se reparte (irá en todas las pedidas)
  for (let i = Math.floor(s / paso); i <= Math.floor(n / paso); i++) for (let j = Math.floor(o / paso); j <= Math.floor(x / paso); j++) lista.push(`${i}:${j}`);
  return lista;
}
/* Guarda lo recibido repartido por teselas. Una tesela sin nada también se guarda: «aquí no hay» es un dato. */
function recordar(capa, paso, pedidas, elementos) {
  const porTesela = new Map(pedidas.map((t) => [t, []]));
  for (const e of elementos) {
    if (!e) continue;
    const suyas = teselasDeElemento(e, paso).filter((t) => porTesela.has(t));
    // Lo que no cae en ninguna (una relación de OSM enorme, con el centro fuera) va en todas, para no perderlo.
    for (const t of suyas.length ? suyas : pedidas) porTesela.get(t).push(e);
  }
  memoria.guardar([...porTesela].map(([t, lista]) => [claveMemoria(capa, paso, t), lista]));
}

let relojCapas = null;
const programarCapas = () => { clearTimeout(relojCapas); relojCapas = setTimeout(actualizarCapas, 250); };
function actualizarCapas() {
  const z = mapa.getZoom(), lotes = [];
  for (const capa of CAPAS) {
    const est = estado[capa.id];
    if (capa.tipo === "fija" || capa.tipo === "vivo" || !estaActiva(capa) || z < capa.zoom) continue;
    const { faltan, paso } = teselasQueFaltan(capa);
    if (!faltan.length || faltan.length > 60) continue;
    // Catastro no admite rectángulos grandes: sus capas se piden tesela a tesela, y no más de 16 de una vez.
    const claves = (capa.porTesela ? faltan.slice(0, 16) : faltan).map((t) => `${t[0]}:${t[1]}`);
    for (const t of claves) est.teselas.add(t);
    est.cargando++; est.error = false; est.incompleta = false;
    // 1.º Lo que haya en la memoria del navegador sale al momento.
    lotes.push(memoria.leer(claves.map((t) => claveMemoria(capa, paso, t)), vidaDe(capa)).then((guardadas) => {
      const quedan = [];
      claves.forEach((t, k) => { if (guardadas[k]) incorporar(capa, guardadas[k]); else quedan.push(t.split(":").map(Number)); });
      est.cargando--;
      return { capa, paso, quedan };
    }));
  }
  pintarEstadoCapas();
  if (!lotes.length) return;
  // 2.º El resto se pide fuera.
  Promise.all(lotes).then((listas) => {
    const tandaOSM = [];
    for (const { capa, paso, quedan } of listas) {
      const est = estado[capa.id];
      if (!quedan.length) continue;
      if (!estaActiva(capa)) { for (const t of quedan) est.teselas.delete(`${t[0]}:${t[1]}`); continue; }      // se apagó mientras tanto
      for (const lote of capa.porTesela ? quedan.map((t) => [t]) : [quedan]) {
        const caja = cajaDe(lote, paso), pedidas = teselasDeCaja(caja, paso);
        for (const t of pedidas) est.teselas.add(t);
        est.cargando++;
        // resultado: true = cargado (y se guarda en la memoria); false = fallo; "parcial" = llegó solo una
        // parte; "descartada" = ya no hacía falta. Salvo en el primer caso, esos trozos de mapa quedan
        // sin dar por cargados y se vuelven a pedir cuando toque.
        let hecho = false;
        const fin = (resultado, elementos) => {
          if (hecho) return;
          hecho = true;
          est.cargando--;
          if (resultado === true) recordar(capa, paso, pedidas, elementos || []);
          else for (const t of pedidas) est.teselas.delete(t);
          if (resultado === false) est.error = true;
          if (resultado === "parcial") est.incompleta = true;
          pintarEstadoCapas();
          // Las capas de Catastro van por tandas de 16 trozos: al acabar una (bien), se mira si queda algo a la vista.
          if (resultado === true && capa.porTesela && !est.cargando) programarCapas();
        };
        const sigue = () => estaActiva(capa) && mapa.getZoom() >= capa.zoom && enVista(caja.s, caja.o, caja.n, caja.e);
        const fallo = (err) => fin(err && err.message === "descartada" ? "descartada" : false);
        if (capa.tipo === "osm") tandaOSM.push({ capa, caja, fin, sigue, fallo });
        else capa.pedir(caja, sigue).then((elementos) => { incorporar(capa, elementos); fin(true, elementos); }, fallo);
      }
    }
    // A OpenStreetMap se le pregunta por tandas pequeñas: así lo primero llega pronto y una capa
    // lenta no deja a las demás esperando. Las que cuestan mucho al servidor van solas.
    const ligeras = tandaOSM.filter((t) => !t.capa.pesada);
    for (let k = 0; k < ligeras.length; k += CAPAS_POR_TANDA) pedirTandaOSM(ligeras.slice(k, k + CAPAS_POR_TANDA));
    for (const una of tandaOSM.filter((t) => t.capa.pesada)) pedirTandaOSM([una]);
    pintarEstadoCapas();
  });
}
/* Una consulta a OpenStreetMap para varias capas a la vez. */
const TOPE_OSM = 8000, CAPAS_POR_TANDA = 3;
function pedirTandaOSM(tanda) {
  const cuerpo = tanda.map(({ capa, caja }) => capa.ql.map((q) => `${q}(${caja.s},${caja.o},${caja.n},${caja.e});`).join("")).join("");
  return overpass(`[out:json][timeout:40];(${cuerpo});out geom qt ${TOPE_OSM};`, () => tanda.some((una) => una.sigue())).then((j) => {
    const elementos = j.elements || [], cortado = elementos.length >= TOPE_OSM;
    // Si se llegó al tope, faltan elementos y no se sabe de qué capa: se repite capa a capa.
    if (cortado && tanda.length > 1) return Promise.all(tanda.map((una) => pedirTandaOSM([una])));
    for (const { capa, fin } of tanda) {
      const suyos = elementos.filter((e) => capa.es(e.tags || {})).map((e) => elementoOSM(e, capa)).filter(Boolean);
      incorporar(capa, suyos);
      fin(cortado ? "parcial" : true, suyos);      // una capa sola que llega al tope: al acercar el mapa se pedirá menos trozo
    }
    return null;
  }).catch((err) => {
    // Si al servidor se le acabó el tiempo con varias capas juntas, la culpa suele ser de una sola:
    // se repite capa a capa para que las demás no paguen por ella.
    if (err && err.message === "overpass" && tanda.length > 1) return Promise.all(tanda.map((una) => pedirTandaOSM([una])));
    for (const { fallo } of tanda) fallo(err);
    return null;
  });
}

/* Capas en vivo: se vuelven a pedir cada pocos segundos mientras están encendidas. */
const relojesVivo = {};
function refrescarVivo(capa) {
  const est = estado[capa.id];
  if (!estaActiva(capa) || document.hidden) return;
  if (mapa.getZoom() < capa.zoom) { vaciar(capa); pintarEstadoCapas(); return; }
  capa.pedir().then((elementos) => {
    const abierto = elementoAbierto && elementoAbierto.capa === capa.id ? elementoAbierto.id : null;
    vaciar(capa); incorporar(capa, elementos); est.error = false;
    if (abierto && est.elementos.has(abierto)) { const e = est.elementos.get(abierto); elementoAbierto = e; marcarSeleccion(e); }
  }, (err) => { est.error = true; est.mensaje = /servir/.test(err.message) ? "solo con el programa del PC" : ""; }).finally(pintarEstadoCapas);
}

/* --- Panel de capas --- */
function pintarEstadoCapas() {
  const z = mapa.getZoom(), cargando = [], fallos = [];
  for (const capa of CAPAS) {
    const est = estado[capa.id], nota = $(`estado-${capa.id}`);
    // (un fallo de una capa que a este zoom ni se pide no se anuncia: ya dirá «acerca el mapa»)
    if (estaActiva(capa)) { if (est.cargando) cargando.push(corto(capa)); else if (est.error && (z >= capa.zoom || capa.tipo === "vivo")) fallos.push(corto(capa)); }
    if (!nota) continue;
    if (capa.opcional) nota.parentElement.hidden = !est.conDatos;
    nota.parentElement.classList.toggle("lejos", est.sinDatos || (estaActiva(capa) && z < capa.zoom));
    nota.textContent = est.sinDatos ? "sin descargar" : !estaActiva(capa) ? "" : z < capa.zoom ? "acerca el mapa" : est.cargando ? "cargando" : est.error ? (est.mensaje || "sin respuesta")
      : est.incompleta ? `${est.elementos.size}, hay más: acerca` : String(est.elementos.size);
  }
  // El aviso dice qué se está pidiendo; si algo no ha contestado, deja reintentarlo. Solo se
  // rehace cuando cambia lo que dice: esta función se llama muchas veces seguidas.
  const aviso = $("aviso-capas"), texto = cargando.length ? `Cargando ${enumerar(cargando)}…` : fallos.length ? `Sin respuesta: ${enumerar(fallos)}.` : "";
  aviso.hidden = !texto;
  if (aviso.dataset.texto !== texto) {
    aviso.dataset.texto = texto;
    if (cargando.length) aviso.replaceChildren(el("i", { className: "girando" }), el("span", { textContent: texto }));
    else if (fallos.length) {
      const reintentar = el("button", { type: "button", textContent: "Reintentar" });
      reintentar.addEventListener("click", actualizarCapas);
      aviso.replaceChildren(el("span", { textContent: texto }), reintentar);
    }
  }
  GRUPOS.forEach((grupo, k) => {
    const suyas = CAPAS.filter((c) => c.grupo === grupo && !c.oculta), encendidas = suyas.filter((c) => capasActivas.has(c.id)).length;
    $(`cuenta-grupo-${k}`).textContent = encendidas ? `${encendidas} de ${suyas.length}` : String(suyas.length);
  });
  if (typeof alCambiarCapas === "function") alCambiarCapas();      // las listas del panel (herramientas.js)
}
function conmutarCapa(capa, encendida) {
  const est = estado[capa.id];
  encendida ? capasActivas.add(capa.id) : capasActivas.delete(capa.id);
  guardarLocal("osintmaps.capas-datos.v1", [...capasActivas]);
  encendida ? est.grupo.addTo(mapa) : mapa.removeLayer(est.grupo);
  if (encendida && capa.traer) capa.traer();
  if (capa.tipo === "vivo") {
    clearInterval(relojesVivo[capa.id]);
    if (encendida) { refrescarVivo(capa); relojesVivo[capa.id] = setInterval(() => refrescarVivo(capa), capa.cada); } else vaciar(capa);
  }
  programarCapas();
  pintarEstadoCapas();
}
const GRUPOS = [...new Set(CAPAS.filter((c) => !c.oculta).map((c) => c.grupo))];
{
  // Abiertos de entrada los grupos con algo encendido y los dos primeros; después, como los deje cada uno.
  const abiertos = leerLocal("osintmaps.grupos.v1", null) || GRUPOS.filter((g, k) => k < 2 || CAPAS.some((c) => c.grupo === g && capasActivas.has(c.id)));
  // (mientras se busca una capa por su nombre los grupos se abren solos: eso no se recuerda)
  const recordar = () => { if (!$("capas").classList.contains("buscando")) guardarLocal("osintmaps.grupos.v1", GRUPOS.filter((g, k) => $(`grupo-${k}`).open)); };
  GRUPOS.forEach((grupo, k) => {
    const caja = el("details", { id: `grupo-${k}`, className: "grupo-de-capas", open: abiertos.includes(grupo) },
      el("summary", {}, el("span", { textContent: grupo }), el("small", { id: `cuenta-grupo-${k}` })));
    caja.addEventListener("toggle", recordar);
    for (const capa of CAPAS.filter((c) => c.grupo === grupo && !c.oculta)) {
      const casilla = el("input", { id: `dato-${capa.id}`, type: "checkbox", checked: capasActivas.has(capa.id) });
      casilla.addEventListener("change", () => conmutarCapa(capa, casilla.checked));
      caja.append(el("label", { className: "casilla", hidden: !!capa.opcional }, casilla, simboloDe(capa), el("span", { textContent: capa.nombre }), el("small", { id: `estado-${capa.id}` })));
    }
    $("capas-datos").append(caja);
  });
}
$("capa-camaras").addEventListener("change", programarCapas);
mapa.on("moveend", programarCapas);
{
  let reloj = null;
  mapa.on("moveend", () => {
    clearTimeout(reloj);
    reloj = setTimeout(() => { for (const capa of CAPAS) if (capa.tipo === "vivo" && capa.alMover && capasActivas.has(capa.id)) refrescarVivo(capa); }, 700);
  });
}
/* Al cambiar de zoom, las áreas pasan de punto a contorno y al revés. Solo hay que
   redibujarlas cuando se cruza ese umbral, no en cada cambio de zoom. */
let conContorno = mapa.getZoom() >= 15;
mapa.on("zoomend", () => {
  if ((mapa.getZoom() >= 15) === conContorno) return;
  conContorno = !conContorno;
  for (const capa of CAPAS) {
    const est = estado[capa.id];
    if (capa.id === "edificios") continue;
    for (const [id, e] of est.elementos) if (e.anillos) { est.grupo.removeLayer(est.dibujos.get(id)); const d = dibujar(capa, e); est.dibujos.set(id, d); d.addTo(est.grupo); alFondo(d); }
  }
});

/* Capas fijas: las que descarga «osintmaps capas» a la carpeta de datos. */
function cargarCapaFija(capa, geojson) {
  const elementos = ((geojson && geojson.features) || []).filter((f) => f.geometry && f.properties).map((f) => {
    const p = f.properties, e = { id: String(p.id), lon: +f.geometry.coordinates[0], lat: +f.geometry.coordinates[1], nombre: p.nombre || capa.nombre, p, url: urlSegura(p.url) };
    e.datos = capa.filas ? capa.filas(e) : [];
    if (capa.color_de) e.color = capa.color_de(p);
    if (p.imagen && urlSegura(p.imagen)) { e.imagen = p.imagen; e.enDirecto = !!capa.vivo; }
    return e;
  });
  incorporar(capa, elementos);
  estado[capa.id].sinDatos = false;
  estado[capa.id].conDatos = elementos.length > 0;
}
{
  const base = new URLSearchParams(location.search).get("datos") || "datos/";
  const fijas = CAPAS.filter((c) => c.tipo === "fija");
  for (const capa of fijas) {
    let pedida = false;
    capa.traer = () => {
      if (pedida) return;
      pedida = true;
      const dentro = window.OSINT_CAPAS && window.OSINT_CAPAS[capa.id];
      (dentro ? Promise.resolve(dentro) : window.OSINT_DATOS ? Promise.reject() : pedirJSON(`${base}capa-${capa.id}.geojson`))
        .then((g) => cargarCapaFija(capa, g)).catch(() => { estado[capa.id].sinDatos = true; /* aún no se ha descargado */ }).finally(pintarEstadoCapas);
    };
  }
  for (const capa of CAPAS) if (!capa.oculta && capasActivas.has(capa.id)) conmutarCapa(capa, true);      // las encendidas se leen ya
  // Las apagadas, cuando la página ya está pintada: no estorban al arrancar y quedan listas para el buscador.
  setTimeout(() => { for (const capa of fijas) capa.traer(); }, 2500);
  programarCapas();
}

/* ====================== 3. Ficha de un elemento o de un punto ====================== */
const capaDe = (e) => CAPA[e.capa] || (e.capa === "lugar" ? CAPA_LUGAR : CAPA_PUNTO);
const puntoDe = (latlng, nombre) => ({ id: `punto/${latlng.lat.toFixed(6)},${latlng.lng.toFixed(6)}`, capa: "punto", lat: +latlng.lat.toFixed(6), lon: +latlng.lng.toFixed(6), nombre: nombre || "Punto del mapa" });
function elementoDeCamara(c) {
  return { id: c.id, capa: "camaras", lat: c.lat, lon: c.lon, nombre: "Cámara de vigilancia", datos: filasCamara(c),
           url: /^(node|way|relation)\/\d+$/.test(c.id) ? `https://www.openstreetmap.org/${c.id}` : null };
}

const marcaSeleccion = L.circleMarker([0, 0], { radius: 15, color: "#e5007d", weight: 3, fill: false, interactive: false });
/* Lo que no tiene su símbolo en el mapa (un sitio del buscador, un punto cualquiera) se señala con una chincheta. */
const chinchetaLugar = L.marker([0, 0], { interactive: false, keyboard: false, zIndexOffset: 600 });
function marcarSeleccion(e) {
  const suelto = e.suelto || e.capa === "punto" || e.capa === "lugar";
  if (suelto) {
    const capa = capaDe(e);
    chinchetaLugar.setIcon(L.divIcon({ className: "chincheta-lugar", html: chinchetaHTML(ICONOS[capa.icono || capa.id] && capa !== CAPA_LUGAR ? capa.icono || capa.id : "punto", capa === CAPA_PUNTO ? "#17242e" : e.color || capa.color, true), iconSize: [32, 42], iconAnchor: [16, 41] }));
    chinchetaLugar.setLatLng([e.lat, e.lon]).addTo(mapa);
    mapa.removeLayer(marcaSeleccion);
  } else { marcaSeleccion.setLatLng([e.lat, e.lon]).addTo(mapa); mapa.removeLayer(chinchetaLugar); }
}
function alSoltarElemento() { mapa.removeLayer(marcaSeleccion); mapa.removeLayer(chinchetaLugar); }
function cerrarElemento() { soltarElemento(); mostrarLista(); if (candidatos.length) filtrar(); if (busquedaCerca) pintarBusquedaCerca(); }

const conReloj = (url) => url + (url.includes("?") ? "&" : "?") + "t=" + Math.floor(Date.now() / 30000);
const posicion = (e) => `${e.lat.toFixed(6)},${e.lon.toFixed(6)}`;
function enlacesFuera(e) {
  const p = posicion(e);
  return [["Cómo llegar", `https://www.google.com/maps/dir/?api=1&destination=${p}`],
    ["Google Maps", `https://www.google.com/maps/@?api=1&map_action=map&center=${p}&zoom=19&basemap=satellite`],
    ["Street View", `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${p}`],
    ["Google Earth", `https://earth.google.com/web/search/${p}`],
    ["OpenStreetMap", `https://www.openstreetmap.org/?mlat=${e.lat}&mlon=${e.lon}#map=19/${e.lat}/${e.lon}`],
    ["Mapillary", `https://www.mapillary.com/app/?lat=${e.lat}&lng=${e.lon}&z=18`],
    ["Bing (vista de pájaro)", `https://www.bing.com/maps?cp=${e.lat}~${e.lon}&lvl=19&style=o`]];
}
function tablaDatos(filas) {
  const dl = el("dl", { className: "datos" });
  for (const [k, v] of filas) {
    if (v == null || v === "") continue;
    const texto = String(v), segura = /^https:\/\//.test(texto) ? urlSegura(texto) : null;
    dl.append(el("dt", { textContent: k }), el("dd", {}, segura ? el("a", { href: segura, target: "_blank", rel: "noopener noreferrer", textContent: new URL(segura).hostname }) : texto));
  }
  return dl.children.length ? dl : null;
}

/* Lo que se sabe de un punto cualquiera: dirección, parcela, altitud, luz y tiempo. */
/* --- Horarios de OpenStreetMap ---
   «Mo-Fr 09:00-14:00,17:00-20:00; Sa 10:00-14:00; Su off» se convierte en una semana de tramos
   (en minutos desde medianoche). Lo que no se entiende (meses, «hasta el anochecer», comentarios)
   devuelve null: entonces se enseña el texto tal cual y no se afirma si está abierto. */
const DIAS_OSM = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"], DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
function semanaOSM(texto) {
  let t = String(texto || "").trim();
  if (!t) return null;
  if (/^24\/7$/.test(t)) return DIAS_OSM.map(() => [[0, 1440]]);
  // «…14:00, Sa 10:00…»: una coma seguida de un día, detrás de una hora, separa reglas (se escribe mucho así).
  t = t.replace(/(\d|off|closed)\s*,\s*(?=(?:Mo|Tu|We|Th|Fr|Sa|Su|PH)\b)/g, "$1;");
  const semana = DIAS_OSM.map(() => null);
  for (const cruda of t.split(";")) {
    const regla = cruda.trim();
    if (!regla) continue;
    const m = /^((?:(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)(?:\s*-\s*(?:Mo|Tu|We|Th|Fr|Sa|Su))?\s*,?\s*)*)(.*)$/.exec(regla);
    const dias = new Set(), listaDias = m[1].trim().replace(/,$/, "");
    let soloFestivos = false;
    if (listaDias) {
      for (const trozo of listaDias.split(",").map((x) => x.trim()).filter(Boolean)) {
        if (trozo === "PH" || trozo === "SH") { soloFestivos = true; continue; }      // los festivos no se saben: se saltan
        const [a, b] = trozo.split("-").map((x) => DIAS_OSM.indexOf(x.trim()));
        if (a < 0 || (b !== undefined && b < 0)) return null;
        if (b === undefined) dias.add(a); else for (let d = a; ; d = (d + 1) % 7) { dias.add(d); if (d === b) break; }
      }
      if (!dias.size && soloFestivos) continue;
    } else for (let d = 0; d < 7; d++) dias.add(d);
    const resto = m[2].trim();
    let tramos = [];
    if (/^(off|closed)$/i.test(resto)) tramos = [];
    else if (!resto) { if (!listaDias) return null; tramos = [[0, 1440]]; }
    else {
      for (const tr of resto.split(",")) {
        const h = /^\s*(\d{1,2}):(\d{2})\s*(?:-\s*(\d{1,2}):(\d{2})|\+)\s*$/.exec(tr);
        if (!h) return null;
        const ini = +h[1] * 60 + +h[2];
        let fin = h[3] !== undefined ? +h[3] * 60 + +h[4] : 1440;
        if (ini >= 1440 || fin > 1440 + 720) return null;
        if (fin <= ini) fin += 1440;      // pasa de medianoche
        tramos.push([ini, fin]);
      }
    }
    for (const d of dias) semana[d] = tramos;
  }
  return semana.some((x) => x) ? semana.map((x) => x || []) : null;
}
const horaDelDia = (m) => { const mm = ((m % 1440) + 1440) % 1440; return `${Math.floor(mm / 60)}:${String(mm % 60).padStart(2, "0")}`; };
function horarioOSM(texto, ahora = new Date()) {
  const semana = semanaOSM(texto);
  if (!semana) return null;
  const SEMANA = 7 * 1440, dia = (ahora.getDay() + 6) % 7, t = dia * 1440 + ahora.getHours() * 60 + ahora.getMinutes();
  const tramos = [];
  semana.forEach((lista, d) => { for (const [a, b] of lista) tramos.push([d * 1440 + a, d * 1440 + b]); });
  const texto7 = () => {      // la semana, juntando los días seguidos que tienen el mismo horario
    const filas = [];
    for (let d = 0; d < 7; d++) {
      const horas = semana[d].length ? semana[d].map(([a, b]) => (b - a >= 1440 ? "24 horas" : `${horaDelDia(a)}–${horaDelDia(b)}`)).join(", ") : "cerrado";
      const ultima = filas[filas.length - 1];
      if (ultima && ultima[2] === horas) ultima[1] = d; else filas.push([d, d, horas]);
    }
    return filas.map(([a, b, horas]) => [a === b ? DIAS_ES[a] : b === a + 1 ? `${DIAS_ES[a]} y ${DIAS_ES[b]}` : `${DIAS_ES[a]} a ${DIAS_ES[b]}`, horas]);
  };
  if (semana.every((lista) => lista.length === 1 && lista[0][0] === 0 && lista[0][1] >= 1440)) return { abierto: true, siempre: true, cambio: "las 24 horas", semana: texto7() };
  if (!tramos.length) return { abierto: false, cambio: "", semana: texto7() };
  // (un tramo que pasa de la medianoche del domingo sigue en el lunes: por eso se mira también t + una semana)
  const actual = tramos.find(([a, b]) => (t >= a && t < b) || (t + SEMANA >= a && t + SEMANA < b));
  if (actual) {
    let fin = actual[1] % SEMANA;
    for (let k = 0; k < 8; k++) { const sigue = tramos.find(([a]) => a % SEMANA === fin); if (!sigue) break; fin = sigue[1] % SEMANA; }      // tramos pegados (hasta las 24:00 y desde las 0:00)
    return { abierto: true, cambio: `cierra a las ${horaDelDia(fin)}`, semana: texto7() };
  }
  let mejor = null;
  for (const [a] of tramos) { const espera = (((a - t) % SEMANA) + SEMANA) % SEMANA; if (!mejor || espera < mejor[0]) mejor = [espera, a]; }
  const d = Math.floor(mejor[1] / 1440) % 7, cuando = d === dia && mejor[0] < 1440 ? "" : d === (dia + 1) % 7 && mejor[0] < 2880 ? "mañana " : `el ${DIAS_ES[d]} `;
  return { abierto: false, cambio: `abre ${cuando}a las ${horaDelDia(mejor[1])}`, semana: texto7() };
}

/* Lo primero que se quiere saber de un negocio: si está abierto, dónde está y cómo se le llama. */
const webDe = (t) => { const w = t.website || t["contact:website"] || t.url; return w ? urlSegura(/^https?:\/\//i.test(w) ? w.replace(/^http:/i, "https:") : `https://${w}`) : null; };
const telefonoDe = (t) => t.phone || t["contact:phone"] || t["contact:mobile"] || "";
const direccionDe = (t) => [[t["addr:street"] || t["addr:place"], t["addr:housenumber"]].filter(Boolean).join(" "), [t["addr:postcode"], t["addr:city"]].filter(Boolean).join(" ")].filter(Boolean).join(", ");
function resumenNegocio(t) {
  const caja = el("div", { className: "negocio" });
  if (t.opening_hours) {
    const h = horarioOSM(t.opening_hours);
    if (h) {
      const tabla = el("dl", { className: "datos" });
      for (const [dias, horas] of h.semana) tabla.append(el("dt", { textContent: dias.replace(/^./, (x) => x.toUpperCase()) }), el("dd", { textContent: horas }));
      caja.append(el("details", { className: "horario" }, el("summary", {}, el("b", { className: h.abierto ? "abierto" : "cerrado", textContent: h.abierto ? "Abierto" : "Cerrado" }),
        el("span", { textContent: h.siempre ? " las 24 horas" : h.cambio ? ` · ${h.cambio}` : "" })), tabla, el("p", { className: "ayuda", textContent: "Horario de OpenStreetMap, sin festivos: puede no estar al día." })));
    } else caja.append(el("p", { className: "horario" }, iconoSVG("reloj", 16), ` Horario: ${t.opening_hours}`));
  }
  const direccion = direccionDe(t), telefono = telefonoDe(t), web = webDe(t);
  if (direccion) caja.append(el("p", {}, iconoSVG("lugar", 16), ` ${direccion}`));
  if (telefono) caja.append(el("p", {}, iconoSVG("telefono", 16), " ", el("a", { href: `tel:${telefono.split(";")[0].replace(/[^\d+]/g, "")}`, textContent: telefono.split(";")[0].trim() })));
  if (web) caja.append(el("p", {}, iconoSVG("web", 16), " ", el("a", { href: web, target: "_blank", rel: "noopener noreferrer", textContent: new URL(web).hostname.replace(/^www\./, "") })));
  return caja.children.length ? caja : null;
}

const RCCOOR = "https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_RCCOOR";
function faseLunar(fecha) {
  const dias = fecha / 86400000 - 10962.76, ciclo = ((dias % 29.530588853) + 29.530588853) % 29.530588853, parte = ciclo / 29.530588853;
  const luz = Math.round(((1 - Math.cos(2 * Math.PI * parte)) / 2) * 100);
  return `${luz} % iluminada, ${parte < 0.5 ? "creciente" : "menguante"}`;
}
function sobreElPunto(e, dl) {
  const fila = (nombre) => { const dd = el("dd", { className: "pendiente", textContent: "consultando…" }); dl.append(el("dt", { textContent: nombre }), dd); return dd; };
  const poner = (dd, texto) => { dd.className = texto ? "" : "pendiente"; dd.textContent = texto || "sin dato"; };
  const direccion = fila("Dirección"), parcela = fila("Parcela"), uso = fila("Catastro"), altitud = fila("Altitud"), tiempo = fila("Ahora"), aire = fila("Aire"), sol = fila("Sol"), luna = fila("Luna");
  poner(luna, faseLunar(Date.now()));
  const sigue = () => elementoAbierto === e;
  pedirJ(`https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${e.lat}&longitude=${e.lon}&current=european_aqi,pm10,pm2_5,nitrogen_dioxide,ozone,uv_index`, null, 15000).then((j) => {
    if (!sigue()) return;
    const c = j.current || {}, i = c.european_aqi;
    poner(aire, i == null ? "" : `${i <= 20 ? "bueno" : i <= 40 ? "aceptable" : i <= 60 ? "regular" : i <= 80 ? "malo" : "muy malo"} (índice europeo ${Math.round(i)}); PM2,5 ${String(c.pm2_5).replace(".", ",")}, NO₂ ${String(c.nitrogen_dioxide).replace(".", ",")}, ozono ${Math.round(c.ozone)} µg/m³` +
      (c.uv_index >= 3 ? `; índice UV ${Math.round(c.uv_index)}` : ""));
  }).catch(() => poner(aire, ""));
  if (typeof identificarEnSuperpuestas === "function") identificarEnSuperpuestas(e, dl, sigue);
  pedirJ(`https://www.cartociudad.es/geocoder/api/geocoder/reverseGeocode?lon=${e.lon}&lat=${e.lat}`, null, 15000).then((j) => {
    if (!sigue()) return;
    poner(direccion, j && j.address ? `${j.address}${j.portalNumber ? " " + j.portalNumber : ""}, ${j.postalCode || ""} ${j.muni || ""}`.replace(/\s+/g, " ").replace(/ ,/g, ",").trim() : "");
  }).catch(() => poner(direccion, ""));
  pedirJ(`${RCCOOR}?CoorX=${e.lon}&CoorY=${e.lat}&SRS=EPSG:4326`, null, 20000).then((j) => {
    const c = (((j.Consulta_RCCOORResult || {}).coordenadas || {}).coord || [])[0];
    if (!sigue()) return null;
    if (!c || !c.pc) { poner(parcela, ""); poner(uso, ""); return null; }
    const refcat = c.pc.pc1 + c.pc.pc2;
    e.refcat = refcat;
    if (tipoParcela(refcat) === "urbana") {
      const fachada = el("img", { alt: "Foto de fachada de Catastro", referrerPolicy: "no-referrer" });      // sin «lazy»: aún no está en la página
      fachada.addEventListener("load", () => {
        if (!sigue() || fachada.naturalWidth < 50) return;      // Catastro manda una imagen diminuta cuando no tiene foto
        const abrir = el("button", { type: "button", className: "portada fachada", title: "Abrir en grande" }, fachada, el("span", { textContent: "Fachada (Catastro)" }));
        abrir.addEventListener("click", () => abrirVisor(Object.assign({}, e, { imagen: fachada.src, original: fachada.src, imagenes: null, enDirecto: false, marco: null, autor: "Dirección General del Catastro" }), "imagen"));
        dl.after(abrir);
      });
      fachada.src = `https://ovc.catastro.meh.es/OVCServWeb/OVCWcfLibres/OVCFotoFachada.svc/RecuperarFotoFachadaGet?ReferenciaCatastral=${refcat}`;
    }
    parcela.className = "";
    parcela.replaceChildren(el("a", { href: `https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCListaBienes.aspx?rc1=${c.pc.pc1}&rc2=${c.pc.pc2}`, target: "_blank", rel: "noopener noreferrer", textContent: refcat }),
      ` (${{ publico: "dominio público", rustica: "rústica", urbana: "urbana" }[tipoParcela(refcat)]})`);
    return pedirJ(`${DATOS_PARCELA}?RefCat=${encodeURIComponent(refcat)}`, null, 20000).then((d) => {
      if (!sigue()) return;
      const res = d.consulta_dnprcResult || {};
      if (res.bico) {
        const debi = (res.bico.bi || {}).debi || {}, cultivos = [...new Set((res.bico.lspr || []).map((x) => (x.dspr || {}).dcc).filter(Boolean))];
        poner(uso, [debi.luso, debi.sfc ? `${miles(+debi.sfc)} m² construidos` : "", debi.ant ? `año ${debi.ant}` : "", cultivos.join(", ")].filter(Boolean).join(", ").toLowerCase());
      } else if (res.lrcdnp && res.lrcdnp.rcdnp) {
        const inm = [].concat(res.lrcdnp.rcdnp), usos = [...new Set(inm.map((x) => (x.debi || {}).luso).filter(Boolean))], anios = inm.map((x) => +(x.debi || {}).ant).filter(Boolean);
        poner(uso, `${inm.length} inmuebles (${usos.join(", ").toLowerCase()})${anios.length ? `, año ${Math.min(...anios)}` : ""}`);
      } else poner(uso, "");
    });
  }).catch(() => { if (parcela.textContent === "consultando…") poner(parcela, ""); poner(uso, ""); });
  pedirJ(`https://api.open-meteo.com/v1/forecast?latitude=${e.lat}&longitude=${e.lon}&current=temperature_2m,precipitation,cloud_cover,wind_speed_10m&daily=sunrise,sunset&timezone=auto&forecast_days=1`, null, 15000).then((j) => {
    if (!sigue()) return;
    poner(altitud, j.elevation != null ? `${Math.round(j.elevation)} m` : "");
    const c = j.current || {};
    poner(tiempo, c.temperature_2m != null ? `${Math.round(c.temperature_2m)} °C, nubes ${c.cloud_cover} %, viento ${Math.round(c.wind_speed_10m)} km/h${c.precipitation ? `, lluvia ${c.precipitation} mm` : ""}` : "");
    const d = j.daily || {};
    poner(sol, d.sunrise && d.sunset ? `sale a las ${d.sunrise[0].slice(11)}, se pone a las ${d.sunset[0].slice(11)}` : "");
  }).catch(() => { poner(altitud, ""); poner(tiempo, ""); poner(sol, ""); });
}

/* Qué hay alrededor, preguntando a OpenStreetMap por un círculo de 200 m. */
function analizarEntorno(e, destino) {
  destino.replaceChildren(el("p", { className: "pendiente", textContent: "Preguntando a OpenStreetMap (hasta un minuto)…" }));
  const r = 200, c = `${e.lat},${e.lon}`;
  overpass(`[out:json][timeout:30];(nwr["man_made"="surveillance"](around:${r},${c});node["highway"="street_lamp"](around:${r},${c});way["barrier"](around:${r},${c});` +
           `node["barrier"](around:${r},${c});nwr["amenity"="police"](around:2500,${c});way["building"](around:${r},${c}););out tags center qt;`, null, true).then((j) => {
    const sitio = (x) => (x.type === "node" ? x : x.center) || {}, lejos = (x) => Math.round(mapa.distance([e.lat, e.lon], [sitio(x).lat, sitio(x).lon]));
    const de = (prueba) => (j.elements || []).filter((x) => sitio(x).lat != null && prueba(x.tags || {})).sort((a, b) => lejos(a) - lejos(b));
    const camaras0 = de((t) => t.man_made === "surveillance" && t.surveillance !== "indoor"), farolas = de((t) => t.highway === "street_lamp");
    const vallas = (j.elements || []).filter((x) => x.type === "way" && (x.tags || {}).barrier), puertas = de((t) => /gate|lift_gate|swing_gate|entrance|turnstile/.test(t.barrier || ""));
    const policia = de((t) => t.amenity === "police"), edificios = (j.elements || []).filter((x) => x.type === "way" && (x.tags || {}).building);
    incorporar(CAPA.camaras, camaras0.map((x) => ({ id: `${x.type}/${x.id}`, lat: sitio(x).lat, lon: sitio(x).lon, etiquetas: x.tags })));
    const abandonado = candidatos.map((k) => [k, mapa.distance([e.lat, e.lon], [k.lat, k.lon])]).sort((a, b) => a[1] - b[1])[0];
    const filas = [["Cámaras", camaras0.length ? `${camaras0.length}, la más cercana a ${lejos(camaras0[0])} m` : "ninguna dibujada"],
      ["Farolas", farolas.length ? `${farolas.length}, la más cercana a ${lejos(farolas[0])} m` : "ninguna dibujada"],
      ["Vallas y muros", vallas.length ? `${vallas.length} tramos` : "ninguno dibujado"], ["Puertas y barreras", puertas.length ? `${puertas.length}, la más cercana a ${lejos(puertas[0])} m` : "ninguna dibujada"],
      ["Edificios", String(edificios.length)], ["Policía", policia.length ? `${(policia[0].tags.name || "comisaría")} a ${miles(lejos(policia[0]))} m` : "ninguna a menos de 2,5 km"]];
    destino.replaceChildren(tablaDatos(filas), el("p", { className: "ayuda", textContent: "Radio de 200 m. OpenStreetMap solo tiene lo que alguien ha dibujado: «ninguna» no es garantía." }));
    if (abandonado && abandonado[1] < 3000) {
      const ir = el("button", { type: "button", textContent: `Sitio abandonado más cercano: ${tituloDe(abandonado[0])}, a ${miles(abandonado[1])} m` });
      ir.addEventListener("click", () => abrirFicha(abandonado[0], true));
      destino.append(el("div", { className: "enlaces" }, ir));
    }
  }).catch(() => destino.replaceChildren(el("p", { className: "pendiente", textContent: "OpenStreetMap no ha respondido. Vuelve a intentarlo en un momento." })));
}

function abrirElemento(e, mover) {
  if (seleccion) mostrarLista();
  soltarMarcador(); soltarElemento(); ocultarFichaRuta();
  elementoAbierto = e;
  const capa = capaDe(e);
  desplegarPanel();

  const volver = el("button", { type: "button", textContent: "Lista" });
  volver.addEventListener("click", cerrarElemento);
  const muestra = simboloDe(capa, e.color, 22);

  // Portada: la imagen propia del elemento si la tiene; si no, la ortofoto de hoy.
  const lado = Math.min(700, Math.max(160, 4 * Math.sqrt(e.superficie || 1600)));
  const portada = el("button", { type: "button", className: "portada", title: "Abrir en grande" });
  const imagen = el("img", { alt: "", referrerPolicy: "no-referrer" });
  const aerea = () => ponerFotoAerea(imagen, fotosAereas(e.lat, e.lon, lado, pxDePantalla(400, 1400)));
  if (e.imagen) {
    imagen.addEventListener("error", () => { if (!imagen.dataset.respaldo) { imagen.dataset.respaldo = "1"; aerea(); rotulo.textContent = "Ortofoto de hoy"; } }, { once: true });
    imagen.src = e.enDirecto ? conReloj(e.imagen) : e.imagen;
  } else aerea();
  const rotulo = el("span", { textContent: e.imagen ? (e.enDirecto ? "Imagen en directo" : "Foto") : e.marco ? "Pulsa para ver la cámara en directo" : "Ortofoto de hoy" });
  portada.append(imagen, rotulo);
  portada.addEventListener("click", () => abrirVisor(e, e.imagen || e.marco ? "imagen" : "ortofoto"));

  const vistas = filaDeVistas(e);
  const negocio = el("div");
  const pintarNegocio = () => { const r = e.etiquetas ? resumenNegocio(e.etiquetas) : null; negocio.replaceChildren(...(r ? [r] : [])); };
  pintarNegocio();

  const acciones = el("div", { className: "enlaces" });
  const guardar = el("button", { type: "button", textContent: "Guardar como marcador" });
  guardar.addEventListener("click", () => {
    const esCamara = /^(camaras|dgt|camvlc)$/.test(e.capa);
    nuevoMarcador(L.latLng(e.lat, e.lon), esCamara ? "camera" : "spot", e.capa === "punto" ? "" : (capa === CAPA_LUGAR ? e.nombre : `${capa.uno || capa.nombre}: ${e.nombre}`).slice(0, 500));
  });
  const centrar = el("button", { type: "button", textContent: "Centrar" });
  centrar.addEventListener("click", () => mapa.setView([e.lat, e.lon], Math.max(mapa.getZoom(), 18)));
  const copiar = el("button", { type: "button", textContent: "Copiar coordenadas" });
  copiar.addEventListener("click", () => {
    const texto = `${e.lat.toFixed(6)}, ${e.lon.toFixed(6)}`;
    (navigator.clipboard ? navigator.clipboard.writeText(texto) : Promise.reject(new Error("sin portapapeles"))).then(() => { copiar.textContent = "Copiadas"; }, () => { copiar.textContent = texto; });
  });
  acciones.append(guardar, centrar, copiar);
  if (e.url && urlSegura(e.url)) acciones.append(el("a", { href: e.url, target: "_blank", rel: "noopener noreferrer", textContent: { wikipedia: "Leer en Wikipedia", commons: "Ficha de la foto", listaroja: "Ficha en Hispania Nostra", subastas: "Subasta en el BOE", aviones: "Seguir el vuelo" }[e.capa] || (/openstreetmap\.org/.test(e.url) ? "Ver en OpenStreetMap" : "Fuente original") }));

  const partes = [el("div", { className: "navegacion" }, volver),
    el("h2", { textContent: e.nombre || capa.nombre }),
    el("div", { className: "lugar" }, muestra, `${e.detalle && capa === CAPA_LUGAR ? e.detalle : (capa.uno && ((e.etiquetas && tipoDeEtiquetas(e.etiquetas)) || ((e.datos || []).find(([k]) => k === "Qué es") || [])[1])) || capa.uno || capa.nombre}. ${e.lat.toFixed(5)}, ${e.lon.toFixed(5)}`),
    negocio, portada, vistas, el("div", { className: "bloque" }, acciones)];

  // Los datos se pintan ahora y otra vez si después llegan las etiquetas de OpenStreetMap (un sitio abierto desde el buscador).
  const zonaDatos = el("div");
  const pintarDatos = () => {
    const tabla = tablaDatos((e.datos || []).concat(e.etiquetas ? filasOSM(e.etiquetas) : []));
    zonaDatos.replaceChildren(...(tabla ? [bloque("Datos", tabla)] : []));
  };
  pintarDatos();
  partes.push(zonaDatos);
  const zonaCrudo = el("div");
  const pintarCrudo = () => zonaCrudo.replaceChildren(...(e.etiquetas ? [el("div", { className: "bloque" }, el("details", {}, el("summary", { textContent: "Todas las etiquetas de OpenStreetMap" }), tablaDatos(Object.entries(e.etiquetas))))] : []));
  if (e.osm && !e.etiquetas) {
    pedirJ(`https://api.openstreetmap.org/api/0.6/${e.osm}.json`, null, 15000).then((j) => {
      const t = ((j.elements || [])[0] || {}).tags;
      if (!t || elementoAbierto !== e) return;
      e.etiquetas = t;
      e.url = `https://www.openstreetmap.org/${e.osm}`;
      e.datos = (e.datos || []).filter(([k]) => k !== "Dirección" || !direccionDe(t));
      pintarNegocio(); pintarDatos(); pintarCrudo();
      if (!acciones.querySelector("a.osm")) acciones.append(el("a", { className: "osm", href: e.url, target: "_blank", rel: "noopener noreferrer", textContent: "Ver en OpenStreetMap" }));
    }).catch(() => { /* se queda con lo que dio el buscador */ });
  }
  if (e.parada) {
    const salidas = el("div");
    partes.push(bloque("Próximos pasos por esta parada", salidas));
    salidasDeParada(e, salidas);
  }
  if (e.pagina) {      // artículo de Wikipedia: su primer párrafo
    const resumen = el("p", { className: "pendiente", textContent: "Cargando el artículo…" });
    partes.push(bloque("De Wikipedia", resumen));
    consultaWiki("es.wikipedia.org", { prop: "extracts", exintro: "1", explaintext: "1", pageids: String(e.pagina) })
      .then((paginas) => { resumen.className = ""; resumen.textContent = ((paginas[0] || {}).extract || "Sin resumen.").slice(0, 1400); })
      .catch(() => { resumen.textContent = "No se pudo cargar el artículo."; });
  }
  if (e.autor || e.licencia) partes.push(el("p", { className: "ayuda", textContent: [e.autor && `Autor: ${e.autor}`, e.licencia && `Licencia: ${e.licencia}`].filter(Boolean).join(". ") }));

  const punto = el("dl", { className: "datos" });
  partes.push(bloque("Sobre este punto", punto));
  const entorno = el("div");
  const analizar = el("button", { type: "button", textContent: "Analizar 200 m alrededor" });
  analizar.addEventListener("click", () => analizarEntorno(e, entorno));
  entorno.append(el("div", { className: "enlaces" }, analizar));
  partes.push(bloque("Qué hay alrededor", entorno));
  pintarCrudo();
  partes.push(zonaCrudo);
  const fuera = el("div", { className: "enlaces" });
  for (const [nombre, url] of enlacesFuera(e)) fuera.append(el("a", { href: url, target: "_blank", rel: "noopener noreferrer", textContent: nombre }));
  partes.push(bloque("Abrir en otra pestaña", fuera));

  $("ficha-elemento").replaceChildren(...partes.filter(Boolean));
  $("lista").hidden = true; $("ver-mas").hidden = true; $("sin-coincidencias").hidden = true; $("ficha").hidden = true;
  $("filtros").hidden = true; $("pie").hidden = true; $("vacio").hidden = true;
  $("ficha-elemento").hidden = false;
  $("contenido").scrollTop = 0;
  marcarSeleccion(e);
  if (mover) mapa.setView([e.lat, e.lon], Math.max(mapa.getZoom(), 17));
  sobreElPunto(e, punto);
  if (e.capa === "punto") analizar.click();
}

/* ====================== 4. Visor a pantalla completa ====================== */
let visor = null;
/* Deja acercar y mover una foto del visor: rueda o pellizco para acercar, arrastrar para moverla y
   doble clic para ir y volver. Si existe una versión mayor de la foto (`grande`), se carga al acercar. */
function hacerAmpliable(img, grande) {
  let k = 1, x = 0, y = 0, pedida = false, pellizco = null;
  const dedos = new Map();
  const centro = () => { const m = img.offsetParent.getBoundingClientRect(); return { x: m.left + img.offsetLeft + img.offsetWidth / 2, y: m.top + img.offsetTop + img.offsetHeight / 2, ancho: m.width, alto: m.height }; };
  const poner = () => {
    const c = centro(), limX = Math.max(0, (img.offsetWidth * k - c.ancho) / 2), limY = Math.max(0, (img.offsetHeight * k - c.alto) / 2);
    x = Math.min(limX, Math.max(-limX, x)); y = Math.min(limY, Math.max(-limY, y));
    img.style.transform = k === 1 ? "" : `translate(${x}px, ${y}px) scale(${k})`;
    img.style.cursor = k === 1 ? "zoom-in" : "grab";
    if (k >= 1.5 && grande && !pedida && grande !== img.src) {
      pedida = true;
      const mayor = new Image();
      mayor.referrerPolicy = "no-referrer";
      mayor.onload = () => { if (document.contains(img)) img.src = grande; };
      mayor.src = grande;
    }
  };
  /* Cambia el aumento dejando quieto el punto de la foto que está bajo (px, py). */
  const acercar = (k2, px, py) => {
    const c = centro(), ux = (px - c.x - x) / k, uy = (py - c.y - y) / k;
    k = Math.min(16, Math.max(1, k2));
    x = px - c.x - ux * k; y = py - c.y - uy * k;
    if (k === 1) x = y = 0;
    poner();
  };
  img.draggable = false;
  img.style.touchAction = "none";
  img.style.cursor = "zoom-in";
  img.addEventListener("wheel", (ev) => { ev.preventDefault(); acercar(k * Math.exp(-ev.deltaY * 0.0016), ev.clientX, ev.clientY); }, { passive: false });
  img.addEventListener("dblclick", (ev) => acercar(k > 1 ? 1 : 3, ev.clientX, ev.clientY));
  img.addEventListener("pointerdown", (ev) => {
    img.setPointerCapture(ev.pointerId);
    dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (dedos.size === 2) { const [a, b] = [...dedos.values()]; pellizco = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, k }; }
  });
  img.addEventListener("pointermove", (ev) => {
    const antes = dedos.get(ev.pointerId);
    if (!antes) return;
    dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (dedos.size === 2 && pellizco) {
      const [a, b] = [...dedos.values()];
      acercar(pellizco.k * Math.hypot(a.x - b.x, a.y - b.y) / pellizco.d, (a.x + b.x) / 2, (a.y + b.y) / 2);
    } else if (dedos.size === 1 && k > 1) { x += ev.clientX - antes.x; y += ev.clientY - antes.y; poner(); }
  });
  const soltar = (ev) => { dedos.delete(ev.pointerId); if (dedos.size < 2) pellizco = null; };
  img.addEventListener("pointerup", soltar);
  img.addEventListener("pointercancel", soltar);
}
function cerrarVisor() {
  if (!visor) return;
  const antes = visor.antes;
  clearInterval(visor.reloj);
  if (visor.mapa) visor.mapa.remove();
  visor.nodo.remove(); visor = null;
  if (antes && antes.focus && document.contains(antes)) antes.focus({ preventScroll: true });      // el foco vuelve a donde estaba
}
function abrirVisor(e, pestana) {
  cerrarVisor();
  const lienzo = el("div", { className: "lienzo" }), opciones = el("div", { className: "opciones" }), pie = el("div", { className: "pie-foto" }), tira = el("div", { className: "miniaturas" });
  const cerrar = el("button", { type: "button", textContent: "Cerrar" });
  cerrar.addEventListener("click", cerrarVisor);
  const pestanas = el("div", { className: "pestanas", role: "tablist" });
  const nodo = el("div", { id: "visor", role: "dialog", ariaLabel: "Imágenes del sitio" },
    el("header", {}, el("h2", { textContent: e.nombre || "Punto del mapa" }), cerrar), pestanas, lienzo, el("div", {}, pie, tira, opciones));
  visor = { nodo, reloj: null, antes: document.activeElement };
  // Cada cambio de pestaña es un turno nuevo: una respuesta que llega tarde, de una pestaña
  // que ya no se está viendo, no debe pintar nada.
  let turno = 0;
  const vigente = (t) => !!visor && visor.nodo === nodo && t === turno;
  const chip = (texto, alPulsar, grupo) => {
    const b = el("button", { type: "button", textContent: texto });
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => { for (const o of grupo.children) if (o.dataset.fila === b.dataset.fila) o.setAttribute("aria-pressed", String(o === b)); alPulsar(); });
    grupo.append(b);
    return b;
  };
  const limpiar = () => {
    clearInterval(visor.reloj);
    if (visor.mapa) { visor.mapa.remove(); visor.mapa = null; }
    lienzo.replaceChildren(); opciones.replaceChildren(); tira.replaceChildren(); pie.replaceChildren();
  };
  const mensaje = (texto) => lienzo.replaceChildren(el("p", { textContent: texto }));
  const foto = (url, textoPie, enlace, grande) => {
    const img = el("img", { alt: "", referrerPolicy: "no-referrer" });
    img.addEventListener("error", () => mensaje("No se ha podido cargar la imagen."));
    img.src = url;
    lienzo.replaceChildren(img);
    hacerAmpliable(img, grande);
    pie.replaceChildren(textoPie || "", enlace && urlSegura(enlace) ? " · " : "", enlace && urlSegura(enlace) ? el("a", { href: enlace, target: "_blank", rel: "noopener noreferrer", textContent: "abrir el original" }) : "");
  };

  const modos = {
    imagen() {
      if (e.marco) { lienzo.replaceChildren(el("iframe", { src: e.marco, title: "Cámara en directo", referrerPolicy: "no-referrer" })); pie.textContent = "Imagen en directo de la cámara municipal."; return; }
      const poner = () => foto(e.enDirecto ? conReloj(e.imagen) : e.original || e.imagen, [e.enDirecto && "Imagen en directo; se renueva sola cada 30 s.", e.autor, e.fecha, e.licencia].filter(Boolean).join(" · "), e.url);
      if ((e.imagenes || []).length > 1) {
        e.imagenes.forEach((url, k) => {
          const b = chip("", () => foto(url, `${e.credito || ""} · foto ${k + 1} de ${e.imagenes.length}`, e.url), tira);
          b.append(el("img", { src: url, alt: "", loading: "lazy", referrerPolicy: "no-referrer" }));
          if (!k) b.click();
        });
        return;
      }
      poner();
      if (e.enDirecto) visor.reloj = setInterval(poner, 30000);
    },
    ortofoto() {
      // Un mapa de verdad dentro del visor: se acerca y se mueve como el grande, y cada trozo llega
      // con todo el detalle que tenga la foto, en vez de una imagen fija estirada.
      const caja = el("div", { className: "mapa-visor" });
      lienzo.replaceChildren(caja);
      const lado0 = Math.min(600, Math.max(120, 3 * Math.sqrt(e.superficie || 1600)));
      // El zoom va siempre en niveles enteros: a medio nivel el navegador estira las teselas y se ven blandas.
      const zoomDe = (metros0) => Math.min(ZOOM_MAX, Math.round(Math.log2((156543.03 * Math.cos((e.lat * Math.PI) / 180) * Math.max(200, Math.min(caja.clientWidth, caja.clientHeight))) / metros0)));
      const mini = L.map(caja, { maxZoom: ZOOM_MAX }).setView([e.lat, e.lon], zoomDe(lado0));
      visor.mapa = mini;
      L.control.scale({ imperial: false }).addTo(mini);
      L.circleMarker([e.lat, e.lon], { radius: 13, color: "#e5007d", weight: 2, fill: false, interactive: false }).addTo(mini);
      let capa = null, elegida = "";
      const describir = (aviso) => {
        const cm = (15654303 * Math.cos((mini.getCenter().lat * Math.PI) / 180)) / 2 ** mini.getZoom() / (window.devicePixelRatio || 1);
        pie.textContent = aviso || `${elegida ? rotuloAntigua(elegida) : "La foto más nítida que hay de este sitio"} · ${cm < 10 ? cm.toFixed(1).replace(".", ",") : Math.round(cm)} cm por punto de pantalla · rueda, pellizco o doble clic para acercar`;
      };
      const poner = (nombre) => {
        if (capa) mini.removeLayer(capa);
        elegida = nombre;
        capa = (nombre ? capaAntigua(nombre, { crossOrigin: "anonymous" }) : mejorFoto()).addTo(mini);
        // Un vuelo que no cubre la zona devuelve todas las teselas lisas (o ninguna).
        let total = 0, lisas = 0, fallos = 0;
        const propia = capa;
        capa.on("tileload", (ev) => { total++; if (nombre && esImagenLisa(ev.tile)) lisas++; });
        capa.on("tileerror", () => { fallos++; });
        capa.on("load", () => { if (propia === capa && nombre && (total ? lisas === total : fallos > 0)) describir("Ese vuelo no cubre esta zona. Prueba otro año."); });
        describir();
      };
      mini.on("zoomend moveend", () => describir());
      const hoy = chip("Hoy", () => poner(""), opciones); hoy.dataset.fila = "anio"; hoy.setAttribute("aria-pressed", "true");
      // En València ciudad hay además fotos y planos municipales, más antiguos y con más detalle.
      const series = [...vuelosDe(e.lat, e.lon), ...(enCaja(VALENCIA_CIUDAD, e.lat, e.lon) ? SERIE_CIUDAD : [])].sort((a, b) => b.anio - a.anio);
      for (const v of series) chip(deLaCiudad(v.nombre) && !/^Plano/.test(v.rotulo) ? `${v.rotulo} ciudad` : v.rotulo, () => poner(v.nombre), opciones).dataset.fila = "anio";
      for (const [texto, metros0] of [["Muy cerca", 40], ["Cerca", 120], ["Entorno", 400], ["Zona", 1200]]) chip(texto, () => mini.setView([e.lat, e.lon], zoomDe(metros0)), tira).dataset.fila = "lado";
      poner("");
    },
    calle() {
      const google = () => {
        lienzo.replaceChildren(el("iframe", { src: `https://www.google.com/maps?layer=c&cbll=${posicion(e)}&cbp=12,${Math.round(e.rumbo || 0)},0,0,0&output=svembed`, title: "Street View", allowFullscreen: true, referrerPolicy: "no-referrer" }));
        pie.textContent = "Street View de Google, incrustado. Si sale en negro, Google no tiene imágenes de este punto.";
      };
      chip("Street View", google, opciones).setAttribute("aria-pressed", "true");
      google();
      const d = 0.0009, t = turno;
      pedirPanoramax({ s: e.lat - d, n: e.lat + d, o: e.lon - d * 1.3, e: e.lon + d * 1.3 }).then((fotos) => {
        if (!vigente(t) || !fotos.length) return;
        fotos.sort((a, b) => metros(e, a) - metros(e, b));
        chip(`Panoramax (${fotos.length} fotos libres)`, () => {
          tira.replaceChildren();
          fotos.slice(0, 40).forEach((f, k) => {
            const b = chip("", () => foto(f.original, `Panoramax · ${fechaCorta(f.fecha)} · a ${Math.round(metros(e, f))} m · ${f.licencia}`, f.url), tira);
            b.append(el("img", { src: f.miniatura, alt: "", loading: "lazy" }));
            if (!k) b.click();
          });
        }, opciones);
        // El visor de Panoramax, incrustado: deja girar las fotos de 360° y pasar de una a otra.
        chip("Panoramax en 360°", () => {
          tira.replaceChildren();
          lienzo.replaceChildren(el("iframe", { src: fotos[0].url, title: "Visor de Panoramax", allowFullscreen: true, referrerPolicy: "no-referrer" }));
          pie.textContent = "Visor de Panoramax: fotos libres a pie de calle. Las de 360° se giran arrastrando.";
        }, opciones);
      }).catch(() => { /* sin fotos libres aquí */ });
    },
    fotos() {
      const t = turno;
      mensaje("Buscando fotos en Wikimedia Commons a menos de 600 m…");
      consultaWiki("commons.wikimedia.org", Object.assign({ ggscoord: `${e.lat}|${e.lon}`, ggsradius: "600", ggslimit: "60" }, PEDIDO_COMMONS, { iiurlwidth: "1920" })).then((paginas) => {
        if (!vigente(t)) return;
        const fotos = paginas.map(fotoCommons).filter(Boolean).sort((a, b) => (a.lat != null ? metros(e, a) : 1e9) - (b.lat != null ? metros(e, b) : 1e9));
        if (!fotos.length) { mensaje("No hay fotos libres de este sitio en Wikimedia Commons."); return; }
        fotos.forEach((f, k) => {
          const b = chip("", () => foto(f.imagen, [f.nombre, f.autor, f.fecha, f.licencia, f.lat != null && `a ${Math.round(metros(e, f))} m`].filter(Boolean).join(" · "), f.url, f.grande), tira);
          b.append(el("img", { src: f.imagen.replace(/\/\d+px-/, "/250px-"), alt: "", loading: "lazy" }));
          if (!k) b.click();
        });
      }).catch(() => { if (vigente(t)) mensaje("Wikimedia Commons no ha respondido."); });
    },
    satelite() {
      const t = turno;
      mensaje("Buscando las últimas pasadas de Sentinel-2…");
      pedirJ("https://earth-search.aws.element84.com/v1/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        collections: ["sentinel-2-l2a"], intersects: { type: "Point", coordinates: [e.lon, e.lat] }, limit: 14, query: { "eo:cloud_cover": { lt: 35 } },
        sortby: [{ field: "properties.datetime", direction: "desc" }] }) }).then((j) => {
        if (!vigente(t)) return;
        const vistas = new Map();
        for (const f of j.features || []) { const dia = f.properties.datetime.slice(0, 10); if (!vistas.has(dia) && f.assets.visual) vistas.set(dia, f); }
        if (!vistas.size) { mensaje("No hay pasadas recientes sin nubes."); return; }
        const d = 0.022, dLon = d / Math.cos((e.lat * Math.PI) / 180);
        [...vistas].slice(0, 10).forEach(([dia, f], k) => {
          const b = chip(fechaCorta(dia), () => {
            foto(`https://titiler.xyz/cog/bbox/${(e.lon - dLon).toFixed(5)},${(e.lat - d).toFixed(5)},${(e.lon + dLon).toFixed(5)},${(e.lat + d).toFixed(5)}/1024x1024.jpg?url=${encodeURIComponent(f.assets.visual.href)}`,
              `Sentinel-2 del ${fechaCorta(dia)}, nubes ${Math.round(f.properties["eo:cloud_cover"])} %. Unos 5 km de lado a 10 m por píxel: sirve para ver cambios recientes, no detalle.`);
            lienzo.append(el("div", { className: "cruz" }));
          }, opciones);
          if (!k) b.click();
        });
      }).catch(() => { if (vigente(t)) mensaje("El catálogo de Sentinel-2 no ha respondido."); });
    },
  };
  const nombres = { imagen: e.enDirecto || e.marco ? "En directo" : "Foto", ortofoto: "Ortofoto por años", calle: "A pie de calle", fotos: "Fotos cerca", satelite: "Satélite reciente" };
  const mostrar = (cual) => {
    turno++;
    limpiar();
    for (const b of pestanas.children) b.setAttribute("aria-selected", String(b.dataset.modo === cual));
    modos[cual]();
  };
  for (const cual of Object.keys(modos)) {
    if (cual === "imagen" && !e.imagen && !e.marco) continue;
    const b = el("button", { type: "button", role: "tab", textContent: nombres[cual] });
    b.dataset.modo = cual;
    b.addEventListener("click", () => mostrar(cual));
    pestanas.append(b);
  }
  document.body.append(nodo);
  mostrar(modos[pestana] && (pestana !== "imagen" || e.imagen || e.marco) ? pestana : "ortofoto");
  cerrar.focus();
}

/* ====================== 5. Menú, buscador y dirección de la página ====================== */
let menu = null;
function cerrarMenu() { if (menu) { menu.remove(); menu = null; } }
function abrirMenuContextual(ev) {
  cerrarMenu();
  const ll = ev.latlng, zona = $("mapa-zona").getBoundingClientRect();
  menu = el("div", { id: "menu-mapa", role: "menu" }, el("div", { className: "coordenadas", textContent: `${ll.lat.toFixed(6)}, ${ll.lng.toFixed(6)}` }));
  const opcion = (texto, icono, hacer) => {
    const b = el("button", { type: "button", role: "menuitem" }, iconoSVG(icono, 18), el("span", { textContent: texto }));
    b.addEventListener("click", () => { cerrarMenu(); hacer(); });
    menu.append(b);
  };
  opcion("¿Qué hay aquí?", "info", () => abrirElemento(puntoDe(ll)));
  opcion("Añadir un marcador aquí", "marcador_nuevo", () => nuevoMarcador(ll));
  opcion("Ruta desde aquí", "ruta", () => rutaDesde(ll));
  opcion("Ruta hasta aquí", "ruta", () => rutaHasta(ll));
  opcion("Medir distancia desde aquí", "medir", () => medirDesde(ll));
  opcion("Ver a pie de calle", "panoramax", () => abrirVisor(puntoDe(ll), "calle"));
  opcion("Ortofotos de este punto por años", "historia", () => abrirVisor(puntoDe(ll), "ortofoto"));
  opcion("Copiar las coordenadas", "copiar", () => { if (navigator.clipboard) navigator.clipboard.writeText(`${ll.lat.toFixed(6)}, ${ll.lng.toFixed(6)}`).catch(() => {}); });
  opcion("Centrar el mapa aquí", "centrar", () => mapa.panTo(ll));
  $("mapa-zona").append(menu);
  const p = ev.containerPoint;
  menu.style.left = `${Math.max(6, Math.min(p.x, zona.width - menu.offsetWidth - 6))}px`;
  menu.style.top = `${Math.max(6, Math.min(p.y, zona.height - menu.offsetHeight - 6))}px`;
  menu.querySelector("button").focus({ preventScroll: true });
}
mapa.on("click movestart zoomstart", cerrarMenu);
document.addEventListener("keydown", (ev) => {
  if (visor) {
    // Con el visor abierto el teclado es suyo: los atajos de la ficha que queda debajo
    // (F, V, X, flechas) no deben actuar, y el tabulador no debe salirse de él.
    if (ev.key === "Escape") cerrarVisor();
    else if (ev.key === "Tab") {
      const focos = [...visor.nodo.querySelectorAll("button, a[href], iframe")].filter((n) => n.offsetParent !== null);
      const i = focos.indexOf(document.activeElement);
      const destino = ev.shiftKey ? (i <= 0 ? focos[focos.length - 1] : null) : i === -1 || i === focos.length - 1 ? focos[0] : null;
      if (destino) { ev.preventDefault(); destino.focus(); }
    }
    ev.stopPropagation();
    return;
  }
  if (ev.key !== "Escape") return;
  if (menu) cerrarMenu();
  else if (elementoAbierto && !/^(INPUT|SELECT|TEXTAREA)$/.test((document.activeElement || {}).tagName || "")) cerrarElemento();
}, true);

/* --- Buscador ---
   Mientras se escribe sale, por este orden: lo que se resuelve sin preguntar a nadie (coordenadas,
   «farmacias cerca de aquí», lo que ya hay cargado) y, un momento después, los sitios y direcciones
   que proponen los callejeros: Photon para negocios y lugares de todo el mundo y CartoCiudad para
   los portales de España. Con Intro, o al dejar de escribir, se pregunta además a Nominatim, que
   entiende frases enteras («mercadona ruzafa»). */
const CAPA_LUGAR = { id: "lugar", nombre: "Lugar", color: "#1a73e8", icono: "lugar" };
const capasBuscables = CAPAS.filter((c) => c.buscar && !c.oculta);
const metrosLegibles = (m) => (m < 950 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 9500 ? 1 : 0).replace(".", ",")} km`);
const desdeElCentro = (lat, lon) => metrosLegibles(mapa.distance(mapa.getCenter(), [lat, lon]));
/* La capa a la que pertenecería algo con estas etiquetas (para darle su símbolo y su nombre). */
const capaDeEtiquetas = (t) => CAPAS.find((c) => c.tipo === "osm" && !c.oculta && c.id !== "tiendas" && c.es(t)) || (t.shop ? CAPA.tiendas : null);

/* Lo último que se ha abierto desde el buscador, para tenerlo a mano. */
let recientes = leerLocal("osintmaps.recientes.v1", []);
if (!Array.isArray(recientes)) recientes = [];
function recordarReciente(e) {
  const ficha = { nombre: e.nombre, detalle: e.detalle || "", lat: e.lat, lon: e.lon, capa: e.capa, osm: e.osm || null };
  recientes = [ficha].concat(recientes.filter((r) => !(r.nombre === ficha.nombre && Math.abs(r.lat - ficha.lat) < 1e-4 && Math.abs(r.lon - ficha.lon) < 1e-4))).slice(0, 8);
  guardarLocal("osintmaps.recientes.v1", recientes);
}

/* De cada callejero, a una ficha común: { id, capa, lat, lon, nombre, detalle, osm, caja }. */
const TIPO_OSM = { N: "node", W: "way", R: "relation" };
function lugarDePhoton(f) {
  const p = f.properties || {}, [lon, lat] = (f.geometry || {}).coordinates || [];
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  const etiquetas = p.osm_key ? { [p.osm_key]: p.osm_value } : {}, capa = capaDeEtiquetas(etiquetas);
  const calle = [p.street, p.housenumber].filter(Boolean).join(" "), tipo = tipoDeEtiquetas(etiquetas) || (VALOR_POR_CLAVE.place[p.type] || "").replace(/^./, (x) => x.toUpperCase());
  const nombre = p.name || calle || p.city || p.county || "Lugar";
  const zona = [p.name ? calle : "", p.district || p.locality, p.city, p.city ? "" : p.county, p.countrycode && p.countrycode !== "ES" ? p.country : ""].filter(Boolean);
  const x = p.extent;      // [oeste, norte, este, sur]
  return { id: `lugar/${p.osm_type}${p.osm_id}`, capa: capa ? capa.id : "lugar", suelto: true, lat, lon, nombre, detalle: [tipo, ...new Set(zona)].filter(Boolean).join(" · "),
    osm: TIPO_OSM[p.osm_type] && p.osm_id ? `${TIPO_OSM[p.osm_type]}/${p.osm_id}` : null, caja: x && x.length === 4 ? [[x[3], x[0]], [x[1], x[2]]] : null,
    datos: [["Qué es", tipo], ["Dirección", [calle, p.postcode, p.city].filter(Boolean).join(", ")]] };
}
const TIPO_CARTO = { portal: "Portal", callejero: "Calle", municipio: "Municipio", poblacion: "Población", provincia: "Provincia", comunidad: "Comunidad autónoma", toponimo: "Paraje",
  carretera: "Carretera", ngbe: "Paraje", expendeduria: "Estanco", punto_recarga_electrica: "Punto de recarga", codpost: "Código postal", refcatastral: "Parcela catastral" };
const enMinusculas = (t) => String(t || "").toLowerCase().replace(/(^|[\s(\-/'’])([a-záéíóúñüàèòïç])/g, (m, a, b) => a + b.toUpperCase()).replace(/\b(De|Del|La|Las|El|Los|Y|I|D'|L')\b/g, (x) => x.toLowerCase()).replace(/^./, (x) => x.toUpperCase());
function lugarDeCarto(c) {
  const lat = +c.lat, lon = +c.lng;
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || (!lat && !lon)) return null;
  const nombre = enMinusculas(String(c.address || "").split(",")[0]) + (c.portalNumber && !/\d/.test(String(c.address).split(",")[0]) ? ` ${c.portalNumber}` : "");
  const grande = /^(municipio|poblacion|provincia|comunidad)$/.test(c.type);
  return { id: `lugar/carto-${c.id}`, capa: "lugar", suelto: true, lat, lon, nombre, detalle: [TIPO_CARTO[c.type] || "", c.muni && !grande ? c.muni : "", c.province && c.province !== c.muni ? c.province : ""].filter(Boolean).join(" · "),
    caja: grande ? [[lat - 0.03, lon - 0.04], [lat + 0.03, lon + 0.04]] : null, datos: [["Qué es", TIPO_CARTO[c.type]], ["Municipio", c.muni], ["Provincia", c.province], ["Código postal", c.postalCode]] };
}
function lugarDeNominatim(l) {
  const lat = +l.lat, lon = +l.lon, caja = l.boundingbox && l.boundingbox.map(Number);
  const etiquetas = l.category ? { [l.category]: l.type } : {}, capa = capaDeEtiquetas(etiquetas);
  return { id: `lugar/${l.osm_type}${l.osm_id}`, capa: capa ? capa.id : "lugar", suelto: true, lat, lon, nombre: l.name || l.display_name.split(",")[0],
    detalle: [tipoDeEtiquetas(etiquetas), l.display_name.split(",").slice(1, 4).map((x) => x.trim()).join(", ")].filter(Boolean).join(" · "),
    osm: /^(node|way|relation)$/.test(l.osm_type) ? `${l.osm_type}/${l.osm_id}` : null, caja: caja ? [[caja[0], caja[2]], [caja[1], caja[3]]] : null, datos: [["Dirección", l.display_name]] };
}
/* Dos callejeros dan a menudo el mismo sitio: se queda el primero. */
function sinRepetidos(lugares) {
  const salida = [];
  for (const l of lugares) {
    if (!l) continue;
    // (mismo nombre, mismo tipo de cosa y al lado: una estación de tren y la de bicis de su puerta se llaman igual y no son lo mismo)
    if (!salida.some((o) => (l.osm && o.osm === l.osm) || (sinAcentos(o.nombre) === sinAcentos(l.nombre) && o.capa === l.capa && mapa.distance([o.lat, o.lon], [l.lat, l.lon]) < 150))) salida.push(l);
  }
  return salida;
}
const pedirPhoton = (texto, tope = 7) => {
  const c = mapa.getCenter();
  return pedirJ(`https://photon.komoot.io/api/?${new URLSearchParams({ q: texto, lat: c.lat.toFixed(4), lon: c.lng.toFixed(4), zoom: String(Math.round(Math.min(16, Math.max(6, mapa.getZoom())))),
    location_bias_scale: "0.4", limit: String(tope), lang: "default" })}`, null, 12000).then((j) => (j.features || []).map(lugarDePhoton));
};
const pedirCarto = (texto, tope = 4) => pedirJ(`https://www.cartociudad.es/geocoder/api/geocoder/candidates?${new URLSearchParams({ q: texto, limit: String(tope) })}`, null, 12000)
  .then((lista) => (Array.isArray(lista) ? lista : []).map(lugarDeCarto));
const pedirNominatim = (texto, tope = 6) => {
  const b = mapa.getBounds();
  return pedirJ(`https://nominatim.openstreetmap.org/search?${new URLSearchParams({ format: "jsonv2", limit: String(tope), "accept-language": "es", q: texto,
    viewbox: `${b.getWest()},${b.getNorth()},${b.getEast()},${b.getSouth()}` })}`, null, 15000).then((lugares) => lugares.map(lugarDeNominatim));
};
/* Los callejeros de escribir (rápidos), juntos. Con número o con varias palabras merece la pena preguntar por portales. */
function sugerirLugares(texto) {
  const conPortal = /\d/.test(texto) || texto.trim().split(/\s+/).length > 1;
  return Promise.all([pedirPhoton(texto).catch(() => []), conPortal ? pedirCarto(texto).catch(() => []) : []])
    .then(([photon, carto]) => sinRepetidos(/\d/.test(texto) ? carto.concat(photon) : photon.concat(carto)));
}

/* Lo que está cerca de lo que se mira (a menos de 30 km), delante; dentro de cada grupo se respeta el orden
   en que lo dio el callejero. Así «estación del norte» no empieza por la de otra ciudad. */
function cercaPrimero(lista) {
  const centro = mapa.getCenter(), lejos = (l) => mapa.distance(centro, [l.lat, l.lon]) > 30000;
  return lista.filter((l) => !lejos(l)).concat(lista.filter(lejos));
}
/* Abre un lugar del buscador: si es grande (una ciudad, un barrio) se encuadra; si no, se va a él. */
function irALugar(e) {
  recordarReciente(e);
  const grande = e.caja && (Math.abs(e.caja[1][0] - e.caja[0][0]) > 0.004 || Math.abs(e.caja[1][1] - e.caja[0][1]) > 0.004);
  if (grande) mapa.fitBounds(e.caja, { maxZoom: 17 });
  abrirElemento(e, !grande);
}
const filaDeLugar = (e) => {
  const capa = capaDe(e);
  return { color: capa.color, icono: capa.icono || capa.id, forma: capa.forma, titulo: e.nombre, detalle: e.detalle, derecha: desdeElCentro(e.lat, e.lon), ir: () => irALugar(e) };
};

/* --- «Farmacias cerca de aquí»: lo más próximo al centro del mapa de una capa --- */
const grupoCerca = L.layerGroup().addTo(mapa);
let busquedaCerca = null;      // { capa, centro, elementos }
function quitarBusquedaCerca() { busquedaCerca = null; grupoCerca.clearLayers(); }
/* Lo más cercano de una capa de OpenStreetMap se pregunta a dos sitios a la vez. Photon contesta en
   décimas de segundo, pero solo con el nombre y la dirección; Overpass trae todas las etiquetas (el
   horario, para decir «abierto» o «cerrado») y a ratos tarda medio minuto. Se enseña lo primero que
   llega y, si después llega lo completo, se cambia por ello. */
function cercaPorPhoton(capa, centro, radio) {
  const filtros = [];
  for (const condicion of capa.condiciones || []) {
    const pares = Object.entries(condicion);
    if (pares.length !== 1) return null;      // «esto y además aquello» no se le puede pedir
    const [clave, valor] = pares[0];
    if (valor === true) filtros.push(clave); else if (valor[0] === "~") return null; else for (const v of valor.split("|")) filtros.push(`${clave}:${v}`);
  }
  if (!filtros.length || filtros.length > 24) return null;
  const consulta = new URLSearchParams({ lat: centro.lat.toFixed(5), lon: centro.lng.toFixed(5), radius: Math.max(1, radio / 1000).toFixed(1), limit: "50" });
  for (const f of filtros) consulta.append("osm_tag", f);
  return pedirJ(`https://photon.komoot.io/reverse?${consulta}`, null, 12000).then((j) => (j.features || []).map((f) => {
    const l = lugarDePhoton(f);
    return l && Object.assign(l, { id: l.osm || l.id, suelto: false, nombre: (f.properties || {}).name || tipoDeEtiquetas({ [f.properties.osm_key]: f.properties.osm_value }) || capa.uno });
  }).filter(Boolean));
}
function buscarCerca(capa, radioPedido) {
  const centro = mapa.getCenter(), turno = ++turnoBusqueda;
  const radio = radioPedido || Math.round(Math.min(6000, Math.max(900, mapa.distance(centro, mapa.getBounds().getNorthEast()) * 1.1)));
  quitarBusquedaCerca();
  if (seleccion || panelOcupado()) { soltarMarcador(); mostrarLista(); }
  $("buscar-texto").value = corto(capa);
  desplegarPanel();
  pintarResultados([[`${capa.nombre}: buscando lo más cercano…`, []]], true);
  let encuadrado = false;
  const mostrar = (elementos, completo) => {
    if (turno !== turnoBusqueda) return;
    const lista = elementos.map((e) => Object.assign(e, { capa: capa.id, lejos: mapa.distance(centro, [e.lat, e.lon]) })).sort((a, b) => a.lejos - b.lejos).slice(0, 60);
    grupoCerca.clearLayers();
    busquedaCerca = { capa, centro, radio, elementos: lista, completo };
    if (capa.tipo === "osm" || capa.tipo === "api") for (const e of lista) dibujar(capa, e).addTo(grupoCerca);
    if (lista.length && !encuadrado) { encuadrado = true; mapa.fitBounds(L.latLngBounds(lista.slice(0, 8).map((e) => [e.lat, e.lon])).extend(centro).pad(0.2), { maxZoom: 17 }); }
    if (!$("ficha-elemento").hidden || panelOcupado()) return;      // (se está mirando ya la ficha de uno: la lista se repinta al volver)
    pintarBusquedaCerca();
  };
  const sinNada = () => {
    if (turno !== turnoBusqueda) return;
    // Si cerca no hay nada, se prueba una vez más lejos antes de decir que no hay.
    if (capa.tipo !== "vivo" && capa.tipo !== "fija" && radio < 20000) buscarCerca(capa, Math.min(25000, radio * 4)); else mostrar([], true);
  };
  const fallo = () => { if (turno === turnoBusqueda && !busquedaCerca) pintarResultados([[`${capa.nombre}: el servicio no ha respondido. Prueba otra vez en un momento.`, []]], true); };
  if (capa.tipo === "osm") {
    const rapido = cercaPorPhoton(capa, centro, radio);
    let hayRapido = false, acabados = 0;
    const completo = overpass(`[out:json][timeout:25];(${capa.ql.map((q) => `${q}(around:${radio},${centro.lat.toFixed(5)},${centro.lng.toFixed(5)});`).join("")});out center tags qt 300;`, null, true)
      .then((j) => (j.elements || []).filter((x) => capa.es(x.tags || {})).map((x) => elementoOSM(x, capa)).filter(Boolean));
    let llegoCompleto = false;
    if (rapido) rapido.then((lista) => { acabados++; if (!llegoCompleto && lista.length) { hayRapido = true; mostrar(lista, false); } }, () => { acabados++; });
    completo.then((lista) => { llegoCompleto = true; if (lista.length) mostrar(lista, true); else if (!hayRapido) sinNada(); else if (busquedaCerca) busquedaCerca.completo = true; },
      () => { if (!hayRapido) { if (rapido) rapido.then((lista) => { if (!lista.length) fallo(); }, fallo); else fallo(); } });
    return;
  }
  let pedido;
  if (capa.tipo === "api") {
    const dLat = radio / 111320, dLon = dLat / Math.cos((centro.lat * Math.PI) / 180);
    pedido = capa.pedir({ s: centro.lat - dLat, n: centro.lat + dLat, o: centro.lng - dLon, e: centro.lng + dLon });
  } else {      // lo que va «en vivo» o ya está descargado: se enciende la capa y se lista lo que trae
    if (!capasActivas.has(capa.id)) { const casilla = $(`dato-${capa.id}`); casilla.checked = true; conmutarCapa(capa, true); }
    pedido = (capa.tipo === "vivo" ? capa.pedir() : Promise.resolve([...estado[capa.id].elementos.values()]));
  }
  pedido.then((elementos) => (elementos.length ? mostrar(elementos, true) : sinNada()), fallo);
}
function pintarBusquedaCerca() {
  const { capa, elementos, radio } = busquedaCerca;
  const filas = elementos.map((e) => {
    const h = e.etiquetas && e.etiquetas.opening_hours ? horarioOSM(e.etiquetas.opening_hours) : null;
    return { color: e.color || capa.color, icono: capa.icono || capa.id, forma: capa.forma, titulo: e.nombre, derecha: metrosLegibles(e.lejos),
      detalle: [h ? (h.siempre ? "Abierto las 24 horas" : (h.abierto ? "Abierto" : "Cerrado") + (h.cambio ? `, ${h.cambio}` : "")) : "", e.etiquetas ? [e.etiquetas["addr:street"], e.etiquetas["addr:housenumber"]].filter(Boolean).join(" ") : (e.detalle || "").split(" · ").slice(1, 3).join(" · ")].filter(Boolean).join(" · "),
      clase: h ? (h.abierto ? "abierto" : "cerrado") : "", ir: () => abrirElemento(e, true) };
  });
  pintarResultados([[elementos.length ? `${capa.nombre}: ${elementos.length === 60 ? "los 60 más cercanos" : `${elementos.length} a menos de ${metrosLegibles(radio)}`}` : `${capa.nombre}: no hay ninguno a menos de ${metrosLegibles(radio)}`, filas]], true);
  const lista = $("resultados-extra"), acciones = el("li", { className: "acciones" });
  const aqui = el("button", { type: "button", textContent: "Buscar en esta zona" }), dejar = el("button", { type: "button", textContent: capasActivas.has(capa.id) ? "La capa está encendida" : "Dejar la capa encendida" }),
    quitar = el("button", { type: "button", textContent: "Quitar" });
  aqui.addEventListener("click", () => buscarCerca(capa));
  dejar.disabled = capasActivas.has(capa.id);
  dejar.addEventListener("click", () => { $(`dato-${capa.id}`).checked = true; conmutarCapa(capa, true); dejar.disabled = true; dejar.textContent = "La capa está encendida"; });
  quitar.addEventListener("click", limpiarBuscador);
  acciones.append(aqui, dejar, quitar);
  lista.insertBefore(acciones, lista.children[1] || null);
}
function limpiarBuscador() {
  turnoBusqueda++;
  quitarBusquedaCerca();
  $("buscar-texto").value = "";
  if (document.activeElement === $("buscar-texto")) pintarSugerencias(); else pintarResultados([]);
  if (candidatos.length && !seleccion && !panelOcupado()) filtrar();
}

/* --- La lista de resultados --- */
let relojBusqueda = null, relojCallejero = null, turnoBusqueda = 0, ultimosLugares = { texto: "", lista: [] };
function pintarResultados(grupos, conVacios) {
  const lista = $("resultados-extra");
  lista.replaceChildren();
  for (const [titulo, filas, clase] of grupos) {
    if (!filas.length && !conVacios && !clase) continue;
    lista.append(el("li", { className: `rotulo ${clase || ""}`.trim(), textContent: titulo }));
    for (const f of filas) {
      const b = el("button", { type: "button", className: f.clase || "" }, f.icono === "reciente" || f.icono === "buscar" ? iconoSVG(f.icono, 20) : simboloSVG(f.icono || "punto", f.color, f.forma, 22),
        el("b", { textContent: f.titulo }), el("em", { textContent: f.derecha || "" }), el("small", { textContent: f.detalle || "" }));
      // (se suelta el campo de búsqueda: en el móvil eso recoge el teclado y deja que la hoja baje a media altura)
      b.addEventListener("click", () => { clearTimeout(temporizadorBusqueda); $("buscar-texto").blur(); f.ir(); });
      lista.append(el("li", {}, b));
    }
  }
  lista.hidden = !lista.children.length;
  $("panel").classList.toggle("con-resultados", !lista.hidden);
}
/* Con el buscador vacío: lo último abierto y las categorías de «cerca de aquí». */
const CATEGORIAS_RAPIDAS = { restaurantes: "Restaurantes", bares: "Bares", cafes: "Cafeterías", supermercados: "Súper", farmacias: "Farmacias", gasolineras: "Gasolineras", bancos: "Cajeros",
  aparcamientos: "Parking", paradas: "Paradas", hoteles: "Hoteles", salud: "Hospitales", aseos: "Aseos", fuentes: "Fuentes", recarga: "Recarga", pintura: "Pintura", bicis: "Bicis" };
function pintarSugerencias() {
  if (busquedaCerca) { pintarBusquedaCerca(); return; }
  const filas = recientes.map((r) => {
    const e = Object.assign({ id: `lugar/reciente-${r.lat},${r.lon}`, suelto: true, datos: [] }, r), capa = capaDe(e);
    return { color: capa.color, icono: "reciente", titulo: r.nombre, detalle: r.detalle, derecha: desdeElCentro(r.lat, r.lon), ir: () => irALugar(e) };
  });
  pintarResultados([["Lo último que has abierto", filas]]);
  const lista = $("resultados-extra"), rejilla = el("li", { className: "categorias" });
  for (const [id, rotulo] of Object.entries(CATEGORIAS_RAPIDAS)) {
    const capa = CAPA[id], b = el("button", { type: "button", title: `${capa.nombre} cerca del centro del mapa` }, simboloDe(capa, null, 26), el("span", { textContent: rotulo }));
    b.addEventListener("click", () => { $("buscar-texto").blur(); buscarCerca(capa); });
    rejilla.append(b);
  }
  lista.prepend(el("li", { className: "rotulo", textContent: "Buscar cerca de aquí" }), rejilla);
  lista.hidden = false;
  $("panel").classList.add("con-resultados");
}
function categoriasDe(q) {
  const palabras = q.split(/\s+/).filter((p) => p.length >= 3);
  if (!palabras.length) return [];
  return capasBuscables.filter((c) => { const claves = c.buscar.split(" "); return palabras.every((p) => claves.some((k) => k.startsWith(p)) || sinAcentos(corto(c)).startsWith(p)); }).slice(0, 3);
}
function buscarTodo(texto, conNominatim) {
  const turno = ++turnoBusqueda, q = sinAcentos(texto.trim());
  clearTimeout(relojCallejero);
  if (busquedaCerca) quitarBusquedaCerca();
  if (!q) { if (document.activeElement === $("buscar-texto")) pintarSugerencias(); else pintarResultados([]); return; }
  if (q.length < 2) { pintarResultados([]); return; }
  const yaVistos = ultimosLugares.texto === q ? ultimosLugares.lista : [];
  const directos = [], enCapas = [], lugares = { lista: yaVistos, estado: q.length >= 3 && !yaVistos.length ? "buscando" : "" };
  const coords = /^(-?\d{1,2}(?:[.,]\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:[.,]\d+)?)$/.exec(texto.trim());
  if (coords) {
    const lat = +coords[1].replace(",", "."), lon = +coords[2].replace(",", ".");
    if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) directos.push({ color: "#17242e", titulo: `${lat}, ${lon}`, detalle: "Ir a estas coordenadas", ir: () => abrirElemento(puntoDe(L.latLng(lat, lon)), true) });
  }
  const refcat = /^[0-9A-Z]{14}(?:[0-9A-Z]{6})?$/.test(texto.trim().toUpperCase()) && /\d/.test(texto) && /[A-Za-z]/.test(texto) ? texto.trim().toUpperCase().slice(0, 14) : null;
  const cerca = coords || refcat ? [] : categoriasDe(q).map((capa) => ({ color: capa.color, icono: capa.icono || capa.id, forma: capa.forma, titulo: `${corto(capa)} cerca de aquí`,
    detalle: "Lo más próximo al centro del mapa", ir: () => buscarCerca(capa) }));
  // (la lista de sitios abandonados ya se ha filtrado con este mismo texto: aquí solo se dice cuántos quedan)
  if (candidatos.length && visibles.length && visibles.length < candidatos.length && q.length >= 3) enCapas.push({ color: "#e5007d", icono: "sitio", forma: "cuadrado",
    titulo: `${miles(visibles.length)} ${visibles.length === 1 ? "sitio abandonado coincide" : "sitios abandonados coinciden"}`, detalle: "Verlos en la lista y encuadrarlos en el mapa", ir: () => { turnoBusqueda++; pintarResultados([]); if (typeof ponerPestana === "function") ponerPestana("sitios"); encuadrarResultados(); } });
  for (const [id, m] of Object.entries(marcadores)) {
    if (!m.deleted && sinAcentos(m.note).includes(q)) enCapas.push({ color: TIPOS_MARCADOR[m.type][1], icono: ICONO_MARCADOR[m.type], titulo: m.note.slice(0, 70), detalle: `Marcador: ${TIPOS_MARCADOR[m.type][0].toLowerCase()}`, ir: () => { mapa.setView([m.lat, m.lng], Math.max(mapa.getZoom(), 17)); abrirMarcador(id); } });
  }
  if ($("capa-camaras").checked && q.length >= 3) {
    // Las cámaras no tienen nombre: se buscan por lo que se sabe de ellas (tipo, zona, operador)
    // y salen las más cercanas al centro del mapa.
    const centro = mapa.getCenter();
    [...camaras.values()].map((c) => [c, filasCamara(c).map((f) => f[1]).join(", ")]).filter(([, texto]) => sinAcentos(texto).includes(q))
      .sort((a, b) => mapa.distance(centro, [a[0].lat, a[0].lon]) - mapa.distance(centro, [b[0].lat, b[0].lon])).slice(0, 4)
      .forEach(([c, texto]) => enCapas.push({ color: CAPA.camaras.color, icono: "camaras", titulo: texto, detalle: "Cámara de vigilancia (OpenStreetMap)", ir: () => abrirElemento(elementoDeCamara(c), true) }));
  }
  for (const capa of q.length >= 3 ? CAPAS : []) {
    if (enCapas.length >= 10) break;
    for (const e of estado[capa.id].elementos.values()) {
      if (enCapas.length >= 10) break;
      if (e.nombre && sinAcentos(e.nombre).includes(q)) enCapas.push({ color: e.color || capa.color, icono: capa.icono || capa.id, forma: capa.forma, titulo: e.nombre, detalle: capa.nombre, derecha: desdeElCentro(e.lat, e.lon), ir: () => abrirElemento(e, true) });
    }
  }
  const pintar = () => pintarResultados([["Ir a", directos], ["Cerca de aquí", cerca],
    [lugares.estado === "buscando" ? "Buscando lugares y direcciones…" : lugares.estado === "nada" && !cerca.length && !enCapas.length && !directos.length ? "No se ha encontrado ningún lugar con ese nombre" : "Lugares y direcciones",
      cercaPrimero(lugares.lista).slice(0, 9).map(filaDeLugar), lugares.estado === "buscando" || (lugares.estado === "nada" && !cerca.length && !enCapas.length && !directos.length) ? "aviso" : ""],
    ["En tus datos y en las capas encendidas", enCapas]]);
  pintar();
  if (refcat) {
    pedirJ(`https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_CPMRC?RefCat=${refcat}&SRS=EPSG:4326`, null, 15000).then((j) => {
      const c = (((j.Consulta_CPMRCResult || {}).coordenadas || {}).coord || [])[0];
      if (turno !== turnoBusqueda || !c || !c.geo) return;
      directos.push({ color: "#17242e", titulo: `Parcela ${refcat}`, detalle: c.ldt || "Referencia catastral", ir: () => abrirElemento(puntoDe(L.latLng(+c.geo.ycen, +c.geo.xcen), `Parcela ${refcat}`), true) });
      pintar();
    }).catch(() => {});
  }
  if (coords || refcat || q.length < 3) { lugares.estado = ""; pintar(); return; }
  // Los callejeros, un momento después de la última tecla; Nominatim, solo al parar o con Intro.
  const preguntar = () => {
    let quedan = conNominatim ? 2 : 1;
    const llega = (lista) => {
      if (turno !== turnoBusqueda) return;
      lugares.lista = sinRepetidos(lugares.lista.concat(lista));
      ultimosLugares = { texto: q, lista: lugares.lista };
      if (--quedan === 0) lugares.estado = lugares.lista.length ? "" : conNominatim ? "nada" : "buscando";
      else if (lugares.lista.length) lugares.estado = "";
      pintar();
    };
    sugerirLugares(texto.trim()).then(llega, () => llega([]));
    if (conNominatim) pedirNominatim(texto.trim()).then(llega, () => llega([]));
  };
  if (conNominatim) preguntar(); else relojCallejero = setTimeout(preguntar, 280);
}
{
  const campo = $("buscar-texto");
  campo.addEventListener("input", (ev) => {
    if (seleccion || panelOcupado()) { soltarMarcador(); mostrarLista(); if (candidatos.length) filtrar(); }
    clearTimeout(relojBusqueda);
    const texto = ev.target.value;
    buscarTodo(texto, false);
    if (texto.trim().length >= 3) relojBusqueda = setTimeout(() => { if (campo.value === texto) buscarTodo(texto, true); }, 1100);      // la pregunta larga, solo cuando se deja de escribir
  });
  // Al entrar en el campo vacío se ofrecen las búsquedas rápidas (y se deja la ficha que hubiera abierta).
  campo.addEventListener("focus", () => {
    if (campo.value.trim() && !busquedaCerca) return;
    if (seleccion || panelOcupado()) { soltarMarcador(); mostrarLista(); if (candidatos.length) filtrar(); }
    pintarSugerencias();
  });
  // Al salir sin haber buscado nada, se recogen. (Se espera un momento: el clic en una sugerencia también saca el foco del campo.)
  let tocandoLista = false;
  $("resultados-extra").addEventListener("pointerdown", () => { tocandoLista = true; setTimeout(() => { tocandoLista = false; }, 600); });
  const recoger = (otraVez) => {
    if (campo.value.trim() || busquedaCerca || document.activeElement === campo || $("resultados-extra").contains(document.activeElement)) return;
    if (tocandoLista) { if (otraVez) setTimeout(() => recoger(false), 700); return; }
    pintarResultados([]);
  };
  campo.addEventListener("blur", () => setTimeout(() => recoger(true), 250));
  campo.addEventListener("search", () => { if (!campo.value) limpiarBuscador(); });      // la «x» del campo
  campo.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { clearTimeout(relojBusqueda); if (campo.value.trim()) buscarTodo(campo.value, true); }
    else if (ev.key === "ArrowDown") { const primero = $("resultados-extra").querySelector("button"); if (primero) { ev.preventDefault(); primero.focus(); } }
    else if (ev.key === "Escape") { ev.stopPropagation(); if (campo.value) limpiarBuscador(); else { campo.blur(); pintarResultados([]); } }
  });
  // Con las flechas se recorre la lista de resultados; hacia arriba desde el primero se vuelve al campo.
  $("resultados-extra").addEventListener("keydown", (ev) => {
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    const botones = [...$("resultados-extra").querySelectorAll("button")], i = botones.indexOf(document.activeElement);
    if (i < 0) return;
    ev.preventDefault();
    (ev.key === "ArrowDown" ? botones[Math.min(botones.length - 1, i + 1)] : i === 0 ? campo : botones[i - 1]).focus();
  });
}

/* --- La dirección de la página recuerda dónde se está mirando --- */
mapa.on("moveend", () => {      // la lectura, al arrancar, está en index.html (vistaDeLaURL)
  const c = mapa.getCenter();
  try { history.replaceState(null, "", `#mapa=${mapa.getZoom()}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`); } catch { /* en un fichero suelto puede no dejar */ }
});
pintarEstadoCapas();

/* Las fichas de los sitios abandonados y de los marcadores propios también
   llevan los botones del visor: se añaden al abrirlas. */
function filaDeVistas(e) {
  const fila = el("div", { className: "vistas" });
  const boton = (texto, icono, hacer) => {
    const b = el("button", { type: "button" }, iconoSVG(icono, 20), el("span", { textContent: texto }));
    b.addEventListener("click", hacer);
    fila.append(b);
  };
  for (const [texto, icono, pestana] of [["Por años", "historia", "ortofoto"], ["Calle", "panoramax", "calle"], ["Fotos", "fotos", "fotos"], ["Satélite", "satelite", "satelite"]]) boton(texto, icono, () => abrirVisor(e, pestana));
  const llegar = el("button", { type: "button", className: "como-llegar" }, iconoSVG("ruta", 20), el("span", { textContent: "Cómo llegar" }));
  llegar.addEventListener("click", () => rutaHasta(L.latLng(e.lat, e.lon), e.nombre));
  return el("div", { className: "acciones-ficha" }, llegar, fila);
}
{
  const fichaOriginal = abrirFicha, marcadorOriginal = abrirMarcador;
  abrirFicha = function (c, mover) {
    fichaOriginal(c, mover);
    const ancla = $("ficha").querySelector(".lugar");
    if (ancla && seleccion === c) ancla.after(filaDeVistas({ lat: c.lat, lon: c.lon, nombre: tituloDe(c), superficie: c.p.superficie_m2 }));
  };
  abrirMarcador = function (id) {
    marcadorOriginal(id);
    const m = marcadores[id], ancla = $("ficha-marcador").querySelector(".lugar");
    if (m && ancla && marcadorAbierto === id && !$("ficha-marcador").querySelector(".vistas")) ancla.after(filaDeVistas({ lat: m.lat, lon: m.lng, nombre: m.note || "Marcador" }));
  };
}
