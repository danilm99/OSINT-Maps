"use strict";
/* OSINT Maps: herramientas sobre el mapa. Se carga la última y usa lo de los otros ficheros.

   1. Pestañas del panel: los sitios, lo que hay en el mapa de las capas encendidas y tus marcadores.
   2. Ruta entre dos puntos y medición de distancias, con una tarjeta sobre el mapa.
   3. Lo que se añade a las fichas: la foto y el resumen de las de Hispania Nostra. */

const servido = /^https?:$/.test(location.protocol) && !window.OSINT_DATOS;      // con «osintmaps servir», no como fichero suelto
const distanciaLegible = (m) => (m < 950 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toLocaleString("es-ES", { maximumFractionDigits: m < 10000 ? 1 : 0 })} km`);
function duracionLegible(s) {
  const min = Math.max(1, Math.round(s / 60));
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60 ? `${min % 60} min` : ""}`.trim();
}
function descargar(nombre, texto, tipo) {
  const enlace = el("a", { href: URL.createObjectURL(new Blob([texto], { type })), download: nombre });
  enlace.click();
  URL.revokeObjectURL(enlace.href);
}

/* ====================== 1. Pestañas y listas del panel ====================== */
const PESTANAS = [["sitios", "Sitios"], ["mapa", "En el mapa"], ["marcadores", "Marcadores"]];
const SIN_LISTA = new Set(["edificios", "farolas", "panoramax"]);      // demasiados y sin nombre: se ven en el mapa, no en la lista
const MAX_LISTA = 150;
let pestana = "sitios";

function ponerPestana(cual) {
  pestana = PESTANAS.some((p) => p[0] === cual) ? cual : "sitios";
  guardarLocal("osintmaps.pestana.v1", pestana);
  $("panel").dataset.pestana = pestana;
  for (const b of $("pestanas").children) b.setAttribute("aria-selected", String(b.dataset.pestana === pestana));
  pintarListas();
}
for (const [id, texto] of PESTANAS) {
  const b = el("button", { type: "button", role: "tab" }, texto, el("small", { id: `cuenta-${id}` }));
  b.dataset.pestana = id;
  b.addEventListener("click", () => {
    if (seleccion || panelOcupado()) { soltarMarcador(); mostrarLista(); if (candidatos.length) filtrar(); }
    ponerPestana(id);
  });
  $("pestanas").append(b);
}

/* Lo que hay de las capas encendidas dentro de lo que se ve, de más cerca a más lejos del centro. */
function elementosEnVista() {
  const vista = mapa.getBounds(), centro = mapa.getCenter(), salida = [];
  for (const capa of CAPAS) {
    if (!estaActiva(capa) || SIN_LISTA.has(capa.id)) continue;
    for (const e of estado[capa.id].elementos.values()) if (vista.contains([e.lat, e.lon])) salida.push([capa, e, mapa.distance(centro, [e.lat, e.lon])]);
  }
  if ($("capa-camaras").checked) for (const c of camaras.values()) if (vista.contains([c.lat, c.lon])) salida.push([CAPA.camaras, elementoDeCamara(c), mapa.distance(centro, [c.lat, c.lon])]);
  return salida.sort((a, b) => a[2] - b[2]);
}
function filaDeLista(simboloNodo, titulo, detalle, alPulsar) {
  const b = el("button", { type: "button" }, simboloNodo, el("b", { textContent: titulo }), el("small", { textContent: detalle }));
  b.addEventListener("click", alPulsar);
  return el("li", {}, b);
}
function exportarVista() {
  const features = elementosEnVista().map(([capa, e]) => ({
    type: "Feature",
    geometry: e.linea ? { type: "LineString", coordinates: e.linea.map(([lat, lon]) => [lon, lat]) } : { type: "Point", coordinates: [e.lon, e.lat] },
    properties: Object.assign({ capa: capa.nombre, nombre: e.nombre }, Object.fromEntries((e.datos || []).filter((d) => d[1] != null && d[1] !== "")), e.etiquetas || {}, e.url ? { url: e.url } : {}),
  }));
  descargar("osintmaps-vista.geojson", JSON.stringify({ type: "FeatureCollection", features }), "application/geo+json");
}
function pintarListaCapas() {
  const todos = elementosEnVista();
  $("cuenta-mapa").textContent = todos.length ? String(todos.length) : "";
  if (pestana !== "mapa") return;
  const lista = $("lista-capas");
  if (!todos.length) {
    lista.replaceChildren(el("li", { className: "hueco", textContent: "De las capas encendidas no hay nada en esta zona. Enciende alguna en «Capas», arriba a la derecha, o acerca el mapa: muchas solo se cargan de cerca." }));
    return;
  }
  const guardar = el("button", { type: "button" }, iconoSVG("descargar", 16), el("span", { textContent: "Guardar como GeoJSON" }));
  guardar.addEventListener("click", exportarVista);
  lista.replaceChildren(el("li", { className: "cabecera-lista" }, el("span", { textContent: todos.length > MAX_LISTA ? `Los ${MAX_LISTA} más cercanos al centro, de ${todos.length}` : `${todos.length} en lo que se ve` }), guardar),
    ...todos.slice(0, MAX_LISTA).map(([capa, e, d]) => filaDeLista(simboloDe(capa, e.color, 24), e.nombre || capa.nombre, `${capa.nombre} · a ${distanciaLegible(d)}`, () => abrirElemento(e, !mapa.getBounds().pad(-0.15).contains([e.lat, e.lon])))));
}
function pintarListaMarcadores() {
  const mios = Object.entries(marcadores).filter(([, m]) => !m.deleted).sort((a, b) => b[1].created - a[1].created);
  $("cuenta-marcadores").textContent = mios.length ? String(mios.length) : "";
  if (pestana !== "marcadores") return;
  const lista = $("lista-marcadores"), centro = mapa.getCenter();
  if (!mios.length) {
    lista.replaceChildren(el("li", { className: "hueco", textContent: "Aún no tienes marcadores. Pulsa con el botón derecho en el mapa (o mantén pulsado en el móvil) y elige «Añadir un marcador aquí»." }));
    return;
  }
  lista.replaceChildren(...mios.map(([id, m]) => filaDeLista(simboloSVG(ICONO_MARCADOR[m.type], TIPOS_MARCADOR[m.type][1], "circulo", 24),
    m.note.split("\n")[0].slice(0, 80) || TIPOS_MARCADOR[m.type][0],
    `${TIPOS_MARCADOR[m.type][0]} · ${new Date(m.created).toLocaleDateString("es-ES")} · a ${distanciaLegible(mapa.distance(centro, [m.lat, m.lng]))}`,
    () => { mapa.setView([m.lat, m.lng], Math.max(mapa.getZoom(), 17)); abrirMarcador(id); })));
}
function pintarListas() { pintarListaCapas(); pintarListaMarcadores(); }
let relojListas = null;
const programarListas = () => { clearTimeout(relojListas); relojListas = setTimeout(pintarListas, 250); };
function alCambiarCapas() { programarListas(); }
mapa.on("moveend", programarListas);
$("capa-camaras").addEventListener("change", programarListas);
{
  // Cada vez que cambian los marcadores (crear, mover, borrar, recuperar una copia) se repinta su lista.
  const original = pintarMarcadores;
  pintarMarcadores = function () { original(); pintarListaMarcadores(); };
}
ponerPestana(leerLocal("osintmaps.pestana.v1", "sitios"));

/* ====================== 2. Ruta y medición ====================== */
const tarjeta = $("tarjeta-mapa");
function ponerTarjeta(...nodos) { tarjeta.replaceChildren(...nodos); tarjeta.hidden = !nodos.length; }
const botonTarjeta = (texto, hacer, pulsado) => {
  const b = el("button", { type: "button", textContent: texto });
  if (pulsado != null) b.setAttribute("aria-pressed", String(pulsado));
  b.addEventListener("click", hacer);
  return b;
};
const AZUL = "#1a73e8";
const extremo = (ll, relleno) => L.circleMarker(ll, { radius: 7, color: "#ffffff", weight: 3, fillColor: relleno, fillOpacity: 1, interactive: false });
const trazo = (puntos, color, discontinuo) => [L.polyline(puntos, { color: "#17242e", weight: 8, opacity: 0.55, interactive: false }),
  L.polyline(puntos, { color, weight: 4.5, opacity: 1, interactive: false, dashArray: discontinuo || null })];

/* --- Ruta: el camino lo calcula el servidor público de OpenStreetMap (OSRM), a pie o en coche. --- */
const RUTAS = { pie: ["A pie", "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"], coche: ["En coche", "https://routing.openstreetmap.de/routed-car/route/v1/driving/"] };
const ruta = { origen: null, destino: null, modo: RUTAS[leerLocal("osintmaps.modo-ruta.v1", "pie")] ? leerLocal("osintmaps.modo-ruta.v1", "pie") : "pie", turno: 0, capa: L.layerGroup().addTo(mapa) };
function quitarRuta() { ruta.turno++; ruta.origen = ruta.destino = null; ruta.capa.clearLayers(); ponerTarjeta(); }
function posicionDelAparato() {
  return new Promise((ok, no) => (navigator.geolocation ? navigator.geolocation.getCurrentPosition((p) => ok(L.latLng(p.coords.latitude, p.coords.longitude)), no, { enableHighAccuracy: true, timeout: 8000 }) : no(new Error("sin geolocalización"))));
}
function rutaDesde(ll) { terminarMedida(true); ruta.origen = ll; calcularRuta(); }
function rutaHasta(ll, nombre) {
  terminarMedida(true);
  ruta.destino = ll; ruta.nombre = nombre || "";
  if (ruta.origen) { calcularRuta(); return; }
  // Sin origen elegido se prueba con la posición del aparato; si no la da, se pide que se marque en el mapa.
  calcularRuta();
  posicionDelAparato().then((p) => { if (!ruta.origen && ruta.destino === ll) { ruta.origen = p; calcularRuta(); } }).catch(() => { /* se queda pidiendo el origen */ });
}
function calcularRuta() {
  const turno = ++ruta.turno, quitar = botonTarjeta("Quitar", quitarRuta);
  ruta.capa.clearLayers();
  if (ruta.origen) extremo(ruta.origen, "#17242e").addTo(ruta.capa);
  if (ruta.destino) extremo(ruta.destino, AZUL).addTo(ruta.capa);
  if (!ruta.origen || !ruta.destino) {
    ponerTarjeta(el("span", { textContent: ruta.origen ? "Ahora elige el destino: botón derecho en el mapa, «Ruta hasta aquí», o el botón «Ruta» de una ficha." : "Elige el origen: botón derecho en el mapa y «Ruta desde aquí»." }), quitar);
    return;
  }
  const modos = el("span", { className: "grupo-botones" }, ...Object.entries(RUTAS).map(([id, [nombre]]) => botonTarjeta(nombre, () => { ruta.modo = id; guardarLocal("osintmaps.modo-ruta.v1", id); calcularRuta(); }, ruta.modo === id)));
  const invertir = botonTarjeta("Invertir", () => { [ruta.origen, ruta.destino] = [ruta.destino, ruta.origen]; calcularRuta(); });
  ponerTarjeta(el("span", { textContent: "Calculando la ruta…" }), modos, quitar);
  const o = ruta.origen, d = ruta.destino;
  pedirJ(`${RUTAS[ruta.modo][1]}${o.lng.toFixed(6)},${o.lat.toFixed(6)};${d.lng.toFixed(6)},${d.lat.toFixed(6)}?overview=full&geometries=geojson`, null, 25000).then((j) => {
    if (turno !== ruta.turno) return;
    const r = (j.routes || [])[0];
    if (j.code !== "Ok" || !r) throw new Error("sin ruta");
    const puntos = r.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
    // El tramo calculado va por calles y caminos; lo que falta hasta cada extremo, en discontinuo.
    for (const capa of [...trazo(puntos, AZUL), ...trazo([[o.lat, o.lng], puntos[0]], AZUL, "2 9"), ...trazo([puntos[puntos.length - 1], [d.lat, d.lng]], AZUL, "2 9")]) capa.addTo(ruta.capa);
    extremo(o, "#17242e").addTo(ruta.capa); extremo(d, AZUL).addTo(ruta.capa);
    if (!mapa.getBounds().contains(L.latLngBounds(puntos))) mapa.fitBounds(L.latLngBounds(puntos).pad(0.15));
    ponerTarjeta(el("b", { textContent: `${distanciaLegible(r.distance)} · ${duracionLegible(r.duration)}` }),
      el("span", { textContent: ruta.nombre ? `hasta ${ruta.nombre.slice(0, 40)}` : "" }), modos, invertir, quitar);
  }).catch(() => { if (turno === ruta.turno) ponerTarjeta(el("span", { textContent: "No se ha podido calcular la ruta entre esos dos puntos." }), modos, quitar); });
}

/* --- Medir: cada clic añade un punto; la tarjeta lleva la cuenta. --- */
const medida = { puntos: [], capa: L.layerGroup().addTo(mapa) };
function pintarMedida() {
  medida.capa.clearLayers();
  for (const capa of trazo(medida.puntos, "#ffffff", "6 7")) capa.addTo(medida.capa);
  medida.puntos.forEach((p, k) => extremo(p, k ? "#e5007d" : "#17242e").addTo(medida.capa));
  let total = 0;
  for (let k = 1; k < medida.puntos.length; k++) total += mapa.distance(medida.puntos[k - 1], medida.puntos[k]);
  const botones = midiendo
    ? [botonTarjeta("Deshacer", () => { if (medida.puntos.length > 1) medida.puntos.pop(); pintarMedida(); }), botonTarjeta("Terminar", () => terminarMedida(false))]
    : [botonTarjeta("Quitar", () => terminarMedida(true))];
  ponerTarjeta(el("b", { textContent: distanciaLegible(total) }),
    el("span", { textContent: midiendo ? (medida.puntos.length < 2 ? "Toca el mapa para añadir puntos." : `${medida.puntos.length - 1} ${medida.puntos.length === 2 ? "tramo" : "tramos"}, en línea recta.`) : "en línea recta" }), ...botones);
}
function medirDesde(ll) {
  quitarRuta();
  midiendo = true;
  medida.puntos = [ll];
  $("mapa").classList.add("colocando");
  pintarMedida();
}
function terminarMedida(borrar) {
  const habia = midiendo || medida.puntos.length > 0;
  midiendo = false;
  $("mapa").classList.remove("colocando");
  if (borrar || medida.puntos.length < 2) { medida.puntos = []; medida.capa.clearLayers(); if (habia) ponerTarjeta(); } else pintarMedida();
}
mapa.on("click", (ev) => { if (midiendo) { medida.puntos.push(ev.latlng); pintarMedida(); } });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && midiendo) terminarMedida(false); });

/* ====================== 3. Fichas de Hispania Nostra: foto y resumen ====================== */
{
  const original = abrirElemento;
  abrirElemento = function (e, mover) {
    original(e, mover);
    if (elementoAbierto !== e || e.capa !== "listaroja" || !e.url || !servido) return;
    const poner = (d) => {
      if (elementoAbierto !== e || !d) return;
      const ficha = $("ficha-elemento");
      if (d.imagen && urlSegura(d.imagen)) {
        e.imagen = d.imagen; e.imagenes = (d.imagenes || []).filter(urlSegura); e.credito = "Hispania Nostra";
        ficha.querySelector(".portada img").src = d.imagen;
        ficha.querySelector(".portada span").textContent = e.imagenes.length > 1 ? `${e.imagenes.length} fotos de Hispania Nostra` : "Foto de Hispania Nostra";
      }
      if (d.descripcion && !ficha.querySelector(".descripcion")) ficha.querySelector(".vistas").after(el("p", { className: "descripcion", textContent: d.descripcion }));
    };
    if (e.detalle) poner(e.detalle);
    else pedirJ(`vivo/ficha?url=${encodeURIComponent(e.url)}`, null, 25000).then((d) => { e.detalle = d; poner(d); }).catch(() => { /* se queda con la ortofoto */ });
  };
}
