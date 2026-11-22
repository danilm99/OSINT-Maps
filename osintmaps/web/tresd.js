"use strict";
/* OSINT Maps: la vista en 3D. Se carga la última y usa lo de los otros ficheros.

   Qué es: el mismo sitio visto en perspectiva. Hay dos maneras de verlo:
   - «Real» (solo en la provincia de València): la maqueta fotográfica del ICV, hecha con el vuelo
     de 2025. Edificios, árboles y muros salen con su forma de verdad, como en Google Earth.
   - Sin ella, o fuera de la provincia: el relieve del terreno con la foto aérea pegada encima y
     cada edificio como un prisma con la altura que consta en OpenStreetMap.

   De dónde sale cada cosa:
   - El dibujo lo hace MapLibre GL, una biblioteca que pinta mapas con la tarjeta gráfica. Pesa
     un megabyte, así que solo se descarga la primera vez que se pulsa «3D».
   - El relieve: teselas públicas de altitud (imágenes en las que cada punto guarda una altura).
   - La foto: las mismas tres fuentes que en 2D, una sobre otra (PNOA en toda España, encima la
     del ICV en la provincia de València y encima la del Ayuntamiento en la ciudad).
   - Los edificios y los nombres: OpenFreeMap, que sirve los datos de OpenStreetMap troceados.
   - La maqueta: el servicio público del ICV (el de su «Visor 3D GVA»). La lee y la pinta el código
     del final de este fichero, sin ninguna biblioteca más.

   Encima se ven los sitios, tus marcadores, lo ya cargado de las capas encendidas, la ruta y
   tu posición. Tocar un punto abre su ficha, igual que en 2D. El mapa plano sigue debajo,
   escondido, y se mueve a la vez: así las capas se siguen cargando según lo que se mira. */

const MAPLIBRE = "https://unpkg.com/maplibre-gl@5.24.1/dist/maplibre-gl";
const HUELLA_MAPLIBRE = { js: "sha384-nXMl9YiLoSG5KBPTFgvxVuIqQQcqIvo0bFrvoEaGJC6r7IibIzF1S36Zbf/sKBtL", css: "sha384-uTttxo/aOKbdE5RlD/SPzSDoDmNvGlUYPjONi2MN/b7c9HPSvW07OIuyP7uL6jxK" };
let mapa3d = null, bajando3d = null, reloj3d = null, firma3d = "", moviendoDesde3d = false;
const en3D = () => $("mapa-zona").classList.contains("en-3d");

function cargarMapLibre() {
  if (window.maplibregl) return Promise.resolve();
  if (!bajando3d) {
    bajando3d = new Promise((ok, no) => {
      document.head.append(el("link", { rel: "stylesheet", href: `${MAPLIBRE}.css`, integrity: HUELLA_MAPLIBRE.css, crossOrigin: "anonymous" }));
      const guion = el("script", { src: `${MAPLIBRE}.js`, integrity: HUELLA_MAPLIBRE.js, crossOrigin: "anonymous" });
      guion.addEventListener("load", () => (window.maplibregl ? ok() : no(new Error("maplibre"))));
      guion.addEventListener("error", () => { bajando3d = null; guion.remove(); no(new Error("maplibre")); });
      document.head.append(guion);
    });
  }
  return bajando3d;
}

/* El «estilo» es la receta que MapLibre sigue: de dónde saca los datos (sources) y en qué orden y cómo los pinta (layers). */
function estilo3D() {
  const vacio = { type: "FeatureCollection", features: [] };
  const c = VALENCIA_CIUDAD, p = VALENCIA_PROVINCIA, letra = ["Noto Sans Regular"];
  return {
    version: 8,
    glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    sources: {
      pnoa: { type: "raster", tiles: [URL_PNOA], tileSize: 256, maxzoom: 20, attribution: "PNOA CC BY 4.0 scne.es" },
      icv: { type: "raster", tileSize: 256, minzoom: 13, maxzoom: 22, bounds: [p.o, p.s, p.e, p.n], attribution: "ICV CC BY 4.0",
        tiles: [`${WMS_ICV}?service=WMS&version=1.1.1&request=GetMap&layers=2025PVAL0015_RGB&styles=&format=image%2Fvnd.jpeg-png&transparent=true&srs=EPSG%3A3857&width=256&height=256&bbox={bbox-epsg-3857}`] },
      ciudad: { type: "raster", tiles: [`${FOTO_VLC}/tile/{z}/{y}/{x}`], tileSize: 256, minzoom: 13, maxzoom: 21, bounds: [c.o, c.s, c.e, c.n], attribution: "Ajuntament de València" },
      relieve: { type: "raster-dem", tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 15, encoding: "terrarium",
        attribution: "Relieve: Mapzen, SRTM y otros" },
      calles: { type: "vector", url: "https://tiles.openfreemap.org/planet", attribution: "OpenFreeMap © OpenMapTiles, datos © OpenStreetMap" },
      puntos: { type: "geojson", data: vacio }, ruta: { type: "geojson", data: vacio }, elegido: { type: "geojson", data: vacio },
    },
    sky: { "sky-color": "#7fb6ea", "horizon-color": "#dfeaf2", "fog-color": "#dfeaf2", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.35 },
    layers: [
      { id: "fondo", type: "background", paint: { "background-color": "#1b262e" } },
      { id: "pnoa", type: "raster", source: "pnoa" },
      { id: "icv", type: "raster", source: "icv", minzoom: 12.5 },
      { id: "ciudad", type: "raster", source: "ciudad", minzoom: 12.5 },
      { id: "edificios", type: "fill-extrusion", source: "calles", "source-layer": "building", minzoom: 13.5,
        paint: { "fill-extrusion-color": ["interpolate", ["linear"], ["coalesce", ["get", "render_height"], 6], 0, "#e9e4da", 30, "#d9dde2", 90, "#c2cbd6"],
          "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6], "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0], "fill-extrusion-opacity": 0.86 } },
      { id: "ruta-borde", type: "line", source: "ruta", filter: ["==", ["geometry-type"], "LineString"], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.9 } },
      { id: "ruta-linea", type: "line", source: "ruta", filter: ["==", ["geometry-type"], "LineString"], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "color"], "line-width": 5 } },
      { id: "ruta-extremos", type: "circle", source: "ruta", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 7, "circle-color": ["get", "color"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 3 } },
      { id: "nombres-calles", type: "symbol", source: "calles", "source-layer": "transportation_name", minzoom: 14.5,
        layout: { "symbol-placement": "line", "text-field": ["coalesce", ["get", "name"], ""], "text-font": letra, "text-size": 12 },
        paint: { "text-color": "#ffffff", "text-halo-color": "rgba(23,36,46,.9)", "text-halo-width": 1.6 } },
      { id: "nombres-lugares", type: "symbol", source: "calles", "source-layer": "place", maxzoom: 15,
        layout: { "text-field": ["coalesce", ["get", "name"], ""], "text-font": letra, "text-size": ["interpolate", ["linear"], ["zoom"], 6, 12, 14, 16] },
        paint: { "text-color": "#ffffff", "text-halo-color": "rgba(23,36,46,.9)", "text-halo-width": 1.8 } },
      { id: "elegido", type: "circle", source: "elegido", paint: { "circle-radius": 15, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#e5007d", "circle-stroke-width": 3.5 } },
      { id: "puntos", type: "circle", source: "puntos",
        paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3.5, 13, 6, 17, 8.5], "circle-color": ["get", "color"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.6 } },
      { id: "puntos-nombres", type: "symbol", source: "puntos", minzoom: 14.5, filter: ["!=", ["get", "nombre"], ""],
        layout: { "text-field": ["get", "nombre"], "text-font": letra, "text-size": 12, "text-anchor": "top", "text-offset": [0, 0.9], "text-max-width": 9, "text-optional": true },
        paint: { "text-color": "#ffffff", "text-halo-color": "rgba(23,36,46,.92)", "text-halo-width": 1.6 } },
    ],
  };
}

/* Lo que hay que pintar encima: se recoge del estado del mapa plano. `clase` dice de qué es cada punto para saber qué ficha abrir. */
function puntos3D() {
  const puntos = [], punto = (lon, lat, propiedades) => puntos.push({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: propiedades });
  if ($("capa-sitios").checked) for (const c of enMapa) punto(c.lon, c.lat, { clase: "sitio", id: c.id, color: colorNota(c.p.puntuacion || 0), nombre: "" });
  if ($("capa-marcadores").checked) for (const [id, m] of Object.entries(marcadores)) if (!m.deleted) punto(m.lng, m.lat, { clase: "marcador", id, color: TIPOS_MARCADOR[m.type][1], nombre: (m.note || "").slice(0, 40) });
  if ($("capa-camaras").checked) for (const c of camaras.values()) punto(c.lon, c.lat, { clase: "camara", id: c.id, color: CAPA.camaras.color, nombre: "" });
  for (const capa of CAPAS) {
    if (capa.oculta || !capasActivas.has(capa.id)) continue;
    for (const e of estado[capa.id].elementos.values()) punto(e.lon, e.lat, { clase: "capa", capa: capa.id, id: e.id, color: e.color || capa.color, nombre: (e.nombre || "").slice(0, 40) });
  }
  if (busquedaCerca) for (const e of busquedaCerca.elementos) punto(e.lon, e.lat, { clase: "cerca", id: e.id, color: e.color || busquedaCerca.capa.color, nombre: (e.nombre || "").slice(0, 40) });
  if (miPosicion) punto(miPosicion.lon, miPosicion.lat, { clase: "yo", id: "yo", color: "#1a73e8", nombre: "Tú" });
  return { type: "FeatureCollection", features: puntos };
}
function ruta3D() {
  const partes = [], op = typeof opcionActual === "function" ? opcionActual() : null;
  if (op) for (const t of op.tramos) partes.push({ type: "Feature", geometry: { type: "LineString", coordinates: t.puntos.map(([lat, lon]) => [lon, lat]) }, properties: { color: t.color } });
  if (typeof ruta === "object") {
    if (ruta.origen && ruta.origen.ll) partes.push({ type: "Feature", geometry: { type: "Point", coordinates: [ruta.origen.ll.lng, ruta.origen.ll.lat] }, properties: { color: "#17242e" } });
    if (ruta.destino && ruta.destino.ll) partes.push({ type: "Feature", geometry: { type: "Point", coordinates: [ruta.destino.ll.lng, ruta.destino.ll.lat] }, properties: { color: "#d93025" } });
  }
  return { type: "FeatureCollection", features: partes };
}
function elegido3D() {
  const m = marcadorAbierto ? marcadores[marcadorAbierto] : null;
  const p = seleccion ? [seleccion.lon, seleccion.lat] : elementoAbierto ? [elementoAbierto.lon, elementoAbierto.lat] : m ? [m.lng, m.lat] : null;
  return { type: "FeatureCollection", features: p ? [{ type: "Feature", geometry: { type: "Point", coordinates: p }, properties: {} }] : [] };
}
/* Se mira cada poco si ha cambiado algo de lo que se pinta (una «firma» barata de calcular) y solo entonces se rehace. */
function refrescar3D() {
  if (!mapa3d || !mapa3d.getSource("puntos")) return;
  // Los prismas de OpenStreetMap solo hacen falta donde la maqueta no tiene nada que enseñar.
  const prismas = malla && malla.estado().pintados ? "none" : "visible";
  if (mapa3d.getLayer("edificios") && (mapa3d.getLayoutProperty("edificios", "visibility") || "visible") !== prismas) mapa3d.setLayoutProperty("edificios", "visibility", prismas);
  const op = typeof opcionActual === "function" ? opcionActual() : null;
  const firma = [enMapa.length, $("capa-sitios").checked, $("capa-marcadores").checked, $("capa-camaras").checked, camaras.size, Object.keys(marcadores).length,
    [...capasActivas].map((id) => `${id}${estado[id] ? estado[id].elementos.size : 0}`).join(","), busquedaCerca ? busquedaCerca.elementos.length : 0,
    miPosicion ? `${miPosicion.lat.toFixed(5)},${miPosicion.lon.toFixed(5)}` : "", typeof ruta === "object" ? `${ruta.turno}/${ruta.modo}/${op ? op.duracion : 0}` : "",
    seleccion ? seleccion.id : "", elementoAbierto ? elementoAbierto.id : "", marcadorAbierto || ""].join("|");
  if (firma === firma3d) return;
  firma3d = firma;
  mapa3d.getSource("puntos").setData(puntos3D());
  mapa3d.getSource("ruta").setData(ruta3D());
  mapa3d.getSource("elegido").setData(elegido3D());
}
function abrirDesde3D(p) {
  if (p.clase === "sitio") { const c = candidatos.find((x) => x.id === p.id); if (c) abrirFicha(c, false); }
  else if (p.clase === "marcador") abrirMarcador(p.id);
  else if (p.clase === "camara") { const c = camaras.get(p.id); if (c) abrirElemento(elementoDeCamara(c)); }
  else if (p.clase === "capa") { const e = estado[p.capa] && estado[p.capa].elementos.get(p.id); if (e) abrirElemento(e); }
  else if (p.clase === "cerca") { const e = busquedaCerca && busquedaCerca.elementos.find((x) => x.id === p.id); if (e) abrirElemento(e); }
  firma3d = "";
  refrescar3D();
}

function aviso3D(texto, dura = 7000) {
  let aviso = $("aviso-3d");
  if (!aviso) { aviso = el("div", { id: "aviso-3d", role: "status" }); $("mapa-zona").append(aviso); }
  aviso.textContent = texto;
  aviso.classList.remove("ido");
  aviso.hidden = false;
  clearTimeout(aviso.reloj);
  if (dura) aviso.reloj = setTimeout(() => { aviso.classList.add("ido"); setTimeout(() => { aviso.hidden = true; }, 700); }, dura);
}
function entrar3D() {
  const boton = $("boton-3d");
  boton.disabled = true;
  aviso3D("Preparando la vista en 3D…", 0);
  cargarMapLibre().then(() => {
    const c = mapa.getCenter(), zona = $("mapa-zona");
    $("vista3d").hidden = false;
    zona.classList.add("en-3d");
    if (mapa.hasLayer(fondoActual)) mapa.removeLayer(fondoActual);      // el mapa plano queda escondido: que no baje teselas
    if (!mapa3d) {
      mapa3d = new maplibregl.Map({ container: "vista3d", style: estilo3D(), center: [c.lng, c.lat], zoom: Math.max(1, mapa.getZoom() - 1), pitch: 62, bearing: -18, maxPitch: 82,
        attributionControl: false });
      mapa3d.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");
      // Los créditos, recogidos tras un botón «i» abajo a la izquierda (abajo a la derecha están los botones del mapa).
      mapa3d.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Maqueta 3D: Institut Cartogràfic Valencià" }), "bottom-left");
      // (MapLibre los despliega al cargar; se recogen en cuanto termina de pintar por primera vez)
      const recogerCreditos = () => { const c = $("vista3d").querySelector(".maplibregl-ctrl-attrib"); if (c && c.classList.contains("maplibregl-compact")) { c.classList.remove("maplibregl-compact-show"); c.removeAttribute("open"); } };
      mapa3d.once("load", recogerCreditos); mapa3d.once("idle", recogerCreditos);
      mapa3d.on("load", () => {
        ponerMalla(quiereMalla());
        firma3d = "";
        refrescar3D();
      });
      // Al parar de mover la vista, el mapa plano (escondido) se lleva al mismo sitio: así se cargan las capas de lo que se mira.
      mapa3d.on("moveend", () => {
        const centro = mapa3d.getCenter();
        moviendoDesde3d = true;
        try { mapa.setView([centro.lat, centro.lng], Math.max(3, Math.min(ZOOM_MAX, Math.round(mapa3d.getZoom() + 1))), { animate: false }); } finally { moviendoDesde3d = false; }
      });
      mapa3d.on("click", (ev) => {
        const tocado = mapa3d.queryRenderedFeatures([[ev.point.x - 6, ev.point.y - 6], [ev.point.x + 6, ev.point.y + 6]], { layers: ["puntos"] }).find((f) => f.properties.clase !== "yo");
        if (tocado) abrirDesde3D(tocado.properties);
        else if (typeof ruta === "object" && ruta.eligiendo) mapa.fire("click", { latlng: L.latLng(ev.lngLat.lat, ev.lngLat.lng) });      // elegir un extremo de la ruta
      });
      // Botón derecho (o mantener pulsado): «¿qué hay aquí?»
      mapa3d.on("contextmenu", (ev) => { abrirElemento(puntoDe(L.latLng(ev.lngLat.lat, ev.lngLat.lng))); firma3d = ""; refrescar3D(); });
      mapa3d.on("mousemove", (ev) => { mapa3d.getCanvas().style.cursor = mapa3d.queryRenderedFeatures(ev.point, { layers: ["puntos"] }).length ? "pointer" : ""; });
      mapa3d.on("error", (ev) => { if (ev && ev.error && /webgl/i.test(String(ev.error.message))) aviso3D("Este navegador no puede dibujar en 3D."); });
    } else {
      mapa3d.resize();
      mapa3d.jumpTo({ center: [c.lng, c.lat], zoom: Math.max(1, mapa.getZoom() - 1) });
    }
    clearInterval(reloj3d);
    reloj3d = setInterval(refrescar3D, 700);
    boton.setAttribute("aria-pressed", "true");
    boton.querySelector(".rotulo").textContent = "2D";
    boton.title = "Volver al mapa plano";
    aviso3D(matchMedia("(pointer: coarse)").matches ? "Un dedo mueve. Con dos dedos se gira; subiéndolos o bajándolos a la vez, se inclina." : "Arrastra para mover. Con el botón derecho (o Ctrl) y arrastrando, se gira y se inclina.");
  }).catch((err) => {
    $("vista3d").hidden = true;
    $("mapa-zona").classList.remove("en-3d");
    if (!mapa.hasLayer(fondoActual)) fondoActual.addTo(mapa);
    aviso3D(err && /webgl|context/i.test(String(err.message)) ? "Este navegador no puede dibujar en 3D." : "No se ha podido cargar la vista en 3D. Comprueba la conexión y vuelve a probar.");
  }).finally(() => { boton.disabled = false; });
}
function salir3D() {
  clearInterval(reloj3d);
  $("vista3d").hidden = true;
  $("mapa-zona").classList.remove("en-3d");
  if (!mapa.hasLayer(fondoActual)) fondoActual.addTo(mapa);
  mapa.invalidateSize({ pan: false });
  const boton = $("boton-3d"), aviso = $("aviso-3d");
  boton.setAttribute("aria-pressed", "false");
  boton.querySelector(".rotulo").textContent = "3D";
  boton.title = "Ver en 3D: relieve, foto aérea y edificios";
  if (aviso) aviso.hidden = true;
}
$("boton-3d").addEventListener("click", () => (en3D() ? salir3D() : entrar3D()));
/* Lo que mueve el mapa plano desde fuera (abrir una ficha, encuadrar una ruta, ir a un resultado) mueve también la vista en 3D. */
mapa.on("moveend", () => {
  if (!en3D() || !mapa3d || moviendoDesde3d) return;
  const c = mapa.getCenter();
  mapa3d.easeTo({ center: [c.lng, c.lat], zoom: Math.max(1, mapa.getZoom() - 1), duration: 700 });
});
/* Cambiar el mapa de fondo estando en 3D no debe volver a poner el plano a bajar teselas. */
$("capa-fondo").addEventListener("change", () => { if (en3D()) setTimeout(() => { if (en3D() && mapa.hasLayer(fondoActual)) mapa.removeLayer(fondoActual); }, 0); });
window.addEventListener("resize", () => { if (en3D() && mapa3d) mapa3d.resize(); });

/* ---------- La maqueta fotográfica del ICV ----------

   Qué es. El ICV voló la provincia en 2025 y, además de la foto, sacó una «malla»: la superficie
   de todo lo que se ve desde arriba (suelo, tejados, copas de árboles) hecha de triángulos, con
   la foto pegada. La publica en cuatro trozos de provincia (sur, centro, norte y Ademuz).

   Cómo está guardada (el formato se llama I3S). Cada trozo de provincia es un árbol de «nodos».
   El de arriba cubre todo con muy poco detalle; cada nodo tiene hijos que cubren partes más
   pequeñas con más detalle, y así 18 niveles hasta hojas de unos 170 m de lado. La lista de nodos
   llega en páginas de 64. De cada nodo interesan su caja (centro y tamaño), a partir de qué tamaño
   en pantalla se queda corto (`lodThreshold`) y dónde están sus triángulos y su foto.

   Qué se hace en cada fotograma. Se baja por el árbol: un nodo que no se ve se salta; uno que en
   pantalla ocupa más de lo que aguanta se cambia por sus hijos; el resto se pinta. Lo que falta
   se pide (pocos a la vez), y mientras llega se sigue viendo el nodo padre, o la foto plana de
   debajo si no hay nada. Lo que lleva rato sin usarse se borra de la memoria.

   Cómo se pinta. MapLibre deja añadir una «capa a medida»: en cada fotograma llama a `render` con
   la matriz que lleva un punto del mapa a la pantalla, y ahí se dibujan los triángulos a mano. */
const MALLA_ICV = ["Sur", "Centro", "Norte", "Ademuz"].map((zona) => `https://gvagis.icv.gva.es/server/rest/services/Malla3D_${zona}/SceneServer/layers/0`);
const LADO_MUNDO = 40075016.685578488, RADIO_TIERRA = 6378137;       // el mapa entero mide eso de lado, en los metros de la proyección
let malla = null;
const quiereMalla = () => leerLocal("osintmaps.malla.v1", true) !== false;

function capaMalla() {
  const tactil = matchMedia("(pointer: coarse)").matches;
  const AGUANTE = tactil ? 1.7 : 1.15;        // cuánto más grande de lo previsto se deja un nodo antes de cambiarlo por sus hijos: más es más ligero y más borroso
  const TOPE = tactil ? 36 : 96;              // nodos que se guardan en la memoria de la tarjeta gráfica
  const LADO_FOTO = tactil ? 1024 : 2048;     // tamaño máximo de la foto de un nodo
  const A_LA_VEZ = 6, POR_PAGINA = 64;
  const arboles = MALLA_ICV.map((url) => ({ url, paginas: new Map(), pidiendo: new Set(), fallo: new Map() }));
  const listos = new Map(), bajando = new Set(), fallidos = new Map(), porSubir = [];
  let gl = null, gl2 = false, programa = null, uMatriz = null, aPos = 0, aUv = 0, mapaGL = null;
  let fotograma = 0, pintados = 0, vista = null, lista = [], cola = [];
  const bien = (r) => (r.ok ? r : Promise.reject(new Error(String(r.status))));
  const repintar = () => { if (mapaGL) mapaGL.triggerRepaint(); };

  /* Una página de nodos: si no está, se pide y de momento se contesta que no hay. */
  const pagina = (arbol, p) => {
    const hecha = arbol.paginas.get(p);
    if (hecha) return hecha;
    if (!arbol.pidiendo.has(p) && !(arbol.fallo.get(p) > Date.now())) {
      arbol.pidiendo.add(p);
      fetch(`${arbol.url}/nodepages/${p}`).then(bien).then((r) => r.json())
        .then((j) => { arbol.paginas.set(p, j.nodes || []); })
        .catch(() => { arbol.fallo.set(p, Date.now() + 20000); })
        .finally(() => { arbol.pidiendo.delete(p); repintar(); });
    }
    return null;
  };
  const nodo = (arbol, i) => { const p = pagina(arbol, Math.floor(i / POR_PAGINA)); return (p && p[i % POR_PAGINA]) || null; };

  /* Lo que se necesita de un nodo, calculado una sola vez. Las coordenadas del mapa van de 0 a 1
     (0,0 arriba a la izquierda); una altura en metros se pasa a esas unidades con `porMetro`. */
  const medidas = (n) => {
    if (n.m) return n.m;
    const c = n.obb.center, h = n.obb.halfSize;
    return (n.m = { x: 0.5 + c[0] / LADO_MUNDO, y: 0.5 - c[1] / LADO_MUNDO, alto: c[2], porMetro: Math.cosh(c[1] / RADIO_TIERRA) / LADO_MUNDO,
      radio: Math.hypot(h[0], h[1], h[2]) / LADO_MUNDO, aguanta: n.lodThreshold ? Math.sqrt(n.lodThreshold * 4 / Math.PI) : 0 });
  };
  /* Diámetro del nodo en pantalla, en píxeles; -1 si queda fuera de la vista. */
  const tamano = (n) => {
    const m = medidas(n), M = vista.M, z = (m.alto - vista.base) * m.porMetro;
    const d = Math.hypot(m.x - vista.ojo[0], m.y - vista.ojo[1], z - vista.ojo[2]);
    if (d <= m.radio) return Infinity;                                         // la cámara está dentro del nodo
    const w = M[3] * m.x + M[7] * m.y + M[11] * z + M[15];
    if (w + vista.pasoW * m.radio <= 0) return -1;                             // entero por detrás de la cámara
    const radioPx = m.radio / d * vista.focal;
    if (w > 0) {
      const px = (M[0] * m.x + M[4] * m.y + M[8] * z + M[12]) / w * vista.ancho / 2, py = (M[1] * m.x + M[5] * m.y + M[9] * z + M[13]) / w * vista.alto / 2;
      if (Math.abs(px) > vista.ancho / 2 + radioPx || Math.abs(py) > vista.alto / 2 + radioPx) return -1;
    }
    return 2 * radioPx;
  };

  /* Baja por el árbol y apunta en `lista` qué nodos pintar. Devuelve si esa rama queda completa:
     si no lo está y el nodo de arriba ya está cargado, se pinta ese en su lugar. */
  const elegir = (arbol, ia, i) => {
    const n = nodo(arbol, i);
    if (!n) return false;
    const px = tamano(n);
    if (px < 0) return true;
    const clave = `${ia}:${i}`, m = medidas(n), marca = lista.length, hijos = n.children || [];
    if (hijos.length && (!m.aguanta || px > m.aguanta * AGUANTE)) {
      let completo = true;
      for (const h of hijos) if (!elegir(arbol, ia, h)) completo = false;
      if (completo) return true;
      const propio = listos.get(clave);
      if (!propio) return false;                    // se quedan los hijos que ya estén
      lista.length = marca;
      lista.push(propio);
      return true;
    }
    if (!n.mesh || !n.mesh.geometry) return true;
    const propio = listos.get(clave);
    if (propio) { lista.push(propio); return true; }
    if (!bajando.has(clave) && !(fallidos.get(clave) > Date.now())) cola.push({ arbol, clave, n, px });
    return false;
  };

  const aImagen = async (blob) => {
    const foto = await createImageBitmap(blob), mayor = Math.max(foto.width, foto.height);
    if (mayor <= LADO_FOTO) return foto;
    const menor = await createImageBitmap(foto, { resizeWidth: Math.round(foto.width * LADO_FOTO / mayor), resizeHeight: Math.round(foto.height * LADO_FOTO / mayor), resizeQuality: "medium" });
    foto.close();
    return menor;
  };
  const pedir = ({ arbol, clave, n }) => {
    bajando.add(clave);
    const base = `${arbol.url}/nodes`, material = n.mesh.material;
    Promise.all([
      fetch(`${base}/${n.mesh.geometry.resource}/geometries/0`).then(bien).then((r) => r.arrayBuffer()),
      material ? fetch(`${base}/${material.resource}/textures/0`).then(bien).then((r) => r.blob()).then(aImagen) : null,
    ]).then(([datos, foto]) => {
      if (gl) porSubir.push({ clave, n, datos, foto });
      else if (foto) foto.close();
    }).catch(() => { fallidos.set(clave, Date.now() + 30000); })
      .finally(() => { bajando.delete(clave); repintar(); });
  };
  /* Pasa un nodo recién bajado a la tarjeta gráfica. El fichero de triángulos trae: cuántos vértices (4 bytes),
     otro número que no hace falta (4 bytes), las posiciones (x, y, z respecto al centro del nodo) y luego,
     para cada vértice, en qué punto de la foto cae (u, v). Cada tres vértices seguidos son un triángulo. */
  const subir = ({ clave, n, datos, foto }) => {
    const cuantos = datos.byteLength >= 8 ? new DataView(datos).getUint32(0, true) : 0;
    if (!cuantos || datos.byteLength < 8 + cuantos * 20) { if (foto) foto.close(); fallidos.set(clave, Date.now() + 600000); return; }
    const guardar = (trozo) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, trozo, gl.STATIC_DRAW); return b; };
    const posiciones = guardar(new Float32Array(datos, 8, cuantos * 3)), fotoXY = guardar(new Float32Array(datos, 8 + cuantos * 12, cuantos * 2));
    const textura = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, textura);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    if (foto) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, foto);
    else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([150, 150, 150, 255]));
    const potencia = (v) => (v & (v - 1)) === 0, reducciones = !!foto && (gl2 || (potencia(foto.width) && potencia(foto.height)));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, reducciones ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (reducciones) gl.generateMipmap(gl.TEXTURE_2D);
    if (foto) foto.close();
    listos.set(clave, { clave, m: medidas(n), posiciones, fotoXY, textura, cuantos, usado: fotograma });
  };
  const soltar = (t) => { gl.deleteBuffer(t.posiciones); gl.deleteBuffer(t.fotoXY); gl.deleteTexture(t.textura); listos.delete(t.clave); };

  return {
    id: "malla", type: "custom", renderingMode: "3d",
    estado: () => ({ listos: listos.size, bajando: bajando.size, pintados, paginas: arboles.reduce((s, a) => s + a.paginas.size, 0), fallidos: fallidos.size }),
    onAdd(m, contexto) {
      mapaGL = m; gl = contexto;
      gl2 = typeof WebGL2RenderingContext !== "undefined" && gl instanceof WebGL2RenderingContext;
      const sombreador = (tipo, texto) => { const s = gl.createShader(tipo); gl.shaderSource(s, texto); gl.compileShader(s); return s; };
      programa = gl.createProgram();
      gl.attachShader(programa, sombreador(gl.VERTEX_SHADER, "attribute vec3 a_pos; attribute vec2 a_uv; uniform mat4 u_m; varying vec2 v_uv; void main() { v_uv = a_uv; gl_Position = u_m * vec4(a_pos, 1.0); }"));
      gl.attachShader(programa, sombreador(gl.FRAGMENT_SHADER, "precision mediump float; uniform sampler2D u_t; varying vec2 v_uv; void main() { gl_FragColor = vec4(texture2D(u_t, v_uv).rgb, 1.0); }"));
      gl.linkProgram(programa);
      uMatriz = gl.getUniformLocation(programa, "u_m");
      aPos = gl.getAttribLocation(programa, "a_pos"); aUv = gl.getAttribLocation(programa, "a_uv");
    },
    onRemove() {
      for (const t of [...listos.values()]) soltar(t);
      for (const p of porSubir.splice(0)) if (p.foto) p.foto.close();
      if (programa) gl.deleteProgram(programa);
      gl = null; mapaGL = null;
    },
    render(_, datos) {
      if (!gl || !mapaGL) return;
      const M = datos && datos.defaultProjectionData ? datos.defaultProjectionData.mainMatrix : (datos && datos.modelViewProjectionMatrix) || datos;
      if (!M || M.length !== 16) return;
      fotograma += 1;
      /* El ojo es el único punto que la matriz manda al centro de la pantalla con profundidad nula:
         tres ecuaciones (x = 0, y = 0, w = 0) con tres incógnitas, resueltas por determinantes. */
      const a = M[0], b = M[4], c = M[8], d = M[1], e = M[5], f = M[9], g = M[3], h = M[7], k = M[11], p = -M[12], q = -M[13], r = -M[15];
      const det = a * (e * k - f * h) - b * (d * k - f * g) + c * (d * h - e * g);
      if (!det) return;
      const lienzo = mapaGL.getCanvas(), campo = (mapaGL.getVerticalFieldOfView ? mapaGL.getVerticalFieldOfView() : 36.87) * Math.PI / 180;
      vista = { M, base: (mapaGL.transform && mapaGL.transform.elevation) || 0, ancho: lienzo.clientWidth, alto: lienzo.clientHeight,
        focal: lienzo.clientHeight / (2 * Math.tan(campo / 2)), pasoW: Math.hypot(g, h, k),
        ojo: [(p * (e * k - f * h) - b * (q * k - f * r) + c * (q * h - e * r)) / det, (a * (q * k - f * r) - p * (d * k - f * g) + c * (d * r - q * g)) / det,
          (a * (e * r - q * h) - b * (d * r - q * g) + p * (d * h - e * g)) / det] };
      lista = []; cola = [];
      arboles.forEach((arbol, ia) => elegir(arbol, ia, 0));
      // Subir a la tarjeta lo que haya llegado (poco cada vez, para no dar tirones) y pedir lo que falta, lo más grande primero.
      for (const recien of porSubir.splice(0, 2)) subir(recien);
      if (porSubir.length) repintar();
      cola.sort((x, y) => y.px - x.px);
      for (const falta of cola) { if (bajando.size >= A_LA_VEZ) break; pedir(falta); }

      if (gl2) gl.bindVertexArray(null);
      gl.useProgram(programa);
      gl.disable(gl.STENCIL_TEST); gl.disable(gl.BLEND); gl.disable(gl.CULL_FACE);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true); gl.depthRange(0, 1); gl.colorMask(true, true, true, true);
      // La maqueta tapa el relieve que hay debajo, así que su profundidad se empieza de cero…
      gl.clearDepth(1); gl.clear(gl.DEPTH_BUFFER_BIT);
      gl.enableVertexAttribArray(aPos); gl.enableVertexAttribArray(aUv);
      gl.activeTexture(gl.TEXTURE0);
      const F = new Float32Array(16), lado = 1 / LADO_MUNDO;
      for (const t of lista) {
        // Matriz del mapa por la del nodo (ponerlo en su sitio y pasar sus metros a unidades del mapa).
        const m = t.m, z = (m.alto - vista.base) * m.porMetro;
        for (let j = 0; j < 4; j += 1) {
          F[j] = M[j] * lado; F[4 + j] = -M[4 + j] * lado; F[8 + j] = M[8 + j] * m.porMetro;
          F[12 + j] = M[j] * m.x + M[4 + j] * m.y + M[8 + j] * z + M[12 + j];
        }
        gl.uniformMatrix4fv(uMatriz, false, F);
        gl.bindBuffer(gl.ARRAY_BUFFER, t.posiciones); gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ARRAY_BUFFER, t.fotoXY); gl.vertexAttribPointer(aUv, 2, gl.FLOAT, false, 0, 0);
        gl.bindTexture(gl.TEXTURE_2D, t.textura);
        gl.drawArrays(gl.TRIANGLES, 0, t.cuantos);
        t.usado = fotograma;
      }
      gl.disableVertexAttribArray(aPos); gl.disableVertexAttribArray(aUv);
      // …y se deja a cero otra vez: lo que MapLibre pinta después (ruta, puntos, nombres) va siempre encima.
      gl.clear(gl.DEPTH_BUFFER_BIT);
      pintados = lista.length;
      if (listos.size > TOPE) for (const t of [...listos.values()].sort((x, y) => x.usado - y.usado).slice(0, listos.size - TOPE)) if (t.usado < fotograma) soltar(t);
    },
  };
}

/* Encender o apagar la maqueta. Con ella puesta, el relieve va a su altura real (sin exagerar) para que case. */
function ponerMalla(si) {
  if (!mapa3d) return;
  if (si && !mapa3d.getLayer("malla")) { malla = capaMalla(); mapa3d.addLayer(malla, "ruta-borde"); }
  if (!si && mapa3d.getLayer("malla")) { mapa3d.removeLayer("malla"); malla = null; }
  mapa3d.setTerrain({ source: "relieve", exaggeration: si ? 1 : 1.3 });
  const boton = $("boton-malla");
  boton.setAttribute("aria-pressed", String(!!si));
  boton.title = si ? "Quitar la maqueta fotográfica y ver solo relieve y prismas (gasta menos datos)" : "Ver la maqueta fotográfica del ICV: edificios y árboles con su forma real";
}
$("boton-malla").addEventListener("click", () => {
  const si = !mapa3d || !mapa3d.getLayer("malla");
  guardarLocal("osintmaps.malla.v1", si);
  ponerMalla(si);
  if (si) aviso3D("Maqueta fotográfica del ICV (vuelo de 2025). Solo cubre la provincia de València.");
});

