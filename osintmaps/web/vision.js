/* OSINT Maps: lo que se ve de cada sitio en la foto aérea.

   Un programa aparte (experimentos/vision) recorre los candidatos y, para cada uno, mira la
   foto de 15 cm de 2025 (en color y en infrarrojo) y la maqueta 3D del ICV. Con un detector
   entrenado en la tarjeta gráfica busca caminos, sendas, muros, vallas y setos; con la altura y
   el infrarrojo dice si queda algo en pie y cuánta vegetación hay dentro. Deja dos cosas en la
   carpeta de datos:

   - revision.json: un resumen por sitio y lo que acertó el detector cuando se le examinó.
   - vision/<id>.json: las líneas detectadas alrededor de ese sitio, para pintarlas en el mapa.

   Aquí solo se enseña: un bloque en la ficha y las líneas sobre el mapa. Si esos ficheros no
   están, este trozo no hace nada. Todo lo que sale de aquí lo ha decidido un programa: es una
   pista para mirar la foto con más intención, no un dato comprobado. */

/* Cómo se pinta cada clase. Sobre una foto aérea un color solo no basta (un seto verde sobre
   un campo verde no se ve), así que cada línea lleva debajo un borde oscuro; y como dos colores
   se pueden confundir, las vallas, los caminos y las sendas van además a trazos distintos. */
const CLASES_VISION = {
  muro: { nombre: "Muro", color: "#ff7a33", trazo: null },
  valla: { nombre: "Valla", color: "#ffd91a", trazo: "7 6" },
  seto: { nombre: "Seto", color: "#63e08c", trazo: null },
  camino: { nombre: "Camino", color: "#ffffff", trazo: "13 7" },
  senda: { nombre: "Senda", color: "#6fd6ff", trazo: "2 7" },
};
const ESTADO_VISION = {
  solar: "Sin nada en pie",
  vegetacion: "Tapado por árboles o maleza",
  ruina_vegetacion: "En pie, con vegetación dentro",
  tejado: "En pie y con cubierta",
  ruina: "En pie a medias o sin cubierta clara",
};

const baseVision = new URLSearchParams(location.search).get("datos") || "datos/";
let revisionAerea = null;                // el resumen de todos los sitios, cuando llega
let fichaVision = null;               // { c, caja }: el bloque de la ficha abierta, por si el resumen llega después
let visionDe = null;                  // id del sitio cuyas líneas están (o van a estar) en el mapa
let lineasVision = [];                // esas líneas, ya descifradas: [{ clase, puntos: [[lat, lon], …] }]
let versionVision = 0;                // sube cada vez que cambian: así se entera la vista 3D
const lineasPorSitio = new Map();         // id → promesa con las líneas de ese sitio (se piden una vez)
const quiereVision = () => leerLocal("osintmaps.vision.v1", true) !== false;

// Las líneas van en su propio panel: por encima de los contornos, por debajo de los puntos, y sin recibir clics.
const panelVision = mapa.createPane("vision");
panelVision.style.zIndex = 360;
panelVision.style.pointerEvents = "none";
const lienzoVision = L.canvas({ padding: 0.3, pane: "vision" });
const capaVision = L.layerGroup().addTo(mapa);

/* El resumen se pide al arrancar, sin esperar a nadie ni hacer esperar: si no existe, no pasa nada.
   En el fichero autónomo de «osintmaps paquete» va dentro (y las líneas no van: pesan demasiado). */
const cuandoVision = window.OSINT_REVISION ? Promise.resolve(window.OSINT_REVISION)
  : window.OSINT_DATOS || !/^https?:$/.test(location.protocol) ? Promise.resolve(null)
  : pedirJSON(`${baseVision}revision.json`).catch(() => null);
cuandoVision.then((r) => {
  revisionAerea = r && r.sitios ? r : null;
  if (!revisionAerea) return;
  if (fichaVision) rellenarVision(fichaVision.c, fichaVision.caja);
  pintarVision();
  // Ya se puede filtrar por lo visto desde el aire y decirlo en la lista. Con una ficha abierta la lista
  // no se toca (para que «siguiente» no cambie): se rehará al volver a ella.
  if (Object.values(revisionAerea.sitios).some((s) => s.estado)) document.getElementById("fila-vision").hidden = false;
  if (!seleccion && typeof filtrar === "function" && candidatos.length) filtrar();
});

/* Para el filtro «Desde el aire» y para la lista. De un sitio sin veredicto no se sabe nada:
   «ocultar lo derribado» lo deja pasar y los «solo…» no. */
const estadoVision = (c) => (revisionAerea && revisionAerea.sitios[c.id] ? revisionAerea.sitios[c.id].estado : null) || null;
function pasaVision(c, modo) {
  const e = estadoVision(c);
  if (modo === "no-solar") return e !== "solar";
  if (modo === "solar") return e === "solar";
  if (modo === "tejado") return e === "tejado";
  if (modo === "ruina") return e === "ruina" || e === "ruina_vegetacion";
  return true;
}
const ETIQUETA_VISION = { solar: "sin nada en pie", vegetacion: "tapado por vegetación", ruina_vegetacion: "en pie, con vegetación", tejado: "en pie, con cubierta", ruina: "en pie a medias" };
const etiquetaVision = (c) => ETIQUETA_VISION[estadoVision(c)] || "";

/* Las líneas de un sitio vienen en poco sitio: cada coordenada en millonésimas de grado contadas
   desde el centro, y cada punto como salto desde el anterior (ver compacto() en detectar.py). */
function descifrarVision(j) {
  const salida = [], [lon0, lat0] = j.o || [0, 0];
  for (const [clase, , saltos] of j.l || []) {
    if (!CLASES_VISION[clase]) continue;
    const puntos = [];
    let x = 0, y = 0;
    for (let k = 0; k + 1 < saltos.length; k += 2) { x += saltos[k]; y += saltos[k + 1]; puntos.push([lat0 + y / 1e6, lon0 + x / 1e6]); }
    if (puntos.length > 1) salida.push({ clase, puntos });
  }
  return salida;
}
function lineasDelSitio(id) {
  if (!lineasPorSitio.has(id)) {
    const p = window.OSINT_DATOS ? Promise.resolve([]) : pedirJSON(`${baseVision}vision/${encodeURIComponent(id)}.json`).then(descifrarVision);
    p.catch(() => lineasPorSitio.delete(id));           // si falla (sin cobertura), que se pueda volver a pedir
    lineasPorSitio.set(id, p);
  }
  return lineasPorSitio.get(id);
}

/* Pinta en el mapa las líneas del sitio de la ficha abierta, si las hay y están encendidas.
   Se llama cada vez que se repintan los contornos: si no ha cambiado el sitio, no hace nada. */
function pintarVision() {
  const s = revisionAerea && seleccion && quiereVision() ? revisionAerea.sitios[seleccion.id] : null;
  const c = s && Object.keys(s.largo_m || {}).length ? seleccion : null;        // si el resumen dice que no hay líneas, ni se piden
  const id = c ? c.id : null;
  if (id === visionDe) return;
  visionDe = id;
  capaVision.clearLayers();
  if (lineasVision.length) { lineasVision = []; versionVision++; }
  if (!c) return;
  lineasDelSitio(id).then((lineas) => {
    if (visionDe !== id) return;                     // mientras llegaban se ha abierto otro sitio
    lineasVision = lineas;
    versionVision++;
    // Una sola pieza por clase (y otra para su borde): pintar cien trozos sueltos se nota al mover el mapa.
    for (const [clase, estilo] of Object.entries(CLASES_VISION)) {
      const trozos = lineas.filter((l) => l.clase === clase).map((l) => l.puntos);
      if (!trozos.length) continue;
      const comun = { renderer: lienzoVision, pane: "vision", interactive: false, lineCap: "round", lineJoin: "round" };
      L.polyline(trozos, { ...comun, color: "#10181d", weight: 5.5, opacity: 0.6 }).addTo(capaVision);
      L.polyline(trozos, { ...comun, color: estilo.color, weight: 3, opacity: 0.95, dashArray: estilo.trazo, lineCap: estilo.trazo ? "butt" : "round" }).addTo(capaVision);
    }
  }).catch(() => { if (visionDe === id) visionDe = null; });
}

/* Para la vista 3D: las mismas líneas, como las quiere MapLibre. */
function lineasVision3D() {
  return { type: "FeatureCollection", features: lineasVision.map((l) => ({ type: "Feature",
    geometry: { type: "LineString", coordinates: l.puntos.map(([lat, lon]) => [lon, lat]) }, properties: { color: CLASES_VISION[l.clase].color } })) };
}

const muestraVision = (estilo) => {
  // Un trocito de línea con el mismo color y el mismo trazo que en el mapa.
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 30 8"); svg.setAttribute("aria-hidden", "true");
  const raya = document.createElementNS("http://www.w3.org/2000/svg", "line");
  for (const [k, v] of Object.entries({ x1: 2, y1: 4, x2: 28, y2: 4, stroke: estilo.color, "stroke-width": 3, "stroke-linecap": estilo.trazo ? "butt" : "round" })) raya.setAttribute(k, v);
  if (estilo.trazo) raya.setAttribute("stroke-dasharray", estilo.trazo);
  svg.append(raya);
  return svg;
};
const enPorCiento = (n) => `${Math.round(n)} %`;
const enMetros = (n) => `${String(Math.round(n * 10) / 10).replace(".", ",")} m`;

/* El bloque de la ficha. Devuelve siempre una caja: vacía y escondida si de ese sitio no se sabe nada (todavía). */
function bloqueVision(c) {
  const caja = el("section", { className: "bloque vision", hidden: true });
  fichaVision = { c, caja };
  if (revisionAerea) rellenarVision(c, caja);
  return caja;
}
function rellenarVision(c, caja) {
  const s = revisionAerea.sitios[c.id];
  if (!s) return;
  const partes = [el("h3", { textContent: `Visto desde el aire (foto de ${revisionAerea.vuelo || "2025"})` })];
  if (ESTADO_VISION[s.estado]) partes.push(el("p", { className: "veredicto", textContent: ESTADO_VISION[s.estado] }));

  const datos = el("dl", { className: "datos" });
  const dato = (k, v) => datos.append(el("dt", { textContent: k }), el("dd", { textContent: v }));
  // La altura sale de la maqueta 3D, que no distingue una pared de la copa de un árbol: se dice.
  if (s.en_pie_pct != null) dato("Levanta más de 2,5 m", `${enPorCiento(s.en_pie_pct)} de la planta, árboles incluidos` + (s.altura_m != null && s.en_pie_pct >= 15 ? `; altura, ${enMetros(s.altura_m)}` : ""));
  if (s.vegetacion_pct != null) dato("Vegetación dentro", enPorCiento(s.vegetacion_pct));
  if (s.cerrado_pct != null) dato("Cierre", s.cerrado_pct ? `muro, valla o seto en ${s.cerrado_pct} de cada 100 direcciones` : "no se ve ninguno alrededor");
  if (s.accesos != null) dato("Accesos", s.accesos ? `${s.accesos === 1 ? "llega 1 camino o senda" : `llegan ${s.accesos} caminos o sendas`} a menos de 20 m` : "no se ve ningún camino a menos de 20 m");
  if (datos.children.length) partes.push(datos);

  // Lo detectado alrededor: sirve de leyenda de lo que se pinta en el mapa.
  const largos = s.largo_m || {}, leyenda = el("ul", { className: "leyenda-vision" });
  for (const [clase, estilo] of Object.entries(CLASES_VISION)) {
    if (largos[clase]) leyenda.append(el("li", {}, muestraVision(estilo), el("span", { textContent: `${estilo.nombre}, ${miles(largos[clase])} m` })));
  }
  if (leyenda.children.length) {
    partes.push(el("p", { className: "sub-vision", textContent: `Detectado a ${revisionAerea.radio_m || 150} m a la redonda:` }), leyenda);
    if (!window.OSINT_DATOS) {
      const ver = el("button", { id: "ver-vision", type: "button", textContent: "Verlo sobre el mapa" });
      ver.setAttribute("aria-pressed", String(quiereVision()));
      ver.addEventListener("click", () => {
        const si = !quiereVision();
        guardarLocal("osintmaps.vision.v1", si);
        ver.setAttribute("aria-pressed", String(si));
        pintarVision();
      });
      partes.push(ver);
    }
  } else partes.push(el("p", { className: "sub-vision", textContent: "No se ha detectado ningún camino, muro ni valla alrededor." }));

  // Cuánto fiarse: lo que acertó el detector en zonas que no vio al aprender.
  const fiab = Object.entries(revisionAerea.fiabilidad || {}).filter(([clase]) => CLASES_VISION[clase]);
  const aviso = el("details", { className: "fiar-vision" }, el("summary", { textContent: "Cuánto fiarse de esto" }));
  aviso.append(el("p", { textContent: "Lo saca un programa mirando la foto y la maqueta 3D, y se equivoca: confunde bordes de bancal con muros, no ve las vallas de alambre fino y pierde los caminos bajo los árboles. Úsalo para saber dónde mirar." }));
  if (fiab.length) {
    aviso.append(el("p", { textContent: "Examinado con lo que hay dibujado en OpenStreetMap en zonas que no había visto (de cada 100 que marca, cuántos coinciden; y de cada 100 que hay dibujados, cuántos encuentra):" }));
    aviso.append(el("ul", {}, ...fiab.map(([clase, f]) => el("li", { textContent: `${CLASES_VISION[clase].nombre}: coinciden ${f.precision}, encuentra ${f.alcance}.` }))));
    aviso.append(el("p", { textContent: "En OpenStreetMap faltan muchos muros y vallas, así que parte de lo que cuenta como fallo es real y no está dibujado." }));
  }
  if (s.estado) aviso.append(el("p", { textContent: "Lo de si queda algo en pie sale de la altura de la maqueta 3D y de una regla ajustada con pocos sitios: un patio con plantas cuenta como vegetación dentro y un árbol cuenta como algo en pie. Tómalo como una primera criba." }));
  partes.push(aviso);

  caja.replaceChildren(...partes);
  caja.hidden = false;
}
