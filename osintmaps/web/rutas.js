"use strict";
/* OSINT Maps: cómo llegar. Se carga después de herramientas.js y usa lo de los otros ficheros
   (mapa, el, $, la tarjeta sobre el mapa, el callejero del buscador...).

   De dónde sale cada cosa:
   - A pie, en coche y en bici: los servidores públicos de OSRM que mantiene la comunidad alemana
     de OpenStreetMap. Devuelven el camino, alternativas y las maniobras una a una.
   - En transporte público: Transitous, un planificador abierto que junta los horarios que
     publican las empresas de medio mundo (aquí, EMT, Metrovalencia, Renfe, MetroBus...).
     Devuelve varios viajes posibles, con sus tramos a pie y en cada línea.

   Cómo está organizado:
   1. Los dos extremos (origen y destino) y de dónde se eligen.
   2. El cálculo de cada modo, convertido a una forma común («opción»).
   3. El dibujo en el mapa y la ficha del panel.
   4. Seguir la posición: cuánto queda y si hay que recalcular. */

const PERFIL_OSRM = { pie: "routed-foot/route/v1/foot", coche: "routed-car/route/v1/driving", bici: "routed-bike/route/v1/bike" };
const MODOS_RUTA = [["pie", "A pie", "pie"], ["publico", "Transporte", "bus"], ["coche", "Coche", "coche"], ["bici", "Bici", "bici"]];
const GRIS_RUTA = "#5f6b76";
const ruta = {
  origen: null, destino: null,      // { ll, nombre, yo } («yo»: es la posición del aparato y se va actualizando)
  modo: MODOS_RUTA.some((m) => m[0] === leerLocal("osintmaps.modo-ruta.v1", "pie")) ? leerLocal("osintmaps.modo-ruta.v1", "pie") : "pie",
  turno: 0, calculo: {}, eligiendo: null, cuando: { tipo: "ahora", hora: "" },
  capa: L.layerGroup().addTo(mapa), marcaPaso: L.circleMarker([0, 0], { radius: 9, color: "#ffffff", weight: 3, fillColor: "#e5007d", fillOpacity: 1, interactive: false }),
};
const hayRuta = () => !!(ruta.origen || ruta.destino);
const coordenadasCortas = (ll) => `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}`;

/* ====================== 1. Los extremos ====================== */
function posicionDelAparato() {
  if (miPosicion && Date.now() - (miPosicion.hora || 0) < 60000) return Promise.resolve(L.latLng(miPosicion.lat, miPosicion.lon));
  return new Promise((ok, no) => (navigator.geolocation ? navigator.geolocation.getCurrentPosition((p) => ok(L.latLng(p.coords.latitude, p.coords.longitude)), no, { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 })
    : no(new Error("sin geolocalización"))));
}
function ponerExtremo(cual, extremo) {
  ruta[cual] = extremo;
  ruta.eligiendo = null;
  ruta.aviso = "";
  if (camposRuta[cual]) camposRuta[cual].blur();      // (si no, el campo se queda con lo que se estaba escribiendo)
  $("mapa").classList.remove("colocando");
  calcularRuta();
}
/* Pone «mi posición» en un extremo. Si el aparato no la da, lo dice y deja el campo listo para escribir. */
function usarMiPosicion(cual) {
  ruta[cual] = { ll: null, nombre: "Tu posición", yo: true, buscando: true };
  ruta.aviso = "";
  if (camposRuta[cual]) camposRuta[cual].blur();
  pintarFichaRuta(); pintarTarjetaRuta();
  posicionDelAparato().then((ll) => {
    if (!ruta[cual] || !ruta[cual].yo) return;
    ruta[cual] = { ll, nombre: "Tu posición", yo: true };
    if (typeof localizar === "function" && !miPosicion) localizar(true);      // de paso, el punto azul
    calcularRuta();
  }).catch(() => {
    if (!ruta[cual] || !ruta[cual].yo) return;
    ruta[cual] = null;
    ruta.aviso = "No se ha podido saber dónde estás. Escribe el punto de salida o elígelo en el mapa.";
    pintarFichaRuta();
  });
}
function rutaHasta(ll, nombre) {
  if (typeof terminarMedida === "function") terminarMedida(true);
  ruta.destino = { ll, nombre: nombre || coordenadasCortas(ll) };
  ruta.aviso = "";
  abrirRuta();
  if (!ruta.origen) usarMiPosicion("origen"); else calcularRuta();
}
function rutaDesde(ll, nombre) {
  if (typeof terminarMedida === "function") terminarMedida(true);
  ruta.origen = { ll, nombre: nombre || coordenadasCortas(ll) };
  ruta.aviso = "";
  abrirRuta();
  calcularRuta();
}
function quitarRuta() {
  ruta.turno++;
  ruta.origen = ruta.destino = null; ruta.calculo = {}; ruta.eligiendo = null; ruta.aviso = "";
  ruta.capa.clearLayers(); mapa.removeLayer(ruta.marcaPaso);
  $("mapa").classList.remove("colocando");
  ponerTarjeta();
  if (!$("ficha-ruta").hidden) { mostrarLista(); if (candidatos.length) filtrar(); }
}
/* Elegir un extremo tocando el mapa. */
mapa.on("click", (ev) => {
  if (!ruta.eligiendo || midiendo || colocando) return;
  ponerExtremo(ruta.eligiendo, { ll: ev.latlng, nombre: coordenadasCortas(ev.latlng) });
  abrirRuta();
});

/* ====================== 2. El cálculo ====================== */
/* Las líneas llegan comprimidas (el formato «polyline» de Google): cada número es la diferencia
   con el anterior, troceada en grupos de 5 bits. `precision` son los decimales que se guardaron. */
function descifrarLinea(texto, precision = 5) {
  const factor = 10 ** precision, puntos = [];
  let i = 0, lat = 0, lon = 0;
  const siguiente = () => {
    let resultado = 0, desplazamiento = 0, trozo;
    do { trozo = texto.charCodeAt(i++) - 63; resultado += (trozo & 0x1f) * 2 ** desplazamiento; desplazamiento += 5; } while (trozo >= 0x20 && i < texto.length + 1);
    return resultado % 2 ? -(resultado + 1) / 2 : resultado / 2;
  };
  while (i < texto.length) { lat += siguiente(); lon += siguiente(); puntos.push([lat / factor, lon / factor]); }
  return puntos;
}

const HACIA = { left: "a la izquierda", right: "a la derecha", "slight left": "ligeramente a la izquierda", "slight right": "ligeramente a la derecha",
  "sharp left": "del todo a la izquierda", "sharp right": "del todo a la derecha", straight: "recto", uturn: "en sentido contrario" };
const ORDINAL = ["", "primera", "segunda", "tercera", "cuarta", "quinta", "sexta", "séptima", "octava"];
/* Una maniobra de OSRM, dicha como la diría alguien que da indicaciones. */
function instruccion(paso) {
  const m = paso.maneuver || {}, via = paso.name || paso.ref || "", por = via ? ` por ${via}` : "", a = via ? ` hacia ${via}` : "";
  const lado = HACIA[m.modifier] || "", gira = lado && lado !== "recto" ? ` ${lado}` : "";
  switch (m.type) {
    case "depart": return `Sal${por}`;
    case "arrive": return `Has llegado${m.modifier === "left" ? ": queda a la izquierda" : m.modifier === "right" ? ": queda a la derecha" : ""}`;
    case "turn": return m.modifier === "straight" ? `Sigue recto${por}` : m.modifier === "uturn" ? `Da la vuelta${por}` : `Gira ${lado}${a}`;
    case "continue": return !gira ? `Continúa${por}` : m.modifier === "uturn" ? `Da la vuelta${por}` : `Gira ${lado} para seguir${por}`;
    case "merge": return `Incorpórate${gira}${via ? ` a ${via}` : ""}`;
    case "on ramp": return `Toma la entrada${gira}${a}`;
    case "off ramp": return `Toma la salida${gira}${paso.destinations ? ` hacia ${paso.destinations.split(",")[0].replace(/^[^:]*:\s*/, "")}` : a}`;
    case "fork": return `En la bifurcación, mantente ${/left/.test(m.modifier || "") ? "a la izquierda" : "a la derecha"}${a}`;
    case "end of road": return `Al final de la calle, gira ${lado || "donde sigue el camino"}${a}`;
    case "roundabout": case "rotary": return `En la rotonda, toma la ${ORDINAL[m.exit] || `${m.exit || ""}.ª`} salida${a}`;
    case "roundabout turn": return `En la rotonda, gira ${lado || "donde sigue el camino"}${a}`;
    default: return `Continúa${por}`;      // «new name», «notification», «use lane»...
  }
}
function iconoDeGiro(m) {
  if (m.type === "arrive") return "g_llegada";
  if (/roundabout|rotary/.test(m.type || "")) return "g_rotonda";
  if (m.type === "depart" || m.type === "new name") return "g_recto";
  return { left: "g_izquierda", "sharp left": "g_izquierda", right: "g_derecha", "sharp right": "g_derecha", "slight left": "g_leve_izquierda", "slight right": "g_leve_derecha", uturn: "g_vuelta" }[m.modifier] || "g_recto";
}
function opcionDeOSRM(r, modo) {
  const puntos = r.geometry.coordinates.map(([lon, lat]) => [lat, lon]), pasos = [];
  for (const p of (r.legs || []).flatMap((l) => l.steps || [])) {
    const m = p.maneuver || {};
    // «Salir de la rotonda» va ya dicho en «toma la segunda salida»: su tramo se suma al anterior.
    if (/^exit (roundabout|rotary)$/.test(m.type)) { if (pasos.length) pasos[pasos.length - 1].metros += p.distance || 0; continue; }
    pasos.push({ icono: iconoDeGiro(m), texto: instruccion(p), metros: p.distance || 0, ll: m.location ? [m.location[1], m.location[0]] : null });
  }
  return { duracion: r.duration, distancia: r.distance, resumen: ((r.legs || [])[0] || {}).summary || "", pasos,
    tramos: [{ puntos, color: AZUL, discontinuo: modo === "pie" ? "1 9" : null }] };
}
const horaCorta = (iso) => { const t = new Date(iso); return Number.isNaN(+t) ? "" : t.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }); };
function opcionDeTransitous(it) {
  const tramos = [], pasos = [], resumen = [], ultimo = it.legs.length - 1;
  it.legs.forEach((l, k) => {
    const aPie = l.mode === "WALK", g = l.legGeometry || {};
    let puntos = [];
    try { puntos = g.points ? descifrarLinea(g.points, g.precision || 7) : []; } catch { puntos = []; }
    if (puntos.length < 2) puntos = [[l.from.lat, l.from.lon], [l.to.lat, l.to.lon]];
    const desde = k === 0 ? ruta.origen.nombre : l.from.name, hasta = k === ultimo ? ruta.destino.nombre : l.to.name;
    const color = aPie ? GRIS_RUTA : /^[0-9a-f]{6}$/i.test(l.routeColor || "") ? `#${l.routeColor}` : esSobreRailes(l.mode) ? "#b91c1c" : "#1d4ed8";
    const intermedias = (l.intermediateStops || []).filter((s) => Number.isFinite(s.lat));
    tramos.push({ puntos, color, discontinuo: aPie ? "1 9" : null, paradas: aPie ? null : [[l.from.lat, l.from.lon], ...intermedias.map((s) => [s.lat, s.lon]), [l.to.lat, l.to.lon]] });
    if (aPie) {
      if (l.duration < 60 && k !== 0 && k !== ultimo) return;      // un transbordo en el mismo andén no merece una línea
      resumen.push({ pie: Math.max(1, Math.round(l.duration / 60)) });
      pasos.push({ icono: "pie", texto: `Camina ${duracionLegible(l.duration)}${l.distance ? ` (${distanciaLegible(l.distance)})` : ""} hasta ${hasta}`, ll: [l.from.lat, l.from.lon] });
    } else {
      const linea = { nombre: l.routeShortName || l.displayName || "", color: l.routeColor, texto: l.routeTextColor, modo: l.mode };
      resumen.push({ linea });
      pasos.push({ linea, texto: `${modoTransporte(l.mode).replace(/^./, (x) => x.toUpperCase())}${l.headsign ? ` hacia ${l.headsign}` : ""}`, ll: [l.from.lat, l.from.lon],
        detalle: `Sube en ${desde} a las ${horaCorta(l.from.departure || l.startTime)} y baja en ${hasta} a las ${horaCorta(l.to.arrival || l.endTime)}` +
          (intermedias.length ? ` (${intermedias.length + 1} paradas)` : "") + (l.agencyName ? `. ${l.agencyName}` : ""),
        directo: !!l.realTime, intermedias: intermedias.map((s) => `${horaCorta(s.arrival || s.departure)} ${s.name}`) });
    }
  });
  return { duracion: it.duration, sale: new Date(it.startTime), llega: new Date(it.endTime), cambios: it.transfers || 0, resumen, tramos, pasos,
    distancia: null, primeraLinea: (it.legs.find((l) => l.mode !== "WALK") || {}).from };
}
function pedirOpciones(modo, o, d) {
  if (modo !== "publico") {
    const par = `${o.lng.toFixed(6)},${o.lat.toFixed(6)};${d.lng.toFixed(6)},${d.lat.toFixed(6)}`;
    return pedirJ(`https://routing.openstreetmap.de/${PERFIL_OSRM[modo]}/${par}?overview=full&geometries=geojson&steps=true&alternatives=true`, null, 30000).then((j) => {
      if (j.code !== "Ok" || !(j.routes || []).length) return [];
      return j.routes.slice(0, 3).map((r) => opcionDeOSRM(r, modo));
    });
  }
  const c = ruta.cuando, hora = c.tipo !== "ahora" && c.hora ? new Date(c.hora) : new Date();
  const consulta = new URLSearchParams({ fromPlace: `${o.lat.toFixed(6)},${o.lng.toFixed(6)}`, toPlace: `${d.lat.toFixed(6)},${d.lng.toFixed(6)}`, time: (Number.isNaN(+hora) ? new Date() : hora).toISOString(),
    arriveBy: String(c.tipo === "llegar"), numItineraries: "5" });
  return pedirJ(`${TRANSITOUS}/plan?${consulta}`, null, 40000).then((j) => (j.itineraries || []).filter((it) => (it.legs || []).some((l) => l.mode !== "WALK")).slice(0, 6).map(opcionDeTransitous)
    .sort((a, b) => (c.tipo === "llegar" ? b.sale - a.sale : a.llega - b.llega)));
}
/* Calcula el modo elegido y, sin prisa, los demás: así cada pestaña enseña lo que se tarda. */
function calcularRuta() {
  const turno = ++ruta.turno;
  ruta.calculo = {};
  mapa.removeLayer(ruta.marcaPaso);
  const o = ruta.origen && ruta.origen.ll, d = ruta.destino && ruta.destino.ll;
  if (!o || !d) { dibujarRuta(); pintarFichaRuta(); pintarTarjetaRuta(); return; }
  const calcular = (modo) => {
    if (turno !== ruta.turno || ruta.calculo[modo]) return Promise.resolve();
    ruta.calculo[modo] = { estado: "cargando", opciones: [], elegida: 0 };
    if (modo === ruta.modo) { pintarFichaRuta(); pintarTarjetaRuta(); }
    return pedirOpciones(modo, o, d).then((opciones) => { if (turno === ruta.turno) ruta.calculo[modo] = { estado: opciones.length ? "bien" : "vacio", opciones, elegida: 0 }; },
      () => { if (turno === ruta.turno) ruta.calculo[modo] = { estado: "fallo", opciones: [], elegida: 0 }; })
      .then(() => { if (turno !== ruta.turno) return; if (modo === ruta.modo) { dibujarRuta(true); pintarTarjetaRuta(); } pintarFichaRuta(); });
  };
  dibujarRuta();
  ruta.calcular = calcular;
  // (los servidores son de voluntarios: los otros modos se piden de uno en uno y dejando un respiro)
  calcular(ruta.modo).then(async () => {
    for (const [modo] of MODOS_RUTA) { if (turno !== ruta.turno) return; if (!ruta.calculo[modo]) { await esperar(450); await calcular(modo); } }
  });
}
function ponerModo(modo) {
  ruta.modo = modo;
  guardarLocal("osintmaps.modo-ruta.v1", modo);
  mapa.removeLayer(ruta.marcaPaso);
  if (!ruta.calculo[modo] && ruta.calcular) ruta.calcular(modo); else { dibujarRuta(true); pintarFichaRuta(); pintarTarjetaRuta(); }
}
const calculoActual = () => ruta.calculo[ruta.modo] || null;
const opcionActual = () => { const c = calculoActual(); return c && c.estado === "bien" ? c.opciones[c.elegida] : null; };

/* ====================== 3. El dibujo y la ficha ====================== */
function dibujarRuta(encuadrar) {
  ruta.capa.clearLayers();
  const o = ruta.origen && ruta.origen.ll, d = ruta.destino && ruta.destino.ll, c = calculoActual(), elegida = opcionActual();
  if (c && c.estado === "bien") {
    // Las alternativas, debajo y en gris: se pueden elegir tocándolas.
    c.opciones.forEach((op, k) => {
      if (k === c.elegida) return;
      for (const t of op.tramos) L.polyline(t.puntos, { color: "#ffffff", weight: 9, opacity: 0.55, interactive: false }).addTo(ruta.capa);
      for (const t of op.tramos) {
        const linea = L.polyline(t.puntos, { color: "#7b8794", weight: 5.5, opacity: 0.95 }).addTo(ruta.capa);
        linea.on("click", (ev) => { L.DomEvent.stopPropagation(ev); elegirOpcion(k); });
        linea.bindTooltip(`${duracionLegible(op.duracion)}${op.distancia ? ` · ${distanciaLegible(op.distancia)}` : ""}: pulsa para elegirla`, { sticky: true });
      }
    });
    for (const t of elegida.tramos) for (const capa of trazo(t.puntos, t.color, t.discontinuo)) { if (t.discontinuo) capa.options.lineCap = "round"; capa.addTo(ruta.capa); }
    for (const t of elegida.tramos) for (const p of t.paradas || []) L.circleMarker(p, { radius: 4.5, color: t.color, weight: 2.5, fillColor: "#ffffff", fillOpacity: 1, interactive: false }).addTo(ruta.capa);
    // Lo que falta desde cada extremo hasta donde empieza el camino calculado, punteado.
    const primero = elegida.tramos[0].puntos[0], ultimo = elegida.tramos[elegida.tramos.length - 1].puntos.slice(-1)[0];
    for (const capa of [...trazo([[o.lat, o.lng], primero], GRIS_RUTA, "1 8"), ...trazo([ultimo, [d.lat, d.lng]], GRIS_RUTA, "1 8")]) capa.addTo(ruta.capa);
    if (encuadrar) {
      const caja = L.latLngBounds(elegida.tramos.flatMap((t) => t.puntos)).extend(o).extend(d);
      if (!mapa.getBounds().pad(-0.08).contains(caja) || mapa.getBoundsZoom(caja) > mapa.getZoom() + 2) mapa.fitBounds(caja.pad(0.12), { maxZoom: 18 });
    }
  }
  if (o) extremo(o, "#17242e").addTo(ruta.capa);
  if (d) extremo(d, "#d93025").addTo(ruta.capa);
  if (typeof refrescar3D === "function") refrescar3D();      // la misma ruta, en la vista en 3D si está abierta
}
function elegirOpcion(k) {
  const c = calculoActual();
  if (!c || !c.opciones[k]) return;
  c.elegida = k;
  mapa.removeLayer(ruta.marcaPaso);
  dibujarRuta(); pintarFichaRuta(); pintarTarjetaRuta();
}
/* La tarjeta sobre el mapa: el resumen, por si el panel está recogido o se está mirando otra ficha. */
function pintarTarjetaRuta() {
  cuidarPantalla();
  if (!hayRuta()) { ponerTarjeta(); return; }
  const quitar = botonTarjeta("Quitar", quitarRuta), ver = botonTarjeta($("ficha-ruta").hidden ? "Ver la ruta" : "Pasos", abrirRuta);
  const c = calculoActual(), op = opcionActual(), nombreModo = MODOS_RUTA.find((m) => m[0] === ruta.modo)[1].toLowerCase();
  if (ruta.eligiendo) { ponerTarjeta(el("span", { textContent: `Toca en el mapa el punto de ${ruta.eligiendo === "origen" ? "salida" : "llegada"}.` }), quitar); return; }
  if (!ruta.origen || !ruta.destino || !ruta.origen.ll) { ponerTarjeta(el("span", { textContent: ruta.origen && ruta.origen.buscando ? "Buscando tu posición…" : ruta.origen ? "Falta el destino de la ruta." : "Falta el punto de salida de la ruta." }), ver, quitar); return; }
  if (!c || c.estado === "cargando") { ponerTarjeta(el("span", { textContent: "Calculando la ruta…" }), quitar); return; }
  if (!op) { ponerTarjeta(el("span", { textContent: c.estado === "fallo" ? "El servicio de rutas no ha respondido." : ruta.modo === "publico" ? "No se ha encontrado transporte público entre esos puntos." : "No hay camino entre esos dos puntos." }), ver, quitar); return; }
  const queda = ruta.progreso && ruta.progreso.turno === ruta.turno && ruta.progreso.modo === ruta.modo ? ruta.progreso : null;
  ponerTarjeta(el("b", { textContent: queda ? `Quedan ${distanciaLegible(queda.metros)} · ${duracionLegible(queda.segundos)}` : `${duracionLegible(op.duracion)}${op.distancia ? ` · ${distanciaLegible(op.distancia)}` : ""}` }),
    el("span", { textContent: queda && queda.fuera ? "Te has salido de la ruta" : op.sale ? `${horaCorta(op.sale)} – ${horaCorta(op.llega)}, ${nombreModo} hasta ${ruta.destino.nombre.slice(0, 32)}` : `${nombreModo} hasta ${ruta.destino.nombre.slice(0, 36)}` }), ver, quitar);
}

/* --- La ficha del panel --- */
function abrirRuta() {
  if (seleccion) mostrarLista();
  soltarMarcador(); soltarElemento();
  desplegarPanel();
  for (const id of ["lista", "ver-mas", "sin-coincidencias", "ficha", "filtros", "pie", "vacio", "ficha-elemento", "ficha-marcador"]) $(id).hidden = true;
  $("ficha-ruta").hidden = false;
  $("contenido").scrollTop = 0;
  pintarFichaRuta(); pintarTarjetaRuta();
}
function cerrarFichaRuta() { mostrarLista(); if (candidatos.length) filtrar(); pintarTarjetaRuta(); }

const camposRuta = {};
{
  const ficha = $("ficha-ruta");
  const volver = el("button", { type: "button", textContent: "Lista" }), quitar = el("button", { type: "button", textContent: "Quitar la ruta" });
  volver.addEventListener("click", cerrarFichaRuta);
  quitar.addEventListener("click", quitarRuta);
  const sugerencias = el("ul", { className: "sugerencias-ruta", hidden: true });
  let relojSugerir = null, turnoSugerir = 0;
  const cerrarSugerencias = () => { turnoSugerir++; sugerencias.hidden = true; sugerencias.replaceChildren(); };
  const sugerir = (cual, campo) => {
    const turno = ++turnoSugerir, texto = campo.value.trim();
    const fila = (icono, titulo, detalle, hacer) => {
      const b = el("button", { type: "button" }, iconoSVG(icono, 18), el("b", { textContent: titulo }), el("small", { textContent: detalle || "" }));
      b.addEventListener("click", () => { cerrarSugerencias(); hacer(); });
      return el("li", {}, b);
    };
    const fijas = [fila("mi_posicion", "Tu posición", "", () => usarMiPosicion(cual)),
      fila("lugar", "Elegir en el mapa", "", () => { ruta.eligiendo = cual; ruta[cual] = null; $("mapa").classList.add("colocando"); pintarFichaRuta(); pintarTarjetaRuta(); if (matchMedia("(max-width: 760px)").matches && typeof ponerHoja === "function") ponerHoja("minima"); })];
    const pintar = (lugares) => {
      sugerencias.replaceChildren(...fijas, ...lugares.slice(0, 7).map((l) => fila(l.reciente ? "reciente" : "lugar", l.nombre, l.detalle, () => ponerExtremo(cual, { ll: L.latLng(l.lat, l.lon), nombre: l.nombre }))));
      sugerencias.hidden = false;
      campo.closest("label").after(sugerencias);
    };
    clearTimeout(relojSugerir);
    const coords = /^(-?\d{1,2}(?:[.,]\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:[.,]\d+)?)$/.exec(texto);
    if (coords) { const lat = +coords[1].replace(",", "."), lon = +coords[2].replace(",", "."); pintar([{ nombre: `${lat}, ${lon}`, detalle: "Estas coordenadas", lat, lon }]); return; }
    if (texto.length < 3) { pintar(recientes.map((r) => Object.assign({ reciente: true }, r))); return; }
    pintar([]);
    relojSugerir = setTimeout(() => sugerirLugares(texto).then((lugares) => { if (turno === turnoSugerir) pintar(lugares); }, () => {}), 300);
  };
  const campo = (cual, rotulo) => {
    const c = el("input", { type: "search", id: `ruta-${cual}`, placeholder: rotulo, autocomplete: "off", ariaLabel: rotulo, enterKeyHint: "search" });
    c.addEventListener("focus", () => { c.select(); sugerir(cual, c); });
    c.addEventListener("input", () => sugerir(cual, c));
    c.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") { ev.stopPropagation(); cerrarSugerencias(); c.blur(); pintarFichaRuta(); }
      else if (ev.key === "Enter" || ev.key === "ArrowDown") { const b = sugerencias.querySelectorAll("button")[ev.key === "Enter" && c.value.trim().length >= 3 ? 2 : 0]; if (b) { ev.preventDefault(); if (ev.key === "Enter") b.click(); else b.focus(); } }
    });
    c.addEventListener("blur", () => setTimeout(() => { if (!sugerencias.contains(document.activeElement) && document.activeElement !== c && !ruta.tocandoSugerencias) { if (!sugerencias.hidden && sugerencias.previousElementSibling === c.closest("label")) cerrarSugerencias(); pintarFichaRuta(); } }, 250));
    return c;
  };
  sugerencias.addEventListener("pointerdown", () => { ruta.tocandoSugerencias = true; setTimeout(() => { ruta.tocandoSugerencias = false; }, 1500); });
  camposRuta.origen = campo("origen", "Desde: tu posición, una dirección, un sitio");
  camposRuta.destino = campo("destino", "Hasta: una dirección, un negocio, un sitio");
  const invertir = el("button", { type: "button", className: "invertir", title: "Cambiar la salida por la llegada", ariaLabel: "Cambiar la salida por la llegada" }, iconoSVG("intercambiar", 20));
  invertir.addEventListener("click", () => { [ruta.origen, ruta.destino] = [ruta.destino, ruta.origen]; ruta.aviso = ""; calcularRuta(); });
  camposRuta.modos = el("div", { className: "modos-ruta", role: "tablist", ariaLabel: "Cómo quieres ir" });
  for (const [id, nombre, icono] of MODOS_RUTA) {
    const b = el("button", { type: "button", role: "tab" }, iconoSVG(icono, 20), el("span", { textContent: nombre }), el("small"));
    b.dataset.modo = id;
    b.addEventListener("click", () => ponerModo(id));
    camposRuta.modos.append(b);
  }
  camposRuta.cuerpo = el("div", { id: "ruta-cuerpo" });
  ficha.append(el("div", { className: "navegacion" }, volver, quitar), el("h2", { textContent: "Cómo llegar" }),
    el("div", { className: "extremos-ruta" }, el("label", {}, el("i", { className: "punto-ruta salida" }), camposRuta.origen), el("label", {}, el("i", { className: "punto-ruta llegada" }), camposRuta.destino), invertir),
    camposRuta.modos, camposRuta.cuerpo);
}
function pintarFichaRuta() {
  if ($("ficha-ruta").hidden) return;
  for (const cual of ["origen", "destino"]) {
    const campo = camposRuta[cual], x = ruta[cual];
    if (document.activeElement !== campo) campo.value = ruta.eligiendo === cual ? "" : x ? (x.buscando ? "Buscando tu posición…" : x.nombre) : "";
    campo.placeholder = ruta.eligiendo === cual ? "Toca el punto en el mapa…" : cual === "origen" ? "Desde: tu posición, una dirección, un sitio" : "Hasta: una dirección, un negocio, un sitio";
  }
  for (const b of camposRuta.modos.children) {
    const c = ruta.calculo[b.dataset.modo], op = c && c.estado === "bien" ? c.opciones[0] : null;
    b.setAttribute("aria-selected", String(b.dataset.modo === ruta.modo));
    b.lastChild.textContent = op ? duracionLegible(op.duracion) : c && c.estado === "cargando" ? "…" : c && c.estado !== "bien" ? "—" : "";
  }
  const cuerpo = camposRuta.cuerpo, c = calculoActual(), partes = [];
  if (ruta.aviso) partes.push(el("p", { className: "aviso-ruta", textContent: ruta.aviso }));
  if (ruta.modo === "publico") partes.push(selectorDeHora());
  if (!ruta.origen || !ruta.destino || !ruta.origen.ll || !ruta.destino.ll) {
    if (!ruta.aviso) partes.push(el("p", { className: "pendiente", textContent: ruta.eligiendo ? "Toca en el mapa el punto que falta." : ruta.origen && ruta.origen.buscando ? "Buscando tu posición…" : !ruta.destino ? "Escribe a dónde quieres ir, o elige el punto en el mapa." : "Escribe desde dónde sales, usa tu posición o elige el punto en el mapa." }));
  } else if (!c || c.estado === "cargando") partes.push(el("p", { className: "pendiente" }, el("i", { className: "girando" }), " Calculando…"));
  else if (c.estado === "fallo") {
    const otra = el("button", { type: "button", textContent: "Reintentar" });
    otra.addEventListener("click", () => { delete ruta.calculo[ruta.modo]; if (ruta.calcular) ruta.calcular(ruta.modo); });
    partes.push(el("p", { className: "pendiente", textContent: "El servicio de rutas no ha respondido." }), el("div", { className: "enlaces" }, otra));
  } else if (c.estado === "vacio") partes.push(el("p", { className: "pendiente", textContent: ruta.modo === "publico" ? "No se ha encontrado ningún viaje en transporte público para esa hora. Prueba otra hora, o mira si andando llegas antes." : "No hay camino entre esos dos puntos con este medio." }));
  else {
    c.opciones.forEach((op, k) => partes.push(tarjetaDeOpcion(op, k, k === c.elegida)));
    const fuera = el("a", { href: `https://www.google.com/maps/dir/?api=1&origin=${ruta.origen.ll.lat.toFixed(6)},${ruta.origen.ll.lng.toFixed(6)}&destination=${ruta.destino.ll.lat.toFixed(6)},${ruta.destino.ll.lng.toFixed(6)}&travelmode=${{ pie: "walking", coche: "driving", bici: "bicycling", publico: "transit" }[ruta.modo]}`,
      target: "_blank", rel: "noopener noreferrer", textContent: "Abrir esta ruta en Google Maps" });
    partes.push(el("p", { className: "ayuda", textContent: ruta.modo === "coche" ? "Tiempo sin contar el tráfico. Camino de OpenStreetMap, calculado con OSRM." : ruta.modo === "publico" ? "Horarios publicados por las empresas de transporte, reunidos por Transitous. «En directo» es que el vehículo ya va comunicando su posición." : "Camino de OpenStreetMap, calculado con OSRM." }),
      el("div", { className: "enlaces" }, fuera));
  }
  cuerpo.replaceChildren(...partes);
}
function selectorDeHora() {
  const tipo = el("select", { ariaLabel: "Cuándo" }, el("option", { value: "ahora", textContent: "Salir ahora" }), el("option", { value: "salir", textContent: "Salir a las…" }), el("option", { value: "llegar", textContent: "Llegar a las…" }));
  tipo.value = ruta.cuando.tipo;
  const ahora = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const hora = el("input", { type: "datetime-local", value: ruta.cuando.hora || ahora, hidden: ruta.cuando.tipo === "ahora", ariaLabel: "Día y hora" });
  const cambiar = () => {
    ruta.cuando = { tipo: tipo.value, hora: tipo.value === "ahora" ? "" : hora.value || ahora };
    hora.hidden = tipo.value === "ahora";
    delete ruta.calculo.publico;
    if (ruta.calcular && ruta.origen && ruta.destino && ruta.origen.ll && ruta.destino.ll) ruta.calcular("publico");
  };
  tipo.addEventListener("change", cambiar); hora.addEventListener("change", cambiar);
  return el("div", { className: "cuando-ruta" }, tipo, hora);
}
function tarjetaDeOpcion(op, k, elegida) {
  const caja = el("section", { className: `opcion-ruta${elegida ? " elegida" : ""}` });
  const cabeza = el("button", { type: "button", className: "cabeza" });
  cabeza.setAttribute("aria-expanded", String(elegida));
  if (op.sale) {
    cabeza.append(el("b", { textContent: `${horaCorta(op.sale)} – ${horaCorta(op.llega)}` }), el("em", { textContent: duracionLegible(op.duracion) }));
    const fila = el("span", { className: "tramos" });
    op.resumen.forEach((r, i) => { if (i) fila.append(el("i", { textContent: "›" })); fila.append(r.linea ? chapaDeLinea(r.linea.nombre, r.linea.color, r.linea.texto, r.linea.modo) : el("span", { className: "a-pie" }, iconoSVG("pie", 15), ` ${r.pie}`)); });
    cabeza.append(fila, el("small", { textContent: `${op.cambios === 0 ? "Sin transbordos" : op.cambios === 1 ? "1 transbordo" : `${op.cambios} transbordos`}${op.primeraLinea && op.primeraLinea.name ? ` · desde ${op.primeraLinea.name}` : ""}` }));
  } else {
    const llegada = new Date(Date.now() + op.duracion * 1000);
    cabeza.append(el("b", { textContent: duracionLegible(op.duracion) }), el("em", { textContent: distanciaLegible(op.distancia) }),
      el("small", { textContent: `${op.resumen ? `Por ${op.resumen}. ` : ""}Saliendo ahora llegas a las ${horaCorta(llegada)}` }));
  }
  cabeza.addEventListener("click", () => elegirOpcion(k));
  caja.append(cabeza);
  if (!elegida) return caja;
  const lista = el("ol", { className: "pasos-ruta" });
  for (const p of op.pasos) {
    const b = el("button", { type: "button" }, p.linea ? chapaDeLinea(p.linea.nombre, p.linea.color, p.linea.texto, p.linea.modo) : iconoSVG(p.icono, 20), el("span", { textContent: p.texto }),
      el("em", { textContent: p.metros ? distanciaLegible(p.metros) : "" }));
    if (p.detalle) b.append(el("small", { textContent: p.detalle + (p.directo ? ". En directo" : "") }));
    b.addEventListener("click", () => { if (!p.ll) return; ruta.marcaPaso.setLatLng(p.ll).addTo(mapa); mapa.setView(p.ll, Math.max(mapa.getZoom(), 17)); if (matchMedia("(max-width: 760px)").matches && typeof ponerHoja === "function") ponerHoja("media"); });
    const li = el("li", {}, b);
    if (p.intermedias && p.intermedias.length) li.append(el("details", {}, el("summary", { textContent: `Ver las ${p.intermedias.length} paradas intermedias` }), el("ul", {}, ...p.intermedias.map((s) => el("li", { textContent: s })))));
    lista.append(li);
  }
  caja.append(lista);
  return caja;
}

/* Mientras hay una ruta que sale de «tu posición», se pide al aparato que no apague la pantalla: quien va
   andando con el móvil en la mano no tiene que ir tocándola. El permiso se pierde al cambiar de
   aplicación, así que se vuelve a pedir al volver. */
let pantallaDespierta = null, pidiendoPantalla = false, pantallaNegada = false;
function cuidarPantalla() {
  const hace = !!(ruta.origen && ruta.origen.yo && ruta.destino && ruta.destino.ll) && !document.hidden;
  if (hace && !pantallaDespierta && !pidiendoPantalla && !pantallaNegada && navigator.wakeLock) {
    pidiendoPantalla = true;
    navigator.wakeLock.request("screen").then((cierre) => {
      pidiendoPantalla = false; pantallaDespierta = cierre;
      cierre.addEventListener("release", () => { if (pantallaDespierta === cierre) pantallaDespierta = null; });
      cuidarPantalla();      // por si mientras se pedía dejó de hacer falta
    }, () => { pidiendoPantalla = false; pantallaNegada = true; });      // el aparato no lo permite (batería baja, por ejemplo): no se insiste
  } else if (!hace && pantallaDespierta) { const cierre = pantallaDespierta; pantallaDespierta = null; cierre.release().catch(() => {}); }
}
document.addEventListener("visibilitychange", () => { pantallaNegada = false; cuidarPantalla(); });

/* ====================== 4. Seguir la posición ======================
   Si la ruta sale de «tu posición», cada vez que el aparato dice dónde está se mira cuánto queda
   (el punto de la ruta más cercano parte el camino en lo andado y lo que falta). Si se está lejos
   de la ruta, se vuelve a calcular, pero no más de una vez cada veinte segundos. */
let ultimoRecalculo = 0;
function alMoverme(pos) {
  const op = opcionActual();
  if (!ruta.origen || !ruta.origen.yo || !ruta.destino || !ruta.destino.ll) return;
  const aqui = L.latLng(pos.lat, pos.lon);
  if (!op || ruta.modo === "publico") { if (ruta.origen.ll && aqui.distanceTo(ruta.origen.ll) > 250 && Date.now() - ultimoRecalculo > 60000) { ultimoRecalculo = Date.now(); ruta.origen.ll = aqui; calcularRuta(); } return; }
  // El punto más cercano de la ruta, mirando cada tramo recto entre dos vértices (en metros, con una proyección local).
  const puntos = op.tramos[0].puntos, kx = 111320 * Math.cos((pos.lat * Math.PI) / 180), ky = 110540;
  let mejor = Infinity, enK = 0, enT = 0;
  for (let k = 0; k + 1 < puntos.length; k++) {
    const ax = (puntos[k][1] - pos.lon) * kx, ay = (puntos[k][0] - pos.lat) * ky, bx = (puntos[k + 1][1] - pos.lon) * kx, by = (puntos[k + 1][0] - pos.lat) * ky;
    const dx = bx - ax, dy = by - ay, largo2 = dx * dx + dy * dy, t = largo2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / largo2)) : 0;
    const d = Math.hypot(ax + t * dx, ay + t * dy);
    if (d < mejor) { mejor = d; enK = k; enT = t; }
  }
  let queda = 0;
  for (let k = enK; k + 1 < puntos.length; k++) queda += mapa.distance(puntos[k], puntos[k + 1]) * (k === enK ? 1 - enT : 1);
  const fuera = mejor > Math.max(60, (pos.precision || 0) * 1.5);
  ruta.progreso = { turno: ruta.turno, modo: ruta.modo, metros: queda, segundos: op.distancia ? (op.duracion * queda) / op.distancia : 0, fuera };
  if (queda < 25) ruta.progreso.metros = 0;
  if (fuera && Date.now() - ultimoRecalculo > 20000) { ultimoRecalculo = Date.now(); ruta.origen.ll = aqui; calcularRuta(); return; }
  pintarTarjetaRuta();
}
