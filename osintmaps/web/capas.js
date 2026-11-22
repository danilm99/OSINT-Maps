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
const wmts = (base, capa, formato) =>
  `${base}?layer=${capa}&style=default&tilematrixset=GoogleMapsCompatible&Service=WMTS&Request=GetTile&Version=1.0.0` +
  `&Format=image/${formato}&TileMatrix={z}&TileCol={x}&TileRow={y}`;

const FONDOS_NUEVOS = {
  esri: ["Satélite (Esri, otra fecha)", L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 20, maxNativeZoom: 19, attribution: "Esri, Maxar, Earthstar Geographics" })],
  s2: ["Satélite Sentinel-2 sin nubes (2023, 10 m)", L.tileLayer("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg",
    { maxZoom: 20, maxNativeZoom: 14, attribution: "Sentinel-2 cloudless 2023, EOX (datos Copernicus)" })],
  base: ["Callejero (IGN)", L.tileLayer(wmts("https://www.ign.es/wmts/ign-base", "IGNBaseTodo", "jpeg"), { maxZoom: 20, maxNativeZoom: 18, attribution: "IGN CC BY 4.0 ign.es" })],
  lidar: ["Relieve LiDAR: edificios y arbolado", L.tileLayer(wmts("https://wmts-mapa-lidar.idee.es/lidar", "EL.GridCoverageDSM", "png"), { maxZoom: 20, maxNativeZoom: 17, attribution: "LiDAR-PNOA CC BY 4.0 scne.es" })],
  relieve: ["Relieve del terreno", L.tileLayer(wmts("https://servicios.idee.es/wmts/mdt", "Relieve", "jpeg"), { maxZoom: 20, maxNativeZoom: 15, attribution: "IGN CC BY 4.0 ign.es" })],
  mtn50: ["Mapa de 1915-1960 (MTN50, 1.ª edición)", L.tileLayer(wmts("https://www.ign.es/wmts/primera-edicion-mtn", "mtn50-edicion1", "jpeg"), { maxZoom: 20, maxNativeZoom: 15, attribution: "IGN CC BY 4.0 ign.es" })],
  catastrones: ["Minutas de 1870-1950 (catastrones)", L.tileLayer(wmts("https://www.ign.es/wmts/primera-edicion-mtn", "catastrones", "jpeg"), { maxZoom: 20, maxNativeZoom: 15, attribution: "IGN CC BY 4.0 ign.es" })],
};
for (const [id, [nombre, capa]] of Object.entries(FONDOS_NUEVOS)) {
  fondos[id] = capa;
  $("capa-fondo").append(el("option", { value: id, textContent: nombre }));
}

mapa.createPane("superpuesto").style.zIndex = 260;
mapa.getPane("superpuesto").style.pointerEvents = "none";
const SUPERPUESTAS = {
  rotulos: ["Calles y nombres sobre la foto", L.tileLayer(wmts("https://www.ign.es/wmts/ign-base", "IGNBaseOrto", "png"), { pane: "superpuesto", maxZoom: 20, maxNativeZoom: 18, crossOrigin: "anonymous" })],
  tren: ["Red ferroviaria (OpenRailwayMap)", L.tileLayer("https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png", { pane: "superpuesto", maxZoom: 20, maxNativeZoom: 19, attribution: "OpenRailwayMap CC BY-SA" })],
  antiguo: ["Mapa de 1915-1960, translúcido", L.tileLayer(wmts("https://www.ign.es/wmts/primera-edicion-mtn", "mtn50-edicion1", "jpeg"), { pane: "superpuesto", opacity: 0.6, maxZoom: 20, maxNativeZoom: 15 })],
  sombras: ["Relieve LiDAR, translúcido", L.tileLayer(wmts("https://wmts-mapa-lidar.idee.es/lidar", "EL.GridCoverageDSM", "png"), { pane: "superpuesto", opacity: 0.55, maxZoom: 20, maxNativeZoom: 17 })],
};
// El servicio del IGN devuelve de vez en cuando una tesela entera de un solo color (un azul liso): se oculta.
SUPERPUESTAS.rotulos[1].on("tileload", (ev) => { if (esImagenLisa(ev.tile)) ev.tile.style.visibility = "hidden"; });
{
  const guardadas = leerLocal("osintmaps.superpuestas.v1", ["rotulos"]) || [];
  const recordar = () => guardarLocal("osintmaps.superpuestas.v1", Object.keys(SUPERPUESTAS).filter((id) => $(`sup-${id}`).checked));
  for (const [id, [nombre, capa]] of Object.entries(SUPERPUESTAS)) {
    const casilla = el("input", { id: `sup-${id}`, type: "checkbox", checked: guardadas.includes(id) });
    casilla.addEventListener("change", () => { casilla.checked ? capa.addTo(mapa) : mapa.removeLayer(capa); recordar(); });
    if (casilla.checked) capa.addTo(mapa);
    $("capas-superponer").append(el("label", { className: "casilla" }, casilla, " " + nombre));
  }
  const fondoGuardado = leerLocal("osintmaps.fondo.v1", "pnoa");
  if (fondos[fondoGuardado] && fondoGuardado !== "pnoa") { $("capa-fondo").value = fondoGuardado; $("capa-fondo").dispatchEvent(new Event("change")); }
  $("capa-fondo").addEventListener("change", (e) => guardarLocal("osintmaps.fondo.v1", e.target.value));
}

/* ====================== 2. Capas de datos ====================== */
const VALENCIA = "https://geoportal.valencia.es/server/rest/services/OPENDATA";
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

/* Consulta a Overpass (la base de datos de OpenStreetMap): de una en una y
   probando otro servidor si el primero no contesta. */
function overpass(consulta) {
  const intento = (k) => pedirJ(OVERPASS[k], { method: "POST", body: new URLSearchParams({ data: consulta }) }, ESPERA_OSM)
    .catch((err) => (k + 1 < OVERPASS.length ? intento(k + 1) : Promise.reject(err)));
  return new Promise((resolver, rechazar) => encolarOSM(() => intento(0).then(resolver, rechazar)));
}

/* Nombres en castellano de las etiquetas de OSM que más salen. */
const ETIQUETA_OSM = {
  name: "Nombre", operator: "Operador", owner: "Propietario", "addr:street": "Calle", "addr:housenumber": "Número", "addr:city": "Localidad",
  start_date: "Desde", end_date: "Hasta", height: "Altura (m)", "building:levels": "Plantas", access: "Acceso", description: "Descripción",
  website: "Web", wikipedia: "Wikipedia", wikidata: "Wikidata", ref: "Referencia", voltage: "Tensión (V)", "tower:type": "Tipo de torre",
  railway: "Ferrocarril", power: "Energía", man_made: "Construcción", military: "Militar", historic: "Histórico", barrier: "Barrera",
  bridge: "Puente", tunnel: "Túnel", landuse: "Uso del suelo", building: "Edificio", abandoned: "Abandonado", disused: "En desuso",
  ruins: "Ruinas", heritage: "Protección", opening_hours: "Horario", lit: "Iluminado", surface: "Firme", material: "Material",
  "lamp_type": "Tipo de lámpara", "light:colour": "Color de la luz", electrified: "Electrificado", gauge: "Ancho de vía (mm)", usage: "Uso", service: "Servicio",
};
const VALOR_OSM = {
  yes: "sí", no: "no", private: "privado", permissive: "tolerado", customers: "clientes", rail: "vía en servicio", disused: "en desuso",
  abandoned: "abandonado", razed: "desmantelado", station: "estación", halt: "apeadero", yard: "playa de vías", siding: "apartadero",
  substation: "subestación", plant: "central", generator: "generador", transformer: "transformador", tower: "torre", mast: "mástil",
  line: "línea", minor_line: "línea menor", wall: "muro", retaining_wall: "muro de contención", noise_barrier: "pantalla acústica",
  city_wall: "muralla", fence: "valla", bunker: "búnker", barracks: "cuartel", ruins: "ruinas", works: "fábrica", chimney: "chimenea",
  silo: "silo", storage_tank: "depósito", water_tower: "depósito elevado", quarry: "cantera", mineshaft: "pozo de mina", adit: "bocamina",
  viaduct: "viaducto", aqueduct: "acueducto", police: "policía", communications_tower: "torre de comunicaciones", industrial: "industrial",
  castle: "castillo", fort: "fuerte", monument: "monumento", memorial: "memorial", archaeological_site: "yacimiento", church: "iglesia",
  farm: "masía o granja", manor: "casa señorial", mine: "mina", tram: "tranvía", subway: "metro", light_rail: "metro ligero", narrow_gauge: "vía estrecha",
};
const valorOSM = (v) => VALOR_OSM[v] || String(v).replace(/_/g, " ");
const tituloOSM = (t, ...claves) => { for (const c of claves) if (t[c]) return valorOSM(t[c]).replace(/^./, (x) => x.toUpperCase()); return ""; };

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
  // --- Abandono y patrimonio ---
  { id: "listaroja", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Lista Roja del Patrimonio", color: "#b3001b", zoom: 0, tipo: "fija",
    color_de: (p) => ({ verde: "#2f9e44", negra: "#111111" }[p.lista] || "#b3001b"),
    filas: (e) => [["Lista", { roja: "Roja: en riesgo de perderse", verde: "Verde: estaba en la Roja y se ha recuperado", negra: "Negra: se ha perdido" }[e.p.lista]], ["Resumen", e.p.resumen]] },
  { id: "subastas", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Inmuebles en subasta (BOE)", color: "#7b2ff7", zoom: 0, tipo: "fija",
    filas: (e) => [["Dirección", e.p.direccion], ["Localidad", e.p.localidad], ["Termina", e.p.fin], ["Valor de subasta", e.p.valor_subasta], ["Tasación", e.p.tasacion],
      ["Puja mínima", e.p.puja_minima], ["Depósito", e.p.deposito], ["Situación posesoria", e.p.situacion_posesoria], ["Visitable", e.p.visitable],
      ["Vivienda habitual", e.p.vivienda_habitual], ["Referencia catastral", e.p.refcat], ["Descripción", e.p.descripcion], ["Cargas", e.p.cargas],
      ["Situado por", { parcela: "la parcela catastral (exacto)", portal: "el portal (bastante exacto)", calle: "la calle (aproximado)" }[e.p.situado_por]], ["Subasta", e.p.subasta]] },
  { id: "abandonado", forma: "rombo", grupo: "Abandono y patrimonio", nombre: "Abandonado o en ruinas (OSM, al momento)", color: "#c026d3", zoom: 13, tipo: "osm",
    ql: ['nwr["abandoned"="yes"]', 'nwr["disused"="yes"]', 'nwr["ruins"="yes"]', 'nwr["building"="ruins"]', 'nwr["historic"="ruins"]', 'nwr[~"^abandoned:"~"."]'],
    es: (t) => t.abandoned === "yes" || t.disused === "yes" || t.ruins === "yes" || t.building === "ruins" || t.historic === "ruins" || Object.keys(t).some((k) => k.startsWith("abandoned:")),
    titulo: (t) => tituloOSM(t, "historic", "building", "man_made", "amenity") || "Abandonado" },
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
  { id: "canteras", grupo: "Infraestructura", nombre: "Canteras y minas", color: "#78350f", zoom: 12, tipo: "osm",
    ql: ['nwr["landuse"="quarry"]', 'nwr["man_made"~"^(adit|mineshaft)$"]', 'nwr["historic"="mine"]'],
    es: (t) => t.landuse === "quarry" || /^(adit|mineshaft)$/.test(t.man_made || "") || t.historic === "mine", titulo: (t) => tituloOSM(t, "man_made", "historic", "landuse") },
  { id: "farolas", tamano: 0.62, grupo: "Infraestructura", nombre: "Farolas (qué está iluminado)", color: "#facc15", zoom: 17, tipo: "osm",
    ql: ['node["highway"="street_lamp"]'], es: (t) => t.highway === "street_lamp", titulo: () => "Farola" },
  // --- Fotos y artículos ---
  { id: "wikipedia", grupo: "Fotos y artículos", nombre: "Artículos de Wikipedia", color: "#f5f5f5", zoom: 13, tipo: "api", pedir: pedirWikipedia },
  { id: "commons", tamano: 0.8, grupo: "Fotos y artículos", nombre: "Fotos de Wikimedia Commons", color: "#0891b2", zoom: 15, tipo: "api", pedir: pedirCommons },
  { id: "panoramax", tamano: 0.7, grupo: "Fotos y artículos", nombre: "Fotos a pie de calle (Panoramax)", color: "#0d9488", zoom: 16, tipo: "api", pedir: pedirPanoramax },
  // --- Catastro ---
  { id: "edificios", grupo: "Catastro", nombre: "Edificios: estado, año y uso", color: "#60a5fa", zoom: 18, tipo: "api", pedir: pedirEdificios, paso: 0.002, porTesela: true },
  // --- En vivo ---
  { id: "aviones", grupo: "En vivo", nombre: "Aviones en vuelo", color: "#facc15", zoom: 7, tipo: "vivo", pedir: pedirAviones, cada: 10000 },
];
const CAPA = Object.fromEntries(CAPAS.map((c) => [c.id, c]));
const CAPA_PUNTO = { id: "punto", nombre: "Punto del mapa", color: "#17242e" };
/* El símbolo de un elemento, como SVG: el mismo que lleva en el mapa. */
const simboloDe = (capa, color, lado = 22) => simboloSVG(capa.icono || capa.id, color || capa.color, capa.forma, lado);
const pasoDe = (z) => (z >= 17 ? 0.005 : z >= 16 ? 0.01 : z >= 15 ? 0.02 : z >= 14 ? 0.04 : z >= 13 ? 0.08 : 0.16);

/* Estado de cada capa: qué trozos del mapa ya se han pedido y qué elementos tiene. */
const estado = {};
for (const c of CAPAS) estado[c.id] = { activa: false, teselas: new Set(), elementos: new Map(), dibujos: new Map(), grupo: L.layerGroup(), cargando: 0, error: false, sinDatos: false };
const capasActivas = new Set(leerLocal("osintmaps.capas-datos.v1", []) || []);

/* --- De dónde sale cada capa "api" --- */
function arcgis(servicios) {
  return (caja) => Promise.all(servicios.map((url) =>
    pedirJ(`${url}/query?where=1%3D1&geometry=${caja.o},${caja.s},${caja.e},${caja.n}&geometryType=esriGeometryEnvelope&inSR=4326` +
           "&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2000&f=geojson")
      .then((g) => {
        // Este servidor contesta «200 OK» también cuando falla, con el error dentro: si se diera
        // por bueno, ese trozo de mapa quedaría como cargado y vacío para siempre.
        if (g.error || !Array.isArray(g.features)) throw new Error("arcgis");
        return g.features.map((f) => elementoGeoJSON(f, url.split("/").slice(-3).join("-"))).filter(Boolean);
      }))).then((listas) => listas.flat());
}
/* Las áreas se guardan como lista de polígonos, y cada polígono como lista de anillos:
   el primero es el contorno y los demás, huecos (un patio, un claro). */
function centroDe(anillos) {
  const fuera = anillos.map((poligono) => poligono[0]).flat();
  return [fuera.reduce((s, q) => s + q[0], 0) / fuera.length, fuera.reduce((s, q) => s + q[1], 0) / fuera.length];
}
const CAMPOS_NOMBRE = ["nombre", "nom", "denominacion", "denominaci", "descripcio", "descripcion", "titulo", "name", "direccion", "adreca", "emplazamiento", "situacion", "texto"];
const CAMPOS_FUERA = /^(objectid|fid|shape.*|x|y|gid|globalid|st_.*|angulo|anggra)$/i;
const CAMPO_BONITO = { idcamara: "Cámara n.º", tipocamara: "Tipo", descripcio: "Descripción", adreca: "Dirección", direccion: "Dirección", denominaci: "Nombre",
  nom: "Nombre", nombre: "Nombre", tipus: "Tipo", tipo: "Tipo", estat: "Estado", estado: "Estado", districte: "Distrito", distrito: "Distrito", barri: "Barrio", barrio: "Barrio",
  superficie: "Superficie", refcat: "Referencia catastral", any: "Año", data: "Fecha", fecha: "Fecha", observacio: "Observaciones", observaciones: "Observaciones" };
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
  e.datos = Object.entries(p).filter(([k, v]) => !CAMPOS_FUERA.test(k) && limpio(v) && typeof v !== "object")
    .map(([k, v]) => [CAMPO_BONITO[k.toLowerCase()] || k.replace(/_/g, " ").replace(/^./, (x) => x.toUpperCase()), /^https:\/\//.test(v) ? v : limpio(v).slice(0, 500)]);
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
  return { id: `commons/${p.pageid}`, lat: c && c.lat, lon: c && c.lon, nombre: p.title.replace(/^File:/, "").replace(/\.[a-z]+$/i, ""), imagen: i.thumburl || i.url,
    original: i.url, url: i.descriptionurl, autor: limpio((m.Artist || {}).value).slice(0, 80), licencia: limpio((m.LicenseShortName || {}).value),
    fecha: limpio((m.DateTimeOriginal || {}).value).slice(0, 10) };
}
// Wikimedia solo sirve las miniaturas en unos anchos fijos (250, 500, 960, 1280, 1920...).
const PEDIDO_COMMONS = { generator: "geosearch", ggsnamespace: "6", prop: "imageinfo|coordinates", iiprop: "url|extmetadata|mime", colimit: "max",
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

const ESTADO_EDIFICIO = { ruin: ["En ruina", "#e5007d"], declined: ["Deficiente", "#f08a00"], functional: ["En uso", "#60a5fa"] };
const USO_EDIFICIO = { "1_residential": "Residencial", "2_agriculture": "Agrario", "3_industrial": "Industrial", "4_1_office": "Oficinas", "4_2_retail": "Comercial", "4_3_publicServices": "Equipamiento o servicio público" };
function pedirEdificios(caja) {
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
  }).then(resolver, rechazar)));
}
function pedirAviones() {
  if (!/^https?:$/.test(location.protocol) || window.OSINT_DATOS) return Promise.reject(new Error("solo con «osintmaps servir»"));
  const c = mapa.getCenter(), b = mapa.getBounds();
  const millas = Math.min(120, Math.max(5, Math.round(mapa.distance(c, b.getNorthEast()) / 1852)));
  return pedirJ(`vivo/aviones?lat=${c.lat.toFixed(3)}&lon=${c.lng.toFixed(3)}&dist=${millas}`, null, 15000).then((j) => (j.ac || []).filter((a) => a.lat != null && a.lon != null).map((a) => ({
    id: `avion/${a.hex}`, lat: a.lat, lon: a.lon, nombre: (a.flight || "").trim() || a.r || a.hex, rumbo: a.track, url: `https://globe.adsb.lol/?icao=${a.hex}`,
    datos: [["Vuelo", (a.flight || "").trim()], ["Matrícula", a.r], ["Modelo", a.t], ["Altitud", typeof a.alt_baro === "number" ? `${miles(a.alt_baro * 0.3048)} m` : a.alt_baro === "ground" ? "en tierra" : ""],
      ["Velocidad", a.gs != null ? `${miles(a.gs * 1.852)} km/h` : ""], ["Rumbo", a.track != null ? `${Math.round(a.track)}°` : ""], ["Código transpondedor", a.squawk], ["Identificador", a.hex]] })));
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
  } else return null;
  if (el0.lat == null) return null;
  el0.nombre = t.name || t["name:es"] || t["name:ca"] || (capa.titulo ? capa.titulo(t) : "") || capa.nombre;
  if (capa.color_de) el0.color = capa.color_de(t);
  return el0;
}
function filasOSM(t) {
  const filas = [];
  for (const [k, nombre] of Object.entries(ETIQUETA_OSM)) if (t[k] && k !== "name") filas.push([nombre, /^(website|wikipedia|wikidata)$/.test(k) ? t[k] : valorOSM(t[k])]);
  return filas;
}

/* --- Dibujo --- */
function dibujar(capa, e) {
  const color = e.color || capa.color;
  const ficha = () => simbolo([e.lat, e.lon], { icono: capa.icono || capa.id, fondo: color, forma: capa.forma, tamano: capa.tamano,
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
  d.on("click", (ev) => { L.DomEvent.stopPropagation(ev); abrirElemento(e); });
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

let relojCapas = null;
const programarCapas = () => { clearTimeout(relojCapas); relojCapas = setTimeout(actualizarCapas, 450); };
function actualizarCapas() {
  const z = mapa.getZoom(), tandaOSM = [];
  for (const capa of CAPAS) {
    const est = estado[capa.id];
    if (capa.tipo === "fija" || capa.tipo === "vivo" || !estaActiva(capa) || z < capa.zoom) continue;
    const { faltan, paso } = teselasQueFaltan(capa);
    if (!faltan.length || faltan.length > 60) continue;
    // Catastro no admite rectángulos grandes: sus capas se piden tesela a tesela.
    for (const lote of capa.porTesela ? faltan.slice(0, 16).map((t) => [t]) : [faltan]) {
      const caja = cajaDe(lote, paso), pedidas = teselasDeCaja(caja, paso);
      for (const t of pedidas) est.teselas.add(t);
      est.cargando++; est.error = false;
      // resultado: true = cargado; false = fallo; "parcial" = llegó solo una parte. Salvo en el
      // primer caso, esos trozos de mapa quedan sin dar por cargados y se vuelven a pedir.
      let hecho = false;
      est.incompleta = false;
      const fin = (resultado) => {
        if (hecho) return;
        hecho = true;
        est.cargando--;
        if (resultado !== true) for (const t of pedidas) est.teselas.delete(t);
        if (resultado === false) est.error = true;
        if (resultado === "parcial") est.incompleta = true;
        pintarEstadoCapas();
      };
      if (capa.tipo === "osm") tandaOSM.push({ capa, caja, fin });
      else capa.pedir(caja).then((elementos) => { incorporar(capa, elementos); fin(true); }, () => fin(false));
    }
  }
  if (tandaOSM.length) pedirTandaOSM(tandaOSM);
  pintarEstadoCapas();
}
/* Una sola consulta a OpenStreetMap para todas las capas que lo necesitan. */
const TOPE_OSM = 8000;
function pedirTandaOSM(tanda) {
  const cuerpo = tanda.map(({ capa, caja }) => capa.ql.map((q) => `${q}(${caja.s},${caja.o},${caja.n},${caja.e});`).join("")).join("");
  return overpass(`[out:json][timeout:40];(${cuerpo});out geom qt ${TOPE_OSM};`).then((j) => {
    // Overpass contesta «200 OK» aunque se le acabe el tiempo: lo avisa en «remark» y manda lo que llevaba.
    if (j.remark && /error|timed out|out of memory/i.test(j.remark)) throw new Error("overpass");
    const elementos = j.elements || [], cortado = elementos.length >= TOPE_OSM;
    // Si se llegó al tope, faltan elementos y no se sabe de qué capa: se repite capa a capa.
    if (cortado && tanda.length > 1) return Promise.all(tanda.map((una) => pedirTandaOSM([una])));
    for (const { capa, fin } of tanda) {
      incorporar(capa, elementos.filter((e) => capa.es(e.tags || {})).map((e) => elementoOSM(e, capa)).filter(Boolean));
      fin(cortado ? "parcial" : true);      // una capa sola que llega al tope: al acercar el mapa se pedirá menos trozo
    }
    return null;
  }).catch(() => { for (const { fin } of tanda) fin(false); });
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
  }, (err) => { est.error = true; est.mensaje = /servir/.test(err.message) ? "solo con «osintmaps servir»" : ""; }).finally(pintarEstadoCapas);
}

/* --- Panel de capas --- */
function pintarEstadoCapas() {
  const z = mapa.getZoom();
  let cargando = 0, fallos = 0;
  for (const capa of CAPAS) {
    const est = estado[capa.id], nota = $(`estado-${capa.id}`);
    if (estaActiva(capa)) { cargando += est.cargando; if (est.error) fallos++; }
    if (!nota) continue;
    nota.parentElement.classList.toggle("lejos", est.sinDatos || (estaActiva(capa) && z < capa.zoom));
    nota.textContent = est.sinDatos ? "sin descargar" : !estaActiva(capa) ? "" : z < capa.zoom ? "acerca el mapa" : est.cargando ? "cargando" : est.error ? (est.mensaje || "sin respuesta")
      : est.incompleta ? `${est.elementos.size}, hay más: acerca` : String(est.elementos.size);
  }
  const aviso = $("aviso-capas");
  aviso.hidden = !cargando && !fallos;
  aviso.textContent = cargando ? "Cargando capas…" : "Alguna capa no ha respondido. Mueve el mapa para reintentar.";
}
function conmutarCapa(capa, encendida) {
  const est = estado[capa.id];
  encendida ? capasActivas.add(capa.id) : capasActivas.delete(capa.id);
  guardarLocal("osintmaps.capas-datos.v1", [...capasActivas]);
  encendida ? est.grupo.addTo(mapa) : mapa.removeLayer(est.grupo);
  if (capa.tipo === "vivo") {
    clearInterval(relojesVivo[capa.id]);
    if (encendida) { refrescarVivo(capa); relojesVivo[capa.id] = setInterval(() => refrescarVivo(capa), capa.cada); } else vaciar(capa);
  }
  programarCapas();
}
{
  let grupoAnterior = "";
  for (const capa of CAPAS) {
    if (capa.oculta) continue;
    if (capa.grupo !== grupoAnterior) { $("capas-datos").append(el("div", { className: "grupo-capas", textContent: capa.grupo })); grupoAnterior = capa.grupo; }
    const casilla = el("input", { id: `dato-${capa.id}`, type: "checkbox", checked: capasActivas.has(capa.id) });
    casilla.addEventListener("change", () => conmutarCapa(capa, casilla.checked));
    $("capas-datos").append(el("label", { className: "casilla" }, casilla, simboloDe(capa), el("span", { textContent: capa.nombre }), el("small", { id: `estado-${capa.id}` })));
  }
}
$("capa-camaras").addEventListener("change", programarCapas);
mapa.on("moveend", programarCapas);
/* Al cambiar de zoom, las áreas pasan de punto a contorno y al revés. */
mapa.on("zoomend", () => {
  for (const capa of CAPAS) {
    const est = estado[capa.id];
    if (capa.id === "edificios" || !estaActiva(capa)) continue;
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
}
{
  const base = new URLSearchParams(location.search).get("datos") || "datos/";
  for (const capa of CAPAS.filter((c) => c.tipo === "fija")) {
    estado[capa.id].sinDatos = true;
    const dentro = window.OSINT_CAPAS && window.OSINT_CAPAS[capa.id];
    (dentro ? Promise.resolve(dentro) : window.OSINT_DATOS ? Promise.reject() : pedirJSON(`${base}capa-${capa.id}.geojson`))
      .then((g) => cargarCapaFija(capa, g)).catch(() => { /* aún no se ha descargado */ }).finally(pintarEstadoCapas);
  }
  for (const capa of CAPAS) if (!capa.oculta && capasActivas.has(capa.id)) conmutarCapa(capa, true);
  programarCapas();
}

/* ====================== 3. Ficha de un elemento o de un punto ====================== */
const capaDe = (e) => CAPA[e.capa] || CAPA_PUNTO;
const puntoDe = (latlng, nombre) => ({ id: `punto/${latlng.lat.toFixed(6)},${latlng.lng.toFixed(6)}`, capa: "punto", lat: +latlng.lat.toFixed(6), lon: +latlng.lng.toFixed(6), nombre: nombre || "Punto del mapa" });
function elementoDeCamara(c) {
  return { id: c.id, capa: "camaras", lat: c.lat, lon: c.lon, nombre: "Cámara de vigilancia", datos: filasCamara(c),
           url: /^(node|way|relation)\/\d+$/.test(c.id) ? `https://www.openstreetmap.org/${c.id}` : null };
}

const marcaSeleccion = L.circleMarker([0, 0], { radius: 15, color: "#e5007d", weight: 3, fill: false, interactive: false });
function marcarSeleccion(e) { marcaSeleccion.setLatLng([e.lat, e.lon]).addTo(mapa); }
function alSoltarElemento() { mapa.removeLayer(marcaSeleccion); }
function cerrarElemento() { soltarElemento(); mostrarLista(); if (candidatos.length) filtrar(); }

/* Ortofoto del IGN centrada en un punto: `lado` son los metros que abarca. */
function urlOrto(lat, lon, lado, vueloNombre, px) {
  const dLat = lado / 2 / 111320, dLon = lado / 2 / (111320 * Math.cos((lat * Math.PI) / 180));
  const q = new URLSearchParams({ SERVICE: "WMS", VERSION: "1.1.1", REQUEST: "GetMap", LAYERS: vueloNombre || "OI.OrthoimageCoverage", STYLES: "", FORMAT: "image/jpeg",
    SRS: "EPSG:4326", WIDTH: px, HEIGHT: px, BBOX: [lon - dLon, lat - dLat, lon + dLon, lat + dLat].map((v) => v.toFixed(6)).join(",") });
  return `${vueloNombre ? WMS_HISTORICO : WMS_ACTUAL}?${q}`;
}
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
const RCCOOR = "https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_RCCOOR";
function faseLunar(fecha) {
  const dias = fecha / 86400000 - 10962.76, ciclo = ((dias % 29.530588853) + 29.530588853) % 29.530588853, parte = ciclo / 29.530588853;
  const luz = Math.round(((1 - Math.cos(2 * Math.PI * parte)) / 2) * 100);
  return `${luz} % iluminada, ${parte < 0.5 ? "creciente" : "menguante"}`;
}
function sobreElPunto(e, dl) {
  const fila = (nombre) => { const dd = el("dd", { className: "pendiente", textContent: "consultando…" }); dl.append(el("dt", { textContent: nombre }), dd); return dd; };
  const poner = (dd, texto) => { dd.className = texto ? "" : "pendiente"; dd.textContent = texto || "sin dato"; };
  const direccion = fila("Dirección"), parcela = fila("Parcela"), uso = fila("Catastro"), altitud = fila("Altitud"), tiempo = fila("Ahora"), sol = fila("Sol"), luna = fila("Luna");
  poner(luna, faseLunar(Date.now()));
  const sigue = () => elementoAbierto === e;
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
           `node["barrier"](around:${r},${c});nwr["amenity"="police"](around:2500,${c});way["building"](around:${r},${c}););out tags center qt;`).then((j) => {
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
  soltarMarcador(); soltarElemento();
  elementoAbierto = e;
  const capa = capaDe(e);
  $("panel").classList.remove("plegado"); $("plegar").textContent = "Ocultar"; $("plegar").setAttribute("aria-expanded", "true");

  const volver = el("button", { type: "button", textContent: "Lista" });
  volver.addEventListener("click", cerrarElemento);
  const muestra = simboloDe(capa, e.color, 22);

  // Portada: la imagen propia del elemento si la tiene; si no, la ortofoto de hoy.
  const lado = Math.min(700, Math.max(160, 4 * Math.sqrt(e.superficie || 1600)));
  const portada = el("button", { type: "button", className: "portada", title: "Abrir en grande" });
  const imagen = el("img", { alt: "", loading: "lazy", referrerPolicy: "no-referrer" });
  imagen.src = e.imagen ? (e.enDirecto ? conReloj(e.imagen) : e.imagen) : urlOrto(e.lat, e.lon, lado, null, 800);
  imagen.addEventListener("error", () => { if (e.imagen && !imagen.dataset.respaldo) { imagen.dataset.respaldo = "1"; imagen.src = urlOrto(e.lat, e.lon, lado, null, 800); rotulo.textContent = "Ortofoto de hoy"; } });
  const rotulo = el("span", { textContent: e.imagen ? (e.enDirecto ? "Imagen en directo" : "Foto") : e.marco ? "Pulsa para ver la cámara en directo" : "Ortofoto de hoy" });
  portada.append(imagen, rotulo);
  portada.addEventListener("click", () => abrirVisor(e, e.imagen || e.marco ? "imagen" : "ortofoto"));

  const vistas = el("div", { className: "vistas" });
  for (const [texto, pestana] of [["Por años", "ortofoto"], ["A pie de calle", "calle"], ["Fotos cerca", "fotos"], ["Satélite", "satelite"]]) {
    const b = el("button", { type: "button", textContent: texto });
    b.addEventListener("click", () => abrirVisor(e, pestana));
    vistas.append(b);
  }

  const acciones = el("div", { className: "enlaces" });
  const guardar = el("button", { type: "button", textContent: "Guardar como marcador" });
  guardar.addEventListener("click", () => {
    const esCamara = /^(camaras|dgt|camvlc)$/.test(e.capa);
    nuevoMarcador(L.latLng(e.lat, e.lon), esCamara ? "camera" : "spot", e.capa === "punto" ? "" : `${capa.nombre}: ${e.nombre}`.slice(0, 500));
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
    el("div", { className: "lugar" }, muestra, `${capa.nombre}. ${e.lat.toFixed(5)}, ${e.lon.toFixed(5)}`),
    portada, vistas, el("div", { className: "bloque" }, acciones)];

  const filas = (e.datos || []).concat(e.etiquetas ? filasOSM(e.etiquetas) : []);
  const tabla = tablaDatos(filas);
  if (tabla) partes.push(bloque("Datos", tabla));
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
  if (e.etiquetas) {
    const crudo = el("details", {}, el("summary", { textContent: "Todas las etiquetas de OpenStreetMap" }), tablaDatos(Object.entries(e.etiquetas)));
    partes.push(el("div", { className: "bloque" }, crudo));
  }
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
function cerrarVisor() {
  if (!visor) return;
  const antes = visor.antes;
  clearInterval(visor.reloj); visor.nodo.remove(); visor = null;
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
  const limpiar = () => { clearInterval(visor.reloj); lienzo.replaceChildren(); opciones.replaceChildren(); tira.replaceChildren(); pie.replaceChildren(); };
  const mensaje = (texto) => lienzo.replaceChildren(el("p", { textContent: texto }));
  const foto = (url, textoPie, enlace) => {
    const img = el("img", { alt: "", referrerPolicy: "no-referrer" });
    img.addEventListener("error", () => mensaje("No se ha podido cargar la imagen."));
    img.src = url;
    lienzo.replaceChildren(img);
    pie.replaceChildren(textoPie || "", enlace && urlSegura(enlace) ? " · " : "", enlace && urlSegura(enlace) ? el("a", { href: enlace, target: "_blank", rel: "noopener noreferrer", textContent: "abrir el original" }) : "");
  };

  const modos = {
    imagen() {
      if (e.marco) { lienzo.replaceChildren(el("iframe", { src: e.marco, title: "Cámara en directo", referrerPolicy: "no-referrer" })); pie.textContent = "Imagen en directo de la cámara municipal."; return; }
      const poner = () => foto(e.enDirecto ? conReloj(e.imagen) : e.original || e.imagen, [e.enDirecto && "Imagen en directo; se renueva sola cada 30 s.", e.autor, e.fecha, e.licencia].filter(Boolean).join(" · "), e.url);
      poner();
      if (e.enDirecto) visor.reloj = setInterval(poner, 30000);
    },
    ortofoto() {
      let vueloActual = null, lado = Math.min(600, Math.max(120, 3 * Math.sqrt(e.superficie || 1600)));
      const pintar = () => {
        const img = el("img", { alt: "", crossOrigin: "anonymous" });
        img.addEventListener("load", () => { if (esImagenLisa(img)) mensaje("Ese vuelo no cubre esta zona."); });
        img.addEventListener("error", () => mensaje("El IGN no ha devuelto la imagen. Prueba otro año."));
        img.src = urlOrto(e.lat, e.lon, lado, vueloActual, 1800);
        lienzo.replaceChildren(img, el("div", { className: "cruz" }));
        pie.textContent = `${vueloActual ? vuelo(vueloActual).rotulo : "Vuelo más reciente"} · ${Math.round(lado)} m de lado · ${(lado / 18).toFixed(0)} cm por píxel pedidos (el original tiene 15 a 50 cm) · PNOA, IGN`;
      };
      const hoy = chip("Hoy", () => { vueloActual = null; pintar(); }, opciones); hoy.dataset.fila = "anio"; hoy.setAttribute("aria-pressed", "true");
      for (const v of [...vuelos].sort((a, b) => b.anio - a.anio)) chip(v.rotulo, () => { vueloActual = v.nombre; pintar(); }, opciones).dataset.fila = "anio";
      for (const [texto, metros0] of [["Muy cerca", 80], ["Cerca", 180], ["Entorno", 450], ["Zona", 1200]]) chip(texto, () => { lado = metros0; pintar(); }, tira).dataset.fila = "lado";
      pintar();
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
          const b = chip("", () => foto(f.imagen, [f.nombre, f.autor, f.fecha, f.licencia, f.lat != null && `a ${Math.round(metros(e, f))} m`].filter(Boolean).join(" · "), f.url), tira);
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
  const opcion = (texto, hacer) => { const b = el("button", { type: "button", role: "menuitem", textContent: texto }); b.addEventListener("click", () => { cerrarMenu(); hacer(); }); menu.append(b); };
  opcion("¿Qué hay aquí?", () => abrirElemento(puntoDe(ll)));
  opcion("Añadir un marcador aquí", () => nuevoMarcador(ll));
  opcion("Ver a pie de calle", () => abrirVisor(puntoDe(ll), "calle"));
  opcion("Ortofotos de este punto por años", () => abrirVisor(puntoDe(ll), "ortofoto"));
  opcion("Copiar las coordenadas", () => { if (navigator.clipboard) navigator.clipboard.writeText(`${ll.lat.toFixed(6)}, ${ll.lng.toFixed(6)}`).catch(() => {}); });
  opcion("Centrar el mapa aquí", () => mapa.panTo(ll));
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

/* --- Buscador: además de filtrar los sitios, busca en las demás capas y en el callejero --- */
let relojBusqueda = null, turnoBusqueda = 0;
function pintarResultados(grupos) {
  const lista = $("resultados-extra");
  lista.replaceChildren();
  for (const [titulo, filas] of grupos) {
    if (!filas.length) continue;
    lista.append(el("li", { className: "rotulo", textContent: titulo }));
    for (const f of filas) {
      const b = el("button", { type: "button" }, simboloSVG(f.icono || "punto", f.color, f.forma, 22), el("b", { textContent: f.titulo }), el("small", { textContent: f.detalle || "" }));
      b.addEventListener("click", () => { clearTimeout(temporizadorBusqueda); f.ir(); });
      lista.append(el("li", {}, b));
    }
  }
  lista.hidden = !lista.children.length;
}
function buscarTodo(texto, conCallejero) {
  const turno = ++turnoBusqueda, q = sinAcentos(texto.trim());
  if (q.length < 3) { pintarResultados([]); return; }
  const directos = [], enCapas = [];
  const coords = /^(-?\d{1,2}(?:[.,]\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:[.,]\d+)?)$/.exec(texto.trim());
  if (coords) {
    const lat = +coords[1].replace(",", "."), lon = +coords[2].replace(",", ".");
    if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) directos.push({ color: "#17242e", titulo: `${lat}, ${lon}`, detalle: "Ir a estas coordenadas", ir: () => abrirElemento(puntoDe(L.latLng(lat, lon)), true) });
  }
  const refcat = /^[0-9A-Z]{14}(?:[0-9A-Z]{6})?$/.test(texto.trim().toUpperCase()) && /\d/.test(texto) && /[A-Za-z]/.test(texto) ? texto.trim().toUpperCase().slice(0, 14) : null;
  for (const [id, m] of Object.entries(marcadores)) {
    if (!m.deleted && sinAcentos(m.note).includes(q)) enCapas.push({ color: TIPOS_MARCADOR[m.type][1], icono: ICONO_MARCADOR[m.type], titulo: m.note.slice(0, 70), detalle: `Marcador: ${TIPOS_MARCADOR[m.type][0].toLowerCase()}`, ir: () => { mapa.setView([m.lat, m.lng], Math.max(mapa.getZoom(), 17)); abrirMarcador(id); } });
  }
  if ($("capa-camaras").checked) {
    // Las cámaras no tienen nombre: se buscan por lo que se sabe de ellas (tipo, zona, operador)
    // y salen las más cercanas al centro del mapa.
    const centro = mapa.getCenter();
    [...camaras.values()].map((c) => [c, filasCamara(c).map((f) => f[1]).join(", ")]).filter(([, texto]) => sinAcentos(texto).includes(q))
      .sort((a, b) => mapa.distance(centro, [a[0].lat, a[0].lon]) - mapa.distance(centro, [b[0].lat, b[0].lon])).slice(0, 4)
      .forEach(([c, texto]) => enCapas.push({ color: CAPA.camaras.color, icono: "camaras", titulo: texto, detalle: "Cámara de vigilancia (OpenStreetMap)", ir: () => abrirElemento(elementoDeCamara(c), true) }));
  }
  for (const capa of CAPAS) {
    if (enCapas.length >= 12) break;
    for (const e of estado[capa.id].elementos.values()) {
      if (enCapas.length >= 12) break;
      if (e.nombre && sinAcentos(e.nombre).includes(q)) enCapas.push({ color: e.color || capa.color, icono: capa.icono || capa.id, forma: capa.forma, titulo: e.nombre, detalle: capa.nombre, ir: () => abrirElemento(e, true) });
    }
  }
  const grupos = [["Ir a", directos], ["En las capas cargadas", enCapas], ["Lugares y direcciones", []]];
  pintarResultados(grupos);
  if (refcat) {
    pedirJ(`https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCoordenadas.svc/json/Consulta_CPMRC?RefCat=${refcat}&SRS=EPSG:4326`, null, 15000).then((j) => {
      const c = (((j.Consulta_CPMRCResult || {}).coordenadas || {}).coord || [])[0];
      if (turno !== turnoBusqueda || !c || !c.geo) return;
      directos.push({ color: "#17242e", titulo: `Parcela ${refcat}`, detalle: c.ldt || "Referencia catastral", ir: () => abrirElemento(puntoDe(L.latLng(+c.geo.ycen, +c.geo.xcen), `Parcela ${refcat}`), true) });
      pintarResultados(grupos);
    }).catch(() => {});
  }
  if (!conCallejero || coords || refcat) return;
  const b = mapa.getBounds();
  pedirJ(`https://nominatim.openstreetmap.org/search?${new URLSearchParams({ format: "jsonv2", countrycodes: "es", limit: "6", "accept-language": "es", q: texto.trim(),
    viewbox: `${b.getWest()},${b.getNorth()},${b.getEast()},${b.getSouth()}` })}`, null, 15000).then((lugares) => {
    if (turno !== turnoBusqueda) return;
    grupos[2][1] = lugares.map((l) => ({ color: "#1f5fd1", titulo: l.name || l.display_name.split(",")[0], detalle: l.display_name, ir: () => {
      const caja = l.boundingbox && l.boundingbox.map(Number);
      if (caja && (caja[1] - caja[0] > 0.004 || caja[3] - caja[2] > 0.004)) { soltarElemento(); mapa.fitBounds([[caja[0], caja[2]], [caja[1], caja[3]]], { maxZoom: 17 }); }
      else abrirElemento(puntoDe(L.latLng(+l.lat, +l.lon), l.name || l.display_name.split(",")[0]), true);
    } }));
    pintarResultados(grupos);
  }).catch(() => {});
}
$("buscar-texto").addEventListener("input", (ev) => {
  if (seleccion || panelOcupado()) { soltarMarcador(); mostrarLista(); if (candidatos.length) filtrar(); }
  clearTimeout(relojBusqueda);
  const texto = ev.target.value;
  buscarTodo(texto, false);
  relojBusqueda = setTimeout(() => buscarTodo(texto, true), 800);      // al callejero, solo cuando se deja de escribir
});
$("buscar-texto").addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  clearTimeout(relojBusqueda);
  buscarTodo(ev.target.value, true);
});

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
  for (const [texto, pestana] of [["Por años", "ortofoto"], ["A pie de calle", "calle"], ["Fotos cerca", "fotos"], ["Satélite", "satelite"]]) {
    const b = el("button", { type: "button", textContent: texto });
    b.addEventListener("click", () => abrirVisor(e, pestana));
    fila.append(b);
  }
  return fila;
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
