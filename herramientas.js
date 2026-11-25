"use strict";
/* OSINT Maps: herramientas sobre el mapa. Se carga la última y usa lo de los otros ficheros.

   1. Pestañas del panel: los sitios, lo que hay en el mapa de las capas encendidas y tus marcadores.
   2. La tarjeta sobre el mapa y la medición de distancias (las rutas están en rutas.js).
   3. Lo que se añade a las fichas: la foto y el resumen de las de Hispania Nostra. */

const distanciaLegible = (m) => (m < 950 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toLocaleString("es-ES", { maximumFractionDigits: m < 10000 ? 1 : 0 })} km`);
function duracionLegible(s) {
  const min = Math.max(1, Math.round(s / 60));
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60 ? `${min % 60} min` : ""}`.trim();
}
function descargar(nombre, texto, tipo) {
  const enlace = el("a", { href: URL.createObjectURL(new Blob([texto], { type: tipo })), download: nombre });
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
/* La forma de un elemento en GeoJSON, que escribe las coordenadas al revés que Leaflet (longitud, latitud).
   Un área lleva su contorno y sus huecos; GeoJSON pide que cada anillo acabe donde empieza. */
function geometriaGeoJSON(e) {
  const girar = (puntos) => puntos.map(([lat, lon]) => [lon, lat]);
  if (e.linea) return { type: "LineString", coordinates: girar(e.linea) };
  if (e.anillos && e.anillos.length) {
    const cerrar = (anillo) => { const a = girar(anillo), u = a[a.length - 1]; if (a[0][0] !== u[0] || a[0][1] !== u[1]) a.push(a[0]); return a; };
    const poligonos = e.anillos.map((poligono) => poligono.map(cerrar));
    return poligonos.length === 1 ? { type: "Polygon", coordinates: poligonos[0] } : { type: "MultiPolygon", coordinates: poligonos };
  }
  return { type: "Point", coordinates: [e.lon, e.lat] };
}
function exportarVista() {
  const features = elementosEnVista().map(([capa, e]) => ({
    type: "Feature",
    geometry: geometriaGeoJSON(e),
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
function alCambiarCapas() { programarListas(); pintarTira(); }
mapa.on("moveend", programarListas);
$("capa-camaras").addEventListener("change", programarListas);
{
  // Cada vez que cambian los marcadores (crear, mover, borrar, recuperar una copia) se repinta su lista.
  const original = pintarMarcadores;
  pintarMarcadores = function () { original(); pintarListaMarcadores(); };
}
ponerPestana(leerLocal("osintmaps.pestana.v1", "sitios"));

/* ====================== 2. Tarjeta del mapa y medición ====================== */
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

/* (Las rutas, «cómo llegar», están en rutas.js, que usa esta tarjeta y estos trazos.) */

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
  if (hayRuta()) quitarRuta();
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
    if (elementoAbierto !== e || e.capa !== "listaroja" || !e.url || !conServidor) return;
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

/* ====================== 4. Alrededor del mapa ====================== */

/* --- Tira de capas encendidas ---
   Una ficha por capa, con su símbolo, su nombre corto y cuántos elementos tiene: es la leyenda
   de lo que se está viendo. Pulsar una ficha oculta la capa; pulsarla otra vez la vuelve a
   mostrar. Las que se han ocultado se quedan en la tira (atenuadas) hasta recargar la página,
   para poder compararlas con un toque. */
const FIJAS_EN_TIRA = [["capa-sitios", "Sitios", "sitio", "#e5007d", "cuadrado"], ["capa-camaras", "Cámaras", "camaras", "#d90429", "circulo"],
  ["capa-marcadores", "Marcadores", "spray", "#2fbf71", "circulo"]];
const enTira = new Set(), fichasDeTira = new Map();
for (const [id, nombre, icono, color, forma] of FIJAS_EN_TIRA) {
  const casilla = $(id), b = el("button", { type: "button" }, simboloSVG(icono, color, forma, 20), el("span", { textContent: nombre }));
  const poner = () => { b.setAttribute("aria-pressed", String(casilla.checked)); b.title = casilla.checked ? `${nombre}: pulsa para ocultar` : `${nombre}: ocultos; pulsa para mostrar`; };
  b.addEventListener("click", () => { casilla.checked = !casilla.checked; casilla.dispatchEvent(new Event("change")); });
  casilla.addEventListener("change", poner);
  poner();
  $("tira-capas").append(b);
}
function pintarTira() {
  const z = mapa.getZoom();
  for (const capa of CAPAS) {
    if (capa.oculta) continue;
    const activa = capasActivas.has(capa.id);
    if (activa) enTira.add(capa.id);
    if (!enTira.has(capa.id)) continue;
    let b = fichasDeTira.get(capa.id);
    if (!b) {
      b = el("button", { type: "button" }, simboloDe(capa, null, 20), el("span", { textContent: corto(capa) }), el("small"));
      b.addEventListener("click", () => { const casilla = $(`dato-${capa.id}`); casilla.checked = !casilla.checked; casilla.dispatchEvent(new Event("change")); });
      fichasDeTira.set(capa.id, b);
      $("tira-capas").append(b);
    }
    const est = estado[capa.id], nota = b.lastChild;
    const lejos = activa && z < capa.zoom && capa.tipo !== "fija", falla = activa && !est.cargando && !lejos && (est.error || est.sinDatos);
    b.setAttribute("aria-pressed", String(activa));
    b.classList.toggle("falla", !!falla);
    b.title = `${capa.nombre}: ` + (!activa ? "oculta; pulsa para mostrarla" : est.sinDatos ? "aún no se ha descargado (osintmaps capas)" : lejos ? "acerca el mapa para verla"
      : est.cargando ? "cargando…" : est.error ? (est.mensaje || "no ha respondido") : `${est.elementos.size} cargados`) + (activa ? ". Pulsa para ocultarla." : "");
    if (activa && est.cargando && !lejos) { if (!nota.firstElementChild) nota.replaceChildren(el("i", { className: "girando" })); }
    else {
      const texto = !activa ? "" : est.sinDatos ? "sin datos" : lejos ? "acerca" : est.error ? "!" : est.incompleta ? `${miles(est.elementos.size)}+` : miles(est.elementos.size);
      if (nota.firstElementChild || nota.textContent !== texto) nota.textContent = texto;
    }
  }
}
pintarTira();
/* --- El móvil: buscador sobre el mapa y panel como hoja ---
   En pantallas estrechas el buscador flota arriba, sobre el mapa, y el panel es una hoja que sube
   desde abajo. La hoja tiene tres alturas: recogida («plegado»: solo la cabecera), media y alta.
   Se cambia arrastrando el asa (o la cabecera) o tocando el asa. */
const pantallaEstrecha = matchMedia("(max-width: 760px)");
const esMovil = () => pantallaEstrecha.matches;
const hojaActual = () => ($("panel").classList.contains("plegado") ? "minima" : $("panel").classList.contains("alta") ? "alta" : "media");
function ponerHoja(altura) {
  const panel = $("panel");
  if (hojaActual() === altura) return;
  panel.classList.toggle("plegado", altura === "minima");
  panel.classList.toggle("alta", altura === "alta");
  panel.style.height = "";
  // El mapa cambia de alto con la hoja: se le avisa cuando acaba el movimiento (y un poco antes, por si no hay
  // transición). Leaflet mantiene en el centro lo que estaba en el centro: lo que se miraba no queda tapado por la hoja.
  setTimeout(() => mapa.invalidateSize({ animate: false }), 60);
  setTimeout(() => mapa.invalidateSize({ animate: false }), 260);
}
/* Lo que llama desplegarPanel(): al abrir una ficha, que se vean a la vez el mapa y la ficha. */
function alDesplegarHoja() { if (esMovil() && hojaActual() !== "media" && document.activeElement !== $("buscar-texto")) ponerHoja("media"); }
{
  const panel = $("panel"), colocar = () => {
    if (esMovil()) $("mapa-zona").append($("buscador")); else { $("cabecera").after($("buscador")); panel.classList.remove("plegado", "alta"); panel.style.height = ""; }
    mapa.invalidateSize({ pan: false });
  };
  pantallaEstrecha.addEventListener("change", colocar);
  colocar();
  // Escribir en el buscador sube la hoja (los resultados salen en ella); al salir del campo sin texto, vuelve a media altura.
  $("buscar-texto").addEventListener("focus", () => { if (esMovil()) ponerHoja("alta"); });
  $("buscar-texto").addEventListener("blur", () => setTimeout(() => {
    if (!esMovil() || hojaActual() !== "alta" || document.activeElement === $("buscar-texto") || $("resultados-extra").contains(document.activeElement)) return;
    if (!$("buscar-texto").value.trim() && $("resultados-extra").hidden) ponerHoja("media");
  }, 1100));
  // Arrastre del asa o de la cabecera.
  let arrastre = null;
  const empezar = (ev) => {
    if (!esMovil() || ev.target.closest("#tema")) return;
    arrastre = { y: ev.clientY, alto: panel.getBoundingClientRect().height, movido: false, id: ev.pointerId };
    ev.currentTarget.setPointerCapture(ev.pointerId);
  };
  const mover = (ev) => {
    if (!arrastre || ev.pointerId !== arrastre.id) return;
    const dy = ev.clientY - arrastre.y;
    if (!arrastre.movido && Math.abs(dy) < 6) return;
    if (!arrastre.movido) { arrastre.movido = true; panel.classList.add("arrastrando"); panel.classList.remove("plegado", "alta"); }
    panel.style.height = `${Math.max(64, Math.min(innerHeight - 58, arrastre.alto - dy))}px`;
    if (!arrastre.cuadro) arrastre.cuadro = requestAnimationFrame(() => { if (arrastre) arrastre.cuadro = 0; mapa.invalidateSize({ animate: false }); });
  };
  const soltar = (ev) => {
    if (!arrastre || ev.pointerId !== arrastre.id) return;
    const { movido, y } = arrastre, alto = panel.getBoundingClientRect().height, dy = ev.clientY - y;
    arrastre = null;
    panel.classList.remove("arrastrando");
    if (!movido) {      // un toque: el asa alterna entre media y la otra que toque
      if (ev.currentTarget.id === "asa-hoja") ponerHoja(hojaActual() === "media" ? "minima" : "media");
      return;
    }
    panel.style.height = "";
    const destino = alto < innerHeight * 0.24 ? "minima" : alto > innerHeight * 0.66 ? "alta" : Math.abs(dy) > 60 && alto > innerHeight * 0.56 ? "alta" : Math.abs(dy) > 60 && alto < innerHeight * 0.34 ? "minima" : "media";
    panel.classList.toggle("plegado", destino === "minima");
    panel.classList.toggle("alta", destino === "alta");
    setTimeout(() => mapa.invalidateSize({ animate: false }), 60);
    setTimeout(() => mapa.invalidateSize({ animate: false }), 260);
  };
  for (const asa of [$("asa-hoja"), $("cabecera")]) {
    asa.addEventListener("pointerdown", empezar);
    asa.addEventListener("pointermove", mover);
    asa.addEventListener("pointerup", soltar);
    asa.addEventListener("pointercancel", soltar);
  }
  // Tocar el mapa con la hoja en alto la baja a media: lo que se quiere entonces es ver el mapa.
  mapa.on("click", () => { if (esMovil() && hojaActual() === "alta") ponerHoja("media"); });
}

/* --- Asa para esconder el panel (ordenador) --- */
function ponerPanel(visible, recordar) {
  const borde = () => mapa.getContainer().getBoundingClientRect().left, antes = borde();
  document.body.classList.toggle("sin-panel", !visible);
  const asa = $("asa-panel");
  asa.setAttribute("aria-expanded", String(visible));
  asa.title = visible ? "Ocultar el panel" : "Mostrar el panel";
  asa.setAttribute("aria-label", asa.title);
  if (recordar) guardarLocal("osintmaps.panel.v1", visible);
  // El mapa gana o pierde ancho por la izquierda: se recoloca para que lo que se veía no se mueva del sitio.
  const corrido = borde() - antes;
  mapa.invalidateSize({ pan: false });
  if (corrido) mapa.panBy([corrido, 0], { animate: false });
}
$("asa-panel").append(iconoSVG("atras", 16));
$("asa-panel").setAttribute("aria-label", "Ocultar el panel");
$("asa-panel").addEventListener("click", () => ponerPanel(document.body.classList.contains("sin-panel"), true));
if (leerLocal("osintmaps.panel.v1", true) === false && matchMedia("(min-width: 761px)").matches) ponerPanel(false);

/* --- Panel de capas: buscar una por su nombre --- */
{
  const panel = $("capas"), campo = $("buscar-capa");
  let abiertos = null;      // cómo estaban los grupos antes de buscar
  campo.addEventListener("input", () => {
    const texto = sinAcentos(campo.value.trim()), grupos = [...panel.querySelectorAll("details.grupo-de-capas")];
    if (texto && !abiertos) abiertos = grupos.map((g) => g.open);
    panel.classList.toggle("buscando", !!texto);
    for (const fila of panel.querySelectorAll(".cuerpo label.casilla")) fila.classList.toggle("oculta-por-busqueda", !!texto && !sinAcentos(fila.textContent).includes(texto));
    grupos.forEach((g, k) => {
      g.classList.toggle("oculta-por-busqueda", !!texto && !g.querySelector("label.casilla:not(.oculta-por-busqueda)"));
      g.open = texto ? true : abiertos ? abiertos[k] : g.open;
    });
    if (!texto) abiertos = null;
  });
}

/* --- Datos guardados en el navegador --- */
function pintarMemoria() {
  memoria.cuantos().then((n) => {
    $("memoria-estado").textContent = n
      ? `${miles(n)} trozos de mapa ya descargados. Al volver a esas zonas salen al momento, sin esperar a Catastro ni a OpenStreetMap. Se renuevan solos: lo de OpenStreetMap cada semana, las parcelas cada mes.`
      : "Aún no hay nada. Lo que vayas viendo se guarda aquí para que la próxima vez salga al momento.";
    $("memoria-vaciar").hidden = !n;
  });
}
$("capas").addEventListener("toggle", () => { if ($("capas").open) pintarMemoria(); });
$("memoria-vaciar").addEventListener("click", () => {
  memoria.vaciar().then(() => {
    for (const capa of CAPAS) if (capa.tipo === "osm" || capa.tipo === "api") vaciar(capa);
    olvidarAcceso();
    actualizarCapas();
    pintarMemoria();
  });
});

/* --- Ajustar la foto: brillo, contraste, color y enfoque ---
   Son filtros del navegador sobre las teselas ya descargadas: no se pide nada nuevo. Sirven para
   ver dentro de las sombras (más brillo), separar cosas de tono parecido (más contraste) o
   remarcar bordes en una foto blanda (enfocar). */
{
  const DEFECTO = { brillo: 100, contraste: 100, color: 100, enfoque: false };
  const ajustes = Object.assign({}, DEFECTO, leerLocal("osintmaps.ajustes.v1", {}) || {});
  const aplicar = () => {
    const neutro = ajustes.brillo === 100 && ajustes.contraste === 100 && ajustes.color === 100;
    document.documentElement.style.setProperty("--ajuste-foto", neutro ? "none" : `brightness(${ajustes.brillo}%) contrast(${ajustes.contraste}%) saturate(${ajustes.color}%)`);
    document.documentElement.classList.toggle("enfocar", !!ajustes.enfoque);
    for (const clave of ["brillo", "contraste", "color"]) { $(`aj-${clave}`).value = ajustes[clave]; $(`aj-${clave}-valor`).textContent = `${ajustes[clave]} %`; }
    $("aj-enfoque").checked = !!ajustes.enfoque;
    $("ajustes-foto").querySelector("summary").textContent = neutro && !ajustes.enfoque ? "Ajustar la foto" : "Ajustar la foto (retocada)";
    guardarLocal("osintmaps.ajustes.v1", ajustes);
  };
  for (const clave of ["brillo", "contraste", "color"]) $(`aj-${clave}`).addEventListener("input", () => { ajustes[clave] = +$(`aj-${clave}`).value; aplicar(); });
  $("aj-enfoque").addEventListener("change", () => { ajustes.enfoque = $("aj-enfoque").checked; aplicar(); });
  $("aj-restablecer").addEventListener("click", () => { Object.assign(ajustes, DEFECTO); aplicar(); });
  aplicar();
  // Doble detalle: solo tiene sentido (y solo se ofrece) en pantallas densas. Cambiarlo rehace las capas: se recarga.
  $("fila-nitidez").hidden = (window.devicePixelRatio || 1) <= 1.25;
  $("aj-nitidez").checked = DENSIDAD === 2;
  $("aj-nitidez").addEventListener("change", () => { guardarLocal("osintmaps.nitidez.v1", $("aj-nitidez").checked); location.reload(); });
}

/* --- Atajo: «/» lleva al buscador --- */
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "/" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const foco = document.activeElement;
  if (foco && (/^(INPUT|TEXTAREA|SELECT)$/.test(foco.tagName) || foco.isContentEditable)) return;
  if (visor) return;      // con el visor de imágenes abierto, el teclado es suyo
  ev.preventDefault();
  desplegarPanel();
  $("buscar-texto").focus();
  $("buscar-texto").select();
});
