/* OSINT Maps: el pulso de la ciudad.

   Una consola sobre el mapa para ver València a lo largo del tiempo: una línea de tiempo que se
   arrastra, los indicadores de toda la ciudad comparados con lo normal a esa hora, y encima del
   mapa lo que marcaba cada estación de Valenbisi, cada aparcamiento y cada tramo de calle, y por
   dónde iban los aviones y los trenes.

   Los datos son siempre un «resumen» con la misma forma (lo arma osintmaps/pulso/resumen.py):

   - Con el programa del ordenador detrás, se le pide el trozo que se quiera, de cualquier día,
     y se vuelve a pedir cada minuto mientras se mira «ahora».
   - En la web publicada no hay a quién pedir: se lee datos/pulso.json, las últimas 48 horas que
     subió el ordenador la última vez que estuvo abierto. Lo de ahora mismo (bicis, aparcamientos
     y tráfico) sí lo puede pedir el navegador al Ayuntamiento, y se añade.

   Este fichero se basta solo: crea su botón, su consola y sus estilos. Usa del visor el mapa
   (`mapa`) y cuatro utilidades (`el`, `pedirJSON`, `hayServidor`, `leerLocal`/`guardarLocal`). */
(() => {
"use strict";
if (typeof mapa === "undefined" || typeof L === "undefined") return;

const GEOPORTAL = "https://geoportal.valencia.es/server/rest/services/OPENDATA";
const CIAN = "#22d3ee", MAGENTA = "#ff2d95", AMBAR = "#fbbf24", LIMA = "#a3e635", ROJO = "#f43f5e", GRIS = "#64748b";
const RANGOS = [["1 h", 1], ["6 h", 6], ["24 h", 24], ["48 h", 48], ["7 d", 168], ["30 d", 720]];
const VELOCIDADES = [[300, "5 min/s"], [900, "15 min/s"], [3600, "1 h/s"], [14400, "4 h/s"]];
/* Las capas del mapa: de qué serie (o rastro) salen. «flujo» es la misma serie de bicis, mirando cuánto ha cambiado. */
const CAPAS_PULSO = [
  { id: "bicis", nombre: "Bicis", serie: "bicis", leyenda: "cada estación de Valenbisi; rojo, sin bicis; magenta, sin huecos; de ámbar a cian, de pocas a muchas bicis" },
  { id: "flujo", nombre: "Flujo de bicis", serie: "bicis", leyenda: "lo que ha cambiado cada estación en media hora; cian, han llegado bicis; magenta, se han ido; más grande, más cambio" },
  { id: "parking", nombre: "Aparcamientos", serie: "parking", leyenda: "el aro va de verde (hay sitio) a ámbar (más del 80 % ocupado) y rojo (más del 95 %)" },
  { id: "trafico", nombre: "Tráfico", serie: "trafico", leyenda: "cada tramo: verde fino, fluido; ámbar, denso; rojo, congestionado; blanco a rayas, cortado" },
  { id: "aforo", nombre: "Aforos", serie: "aforo", leyenda: "cada espira bajo el asfalto: más grande y más opaco, más vehículos por hora" },
  { id: "no2", nombre: "NO₂", serie: "no2", leyenda: "cada estación de aire: verde por debajo de 40 µg/m³, ámbar hasta 100, rojo por encima" },
  { id: "aviones", nombre: "Aviones", rastro: "aviones", leyenda: "cada avión con su indicativo y su altitud, y por dónde ha ido los últimos 8 minutos" },
  { id: "trenes", nombre: "Trenes", rastro: "trenes", leyenda: "cada tren de Cercanías y su recorrido del último cuarto de hora" },
];
const TEJAS = ["bicis_fuera", "parking_ocupacion", "trafico_indice", "aforo", "aforo_bici", "aire_no2", "aire_pm25", "aviones", "aviones_bajos", "trenes", "meteo_temperatura", "meteo_lluvia"];
const ESTADO_TRAFICO = ["fluido", "denso", "congestionado", "cortado"];

const ajustes = Object.assign({ abierto: false, clave: "trafico_indice", capas: ["bicis", "trafico", "aviones", "trenes"], horas: 48, velocidad: 1, fondo: true },
  leerLocal("osintmaps.pulso.v1", {}));
const recordar = () => guardarLocal("osintmaps.pulso.v1", ajustes);

let R = null;                 // el resumen cargado
let T = 0;                    // el momento que se está mirando (segundos desde 1970)
let enDirecto = true;         // el cursor sigue al final de los datos
let reproduciendo = false, ultimoCuadro = 0, relojDirecto = 0, cargando = false, hastaFijo = null;
let horasVistas = 0;          // el rato que se está enseñando (puede ser menos que el elegido si aún hay poco histórico)
let servidor = false;         // ¿está detrás el programa del ordenador?
let vivoWeb = null;           // en la web: lo de ahora mismo, pedido al Ayuntamiento {serie: {id: valor}, t}
const dibujadas = {};         // id de capa -> { grupo, piezas }

/* ---------- Horas y cifras ---------- */
const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const dos = (n) => String(n).padStart(2, "0");
const hora = (t) => { const d = new Date(t * 1000); return `${dos(d.getHours())}:${dos(d.getMinutes())}`; };
const dia = (t) => { const d = new Date(t * 1000); return `${DIAS[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`; };
const hace = (seg) => (seg < 90 ? "ahora mismo" : seg < 5400 ? `hace ${Math.round(seg / 60)} min` : seg < 129600 ? `hace ${Math.round(seg / 3600)} h` : `hace ${Math.round(seg / 86400)} días`);
const cifra = (v) => (v == null ? "—" : Math.abs(v) >= 100 || Number.isInteger(v) ? Math.round(v).toLocaleString("es-ES") : v.toLocaleString("es-ES", { maximumFractionDigits: 1 }));
const ahoraSeg = () => Math.floor(Date.now() / 1000);

/* ---------- Leer del resumen ---------- */
const finDatos = () => (R ? Math.min(R.hasta, Math.max(R.desde, ...Object.values(R.fuentes).map((f) => f.ultima || 0))) : 0);
function indice(bloque, t) {      // el último instante de la rejilla que no pasa de t
  if (!bloque) return -1;
  const i = Math.floor((t - bloque.t0) / bloque.paso);
  return i < 0 ? -1 : Math.min(i, bloque.n - 1);
}
function indicador(clave, t) {
  const c = R && R.indicadores.claves[clave], i = indice(R && R.indicadores, t);
  return c && i >= 0 ? { v: c.v[i], normal: c.normal ? c.normal[i] : null } : { v: null, normal: null };
}
/* Lo que marcaba el punto k de una serie en el momento t. En la web, mirando «ahora», vale lo recién pedido. */
function valor(serie, k, t) {
  const b = R.puntos[serie];
  if (vivoWeb && enDirecto && vivoWeb[serie]) { const v = vivoWeb[serie][b.ids[k]]; if (v != null) return v; }
  const i = indice(b, t);
  return i < 0 ? null : b.v[k][i];
}
/* En la web, mirando «ahora» con un histórico que ya tiene un rato: lo que no se puede pedir al momento es viejo. */
const atrasoWeb = () => (!servidor && enDirecto && R ? ahoraSeg() - finDatos() : 0);
const sucesoEn = (clave, t) => (R.sucesos || []).find((s) => s.clave === clave && s.desde - 900 <= t && t <= s.hasta + 900);

/* ====================== La consola ====================== */
const estilo = el("style", { textContent: `
  #boton-pulso { position: absolute; right: 10px; bottom: 228px; z-index: 800; display: inline-flex; align-items: center; gap: 7px; border: 1px solid var(--linea); background: var(--papel);
    color: var(--tinta); border-radius: 8px; padding: 8px 12px; font-weight: 600; box-shadow: 0 1px 3px rgba(23,36,46,.28); }
  #boton-pulso[aria-pressed=true] { background: #06131c; border-color: ${CIAN}; color: ${CIAN}; }
  #boton-pulso svg { flex: none; }
  #pulso { position: absolute; left: 10px; right: 10px; bottom: 10px; z-index: 795; display: grid; gap: 6px; padding: 9px 12px 10px; color: #dbeafe;
    background: rgba(5,12,19,.9); border: 1px solid rgba(34,211,238,.45); border-radius: 10px; box-shadow: 0 0 0 1px rgba(0,0,0,.5), 0 8px 30px rgba(0,0,0,.45);
    -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); font: 12px/1.3 ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
  #pulso[hidden] { display: none; }
  #pulso button { font: inherit; color: inherit; background: none; border: 1px solid rgba(148,163,184,.35); border-radius: 5px; padding: 3px 8px; cursor: pointer; white-space: nowrap; }
  #pulso button:hover { border-color: ${CIAN}; }
  #pulso button[aria-pressed=true] { background: rgba(34,211,238,.16); border-color: ${CIAN}; color: ${CIAN}; }
  #pulso .pz-fila { display: flex; align-items: center; gap: 6px; min-width: 0; }
  #pulso .pz-fila > * { flex: none; } #pulso .pz-fila > .pz-hueco { flex: 1 0 4px; }
  #pulso .pz-cabecera { flex-wrap: wrap; row-gap: 5px; }
  #pulso .pz-mas { flex: 1 1 auto; display: flex; flex-wrap: wrap; align-items: center; gap: 5px 6px; min-width: 0; } #pulso .pz-mas > * { flex: none; }
  #pulso .pz-mas > .pz-hueco { flex: 1 0 4px; }
  #pulso .pz-desliza { overflow-x: auto; scrollbar-width: none; } #pulso .pz-desliza::-webkit-scrollbar { display: none; }
  #pulso .pz-marca { letter-spacing: .14em; color: ${CIAN}; font-weight: 700; }
  #pulso .pz-reloj { font: 600 22px/1 "Barlow Condensed", ui-monospace, monospace; letter-spacing: .03em; color: #fff; white-space: nowrap; }
  #pulso .pz-modo { border: 1px solid; border-radius: 3px; padding: 1px 6px; font-size: 11px; letter-spacing: .08em; white-space: nowrap; }
  #pulso .pz-modo.pz-directo { color: ${LIMA}; } #pulso .pz-modo.pz-pasado { color: ${AMBAR}; } #pulso .pz-modo.pz-web { color: ${CIAN}; }
  #pulso .pz-modo.pz-directo::before { content: "● "; animation: pulso-late 1.6s infinite; }
  @keyframes pulso-late { 50% { opacity: .25; } }
  #pulso .pz-tejas { display: flex; gap: 6px; }
  #pulso .pz-teja { flex: none; display: grid; gap: 1px; text-align: left; padding: 5px 9px; min-width: 104px; border-color: rgba(148,163,184,.25); }
  #pulso .pz-teja b { font: 600 20px/1 "Barlow Condensed", ui-monospace, monospace; color: #fff; }
  #pulso .pz-teja small { font-size: 10.5px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px; }
  #pulso .pz-teja i { font-style: normal; font-size: 10.5px; color: #64748b; }
  #pulso .pz-teja i.pz-sube { color: ${AMBAR}; } #pulso .pz-teja i.pz-baja { color: ${CIAN}; }
  #pulso .pz-teja.pz-fuera { border-color: ${MAGENTA}; box-shadow: inset 0 0 0 1px ${MAGENTA}; } #pulso .pz-teja.pz-fuera i { color: ${MAGENTA}; }
  #pulso canvas { width: 100%; height: 74px; display: block; cursor: ew-resize; touch-action: none; border-radius: 4px; background: rgba(15,23,42,.6); }
  #pulso .pz-nota { color: #94a3b8; font-size: 11px; } #pulso .pz-nota b { color: #e2e8f0; font-weight: 600; }
  #pulso .pz-lista { max-height: 180px; overflow-y: auto; display: grid; gap: 3px; padding: 6px 0 2px; border-top: 1px solid rgba(148,163,184,.2); }
  #pulso .pz-lista button { text-align: left; border: 0; padding: 2px 4px; white-space: normal; } #pulso .pz-lista button:hover { color: ${CIAN}; }
  #pulso .pz-lista .pz-mal { color: ${ROJO}; } #pulso .pz-lista .pz-bien { color: ${LIMA}; }
  #pulso input[type=date] { font: inherit; color: #dbeafe; background: rgba(15,23,42,.8); border: 1px solid rgba(148,163,184,.35); border-radius: 5px; padding: 2px 4px; color-scheme: dark; }
  .pulso-rotulo { background: rgba(5,12,19,.85); border: 1px solid rgba(34,211,238,.5); color: #e0f2fe; font: 11px/1.2 ui-monospace, Menlo, Consolas, monospace; padding: 1px 5px; border-radius: 3px; box-shadow: none; white-space: nowrap; }
  .pulso-rotulo::before { display: none; }
  .pulso-avion { color: ${AMBAR}; filter: drop-shadow(0 0 3px rgba(251,191,36,.8)); }
  .pulso-ficha { font: 12px/1.4 ui-monospace, Menlo, Consolas, monospace; min-width: 200px; } .pulso-ficha b { font-size: 13px; } .pulso-ficha canvas { width: 100%; height: 60px; display: block; margin-top: 5px; }
  #mapa-zona.con-pulso :is(#cerca, #anadir, #boton-3d, #boton-pulso, #leyenda, #tarjeta-mapa, #aviso-capas) { margin-bottom: var(--alto-pulso, 0px); }
  #mapa-zona.con-pulso .leaflet-bottom { bottom: calc(var(--alto-pulso, 0px) + 4px); }
  #mapa-zona.en-3d :is(#pulso, #boton-pulso) { display: none; }
  @media (max-width: 760px) {
    #boton-pulso { right: 8px; bottom: 192px; padding: 11px; border-radius: 23px; min-width: 46px; justify-content: center; } #boton-pulso .rotulo { display: none; }
    #pulso { left: 6px; right: 6px; bottom: 18px; padding: 7px 8px 8px; gap: 5px; } #pulso canvas { height: 58px; } #pulso .pz-reloj { font-size: 18px; letter-spacing: 0; }
    #pulso .pz-marca, #pulso .pz-leyenda { display: none; } #pulso .pz-teja { min-width: 92px; padding: 4px 7px; } #pulso .pz-teja b { font-size: 18px; }
    #pulso .pz-cabecera { flex-wrap: wrap; } #pulso .pz-cabecera > .pz-reloj { flex: 1 1 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; } #pulso .pz-cabecera > button { padding: 5px 10px; }
    #pulso .pz-mas { order: 5; flex: 1 0 100%; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; } #pulso .pz-mas::-webkit-scrollbar { display: none; }
    #pulso .pz-mas > .pz-hueco { display: none; } #pulso .pz-nota:empty { display: none; }
    #mapa-zona.con-pulso .leaflet-bottom { display: none; }
    #panel.alta ~ #mapa-zona :is(#pulso, #boton-pulso) { display: none !important; }
  }` });
document.head.append(estilo);

const zona = document.getElementById("mapa-zona");
const boton = el("button", { id: "boton-pulso", type: "button", title: "Pulso: la ciudad a lo largo del tiempo" });
boton.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12h4l3-8 4 16 3-8h6"/></svg><span class="rotulo">Pulso</span>';
boton.setAttribute("aria-pressed", "false");
const consola = el("section", { id: "pulso", hidden: true });
consola.setAttribute("aria-label", "Pulso de la ciudad: línea de tiempo e indicadores");
zona.append(boton, consola);
L.DomEvent.disableClickPropagation(consola); L.DomEvent.disableScrollPropagation(consola);

const reloj = el("span", { className: "pz-reloj", textContent: "--:--" }), modo = el("span", { className: "pz-modo" });
const bPlay = el("button", { type: "button", title: "Reproducir o parar", textContent: "▶" });
const bVel = el("button", { type: "button", title: "Velocidad de la reproducción" });
const bAhora = el("button", { type: "button", textContent: "AHORA", title: "Volver al final de los datos" });
const bSucesos = el("button", { type: "button" }), bFuentes = el("button", { type: "button", textContent: "Leyenda y fuentes" });
const bFondo = el("button", { type: "button", textContent: "Fondo oscuro", title: "Poner el mapa oscuro mientras el pulso está abierto" });
const bCerrar = el("button", { type: "button", textContent: "✕", title: "Cerrar el pulso" });
const filaRangos = el("span", { className: "pz-fila" }), fecha = el("input", { type: "date", title: "Ir a un día concreto" });
const tejas = el("div", { className: "pz-tejas" }), lienzo = el("canvas"), nota = el("div", { className: "pz-nota" });
const filaCapas = el("div", { className: "pz-fila pz-desliza" }), lista = el("div", { className: "pz-lista", hidden: true });
consola.append(
  // En pantallas anchas todo cabe en una línea; en el móvil, lo de «mas» baja a una segunda línea que se desliza.
  el("div", { className: "pz-fila pz-cabecera" }, el("span", { className: "pz-marca", textContent: "PULSO" }), reloj, modo, bPlay,
    el("span", { className: "pz-mas" }, bVel, bAhora, el("span", { className: "pz-hueco" }), filaRangos, fecha, bSucesos, bFuentes, bFondo), bCerrar),
  el("div", { className: "pz-fila pz-desliza" }, tejas), lienzo, filaCapas, nota, lista);
/* La rueda del ratón sobre una fila la desliza de lado. */
for (const fila of consola.querySelectorAll(".pz-desliza")) fila.addEventListener("wheel", (ev) => { if (!ev.deltaX && fila.scrollWidth > fila.clientWidth) { fila.scrollLeft += ev.deltaY; ev.preventDefault(); } }, { passive: false });

/* ---------- Tejas: un indicador cada una ---------- */
function pintarTejas() {
  tejas.replaceChildren();
  if (!R) return;
  for (const clave of TEJAS) {
    const info = R.indicadores.claves[clave];
    if (!info) continue;
    let { v, normal } = indicador(clave, T), viejo = atrasoWeb() > 1200;
    if (vivoWeb && enDirecto && vivoWeb.indicadores[clave] != null) { v = vivoWeb.indicadores[clave]; viejo = false; }
    const teja = el("button", { type: "button", className: "pz-teja", title: `${info.nombre} (${info.unidad})${info.nota ? `: ${info.nota}` : ""}` });
    teja.setAttribute("aria-pressed", String(clave === ajustes.clave));
    let comparacion = el("i", { textContent: info.unidad });
    if (viejo) comparacion = el("i", { textContent: `dato de ${hace(atrasoWeb())}` });
    else if (v != null && normal != null && Math.abs(normal) > 0.5) {
      const d = Math.round(100 * (v - normal) / Math.abs(normal));
      if (d > 300) comparacion = el("i", { className: "pz-sube", textContent: `▲ ${cifra(v / normal)} veces lo normal` });
      else if (Math.abs(d) >= 8) comparacion = el("i", { className: d > 0 ? "pz-sube" : "pz-baja", textContent: `${d > 0 ? "▲ +" : "▼ "}${d} % sobre lo normal`.replace("▼ -", "▼ −") });
      else comparacion = el("i", { textContent: "como siempre a esta hora" });
    }
    if (!viejo && sucesoEn(clave, T)) teja.classList.add("pz-fuera");
    teja.append(el("small", { textContent: info.nombre }), el("b", { textContent: cifra(v) }), comparacion);
    teja.addEventListener("click", () => { ajustes.clave = clave; recordar(); pintarTejas(); pintarLinea(); });
    tejas.append(teja);
  }
}

/* ---------- La línea de tiempo ---------- */
const xDe = (t, ancho) => ((t - R.desde) / (R.hasta - R.desde)) * ancho;
function pintarLinea() {
  const ancho = lienzo.clientWidth, alto = lienzo.clientHeight, dpr = window.devicePixelRatio || 1;
  if (!ancho) return;
  if (lienzo.width !== Math.round(ancho * dpr)) { lienzo.width = Math.round(ancho * dpr); lienzo.height = Math.round(alto * dpr); }
  const c = lienzo.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, ancho, alto);
  if (!R) return;
  const info = R.indicadores.claves[ajustes.clave] || Object.values(R.indicadores.claves)[0];
  const { t0, paso, n } = R.indicadores, base = alto - 14;
  // Días y horas: una raya en cada medianoche y la hora cada tanto (según lo que quepa), sin pisar rótulos.
  const pxHora = ancho / ((R.hasta - R.desde) / 3600), cadaH = [1, 2, 3, 6, 12, 24, 168].find((h) => h * pxHora >= 38) || 168;
  c.font = "10px ui-monospace, Menlo, Consolas, monospace"; c.textBaseline = "bottom";
  const d0 = new Date(R.desde * 1000); d0.setMinutes(0, 0, 0);
  const rotulos = [];
  for (let t = d0.getTime() / 1000; t <= R.hasta; t += 3600) {
    const d = new Date(t * 1000), medianoche = d.getHours() === 0;
    if (t < R.desde || (!medianoche && (cadaH >= 24 || d.getHours() % cadaH)) || (cadaH === 168 && d.getDay() !== 1)) continue;
    const x = xDe(t, ancho);
    c.fillStyle = medianoche ? "rgba(148,163,184,.4)" : "rgba(148,163,184,.14)"; c.fillRect(Math.round(x), 0, 1, base);
    rotulos.push([x + 3, medianoche ? dia(t) : dos(d.getHours()), medianoche]);
  }
  const ocupado = [];
  c.fillStyle = "#64748b";
  for (const [x, texto, primero] of rotulos.filter((r) => r[2]).concat(rotulos.filter((r) => !r[2]))) {      // primero los días
    const fin = x + c.measureText(texto).width;
    if (fin > ancho || ocupado.some(([a0, b0]) => x < b0 + 8 && fin > a0 - 8)) continue;
    ocupado.push([x, fin]); c.fillText(texto, x, alto);
  }
  if (!info) return;
  // La escala: del mínimo al máximo de lo que se ve, contando lo normal.
  const todos = info.v.concat(info.normal || []).filter((x) => x != null);
  let min = Math.min(...todos), max = Math.max(...todos);
  if (!todos.length) { min = 0; max = 1; }
  if (max - min < 1e-6) { max += 1; min -= 1; }
  const yDe = (v) => 4 + (base - 8) * (1 - (v - min) / (max - min));
  const xi = (i) => xDe(t0 + (i + 0.5) * paso, ancho);
  // Huecos: los ratos sin dato de este indicador, rayados.
  c.fillStyle = "rgba(148,163,184,.09)";
  for (let i = 0, desde = -1; i <= n; i++) {
    const falta = i < n && info.v[i] == null;
    if (falta && desde < 0) desde = i;
    if (!falta && desde >= 0) { const a = Math.max(0, xDe(t0 + desde * paso, ancho)); c.fillRect(a, 0, Math.min(ancho, xDe(t0 + i * paso, ancho)) - a, base); desde = -1; }
  }
  const trazo = (valores, color, grosor, rayas) => {
    c.strokeStyle = color; c.lineWidth = grosor; c.setLineDash(rayas || []); c.beginPath();
    let seguido = false;
    valores.forEach((v, i) => { if (v == null) { seguido = false; return; } seguido ? c.lineTo(xi(i), yDe(v)) : c.moveTo(xi(i), yDe(v)); seguido = true; });
    c.stroke(); c.setLineDash([]);
  };
  if (info.normal) trazo(info.normal, "rgba(148,163,184,.75)", 1, [3, 3]);
  // Relleno bajo la curva y la curva.
  c.fillStyle = "rgba(34,211,238,.13)";
  for (let i = 0, a = -1; i <= n; i++) {
    const hay = i < n && info.v[i] != null;
    if (hay && a < 0) a = i;
    if (!hay && a >= 0) { c.beginPath(); c.moveTo(xi(a), base); for (let k = a; k < i; k++) c.lineTo(xi(k), yDe(info.v[k])); c.lineTo(xi(i - 1), base); c.fill(); a = -1; }
  }
  trazo(info.v, CIAN, 1.6);
  // Sucesos: lo que se salió de lo normal, en magenta (más vivo si es de este indicador).
  for (const s of R.sucesos || []) {
    const a = xDe(Math.max(s.desde - 450, R.desde), ancho), b = xDe(Math.min(s.hasta + 450, R.hasta), ancho);
    c.fillStyle = s.clave === ajustes.clave ? MAGENTA : "rgba(255,45,149,.4)"; c.fillRect(a, base, Math.max(3, b - a), 3);
  }
  c.fillStyle = "#94a3b8"; c.textBaseline = "top"; c.textAlign = "right";
  c.fillText(`${cifra(max)} ${info.unidad === "%" ? "%" : ""}`, ancho - 4, 3); c.textAlign = "left";
  // El cursor.
  const x = Math.max(1, Math.min(ancho - 1, xDe(T, ancho)));
  c.fillStyle = "#fff"; c.fillRect(Math.round(x) - 0.5, 0, 1.5, base + 3);
  c.beginPath(); c.moveTo(x - 5, 0); c.lineTo(x + 5, 0); c.lineTo(x, 6); c.fill();
}
function arrastrar(ev) {
  if (!R) return;
  const caja = lienzo.getBoundingClientRect(), f = Math.max(0, Math.min(1, (ev.clientX - caja.left) / caja.width));
  const t = R.desde + f * (R.hasta - R.desde), fin = finDatos();
  irA(Math.min(t, fin), t >= fin - (R.hasta - R.desde) * 0.012 && hastaFijo == null);
}
lienzo.addEventListener("pointerdown", (ev) => { lienzo.setPointerCapture(ev.pointerId); parar(); arrastrar(ev); });
lienzo.addEventListener("pointermove", (ev) => { if (lienzo.hasPointerCapture(ev.pointerId)) arrastrar(ev); });

/* ---------- Mover el tiempo ---------- */
function irA(t, directo = false) {
  T = Math.max(R.desde, Math.min(t, finDatos()));
  enDirecto = directo;
  pintarTodo();
}
function pintarCabecera() {
  if (!R) { reloj.textContent = "--:--"; return; }
  const visto = enDirecto && vivoWeb ? ahoraSeg() : T;
  reloj.textContent = `${dia(visto)} · ${hora(visto)}`;
  const atraso = ahoraSeg() - finDatos();
  if (!enDirecto) { modo.className = "pz-modo pz-pasado"; modo.textContent = "HISTÓRICO"; }
  else if (servidor && atraso < 900) { modo.className = "pz-modo pz-directo"; modo.textContent = "EN DIRECTO"; }
  else if (vivoWeb) { modo.className = "pz-modo pz-directo"; modo.textContent = "AHORA · WEB"; }
  else { modo.className = "pz-modo pz-web"; modo.textContent = `DATOS DE ${hace(atraso).toUpperCase()}`; }
  bPlay.textContent = reproduciendo ? "❚❚" : "▶";
  bAhora.setAttribute("aria-pressed", String(enDirecto));
}
function pintarNota() {
  if (!R) return;
  const partes = [];
  const atraso = ahoraSeg() - finDatos();
  if (!servidor) {
    partes.push(`Versión web: el histórico es lo que subió el ordenador <b>${hace(ahoraSeg() - R.generado)}</b> (las últimas 48 h).`);
    partes.push(vivoWeb ? "Bicis, aparcamientos y tráfico de ahora mismo se piden al Ayuntamiento." : "");
  } else if (atraso > 900) partes.push(`El recolector no está en marcha: lo último es de <b>${hace(atraso)}</b>. Se pone en marcha con <b>osintmaps servir --pulso</b>.`);
  const info = R.indicadores.claves[ajustes.clave];
  if (info && !info.normal) partes.push('<span class="pz-leyenda">Aún no hay días anteriores con los que comparar: «lo normal» aparece cuando se junte histórico.</span>');
  else if (info) partes.push('<span class="pz-leyenda">Línea de puntos: lo normal a esa hora. Rayado: sin datos (el programa estaba cerrado).</span>');
  nota.innerHTML = partes.filter(Boolean).join(" ");
}
function pintarTodo() { pintarCabecera(); pintarTejas(); pintarLinea(); pintarMapa(); }

function cuadro(ms) {
  if (!reproduciendo) return;
  const dt = Math.min(0.25, (ms - ultimoCuadro) / 1000); ultimoCuadro = ms;
  const fin = finDatos(), t = T + dt * VELOCIDADES[ajustes.velocidad][0];
  if (t >= fin) { reproduciendo = false; irA(fin, hastaFijo == null); return; }
  T = t; enDirecto = false; pintarCabecera(); pintarLinea(); pintarMapa(true);
  if (Math.floor(ms / 400) !== Math.floor((ms - dt * 1000) / 400)) pintarTejas();
  requestAnimationFrame(cuadro);
}
function parar() { if (reproduciendo) { reproduciendo = false; pintarCabecera(); pintarTejas(); } }
bPlay.addEventListener("click", () => {
  if (!R) return;
  if (reproduciendo) { parar(); return; }
  if (T >= finDatos() - 60) T = R.desde;         // al final: se empieza desde el principio
  reproduciendo = true; enDirecto = false; ultimoCuadro = performance.now(); requestAnimationFrame(cuadro);
});
const pintarVel = () => { bVel.textContent = VELOCIDADES[ajustes.velocidad][1]; };
bVel.addEventListener("click", () => { ajustes.velocidad = (ajustes.velocidad + 1) % VELOCIDADES.length; recordar(); pintarVel(); });
bAhora.addEventListener("click", () => { parar(); if (hastaFijo != null) { hastaFijo = null; fecha.value = ""; cargar(); } else if (R) irA(finDatos(), true); });

/* ====================== El mapa ====================== */
const lienzoMapa = (() => { mapa.createPane("pulso").style.zIndex = 430; mapa.createPane("pulso-rotulos").style.zIndex = 640; return L.canvas({ pane: "pulso", tolerance: 6 }); })();
const escala = () => Math.max(0.45, Math.min(1.7, 1 + (mapa.getZoom() - 14) * 0.2));
const mezcla = (a, b, f) => { const p = (h, i) => parseInt(h.slice(1 + 2 * i, 3 + 2 * i), 16); return `rgb(${[0, 1, 2].map((i) => Math.round(p(a, i) + (p(b, i) - p(a, i)) * f)).join(",")})`; };

/* Cada capa sabe crear sus piezas una vez (al cargar un resumen) y repintarlas para un momento. */
const PINTORES = {
  bicis: {
    crear: (b, k) => L.circleMarker([b.lat[k], b.lon[k]], { renderer: lienzoMapa, weight: 1, color: "#020617", fillOpacity: 0.92 }),
    pintar(pieza, b, k, t) {
      const v = valor("bicis", k, t), cap = (b.cap && b.cap[k]) || 20;
      if (v == null) return pieza.setStyle({ fillColor: GRIS, fillOpacity: 0.35, radius: 3 * escala() });
      const lleno = Math.min(1, v / cap);
      pieza.setStyle({ fillOpacity: 0.92, radius: (3 + Math.sqrt(cap) * 0.9) * escala(), fillColor: v === 0 ? ROJO : lleno >= 0.999 ? MAGENTA : mezcla("#fbbf24", "#22d3ee", lleno) });
    },
    texto: (b, k, t) => { const v = valor("bicis", k, t); return `${b.nombre[k] || "Valenbisi"}<br><b>${v == null ? "sin dato" : `${cifra(v)} bicis`}</b>${b.cap ? ` de ${b.cap[k]} anclajes` : ""}`; },
  },
  flujo: {      // cuánto han cambiado las bicis ancladas en la última media hora: llegan (cian) o se van (magenta)
    crear: (b, k) => L.circleMarker([b.lat[k], b.lon[k]], { renderer: lienzoMapa, weight: 1.5, fillOpacity: 0.3 }),
    cambio(k, t) { const a = valor("bicis", k, t), antes = (() => { const b = R.puntos.bicis, i = indice(b, t - 1800); return i < 0 ? null : b.v[k][i]; })(); return a == null || antes == null ? null : a - antes; },
    pintar(pieza, b, k, t) {
      const d = this.cambio(k, t);
      if (!d) return pieza.setStyle({ radius: 0, opacity: 0, fillOpacity: 0 });
      pieza.setStyle({ radius: (2 + Math.sqrt(Math.abs(d)) * 4.5) * escala(), opacity: 0.95, fillOpacity: 0.3, color: d > 0 ? CIAN : MAGENTA, fillColor: d > 0 ? CIAN : MAGENTA });
    },
    texto(b, k, t) { const d = this.cambio(k, t); return `${b.nombre[k] || "Valenbisi"}<br><b>${d == null ? "sin dato" : d > 0 ? `+${d} bicis en media hora: llega gente` : d < 0 ? `${d} bicis en media hora: se va gente` : "sin cambios en media hora"}</b>`; },
  },
  parking: {
    crear: (b, k) => L.circleMarker([b.lat[k], b.lon[k]], { renderer: lienzoMapa, weight: 2.5, fillOpacity: 0.85, fillColor: "#020617" }),
    pintar(pieza, b, k, t) {
      const v = valor("parking", k, t), cap = b.cap && b.cap[k];
      const ocupado = v == null || !cap ? null : 1 - Math.min(1, v / cap);
      pieza.setStyle({ radius: (5 + Math.sqrt(cap || 200) * 0.28) * escala(), color: ocupado == null ? GRIS : ocupado > 0.95 ? ROJO : ocupado > 0.8 ? AMBAR : LIMA });
    },
    texto: (b, k, t) => { const v = valor("parking", k, t); return `${b.nombre[k] || "Aparcamiento"}<br><b>${v == null ? "sin dato" : `${cifra(v)} plazas libres`}</b>${b.cap && b.cap[k] ? ` de ${cifra(b.cap[k])}` : ""}`; },
  },
  trafico: {
    crear: (b, k) => (b.geo && b.geo[k] ? L.polyline(b.geo[k], { renderer: lienzoMapa, lineCap: "round" }) : null),
    pintar(pieza, b, k, t) {
      const v = valor("trafico", k, t), z = escala();
      pieza.setStyle(v == null ? { color: GRIS, weight: 1.5 * z, opacity: 0.25, dashArray: null } : v === 0 ? { color: "#2dd4bf", weight: 2 * z, opacity: 0.45, dashArray: null }
        : v === 3 ? { color: "#e2e8f0", weight: 3 * z, opacity: 0.9, dashArray: "2 7" } : { color: v === 1 ? AMBAR : ROJO, weight: (v === 1 ? 4 : 5.5) * z, opacity: 0.95, dashArray: null });
    },
    texto: (b, k, t) => { const v = valor("trafico", k, t); return `${b.nombre[k] || "Tramo"}<br><b>${v == null ? "sin dato" : ESTADO_TRAFICO[v]}</b>`; },
  },
  aforo: {
    crear: (b, k) => L.circleMarker([b.lat[k], b.lon[k]], { renderer: lienzoMapa, stroke: false, fillColor: CIAN }),
    pintar(pieza, b, k, t) { const v = valor("aforo", k, t); pieza.setStyle({ radius: v == null ? 0 : (1.2 + Math.sqrt(v) * 0.22) * escala(), fillOpacity: v == null ? 0 : Math.min(0.75, 0.18 + v / 2500) }); },
    texto: (b, k, t) => { const v = valor("aforo", k, t); return `Punto de aforo ${b.ids[k]}<br><b>${v == null ? "sin dato" : `${cifra(v)} vehículos por hora`}</b>`; },
  },
  no2: {
    crear: (b, k) => L.circleMarker([b.lat[k], b.lon[k]], { renderer: lienzoMapa, weight: 2, fillOpacity: 0.25 }),
    pintar(pieza, b, k, t) { const v = valor("no2", k, t), color = v == null ? GRIS : v >= 100 ? ROJO : v >= 40 ? AMBAR : LIMA; pieza.setStyle({ radius: (v == null ? 6 : 8 + Math.sqrt(v) * 1.6) * escala(), color, fillColor: color }); },
    texto: (b, k, t) => { const v = valor("no2", k, t); return `${b.nombre[k] || "Estación"}<br><b>NO₂: ${v == null ? "sin dato" : `${cifra(v)} µg/m³`}</b>`; },
  },
};

function quitarCapa(id) { if (dibujadas[id]) { mapa.removeLayer(dibujadas[id].grupo); delete dibujadas[id]; } }
function crearCapa(capa) {
  quitarCapa(capa.id);
  if (!R || !ajustes.capas.includes(capa.id)) return;
  const grupo = L.layerGroup().addTo(mapa);
  if (capa.rastro) { dibujadas[capa.id] = { grupo, objetos: new Map() }; return; }
  const b = R.puntos[capa.serie], pintor = PINTORES[capa.id];
  if (!b) { dibujadas[capa.id] = { grupo, piezas: [] }; return; }
  const piezas = b.ids.map((_, k) => {
    const pieza = pintor.crear(b, k);
    if (!pieza) return null;
    pieza.bindTooltip(() => pintor.texto(b, k, T), { className: "pulso-rotulo", sticky: true, direction: "top", opacity: 1 });
    pieza.on("click", (ev) => { L.DomEvent.stop(ev); pieza.closeTooltip(); fichaDePunto(capa, b, k, ev.latlng); });
    return pieza.addTo(grupo);
  });
  dibujadas[capa.id] = { grupo, piezas, b };
}
/* Dónde estaba un objeto en el momento t, entre dos posiciones conocidas. */
function posicion(p, t) {
  let a = 0, z = p.length - 1;
  if (t < p[0][0] || t > p[z][0] + 90) return null;
  while (z - a > 1) { const m = (a + z) >> 1; p[m][0] <= t ? (a = m) : (z = m); }
  if (t >= p[z][0]) return { lat: p[z][1], lon: p[z][2], alt: p[z][3], rumbo: p[z][4], i: z };
  if (p[z][0] - p[a][0] > 420) return t - p[a][0] < 90 ? { lat: p[a][1], lon: p[a][2], alt: p[a][3], rumbo: p[a][4], i: a } : null;      // un hueco: no se inventa el camino
  const f = (t - p[a][0]) / (p[z][0] - p[a][0]);
  return { lat: p[a][1] + (p[z][1] - p[a][1]) * f, lon: p[a][2] + (p[z][2] - p[a][2]) * f, alt: p[a][3], rumbo: p[a][4] != null ? p[a][4] : null, i: a };
}
function pintarRastros(capa) {
  const d = dibujadas[capa.id], lista0 = (R.rastros && R.rastros[capa.rastro]) || [], avion = capa.id === "aviones", cola = avion ? 480 : 900;
  const vistos = new Set(), viejos = atrasoWeb() > 300;      // en la web, un avión de hace un rato ya no está ahí
  for (const o of lista0) {
    const pos = viejos ? null : posicion(o.p, T);
    if (!pos) continue;
    vistos.add(o.id);
    let pieza = d.objetos.get(o.id);
    if (!pieza) {
      pieza = { linea: L.polyline([], { renderer: lienzoMapa, color: avion ? AMBAR : LIMA, weight: avion ? 1.5 : 2.5, opacity: 0.75, interactive: false }).addTo(d.grupo) };
      pieza.cabeza = avion
        ? L.marker([pos.lat, pos.lon], { pane: "pulso-rotulos", icon: L.divIcon({ className: "pulso-avion", iconSize: [18, 18], iconAnchor: [9, 9], html: '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 2l2.6 8.2 7.4 4.3v2l-7.4-2.2-.9 4.9 2.3 1.6V22l-4-1.1L8 22v-1.2l2.3-1.6-.9-4.9L2 16.5v-2l7.4-4.3z"/></svg>' }) })
        : L.circleMarker([pos.lat, pos.lon], { renderer: lienzoMapa, radius: 5, weight: 2, color: "#020617", fillColor: LIMA, fillOpacity: 1 });
      pieza.cabeza.bindTooltip("", { className: "pulso-rotulo", direction: "right", offset: [8, 0], opacity: 1, permanent: avion && mapa.getZoom() >= 10 }).addTo(d.grupo);
      d.objetos.set(o.id, pieza);
    }
    const puntos = [];
    for (let i = pos.i; i >= 0 && o.p[i][0] >= T - cola; i--) puntos.unshift([o.p[i][1], o.p[i][2]]);
    puntos.push([pos.lat, pos.lon]);
    pieza.linea.setLatLngs(puntos);
    pieza.cabeza.setLatLng([pos.lat, pos.lon]);
    if (avion) {
      const svg = pieza.cabeza.getElement() && pieza.cabeza.getElement().firstChild;
      if (svg && pos.rumbo != null) svg.style.transform = `rotate(${pos.rumbo}deg)`;
      pieza.cabeza.setTooltipContent(`${o.nombre}${pos.alt != null ? ` · ${pos.alt === 0 ? "en tierra" : `${cifra(pos.alt)} m`}` : ""}`);
    } else pieza.cabeza.setTooltipContent(`Tren ${o.nombre}`);
  }
  for (const [id, pieza] of d.objetos) if (!vistos.has(id)) { d.grupo.removeLayer(pieza.linea); d.grupo.removeLayer(pieza.cabeza); d.objetos.delete(id); }
}
let ultimoPintado = {};
function pintarMapa(rapido = false) {
  if (!R) return;
  for (const capa of CAPAS_PULSO) {
    const d = dibujadas[capa.id];
    if (!d) continue;
    if (capa.rastro) { pintarRastros(capa); continue; }
    if (!d.b) continue;
    // Reproduciendo, los puntos fijos solo se repintan cuando cambia el instante de su rejilla.
    const i = `${indice(d.b, T)}|${capa.id === "flujo" ? indice(d.b, T - 1800) : ""}|${enDirecto && vivoWeb ? vivoWeb.t : ""}|${mapa.getZoom()}`;
    if (rapido && ultimoPintado[capa.id] === i) continue;
    ultimoPintado[capa.id] = i;
    d.piezas.forEach((pieza, k) => { if (pieza) PINTORES[capa.id].pintar(pieza, d.b, k, T); });
  }
}
mapa.on("zoomend", () => { if (R && !consola.hidden) { ultimoPintado = {}; pintarMapa(); } });

function pintarChips() {
  filaCapas.replaceChildren(el("span", { className: "pz-nota", textContent: "En el mapa:" }));
  for (const capa of CAPAS_PULSO) {
    const hay = R && (capa.rastro ? R.rastros && R.rastros[capa.rastro] : R.puntos[capa.serie]);
    const chip = el("button", { type: "button", textContent: capa.nombre, disabled: !hay, title: hay ? `${capa.nombre}: ${capa.leyenda}` : "Sin datos de esto en este rato" });
    chip.setAttribute("aria-pressed", String(ajustes.capas.includes(capa.id)));
    if (!hay) chip.style.opacity = 0.4;
    chip.addEventListener("click", () => {
      ajustes.capas = ajustes.capas.includes(capa.id) ? ajustes.capas.filter((x) => x !== capa.id) : ajustes.capas.concat(capa.id);
      recordar(); crearCapa(capa); ultimoPintado = {}; pintarMapa(); pintarChips();
    });
    filaCapas.append(chip);
  }
}

/* La historia de un punto: en el ordenador, la última semana; en la web, lo que trae el resumen. */
function fichaDePunto(capa, b, k, donde) {
  const caja = el("div", { className: "pulso-ficha" }), grafica = el("canvas"), pie = el("div", { textContent: "" });
  caja.innerHTML = PINTORES[capa.id].texto(b, k, T);
  caja.append(grafica, pie);
  L.popup({ maxWidth: 300 }).setLatLng(donde).setContent(caja).openOn(mapa);
  const dibujar = (puntos, desde, hasta) => {
    const ancho = grafica.clientWidth || 240, alto = 60, dpr = window.devicePixelRatio || 1;
    grafica.width = ancho * dpr; grafica.height = alto * dpr;
    const c = grafica.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const vs = puntos.map((p) => p[1]).filter((v) => v != null);
    if (!vs.length) { pie.textContent = "Sin historia de este punto."; return; }
    const max = Math.max(...vs, 1), x = (t) => ((t - desde) / (hasta - desde)) * ancho, y = (v) => alto - 3 - (alto - 8) * (v / max);
    c.strokeStyle = "#0891b2"; c.lineWidth = 1.5; c.beginPath();
    let antes = null;
    for (const [t, v] of puntos) {       // escalones: el valor vale hasta el siguiente cambio
      if (v == null) { antes = null; continue; }
      if (antes == null) c.moveTo(x(Math.max(t, desde)), y(v)); else { c.lineTo(x(t), y(antes)); c.lineTo(x(t), y(v)); }
      antes = v;
    }
    if (antes != null) c.lineTo(x(hasta), y(antes));
    c.stroke();
    c.fillStyle = "#e5007d"; c.fillRect(Math.max(0, Math.min(ancho - 1.5, x(T))), 0, 1.5, alto);
    pie.textContent = `${dia(desde)} ${hora(desde)} → ${dia(hasta)} ${hora(hasta)} · máximo ${cifra(max)}`;
  };
  const delResumen = () => dibujar(b.v[k].map((v, i) => [b.t0 + i * b.paso, v]), b.t0, b.t0 + (b.n - 1) * b.paso);
  if (!servidor) { delResumen(); return; }
  const hasta = Math.min(ahoraSeg(), Math.max(T + 86400, R.hasta)), desde = hasta - 7 * 86400;
  pedirJSON(`vivo/pulso/punto?serie=${capa.serie}&id=${encodeURIComponent(b.ids[k])}&desde=${desde}&hasta=${hasta}`)
    .then((j) => dibujar(j.cambios, Math.max(desde, j.cambios.length ? j.cambios[0][0] : desde), hasta)).catch(delResumen);
}

/* ====================== Sucesos y fuentes ====================== */
function abrirLista(cual) {
  const abierta = !lista.hidden && lista.dataset.cual === cual;
  lista.hidden = abierta; lista.dataset.cual = cual; lista.replaceChildren();
  bSucesos.setAttribute("aria-pressed", String(!abierta && cual === "sucesos")); bFuentes.setAttribute("aria-pressed", String(!abierta && cual === "fuentes"));
  if (abierta || !R) return;
  if (cual === "sucesos") {
    if (!(R.sucesos || []).length) lista.append(el("span", { className: "pz-nota", textContent: "Nada se ha salido de lo normal en este rato (o aún no hay histórico con el que comparar)." }));
    for (const s of R.sucesos || []) {
      const info = R.indicadores.claves[s.clave] || { nombre: s.clave, unidad: "" };
      const fila = el("button", { type: "button", textContent: `${dia(s.desde)} ${hora(s.desde)}${s.hasta - s.desde > 600 ? `–${hora(s.hasta)}` : ""} · ${info.nombre}: ${cifra(s.valor)} (lo normal, ${cifra(s.normal)})` });
      fila.addEventListener("click", () => { parar(); ajustes.clave = s.clave; recordar(); irA(s.desde, false); });
      lista.append(fila);
    }
  } else {
    const poner = (texto, clase) => lista.append(el("span", { className: clase || "pz-nota", textContent: texto }));
    // Primero, cómo se lee lo que está encendido en el mapa.
    for (const capa of CAPAS_PULSO) if (dibujadas[capa.id]) poner(`${capa.nombre}: ${capa.leyenda}.`);
    for (const [id, f] of Object.entries(R.fuentes)) {
      const viejo = ahoraSeg() - f.ultima;
      poner(`${viejo < 3 * f.cada + 300 ? "●" : "○"} ${f.nombre} (${f.origen}): última lectura ${hace(viejo)}; se pide cada ${f.cada < 120 ? `${f.cada} s` : `${Math.round(f.cada / 60)} min`}`, viejo < 3 * f.cada + 300 ? "pz-bien" : "pz-nota");
    }
    if (servidor) pedirJSON("vivo/pulso/estado").then((e) => {
      if (lista.hidden || lista.dataset.cual !== "fuentes") return;
      for (const f of e.fuentes) if (f.error && !f.ok) poner(`✕ ${f.nombre}: ${f.error}`, "pz-mal");
      poner(`Histórico desde ${e.desde ? `${dia(e.desde)} ${hora(e.desde)}` : "ahora"} · ${(e.bytes / 1048576).toLocaleString("es-ES", { maximumFractionDigits: 1 })} MB en datos/pulso.sqlite · ${e.en_marcha ? "recolector en marcha" : "recolector parado"}`);
      const p = e.publicacion;
      if (!p) poner("La web no se actualiza sola: arranca con --publicar-datos para que reciba los datos.");
      else if (p.resultado === "fallo") poner(`✕ No se pudo actualizar la web: ${p.error}`, "pz-mal");
      else poner(p.cuando ? `Web actualizada ${hace(ahoraSeg() - p.cuando)} (${Math.round(p.bytes / 1024)} KB); se repite cada ${p.cada_minutos} min.` : `La web recibirá los datos en un momento y luego cada ${p.cada_minutos} min.`, "pz-bien");
    }).catch(() => {});
    else poner(`Publicado ${hace(ahoraSeg() - R.generado)} desde el ordenador. Aviones y trenes solo se guardan mientras el programa está abierto.`);
  }
}
bSucesos.addEventListener("click", () => abrirLista("sucesos")); bFuentes.addEventListener("click", () => abrirLista("fuentes"));

/* ====================== Cargar ====================== */
function pintarRangos() {
  filaRangos.replaceChildren();
  filaRangos.hidden = fecha.hidden = !servidor;       // en la web hay lo que hay: 48 horas
  for (const [nombre, horas] of RANGOS) {
    const b = el("button", { type: "button", textContent: nombre });
    b.setAttribute("aria-pressed", String(hastaFijo == null && horasVistas === horas));
    b.addEventListener("click", () => { ajustes.horas = horas; hastaFijo = null; fecha.value = ""; recordar(); cargar(); });
    filaRangos.append(b);
  }
}
fecha.addEventListener("change", () => {
  if (!fecha.value) { hastaFijo = null; cargar(); return; }
  const d = new Date(`${fecha.value}T00:00:00`);
  hastaFijo = Math.min(ahoraSeg(), d.getTime() / 1000 + 86400); cargar(d.getTime() / 1000);
});

function recibir(resumen, mantener) {
  const seguia = enDirecto || !R;
  R = resumen;
  if (!mantener || seguia) { T = finDatos(); enDirecto = hastaFijo == null; } else T = Math.max(R.desde, Math.min(T, finDatos()));
  bSucesos.textContent = `Sucesos${(R.sucesos || []).length ? ` (${R.sucesos.length})` : ""}`;
  ultimoPintado = {};
  for (const capa of CAPAS_PULSO) if (!capa.rastro || !dibujadas[capa.id]) crearCapa(capa);
  pintarRangos(); pintarChips(); pintarNota(); pintarTodo();
  if (!lista.hidden) { const cual = lista.dataset.cual; lista.hidden = true; abrirLista(cual); }
}
function cargar(desdeFijo, mantener = false) {
  if (cargando) return Promise.resolve();
  cargando = true;
  if (!R) nota.textContent = "Cargando el pulso…";
  return hayServidor.then((si) => {
    servidor = si;
    if (!si) return pedirJSON(`${new URLSearchParams(location.search).get("datos") || "datos/"}pulso.json`);
    return pedirJSON("vivo/pulso/estado").then((e) => {
      if (!e.hay || !e.desde) throw new Error("sin histórico");
      // Con poco histórico (los primeros días) se enseña el rato más corto en el que cabe todo, no 48 horas casi vacías.
      const hasta = hastaFijo != null ? hastaFijo : ahoraSeg(), cabe = (RANGOS.find(([, h]) => h * 3600 >= hasta - e.desde) || RANGOS[RANGOS.length - 1])[1];
      horasVistas = Math.min(ajustes.horas, cabe);
      const desde = desdeFijo != null ? desdeFijo : hasta - horasVistas * 3600;
      return pedirJSON(`vivo/pulso/resumen?desde=${Math.round(desde)}&hasta=${Math.round(hasta)}${hasta - desde > 49 * 3600 ? "&rastros=0" : ""}`);
    });
  }).then((resumen) => {
    if (!resumen || resumen.v !== 1 || !resumen.indicadores) throw new Error("resumen no válido");
    recibir(resumen, mantener);
    if (!servidor) pedirVivoWeb();
  }).catch(() => {
    if (R) return;            // falló un refresco: se sigue con lo que había
    pintarRangos();
    nota.innerHTML = servidor
      ? "Aún no hay histórico. Arranca el programa con <b>osintmaps servir --pulso</b> (o con abrir-mapa.bat) y vuelve en unos minutos."
      : "Aún no se ha publicado el pulso en esta web. Lo sube el programa del ordenador cuando se abre con <b>--pulso --publicar-datos</b>.";
  }).finally(() => { cargando = false; });
}

/* En la web: lo de ahora mismo de lo que el navegador puede pedir solo (el geoportal de València lo permite). */
const pedirCapa = (servicio, campos) => fetch(`${GEOPORTAL}/${servicio.replace("/", "/MapServer/")}/query?where=1%3D1&outFields=${campos}&returnGeometry=false&resultRecordCount=2000&f=json`)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status)))).then((j) => (j.features || []).map((f) => f.attributes || {}));
function pedirVivoWeb() {
  if (servidor || !R || consola.hidden) return;
  const num = (x) => (x == null || x === "" || Number.isNaN(+x) ? null : +x);
  Promise.all([
    pedirCapa("Trafico/228", "number,available,free,total,open").catch(() => null),
    pedirCapa("Trafico/194", "id_aparcamiento,plazaslibr,plazastota").catch(() => null),
    pedirCapa("Trafico/192", "idtramo,estado").catch(() => null),
  ]).then(([bicis, parking, trafico]) => {
    if (!bicis && !parking && !trafico) return;
    const v = { t: ahoraSeg(), indicadores: {} };
    if (bicis) {
      v.bicis = {}; let ancladas = 0, anclajes = 0;
      for (const p of bicis) { const n = num(p.available); if (p.number == null || n == null || p.open === "F") continue; v.bicis[String(p.number)] = n; ancladas += n; anclajes += num(p.total) || n + (num(p.free) || 0); }
      if (anclajes) v.indicadores.bicis_fuera = Math.round(1000 * (1 - ancladas / anclajes)) / 10;
    }
    if (parking) {
      v.parking = {}; let libres = 0, plazas = 0;
      for (const p of parking) { const n = num(p.plazaslibr), t = num(p.plazastota); if (p.id_aparcamiento == null || n == null) continue; v.parking[String(p.id_aparcamiento)] = n; if (t) { libres += Math.min(n, t); plazas += t; } }
      if (plazas) v.indicadores.parking_ocupacion = Math.round(1000 * (1 - libres / plazas)) / 10;
    }
    if (trafico) {
      v.trafico = {}; let suma = 0, abiertos = 0;
      for (const p of trafico) { let n = num(p.estado); if (p.idtramo == null || n == null) continue; if (n >= 5 && n <= 8) n -= 5; if (n < 0 || n > 3) continue; v.trafico[String(p.idtramo)] = n; if (n < 3) { suma += n; abiertos++; } }
      if (abiertos) v.indicadores.trafico_indice = Math.round(1000 * suma / (2 * abiertos)) / 10;
    }
    vivoWeb = v;
    if (enDirecto) { ultimoPintado = {}; pintarTodo(); }
    pintarNota();
  });
}

/* ====================== Abrir y cerrar ====================== */
const medir = new ResizeObserver(() => { zona.style.setProperty("--alto-pulso", `${consola.offsetHeight + 12}px`); pintarLinea(); });
function abrir() {
  consola.hidden = false; zona.classList.add("con-pulso"); boton.setAttribute("aria-pressed", "true");
  medir.observe(consola);
  // En el móvil la hoja de abajo se pliega: el mapa y la consola necesitan el sitio.
  if (matchMedia("(max-width: 760px)").matches && typeof ponerHoja === "function") ponerHoja("minima");
  ponerFondo();
  ajustes.abierto = true; recordar(); pintarVel();
  cargar().then(() => { for (const capa of CAPAS_PULSO) crearCapa(capa); ultimoPintado = {}; pintarMapa(); });
  clearInterval(relojDirecto);
  // Mirando «ahora», se vuelve a pedir cada minuto (en la web, lo que el navegador puede pedir solo, cada dos).
  relojDirecto = setInterval(() => {
    if (consola.hidden || document.hidden || reproduciendo) return;
    if (servidor) { if (enDirecto && hastaFijo == null) cargar(undefined, true); }
    else { pedirVivoWeb(); if (ahoraSeg() - R?.generado > 1200) cargar(undefined, true); }
    pintarCabecera();
  }, 60000);
}
function cerrar() {
  parar(); consola.hidden = true; zona.classList.remove("con-pulso"); boton.setAttribute("aria-pressed", "false");
  zona.style.removeProperty("--alto-pulso"); medir.disconnect(); clearInterval(relojDirecto);
  for (const capa of CAPAS_PULSO) quitarCapa(capa.id);
  quitarFondo(); mapa.closePopup();
  ajustes.abierto = false; recordar();
}
/* El mapa oscuro mientras el pulso está abierto; al cerrar vuelve el fondo que había. */
const selector = document.getElementById("capa-fondo");
function ponerFondo() {
  bFondo.setAttribute("aria-pressed", String(!!ajustes.fondo));
  const oscuro = selector && [...selector.options].find((o) => o.value === "gris_oscuro");
  bFondo.hidden = !oscuro;
  if (!oscuro || !ajustes.fondo || selector.value === "gris_oscuro") return;
  // El visor recuerda el fondo elegido: se apunta cuál había para devolverlo aunque se cierre la página con el pulso abierto.
  ajustes.fondoAnterior = selector.value; recordar();
  selector.value = "gris_oscuro"; selector.dispatchEvent(new Event("change"));
}
function quitarFondo() {
  if (!ajustes.fondoAnterior || !selector) return;
  if (selector.value === "gris_oscuro") { selector.value = ajustes.fondoAnterior; selector.dispatchEvent(new Event("change")); }
  delete ajustes.fondoAnterior; recordar();
}
bFondo.addEventListener("click", () => { ajustes.fondo = !ajustes.fondo; recordar(); ajustes.fondo ? ponerFondo() : (quitarFondo(), bFondo.setAttribute("aria-pressed", "false")); });
boton.addEventListener("click", () => (consola.hidden ? abrir() : cerrar()));
bCerrar.addEventListener("click", cerrar);
document.addEventListener("keydown", (ev) => {
  if (consola.hidden || !R || /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || "")) return;
  if (ev.key === " " && consola.contains(document.activeElement)) { ev.preventDefault(); bPlay.click(); }
  else if ((ev.key === "," || ev.key === ".") && !ev.ctrlKey && !ev.metaKey) { parar(); irA(T + (ev.key === "." ? 1 : -1) * R.indicadores.paso, false); }
});
window.OSINT_PULSO = { abrir, cerrar, estado: () => ({ R, T, enDirecto, servidor, vivoWeb, capas: Object.keys(dibujadas) }) };
// Si estaba abierto la última vez, o la dirección lleva «?pulso», se abre solo.
if (ajustes.abierto || new URLSearchParams(location.search).has("pulso")) setTimeout(abrir, 0);
})();
