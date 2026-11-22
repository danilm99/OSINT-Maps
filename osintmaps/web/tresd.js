"use strict";
/* OSINT Maps: la vista en 3D. Se carga la última y usa lo de los otros ficheros.

   Qué es: el mismo sitio visto en perspectiva, con el relieve del terreno, la foto aérea pegada
   encima y los edificios levantados con su altura. No es una maqueta fotográfica como la de
   Google Earth (de València no hay ninguna pública): cada edificio es un prisma con la altura
   que consta en OpenStreetMap, y donde no consta, una altura por defecto.

   De dónde sale cada cosa:
   - El dibujo lo hace MapLibre GL, una biblioteca que pinta mapas con la tarjeta gráfica. Pesa
     un megabyte, así que solo se descarga la primera vez que se pulsa «3D».
   - El relieve: teselas públicas de altitud (imágenes en las que cada punto guarda una altura).
   - La foto: las mismas tres fuentes que en 2D, una sobre otra (PNOA en toda España, encima la
     del ICV en la provincia de València y encima la del Ayuntamiento en la ciudad).
   - Los edificios y los nombres: OpenFreeMap, que sirve los datos de OpenStreetMap troceados.

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
      mapa3d.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
      // (MapLibre los despliega al cargar; se recogen en cuanto termina de pintar por primera vez)
      const recogerCreditos = () => { const c = $("vista3d").querySelector(".maplibregl-ctrl-attrib"); if (c && c.classList.contains("maplibregl-compact")) { c.classList.remove("maplibregl-compact-show"); c.removeAttribute("open"); } };
      mapa3d.once("load", recogerCreditos); mapa3d.once("idle", recogerCreditos);
      mapa3d.on("load", () => {
        mapa3d.setTerrain({ source: "relieve", exaggeration: 1.3 });
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
