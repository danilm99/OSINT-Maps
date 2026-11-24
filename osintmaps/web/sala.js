/* OSINT Maps: la sala de control.

   Una pantalla para ver València de un vistazo con datos públicos y de conjunto: qué barrios están
   fuera de lo normal y por qué (el «cruce» del programa del ordenador), los sucesos en marcha, las
   cifras de la ciudad, lo que se publica y lo previsto para hoy.

   - Con el programa del ordenador detrás («osintmaps servir --pulso»), todo se pide a /vivo/sala/...
     cada medio minuto, y hay fichas completas de cada suceso, barrio e inmueble.
   - En la web publicada se lee datos/sala.json, que el ordenador sube cada cuarto de hora (sin el
     texto de las publicaciones de redes, que solo se cuentan). Las fichas son más cortas.

   Nada sigue a nadie: todo son cifras de barrio y de ciudad, titulares públicos y avisos oficiales.

   Este fichero también deja preparadas las piezas que usa la máquina del tiempo (pulso.js): el mapa
   (`mapa`) y cuatro utilidades (`el`, `pedirJSON`, `hayServidor`, `leerLocal`/`guardarLocal`). */
(() => {
"use strict";
if (typeof L === "undefined") return;

/* ====================== Utilidades ====================== */
const $ = (id) => document.getElementById(id);
const el = (etiqueta, props = {}, ...hijos) => {
  const nodo = Object.assign(document.createElement(etiqueta), props);
  for (const h of hijos) if (h != null && h !== false) nodo.append(h);
  return nodo;
};
const pedirJSON = (ruta) => fetch(ruta, { cache: "no-cache" }).then((r) => (r.ok ? r.json()
  : r.json().catch(() => ({})).then((j) => Promise.reject(new Error(j.error || `error ${r.status}`)))));
const hayServidor = !/^https?:$/.test(location.protocol) ? Promise.resolve(false)
  : fetch("vivo/hola", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((j) => !!(j && j.osintmaps)).catch(() => false);
const leerLocal = (clave, porDefecto) => { try { return JSON.parse(localStorage.getItem(clave)) ?? porDefecto; } catch { return porDefecto; } };
const guardarLocal = (clave, valor) => { try { localStorage.setItem(clave, JSON.stringify(valor)); } catch { /* sin almacenamiento */ } };
Object.assign(window, { el, pedirJSON, hayServidor, leerLocal, guardarLocal });

const urlSegura = (u) => { try { return /^https?:$/.test(new URL(u).protocol) ? u : null; } catch { return null; } };
const enlace = (texto, url, props = {}) => (urlSegura(url) ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer", textContent: texto, ...props }) : el("span", { textContent: texto }));
const dos = (n) => String(n).padStart(2, "0");
const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const DIAS_LARGOS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const hora = (t) => { const d = new Date(t * 1000); return `${dos(d.getHours())}:${dos(d.getMinutes())}`; };
const fecha = (t) => { const d = new Date(t * 1000); return `${DIAS[d.getDay()]} ${d.getDate()} ${MESES[d.getMonth()]}`; };
const fechaHora = (t) => (Math.abs(Date.now() / 1000 - t) < 20 * 3600 ? hora(t) : `${fecha(t)} ${hora(t)}`);
const ahoraSeg = () => Math.floor(Date.now() / 1000);
const hace = (seg) => (seg < 90 ? "ahora mismo" : seg < 5400 ? `hace ${Math.round(seg / 60)} min` : seg < 129600 ? `hace ${Math.round(seg / 3600)} h` : `hace ${Math.round(seg / 86400)} días`);
const duracion = (seg) => (seg < 3600 ? `${Math.max(1, Math.round(seg / 60))} min` : `${Math.floor(seg / 3600)} h ${dos(Math.round((seg % 3600) / 60))}`);
const cifra = (v, dec = 1) => (v == null || Number.isNaN(v) ? "—"
  : Math.abs(v) >= 100 || Number.isInteger(v) ? Math.round(v).toLocaleString("es-ES") : Number(v).toLocaleString("es-ES", { maximumFractionDigits: dec }));
const cifraCorta = (v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toLocaleString("es-ES", { maximumFractionDigits: 1 })}k` : cifra(v));
const movil = () => matchMedia("(max-width: 760px)").matches;

/* ====================== Colores y nombres ====================== */
const C = { cian: "#22d3ee", magenta: "#ff2d95", ambar: "#fbbf24", lima: "#a3e635", rojo: "#f43f5e", violeta: "#a78bfa", naranja: "#fb923c",
  azul: "#60a5fa", gris: "#64748b", texto: "#d8e6ee", suave: "#8aa2b0", tenue: "#4d6574" };
const COLOR_FAMILIA = { afluencia: C.cian, salida: C.violeta, congestion: C.ambar, corte: C.naranja, servicio: C.rojo, atencion: C.magenta, alerta: C.rojo, ambiente: C.lima };
const COLOR_TIPO = { concentracion: C.cian, salida: C.violeta, incidente: C.rojo, congestion: C.ambar, corte: C.naranja, servicio: C.rojo, conversacion: C.magenta, ciudad: "#e2e8f0" };
const COLOR_CATEGORIA = { emergencia: C.rojo, accidente: C.naranja, seguridad: "#fb7185", protesta: C.magenta, trafico: C.ambar, transporte: C.cian,
  meteo: C.azul, evento: C.violeta, deporte: C.lima, vivienda: "#f472b6", urbanismo: "#94a3b8", sanidad: "#34d399", medioambiente: "#86efac",
  politica: "#cbd5e1", cultura: "#c4b5fd", economia: "#fde68a" };
const NOMBRE_FAMILIA = { afluencia: "llega gente", salida: "se va gente", congestion: "más tráfico", corte: "cortes", servicio: "metro", atencion: "se habla",
  alerta: "alerta", ambiente: "aire" };
const NOMBRE_FUENTE = { prensa: "Prensa", bluesky: "Bluesky", mastodon: "Mastodon", dgt: "DGT", renfe: "Renfe", meteoalarm: "AEMET" };
const CLASE_NIVEL = { normal: [C.lima, "Normal", 1], atencion: [C.ambar, "Atención", 2], alta: [C.naranja, "Alta", 3], "muy alta": [C.rojo, "Muy alta", 4] };
const GRAVEDAD = ["sin heridos", "heridos leves", "heridos de baja gravedad", "heridos graves", "fallecidos"];
const TEJAS = [["trafico_indice", "Tráfico"], ["trafico_cortado", "Tramos cortados"], ["bicis_fuera", "Valenbisi en uso"], ["parking_ocupacion", "Aparcamientos"],
  ["metro_salidas", "Metro · salidas 30 min"], ["metro_sin_servicio", "Estaciones sin metro"], ["trenes_retraso", "Retraso Cercanías"], ["trenes_retrasados", "Trenes retrasados"],
  ["aforo", "Vehículos/hora"], ["aforo_bici", "Bicis/hora"], ["aire_no2", "NO₂"], ["aire_pm25", "PM2,5"], ["helicopteros", "Helicópteros"], ["aviones_bajos", "Aviones bajos"],
  ["meteo_temperatura", "Temperatura"], ["meteo_lluvia", "Lluvia"], ["ora_ocupacion", "Zona azul (previsión)"], ["ruido_noche", "Ruido Russafa (anoche)"]];
const RASGOS_WEB = ["aforo", "trafico", "bici_llegadas", "bici_salidas", "bici_ocupacion", "parking", "metro", "social"];
const BASE = new URLSearchParams(location.search).get("datos") || "datos/";

/* ====================== Estado ====================== */
let E = null;                 // lo último de la sala (estado)
let servidor = false;
let geo = null;               // los barrios (GeoJSON)
const props = {};             // código -> propiedades del barrio
let modo = { tipo: "nivel" }; // cómo se pintan los barrios: nivel, comparar o movilidad
let fichaAbierta = null;
let investigando = false;
let ultimoError = null;
const ajustes = Object.assign({ capas: { barrios: true, sucesos: true, textos: true, avisos: true, agenda: true, obras: false, helis: true, nombres: true }, feed: "todo" },
  leerLocal("osintmaps.sala.v1", {}));
const recordar = () => guardarLocal("osintmaps.sala.v1", ajustes);
const nombreBarrio = (c) => (c === "VLC" ? "Toda la ciudad" : props[c]?.nombre || c || "");

/* ====================== El mapa ====================== */
const mapa = L.map("mapa", { zoomControl: true, minZoom: 10, maxZoom: 19, zoomSnap: 0.5 }).setView([39.4699, -0.3763], movil() ? 12.5 : 13);
window.mapa = mapa;
mapa.createPane("barrios").style.zIndex = 350;
mapa.createPane("rotulos").style.zIndex = 450;
mapa.getPane("rotulos").style.pointerEvents = "none";
mapa.createPane("sucesos").style.zIndex = 640;
const ESRI = (parte) => `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_${parte}/MapServer/tile/{z}/{y}/{x}`;
L.tileLayer(ESRI("Base"), { maxZoom: 19, maxNativeZoom: 16, attribution: "Esri, HERE, Garmin, OpenStreetMap" }).addTo(mapa);
L.tileLayer(ESRI("Reference"), { maxZoom: 19, maxNativeZoom: 16, pane: "rotulos" }).addTo(mapa);
mapa.attributionControl.addAttribution("Datos: Ajuntament de València, FGV, Renfe, DGT, AEMET, prensa local, adsb.fi");

const capas = {
  sucesos: L.layerGroup(), textos: L.layerGroup(), avisos: L.layerGroup(), agenda: L.layerGroup(), obras: L.layerGroup(),
  helis: L.layerGroup(), nombres: L.layerGroup(), foco: L.layerGroup().addTo(mapa), barrios: null,
};
const CAPAS_MAPA = [
  ["barrios", "Barrios", C.cian], ["sucesos", "Sucesos", C.magenta], ["textos", "Noticias", C.violeta], ["avisos", "Incidencias", C.ambar],
  ["agenda", "Previsto", C.ambar], ["obras", "Obras", C.gris], ["helis", "Helicópteros", C.rojo], ["nombres", "Nombres", C.suave],
];
function ponerCapa(id, si) {
  ajustes.capas[id] = si; recordar();
  const capa = capas[id];
  if (capa) si ? capa.addTo(mapa) : mapa.removeLayer(capa);
  if (id === "helis") si ? pedirCielo() : null;
  pintarLeyenda();
}
const barraMapa = $("herramientas-mapa");
for (const [id, nombre, color] of CAPAS_MAPA) {
  const b = el("button", { type: "button", title: `Ver u ocultar: ${nombre}` }, el("i"), nombre);
  b.style.setProperty("--c", color);
  b.setAttribute("aria-pressed", String(!!ajustes.capas[id]));
  b.addEventListener("click", () => { const si = b.getAttribute("aria-pressed") !== "true"; b.setAttribute("aria-pressed", String(si)); ponerCapa(id, si); });
  barraMapa.append(b);
}
const bInvestigar = el("button", { type: "button", className: "investigar", title: "Investigar un punto: pulsa en el mapa para ver la ficha de ese inmueble (también con clic derecho)" }, "⌖ Investigar");
bInvestigar.setAttribute("aria-pressed", "false");
bInvestigar.addEventListener("click", () => { investigando = !investigando; bInvestigar.setAttribute("aria-pressed", String(investigando)); $("mapa-zona").classList.toggle("investigando", investigando); });
barraMapa.append(bInvestigar);
L.DomEvent.disableClickPropagation(barraMapa);
for (const id of ["sucesos", "textos", "avisos", "agenda", "obras", "helis", "nombres"]) if (ajustes.capas[id]) capas[id].addTo(mapa);

mapa.on("click", (ev) => { if (investigando) abrirLugar(ev.latlng.lat, ev.latlng.lng); });
mapa.on("contextmenu", (ev) => abrirLugar(ev.latlng.lat, ev.latlng.lng));
mapa.on("zoomend", () => pintarNombres());

/* ---------- Barrios ---------- */
function familiaDominante(b) {
  let mejor = null, max = 0;
  for (const [f, v] of Object.entries(b?.familias || {})) if (v > max) { max = v; mejor = f; }
  return mejor;
}
const barriosEnSuceso = () => new Set((E?.sucesos || []).filter((s) => s.estado === "activo").flatMap((s) => s.ahora?.length ? s.ahora : s.barrios));
let enSuceso = new Set();
function colorDivergente(v, escala, pos = C.cian, neg = C.naranja) {
  if (v == null || !escala) return [C.gris, 0];
  const f = Math.max(-1, Math.min(1, v / escala));
  return [f >= 0 ? pos : neg, Math.abs(f) * 0.62];
}
function estiloBarrio(f) {
  const c = f.properties.codigo;
  if (modo.tipo !== "nivel") {
    const [color, a] = colorDivergente(modo.valores?.[c], modo.escala, modo.pos, modo.neg);
    return { pane: "barrios", color: "#1d4655", weight: 0.8, opacity: 0.8, fillColor: color, fillOpacity: modo.valores?.[c] == null ? 0.04 : a };
  }
  const b = E?.barrios?.[c];
  const n = b?.nivel || 0;
  const color = COLOR_FAMILIA[familiaDominante(b)] || C.cian;
  const activo = enSuceso.has(c);
  return { pane: "barrios", color: activo ? color : "#1d4655", weight: activo ? 2.2 : 0.8, opacity: activo ? 1 : 0.75,
    fillColor: color, fillOpacity: n < 2 ? 0.02 : Math.min(0.6, 0.1 + (n - 2) * 0.08) };
}
function tooltipBarrio(c) {
  const b = E?.barrios?.[c];
  const caja = el("div", {}, el("div", { className: "tt-n", textContent: nombreBarrio(c) }));
  if (modo.tipo !== "nivel") {
    const v = modo.valores?.[c];
    caja.append(el("div", { className: "tt-s", textContent: v == null ? "sin datos" : `${modo.etiqueta}: ${v > 0 ? "+" : ""}${cifra(v)} ${modo.unidad || ""}` }));
    return caja;
  }
  if (!b) { caja.append(el("div", { className: "tt-s", textContent: "Sin datos aún" })); return caja; }
  const s = b.senales?.[0];
  caja.append(el("div", { className: "tt-s", textContent: b.nivel >= 2 ? `Nivel ${cifra(b.nivel)} · ${NOMBRE_FAMILIA[familiaDominante(b)] || ""}` : "Dentro de lo normal" }));
  if (s && b.nivel >= 2) caja.append(el("div", { className: "tt-s", textContent: `${E.rasgos?.[s.rasgo]?.nombre || s.rasgo}: ${cifra(s.valor)} (normal ${cifra(s.normal)})` }));
  return caja;
}
function pintarBarrios() {
  if (!geo) return;
  enSuceso = barriosEnSuceso();
  if (!capas.barrios) {
    capas.barrios = L.geoJSON(geo, {
      pane: "barrios", style: estiloBarrio,
      onEachFeature: (f, capa) => {
        capa.on("click", (ev) => { L.DomEvent.stop(ev); investigando ? abrirLugar(ev.latlng.lat, ev.latlng.lng) : abrirBarrio(f.properties.codigo); });
        capa.on("contextmenu", (ev) => { L.DomEvent.stop(ev); abrirLugar(ev.latlng.lat, ev.latlng.lng); });
        capa.bindTooltip(() => tooltipBarrio(f.properties.codigo), { sticky: true, className: "sala", direction: "top", offset: [0, -10] });
      },
    });
    if (ajustes.capas.barrios) capas.barrios.addTo(mapa);
  } else capas.barrios.setStyle(estiloBarrio);
  pintarNombres();
}
function pintarNombres() {
  capas.nombres.clearLayers();
  if (!geo || !ajustes.capas.nombres || mapa.getZoom() < 13.5) return;
  for (const f of geo.features) {
    const p = f.properties;
    if (p.lat == null) continue;
    capas.nombres.addLayer(L.tooltip({ permanent: true, direction: "center", className: "nombre-barrio", interactive: false, pane: "rotulos" })
      .setLatLng([p.lat, p.lon]).setContent(String(p.nombre || "")));
  }
}

/* ---------- Sucesos, textos, avisos, agenda ---------- */
function pintarCapas() {
  capas.sucesos.clearLayers();
  for (const s of E?.sucesos || []) {
    if (s.lat == null) continue;
    const activo = s.estado === "activo";
    const d = Math.round(Math.max(14, Math.min(46, 10 + (s.puntuacion || 0) * 3)));
    const color = COLOR_TIPO[s.tipo] || C.cian;
    const icono = L.divIcon({ className: `icono-suceso ${activo ? "activo" : "cerrado"}`, html: `<span style="--c:${color};--d:${d}px"></span>`, iconSize: [d, d] });
    L.marker([s.lat, s.lon], { icon: icono, pane: "sucesos", title: s.titulo || "", keyboard: false, zIndexOffset: activo ? 1000 : 0 })
      .on("click", () => abrirSuceso(s.id)).addTo(capas.sucesos);
  }
  capas.textos.clearLayers();
  const desde = ahoraSeg() - 6 * 3600;
  for (const it of E?.feed || []) {
    if (it.lat == null || it.t < desde || it.fuente === "dgt" || it.fuente === "renfe") continue;
    const color = COLOR_CATEGORIA[it.categoria] || C.violeta;
    L.circleMarker([it.lat, it.lon], { radius: it.urgencia >= 2 ? 6 : 4.5, color, weight: 1.5, fillColor: color, fillOpacity: 0.55 })
      .bindPopup(() => popupTexto(it), { maxWidth: 300 }).addTo(capas.textos);
  }
  capas.avisos.clearLayers();
  for (const a of E?.avisos || []) {
    if (a.lat == null) continue;
    const icono = L.divIcon({ className: `icono-aviso u${Math.min(2, a.urgencia || 0)}`, html: "▲", iconSize: [16, 16] });
    L.marker([a.lat, a.lon], { icon: icono, title: a.titulo || "", keyboard: false }).bindPopup(() => popupTexto(a), { maxWidth: 300 }).addTo(capas.avisos);
  }
  capas.agenda.clearLayers();
  for (const a of E?.agenda?.destacado || []) {
    if (a.lat == null) continue;
    const icono = L.divIcon({ className: "icono-agenda", html: a.tipo === "partido" ? "◆" : "★", iconSize: [18, 18] });
    L.marker([a.lat, a.lon], { icon: icono, title: a.titulo || "", keyboard: false }).bindPopup(() => popupCita(a), { maxWidth: 300 }).addTo(capas.agenda);
  }
  capas.obras.clearLayers();
  for (const a of E?.agenda?.planificado || []) {
    L.circleMarker([a.lat, a.lon], { radius: 3, color: "#94a3b8", weight: 1, fillColor: "#94a3b8", fillOpacity: 0.35 })
      .bindPopup(() => popupCita(a), { maxWidth: 300 }).addTo(capas.obras);
  }
}
function popupTexto(it) {
  const caja = el("div", {},
    el("div", { className: "tt-s", textContent: `${NOMBRE_FUENTE[it.fuente] || it.fuente}${it.medio ? ` · ${it.medio}` : ""} · ${fechaHora(it.t)}` }),
    el("div", { style: "margin:4px 0; font-weight:600" }, enlace(it.titulo || "(sin título)", it.url)));
  if (it.barrio) caja.append(el("div", { className: "tt-s", textContent: nombreBarrio(it.barrio) + (it.lugar ? ` · ${it.lugar}` : "") }));
  return caja;
}
function popupCita(a) {
  return el("div", {},
    el("div", { className: "tt-s", textContent: `${a.tipo}${a.subtipo && a.subtipo !== a.tipo ? ` (${a.subtipo.split(":")[1] || ""})` : ""}` }),
    el("div", { style: "margin:4px 0; font-weight:600", textContent: a.titulo || "" }),
    el("div", { className: "tt-s", textContent: `${fechaHora(a.desde)} → ${fechaHora(a.hasta)}` }));
}

/* ---------- Helicópteros ahora (del histórico del pulso: no se pregunta a nadie más) ---------- */
let relojCielo = 0;
async function pedirCielo() {
  clearTimeout(relojCielo);
  if (!servidor || !ajustes.capas.helis) { capas.helis.clearLayers(); return; }
  try {
    const d = await pedirJSON("vivo/sala/cielo");
    capas.helis.clearLayers();
    for (const [ident, h] of Object.entries(d.helicopteros || {})) {
      const p = h.p.map((x) => [x[1], x[2]]);
      L.polyline(p, { color: C.rojo, weight: 1.6, opacity: 0.7, dashArray: "3 4" }).addTo(capas.helis);
      const u = h.p[h.p.length - 1];
      const icono = L.divIcon({ className: "icono-heli", html: "<b></b>", iconSize: [14, 14], iconAnchor: [7, 7] });
      L.marker([u[1], u[2]], { icon: icono, keyboard: false, title: h.nombre || ident })
        .bindTooltip(`${h.nombre || ident} · ${u[3] == null ? "?" : `${u[3]} m`}`, { className: "sala", direction: "right", offset: [8, 0] }).addTo(capas.helis);
    }
  } catch { /* sin cielo */ }
  relojCielo = setTimeout(pedirCielo, 30000);
}

/* ====================== Leyenda ====================== */
function pintarLeyenda() {
  const ley = $("leyenda");
  ley.replaceChildren();
  if (modo.tipo === "nivel") {
    ley.append(el("div", { className: "titulo", textContent: "Barrios fuera de lo normal" }));
    for (const f of ["afluencia", "salida", "congestion", "corte", "atencion", "alerta"]) {
      const c = el("span", { className: "cuadro" }); c.style.setProperty("--c", COLOR_FAMILIA[f]);
      ley.append(el("div", { className: "lin" }, c, NOMBRE_FAMILIA[f]));
    }
    ley.append(el("div", { className: "lin", textContent: "Más intenso, más lejos de lo normal para esa hora y ese día." }));
  } else {
    ley.append(el("div", { className: "titulo", textContent: modo.titulo || "" }));
    const g = el("div", { className: "degradado" });
    g.style.background = `linear-gradient(90deg, ${modo.neg}, #0b1621 50%, ${modo.pos})`;
    ley.append(g, el("div", { className: "lin", style: "justify-content:space-between" }, el("span", { textContent: modo.izquierda || "menos" }), el("span", { textContent: modo.derecha || "más" })));
  }
}

/* ====================== Cabecera ====================== */
function pintarReloj() {
  const d = new Date();
  $("reloj").firstChild.nodeValue = `${dos(d.getHours())}:${dos(d.getMinutes())}:${dos(d.getSeconds())}`;
  $("fecha").textContent = `${DIAS_LARGOS[d.getDay()]} ${d.getDate()} ${MESES[d.getMonth()]}`;
  const vivo = $("vivo");
  if (!E) { vivo.className = "vivo parado"; vivo.textContent = "sin datos"; return; }
  const edad = ahoraSeg() - (E.generado || 0);
  const limite = servidor ? 150 : 25 * 60;
  vivo.className = `vivo${edad > limite * 6 ? " parado" : edad > limite ? " atrasado" : ""}`;
  vivo.textContent = servidor ? (edad > limite ? `datos ${hace(edad)}` : "en directo") : `web · ${hace(edad)}`;
}
setInterval(pintarReloj, 1000);

function pintarCabecera() {
  const [color, nombre, barras] = CLASE_NIVEL[E.nivel?.clase] || CLASE_NIVEL.normal;
  const v = $("nivel-valor");
  v.textContent = nombre; v.style.color = color;
  $("nivel-ciudad").title = `${E.nivel?.frase || ""} (nivel ${cifra(E.nivel?.valor)})`;
  $("nivel-barras").replaceChildren(...[1, 2, 3, 4].map((k) => { const s = el("span"); if (k <= barras) { s.style.background = color; s.style.boxShadow = `0 0 6px ${color}`; } return s; }));
  const fuentes = E.fuentes || [];
  const ahora = ahoraSeg();
  const bien = fuentes.filter((f) => f.ok && f.ultima && ahora - f.ultima < Math.max(3 * (f.cada || 600), 1800)).length;
  const chip = $("chip-fuentes");
  chip.className = `chip ${!fuentes.length ? "" : bien === fuentes.length ? "ok" : bien >= fuentes.length * 0.7 ? "aviso" : "mal"}`;
  chip.replaceChildren(el("span", { className: "punto" }), fuentes.length ? `Fuentes ${bien}/${fuentes.length}` : "Fuentes");
  const ap = E.aprendiendo;
  const chipAp = $("chip-aprendiendo");
  chipAp.hidden = !ap || ap.listo;
  if (ap && !ap.listo) chipAp.textContent = `Aprendiendo · ${Math.min(4, ap.semanas || 0)}/4 sem`;
  const ia = E.ia || {};
  const chipIa = $("chip-ia");
  chipIa.hidden = !servidor;
  chipIa.className = `chip opcional ${ia.disponible ? "ia" : ""}`;
  chipIa.textContent = ia.disponible ? `IA · ${ia.modelo}` : "IA local: no";
  chipIa.title = ia.disponible ? `IA local (${ia.modelo}): ${ia.hechos?.sucesos || 0} sucesos resumidos, ${ia.hechos?.textos || 0} textos leídos` : "Sin IA local: todo funciona con reglas. Instala Ollama para que resuma sucesos y escriba el parte.";
  const activos = (E.sucesos || []).filter((s) => s.estado === "activo").length;
  $("pestana-n").textContent = activos ? `(${activos})` : "";
  const aviso = $("aviso-mapa");
  aviso.hidden = !!E.hay;
  if (!E.hay) { $("aviso-titulo").textContent = "Preparando la sala"; $("aviso-texto").textContent = E.fase || "Esperando al programa del ordenador…"; }
}
$("chip-fuentes").addEventListener("click", abrirFuentes);

/* ====================== Columnas ====================== */
function pintarTejas() {
  const porClave = Object.fromEntries((E.ciudad || []).map((c) => [c.clave, c]));
  const tejas = [];
  for (const [clave, nombre] of TEJAS) {
    const c = porClave[clave];
    if (!c) continue;
    const z = c.z;
    const t = el("div", { className: `teja${z >= 2 ? " alto" : z <= -2 ? " bajo" : ""}`, title: `${c.nombre}${c.normal != null ? ` · lo normal a esta hora: ${cifra(c.normal)}` : ""}` },
      el("div", { className: "n", textContent: nombre }),
      el("div", { className: "v mono" }, cifra(c.valor), el("small", { textContent: c.unidad && c.unidad.length < 12 ? c.unidad : "" })),
      el("div", { className: "z mono", textContent: c.normal != null ? `normal ${cifra(c.normal)}${z != null ? ` · z ${z > 0 ? "+" : ""}${cifra(z)}` : ""}` : "aprendiendo…" }));
    if (z != null) {
      const barra = el("i", { className: "barra" });
      barra.style.width = `${Math.min(100, Math.abs(z) * 25)}%`;
      barra.style.background = z >= 2 ? C.magenta : z <= -2 ? C.azul : C.tenue;
      t.append(barra);
    }
    tejas.push(t);
  }
  $("tejas").replaceChildren(...(tejas.length ? tejas : [el("div", { className: "vacio", textContent: "Aún no han llegado cifras." })]));
  const ultima = Math.max(0, ...(E.ciudad || []).map((c) => c.t || 0));
  $("estado-nota").textContent = ultima ? hora(ultima) : "";
}

function pintarListaBarrios() {
  const filas = Object.entries(E.barrios || {}).filter(([c, b]) => c !== "VLC" && b.nivel >= 2).sort((a, b) => b[1].nivel - a[1].nivel).slice(0, 10);
  const caja = $("lista-barrios");
  if (!filas.length) { caja.replaceChildren(el("div", { className: "vacio", textContent: E.t ? "Todos los barrios dentro de lo normal." : "Calculando…" })); return; }
  caja.replaceChildren(...filas.map(([c, b]) => {
    const fam = familiaDominante(b);
    const color = COLOR_FAMILIA[fam] || C.cian;
    const s = b.senales?.[0];
    const medidor = el("div", { className: "medidor" }, el("i"));
    medidor.firstChild.style.cssText = `width:${Math.min(100, b.nivel * 10)}%; background:${color}; box-shadow: 0 0 6px ${color}`;
    const fila = el("div", { className: "fila", onclick: () => abrirBarrio(c) },
      el("span", { className: "t", textContent: nombreBarrio(c) }), el("span", { className: "mono", style: `color:${color}`, textContent: cifra(b.nivel) }),
      el("span", { className: "s", textContent: `${NOMBRE_FAMILIA[fam] || ""}${s ? ` · ${E.rasgos?.[s.rasgo]?.nombre || s.rasgo} ${cifra(s.valor)} (normal ${cifra(s.normal)})` : ""}` }), medidor);
    return fila;
  }));
}

function pintarParte() {
  const p = E.parte || {};
  const caja = $("parte");
  caja.replaceChildren();
  if (p.ia?.texto) {
    caja.append(el("div", { textContent: p.ia.texto }), el("div", { className: "alt", textContent: p.texto }));
    $("parte-nota").textContent = `IA · ${hora(p.ia.t)}`;
  } else {
    caja.append(el("div", { textContent: p.texto || "—" }));
    $("parte-nota").textContent = p.t ? `reglas · ${hora(p.t)}` : "";
  }
}

function pintarHoy() {
  const ag = E.agenda || {};
  const fin = new Date(); fin.setHours(23, 59, 59);
  const filas = (ag.destacado || []).filter((a) => a.desde <= fin.getTime() / 1000 + 86400);
  const caja = $("hoy");
  caja.replaceChildren(...filas.slice(0, 12).map((a) => el("div", { className: "a", style: "cursor:pointer", onclick: () => (a.lat != null ? mapa.flyTo([a.lat, a.lon], 15) : null) },
    el("span", { className: "h", textContent: a.tipo === "partido" || a.tipo === "festejo" ? (a.desde < fin.getTime() / 1000 ? hora(a.desde) : fecha(a.desde).split(" ")[0]) : a.tipo === "fiesta" ? "fiesta" : "festivo" }),
    el("span", { textContent: a.titulo || "" }))));
  const cuenta = ag.cuenta || {};
  const nombres = { obra: "obras", ocupacion: "ocupaciones de vía", mudanza: "mudanzas" };
  const resumen = Object.entries(cuenta).map(([k, n]) => `${n} ${nombres[k] || k}`).join(" · ");
  if (resumen) caja.append(el("div", { className: "vacio", style: "padding-top:6px", textContent: `En curso: ${resumen}` }));
  if (!filas.length && !resumen) caja.replaceChildren(el("div", { className: "vacio", textContent: "Nada previsto." }));
  $("hoy-nota").textContent = filas.length ? `${filas.length}` : "";
}

function pintarSucesos() {
  const todos = [...(E.sucesos || [])].sort((a, b) => (b.estado === "activo") - (a.estado === "activo") || (b.estado === "activo" ? b.puntuacion - a.puntuacion : b.fin - a.fin));
  const activos = todos.filter((s) => s.estado === "activo").length;
  $("sucesos-nota").textContent = `${activos} activo${activos === 1 ? "" : "s"} · 24 h: ${todos.length}`;
  const caja = $("sucesos");
  if (!todos.length) {
    caja.replaceChildren(el("div", { className: "vacio", textContent: E.aprendiendo && !E.aprendiendo.listo
      ? "Nada fuera de lo normal. (La sala aún está aprendiendo cómo es cada barrio a cada hora: con pocos días de histórico solo salta lo muy claro.)"
      : "Nada fuera de lo normal en las últimas 24 horas." }));
    return;
  }
  caja.replaceChildren(...todos.map((s) => {
    const color = COLOR_TIPO[s.tipo] || C.cian;
    const fila = el("div", { className: `suceso ${s.estado === "activo" ? "activo" : "cerrado"}`, onclick: () => abrirSuceso(s.id) },
      el("span", { className: "marca-s" }), el("span", { className: "t", textContent: s.titulo || "Suceso" }), el("span", { className: "p", textContent: cifra(s.puntuacion) }),
      el("div", { className: "s" },
        el("span", { className: "etiqueta", style: `color:${color}`, textContent: s.tipo_nombre || s.tipo }),
        el("span", { className: "mono", textContent: s.estado === "activo" ? `desde ${hora(s.inicio)} · ${duracion(ahoraSeg() - s.inicio)}` : `${hora(s.inicio)}–${hora(s.fin)}` }),
        el("span", { className: s.explicado ? "con-causa" : "sin-causa", textContent: s.explicado ? "explicado" : "sin causa conocida" })));
    fila.style.setProperty("--c", color);
    return fila;
  }));
}

const PESTANAS_FEED = [["todo", "Todo"], ["prensa", "Prensa"], ["redes", "Redes"], ["avisos", "Avisos"]];
const pestanasFeed = $("pestanas-feed");
for (const [id, nombre] of PESTANAS_FEED) {
  const b = el("button", { type: "button", textContent: nombre });
  b.setAttribute("aria-pressed", String(ajustes.feed === id));
  b.addEventListener("click", () => { ajustes.feed = id; recordar(); for (const x of pestanasFeed.children) x.setAttribute("aria-pressed", String(x === b)); pintarFeed(); });
  pestanasFeed.append(b);
}
function filaTexto(it) {
  const color = COLOR_CATEGORIA[it.categoria] || C.gris;
  const s = el("div", { className: "s" }, el("span", { textContent: it.medio || NOMBRE_FUENTE[it.fuente] || it.fuente }));
  if (it.categoria && it.categoria !== "otros") s.append(el("span", { className: "etiqueta", style: `color:${color}`, textContent: it.categoria }));
  if (it.barrio) s.append(el("span", { textContent: nombreBarrio(it.barrio) }));
  if (it.lat != null) s.append(el("span", { className: "ir", textContent: "⌖ ver", title: "Ver en el mapa", onclick: () => { ponerVista("mapa"); mapa.flyTo([it.lat, it.lon], 16); } }));
  const reciente = ahoraSeg() - it.t < 20 * 3600;
  const d = new Date(it.t * 1000);
  return el("div", { className: `texto${(it.urgencia || 0) >= 2 ? " urgente" : ""}` },
    el("span", { className: "h", title: `${fecha(it.t)} ${hora(it.t)}`, textContent: reciente ? hora(it.t) : `${d.getDate()}/${d.getMonth() + 1}` }),
    el("div", { className: "t" }, enlace(it.titulo || "(sin título)", it.url)), s);
}
function pintarFeed() {
  const caja = $("feed");
  let lista;
  if (ajustes.feed === "avisos") lista = E.avisos || [];
  const TEMAS_SALA = ["emergencia", "accidente", "seguridad", "protesta", "trafico", "transporte", "meteo", "evento", "deporte"];
  if (ajustes.feed !== "avisos") lista = (E.feed || []).filter((it) => ajustes.feed === "todo"
    ? it.fuente === "prensa" || (["bluesky", "mastodon"].includes(it.fuente) && it.barrio && TEMAS_SALA.includes(it.categoria))
    : ajustes.feed === "prensa" ? it.fuente === "prensa" : ["bluesky", "mastodon"].includes(it.fuente));
  const filas = lista.slice(0, 80).map(filaTexto);
  if (ajustes.feed === "redes" && E.publico) {
    const c = E.conversacion || {};
    filas.unshift(el("div", { className: "aviso-web", textContent: `En la web solo se cuentan las publicaciones de redes (en el ordenador se ven enteras): ${c.publicaciones || 0} sobre la ciudad en las últimas dos horas.` }));
  }
  caja.replaceChildren(...(filas.length ? filas : [el("div", { className: "vacio", textContent: "Nada todavía." })]));
}

/* ====================== Cargar ====================== */
let relojCarga = 0;
async function cargar() {
  clearTimeout(relojCarga);
  try {
    E = await pedirJSON(servidor ? "vivo/sala/estado" : `${BASE}sala.json`);
    ultimoError = null;
    if (!geo && E.hay) {
      geo = await pedirJSON(servidor ? "vivo/sala/barrios" : `${BASE}sala-barrios.json`).catch(() => null);
      for (const f of geo?.features || []) props[f.properties.codigo] = f.properties;
    }
    pintarTodo();
  } catch (err) {
    ultimoError = err;
    if (!E) {
      $("aviso-mapa").hidden = false;
      $("aviso-titulo").textContent = "Sin datos de la sala";
      $("aviso-texto").textContent = servidor ? `El programa no contesta (${err.message}).` : "Aún no se han publicado los datos de la sala. Se suben desde el ordenador con «osintmaps servir --pulso --publicar-datos».";
    }
  }
  relojCarga = setTimeout(cargar, servidor ? 30000 : 120000);
}
function pintarTodo() {
  if (!E) return;
  pintarCabecera(); pintarReloj();
  pintarTejas(); pintarListaBarrios(); pintarParte(); pintarHoy(); pintarSucesos(); pintarFeed();
  pintarBarrios(); pintarCapas(); pintarLeyenda();
}

/* ====================== La ficha ====================== */
function abrirFicha({ tipo, color = C.cian, titulo, sub, clave, estrecha = false }) {
  const f = $("ficha");
  f.replaceChildren();
  f.classList.toggle("estrecha", estrecha);
  f.style.setProperty("--c", color);
  const h3 = el("h3", { textContent: titulo || "" });
  const cab = el("div", { className: "cab" },
    el("div", { style: "min-width:0" }, el("div", { className: "tipo", textContent: tipo }), h3, sub ? el("div", { className: "sub" }, sub) : null),
    el("button", { className: "cerrar", type: "button", title: "Cerrar (Esc)", textContent: "×", onclick: cerrarFicha }));
  const contenido = el("div", { className: "contenido" });
  f.append(cab, contenido);
  f.hidden = false;
  L.DomEvent.disableClickPropagation(f); L.DomEvent.disableScrollPropagation(f);
  fichaAbierta = clave;
  if (clave) history.replaceState(null, "", `#${clave}`);
  if (movil()) ponerVista("mapa");
  contenido.titulo = h3;
  return contenido;
}
function cerrarFicha() {
  $("ficha").hidden = true;
  fichaAbierta = null;
  capas.foco.clearLayers();
  if (modo.tipo !== "nivel") { modo = { tipo: "nivel" }; pintarBarrios(); pintarLeyenda(); }
  history.replaceState(null, "", location.pathname + location.search);
}
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !$("ficha").hidden) cerrarFicha(); });
const seccion = (titulo, ...hijos) => el("section", {}, el("h4", { textContent: titulo }), ...hijos);
const cargando = (caja) => caja.replaceChildren(el("p", { className: "vacio", textContent: "Cargando…" }));
const fallo = (caja, err) => caja.replaceChildren(el("p", { className: "vacio", textContent: `No se ha podido cargar: ${err.message}` }));
const avisoWeb = (texto) => el("div", { className: "aviso-web", textContent: texto });
function resaltarBarrios(codigos, color = C.magenta) {
  capas.foco.clearLayers();
  if (!geo) return;
  const set = new Set(codigos);
  const elegidos = geo.features.filter((f) => set.has(f.properties.codigo));
  if (elegidos.length) L.geoJSON({ type: "FeatureCollection", features: elegidos }, { pane: "barrios", interactive: false,
    style: { color, weight: 3, opacity: 1, fill: false, dashArray: "6 4" } }).addTo(capas.foco);
  return elegidos;
}
function tablaSenales(senales) {
  if (!senales?.length) return el("p", { className: "vacio", textContent: "Sin señales." });
  const t = el("table", { className: "datos" }, el("tr", {}, ...["Barrio", "Qué", "Ahora", "Normal", "z"].map((x) => el("th", { textContent: x }))));
  for (const s of senales) {
    const info = E?.rasgos?.[s.rasgo] || {};
    const z = s.z;
    t.append(el("tr", {},
      el("td", { textContent: s.barrio === "barrios" ? "la mitad de los barrios" : nombreBarrio(s.barrio) }),
      el("td", { textContent: `${info.nombre || s.rasgo}` }),
      el("td", { className: "num", textContent: s.valor == null ? "—" : `${cifra(s.valor)} ${info.unidad && info.unidad.length < 10 ? info.unidad : ""}` }),
      el("td", { className: "num", textContent: cifra(s.normal) }),
      el("td", { className: `num ${z >= 1 ? "z-pos" : z <= -1 ? "z-neg" : "z-0"}`, textContent: z == null ? "—" : `${z > 0 ? "+" : ""}${cifra(z)}` })));
  }
  return t;
}
function listaCausas(causa) {
  const caja = el("div");
  const candidatas = causa?.candidatas || [];
  if (!candidatas.length) caja.append(el("p", { className: "sin-causa", textContent: "Sin causa conocida: nada previsto en la zona, ni lluvia, ni noticias que lo expliquen." }));
  for (const c of candidatas) {
    caja.append(el("div", { className: "causa" },
      el("span", { className: "etiqueta", style: `color:${c === causa.probable ? C.lima : C.suave}`, textContent: c.tipo }),
      el("span", {}, enlace(c.titulo || "", c.url), c.desde ? el("span", { className: "pie", textContent: ` · ${fechaHora(c.desde)}` }) : null),
      el("span", { className: "peso mono", style: `color:${c.peso >= 0.5 ? C.lima : C.suave}`, title: "Lo que encaja esta causa (0 a 1)", textContent: cifra(c.peso, 2) })));
  }
  return caja;
}

/* ---------- Gráficas ---------- */
function marcasDeTiempo(x0, x1) {
  const pasos = [600, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
  const paso = pasos.find((p) => (x1 - x0) / p <= 6) || 86400;
  const salida = [];
  for (let x = Math.ceil(x0 / paso) * paso; x <= x1; x += paso) salida.push([x, hora(x)]);
  return salida;
}
const marcasDeFranjas = () => [0, 6, 12, 18, 24, 30, 36, 42].map((s) => [s, `${dos(s / 2)}h`]);
function grafica(lienzo, series, op = {}) {
  const dpr = window.devicePixelRatio || 1, w = lienzo.clientWidth || 480, h = lienzo.clientHeight || 120;
  lienzo.width = Math.round(w * dpr); lienzo.height = Math.round(h * dpr);
  const g = lienzo.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const pts = series.flatMap((s) => s.puntos.filter((p) => p[1] != null));
  g.font = "10px 'JetBrains Mono', monospace";
  if (!pts.length) { g.fillStyle = C.tenue; g.fillText("Sin datos aún", 8, h / 2); return; }
  const x0 = op.x0 ?? Math.min(...pts.map((p) => p[0])), x1 = op.x1 ?? Math.max(...pts.map((p) => p[0]));
  let y0 = Math.min(...pts.map((p) => p[1])), y1 = Math.max(...pts.map((p) => p[1]));
  if (op.cero !== false && y0 > 0) y0 = 0;
  if (y1 === y0) y1 = y0 + 1;
  y1 += (y1 - y0) * 0.08;
  const iz = 38, de = 8, ar = op.leyenda ? 16 : 6, ab = 16;
  const X = (x) => iz + ((x - x0) / (x1 - x0 || 1)) * (w - iz - de);
  const Y = (y) => ar + (1 - (y - y0) / (y1 - y0)) * (h - ar - ab);
  if (op.banda) { g.fillStyle = "rgba(255,45,149,.09)"; g.fillRect(X(op.banda[0]), ar, Math.max(2, X(op.banda[1]) - X(op.banda[0])), h - ar - ab); }
  g.strokeStyle = "rgba(34,211,238,.09)"; g.lineWidth = 1; g.fillStyle = C.tenue; g.textAlign = "right"; g.textBaseline = "middle";
  for (let k = 0; k <= 3; k++) {
    const v = y0 + (k / 3) * (y1 - y0), y = Y(v);
    g.beginPath(); g.moveTo(iz, y); g.lineTo(w - de, y); g.stroke(); g.fillText(cifraCorta(v), iz - 5, y);
  }
  g.textAlign = "center"; g.textBaseline = "top";
  for (const [x, txt] of (op.marcas || marcasDeTiempo)(x0, x1)) {
    const xx = X(x);
    if (xx < iz - 1 || xx > w - de + 1) continue;
    g.fillText(txt, xx, h - ab + 3);
    g.strokeStyle = "rgba(34,211,238,.05)"; g.beginPath(); g.moveTo(xx, ar); g.lineTo(xx, h - ab); g.stroke();
  }
  for (const s of series) {
    g.strokeStyle = s.color; g.lineWidth = s.grosor || 1.7; g.setLineDash(s.discontinua ? [4, 3] : []);
    g.beginPath(); let dentro = false;
    for (const [x, y] of s.puntos) {
      if (y == null) { dentro = false; continue; }
      const xx = X(x), yy = Y(y);
      dentro ? g.lineTo(xx, yy) : g.moveTo(xx, yy); dentro = true;
    }
    g.stroke(); g.setLineDash([]);
  }
  if (op.cursor != null) { g.strokeStyle = C.magenta; g.lineWidth = 1.2; g.beginPath(); g.moveTo(X(op.cursor), ar); g.lineTo(X(op.cursor), h - ab); g.stroke(); }
  if (op.leyenda) {
    let xx = iz + 2; g.textAlign = "left"; g.textBaseline = "top";
    for (const s of series.filter((x) => x.nombre)) {
      g.fillStyle = s.color; g.fillRect(xx, 6, 10, 2);
      g.fillStyle = C.suave; g.fillText(s.nombre, xx + 13, 1);
      xx += 22 + g.measureText(s.nombre).width;
    }
  }
}
const lienzo = (alta = false) => el("canvas", { className: `grafica${alta ? " alta" : ""}` });
const COLORES_SERIE = [C.cian, C.magenta, C.ambar, C.lima];

/* ---------- Suceso ---------- */
async function abrirSuceso(id) {
  const corto = (E?.sucesos || []).find((s) => s.id === id);
  const color = COLOR_TIPO[corto?.tipo] || C.cian;
  const cont = abrirFicha({ tipo: `${corto?.tipo_nombre || "Suceso"} · ${corto?.estado === "activo" ? "en marcha" : "cerrado"}`, color, titulo: corto?.titulo || "Suceso", clave: `suceso=${id}`,
    sub: corto ? `${fechaHora(corto.inicio)} → ${corto.estado === "activo" ? "ahora" : hora(corto.fin)} · ${duracion((corto.estado === "activo" ? ahoraSeg() : corto.fin) - corto.inicio)} · puntuación ${cifra(corto.puntuacion)}` : null });
  const barrios = corto ? (corto.barrios || []).filter((b) => b !== "VLC") : [];
  const elegidos = resaltarBarrios(barrios, color);
  if (elegidos?.length) mapa.flyToBounds(L.geoJSON({ type: "FeatureCollection", features: elegidos }).getBounds(), { padding: [40, 40], maxZoom: 15, duration: 0.6 });
  if (!servidor) { pintarSucesoCorto(cont, corto); return; }
  cargando(cont);
  try {
    const d = await pedirJSON(`vivo/sala/evento?id=${encodeURIComponent(id)}`);
    if (fichaAbierta !== `suceso=${id}`) return;
    cont.replaceChildren();
    pintarSucesoEntero(cont, d, color);
  } catch (err) { fallo(cont, err); }
}
function relacionados(id, causaId) {
  const otros = (E?.sucesos || []).filter((x) => x.id !== id && causaId && x.causa?.id === causaId);
  if (!otros.length) return null;
  return seccion("Con la misma causa", ...otros.map((x) => el("div", { className: "fila", onclick: () => abrirSuceso(x.id) },
    el("span", { className: "t", textContent: x.titulo }), el("span", { className: "mono", textContent: hora(x.inicio) }))));
}
function pintarSucesoCorto(cont, s) {
  if (!s) { cont.append(el("p", { className: "vacio", textContent: "Ese suceso ya no está en los datos publicados." })); return; }
  if (s.resumen) cont.append(seccion("Resumen", el("div", { className: "resumen" }, s.resumen, el("small", { textContent: "IA local" }))));
  cont.append(seccion("Por qué", s.causa ? listaCausas({ candidatas: [s.causa], probable: s.causa }) : el("p", { className: "sin-causa", textContent: "Sin causa conocida." })));
  const senales = (s.ahora?.length ? s.ahora : s.barrios).flatMap((b) => (E.barrios?.[b]?.senales || []).map((x) => ({ ...x, barrio: b })));
  cont.append(seccion("Señales ahora", tablaSenales(senales)));
  cont.append(seccion("Barrios", el("div", {}, ...(s.barrios || []).map((b) => el("button", { className: "boton-fino", style: "margin:0 4px 4px 0", type: "button", textContent: nombreBarrio(b), onclick: () => abrirBarrio(b) })))));
  const rel = relacionados(s.id, s.causa?.id); if (rel) cont.append(rel);
  cont.append(avisoWeb("La evolución de cada señal, los textos y los helicópteros de la zona se ven en el programa del ordenador."));
}
function pintarSucesoEntero(cont, d, color) {
  const s = d.suceso;
  if (s.resumen) cont.append(seccion("Resumen", el("div", { className: "resumen" }, s.resumen, el("small", { textContent: "IA local · a partir de las señales y lo publicado" }))));
  cont.append(seccion("Por qué", listaCausas(s.causa)));
  const rel = relacionados(s.id, s.causa?.probable?.id); if (rel) cont.append(rel);
  cont.append(seccion("Señales en el momento más fuerte", tablaSenales(s.evidencias?.pico || []),
    el("p", { className: "pie", textContent: `Pico a las ${hora(s.pico)}. z: cuánto se separa de lo normal para ese barrio a esa hora (±2 ya es raro).` })));
  for (const [rasgo, serie] of Object.entries(d.series || {})) {
    const info = d.rasgos?.[rasgo] || {};
    const lineas = [];
    Object.entries(serie.valores || {}).slice(0, 3).forEach(([b, puntos], k) => {
      lineas.push({ nombre: d.nombres?.[b] || b, color: COLORES_SERIE[k], puntos });
      const normal = serie.normal?.[b];
      if (normal?.length) lineas.push({ color: COLORES_SERIE[k], discontinua: true, grosor: 1.1, puntos: normal });
    });
    const c = lienzo();
    cont.append(seccion(`${info.nombre || rasgo} (${info.unidad || ""})`, c, el("p", { className: "pie", textContent: "Línea: lo que marcaba. Discontinua: lo normal a esa hora. Rosa: el suceso." })));
    requestAnimationFrame(() => grafica(c, lineas, { x0: d.desde, x1: d.hasta, banda: [s.inicio, s.fin], leyenda: true }));
  }
  if (Object.keys(d.nivel || {}).length) {
    const c = lienzo();
    cont.append(seccion("Nivel de cada barrio", c));
    requestAnimationFrame(() => grafica(c, Object.entries(d.nivel).slice(0, 4).map(([b, p], k) => ({ nombre: d.nombres?.[b] || b, color: COLORES_SERIE[k], puntos: p })),
      { x0: d.desde, x1: d.hasta, banda: [s.inicio, s.fin], leyenda: true }));
  }
  const textos = s.causa?.textos || [];
  if (textos.length) cont.append(seccion("Lo que se ha publicado de la zona", ...textos.map((t) => filaTexto({ ...t, medio: NOMBRE_FUENTE[t.fuente] }))));
  const helis = Object.entries(d.helicopteros || {});
  if (helis.length) {
    for (const [, h] of helis) L.polyline(h.p.map((x) => [x[1], x[2]]), { color: C.rojo, weight: 2.2, opacity: 0.9 }).addTo(capas.foco);
    cont.append(seccion("Helicópteros sobre la zona", el("p", { textContent: helis.map(([id, h]) => `${h.nombre || id} (${hora(h.p[0][0])}–${hora(h.p[h.p.length - 1][0])})`).join(" · ") }),
      el("p", { className: "pie", textContent: "Su recorrido está dibujado en rojo en el mapa. Son aeronaves que emiten su posición (ADS-B)." })));
  }
  cont.append(seccion("Barrios", el("div", {}, ...(s.barrios || []).filter((b) => b !== "VLC").map((b) => el("button", { className: "boton-fino", style: "margin:0 4px 4px 0", type: "button", textContent: nombreBarrio(b), onclick: () => abrirBarrio(b) })))));
}

/* ---------- Barrio ---------- */
async function abrirBarrio(codigo) {
  const p = props[codigo] || {};
  const b = E?.barrios?.[codigo];
  const cont = abrirFicha({ tipo: "Barrio", color: COLOR_FAMILIA[familiaDominante(b)] || C.cian, titulo: nombreBarrio(codigo), clave: `barrio=${codigo}`,
    sub: p.distrito_nombre ? `Distrito ${p.distrito_nombre}` : null });
  resaltarBarrios([codigo], C.cian);
  if (!servidor) { pintarBarrioCorto(cont, codigo, b, p); return; }
  cargando(cont);
  try {
    const d = await pedirJSON(`vivo/sala/barrio?codigo=${encodeURIComponent(codigo)}`);
    if (fichaAbierta !== `barrio=${codigo}`) return;
    cont.replaceChildren();
    pintarBarrioEntero(cont, d);
  } catch (err) { fallo(cont, err); }
}
function seccionAhora(b) {
  if (!b) return seccion("Ahora", el("p", { className: "vacio", textContent: "Sin datos aún." }));
  const familias = Object.entries(b.familias || {}).sort((x, y) => y[1] - x[1]);
  const caja = el("div");
  caja.append(el("p", { textContent: b.nivel >= 3 ? `Fuera de lo normal (nivel ${cifra(b.nivel)}).` : b.nivel >= 1.5 ? `Algo distinto de lo normal (nivel ${cifra(b.nivel)}).` : "Dentro de lo normal." }));
  for (const [f, v] of familias) {
    const m = el("div", { className: "medidor" }, el("i"));
    m.firstChild.style.cssText = `width:${Math.min(100, v * 10)}%; background:${COLOR_FAMILIA[f]}`;
    caja.append(el("div", { className: "fila", style: "cursor:default" }, el("span", { textContent: NOMBRE_FAMILIA[f] || f }), el("span", { className: "mono", textContent: cifra(v) }), m));
  }
  return seccion("Ahora", caja, tablaSenales((b.senales || []).map((s) => ({ ...s }))));
}
function seccionValores(b) {
  const filas = Object.entries(b?.valores || {}).filter(([r]) => E?.rasgos?.[r]);
  if (!filas.length) return null;
  const t = el("table", { className: "datos" }, el("tr", {}, ...["Qué", "Ahora", "Normal"].map((x) => el("th", { textContent: x }))));
  for (const [r, v] of filas) {
    const info = E.rasgos[r];
    t.append(el("tr", {}, el("td", { textContent: `${info.nombre}${info.unidad ? ` (${info.unidad})` : ""}` }), el("td", { className: "num", textContent: cifra(v) }),
      el("td", { className: "num", textContent: cifra(b.normal?.[r]) })));
  }
  return seccion("Todas las cifras del barrio", t);
}
function seccionContexto(ctx, p) {
  const v = ctx?.vulnerabilidad || {}, q = ctx?.quejas, a = ctx?.accidentes;
  const caja = el("div", { className: "rejilla-2" });
  const dato = (n, val) => el("div", { className: "dato" }, el("div", { className: "n", textContent: n }), el("div", { className: "v", textContent: val }));
  if (v.vul_global || p?.vulnerabilidad_texto) caja.append(dato("Vulnerabilidad", `${v.vul_global || p.vulnerabilidad_texto} (${cifra(v.ind_global ?? p.vulnerabilidad)})`));
  if (v.vul_econom) caja.append(dato("Económica", v.vul_econom.replace("Vulnerabilidad ", "")));
  if (v.vul_dem) caja.append(dato("Demográfica", v.vul_dem.replace("Vulnerabilidad ", "")));
  if (v.vul_equip) caja.append(dato("Equipamientos", v.vul_equip.replace("Vulnerabilidad ", "")));
  if (q || p?.quejas != null) caja.append(dato("Quejas y sugerencias (12 meses)", cifra(q?.total ?? p.quejas)));
  if (a || p?.accidentes != null) caja.append(dato("Accidentes situados (12 meses)", a ? `${cifra(a.total)} · ${cifra(a.heridos)} con heridos · ${cifra(a.graves)} graves` : cifra(p.accidentes)));
  const extra = [];
  if (q?.temas?.length) extra.push(el("p", { className: "pie", style: "margin-top:8px", textContent: `De qué se quejan: ${q.temas.map(([t, n]) => `${t} (${n})`).join(" · ")}` }));
  if (!caja.children.length && !extra.length) return null;
  return seccion("Contexto (Ajuntament de València)", caja, ...extra);
}
function pintarBarrioCorto(cont, codigo, b, p) {
  cont.append(seccionAhora(b));
  const vals = seccionValores(b); if (vals) cont.append(vals);
  const ctx = seccionContexto(null, p); if (ctx) cont.append(ctx);
  const sucesos = (E?.sucesos || []).filter((s) => (s.barrios || []).includes(codigo));
  if (sucesos.length) cont.append(seccion("Sucesos (24 h)", ...sucesos.map((s) => el("div", { className: "fila", onclick: () => abrirSuceso(s.id) }, el("span", { className: "t", textContent: s.titulo }), el("span", { className: "mono", textContent: hora(s.inicio) })))));
  cont.append(avisoWeb("El histórico del barrio, sus sucesos del último mes, sus obras y lo publicado se ven en el programa del ordenador."));
}
function pintarBarrioEntero(cont, d) {
  cont.append(seccionAhora(d.actual));
  if (d.nivel_24h?.length) {
    const c = lienzo();
    cont.append(seccion("Nivel en las últimas 24 horas", c));
    requestAnimationFrame(() => grafica(c, [{ color: C.cian, puntos: d.nivel_24h }], { x0: ahoraSeg() - 86400, x1: ahoraSeg() }));
  }
  const vals = seccionValores(d.actual); if (vals) cont.append(vals);
  const ctx = seccionContexto(d.contexto, props[d.codigo]); if (ctx) cont.append(ctx);
  if (d.sucesos?.length) cont.append(seccion("Sucesos del último mes", ...d.sucesos.map((s) => el("div", { className: "fila", onclick: () => abrirSuceso(s.id) },
    el("span", { className: "t", textContent: s.titulo }), el("span", { className: "mono", textContent: fecha(s.inicio) })))));
  if (d.agenda?.length) cont.append(seccion(`Obras, ocupaciones y festejos (${d.agenda.length})`, ...d.agenda.slice(0, 25).map((a) => el("div", { className: "fila", style: "cursor:default" },
    el("span", { textContent: a.titulo || a.tipo }), el("span", { className: "mono pie", textContent: `hasta ${fecha(a.hasta)}` })))));
  if (d.items?.length) cont.append(seccion("Lo publicado (7 días)", ...d.items.slice(0, 25).map((t) => filaTexto({ ...t, medio: NOMBRE_FUENTE[t.fuente] }))));
  cont.append(seccion("Vecinos", el("div", {}, ...(d.vecinos || []).map((v) => el("button", { className: "boton-fino", style: "margin:0 4px 4px 0", type: "button", textContent: v.nombre, onclick: () => abrirBarrio(v.codigo) })))));
}

/* ---------- Un punto: la ficha del inmueble ---------- */
async function abrirLugar(lat, lon) {
  if (investigando) { investigando = false; bInvestigar.setAttribute("aria-pressed", "false"); $("mapa-zona").classList.remove("investigando"); }
  const clave = `lugar=${lat.toFixed(5)},${lon.toFixed(5)}`;
  const cont = abrirFicha({ tipo: "Inmueble · punto", color: C.magenta, titulo: `${lat.toFixed(5)}, ${lon.toFixed(5)}`, clave });
  capas.foco.clearLayers();
  L.circleMarker([lat, lon], { radius: 9, color: C.magenta, weight: 2, fill: false }).addTo(capas.foco);
  L.circleMarker([lat, lon], { radius: 2.5, color: C.magenta, weight: 0, fillColor: C.magenta, fillOpacity: 1 }).addTo(capas.foco);
  const visor = el("a", { className: "boton-fino", href: `./#mapa=19/${lat.toFixed(6)}/${lon.toFixed(6)}`, textContent: "Ver en el mapa completo ↗",
    title: "El mapa completo: fotos aéreas de otros años, Catastro, la historia del sitio" });
  if (!servidor) {
    cont.append(avisoWeb("La ficha de un inmueble (Catastro, patrimonio, registro de solares, accidentes de esa esquina, obras...) la prepara el programa del ordenador."),
      el("section", {}, visor));
    return;
  }
  cargando(cont);
  try {
    const d = await pedirJSON(`vivo/sala/lugar?lat=${lat}&lon=${lon}`);
    if (fichaAbierta !== clave) return;
    cont.replaceChildren();
    pintarLugar(cont, d, visor);
  } catch (err) { fallo(cont, err); }
}
function pintarLugar(cont, d, visor) {
  if (d.calle) cont.titulo.textContent = `${d.calle.nombre}${d.calle.numero ? `, ${d.calle.numero}` : ""}`;
  const dato = (n, val) => el("div", { className: "dato" }, el("div", { className: "n", textContent: n }), el("div", { className: "v" }, val));
  const base = el("div", { className: "rejilla-2" });
  if (d.barrio) base.append(dato("Barrio", el("a", { href: "#", textContent: d.barrio_nombre || d.barrio, onclick: (ev) => { ev.preventDefault(); abrirBarrio(d.barrio); } })));
  if (d.calle) base.append(dato("Calle más cercana", `${d.calle.nombre}${d.calle.numero ? ` ${d.calle.numero}` : ""} (a ${d.calle.metros} m)`));
  base.append(dato("Coordenadas", `${d.lat}, ${d.lon}`));
  cont.append(seccion("Dónde", base));
  const cat = d.catastro || {};
  if (cat.rc || cat.error) {
    const caja = el("div", { className: "rejilla-2" });
    if (cat.rc) caja.append(dato("Referencia catastral", cat.enlace ? enlace(cat.rc, cat.enlace) : cat.rc));
    if (cat.direccion) caja.append(dato("Dirección catastral", cat.direccion));
    if (cat.uso) caja.append(dato("Uso", cat.uso));
    if (cat["año"]) caja.append(dato("Construido", String(cat["año"])));
    if (cat.inmuebles) caja.append(dato("Inmuebles en la parcela", cifra(cat.inmuebles)));
    if (cat.superficie || cat.superficie_total) caja.append(dato("Superficie construida", `${cifra(cat.superficie_total || cat.superficie)} m²`));
    if (cat.usos?.length > 1) caja.append(dato("Usos", cat.usos.map(([u, n]) => `${u} (${n})`).join(", ")));
    if (cat.parcela) caja.append(dato("Parcela", cat.parcela));
    if (cat.suelo) caja.append(dato("Suelo", `${cifra(cat.suelo)} m²`));
    if (cat.tipologia) caja.append(dato("Tipología", cat.tipologia));
    if (cat.construcciones?.length) caja.append(dato("Construcción", cat.construcciones.map(([u, m]) => `${u} ${cifra(m)} m²`).join(" · ")));
    if (cat.plano) caja.append(dato("Plano", enlace("cartografía catastral ↗", cat.plano)));
    if (cat.error) caja.append(dato("Catastro", `no ha contestado (${cat.error})`));
    cont.append(seccion("Catastro (datos no protegidos)", caja));
  }
  if (d.patrimonio?.length) cont.append(seccion("Patrimonio catalogado", ...d.patrimonio.map((p) => el("div", { className: "fila", style: "cursor:default" },
    el("span", { className: "t", textContent: p.nombre || p.codigo }), el("span", { className: "etiqueta", style: `color:${C.ambar}`, textContent: p.proteccion || "" }),
    el("span", { className: "s", textContent: [p.categoria, p.elemento, p.metros ? `a ${p.metros} m` : "aquí"].filter(Boolean).join(" · ") })))));
  if (d.registro?.length) cont.append(seccion("Registro municipal de solares y edificios a rehabilitar", ...d.registro.map((r) => el("div", { className: "fila", style: "cursor:default" },
    el("span", { className: "t", textContent: `${r.seccion || ""} · ${r.direccion || ""}` }), el("span", { className: "mono pie", textContent: r.refcat || "" })))));
  if (d.vpp?.length) cont.append(seccion("Vivienda de protección pública", ...d.vpp.map((v) => el("p", { textContent: [`${cifra(v.viviendas)} viviendas`, v.tipo, v.regimen, v.promocion, v.uso].filter(Boolean).join(" · ") }))));
  if (d.zas?.length) cont.append(seccion("Zona acústicamente saturada", el("p", { textContent: d.zas.join(", ") })));
  if (d.accidentes?.length) {
    const graves = d.accidentes.filter((a) => a.gravedad >= 3).length;
    cont.append(seccion(`Accidentes de tráfico a menos de 40 m (${d.accidentes.length}${graves ? `, ${graves} graves` : ""})`,
      ...d.accidentes.slice(0, 15).map((a) => el("div", { className: "fila", style: "cursor:default" },
        el("span", { textContent: `${a.tipo || "Accidente"} · ${a.unidades || ""}` }), el("span", { className: "mono pie", textContent: fecha(a.t) }),
        el("span", { className: "s", style: a.gravedad >= 3 ? `color:${C.rojo}` : "", textContent: `${GRAVEDAD[a.gravedad] || ""} · ${a.ubicacion}` })))));
  }
  if (d.agenda?.length) cont.append(seccion("Obras y ocupaciones registradas aquí", ...d.agenda.slice(0, 15).map((a) => el("div", { className: "fila", style: "cursor:default" },
    el("span", { textContent: a.titulo || a.tipo }), el("span", { className: "mono pie", textContent: `${fecha(a.desde)} → ${fecha(a.hasta)}` })))));
  if (d.cerca?.length) cont.append(seccion("Al lado", el("p", { textContent: d.cerca.map((c) => `${c.nombre} (${c.metros} m)`).join(" · ") })));
  if (d.textos?.length) cont.append(seccion("Noticias y avisos de este punto (6 meses)", ...d.textos.map((t) => filaTexto({ ...t, medio: NOMBRE_FUENTE[t.fuente] }))));
  if (d.sucesos?.length) cont.append(seccion("Sucesos en el barrio (90 días)", ...d.sucesos.map((s) => el("div", { className: "fila", onclick: () => abrirSuceso(s.id) },
    el("span", { className: "t", textContent: s.titulo }), el("span", { className: "mono", textContent: fecha(s.inicio) })))));
  cont.append(el("section", {}, visor, el("p", { className: "pie", style: "margin-top:8px", textContent: "Solo datos públicos de inmuebles y calles: nada sobre quién vive o es propietario." })));
}

/* ---------- Comparar dos días ---------- */
let perfilesWeb = null;
async function abrirComparar() {
  const cont = abrirFicha({ tipo: "Comparar", color: C.cian, titulo: "¿Cómo cambia la ciudad de un día a otro?", clave: "comparar", estrecha: true,
    sub: "Media de cada media hora con todo el histórico (o un día concreto)" });
  const rasgos = servidor ? Object.keys(E?.rasgos || {}).concat(["nivel"]) : RASGOS_WEB;
  const sRasgo = el("select", {}, ...rasgos.map((r) => el("option", { value: r, textContent: r === "nivel" ? "Nivel (fuera de lo normal)" : E?.rasgos?.[r]?.nombre || r })));
  sRasgo.value = rasgos.includes(ajustes.compararRasgo) ? ajustes.compararRasgo : "aforo";
  const opciones = () => [["L", "Laborable (media)"], ["S", "Sábado (media)"], ["D", "Domingo o festivo (media)"]];
  const sA = el("select", {}, ...opciones().map(([v, t]) => el("option", { value: v, textContent: t })));
  const sB = el("select", {}, ...opciones().map(([v, t]) => el("option", { value: v, textContent: t })));
  sA.value = "L"; sB.value = "S";
  const franjaAhora = (() => { const d = new Date(); return d.getHours() * 2 + (d.getMinutes() >= 30 ? 1 : 0); })();
  const rHora = el("input", { type: "range", min: 0, max: 47, step: 1, value: franjaAhora });
  const etHora = el("span", { className: "mono" });
  const bPlay = el("button", { type: "button", className: "boton-fino", textContent: "▶ Día entero" });
  cont.append(el("div", { className: "controles" }, el("label", {}, "Qué", sRasgo), el("label", {}, "A", sA), el("label", {}, "B", sB)),
    el("div", { className: "controles" }, el("label", { style: "flex:1" }, el("span", {}, "Hora ", etHora), rHora), bPlay));
  const c = lienzo(true);
  const nota = el("p", { className: "pie" });
  const ranking = el("div");
  cont.append(seccion("Toda la ciudad", c, nota), seccion("Dónde cambia más a esa hora", ranking));
  let datos = null, reloj = 0;
  const cargarFechas = async () => {
    if (!servidor) return;
    try {
      const d = await pedirJSON(`vivo/sala/comparar?rasgo=${sRasgo.value}&a=L&b=S`);
      for (const s of [sA, sB]) for (const dia of (d.dias || []).slice(-45).reverse()) s.append(el("option", { value: dia, textContent: fecha(new Date(`${dia}T12:00`).getTime() / 1000) }));
    } catch { /* sin fechas */ }
  };
  async function recargar() {
    ajustes.compararRasgo = sRasgo.value; recordar();
    try {
      if (servidor) datos = await pedirJSON(`vivo/sala/comparar?rasgo=${encodeURIComponent(sRasgo.value)}&a=${encodeURIComponent(sA.value)}&b=${encodeURIComponent(sB.value)}`);
      else {
        perfilesWeb ||= await pedirJSON(`${BASE}sala-perfiles.json`);
        const r = perfilesWeb.rasgos?.[sRasgo.value] || {};
        const valores = (v) => (["L", "S", "D"].includes(v) ? r[v] || {} : {});
        datos = { nombre: r.nombre, unidad: r.unidad, a: { nombre: sA.selectedOptions[0].textContent, valores: valores(sA.value) }, b: { nombre: sB.selectedOptions[0].textContent, valores: valores(sB.value) } };
      }
      pintar();
    } catch (err) { nota.textContent = `No se ha podido cargar: ${err.message}`; }
  }
  function pintar() {
    if (!datos || fichaAbierta !== "comparar") return;
    const k = Number(rHora.value);
    etHora.textContent = `${dos(Math.floor(k / 2))}:${k % 2 ? "30" : "00"}`;
    const a = datos.a?.valores || {}, b = datos.b?.valores || {};
    const ciudadA = a.VLC || [], ciudadB = b.VLC || [];
    grafica(c, [{ nombre: `A · ${sA.selectedOptions[0].textContent}`, color: C.naranja, puntos: ciudadA.map((v, i) => [i, v]) },
      { nombre: `B · ${sB.selectedOptions[0].textContent}`, color: C.cian, puntos: ciudadB.map((v, i) => [i, v]) }],
    { x0: 0, x1: 47, cursor: k, marcas: marcasDeFranjas, leyenda: true });
    const dif = {};
    for (const codigo of Object.keys(props)) {
      const va = a[codigo]?.[k], vb = b[codigo]?.[k];
      if (va != null && vb != null) dif[codigo] = vb - va;
    }
    const absolutos = Object.values(dif).map(Math.abs).sort((x, y) => x - y);
    const escala = absolutos.length ? absolutos[Math.floor(absolutos.length * 0.9)] || absolutos[absolutos.length - 1] : 0;
    modo = { tipo: "comparar", valores: dif, escala, pos: C.cian, neg: C.naranja, etiqueta: "B − A", unidad: datos.unidad,
      titulo: `${datos.nombre || sRasgo.value}: B − A a las ${etHora.textContent}`, izquierda: "más en A", derecha: "más en B" };
    pintarBarrios(); pintarLeyenda();
    const va = ciudadA[k], vb = ciudadB[k];
    nota.textContent = va == null || vb == null ? "Aún no hay histórico suficiente de alguno de los dos días."
      : `A las ${etHora.textContent}: A ${cifra(va)}, B ${cifra(vb)} ${datos.unidad || ""} (${vb >= va ? "+" : ""}${cifra(vb - va)}).`;
    const orden = Object.entries(dif).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1])).slice(0, 10);
    ranking.replaceChildren(...(orden.length ? orden.map(([codigo, v]) => el("div", { className: "fila", onclick: () => abrirBarrio(codigo) },
      el("span", { className: "t", textContent: nombreBarrio(codigo) }), el("span", { className: "mono", style: `color:${v >= 0 ? C.cian : C.naranja}`, textContent: `${v >= 0 ? "+" : ""}${cifra(v)}` })))
      : [el("p", { className: "vacio", textContent: "Sin datos de barrios para comparar todavía." })]));
  }
  sRasgo.addEventListener("change", recargar); sA.addEventListener("change", recargar); sB.addEventListener("change", recargar);
  rHora.addEventListener("input", pintar);
  bPlay.addEventListener("click", () => {
    if (reloj) { clearInterval(reloj); reloj = 0; bPlay.textContent = "▶ Día entero"; return; }
    bPlay.textContent = "■ Parar";
    reloj = setInterval(() => { if (fichaAbierta !== "comparar") { clearInterval(reloj); reloj = 0; return; } rHora.value = (Number(rHora.value) + 1) % 48; pintar(); }, 450);
  });
  await cargarFechas();
  recargar();
}

/* ---------- Movilidad ---------- */
async function abrirMovilidad() {
  const cont = abrirFicha({ tipo: "Movilidad", color: C.violeta, titulo: "Hacia dónde se mueve la gente", clave: "movilidad", estrecha: true,
    sub: "Bicis de Valenbisi que llegan a cada barrio menos las que salen: dónde se concentra la gente y de dónde se va" });
  const sHoras = el("select", {}, ...[[1, "Última hora"], [3, "3 horas"], [6, "6 horas"], [12, "12 horas"], [24, "24 horas"]].map(([v, t]) => el("option", { value: v, textContent: t })));
  sHoras.value = String(ajustes.movilidadHoras || 1);
  cont.append(el("div", { className: "controles" }, el("label", {}, "Rato", sHoras)));
  const balance = el("div"), curvas = el("div");
  cont.append(seccion("Balance por barrio", balance), curvas);
  async function cargarMov() {
    ajustes.movilidadHoras = Number(sHoras.value); recordar();
    let barrios = {}, d = null;
    if (servidor) {
      try { d = await pedirJSON(`vivo/sala/movilidad?horas=${sHoras.value}`); barrios = d.barrios || {}; } catch (err) { balance.replaceChildren(el("p", { className: "vacio", textContent: err.message })); return; }
    } else {
      for (const [c, b] of Object.entries(E?.barrios || {})) {
        if (b.valores?.bici_llegadas == null) continue;
        barrios[c] = { llegan: b.valores.bici_llegadas, salen: b.valores.bici_salidas, neto: b.valores.bici_llegadas - b.valores.bici_salidas };
      }
      balance.append(avisoWeb("En la web solo están los últimos diez minutos publicados; en el ordenador se ve el rato que se elija y la curva del día."));
    }
    if (fichaAbierta !== "movilidad") return;
    const netos = Object.fromEntries(Object.entries(barrios).filter(([c]) => c !== "VLC").map(([c, v]) => [c, v.neto]));
    const absolutos = Object.values(netos).map(Math.abs).sort((x, y) => x - y);
    modo = { tipo: "movilidad", valores: netos, escala: absolutos[Math.floor(absolutos.length * 0.9)] || absolutos[absolutos.length - 1] || 1,
      pos: C.cian, neg: C.violeta, etiqueta: "Balance de bicis", unidad: "bicis", titulo: "Bicis que llegan menos las que salen", izquierda: "salen más", derecha: "llegan más" };
    pintarBarrios(); pintarLeyenda();
    const orden = Object.entries(barrios).filter(([c]) => c !== "VLC").sort((x, y) => y[1].neto - x[1].neto);
    const fila = ([c, v]) => el("div", { className: "fila", onclick: () => abrirBarrio(c) }, el("span", { className: "t", textContent: nombreBarrio(c) }),
      el("span", { className: "mono", style: `color:${v.neto >= 0 ? C.cian : C.violeta}`, textContent: `${v.neto >= 0 ? "+" : ""}${cifra(v.neto)}` }),
      el("span", { className: "s", textContent: `llegan ${cifra(v.llegan)} · salen ${cifra(v.salen)}` }));
    balance.replaceChildren(...balance.querySelectorAll(".aviso-web"),
      el("h4", { textContent: "Donde más llegan", style: "margin-top:4px" }), ...orden.slice(0, 6).map(fila),
      el("h4", { textContent: "De donde más salen", style: "margin-top:12px" }), ...orden.slice(-6).reverse().map(fila));
    curvas.replaceChildren();
    if (d?.hoy) {
      for (const [r, nombre] of [["bici_llegadas", "Bicis que llegan (toda la ciudad, cada 10 min)"], ["trafico", "Tráfico (0 a 100)"], ["metro", "Salidas de metro en 30 min"]]) {
        const c = lienzo();
        curvas.append(seccion(`Hoy frente a lo normal: ${nombre}`, c));
        const hoy = (d.hoy[r] || []).map((v, i) => [i, v]), normal = (d.normal[r] || []).map((v, i) => [i, v]);
        requestAnimationFrame(() => grafica(c, [{ nombre: "lo normal", color: C.suave, discontinua: true, puntos: normal }, { nombre: "hoy", color: C.cian, puntos: hoy }],
          { x0: 0, x1: 47, cursor: d.franja, marcas: marcasDeFranjas, leyenda: true }));
      }
    }
  }
  sHoras.addEventListener("change", cargarMov);
  cargarMov();
  const flujos = el("div");
  cont.append(flujos);
  pintarFlujos(flujos);
}

/* ---------- Viajes entre distritos (MITMA): un día tipo, hora a hora ---------- */
let mitmaWeb = null;
async function datosFlujos(dia) {
  if (servidor) return pedirJSON(`vivo/sala/flujos${dia ? `?dia=${encodeURIComponent(dia)}` : ""}`);
  mitmaWeb ||= await pedirJSON(`${BASE}sala-movilidad.json`);
  const elegido = dia || mitmaWeb.dias[0].dia;
  return { ...mitmaWeb, dia: elegido, horas: mitmaWeb.horas[elegido] };
}
async function pintarFlujos(caja) {
  let d;
  try { d = await datosFlujos(); } catch (err) {
    caja.replaceChildren(seccion("Viajes entre distritos (MITMA)", el("p", { className: "vacio", textContent: servidor ? err.message : "Aún no se han publicado." })));
    return;
  }
  if (fichaAbierta !== "movilidad") return;
  const TIPOS = { L: "laborable", S: "sábado", D: "domingo" };
  const sDia = el("select", {}, ...d.dias.map((x) => el("option", { value: x.dia, textContent: `${x.nombre} (${TIPOS[x.tipo] || x.tipo})` })));
  const rHora = el("input", { type: "range", min: 0, max: 23, step: 1, value: new Date().getHours() });
  const etHora = el("span", { className: "mono" });
  const bPlay = el("button", { type: "button", className: "boton-fino", textContent: "▶ Día entero" });
  const c = lienzo(), resumen = el("p", { className: "pie" }), tabla = el("div");
  caja.replaceChildren(seccion("Viajes entre distritos · un día tipo",
    el("div", { className: "controles" }, el("label", {}, "Día", sDia), el("label", { style: "flex:1" }, el("span", {}, "Hora ", etHora), rHora), bPlay),
    c, resumen, tabla,
    el("p", { className: "pie", textContent: "Ministerio de Transportes (MITMA): viajes estimados con datos de teléfonos móviles, agregados y anónimos por el Ministerio. Cuántos viajes hay de un distrito a otro; nunca de quién." })));
  const COLORES = [C.cian, C.naranja, C.violeta];
  const dibujar = () => {
    if (fichaAbierta !== "movilidad") return;
    const h = Number(rHora.value);
    etHora.textContent = `${dos(h)}:00`;
    grafica(c, d.dias.map((x, k) => ({ nombre: TIPOS[x.tipo] || x.nombre, color: COLORES[k % 3], grosor: x.dia === d.dia ? 2.4 : 1.2, puntos: x.por_hora.map((v, i) => [i, v]) })),
      { x0: 0, x1: 23, cursor: h, marcas: () => [0, 4, 8, 12, 16, 20].map((x) => [x, `${dos(x)}h`]), leyenda: true });
    capas.foco.clearLayers();
    const horas = d.horas[h] || [];
    const lineas = horas.filter(([o, de]) => o !== de && d.zonas[o]?.lat != null && d.zonas[de]?.lat != null).slice(0, 45);
    const max = Math.max(1, ...lineas.map((x) => x[2]));
    for (const [o, de, v] of lineas) {
      const a = d.zonas[o], b = d.zonas[de], f = v / max;
      // Un poco curvadas, siempre hacia el mismo lado: la ida y la vuelta no se pisan.
      const medio = [(a.lat + b.lat) / 2 + (b.lon - a.lon) * 0.16, (a.lon + b.lon) / 2 - (b.lat - a.lat) * 0.16];
      L.polyline([[a.lat, a.lon], medio, [b.lat, b.lon]], { color: C.cian, weight: 1 + 7 * f, opacity: 0.2 + 0.65 * f, interactive: false }).addTo(capas.foco);
    }
    const llegan = {}, salen = {};
    let total = 0, dentro = 0;
    for (const [o, de, v] of horas) {
      total += v;
      if (o !== "fuera" && de !== "fuera") dentro += v;
      if (o !== de) { llegan[de] = (llegan[de] || 0) + v; salen[o] = (salen[o] || 0) + v; }
    }
    for (const [z, v] of Object.entries(llegan)) {
      const zona = d.zonas[z];
      if (zona?.lat == null) continue;
      L.circleMarker([zona.lat, zona.lon], { radius: 4 + 14 * Math.sqrt(v / Math.max(...Object.values(llegan))), color: C.cian, weight: 1.5, fillColor: C.cian, fillOpacity: 0.15, interactive: false }).addTo(capas.foco);
    }
    resumen.textContent = `${dos(h)}:00 del ${d.dias.find((x) => x.dia === d.dia)?.nombre || d.dia}: ${cifra(total)} viajes con origen o destino en València, ${cifra(dentro)} dentro de la ciudad. Las líneas, los 45 trayectos más usados entre distritos; los círculos, lo que llega a cada uno.`;
    const balance = Object.keys(d.zonas).filter((z) => z !== "fuera").map((z) => [z, (llegan[z] || 0) - (salen[z] || 0), llegan[z] || 0, salen[z] || 0]).sort((x, y) => y[1] - x[1]);
    const fila = ([z, neto, ll, sa]) => el("div", { className: "fila", style: "cursor:default" }, el("span", { className: "t", textContent: d.zonas[z]?.nombre || z }),
      el("span", { className: "mono", style: `color:${neto >= 0 ? C.cian : C.violeta}`, textContent: `${neto >= 0 ? "+" : ""}${cifra(neto)}` }),
      el("span", { className: "s", textContent: `llegan ${cifra(ll)} · salen ${cifra(sa)}` }));
    tabla.replaceChildren(el("h4", { textContent: "Atraen gente a esa hora", style: "margin-top:6px" }), ...balance.slice(0, 4).map(fila),
      el("h4", { textContent: "Se vacían a esa hora", style: "margin-top:10px" }), ...balance.slice(-4).reverse().map(fila));
  };
  sDia.addEventListener("change", async () => { try { d = await datosFlujos(sDia.value); dibujar(); } catch (err) { resumen.textContent = err.message; } });
  rHora.addEventListener("input", dibujar);
  let reloj = 0;
  bPlay.addEventListener("click", () => {
    if (reloj) { clearInterval(reloj); reloj = 0; bPlay.textContent = "▶ Día entero"; return; }
    bPlay.textContent = "■ Parar";
    reloj = setInterval(() => { if (fichaAbierta !== "movilidad") { clearInterval(reloj); reloj = 0; return; } rHora.value = (Number(rHora.value) + 1) % 24; dibujar(); }, 700);
  });
  dibujar();
}

/* ---------- Fuentes ---------- */
function abrirFuentes() {
  const cont = abrirFicha({ tipo: "Fuentes", titulo: "De dónde salen los datos", clave: "fuentes", sub: "Cada fuente, cuándo contestó por última vez y de quién son los datos" });
  const ahora = ahoraSeg();
  const t = el("table", { className: "datos" }, el("tr", {}, ...["", "Fuente", "Última", "Origen"].map((x) => el("th", { textContent: x }))));
  for (const f of E?.fuentes || []) {
    const bien = f.ok && f.ultima && ahora - f.ultima < Math.max(3 * (f.cada || 600), 1800);
    t.append(el("tr", { title: f.error || "" },
      el("td", { style: `color:${bien ? C.lima : f.ultima ? C.ambar : C.rojo}`, textContent: "●" }), el("td", { textContent: f.nombre || f.id }),
      el("td", { className: "num", textContent: f.ultima ? hace(ahora - f.ultima) : "nunca" }), el("td", { className: "pie", textContent: f.origen || "" })));
  }
  cont.append(seccion("Fuentes", t), el("p", { className: "pie", textContent: "Todo son datos públicos y de conjunto. De las redes se guarda el texto público, la fecha y el enlace de cada publicación, nunca quién la escribió, y nada se junta por persona." }));
}

/* ====================== Pestañas (móvil) y herramientas ====================== */
function ponerVista(v) {
  $("rejilla").dataset.vista = v;
  for (const b of document.querySelectorAll("#pestanas button")) b.setAttribute("aria-pressed", String(b.dataset.vista === v));
  if (v === "mapa") setTimeout(() => mapa.invalidateSize(), 50);
}
for (const b of document.querySelectorAll("#pestanas button")) b.addEventListener("click", () => ponerVista(b.dataset.vista));
$("b-comparar").addEventListener("click", abrirComparar);
$("b-movilidad").addEventListener("click", abrirMovilidad);
$("b-tiempo").addEventListener("click", () => {
  const p = window.OSINT_PULSO;
  if (!p) return;
  const abierto = $("b-tiempo").getAttribute("aria-pressed") === "true";
  abierto ? p.cerrar() : p.abrir();
  $("b-tiempo").setAttribute("aria-pressed", String(!abierto));
  if (!abierto) ponerVista("mapa");
});
window.OSINT_SALA = { estado: () => E, abrirSuceso, abrirBarrio, abrirLugar, abrirComparar, abrirMovilidad, cerrarFicha, modo: () => modo, servidor: () => servidor };

/* ====================== Arranque ====================== */
pintarLeyenda();
pintarReloj();
hayServidor.then(async (si) => {
  servidor = si;
  document.documentElement.classList.toggle("sin-servidor", !si);
  await cargar();
  if (servidor && ajustes.capas.helis) pedirCielo();
  // Lo que pide la dirección: #suceso=..., #barrio=..., #lugar=lat,lon, #comparar, #movilidad
  const [clave, valor] = decodeURIComponent(location.hash.slice(1)).split("=");
  if (clave === "suceso" && valor) abrirSuceso(valor);
  else if (clave === "barrio" && valor) abrirBarrio(valor);
  else if (clave === "lugar" && valor) { const [la, lo] = valor.split(",").map(Number); if (Number.isFinite(la) && Number.isFinite(lo)) abrirLugar(la, lo); }
  else if (clave === "comparar") abrirComparar();
  else if (clave === "movilidad") abrirMovilidad();
});
document.addEventListener("visibilitychange", () => { if (!document.hidden && E && ahoraSeg() - E.generado > (servidor ? 45 : 600)) cargar(); });
})();
