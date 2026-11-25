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
const MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
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

/* ====================== Colores, dibujos y nombres ====================== */
// Cada color dice una cosa: verde, ámbar, rojo y blanco a rayas, el tráfico; azul a cian, la gente; magenta, lo que
// se sale de lo normal; cian, la interfaz.
const C = { cian: "#22d3ee", magenta: "#ff2d95", ambar: "#fbbf24", lima: "#4ade80", rojo: "#f43f5e", violeta: "#a78bfa", naranja: "#fb923c",
  azul: "#60a5fa", gris: "#64748b", blanco: "#e2e8f0", texto: "#dbe7ee", suave: "#91a8b5", tenue: "#5a7482" };
const COLOR_FAMILIA = { afluencia: C.cian, salida: C.violeta, congestion: C.ambar, corte: C.naranja, servicio: C.rojo, atencion: C.magenta, alerta: C.rojo, ambiente: C.lima };
const COLOR_TIPO = { concentracion: C.magenta, salida: C.magenta, incidente: C.rojo, congestion: C.magenta, corte: C.magenta, servicio: C.magenta, conversacion: C.magenta, ciudad: C.magenta };
const COLOR_CATEGORIA = { emergencia: C.rojo, accidente: C.naranja, seguridad: "#fb7185", protesta: "#c084fc", trafico: C.ambar, transporte: C.cian,
  meteo: C.azul, evento: C.violeta, deporte: "#86efac", vivienda: "#f472b6", urbanismo: "#94a3b8", sanidad: "#34d399", medioambiente: "#86efac",
  politica: "#cbd5e1", cultura: "#c4b5fd", economia: "#fde68a" };
const COLOR_TRAFICO = [C.lima, C.ambar, C.rojo, C.blanco];
const NOMBRE_TRAFICO = ["fluido", "denso", "atasco", "cortado"];
const NOMBRE_FAMILIA = { afluencia: "llega gente", salida: "se va gente", congestion: "más tráfico", corte: "cortes", servicio: "metro", atencion: "se habla",
  alerta: "alerta", ambiente: "aire" };
const NOMBRE_FUENTE = { prensa: "Prensa", bluesky: "Bluesky", mastodon: "Mastodon", dgt: "DGT", renfe: "Renfe", meteoalarm: "AEMET" };
const NOMBRE_CATEGORIA = { emergencia: "emergencia", accidente: "accidente", seguridad: "seguridad", protesta: "protesta", trafico: "tráfico", transporte: "transporte",
  meteo: "tiempo", evento: "evento", deporte: "deporte", vivienda: "vivienda", urbanismo: "urbanismo", sanidad: "sanidad", medioambiente: "medio ambiente",
  politica: "política", cultura: "cultura", economia: "economía" };
const CLASE_NIVEL = { normal: [C.lima, "Normal", 1], atencion: [C.ambar, "Atención", 2], alta: [C.naranja, "Alta", 3], "muy alta": [C.rojo, "Muy alta", 4] };
const GRAVEDAD = ["sin heridos", "heridos leves", "heridos de baja gravedad", "heridos graves", "fallecidos"];
const TEJAS = [["trafico_indice", "Tráfico"], ["trafico_cortado", "Tramos cortados"], ["bicis_fuera", "Valenbisi en uso"], ["parking_ocupacion", "Aparcamientos"],
  ["metro_salidas", "Metro: salidas en 30 min"], ["metro_sin_servicio", "Estaciones sin metro"], ["trenes_retraso", "Retraso en Cercanías"], ["trenes_retrasados", "Trenes con retraso"],
  ["aforo", "Vehículos por hora"], ["aforo_bici", "Bicis por hora"], ["aire_no2", "NO₂"], ["aire_pm25", "PM2,5"], ["helicopteros", "Helicópteros"], ["aviones_bajos", "Aviones bajos"],
  ["meteo_temperatura", "Temperatura"], ["meteo_lluvia", "Lluvia"], ["ora_ocupacion", "Zona azul (previsión)"], ["ruido_noche", "Ruido en Russafa (anoche)"]];
// Las cifras que se ven de un vistazo; el resto, al pulsar «Ver todas las cifras».
const TEJAS_PRINCIPALES = [["bicis_fuera", "Valenbisi en uso"], ["parking_ocupacion", "Aparcamientos"], ["metro_sin_servicio", "Sin metro"],
  ["trenes_retraso", "Retraso en Cercanías"], ["aire_no2", "Aire (NO₂)"], ["meteo_temperatura", "Temperatura"]];
const RASGOS_WEB = ["aforo", "trafico", "bici_llegadas", "bici_salidas", "bici_ocupacion", "parking", "metro", "social"];
const REDES = ["bluesky", "mastodon"];
const BASE = new URLSearchParams(location.search).get("datos") || "datos/";
const GEOPORTAL = "https://geoportal.valencia.es/server/rest/services/OPENDATA";

// Los dibujos de las marcas, de 24×24 con trazo: los mismos en el mapa, en las listas y en la leyenda.
const ICONOS = {
  noticia: '<rect x="4" y="5" width="16" height="14" rx="1.5"/><path d="M8 9h8M8 12.5h8M8 16h5"/>',
  redes: '<path d="M5 5.5h14v10h-8.5L6 19v-3.5H5z"/>',
  emergencia: '<path d="M12 3c.6 3.2 4.8 5 4.8 9.6a4.8 4.8 0 0 1-9.6 0c0-2.4 1.3-4 2.4-5 .2 1.5 1 2.5 2.1 2.8-.3-2.6-.1-5 .3-7.4z"/>',
  accidente: '<path d="M5 17l1.5-4.3a2 2 0 0 1 1.9-1.4h7.2a2 2 0 0 1 1.9 1.4L19 17v2.5H5z"/><path d="M8.5 17h.01M15.5 17h.01M12 4v3.3M8.2 5.6l1.3 2M15.8 5.6l-1.3 2"/>',
  seguridad: '<path d="M12 3l7 3v5.5c0 4.3-2.9 7.7-7 9.5-4.1-1.8-7-5.2-7-9.5V6z"/>',
  protesta: '<path d="M4 10v4h3l8 4.5v-13L7 10z"/><path d="M18.2 9.5a3.5 3.5 0 0 1 0 5"/>',
  trafico: '<path d="M10.2 4h3.6l4.4 14.5H5.8z"/><path d="M8.7 9.5h6.6M7.4 14h9.2M4 18.5h16"/>',
  transporte: '<rect x="6" y="3.5" width="12" height="13" rx="2.5"/><path d="M6 10h12M9 16.5 7 20M15 16.5l2 3.5M9 13.3h.01M15 13.3h.01"/>',
  meteo: '<path d="M7 18h10a4 4 0 0 0 .4-8 5.5 5.5 0 0 0-10.6 1.4A3.3 3.3 0 0 0 7 18z"/>',
  evento: '<path d="M4 8.5V6h16v2.5a2 2 0 0 0 0 4V15H4v-2.5a2 2 0 0 0 0-4z"/><path d="M14 6v9"/>',
  cultura: '<path d="M9 17V6l10-2v11"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="15" r="2"/>',
  deporte: '<circle cx="12" cy="12" r="8"/><path d="m12 8 3.3 2.4-1.3 3.9h-4l-1.3-3.9zM12 4v4M15.3 10.4l3.9-1.3M14 14.3l2.3 3.3M10 14.3l-2.3 3.3M8.7 10.4 4.8 9.1"/>',
  politica: '<path d="M4 9.5 12 5l8 4.5M6 10.5V17M10 10.5V17M14 10.5V17M18 10.5V17M4 19h16"/>',
  sanidad: '<path d="M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z"/>',
  vivienda: '<path d="M4 11.5 12 5l8 6.5M6.5 10v9h11v-9M10.5 19v-5h3v5"/>',
  urbanismo: '<path d="M4 20V9h6v11M10 20V4h9v16M3 20h18M13 8h3M13 11.5h3M13 15h3"/>',
  medioambiente: '<path d="M5 19c0-8.5 5.5-13.5 14-14-.5 9-6 14-14 14zM5 19l7.5-7.5"/>',
  economia: '<circle cx="12" cy="12" r="8"/><path d="M15 9.2a3.6 3.6 0 1 0 0 5.6M7.5 11h6M7.5 13.2h6"/>',
  aviso: '<path d="M12 6.5v6.5M12 17.2h.01"/>',
  carril: '<path d="M6.5 12h11"/>',
  obra: '<path d="M10.2 5h3.6l3.6 12H6.6z"/><path d="M8.9 10h6.2M5 17.5h14"/>',
  estrella: '<path d="M12 4.5l2.3 4.8 5.2.6-3.9 3.6 1.1 5.2L12 16.1l-4.7 2.6 1.1-5.2-3.9-3.6 5.2-.6z"/>',
  gente: '<circle cx="9" cy="8.5" r="2.6"/><circle cx="16.5" cy="9.5" r="2"/><path d="M4 19c0-3 2.2-5.2 5-5.2s5 2.2 5 5.2M14.5 14.3c2.6-.4 4.8 1.5 4.8 4.4"/>',
  salida: '<circle cx="8.5" cy="8.5" r="2.6"/><path d="M3.5 19c0-3 2.2-5.2 5-5.2 1.6 0 3 .7 3.9 1.8M14 11h6.5M17.5 8l3 3-3 3"/>',
  incidente: '<path d="M12 4l9 15.5H3z"/><path d="M12 10v4.3M12 17h.01"/>',
  coche: '<path d="M5 15.5l1.6-4.6a2 2 0 0 1 1.9-1.4h7a2 2 0 0 1 1.9 1.4l1.6 4.6v3H5z"/><path d="M8.5 15.5h.01M15.5 15.5h.01"/>',
  corte: '<path d="M3.5 9h17v5h-17zM7 14v5M17 14v5M8 9l-3 5M13.5 9l-3 5M19 9l-3 5"/>',
  ciudad: '<path d="M3 20h18M5 20V10h4v10M9 20V5h6v15M15 20v-8h4v8"/>',
};
const dibujo = (nombre, tam = 14) => `<svg viewBox="0 0 24 24" width="${tam}" height="${tam}" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONOS[nombre] || ICONOS.noticia}</svg>`;
const icono = (nombre, color, grande = false) => { const s = el("span", { className: `ico${grande ? " grande" : ""}`, innerHTML: dibujo(nombre, grande ? 17 : 14) }); s.style.setProperty("--c", color); return s; };
const DIBUJO_TIPO = { concentracion: "gente", salida: "salida", incidente: "incidente", congestion: "coche", corte: "corte", servicio: "transporte", conversacion: "redes", ciudad: "ciudad" };
const dibujoDeTexto = (it) => (it.fuente === "renfe" ? "transporte" : it.fuente === "meteoalarm" ? "meteo" : it.fuente === "dgt" ? dibujoDeAviso(it)
  : ICONOS[it.categoria] ? it.categoria : REDES.includes(it.fuente) ? "redes" : "noticia");
function dibujoDeAviso(a) {
  const t = a.tipo || "";
  if (a.fuente === "renfe") return "transporte";
  if (a.fuente === "meteoalarm") return "meteo";
  if (/Roadworks|Maintenance|Construction/i.test(t)) return "obra";
  if (/Accident|Vehicle/i.test(t)) return "accidente";
  if (/Lane|Carriageway/i.test(t)) return "carril";
  if (/Weather|Environment|Wind|Fog|Snow|Ice/i.test(t)) return "meteo";
  return "aviso";
}
const colorDeTexto = (it) => (it.fuente === "dgt" ? C.ambar : COLOR_CATEGORIA[it.categoria] || (REDES.includes(it.fuente) ? C.violeta : C.suave));

/* ====================== Estado ====================== */
let E = null;                 // lo último de la sala (estado)
let servidor = false;
let geo = null;               // los barrios (GeoJSON)
const props = {};             // código -> propiedades del barrio
let modo = { tipo: "nivel" }; // cómo se pintan los barrios: nivel, comparar o movilidad
let fichaAbierta = null;
let investigando = false;
let ultimoError = null;
let tramos = null;            // el trazado de cada tramo de calle: [[id, nombre, [[lat, lon], ...]], ...]
let estadosTrafico = {};      // id del tramo -> 0 fluido, 1 denso, 2 atasco, 3 cortado (null: sin datos)
let traficoDe = { origen: null, t: 0 };     // de dónde y de cuándo es el estado del tráfico
const POR_DEFECTO = { trafico: true, calor: true, sucesos: true, textos: true, agenda: true, avisos: true, barrios: false, riesgo: false, obras: false, helis: true, nombres: false };
const guardado = leerLocal("osintmaps.sala.v2", {});
const ajustes = { feed: guardado.feed || "todo", plegado: !!guardado.plegado, capas: Object.assign({}, POR_DEFECTO, guardado.capas || {}) };
const recordar = () => guardarLocal("osintmaps.sala.v2", ajustes);
const nombreBarrio = (c) => (c === "VLC" ? "Toda la ciudad" : props[c]?.nombre || c || "");

/* ====================== El mapa ====================== */
const mapa = L.map("mapa", { zoomControl: true, minZoom: 10, maxZoom: 19, zoomSnap: 0.5 }).setView([39.4699, -0.3763], movil() ? 12.5 : 13);
window.mapa = mapa;
// De abajo arriba: el fondo, el calor de gente, los barrios y las calles (en un mismo lienzo, para que se puedan
// pulsar los dos), los rótulos del fondo, lo resaltado y las marcas.
for (const [nombre, z, sinRaton] of [["calor", 380, true], ["vectores", 400, false], ["rotulos", 450, true], ["foco", 455, true], ["sucesos", 640, false]]) {
  const p = mapa.createPane(nombre); p.style.zIndex = z; if (sinRaton) p.style.pointerEvents = "none";
}
const vectores = L.canvas({ pane: "vectores", tolerance: 6, padding: 0.4 });
const ESRI = (parte) => `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_${parte}/MapServer/tile/{z}/{y}/{x}`;
L.tileLayer(ESRI("Base"), { maxZoom: 19, maxNativeZoom: 16, attribution: "Esri, HERE, Garmin, OpenStreetMap" }).addTo(mapa);
L.tileLayer(ESRI("Reference"), { maxZoom: 19, maxNativeZoom: 16, pane: "rotulos" }).addTo(mapa);
mapa.attributionControl.addAttribution("Datos: Ajuntament de València, FGV, Renfe, DGT, AEMET, prensa local, adsb.fi");

/* ---------- El calor de gente: un lienzo propio (como simpleheat: sellos que se suman y luego se colorean) ---------- */
const CapaCalor = L.Layer.extend({
  options: { pane: "calor", metros: 260, minimo: 13, maximo: 64, ganancia: 0.6 },
  initialize(puntos, op) { L.setOptions(this, op); this._puntos = puntos || []; },
  ponerPuntos(puntos) { this._puntos = puntos || []; if (this._map) this._pintar(); return this; },
  onAdd(m) {
    this._lienzo = L.DomUtil.create("canvas", "capa-calor leaflet-zoom-hide");
    this.getPane().appendChild(this._lienzo);
    m.on("moveend zoomend resize", this._pintar, this);
    this._pintar();
  },
  onRemove(m) { m.off("moveend zoomend resize", this._pintar, this); this._lienzo.remove(); this._lienzo = null; },
  _sello(r) {
    if (this._r === r) return this._s;
    const s = document.createElement("canvas"); s.width = s.height = 2 * r;
    const g = s.getContext("2d"), grad = g.createRadialGradient(r, r, 0, r, r, r);
    grad.addColorStop(0, "rgba(0,0,0,1)"); grad.addColorStop(0.45, "rgba(0,0,0,.55)"); grad.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grad; g.fillRect(0, 0, 2 * r, 2 * r);
    this._r = r; this._s = s;
    return s;
  },
  _paleta() {
    if (this._p) return this._p;
    const c = document.createElement("canvas"); c.width = 256; c.height = 1;
    const g = c.getContext("2d"), grad = g.createLinearGradient(0, 0, 256, 0);
    for (const [k, color] of this.options.colores || [[0, "#0b1d4d"], [0.22, "#2563eb"], [0.45, "#7c3aed"], [0.7, "#22d3ee"], [1, "#ecfeff"]]) grad.addColorStop(k, color);
    g.fillStyle = grad; g.fillRect(0, 0, 256, 1);
    return (this._p = g.getImageData(0, 0, 256, 1).data);
  },
  _pintar() {
    const m = this._map, c = this._lienzo;
    if (!m || !c) return;
    const tam = m.getSize(), dpr = Math.min(2, window.devicePixelRatio || 1);
    L.DomUtil.setPosition(c, m.containerPointToLayerPoint([0, 0]));
    c.width = Math.round(tam.x * dpr); c.height = Math.round(tam.y * dpr);
    c.style.width = `${tam.x}px`; c.style.height = `${tam.y}px`;
    const g = c.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, tam.x, tam.y);
    if (!this._puntos.length) return;
    const lat = m.getCenter().lat;
    const metrosPorPixel = 40075016.686 * Math.cos(lat * Math.PI / 180) / (256 * 2 ** m.getZoom());
    const r = Math.round(Math.max(this.options.minimo, Math.min(this.options.maximo, this.options.metros / metrosPorPixel)));
    const sello = this._sello(r);
    for (const [la, lo, w] of this._puntos) {
      const p = m.latLngToContainerPoint([la, lo]);
      if (p.x < -r || p.y < -r || p.x > tam.x + r || p.y > tam.y + r) continue;
      g.globalAlpha = Math.max(0.04, Math.min(0.92, w * this.options.ganancia));
      g.drawImage(sello, p.x - r, p.y - r);
    }
    g.globalAlpha = 1;
    const img = g.getImageData(0, 0, c.width, c.height), d = img.data, pal = this._paleta();
    for (let i = 3; i < d.length; i += 4) {
      const a = d[i];
      if (!a) continue;
      const j = a * 4;
      d[i - 3] = pal[j]; d[i - 2] = pal[j + 1]; d[i - 1] = pal[j + 2]; d[i] = Math.min(235, a * 1.15);
    }
    g.putImageData(img, 0, 0);
  },
});

const capas = {
  trafico: L.layerGroup(), calor: new CapaCalor([]), sucesos: L.layerGroup(), textos: L.layerGroup(), avisos: L.layerGroup(), agenda: L.layerGroup(),
  obras: L.layerGroup(), helis: L.layerGroup(), nombres: L.layerGroup(), foco: L.layerGroup().addTo(mapa), barrios: null,
  riesgo: new CapaCalor([], { metros: 150, minimo: 9, maximo: 46, ganancia: 0.75, colores: [[0, "#3b1206"], [0.3, "#b45309"], [0.6, "#fb923c"], [1, "#fff7ed"]] }),
};
const enHistorico = () => !!document.getElementById("pulso") && !document.getElementById("pulso").hidden;
function ponerCapa(id, si) {
  ajustes.capas[id] = si; recordar();
  const capa = id === "barrios" ? null : capas[id];
  const ver = si && !((id === "trafico" || id === "calor") && enHistorico());
  if (capa) ver ? capa.addTo(mapa) : mapa.removeLayer(capa);
  if (id === "barrios") pintarBarrios();
  if (id === "nombres") pintarNombres();
  if (id === "helis" && si) pedirCielo();
  if (id === "trafico" && si) pintarTrafico();
  if (id === "riesgo" && si) pedirRiesgo().catch(() => {});
  pintarLeyenda();
}

/* ---------- El panel de capas, con la leyenda de cada una dentro ---------- */
const ley = (...hijos) => el("span", { className: "ley" }, ...hijos);
const linea = (color, texto, rayas = false) => { const i = el("i", { className: `linea${rayas ? " rayas" : ""}` }); i.style.setProperty("--c", color); return el("span", {}, i, texto); };
const mini = (nombre, color, texto, carretera = false) => { const s = el("i", { className: `mini${carretera ? " carretera" : ""}`, innerHTML: dibujo(nombre, 10) }); s.style.setProperty("--c", color); return el("span", {}, s, texto || ""); };
const DEF_CAPAS = [
  { id: "trafico", nombre: "Tráfico", ley: () => ley(linea(C.lima, "fluido"), linea(C.ambar, "denso"), linea(C.rojo, "atasco"), linea(C.blanco, "cortado", true)) },
  { id: "calor", nombre: "Gente", ley: () => ley(el("span", {}, "poca", el("i", { className: "rampa" }), "mucha"), el("span", { textContent: "bicis y aparcamientos, última hora" })),
    titulo: "Dónde se mueve más gente en la última hora: bicis de Valenbisi que salen y llegan, bicis por el carril bici y coches en los aparcamientos públicos. No hay contadores de personas en la calle." },
  { id: "sucesos", nombre: "Sucesos", ley: () => ley(mini("gente", C.magenta, "fuera de lo normal"), mini("incidente", C.rojo, "incidente")),
    titulo: "Lo que se sale de lo normal para la hora en varias fuentes a la vez (el cruce de datos)" },
  { id: "textos", nombre: "Noticias", ley: () => ley(mini("emergencia", C.rojo), mini("seguridad", "#fb7185"), mini("deporte", "#86efac"), mini("politica", "#cbd5e1"), el("span", { textContent: "últimas 6 h" })),
    titulo: "Noticias y publicaciones que dicen dónde pasa algo, de las últimas seis horas" },
  { id: "agenda", nombre: "Hoy", ley: () => ley(mini("deporte", C.ambar, "partidos"), mini("estrella", C.ambar, "fiestas")) },
  { id: "avisos", nombre: "Carreteras y trenes", ley: () => ley(mini("carril", C.ambar, "carril cortado", true), mini("aviso", C.ambar, "incidencia", true), mini("transporte", C.cian, "Renfe")) },
  { id: "barrios", nombre: "Barrios fuera de lo normal", ley: () => ley(el("span", {}, el("i", { className: "cuadro" }), "más intenso, más raro")),
    titulo: "Cada barrio frente a lo normal para esa hora y ese día: cuanto más intenso, más lejos de lo normal" },
  { id: "riesgo", nombre: "Accidentes a esta hora", ley: () => ley(el("span", {}, "pocos", el("i", { className: "rampa naranja" }), "muchos")),
    titulo: "Dónde ha habido más accidentes de tráfico a esta hora en días como hoy (datos del Ajuntament). Por lugar, no por persona." },
  { id: "obras", nombre: "Obras y cortes previstos" },
  { id: "helis", nombre: "Helicópteros", soloServidor: true },
  { id: "nombres", nombre: "Nombres de barrio" },
];
const panelCapas = $("capas");
function montarCapas() {
  const plegar = el("button", { type: "button", textContent: movil() ? "Cerrar" : ajustes.plegado ? "Mostrar" : "Ocultar", title: "Mostrar u ocultar la lista de capas" });
  plegar.addEventListener("click", () => {
    if (movil()) { cerrarCapas(); return; }
    ajustes.plegado = !ajustes.plegado; recordar();
    panelCapas.classList.toggle("plegado", ajustes.plegado); plegar.textContent = ajustes.plegado ? "Mostrar" : "Ocultar";
  });
  panelCapas.replaceChildren(el("div", { className: "cab" }, el("span", { textContent: "Capas" }), plegar));
  panelCapas.classList.toggle("plegado", ajustes.plegado && !movil());
  for (const d of DEF_CAPAS) {
    if (d.soloServidor && !servidor) continue;
    const b = el("button", { type: "button", className: "capa", role: "switch", title: d.titulo || "" }, el("span", { className: "interruptor" }), el("span", { className: "nombre", textContent: d.nombre }), d.ley ? d.ley() : null);
    b.setAttribute("aria-checked", String(!!ajustes.capas[d.id]));
    b.addEventListener("click", () => { const si = b.getAttribute("aria-checked") !== "true"; b.setAttribute("aria-checked", String(si)); ponerCapa(d.id, si); });
    panelCapas.append(b);
  }
}
function cerrarCapas() { $("mapa-zona").classList.remove("capas-abiertas"); $("b-capas").setAttribute("aria-expanded", "false"); }
$("b-capas").addEventListener("click", () => {
  const abierto = $("mapa-zona").classList.toggle("capas-abiertas");
  $("b-capas").setAttribute("aria-expanded", String(abierto));
});
L.DomEvent.disableClickPropagation(panelCapas); L.DomEvent.disableScrollPropagation(panelCapas);
for (const id of ["b-capas", "b-investigar", "tira-parte"]) L.DomEvent.disableClickPropagation($(id));
montarCapas();
const bInvestigar = $("b-investigar");
bInvestigar.addEventListener("click", () => { investigando = !investigando; bInvestigar.setAttribute("aria-pressed", String(investigando)); $("mapa-zona").classList.toggle("investigando", investigando); });
for (const id of ["trafico", "calor", "riesgo", "sucesos", "textos", "avisos", "agenda", "obras", "helis", "nombres"]) if (ajustes.capas[id]) capas[id].addTo(mapa);

mapa.on("click", (ev) => { if (investigando) abrirLugar(ev.latlng.lat, ev.latlng.lng); else if (movil()) cerrarCapas(); });
mapa.on("contextmenu", (ev) => abrirLugar(ev.latlng.lat, ev.latlng.lng));
mapa.on("zoomend", () => { pintarNombres(); if (ajustes.capas.trafico) pintarTrafico(); if (E) pintarCapas(); });

/* ---------- Barrios: un contorno tenue que se puede pulsar; relleno solo si están fuera de lo normal ---------- */
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
    return { color: "#1e4252", weight: 0.8, opacity: 0.8, dashArray: null, fillColor: color, fillOpacity: modo.valores?.[c] == null ? 0.04 : a };
  }
  const n = E?.barrios?.[c]?.nivel || 0;
  const raro = ajustes.capas.barrios && n >= 2.5;
  if (enSuceso.has(c)) return { color: C.magenta, weight: 1.6, opacity: 0.75, dashArray: "4 4", fillColor: C.magenta, fillOpacity: raro ? Math.min(0.42, 0.06 + (n - 2.5) * 0.06) : 0.06 };
  return { color: raro ? C.magenta : "#27485a", weight: raro ? 1 : 0.6, opacity: raro ? 0.7 : 0.45, dashArray: null,
    fillColor: C.magenta, fillOpacity: raro ? Math.min(0.42, 0.06 + (n - 2.5) * 0.06) : 0 };
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
  caja.append(el("div", { className: "tt-s", textContent: b.nivel >= 2.5 ? `Fuera de lo normal (${cifra(b.nivel)}): ${NOMBRE_FAMILIA[familiaDominante(b)] || ""}` : "Dentro de lo normal" }));
  if (s && b.nivel >= 2.5) caja.append(el("div", { className: "tt-s", textContent: `${E.rasgos?.[s.rasgo]?.nombre || s.rasgo}: ${cifra(s.valor)} (lo normal, ${cifra(s.normal)})` }));
  caja.append(el("div", { className: "tt-s", textContent: "Pulsa para ver la ficha del barrio" }));
  return caja;
}
function pintarBarrios() {
  if (!geo) return;
  enSuceso = barriosEnSuceso();
  if (!capas.barrios) {
    capas.barrios = L.geoJSON(geo, {
      renderer: vectores, style: estiloBarrio,
      onEachFeature: (f, capa) => {
        capa.on("click", (ev) => { L.DomEvent.stop(ev); investigando ? abrirLugar(ev.latlng.lat, ev.latlng.lng) : abrirBarrio(f.properties.codigo); });
        capa.on("contextmenu", (ev) => { L.DomEvent.stop(ev); abrirLugar(ev.latlng.lat, ev.latlng.lng); });
        capa.bindTooltip(() => tooltipBarrio(f.properties.codigo), { sticky: true, className: "sala", direction: "top", offset: [0, -10] });
      },
    }).addTo(mapa);
  } else capas.barrios.setStyle(estiloBarrio);
  capas.barrios.bringToBack();
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

/* ---------- Tráfico: cada tramo de calle, del color de su estado ---------- */
function grosor(estado) {
  const z = mapa.getZoom();
  const base = z >= 16 ? 5 : z >= 15 ? 4 : z >= 14 ? 3.2 : z >= 13 ? 2.6 : 2;
  return estado === 0 ? base * 0.7 : estado === 3 ? base * 0.9 : base + (estado === 2 ? 1.2 : 0.6);
}
function pintarTrafico() {
  capas.trafico.clearLayers();
  if (!tramos || !ajustes.capas.trafico) return;
  // Primero lo fluido y encima lo demás: un atasco no se queda debajo de una calle verde.
  for (const estado of [0, 1, 2, 3]) {
    for (const [id, nombre, trazo] of tramos) {
      if (estadosTrafico[id] !== estado) continue;
      L.polyline(trazo, { renderer: vectores, color: COLOR_TRAFICO[estado], weight: grosor(estado), opacity: estado === 0 ? 0.6 : 0.95,
        dashArray: estado === 3 ? "4 5" : null, lineCap: estado === 3 ? "butt" : "round" })
        .bindTooltip(() => el("div", {}, el("div", { className: "tt-n", textContent: nombre || "Tramo" }), el("div", { className: "tt-s", textContent: NOMBRE_TRAFICO[estado] })),
          { sticky: true, className: "sala", direction: "top", offset: [0, -8] })
        .addTo(capas.trafico);
    }
  }
}
// El estado de cada tramo lo da el geoportal del Ajuntament, que se puede pedir desde el navegador: así está al
// minuto también en la web. Si no contesta, vale lo último que guardó el programa.
let relojTrafico = 0;
async function pedirTraficoVivo() {
  clearTimeout(relojTrafico);
  relojTrafico = setTimeout(pedirTraficoVivo, 180000);
  if (document.hidden) return;
  try {
    const r = await fetch(`${GEOPORTAL}/Trafico/MapServer/192/query?where=1%3D1&outFields=idtramo,estado&returnGeometry=false&resultRecordCount=2000&f=json`);
    if (!r.ok) throw new Error(r.status);
    const j = await r.json();
    const estados = {};
    for (const f of j.features || []) {
      const a = f.attributes || {};
      let n = Number(a.estado);
      if (a.idtramo == null || a.estado == null || !Number.isFinite(n)) continue;
      if (n >= 5 && n <= 8) n -= 5;
      estados[String(a.idtramo)] = n >= 0 && n <= 3 ? n : null;
    }
    if (!Object.keys(estados).length) return;
    estadosTrafico = estados; traficoDe = { origen: "geoportal", t: ahoraSeg() };
    pintarTrafico(); if (E) pintarTejas();
  } catch { /* se queda con lo del programa */ }
}
function traficoDelPrograma() {
  const t = E?.trafico;
  if (!t?.estados || !Object.keys(t.estados).length) return;
  if (traficoDe.origen === "geoportal" && ahoraSeg() - traficoDe.t < 600) return;    // lo del geoportal es más fresco
  if (traficoDe.origen === "programa" && traficoDe.t === t.t) return;
  estadosTrafico = t.estados; traficoDe = { origen: "programa", t: t.t };
  pintarTrafico();
}

/* ---------- Marcas: sucesos, noticias, carreteras, lo de hoy, obras ---------- */
function insignia({ dibujo: d, color, tam = 24, llena = false, cuenta = 0, clase = "" }) {
  return L.divIcon({ className: `insignia ${clase}${llena ? " llena" : ""}`, iconSize: [tam, tam], iconAnchor: [tam / 2, tam / 2],
    html: `<span style="--c:${color}">${dibujo(d, Math.round(tam * 0.58))}</span>${cuenta > 1 ? `<b style="--c:${color}">${cuenta}</b>` : ""}` });
}
// Lo que cae en el mismo sitio (a unos cien metros) va en una sola marca con el número de cosas.
function agrupar(lista) {
  const grupos = new Map();
  for (const x of lista) {
    const k = `${x.lat.toFixed(3)},${x.lon.toFixed(3)}`;
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(x);
  }
  return [...grupos.values()];
}
function popupLista(lista, cita = false) {
  if (lista.length === 1) return cita ? popupCita(lista[0]) : popupTexto(lista[0]);
  return el("div", { className: "pop-lista" }, ...lista.slice(0, 8).map((x) => (cita ? popupCita(x) : popupTexto(x))),
    lista.length > 8 ? el("div", { className: "tt-s", textContent: `y ${lista.length - 8} más` }) : null);
}
function pintarCapas() {
  capas.sucesos.clearLayers();
  const tMirado = instante == null || !lineaT ? null : lineaT.desde + instante * lineaT.paso;
  const deAhora = tMirado == null ? (E?.sucesos || []).filter((s) => s.valoracion !== "falso")
    : (lineaT.sucesos || []).filter((s) => s.inicio <= tMirado && s.fin >= tMirado - lineaT.paso).map((s) => ({ ...s, estado: "activo" }));
  const ordenados = [...deAhora].filter((s) => s.lat != null).sort((a, b) => (a.estado === "activo") - (b.estado === "activo") || (a.puntuacion || 0) - (b.puntuacion || 0));
  const conRotulo = new Set(), ocupado = [];
  for (const s of [...ordenados].reverse()) {
    if (s.estado !== "activo" || conRotulo.size >= 3) continue;
    const p = mapa.latLngToContainerPoint([s.lat, s.lon]);
    if (ocupado.some((q) => Math.abs(q.y - p.y) < 34 && Math.abs(q.x - p.x) < 250)) continue;     // los rótulos van a la derecha, unos 230 px
    conRotulo.add(s.id); ocupado.push(p);
  }
  for (const s of ordenados) {
    const activo = s.estado === "activo";
    const d = Math.round(Math.max(28, Math.min(44, 22 + (s.puntuacion || 0) * 1.6)));
    const color = COLOR_TIPO[s.tipo] || C.magenta;
    const marca = L.marker([s.lat, s.lon], { pane: "sucesos", title: s.titulo || "", keyboard: false, zIndexOffset: activo ? 1000 : 0,
      icon: L.divIcon({ className: `marca-suceso ${activo ? "activo" : "cerrado"}`, iconSize: [d, d], iconAnchor: [d / 2, d / 2],
        html: `<span style="--c:${color}">${dibujo(DIBUJO_TIPO[s.tipo] || "gente", Math.round(d * 0.5))}</span>` }) })
      .on("click", () => abrirSuceso(s.id)).addTo(capas.sucesos);
    if (conRotulo.has(s.id)) {
      const rotulo = el("span", { textContent: (s.titulo || "").split(" — ")[0] });
      marca.bindTooltip(rotulo, { permanent: true, direction: "right", offset: [d / 2 + 4, 0], className: `rotulo-suceso${s.tipo === "incidente" ? " rojo" : ""}`, interactive: false });
    }
  }
  capas.textos.clearLayers();
  const desde = ahoraSeg() - 6 * 3600;
  const textos = (E?.feed || []).filter((it) => it.lat != null && it.t >= desde && !["dgt", "renfe", "meteoalarm"].includes(it.fuente));
  for (const grupo of agrupar(textos)) {
    const it = [...grupo].sort((a, b) => (b.urgencia || 0) - (a.urgencia || 0) || b.t - a.t)[0];
    L.marker([it.lat, it.lon], { keyboard: false, title: it.titulo || "", icon: insignia({ dibujo: dibujoDeTexto(it), color: colorDeTexto(it), llena: (it.urgencia || 0) >= 2, cuenta: grupo.length }) })
      .bindPopup(() => popupLista(grupo), { maxWidth: 320 }).addTo(capas.textos);
  }
  capas.avisos.clearLayers();
  for (const grupo of agrupar((E?.avisos || []).filter((a) => a.lat != null))) {
    const a = grupo[0];
    const tren = a.fuente === "renfe";
    L.marker([a.lat, a.lon], { keyboard: false, title: a.titulo || "",
      icon: insignia({ dibujo: dibujoDeAviso(a), color: tren ? C.cian : C.ambar, tam: tren ? 22 : 20, clase: tren ? "" : "carretera", cuenta: grupo.length, llena: (a.urgencia || 0) >= 2 }) })
      .bindPopup(() => popupLista(grupo), { maxWidth: 320 }).addTo(capas.avisos);
  }
  capas.agenda.clearLayers();
  for (const grupo of agrupar((E?.agenda?.destacado || []).filter((a) => a.lat != null))) {
    const a = grupo[0];
    L.marker([a.lat, a.lon], { keyboard: false, title: a.titulo || "", icon: insignia({ dibujo: a.tipo === "partido" ? "deporte" : a.tipo === "festejo" ? "evento" : "estrella", color: C.ambar, tam: 26, llena: true, cuenta: grupo.length }) })
      .on("click", (ev) => { if (grupo.length === 1) { ev.target.closePopup(); abrirPrevisto(a); } })
      .bindPopup(() => popupLista(grupo, true), { maxWidth: 320 }).addTo(capas.agenda);
  }
  capas.obras.clearLayers();
  for (const a of E?.agenda?.planificado || []) {
    if (a.lat == null) continue;
    L.circleMarker([a.lat, a.lon], { renderer: vectores, radius: 3, color: "#94a3b8", weight: 1, fillColor: "#94a3b8", fillOpacity: 0.35 })
      .bindPopup(() => popupCita(a), { maxWidth: 300 }).addTo(capas.obras);
  }
}
function popupTexto(it) {
  const caja = el("div", {},
    el("div", { className: "tt-s", textContent: `${NOMBRE_FUENTE[it.fuente] || it.fuente}${it.medio ? `, ${it.medio}` : ""}, ${fechaHora(it.t)}` }),
    el("div", { style: "margin:4px 0; font-weight:600" }, enlace(it.titulo || "(sin título)", it.url)));
  if (it.barrio) caja.append(el("div", { className: "tt-s", textContent: nombreBarrio(it.barrio) + (it.lugar ? `, ${it.lugar}` : "") }));
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
      L.polyline(p, { renderer: vectores, color: C.rojo, weight: 1.6, opacity: 0.7, dashArray: "3 4", interactive: false }).addTo(capas.helis);
      const u = h.p[h.p.length - 1];
      const marca = L.divIcon({ className: "icono-heli", html: "<b></b>", iconSize: [14, 14], iconAnchor: [7, 7] });
      L.marker([u[1], u[2]], { icon: marca, keyboard: false, title: h.nombre || ident })
        .bindTooltip(`${h.nombre || ident}, ${u[3] == null ? "altura desconocida" : `${u[3]} m`}`, { className: "sala", direction: "right", offset: [8, 0] }).addTo(capas.helis);
    }
  } catch { /* sin cielo */ }
  relojCielo = setTimeout(pedirCielo, 30000);
}

/* ====================== Leyenda (solo para comparar y movilidad: la del día a día está en las capas) ====================== */
function pintarLeyenda() {
  const caja = $("leyenda");
  caja.replaceChildren();
  if (modo.tipo === "nivel") return;
  caja.append(el("div", { className: "titulo", textContent: modo.titulo || "" }));
  const g = el("div", { className: "degradado" });
  g.style.background = `linear-gradient(90deg, ${modo.neg}, #0d1822 50%, ${modo.pos})`;
  caja.append(g, el("div", { className: "lin", style: "justify-content:space-between" }, el("span", { textContent: modo.izquierda || "menos" }), el("span", { textContent: modo.derecha || "más" })));
}

/* ====================== Cabecera ====================== */
function pintarReloj() {
  const d = new Date();
  $("reloj").firstChild.nodeValue = `${dos(d.getHours())}:${dos(d.getMinutes())}:${dos(d.getSeconds())}`;
  $("fecha").textContent = `${DIAS_LARGOS[d.getDay()]} ${d.getDate()} de ${MESES_LARGOS[d.getMonth()]}`;
  const vivo = $("vivo");
  if (!E) { vivo.className = "vivo parado"; vivo.textContent = "sin datos"; return; }
  const edad = ahoraSeg() - (E.generado || 0);
  const limite = servidor ? 150 : 25 * 60;
  vivo.className = `vivo${edad > limite * 6 ? " parado" : edad > limite ? " atrasado" : ""}`;
  vivo.textContent = servidor && edad <= limite ? "en directo" : `actualizado ${hace(edad)}`;
}
setInterval(pintarReloj, 1000);

function pintarCabecera() {
  const ap = E.aprendiendo;
  const aprendiendo = !!ap && !ap.listo;
  let clase = E.nivel?.clase || "normal";
  // Con menos de cuatro semanas de histórico, lo normal de cada barrio a cada hora aún no es fiable: no se pasa de «atención».
  if (aprendiendo && (clase === "alta" || clase === "muy alta")) clase = "atencion";
  const [color, nombre, barras] = CLASE_NIVEL[clase] || CLASE_NIVEL.normal;
  const caja = $("nivel-ciudad");
  caja.style.setProperty("--c", color);
  caja.classList.toggle("provisional", aprendiendo);
  $("nivel-valor").textContent = nombre;
  $("nivel-detalle").textContent = !aprendiendo ? "" : ap.dias != null && ap.dias < 7 ? `aprendiendo, día ${Math.floor(ap.dias) + 1} de 28` : `aprendiendo, semana ${Math.min(4, (ap.semanas || 0) + 1)} de 4`;
  caja.title = `${E.nivel?.frase || ""}${aprendiendo ? ". Con menos de cuatro semanas de histórico lo normal aún no es fiable, así que la sala no pasa de «atención»." : ""}`;
  $("nivel-barras").replaceChildren(...[1, 2, 3, 4].map((k) => { const s = el("span"); if (k <= barras) { s.style.background = color; s.style.boxShadow = `0 0 6px ${color}`; } return s; }));
  const fuentes = E.fuentes || [];
  const ahora = ahoraSeg();
  const bien = fuentes.filter((f) => f.ok && f.ultima && ahora - f.ultima < Math.max(3 * (f.cada || 600), 1800)).length;
  const chip = $("chip-fuentes");
  chip.className = `chip ${!fuentes.length ? "" : bien === fuentes.length ? "ok" : bien >= fuentes.length * 0.7 ? "aviso" : "mal"}`;
  chip.replaceChildren(el("span", { className: "punto" }), fuentes.length ? `${bien} de ${fuentes.length} fuentes` : "Fuentes");
  const ia = E.ia || {};
  const chipIa = $("chip-ia");
  chipIa.hidden = !servidor;
  chipIa.className = `chip opcional ${ia.disponible ? "ia" : ""}`;
  chipIa.textContent = ia.disponible ? `IA local (${ia.modelo})` : "Sin IA local";
  chipIa.title = ia.disponible ? `IA local (${ia.modelo}): ${ia.hechos?.sucesos || 0} sucesos resumidos y ${ia.hechos?.textos || 0} textos leídos` : "Sin IA local: todo funciona con reglas. Instala Ollama para que resuma sucesos y escriba el parte.";
  const activos = (E.sucesos || []).filter((s) => s.estado === "activo").length;
  $("pestana-n").textContent = activos ? `(${activos})` : "";
  const aviso = $("aviso-mapa");
  aviso.hidden = !!E.hay;
  if (!E.hay) { $("aviso-titulo").textContent = "Preparando la sala"; $("aviso-texto").textContent = E.fase || "Esperando al programa del ordenador…"; }
}
$("chip-fuentes").addEventListener("click", abrirFuentes);

/* ====================== Columnas ====================== */
function tejaTrafico() {
  const cuenta = [0, 0, 0, 0];
  let total = 0;
  for (const v of Object.values(estadosTrafico)) if (v != null && v >= 0 && v <= 3) { cuenta[v]++; total++; }
  const caja = el("div", { className: "teja ancha" }, el("div", { className: "n", textContent: "Tráfico en las calles" }));
  if (!total) { caja.append(el("div", { className: "z", textContent: "Sin datos del estado de las calles." })); return caja; }
  const frase = cuenta[2] ? `${cuenta[2]} ${cuenta[2] === 1 ? "tramo con atasco" : "tramos con atasco"}`
    : cuenta[1] ? `${cuenta[1]} ${cuenta[1] === 1 ? "tramo denso" : "tramos densos"}` : "Todo fluido";
  const reparto = el("div", { className: "reparto" });
  cuenta.forEach((n, k) => {
    if (!n) return;
    const i = el("i", { title: `${NOMBRE_TRAFICO[k]}: ${n}` });
    i.style.cssText = `flex:${n} 1 0; background:${k === 3 ? "repeating-linear-gradient(90deg, #e2e8f0 0 4px, #2a3a44 4px 6px)" : COLOR_TRAFICO[k]}`;
    reparto.append(i);
  });
  const leyenda = el("div", { className: "reparto-ley" }, ...cuenta.map((n, k) => {
    const i = el("i", { className: k === 3 ? "rayas" : "" }); i.style.setProperty("--c", COLOR_TRAFICO[k]);
    return el("span", {}, i, `${NOMBRE_TRAFICO[k]} `, el("b", { textContent: String(n) }));
  }));
  caja.title = traficoDe.origen === "geoportal" ? `Estado de ${total} tramos según el Ajuntament, ${hace(ahoraSeg() - traficoDe.t)}` : `Estado de ${total} tramos, lo último que guardó el programa`;
  caja.classList.add(cuenta[2] ? "alto" : cuenta[1] > total * 0.1 ? "alto" : "normal");
  caja.append(el("div", { className: "v", textContent: frase }), reparto, leyenda);
  return caja;
}
function teja(c, nombre) {
  const z = c.z;
  const estado = z == null ? "" : z >= 2 ? "alto" : z <= -2 ? "bajo" : "normal";
  const frase = c.normal == null ? "aprendiendo lo normal" : z >= 2 ? `más de lo normal (${cifra(c.normal)})` : z <= -2 ? `menos de lo normal (${cifra(c.normal)})` : "normal para la hora";
  return el("div", { className: `teja ${estado}`, title: `${c.nombre}${c.normal != null ? `. Lo normal a esta hora: ${cifra(c.normal)} ${c.unidad || ""}` : ""}` },
    el("div", { className: "n", textContent: nombre }),
    el("div", { className: "v" }, cifra(c.valor), el("small", { textContent: c.unidad && c.unidad.length < 14 ? c.unidad : "" })),
    el("div", { className: "z", textContent: frase }));
}
function pintarTejas() {
  const porClave = Object.fromEntries((E.ciudad || []).map((c) => [c.clave, c]));
  const principales = TEJAS_PRINCIPALES.filter(([clave]) => porClave[clave]).map(([clave, nombre]) => teja(porClave[clave], nombre));
  $("tejas").replaceChildren(tejaTrafico(), ...principales);
  $("tejas-todas").replaceChildren(...TEJAS.filter(([clave]) => porClave[clave]).map(([clave, nombre]) => teja(porClave[clave], nombre)));
  const ultima = Math.max(0, ...(E.ciudad || []).map((c) => c.t || 0));
  $("estado-nota").textContent = ultima ? `datos de las ${hora(ultima)}` : "";
}
$("mas-cifras").addEventListener("click", () => {
  const caja = $("tejas-todas"), b = $("mas-cifras");
  caja.hidden = !caja.hidden;
  b.setAttribute("aria-expanded", String(!caja.hidden));
  b.textContent = caja.hidden ? "Ver todas las cifras" : "Ver menos cifras";
});

function pintarListaBarrios() {
  const filas = Object.entries(E.barrios || {}).filter(([c, b]) => c !== "VLC" && b.nivel >= 2.5).sort((a, b) => b[1].nivel - a[1].nivel);
  $("barrios-nota").textContent = filas.length ? String(filas.length) : "";
  const caja = $("lista-barrios");
  if (!filas.length) { caja.replaceChildren(el("div", { className: "vacio", textContent: E.t ? "Todos los barrios están dentro de lo normal para la hora." : "Calculando…" })); return; }
  caja.replaceChildren(...filas.slice(0, 8).map(([c, b]) => {
    const fam = familiaDominante(b);
    const s = b.senales?.[0];
    const medidor = el("div", { className: "medidor" }, el("i"));
    medidor.firstChild.style.cssText = `width:${Math.min(100, b.nivel * 10)}%; background:${C.magenta}`;
    return el("div", { className: "fila", onclick: () => abrirBarrio(c) },
      el("span", { className: "t", textContent: nombreBarrio(c) }), el("span", { className: "num", style: `color:${C.magenta}`, textContent: cifra(b.nivel) }),
      el("span", { className: "s", textContent: `${NOMBRE_FAMILIA[fam] || ""}${s ? `: ${(E.rasgos?.[s.rasgo]?.nombre || s.rasgo).toLowerCase()} ${cifra(s.valor)}, lo normal ${cifra(s.normal)}` : ""}` }), medidor);
  }));
}

function pintarParte() {
  const p = E.parte || {};
  const caja = $("parte");
  const abierto = !!caja.querySelector("details")?.open;
  const principal = p.ia?.texto || p.texto || "";
  caja.replaceChildren(el("div", { textContent: principal || "—" }));
  if (p.ia?.texto && p.texto) {
    const detalle = el("details", {}, el("summary", { textContent: "Ver el parte con todas las cifras" }), el("p", { textContent: p.texto }));
    detalle.open = abierto;
    caja.append(detalle);
  }
  $("parte-nota").textContent = p.ia?.texto ? `IA local, ${hora(p.ia.t)}` : p.t ? hora(p.t) : "";
  $("tira-parte").replaceChildren(...(principal ? [el("span", { className: "texto-tira", textContent: principal })] : []));
}
const tira = $("tira-parte");
tira.addEventListener("click", () => tira.classList.toggle("abierta"));
tira.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); tira.classList.toggle("abierta"); } });

function pintarHoy() {
  const ag = E.agenda || {};
  const fin = new Date(); fin.setHours(23, 59, 59);
  const filas = (ag.destacado || []).filter((a) => a.desde <= fin.getTime() / 1000 + 86400);
  const caja = $("hoy");
  caja.replaceChildren(...filas.slice(0, 12).map((a) => el("div", { className: "a", title: a.lat != null ? "Ver qué pasa alrededor" : "", onclick: () => (a.lat != null ? abrirPrevisto(a) : null) },
    icono(a.tipo === "partido" ? "deporte" : a.tipo === "festejo" ? "evento" : "estrella", C.ambar),
    el("span", { className: "h", textContent: a.tipo === "partido" || a.tipo === "festejo" ? (a.desde < fin.getTime() / 1000 ? hora(a.desde) : fecha(a.desde).split(" ")[0]) : a.tipo === "fiesta" ? "fiesta" : "festivo" }),
    el("span", {}, a.titulo || "", a.aforo ? el("small", { className: "aforo", textContent: ` aforo ${cifra(a.aforo)}`, title: `${a.recinto}: caben unas ${cifra(a.aforo)} personas` }) : null))));
  const cuenta = ag.cuenta || {};
  const nombres = { obra: "obras", ocupacion: "ocupaciones de la vía", mudanza: "mudanzas" };
  const resumen = Object.entries(cuenta).map(([k, n]) => `${n} ${nombres[k] || k}`).join(", ");
  if (resumen) caja.append(el("div", { className: "vacio", style: "padding-top:6px", textContent: `En curso: ${resumen}.` }));
  if (!filas.length && !resumen) caja.replaceChildren(el("div", { className: "vacio", textContent: "Nada previsto para hoy." }));
  $("hoy-nota").textContent = filas.length ? String(filas.length) : "";
}

function pintarSucesos() {
  const todos = [...(E.sucesos || [])].sort((a, b) => (b.estado === "activo") - (a.estado === "activo") || (b.estado === "activo" ? b.puntuacion - a.puntuacion : b.fin - a.fin));
  const activos = todos.filter((s) => s.estado === "activo").length;
  $("sucesos-nota").textContent = activos ? `${activos} en marcha` : todos.length ? `${todos.length} en las últimas 24 h` : "";
  const caja = $("sucesos");
  if (!todos.length) {
    caja.replaceChildren(el("div", { className: "vacio", textContent: E.aprendiendo && !E.aprendiendo.listo
      ? "Nada fuera de lo normal. La sala aún está aprendiendo cómo es cada barrio a cada hora: con pocos días de histórico solo salta lo muy claro."
      : "Nada fuera de lo normal en las últimas 24 horas." }));
    return;
  }
  caja.replaceChildren(...todos.map((s) => {
    const activo = s.estado === "activo";
    const color = COLOR_TIPO[s.tipo] || C.magenta;
    const fuerza = el("div", { className: "fuerza", title: `Fuerza ${cifra(s.puntuacion)} (cuántas fuentes y cuánto se salen de lo normal)` }, el("i"));
    fuerza.firstChild.style.width = `${Math.min(100, (s.puntuacion || 0) * 7)}%`;
    const fila = el("div", { className: `suceso ${activo ? "activo" : "cerrado"}`, onclick: () => abrirSuceso(s.id) },
      icono(DIBUJO_TIPO[s.tipo] || "gente", color, true), el("div", { className: "t", textContent: s.titulo || "Suceso" }),
      el("div", { className: "s" },
        el("span", { textContent: s.tipo_nombre || s.tipo }),
        el("span", { textContent: activo ? `desde las ${hora(s.inicio)} (${duracion(ahoraSeg() - s.inicio)})` : `de ${hora(s.inicio)} a ${hora(s.fin)}` }),
        insigniaConfianza(s),
        el("span", { className: s.explicado ? "con-causa" : "sin-causa", textContent: s.explicado ? "con causa probable" : "sin causa conocida" })),
      fuerza);
    fila.style.setProperty("--c", color);
    if (s.valoracion === "falso") fila.classList.add("falso");
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
  const color = colorDeTexto(it);
  const reciente = ahoraSeg() - it.t < 20 * 3600;
  const d = new Date(it.t * 1000);
  const s = el("div", { className: "s" }, el("span", { title: `${fecha(it.t)} ${hora(it.t)}`, textContent: reciente ? hora(it.t) : `${d.getDate()}/${d.getMonth() + 1}` }),
    el("span", { textContent: it.medio || NOMBRE_FUENTE[it.fuente] || it.fuente }));
  if (NOMBRE_CATEGORIA[it.categoria]) s.append(el("span", { style: `color:${color}`, textContent: NOMBRE_CATEGORIA[it.categoria] }));
  if (it.barrio) s.append(el("span", { textContent: nombreBarrio(it.barrio) }));
  if (it.lat != null) s.append(el("span", { className: "ir", textContent: "Ver en el mapa", onclick: () => { ponerVista("mapa"); mapa.flyTo([it.lat, it.lon], 16); } }));
  const mas = masMedios(it);
  if (mas) s.append(mas[0]);
  return el("div", { className: `texto${(it.urgencia || 0) >= 2 ? " urgente" : ""}` },
    icono(dibujoDeTexto(it), color), el("div", { className: "t" }, enlace(it.titulo || "(sin título)", it.url)), s, mas ? mas[1] : null);
}
function pintarFeed() {
  const caja = $("feed");
  let lista;
  if (ajustes.feed === "avisos") lista = E.avisos || [];
  const TEMAS_SALA = ["emergencia", "accidente", "seguridad", "protesta", "trafico", "transporte", "meteo", "evento", "deporte"];
  if (ajustes.feed !== "avisos") lista = (E.feed || []).filter((it) => ajustes.feed === "todo"
    ? it.fuente === "prensa" || (REDES.includes(it.fuente) && it.barrio && TEMAS_SALA.includes(it.categoria))
    : ajustes.feed === "prensa" ? it.fuente === "prensa" : REDES.includes(it.fuente));
  const filas = lista.slice(0, 80).map(filaTexto);
  if (ajustes.feed === "redes" && E.publico) {
    const c = E.conversacion || {};
    filas.unshift(el("div", { className: "aviso-web", textContent: `En la web las publicaciones de redes solo se cuentan (en el ordenador se ven enteras): ${c.publicaciones || 0} sobre la ciudad en las últimas dos horas.` }));
  }
  caja.replaceChildren(...(filas.length ? filas : [el("div", { className: "vacio", textContent: "Aún no ha llegado nada." })]));
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
    if (!tramos && E.hay) cargarTramos();
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
let pidiendoTramos = false;
async function cargarTramos() {
  if (pidiendoTramos) return;
  pidiendoTramos = true;
  try {
    const d = await pedirJSON(servidor ? "vivo/sala/tramos" : `${BASE}sala-tramos.json`);
    tramos = d.tramos || [];
    pintarTrafico();
    if (E) pintarTejas();
  } catch { /* sin trazado: se vuelve a pedir en la próxima carga */ }
  pidiendoTramos = false;
}
function pintarTodo() {
  if (!E) return;
  traficoDelPrograma();
  pintarCabecera(); pintarReloj();
  pintarTejas(); pintarListaBarrios(); pintarParte(); pintarHoy(); pintarSucesos(); pintarFeed();
  pintarBarrios(); pintarCapas(); pintarLeyenda();
  capas.calor.ponerPuntos(E.calor?.puntos || []);
  pintarNovedades();
  if (instante == null) cargarLinea();
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
  if (modo.tipo !== "nivel" && modo.tipo !== "instante") { modo = { tipo: "nivel" }; pintarBarrios(); pintarLeyenda(); }
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
  if (elegidos.length) L.geoJSON({ type: "FeatureCollection", features: elegidos }, { pane: "foco", interactive: false,
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
  cont.append(seccionConfianza(s, { grado: s.confianza }, s.id));
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
  cont.append(seccionConfianza(s, d.confianza, s.id));
  cont.append(seccion("Por qué", listaCausas(s.causa)));
  const rel = relacionados(s.id, s.causa?.probable?.id); if (rel) cont.append(rel);
  const alcance = seccionAlcance(d.alcance); if (alcance) cont.append(alcance);
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
    for (const [, h] of helis) L.polyline(h.p.map((x) => [x[1], x[2]]), { pane: "foco", interactive: false, color: C.rojo, weight: 2.2, opacity: 0.9 }).addTo(capas.foco);
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
  L.circleMarker([lat, lon], { pane: "foco", interactive: false, radius: 9, color: C.magenta, weight: 2, fill: false }).addTo(capas.foco);
  L.circleMarker([lat, lon], { pane: "foco", interactive: false, radius: 2.5, color: C.magenta, weight: 0, fillColor: C.magenta, fillOpacity: 1 }).addTo(capas.foco);
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
      L.polyline([[a.lat, a.lon], medio, [b.lat, b.lon]], { pane: "foco", color: C.cian, weight: 1 + 7 * f, opacity: 0.2 + 0.65 * f, interactive: false }).addTo(capas.foco);
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
      L.circleMarker([zona.lat, zona.lon], { pane: "foco", radius: 4 + 14 * Math.sqrt(v / Math.max(...Object.values(llegan))), color: C.cian, weight: 1.5, fillColor: C.cian, fillOpacity: 0.15, interactive: false }).addTo(capas.foco);
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

/* ====================== Confianza, valoración e hilos ====================== */
const NOMBRE_CONFIANZA = { alta: "Confianza alta", media: "Confianza media", baja: "Confianza baja" };
const TITULO_CONFIANZA = { alta: "Lo dicen dos clases de fuente distintas (una, sensores o una fuente oficial) y lleva al menos veinte minutos",
  media: "Lo dicen dos clases de fuente, o varios sensores distintos, pero falta tiempo o corroboración", baja: "Una sola clase de fuente, muy reciente o con lo normal aún por aprender: puede no ser nada" };
function insigniaConfianza(s) {
  if (s?.valoracion === "falso") return el("span", { className: "conf baja", textContent: "Falso positivo", title: "Marcado a mano como falso positivo" });
  if (s?.valoracion === "confirmado") return el("span", { className: "conf alta", textContent: "Confirmado", title: "Confirmado a mano" });
  const g = s?.confianza || "baja";
  return el("span", { className: `conf ${g}`, textContent: NOMBRE_CONFIANZA[g], title: TITULO_CONFIANZA[g] });
}
const CLASES_FUENTE = [["sensor", "Sensores", "Lo que miden las bicis, los aparcamientos, las espiras, el metro o los aviones"], ["oficial", "Fuente oficial", "Incidencias de la DGT, Renfe o avisos de AEMET"],
  ["texto", "Se publica", "Prensa y redes"], ["previsto", "Agenda", "Algo previsto en ese sitio a esa hora"]];
function seccionConfianza(s, conf, id) {
  const caja = seccion("Cuánto fiarse", el("div", { style: "margin-bottom:8px" }, insigniaConfianza({ confianza: conf?.grado, valoracion: s.valoracion ?? s.evidencias?.valoracion })));
  if (conf?.clases) {
    caja.append(el("div", { className: "matriz" }, ...CLASES_FUENTE.map(([clave, nombre, titulo]) => {
      const cosas = conf.clases[clave] || [];
      return el("div", { className: `celda${cosas.length ? " si" : ""}`, title: titulo }, el("b", { textContent: nombre }),
        el("span", { textContent: cosas.length ? cosas.join(", ") : "nada" }));
    })));
    for (const m of conf.motivos || []) caja.append(el("p", { className: "pie", textContent: m }));
  }
  const botones = el("div", { className: "controles", style: "margin-top:8px" });
  if (servidor) {
    const actual = s.valoracion ?? s.evidencias?.valoracion ?? null;
    for (const [valor, texto, titulo] of [["confirmado", "Confirmado", "Ha pasado de verdad: sube la confianza y cuenta a favor de este tipo de suceso en estos barrios"],
      ["falso", "Falso positivo", "No era nada: lo parecido (este tipo, en estos barrios, a esta hora y sin más fuerza) no volverá a saltar"]]) {
      const b = el("button", { type: "button", className: "boton-fino", textContent: actual === valor ? `${texto} ✓` : texto, title: titulo });
      b.setAttribute("aria-pressed", String(actual === valor));
      b.addEventListener("click", async () => {
        try {
          const r = await fetch(`vivo/sala/valorar?id=${encodeURIComponent(id)}&valor=${actual === valor ? "" : valor}`, { method: "POST" });
          if (!r.ok) throw new Error(`error ${r.status}`);
          await cargar(); abrirSuceso(id);
        } catch (err) { b.textContent = `No se ha podido (${err.message})`; }
      });
      botones.append(b);
    }
  }
  botones.append(el("button", { type: "button", className: "boton-fino", textContent: "Informe del suceso", title: "La cronología del suceso, para imprimir o guardar", onclick: () => abrirCronologia(id) }));
  caja.append(botones);
  return caja;
}
function seccionAlcance(alcance) {
  if (!alcance?.length) return null;
  const t = el("table", { className: "datos" }, el("tr", {}, ...["Barrio", "Distancia", "Nivel", "Cuándo", "Qué"].map((x) => el("th", { textContent: x }))));
  for (const a of alcance) t.append(el("tr", { style: "cursor:pointer", onclick: () => abrirBarrio(a.barrio) }, el("td", { textContent: a.nombre }),
    el("td", { textContent: a.anillo === 1 ? "al lado" : "a dos barrios" }), el("td", { className: "num", textContent: cifra(a.nivel) }),
    el("td", { className: "num", textContent: a.minutos ? `+${a.minutos} min` : "a la vez" }), el("td", { textContent: a.senal ? a.senal.nombre : "" })));
  return seccion("Hasta dónde llega", t, el("p", { className: "pie", textContent: "Barrios de alrededor que se han salido de lo normal desde que empezó." }));
}
function masMedios(it) {
  if (!it.mas?.length) return null;
  const lista = el("div", { className: "hilo", hidden: true }, ...it.mas.map((m) => el("div", {}, el("span", { className: "pie", textContent: `${hora(m.t)} ${m.medio || ""} ` }), enlace(m.titulo || "", m.url))));
  const boton = el("button", { type: "button", className: "boton-texto", style: "margin:0", textContent: `y ${it.mas.length} ${it.mas.length === 1 ? "medio más" : "medios más"}`,
    title: "Otros medios que cuentan lo mismo", onclick: () => { lista.hidden = !lista.hidden; } });
  return [boton, lista];
}

/* ====================== Línea de tiempo de 24 horas ====================== */
let lineaT = null;           // {desde, paso, n, maximo, barrios, sucesos}
let instante = null;        // el índice de la línea que se está mirando (null: ahora)
const cajaLinea = $("linea"), lienzoLinea = $("linea-lienzo");
async function cargarLinea() {
  try { lineaT = await pedirJSON(servidor ? "vivo/sala/linea" : `${BASE}sala-linea.json`); } catch { return; }
  cajaLinea.hidden = !lineaT?.n;
  pintarLinea();
}
const colorNivel = (v) => (v >= 8 ? C.rojo : v >= 5 ? C.naranja : v >= 3 ? C.ambar : v >= 1.5 ? "#2f6f7d" : "#16303b");
function pintarLinea() {
  if (!lineaT?.n || cajaLinea.hidden) return;
  const dpr = Math.min(2, window.devicePixelRatio || 1), w = lienzoLinea.clientWidth, h = lienzoLinea.clientHeight;
  if (!w) return;
  lienzoLinea.width = w * dpr; lienzoLinea.height = h * dpr;
  const g = lienzoLinea.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const n = lineaT.n, ancho = w / n, base = h - 13, alto = base - 12;
  for (let k = 0; k < n; k++) {
    const v = lineaT.maximo[k] || 0;
    g.fillStyle = colorNivel(v);
    const a = Math.max(2, Math.min(1, v / 10) * alto);
    g.fillRect(k * ancho, base - a, Math.max(1, ancho - 0.6), a);
  }
  // Los sucesos, como tramos encima; las horas, debajo.
  const x = (t) => ((t - lineaT.desde) / lineaT.paso + 1) * ancho;
  let fila = 0;
  for (const s of lineaT.sucesos || []) {
    if (s.valoracion === "falso") continue;
    g.fillStyle = s.tipo === "incidente" ? C.rojo : C.magenta;
    g.globalAlpha = s.confianza === "baja" ? 0.45 : 1;
    const x0 = Math.max(0, x(s.inicio) - ancho), x1 = Math.min(w, x(s.fin));
    g.fillRect(x0, 2 + (fila++ % 2) * 4, Math.max(3, x1 - x0), 3);
  }
  g.globalAlpha = 1;
  g.fillStyle = C.tenue; g.font = "10px Barlow, sans-serif"; g.textBaseline = "bottom";
  for (let k = 0; k < n; k++) {
    const d = new Date((lineaT.desde + k * lineaT.paso) * 1000);
    if (d.getMinutes() === 0 && d.getHours() % (w < 500 ? 6 : 3) === 0) { g.fillRect(k * ancho, base, 1, 3); g.fillText(`${dos(d.getHours())}h`, k * ancho + 3, h); }
  }
  if (instante != null) { g.fillStyle = "#fff"; g.fillRect(instante * ancho + ancho / 2 - 1, 0, 2, base); }
  $("linea-rotulo").textContent = instante == null ? "Últimas 24 h" : `${fechaHora(lineaT.desde + instante * lineaT.paso)}, ${hace(ahoraSeg() - (lineaT.desde + instante * lineaT.paso))}`;
  $("linea-ahora").hidden = instante == null;
}
function ponerInstante(k) {
  if (!lineaT) return;
  instante = k == null ? null : Math.max(0, Math.min(lineaT.n - 1, k));
  if (instante == null || instante >= lineaT.n - 1) {
    instante = null;
    if (modo.tipo === "instante") { modo = { tipo: "nivel" }; }
  } else {
    const valores = {};
    for (const [b, fila] of Object.entries(lineaT.barrios || {})) if (b !== "VLC" && fila[instante]) valores[b] = fila[instante];
    modo = { tipo: "instante", valores, escala: 10, pos: C.magenta, neg: C.magenta, etiqueta: "Nivel", unidad: "", titulo: `Barrios fuera de lo normal a las ${hora(lineaT.desde + instante * lineaT.paso)}`,
      izquierda: "normal", derecha: "muy fuera" };
  }
  pintarBarrios(); pintarCapas(); pintarLeyenda(); pintarLinea();
}
{
  let arrastrando = false;
  const indice = (ev) => { const r = lienzoLinea.getBoundingClientRect(); return Math.floor(((ev.clientX - r.left) / r.width) * lineaT.n); };
  lienzoLinea.addEventListener("pointerdown", (ev) => { if (!lineaT) return; arrastrando = true; lienzoLinea.setPointerCapture(ev.pointerId); ponerInstante(indice(ev)); });
  lienzoLinea.addEventListener("pointermove", (ev) => { if (arrastrando) ponerInstante(indice(ev)); });
  lienzoLinea.addEventListener("pointerup", () => { arrastrando = false; });
  lienzoLinea.addEventListener("keydown", (ev) => {
    if (!lineaT || !["ArrowLeft", "ArrowRight", "Escape"].includes(ev.key)) return;
    ev.preventDefault();
    ponerInstante(ev.key === "Escape" ? null : (instante ?? lineaT.n - 1) + (ev.key === "ArrowLeft" ? -1 : 1));
  });
  $("linea-ahora").addEventListener("click", () => ponerInstante(null));
  L.DomEvent.disableClickPropagation(cajaLinea); L.DomEvent.disableScrollPropagation(cajaLinea);
  window.addEventListener("resize", pintarLinea);
}

/* ====================== Qué ha cambiado desde la última visita ====================== */
function pintarNovedades() {
  const caja = $("novedades");
  const antes = leerLocal("osintmaps.sala.visto", null);
  const ahora = ahoraSeg();
  const ids = (E.sucesos || []).map((s) => s.id);
  guardarLocal("osintmaps.sala.visto", { t: ahora, ids, abiertos: (E.sucesos || []).filter((s) => s.estado === "activo").map((s) => s.id) });
  if (pintarNovedades.hecho) return;
  pintarNovedades.hecho = true;
  if (!antes || ahora - antes.t < 1800 || ahora - antes.t > 7 * 86400) return;
  const nuevos = (E.sucesos || []).filter((s) => !antes.ids?.includes(s.id) && s.valoracion !== "falso");
  const cerrados = (E.sucesos || []).filter((s) => s.estado !== "activo" && antes.abiertos?.includes(s.id));
  const urgentes = (E.feed || []).filter((it) => it.t > antes.t && (it.urgencia || 0) >= 2);
  const partes = [];
  if (nuevos.length) partes.push(`${nuevos.length} ${nuevos.length === 1 ? "suceso nuevo" : "sucesos nuevos"}`);
  if (cerrados.length) partes.push(`${cerrados.length} ${cerrados.length === 1 ? "se ha cerrado" : "se han cerrado"}`);
  if (urgentes.length) partes.push(`${urgentes.length} ${urgentes.length === 1 ? "noticia urgente" : "noticias urgentes"}`);
  const texto = `Desde tu última visita (${fechaHora(antes.t)}): ${partes.length ? partes.join(", ") : "nada nuevo"}.`;
  const ver = partes.length ? el("button", { type: "button", className: "boton-fino", textContent: "Ver", onclick: () => {
    const cont = abrirFicha({ tipo: "Novedades", titulo: `Desde ${fechaHora(antes.t)}`, clave: null, estrecha: true });
    if (nuevos.length) cont.append(seccion("Sucesos nuevos", ...nuevos.map(filaSuceso)));
    if (cerrados.length) cont.append(seccion("Se han cerrado", ...cerrados.map(filaSuceso)));
    if (urgentes.length) cont.append(seccion("Noticias urgentes", ...urgentes.map(filaTexto)));
    caja.hidden = true;
  } }) : null;
  caja.replaceChildren(el("span", { textContent: texto }), ver, el("button", { type: "button", className: "boton-texto", style: "margin:0", textContent: "Cerrar", onclick: () => { caja.hidden = true; } }));
  caja.hidden = false;
  if (!partes.length) setTimeout(() => { caja.hidden = true; }, 6000);
}

/* ====================== Lo previsto: esperado frente a observado ====================== */
async function abrirPrevisto(a) {
  const cont = abrirFicha({ tipo: a.tipo === "partido" ? "Partido" : "Previsto", color: C.ambar, titulo: a.titulo, clave: `previsto=${a.id}`,
    sub: `${fechaHora(a.desde)} → ${hora(a.hasta)}${a.aforo ? ` · aforo ${cifra(a.aforo)}` : ""}` });
  if (a.lat != null) { capas.foco.clearLayers(); L.circle([a.lat, a.lon], { pane: "foco", interactive: false, radius: 600, color: C.ambar, weight: 1.5, dashArray: "5 5", fillOpacity: 0.04 }).addTo(capas.foco); mapa.flyTo([a.lat, a.lon], 15, { duration: 0.6 }); }
  if (!servidor) {
    cont.append(seccion("Qué se sabe", el("p", { textContent: a.recinto ? `${a.recinto}: caben unas ${cifra(a.aforo)} personas.` : "Sin datos del recinto." })),
      avisoWeb("Cómo se llena y se vacía el barrio alrededor, frente a otras veces en el mismo sitio, se ve en el programa del ordenador."));
    return;
  }
  cargando(cont);
  try {
    const d = await pedirJSON(`vivo/sala/previsto?id=${encodeURIComponent(a.id)}`);
    if (fichaAbierta !== `previsto=${a.id}`) return;
    cont.replaceChildren();
    resaltarBarrios([d.barrios[0].codigo], C.ambar);
    cont.append(seccion("De un vistazo", ...d.frases.map((f) => el("p", { textContent: f }))));
    const fin = d.desde + (Object.values(d.rasgos)[0]?.ahora || Object.values(d.rasgos)[0]?.esperado || []).length * d.paso;
    for (const [, x] of Object.entries(d.rasgos)) {
      const puntos = (fila) => (fila || []).map((v, k) => [d.desde + k * d.paso, v]).filter((p) => p[1] != null);
      const lineas = [{ nombre: "esta vez", color: C.cian, puntos: puntos(x.ahora) }];
      if (x.esperado) lineas.push({ nombre: "otras veces", color: C.ambar, discontinua: true, grosor: 1.3, puntos: puntos(x.esperado).map(([t, v]) => [t, v]) });
      if (!lineas[0].puntos.length && !x.esperado) continue;
      const c = lienzo();
      cont.append(seccion(`${x.nombre} (${x.unidad})`, c));
      requestAnimationFrame(() => grafica(c, lineas, { x0: d.desde, x1: fin, banda: [d.cita.desde, d.cita.hasta], leyenda: true }));
    }
    cont.append(el("p", { className: "pie", textContent: `Media de ${d.barrios.map((b) => b.nombre).join(", ")}. Franja: lo que dura lo previsto. `
      + (d.anteriores.length ? `Otras veces: ${d.anteriores.map((x) => `${x.titulo} (${fecha(x.desde)})`).join("; ")}.` : "") }));
  } catch (err) { fallo(cont, err); }
}

/* ====================== Informes: relevo, cronología de un suceso y calidad ====================== */
const imprimir = () => { document.body.classList.add("imprimiendo"); window.print(); setTimeout(() => document.body.classList.remove("imprimiendo"), 500); };
function botonesInforme(texto) {
  const copiar = el("button", { type: "button", className: "boton-fino", textContent: "Copiar el texto", onclick: async () => {
    try { await navigator.clipboard.writeText(texto()); copiar.textContent = "Copiado"; } catch { copiar.textContent = "No se ha podido copiar"; }
    setTimeout(() => { copiar.textContent = "Copiar el texto"; }, 2000);
  } });
  return el("div", { className: "controles no-imprimir" }, copiar, el("button", { type: "button", className: "boton-fino", textContent: "Imprimir o guardar en PDF", onclick: imprimir }));
}
function filaSuceso(s) {
  return el("div", { className: "fila", onclick: () => abrirSuceso(s.id) }, el("span", { className: "t", textContent: s.titulo }), insigniaConfianza(s),
    el("span", { className: "s", textContent: s.estado === "activo" ? `desde las ${hora(s.inicio)}` : `de ${hora(s.inicio)} a ${hora(s.fin)}` }));
}
function abrirInformes() {
  const cont = abrirFicha({ tipo: "Informes", titulo: "Informes de la sala", clave: "informes", estrecha: true, sub: "Hechos con lo que la sala tiene guardado; todos se pueden imprimir" });
  const entrada = (titulo, texto, al_pulsar) => el("div", { className: "fila", onclick: al_pulsar }, el("span", { className: "t", textContent: titulo }), el("span", { className: "s", textContent: texto }));
  cont.append(seccion("Elige uno",
    entrada("Relevo de turno", "Qué ha pasado en las últimas horas, qué sigue abierto y qué viene", () => abrirRelevo(8)),
    entrada("Calidad de la semana", "Sucesos por tipo y confianza, aciertos y falsos positivos, fuentes que fallan", abrirCalidad),
    entrada("Riesgo de accidente ahora", "Los cruces con más accidentes a esta hora en días como hoy", abrirRiesgo)),
    el("p", { className: "pie", textContent: "El informe de un suceso está en su ficha («Informe del suceso») y el de algo previsto, al pulsarlo en «Hoy»." }));
  const al = E?.alertas;
  if (servidor && al) cont.append(seccion("Alertas al móvil", el("p", { textContent: al.encendidas ? `Encendidas: ${al.enviadas} enviadas esta semana.${al.error ? ` Último fallo: ${al.error}` : ""}`
    : "Apagadas. Para recibir un aviso cuando salte un suceso con confianza alta: instala la aplicación ntfy en el móvil, suscríbete a un tema con un nombre difícil de adivinar y escribe ese nombre en datos/alertas.json, así: {\"ntfy\": \"tu-tema\"}." })));
  cont.append(seccion("Pantalla", el("button", { type: "button", className: "boton-fino", textContent: "Modo pared", title: "Pantalla completa, sin paneles de trabajo, y recorriendo sola los sucesos en marcha (tecla P)", onclick: () => { cerrarFicha(); ponerPared(true); } })));
}
async function abrirRelevo(horas) {
  const cont = abrirFicha({ tipo: "Informe", titulo: "Relevo de turno", clave: "relevo", sub: `Últimas ${horas} horas y próximas ${horas}` });
  cargando(cont);
  try {
    const d = await pedirJSON(servidor ? `vivo/sala/relevo?horas=${horas}` : `${BASE}sala-relevo.json`);
    if (fichaAbierta !== "relevo") return;
    cont.replaceChildren();
    const selector = el("div", { className: "controles no-imprimir" });
    if (servidor) for (const h of [4, 8, 12, 24]) { const b = el("button", { type: "button", className: "boton-fino", textContent: `${h} h`, onclick: () => abrirRelevo(h) }); b.setAttribute("aria-pressed", String(h === d.horas)); selector.append(b); }
    cont.append(selector, botonesInforme(() => d.texto));
    cont.append(seccion(`Abierto ahora (${d.abiertos.length})`, ...(d.abiertos.length ? d.abiertos.map(filaSuceso) : [el("p", { className: "vacio", textContent: "Nada." })])));
    cont.append(seccion(`Cerrado en el turno (${d.cerrados.length})`, ...(d.cerrados.length ? d.cerrados.map(filaSuceso) : [el("p", { className: "vacio", textContent: "Nada." })])));
    if (d.urgentes.length) cont.append(seccion("Noticias urgentes", ...d.urgentes.map((u) => filaTexto({ ...u, medio: "Prensa" }))));
    cont.append(seccion("Avisos en vigor", ...(d.avisos.length ? d.avisos.map((a) => el("p", { textContent: a.titulo })) : [el("p", { className: "vacio", textContent: "Ninguno." })]),
      el("p", { className: "pie", textContent: `Incidencias de carretera activas en el área (DGT): ${d.incidencias}.` })));
    cont.append(seccion(`Próximas ${d.horas} horas`, ...(d.proximo.length ? d.proximo.map((p) => el("div", { className: "fila" },
      el("span", { className: "t", textContent: p.titulo }), el("span", { className: "num", textContent: p.aforo ? `aforo ${cifra(p.aforo)}` : "" }),
      el("span", { className: "s", textContent: `${p.en_marcha ? "en marcha" : fechaHora(p.desde)}${p.barrio_nombre ? `, ${p.barrio_nombre}` : ""}` }))) : [el("p", { className: "vacio", textContent: "Nada destacado en la agenda." })]),
      d.cortes_previstos ? el("p", { className: "pie", textContent: `Empiezan ${d.cortes_previstos} obras u ocupaciones de la vía.` }) : null));
    cont.append(seccion("Fuentes", el("p", { textContent: d.fuentes_caidas.length ? `Fallan: ${d.fuentes_caidas.join(", ")}.` : `Las ${d.fuentes} contestan.` })));
    if (d.aprendiendo && !d.aprendiendo.listo) cont.append(el("p", { className: "pie", textContent: `La sala lleva ${cifra(d.aprendiendo.dias)} días aprendiendo lo normal de cada barrio (necesita 28): lo de confianza baja puede no ser nada.` }));
    if (!servidor) cont.append(avisoWeb(`Hecho por el ordenador ${hace(ahoraSeg() - d.generado)}.`));
  } catch (err) { fallo(cont, err); }
}
async function abrirCronologia(id) {
  if (!servidor) { const cont = abrirFicha({ tipo: "Informe", titulo: "Informe del suceso", clave: null }); cont.append(avisoWeb("El informe de un suceso se hace en el programa del ordenador.")); return; }
  const cont = abrirFicha({ tipo: "Informe del suceso", titulo: "…", clave: `informe=${id}` });
  cargando(cont);
  try {
    const d = await pedirJSON(`vivo/sala/cronologia?id=${encodeURIComponent(id)}`);
    if (fichaAbierta !== `informe=${id}`) return;
    const s = d.suceso;
    cont.titulo.textContent = s.titulo;
    cont.replaceChildren(botonesInforme(() => [s.titulo, `${fechaHora(s.inicio)} a ${s.estado === "activo" ? "ahora" : hora(s.fin)}. ${NOMBRE_CONFIANZA[d.confianza?.grado || "baja"]}.`,
      s.resumen || "", "", ...d.hitos.map((h) => `${hora(h.t)}  ${h.que}: ${h.detalle || ""}`)].join("\n")),
      el("div", { className: "controles no-imprimir" }, el("button", { type: "button", className: "boton-fino", textContent: "Volver a la ficha", onclick: () => abrirSuceso(id) })));
    cont.append(seccion("Resumen", el("p", {}, insigniaConfianza(s), ` ${s.tipo_nombre}. ${fechaHora(s.inicio)} a ${s.estado === "activo" ? "ahora (sigue abierto)" : hora(s.fin)}, ${duracion((s.estado === "activo" ? ahoraSeg() : s.fin) - s.inicio)}.`),
      s.resumen ? el("div", { className: "resumen" }, s.resumen, el("small", { textContent: "IA local" })) : null,
      el("p", { textContent: d.causa ? `Causa probable: ${d.causa.titulo}.` : "Sin causa conocida." }), ...(d.confianza?.motivos || []).map((m) => el("p", { className: "pie", textContent: m }))));
    const t = el("table", { className: "datos" }, el("tr", {}, ...["Hora", "Qué", "Detalle"].map((x) => el("th", { textContent: x }))));
    for (const h of d.hitos) t.append(el("tr", {}, el("td", { className: "num", textContent: hora(h.t) }), el("td", { textContent: h.que }), el("td", {}, h.url ? enlace(h.detalle, h.url) : (h.detalle || ""))));
    cont.append(seccion("Cronología", t));
    const alcance = seccionAlcance(d.alcance); if (alcance) cont.append(alcance);
    cont.append(el("p", { className: "pie", textContent: `Informe hecho el ${fecha(ahoraSeg())} a las ${hora(ahoraSeg())} con datos públicos y de conjunto. No identifica a nadie.` }));
  } catch (err) { fallo(cont, err); }
}
async function abrirCalidad() {
  const cont = abrirFicha({ tipo: "Informe", titulo: "Calidad de la semana", clave: "calidad", sub: "Cómo ha acertado la sala y qué fuentes han fallado" });
  cargando(cont);
  try {
    const d = await pedirJSON(servidor ? "vivo/sala/calidad?dias=7" : `${BASE}sala-calidad.json`);
    if (fichaAbierta !== "calidad") return;
    cont.replaceChildren(botonesInforme(() => `Calidad de la sala, últimos ${d.dias} días: ${d.sucesos} sucesos, ${d.valoraciones.confirmados} confirmados, ${d.valoraciones.falsos} falsos positivos.`));
    const v = d.valoraciones, c = d.por_confianza || {};
    const dato = (n, valor) => el("div", { className: "dato" }, el("div", { className: "n", textContent: n }), el("div", { className: "v", textContent: valor }));
    cont.append(seccion(`Sucesos (${d.dias} días)`, el("div", { className: "rejilla-2" }, dato("Sucesos", cifra(d.sucesos)), dato("Con causa probable", cifra(d.explicados)),
      dato("Confianza alta / media / baja", `${c.alta || 0} / ${c.media || 0} / ${c.baja || 0}`),
      dato("Confirmados / falsos positivos", `${v.confirmados} / ${v.falsos}${v.acierto != null ? ` (${v.acierto} % de acierto)` : ""}`), dato("Sin valorar", cifra(v.sin_valorar)))));
    if (d.por_tipo.length) cont.append(seccion("Por tipo", ...d.por_tipo.map(([tipo, n]) => el("div", { className: "causa" }, el("span", { textContent: tipo }), el("span"), el("span", { className: "peso", textContent: String(n) })))));
    if (d.barrios.length) cont.append(seccion("Barrios que más saltan", ...d.barrios.map((b) => el("div", { className: "fila", onclick: () => abrirBarrio(b.codigo) }, el("span", { className: "t", textContent: b.nombre }), el("span", { className: "num", textContent: String(b.n) })))),
      el("p", { className: "pie", textContent: "Si un barrio salta mucho sin que pase nada, marca sus sucesos como falso positivo: lo parecido dejará de saltar." }));
    const t = el("table", { className: "datos" }, el("tr", {}, ...["Fuente", "Tomas", "Bien"].map((x) => el("th", { textContent: x }))));
    for (const f of d.fuentes) t.append(el("tr", {}, el("td", { textContent: f.nombre }), el("td", { className: "num", textContent: cifra(f.tomas) }),
      el("td", { className: `num ${f.bien < 90 ? "z-pos" : "z-0"}`, textContent: f.bien == null ? "—" : `${cifra(f.bien)} %` })));
    cont.append(seccion("Fuentes", t));
    if (d.aprendiendo && !d.aprendiendo.listo) cont.append(el("p", { className: "pie", textContent: `Con ${cifra(d.aprendiendo.dias)} días de histórico (de 28) es normal que haya falsos positivos.` }));
  } catch (err) { fallo(cont, err); }
}
let riesgo = null;
async function pedirRiesgo() {
  if (!riesgo || ahoraSeg() - riesgo.pedido > 1800) { riesgo = await pedirJSON(servidor ? "vivo/sala/riesgo" : `${BASE}sala-riesgo.json`); riesgo.pedido = ahoraSeg(); }
  capas.riesgo.ponerPuntos(riesgo.puntos || []);
  return riesgo;
}
async function abrirRiesgo() {
  const cont = abrirFicha({ tipo: "Informe", titulo: "Riesgo de accidente ahora", clave: "riesgo", estrecha: true, color: C.naranja });
  cargando(cont);
  try {
    const d = await pedirRiesgo();
    if (!ajustes.capas.riesgo) { ponerCapa("riesgo", true); montarCapas(); }
    cont.replaceChildren(seccion("De dónde sale", el("p", { textContent: `${cifra(d.n)} accidentes de tráfico registrados por el Ajuntament ${d.franja || ""} en ${d.dias || "días como hoy"}. En el mapa, en naranja: más intenso, más accidentes y más graves.` })));
    cont.append(seccion("Los cruces con más", ...(d.cruces || []).map((c) => el("div", { className: "fila", onclick: () => { ponerVista("mapa"); mapa.flyTo([c.lat, c.lon], 17); } },
      el("span", { className: "t", textContent: c.ubicacion || "" }), el("span", { className: "num", textContent: String(c.n) }),
      el("span", { className: "s", textContent: `${c.barrio_nombre || ""}${c.gravedad ? `, hasta ${GRAVEDAD[c.gravedad]}` : ""}` })))),
      el("p", { className: "pie", textContent: "Es dónde y a qué hora ha habido accidentes, no una predicción de nadie en concreto." }));
  } catch (err) { fallo(cont, err); }
}

/* ====================== Modo pared ====================== */
let relojPared = 0, turnoPared = 0;
function ponerPared(si) {
  document.body.classList.toggle("pared", si);
  clearInterval(relojPared);
  if (si) {
    document.documentElement.requestFullscreen?.().catch(() => {});
    const paso = () => {
      const activos = (E?.sucesos || []).filter((s) => s.estado === "activo" && s.lat != null && s.valoracion !== "falso");
      if (!activos.length || turnoPared % (activos.length + 1) === activos.length) mapa.flyTo([39.4699, -0.3763], 13, { duration: 1.5 });
      else { const s = activos[turnoPared % (activos.length + 1)]; mapa.flyTo([s.lat, s.lon], 15, { duration: 1.5 }); }
      turnoPared++;
    };
    relojPared = setInterval(paso, 25000);
  } else if (document.fullscreenElement) document.exitFullscreen?.();
  setTimeout(() => { mapa.invalidateSize(); pintarLinea(); }, 300);
}
document.addEventListener("keydown", (ev) => {
  if (ev.target.matches("input, select, textarea") || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if (ev.key === "p" || ev.key === "P") ponerPared(!document.body.classList.contains("pared"));
  else if (ev.key === "Escape" && document.body.classList.contains("pared")) ponerPared(false);
});
$("salir-pared").addEventListener("click", () => ponerPared(false));
$("b-informes").addEventListener("click", abrirInformes);

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
window.OSINT_SALA = { estado: () => E, abrirSuceso, abrirBarrio, abrirLugar, abrirComparar, abrirMovilidad, cerrarFicha, modo: () => modo, servidor: () => servidor,
  abrirInformes, abrirRelevo, abrirCalidad, abrirRiesgo, abrirCronologia, abrirPrevisto, ponerInstante, ponerPared, linea: () => lineaT, instante: () => instante,
  capas: () => ({ barrios: capas.barrios ? capas.barrios.getLayers().length : 0, tramos: capas.trafico.getLayers().length, calor: (E?.calor?.puntos || []).length,
    sucesos: capas.sucesos.getLayers().length, textos: capas.textos.getLayers().length, avisos: capas.avisos.getLayers().length, agenda: capas.agenda.getLayers().length,
    trafico: traficoDe.origen }) };

/* ====================== Arranque ====================== */
pintarLeyenda();
pintarReloj();
function vigilarHistorico() {
  const caja = $("pulso");
  if (!caja) return;
  new MutationObserver(() => {
    const abierto = !caja.hidden;
    $("b-tiempo").setAttribute("aria-pressed", String(abierto));
    for (const id of ["trafico", "calor"]) if (ajustes.capas[id]) (abierto ? mapa.removeLayer(capas[id]) : capas[id].addTo(mapa));
    if (abierto) ponerInstante(null);
    cajaLinea.hidden = abierto || !lineaT?.n;
    if (!abierto) { pintarTrafico(); pintarLinea(); }
  }).observe(caja, { attributes: true, attributeFilter: ["hidden"] });
}
hayServidor.then(async (si) => {
  servidor = si;
  document.documentElement.classList.toggle("sin-servidor", !si);
  montarCapas();
  vigilarHistorico();
  await cargar();
  pedirTraficoVivo();
  if (servidor && ajustes.capas.helis) pedirCielo();
  // Lo que pide la dirección: #suceso=..., #barrio=..., #lugar=lat,lon, #vista=lat,lon,zoom, #comparar, #movilidad
  const [clave, valor] = decodeURIComponent(location.hash.slice(1)).split("=");
  if (clave === "suceso" && valor) abrirSuceso(valor);
  else if (clave === "barrio" && valor) abrirBarrio(valor);
  else if (clave === "lugar" && valor) { const [la, lo] = valor.split(",").map(Number); if (Number.isFinite(la) && Number.isFinite(lo)) abrirLugar(la, lo); }
  else if (clave === "vista" && valor) { const [la, lo, z] = valor.split(",").map(Number); if (Number.isFinite(la) && Number.isFinite(lo)) mapa.setView([la, lo], Number.isFinite(z) ? z : 15); }
  else if (clave === "comparar") abrirComparar();
  else if (clave === "movilidad") abrirMovilidad();
  else if (clave === "informes") abrirInformes();
  else if (clave === "relevo") abrirRelevo(8);
  else if (clave === "calidad") abrirCalidad();
  else if (clave === "riesgo") abrirRiesgo();
  else if (clave === "informe" && valor) abrirCronologia(valor);
  else if (clave === "previsto" && valor) { const a = (E?.agenda?.destacado || []).find((x) => x.id === valor); if (a) abrirPrevisto(a); }
  else if (clave === "pared") ponerPared(true);
  if (ajustes.capas.riesgo) pedirRiesgo().catch(() => {});
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  if (E && ahoraSeg() - E.generado > (servidor ? 45 : 600)) cargar();
  if (ahoraSeg() - traficoDe.t > 240) pedirTraficoVivo();
});
})();
