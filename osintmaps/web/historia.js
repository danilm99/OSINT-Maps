"use strict";
/* OSINT Maps: la historia de un sitio.

   Al abrir la ficha de un sitio (o de cualquier edificio o punto del mapa) este trozo junta lo
   que se sabe de su pasado, en dos tiempos:

   1. Al momento y sin red, lo que ya está en los datos: el año de Catastro, las etiquetas de
      OpenStreetMap (qué fue, desde cuándo), si figura en la Lista Roja o sale a subasta, el año
      en que deja de verse el tejado en las fotos aéreas y las noticias que el programa buscó en
      su día («osintmaps historia» las deja en datos/historia.json).
   2. Al pulsar «Buscar su historia», lo que contestan los servicios abiertos que dejan que una
      página web les pregunte, sin cuenta ni clave:
      - Wikidata: la ficha del sitio (fechas, protección, estado) y qué hay catalogado alrededor.
      - Wikipedia, en castellano o en valenciano: el arranque del artículo.
      - Wikimedia Commons: fotos de alrededor, con su año.
      - Topónimos: el Nomenclátor del IGN, el Nomenclàtor Toponímic Valencià (ICV) y los nombres
        de OpenStreetMap. Una ruina sin nombre en Catastro lo tiene muchas veces en el mapa.
      - Catastro: dirección o paraje y para qué consta cada construcción.

   Lo que una página NO puede hacer es buscar en Google Noticias ni en las hemerotecas: no
   admiten preguntas de otra web. Para eso están las noticias guardadas, la búsqueda al momento
   (solo con «osintmaps servir» detrás, que pregunta por la página) y los enlaces de «Seguir
   buscando», que abren la búsqueda ya escrita en cada portal.

   El resumen no lo redacta nadie: se monta con frases hechas sobre los datos encontrados y cada
   dato dice de dónde sale. Si ninguna fuente dice cuándo se abandonó, se dice que no consta.
   Los textos vienen de fuentes que edita cualquiera: siempre se ponen como texto, nunca como HTML. */

const baseHistoria = new URLSearchParams(location.search).get("datos") || "datos/";
const VERSION_HISTORIA = 1;                    // cambia si cambia la forma de lo que se guarda
const VIDA_HISTORIA = 14 * DIA;                // lo buscado en internet vale dos semanas
const historiasVistas = new Map();             // id del sujeto → lo encontrado, mientras la página siga abierta
let prensaGuardada = null;                     // datos/historia.json: { sitios: { id: { consulta, consultado, noticias } } }
let fichaHistoria = null;                      // el bloque que hay en la ficha abierta: { s, caja, r, parcial, buscando, esperando }
const quiereHistoriaSola = () => !!(leerLocal("osintmaps.historia.v1", null) || {}).sola;

/* Las noticias guardadas se piden al arrancar, sin hacer esperar a nadie: si no están, no pasa nada.
   En el fichero autónomo de «osintmaps paquete» van dentro. */
const cuandoPrensa = window.OSINT_HISTORIA ? Promise.resolve(window.OSINT_HISTORIA)
  : window.OSINT_DATOS || !/^https?:$/.test(location.protocol) ? Promise.resolve(null)
  : pedirJSON(`${baseHistoria}historia.json`).catch(() => null);
cuandoPrensa.then((j) => {
  prensaGuardada = j && j.sitios ? j : null;
  if (prensaGuardada && fichaHistoria && document.body.contains(fichaHistoria.caja)) pintarHistoria();
});

/* ====================== 1. De quién se cuenta la historia ======================
   Un «sujeto» es lo mínimo que hace falta saber de un sitio para buscarle el pasado, venga de la
   lista de sitios o de cualquier capa: dónde está, cómo se llama (si se llama), su referencia
   catastral y las etiquetas de OpenStreetMap que traiga. */
const CAPAS_CON_NOMBRE_PROPIO = new Set(["listaroja", "wikipedia", "bic", "refugios", "lugar"]);
const GRUPOS_CON_HISTORIA = new Set(["Abandono y patrimonio", "Catastro", "Infraestructura"]);
const CAPAS_SIN_HISTORIA = new Set(["farolas", "muros"]);
const tieneHistoria = (e) => e.capa === "punto" || e.capa === "lugar" || e.capa === "wikipedia"
  || (!!CAPA[e.capa] && GRUPOS_CON_HISTORIA.has(CAPA[e.capa].grupo) && !CAPAS_SIN_HISTORIA.has(e.capa));
const soloQ = (t) => (/^Q\d+$/.test(t || "") ? t : "");

function sujetoDeSitio(c) {
  const p = c.p;
  return { id: `sitio|${c.id}`, clave: String(c.id), sitio: c, lat: c.lat, lon: c.lon, nombre: p.nombre || "", municipio: p.municipio || "", refcat: (p.refcats || [])[0] || "",
    anio: +p.anio || null, superficie: +p.superficie_m2 || 0, etiquetas: p.etiquetas || null, wikidata: soloQ(p.wikidata), wikipedia: p.wikipedia || "", abandonado: true,
    estado: NOMBRE_ESTADO[p.estado] || "", fuentes: p.fuentes || [] };
}
function sujetoDeElemento(e) {
  const t = e.etiquetas || null, p = e.p || {};
  const fila = (e.datos || []).find(([k]) => k === "Año de construcción" || k === "Construido en");
  return { id: String(e.id), clave: "", elemento: e, lat: e.lat, lon: e.lon,
    nombre: t ? t.name || t["name:es"] || t["name:ca"] || "" : CAPAS_CON_NOMBRE_PROPIO.has(e.capa) ? e.nombre || "" : "",
    municipio: "", refcat: e.refcat || p.refcat || "", anio: +p.anio || (fila ? +fila[1] : 0) || null, superficie: +e.superficie || +p.superficie || 0, etiquetas: t,
    wikidata: soloQ(t && t.wikidata), wikipedia: (t && t.wikipedia) || (e.capa === "wikipedia" && e.nombre ? `es:${e.nombre}` : ""), conArticulo: e.capa === "wikipedia",
    abandonado: /^(posibles|abandonado|listaroja)$/.test(e.capa) || /^(ruin|declined)$/.test(e.estado_edificio || ""), estado: "", fuentes: [] };
}
const radioDelSujeto = (s) => Math.sqrt((s.superficie || 400) / Math.PI);
const municipioCorto = (m) => String(m || "").split(" / ")[0].trim();      // «Sagunt / Sagunto» → «Sagunt»
const enLaComunitat = (s) => s.lat > COMUNITAT.s && s.lat < COMUNITAT.n && s.lon > COMUNITAT.o && s.lon < COMUNITAT.e;

/* --- Fechas ---
   Cada fecha se guarda con tres cosas: «orden» (un número para ponerlas en fila), «texto» (cómo se
   enseña en la cronología) y «frase» (cómo entra en una oración: «en 1889», «en el siglo XV»). */
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
function romano(n) {
  let s = "";
  for (const [v, r] of [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]]) while (n >= v) { s += r; n -= v; }
  return s;
}
const fechaDeAnio = (a, hacia) => ({ orden: a, texto: `${hacia ? "hacia " : ""}${a}`, frase: `${hacia ? "hacia" : "en"} ${a}` });
const fechaDeSiglo = (siglo, antes) => ({ orden: (antes ? -siglo : siglo - 1) * 100 + 50, texto: `siglo ${romano(siglo)}${antes ? " a. C." : ""}`, frase: `en el siglo ${romano(siglo)}${antes ? " a. C." : ""}` });
/* Wikidata da cada fecha con su precisión: 7 es «el siglo», 8 «la década», 9 «el año», 10 «el mes» y 11 «el día». */
function fechaWikidata(v) {
  const m = /^([+-])(\d+)-(\d\d)-(\d\d)/.exec((v && v.time) || "");
  if (!m) return null;
  const anio = +m[2], antes = m[1] === "-", p = v.precision;
  if (!anio || p < 7) return null;
  if (p === 7) return fechaDeSiglo(Math.ceil(anio / 100), antes);
  if (antes) return { orden: -anio, texto: `${anio} a. C.`, frase: `en el ${anio} a. C.` };
  if (p === 8) { const d = Math.floor(anio / 10) * 10; return { orden: d + 5, texto: `década de ${d}`, frase: `en la década de ${d}` }; }
  if (p === 9 || !+m[3]) return fechaDeAnio(anio);
  const mes = MESES[+m[3] - 1];
  if (p === 10 || !+m[4]) return { orden: anio + (+m[3] - 1) / 12, texto: `${mes} de ${anio}`, frase: `en ${mes} de ${anio}` };
  return { orden: anio + (+m[3] - 1) / 12 + +m[4] / 400, texto: `${+m[4]} de ${mes} de ${anio}`, frase: `el ${+m[4]} de ${mes} de ${anio}` };
}
/* En OpenStreetMap una fecha puede ser «1920», «1920-05», «~1850», «C19» o «before 1900». */
function fechaOSM(v) {
  const t = String(v || "").trim();
  let m = /^(~)?(\d{4})(?:-(\d\d))?(?:-\d\d)?$/.exec(t);
  if (m && +m[3] >= 1 && +m[3] <= 12 && !m[1]) return { orden: +m[2] + (+m[3] - 1) / 12, texto: `${MESES[+m[3] - 1]} de ${m[2]}`, frase: `en ${MESES[+m[3] - 1]} de ${m[2]}` };
  if (m) return fechaDeAnio(+m[2], !!m[1]);
  m = /^C(\d{1,2})$/i.exec(t);
  if (m && +m[1]) return fechaDeSiglo(+m[1], false);
  m = /\b(\d{4})\b/.exec(t);
  return m ? { orden: +m[1], texto: t, frase: `(${t})` } : null;
}

/* --- Nombres ---
   Para saber si dos nombres son el mismo sitio se comparan sus palabras sin acentos, sin artículos
   y con las formas valencianas llevadas a las castellanas («Castell» = «Castillo»). Que coincida
   solo la palabra genérica («Torre», «Molino») no cuenta: hace falta al menos una palabra propia. */
const PALABRAS_HUECAS = new Set("de del la las el los els les l d y i en a al dels sa es un una antigua antiguo antic antiga vieja viejo vell vella".split(" "));
const FORMA_COMUN = { castell: "castillo", moli: "molino", esglesia: "iglesia", estacio: "estacion", pont: "puente", convent: "convento", monestir: "monasterio", font: "fuente",
  cova: "cueva", masia: "mas", forn: "horno", pou: "pozo", creu: "cruz", sant: "san", palau: "palacio", torreta: "torre", fabrica: "fabrica", ermitori: "ermita", alqueria: "alqueria" };
const PALABRAS_DE_TIPO = new Set("castillo molino iglesia estacion puente convento monasterio fuente cueva mas horno pozo cruz san santa palacio torre fabrica ermita alqueria casa casas caseta casilla corral corrales venta apeadero cementerio hospital sanatorio cuartel balneario nevera aljibe refugio poblado antigua".split(" "));
const palabrasDe = (t) => sinAcentos(t).replace(/[^a-z0-9]+/g, " ").split(" ").filter((x) => x.length > 1 && !PALABRAS_HUECAS.has(x)).map((x) => FORMA_COMUN[x] || x);
function parecidoDeNombres(a, b) {
  const A = new Set(palabrasDe(a)), B = new Set(palabrasDe(b));
  if (!A.size || !B.size) return 0;
  let comunes = 0, propias = 0;
  for (const x of A) if (B.has(x)) { comunes++; if (!PALABRAS_DE_TIPO.has(x)) propias++; }
  return propias ? comunes / Math.min(A.size, B.size) : 0;
}

/* ====================== 2. Lo que ya está en los datos ====================== */
/* El año en que deja de verse el tejado, a partir de la serie que trae la capa de tejados
   («2017: 92 %, 2018: 90 %, … 2025: 12 %»): el primer año en que baja a menos de la mitad y ya no se recupera. */
function perdidaDeTejado(texto) {
  const serie = [...String(texto || "").matchAll(/(\d{4}):\s*(\d+)\s*%/g)].map((m) => [+m[1], +m[2]]);
  if (serie.length < 3) return null;
  const tenia = Math.max(...serie.slice(0, 3).map((x) => x[1]));
  if (tenia < 40) return null;
  for (let i = 1; i < serie.length; i++) {
    if (serie[i][1] <= tenia / 2 && serie.slice(i).every((x) => x[1] <= tenia * 0.6)) return { desde: serie[i - 1][0], hasta: serie[i][0] };
  }
  return null;
}
const NOMBRE_DE_FUENTE = { catastro: "Catastro", osm: "OpenStreetMap", wikidata: "Wikidata" };
const QUE_FUE = /^(?:abandoned|disused|was|razed|demolished|removed|ruins|historic):(amenity|shop|building|man_made|railway|industrial|military|tourism|leisure|office|craft|landuse|power|aeroway|healthcare)$/;
function hechosLocales(s) {
  const h = { fechas: [], datos: [], curiosidades: [], origen: null, cierre: null, tejado: null, roja: [], subasta: null, aire: "", prensa: null };
  const t = s.etiquetas || {};
  // OpenStreetMap: cuándo se hizo, cuándo dejó de usarse y qué fue.
  const inicio = fechaOSM(t.start_date || t["building:start_date"] || t.construction_date || t.opening_date);
  if (inicio) { h.fechas.push(Object.assign({ hecho: "Construcción o apertura", fuente: "OpenStreetMap" }, inicio)); h.origen = Object.assign({ verbo: "Se construyó o abrió", fuente: "OpenStreetMap" }, inicio); }
  const fin = fechaOSM(t.end_date);
  if (fin) { h.fechas.push(Object.assign({ hecho: "Deja de usarse", fuente: "OpenStreetMap" }, fin)); h.cierre = Object.assign({ verbo: "Dejó de usarse", fuente: "OpenStreetMap" }, fin); }
  const fue = new Set();
  for (const [k, v] of Object.entries(t)) { const m = QUE_FUE.exec(k); if (m && v && v !== "yes" && v !== "no") fue.add(valorOSM(v, m[1])); }
  if (fue.size) h.datos.push(["Qué fue", [...fue].join(", ")]);
  const otros = [...new Set([t.old_name, t.alt_name, t.loc_name, t.official_name, t["name:ca"], t["name:es"]].filter((x) => x && x !== s.nombre).flatMap((x) => String(x).split(";").map((y) => y.trim())))];
  if (otros.length) h.datos.push(["Otros nombres", otros.join(", ")]);
  if (t["historic:civilization"]) h.datos.push(["Época", valorOSM(t["historic:civilization"], "historic:civilization")]);
  if (t.architect) h.datos.push(["Arquitecto", t.architect]);
  if (t.protection_title || t["ref:bic"]) h.datos.push(["Protección (OpenStreetMap)", [t.protection_title, t["ref:bic"] && `BIC ${t["ref:bic"]}`].filter(Boolean).join(", ")]);
  for (const k of ["description", "description:es", "description:ca", "inscription"]) if (t[k]) h.curiosidades.push(limpio(t[k]).slice(0, 400));
  // Catastro.
  if (s.anio && s.anio > 1000 && s.anio <= new Date().getFullYear()) {
    h.fechas.push(Object.assign({ hecho: "Construcción", fuente: "Catastro", nota: "en edificios viejos suele ser un año aproximado" }, fechaDeAnio(s.anio)));
    if (!h.origen) h.origen = Object.assign({ catastro: true }, fechaDeAnio(s.anio));
  }
  // Lo que dicen las otras capas del mismo sitio.
  const cerca = (capa, prueba) => {
    const est = estado[capa], lista = [];
    if (est) for (const e of est.elementos.values()) { const d = mapa.distance([s.lat, s.lon], [e.lat, e.lon]); if (prueba(e, d)) lista.push({ e, d }); }
    return lista.sort((a, b) => a.d - b.d);
  };
  const mio = s.elemento || null, radio = radioDelSujeto(s);
  const posible = mio && mio.capa === "posibles" ? mio : (cerca("posibles", (e, d) => (s.refcat && e.p.refcat === s.refcat) || d <= 15)[0] || {}).e;
  if (posible) {
    h.tejado = perdidaDeTejado(posible.p.tejado);
    if (h.tejado) h.fechas.push({ orden: h.tejado.hasta, texto: `${h.tejado.desde} a ${h.tejado.hasta}`, hecho: "Deja de verse el tejado", fuente: "fotos aéreas de cada año", nota: "lo dice un programa comparando fotos: puede ser una obra o un derribo" });
  }
  h.roja = mio && mio.capa === "listaroja" ? [] : cerca("listaroja", (e, d) => d <= radio + 100 || (!!s.nombre && d <= 600 && parecidoDeNombres(s.nombre, e.nombre) >= 0.6)).slice(0, 2);
  const subasta = mio && mio.capa === "subastas" ? null : cerca("subastas", (e, d) => (s.refcat && String(e.p.refcat || "").slice(0, 14) === s.refcat.slice(0, 14)) || (e.p.situado_por === "parcela" && d <= 20))[0];
  if (subasta) h.subasta = subasta.e;
  // Lo visto desde el aire (vision.js) y las noticias que buscó el programa.
  if (s.sitio && typeof etiquetaVision === "function") h.aire = etiquetaVision(s.sitio);
  if (s.clave && prensaGuardada && prensaGuardada.sitios[s.clave]) h.prensa = prensaGuardada.sitios[s.clave];
  return h;
}

/* ====================== 3. Lo que hay que preguntar fuera ====================== */
/* --- Topónimos --- */
const ES_NOMBRE_DE_EDIFICIO = /edific|constru|casa|caseta|casilla|mas[ií]a|\bmas\b|corral|molin|mol[ií]\b|ermita|castell|castillo|torre|f[aà]brica|\bventa\b|alquer|cabany|barraca|estaci|apeadero|convent|monest|iglesia|esgl[eé]sia|balneari|\bforn\b|horno|nevera|cementeri|sanatori|hospital|cuartel|ru[ií]na|restes|restos|refugi/i;
const ES_NOMBRE_DE_PARAJE = /partida|paratge|paraje|\blloc\b|lugar|finca|urbanitzaci|urbanizaci|pol[ií]gon/i;
const ES_NOMBRE_DE_CAMINO = /cam[ií]|senda|carretera|v[ií]a pecuaria|assagador|vereda|carrer|calle/i;
const claseDeToponimo = (tipo, nombre) => {
  const t = tipo || nombre;
  return ES_NOMBRE_DE_CAMINO.test(tipo || "") ? "camino" : ES_NOMBRE_DE_EDIFICIO.test(t) ? "edificio" : ES_NOMBRE_DE_PARAJE.test(t) ? "paraje" : "otro";
};
/* Distancia en metros de un punto a una línea quebrada (o a un punto suelto), en plano: a estas
   distancias la Tierra se puede dar por plana. Los vértices van como [latitud, longitud]. */
function distanciaALinea(s, pts) {
  const kx = 111320 * Math.cos(s.lat * Math.PI / 180), ky = 110540;
  const P = pts.map(([la, lo]) => [(lo - s.lon) * kx, (la - s.lat) * ky]);
  if (!P.length) return Infinity;
  let min = Math.hypot(P[0][0], P[0][1]);
  for (let i = 0; i + 1 < P.length; i++) {
    const [x1, y1] = P[i], dx = P[i + 1][0] - x1, dy = P[i + 1][1] - y1, l2 = dx * dx + dy * dy;
    const t = l2 ? Math.max(0, Math.min(1, -(x1 * dx + y1 * dy) / l2)) : 0;
    min = Math.min(min, Math.hypot(x1 + t * dx, y1 + t * dy));
  }
  return min;
}
/* ¿Está el punto dentro del contorno? Se cuenta cuántas veces cruza el contorno una línea que sale del punto hacia el este. */
function dentroDeContorno(s, pts) {
  let dentro = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [yi, xi] = pts[i], [yj, xj] = pts[j];
    if ((yi > s.lat) !== (yj > s.lat) && s.lon < ((xj - xi) * (s.lat - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}
/* Los nombres de OpenStreetMap más cercanos (Photon). De paso dicen el municipio y la comarca. */
const CLASE_DE_OSM = { highway: "camino", building: "edificio", historic: "edificio", amenity: "edificio", man_made: "edificio", tourism: "edificio", railway: "edificio", military: "edificio", craft: "edificio", landuse: "paraje", place: "paraje" };
function pedirNombresOSM(s) {
  return pedirJ(`https://photon.komoot.io/reverse?lon=${s.lon}&lat=${s.lat}&limit=8`, null, 15000).then((j) => (j.features || []).map((f) => {
    const p = f.properties || {}, c = (f.geometry || {}).coordinates || [], caja = p.extent || null;
    // Para un edificio o una finca, Photon da el centro y la caja que lo contiene: si el punto cae dentro de una caja pequeña, está encima.
    const dentro = !!caja && caja.length === 4 && s.lon >= caja[0] && s.lon <= caja[2] && s.lat <= caja[1] && s.lat >= caja[3] && mapa.distance([caja[1], caja[0]], [caja[3], caja[2]]) < 400;
    const aldea = p.osm_key === "place" && /^(isolated_dwelling|farm)$/.test(p.osm_value || "");
    return { nombre: p.name || "", tipo: p.osm_key && p.osm_value ? valorOSM(p.osm_value, p.osm_key) : "", clase: aldea ? "edificio" : CLASE_DE_OSM[p.osm_key] || "otro",
      municipio: p.city || p.town || p.village || "", comarca: p.county || "", dentro, d: dentro ? 0 : c.length === 2 ? mapa.distance([s.lat, s.lon], [c[1], c[0]]) : Infinity };
  }));
}
/* Nomenclátor Geográfico Básico de España (IGN): los nombres del mapa 1:25.000, de toda España. */
function pedirToponimosIGN(s) {
  const dLat = 0.0036, dLon = dLat / Math.cos(s.lat * Math.PI / 180);      // unos 400 m a cada lado
  const caja = [s.lon - dLon, s.lat - dLat, s.lon + dLon, s.lat + dLat].map((v) => v.toFixed(5)).join(",");
  return pedirJ(`https://api-features.ign.es/collections/namedplace/items?bbox=${caja}&limit=60&f=json`, null, 15000).then((j) => (j.features || [])
    .filter((f) => f.geometry && f.geometry.type === "Point" && (f.properties || {}).etiqueta)
    .map((f) => ({ nombre: f.properties.etiqueta, tipo: String(f.properties.tipo || "").toLowerCase(), clase: claseDeToponimo(f.properties.tipo, f.properties.etiqueta), dentro: false,
      d: mapa.distance([s.lat, s.lon], [f.geometry.coordinates[1], f.geometry.coordinates[0]]), fuente: "IGN" })));
}
/* Nomenclàtor Toponímic Valencià (ICV): más de 120.000 nombres de la Comunitat, con partidas, masías y corrales.
   Contesta en GML, que es XML: de cada lugar se lee el nombre, el tipo y los vértices de su dibujo. */
const NTV = "https://catalogo.icv.gva.es/inspireICV/services/wfsGN";
function pedirToponimosICV(s) {
  const dLat = 0.0027, dLon = dLat / Math.cos(s.lat * Math.PI / 180);      // unos 300 m a cada lado
  const caja = [s.lat - dLat, s.lon - dLon, s.lat + dLat, s.lon + dLon].map((v) => v.toFixed(5)).join(",");
  return pedirTexto(`${NTV}?service=WFS&version=2.0.0&request=GetFeature&typeNames=gn:NamedPlace&count=60&bbox=${caja},urn:ogc:def:crs:EPSG::4326`, null, 20000).then((xml) => {
    const doc = new DOMParser().parseFromString(xml, "text/xml"), salida = [];
    if (doc.getElementsByTagName("parsererror").length) throw new Error("xml");
    for (const nodo of doc.getElementsByTagNameNS("*", "NamedPlace")) {
      const texto = (nombre) => { const e = nodo.getElementsByTagNameNS("*", nombre)[0]; return e ? e.textContent.trim() : ""; };
      const nombre = texto("text"), tipo = texto("localType");
      if (!nombre) continue;
      let d = Infinity, dentro = false;
      for (const lista of [...nodo.getElementsByTagNameNS("*", "posList"), ...nodo.getElementsByTagNameNS("*", "pos")]) {
        const v = lista.textContent.trim().split(/\s+/).map(Number), pts = [];
        for (let i = 0; i + 1 < v.length; i += 2) if (Number.isFinite(v[i]) && Number.isFinite(v[i + 1])) pts.push([v[i], v[i + 1]]);
        d = Math.min(d, distanciaALinea(s, pts));
        if (lista.parentNode.localName === "LinearRing" && lista.parentNode.parentNode.localName === "exterior" && dentroDeContorno(s, pts)) dentro = true;
      }
      if (d === Infinity) continue;
      salida.push({ nombre, tipo: tipo.toLowerCase(), clase: claseDeToponimo(tipo, nombre), dentro, d: dentro ? 0 : d, fuente: "ICV" });
    }
    return salida;
  });
}
/* El mismo nombre llega de varias fuentes: se queda una fila, con la distancia menor y todas las fuentes. */
function juntarToponimos(lista) {
  const vistos = new Map();
  for (const t of lista) {
    const clave = palabrasDe(t.nombre).join(" ") || sinAcentos(t.nombre);
    const ya = vistos.get(clave);
    if (!ya) { vistos.set(clave, Object.assign({}, t, { fuentes: [t.fuente] })); continue; }
    if (!ya.fuentes.includes(t.fuente)) ya.fuentes.push(t.fuente);
    if (t.clase !== "otro" && ya.clase === "otro") { ya.clase = t.clase; ya.tipo = t.tipo; }
    if (t.d < ya.d) { ya.d = t.d; ya.dentro = t.dentro; }
  }
  return [...vistos.values()].map((t) => { const u = Object.assign({}, t, { fuente: t.fuentes.join(", "), d: Math.round(t.d) }); delete u.fuentes; return u; }).sort((a, b) => a.d - b.d);
}

/* --- Wikidata ---
   Lo que hay a 400 m: con su tipo, su protección y la dirección de su artículo y de su ficha oficial si
   los tiene. La consulta (SPARQL) devuelve una fila por cada combinación de tipo y protección: aquí se juntan. */
function pedirWikidataCerca(s) {
  const consulta = `SELECT ?item ?itemLabel ?itemDescription ?dist ?tipoLabel ?catLabel ?ficha ?es ?ca WHERE {
    SERVICE wikibase:around { ?item wdt:P625 ?c . bd:serviceParam wikibase:center "Point(${(+s.lon).toFixed(6)} ${(+s.lat).toFixed(6)})"^^geo:wktLiteral ; wikibase:radius "0.4" ; wikibase:distance ?dist . }
    OPTIONAL { ?item wdt:P31 ?tipo } OPTIONAL { ?item wdt:P1435 ?cat } OPTIONAL { ?item wdt:P973 ?ficha }
    OPTIONAL { ?es schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> }
    OPTIONAL { ?ca schema:about ?item ; schema:isPartOf <https://ca.wikipedia.org/> }
    SERVICE wikibase:label { bd:serviceParam wikibase:language "es,ca,en" } } ORDER BY ?dist LIMIT 150`;
  return pedirJ(`https://query.wikidata.org/sparql?format=json&query=${encodeURIComponent(consulta.replace(/\s+/g, " "))}`, null, 25000).then((j) => {
    const vistos = new Map(), de = (b, k) => (b[k] ? b[k].value : "");
    for (const b of ((j.results || {}).bindings || [])) {
      const q = de(b, "item").split("/").pop(), nombre = de(b, "itemLabel");
      if (!soloQ(q) || !nombre || nombre === q) continue;      // sin nombre en castellano, valenciano ni inglés: no se puede enseñar
      if (!vistos.has(q)) vistos.set(q, { q, nombre, descripcion: de(b, "itemDescription"), d: Math.round(+de(b, "dist") * 1000), tipos: [], cats: [], ficha: urlSegura(de(b, "ficha")) || "", es: urlSegura(de(b, "es")) || "", ca: urlSegura(de(b, "ca")) || "" });
      const x = vistos.get(q), tipo = de(b, "tipoLabel"), cat = de(b, "catLabel");
      if (tipo && !soloQ(tipo) && !x.tipos.includes(tipo)) x.tipos.push(tipo);
      if (cat && !soloQ(cat) && !x.cats.includes(cat)) x.cats.push(cat);
    }
    return [...vistos.values()].sort((a, b) => a.d - b.d);
  });
}
/* Cosas que Wikidata sitúa con un punto y que no son «el edificio»: sirven de contexto, no de identidad. */
const NO_ES_EL_SITIO = /municipio|capital|asentamiento|localidad|entidad|pedan|barrio|calle|avenida|alameda|plaza|retablo|sotabalc|panel|estatua|escultura|placa|r[oó]tulo|comisi[oó]n|instituci[oó]n|empresa|organizaci|parada|l[ií]nea|ruta|biblioteca/i;
const esUnSitio = (x) => !x.tipos.length || !x.tipos.every((t) => NO_ES_EL_SITIO.test(t));
const esContexto = (x) => (x.cats.length || x.ficha || x.es || x.ca) && !x.tipos.some((t) => /municipio|capital|asentamiento|localidad|entidad|comisi[oó]n|instituci[oó]n|biblioteca|alameda|calle|avenida/i.test(t));

const API_WIKIDATA = "https://www.wikidata.org/w/api.php";
const FECHAS_WD = { P571: ["Construcción o fundación", "Se construyó"], P1619: ["Inauguración", "Se inauguró"], P729: ["Entrada en servicio", "Entró en servicio"],
  P3999: ["Cierre", "Cerró"], P730: ["Fin del servicio", "Dejó de prestar servicio"], P576: ["Desaparición o derribo", "Desapareció o se derribó"] };
const DATOS_WD = { P149: "Estilo", P84: "Arquitecto", P186: "Material", P366: "Uso", P81: "Línea", P138: "Lleva el nombre de", P1366: "Sustituido por", P1365: "Sustituye a", P361: "Forma parte de" };
const CON_NOMBRE_WD = ["P31", "P1435", "P5817", "P5816", "P793", ...Object.keys(DATOS_WD)];
/* Los valores de una propiedad: fuera los retirados, primero los preferidos. */
const valoresWD = (e, p) => ((e.claims || {})[p] || []).filter((c) => c.rank !== "deprecated" && c.mainsnak && c.mainsnak.snaktype === "value" && c.mainsnak.datavalue)
  .sort((a, b) => (b.rank === "preferred") - (a.rank === "preferred")).map((c) => ({ v: c.mainsnak.datavalue.value, tipo: c.mainsnak.datavalue.type, cal: c.qualifiers || {} }));
const rotuloWD = (x) => ((x.labels || {}).es || (x.labels || {}).ca || (x.labels || {}).en || {}).value || "";
function leerEntidad(e, nombres) {
  const deQ = (p) => [...new Set(valoresWD(e, p).filter((x) => x.tipo === "wikibase-entityid").map((x) => nombres[x.v.id]).filter(Boolean))];
  const textos = (p) => valoresWD(e, p).map((x) => (typeof x.v === "string" ? x.v : "")).filter(Boolean);
  const fechaDeCal = (x, p) => { const c = ((x.cal[p] || [])[0] || {}).datavalue; return c && c.type === "time" ? fechaWikidata(c.value) : null; };
  const ent = { q: e.id, nombre: rotuloWD(e), descripcion: ((e.descriptions || {}).es || (e.descriptions || {}).ca || {}).value || "", tipos: deQ("P31"), proteccion: deQ("P1435"),
    uso: deQ("P5817"), conservacion: deQ("P5816"), fechas: [], datos: [], enlaces: [], wikis: {}, origen: null, cierre: null };
  for (const [p, [hecho, verbo]] of Object.entries(FECHAS_WD)) {
    for (const x of valoresWD(e, p).slice(0, 2)) {
      const f = x.tipo === "time" && fechaWikidata(x.v);
      if (!f) continue;
      ent.fechas.push(Object.assign({ hecho, fuente: "Wikidata" }, f));
      if (!ent.origen && (p === "P571" || p === "P1619")) ent.origen = Object.assign({ verbo, fuente: "Wikidata" }, f);
      if (!ent.cierre && (p === "P3999" || p === "P730" || p === "P576")) ent.cierre = Object.assign({ verbo, fuente: "Wikidata" }, f);
    }
  }
  for (const x of valoresWD(e, "P793")) { const f = fechaDeCal(x, "P585"), que = x.tipo === "wikibase-entityid" && nombres[x.v.id]; if (f && que) ent.fechas.push(Object.assign({ hecho: que.replace(/^./, (c) => c.toUpperCase()), fuente: "Wikidata" }, f)); }
  for (const x of valoresWD(e, "P1435")) { const f = fechaDeCal(x, "P580"), que = x.tipo === "wikibase-entityid" && nombres[x.v.id]; if (f && que) ent.fechas.push(Object.assign({ hecho: `Protección: ${que}`, fuente: "Wikidata" }, f)); }
  for (const [p, nombre] of Object.entries(DATOS_WD)) { const v = deQ(p); if (v.length) ent.datos.push([nombre, v.join(", ")]); }
  const plantas = valoresWD(e, "P1101").map((x) => (x.v && x.v.amount ? String(+x.v.amount) : "")).filter(Boolean)[0];
  if (plantas) ent.datos.push(["Plantas", plantas]);
  if (textos("P2473").length) ent.datos.push(["Código en el inventario valenciano", textos("P2473").join(", ")]);
  if (textos("P808").length) ent.datos.push(["Código de bien de interés cultural", textos("P808").join(", ")]);
  const enlace = (texto, url) => { const u = urlSegura(url); if (u && !ent.enlaces.some((x) => x[1] === u)) ent.enlaces.push([texto, u]); };
  for (const u of textos("P973")) { const sede = (() => { try { return new URL(u).hostname; } catch { return ""; } })(); enlace(/gva\.es$/.test(sede) ? "Ficha de patrimonio de la Generalitat" : `Descripción en ${sede.replace(/^www\./, "")}`, u); }
  for (const u of textos("P856")) enlace("Web oficial", u);
  for (const c of textos("P4868")) enlace("Ficha en la Lista Roja", `https://listaroja.hispanianostra.org/ficha/${encodeURIComponent(c)}/`);
  for (const c of textos("P12661")) enlace("Castillos de España", `https://www.xn--castillosdeespaa-lub.es/es/content/${encodeURIComponent(c)}`);
  for (const [idioma, sitio] of [["es", "eswiki"], ["ca", "cawiki"], ["en", "enwiki"]]) { const t = ((e.sitelinks || {})[sitio] || {}).title; if (t) ent.wikis[idioma] = t; }
  const categoria = ((e.sitelinks || {}).commonswiki || {}).title || (textos("P373")[0] ? `Category:${textos("P373")[0]}` : "");
  if (categoria) enlace("Más fotos en Commons", `https://commons.wikimedia.org/wiki/${encodeURIComponent(categoria.replace(/ /g, "_"))}`);
  enlace("Wikidata", `https://www.wikidata.org/wiki/${e.id}`);
  return ent;
}
/* La ficha de un elemento. Sus valores (tipo, protección…) son otros elementos: en una segunda petición se piden sus nombres. */
async function pedirEntidadWikidata(q) {
  const comun = { action: "wbgetentities", format: "json", origin: "*", languages: "es|ca|en" };
  const j = await pedirJ(`${API_WIKIDATA}?${new URLSearchParams(Object.assign({ ids: q, props: "labels|descriptions|claims|sitelinks", sitefilter: "eswiki|cawiki|enwiki|commonswiki" }, comun))}`, null, 20000);
  const e = (j.entities || {})[q];
  if (!e || !e.claims) throw new Error("sin ficha");
  const ids = new Set(), nombres = {};
  for (const p of CON_NOMBRE_WD) for (const x of valoresWD(e, p)) if (x.tipo === "wikibase-entityid" && soloQ(x.v.id)) ids.add(x.v.id);
  if (ids.size) {
    const k = await pedirJ(`${API_WIKIDATA}?${new URLSearchParams(Object.assign({ ids: [...ids].slice(0, 50).join("|"), props: "labels" }, comun))}`, null, 20000).catch(() => ({}));
    for (const [id, x] of Object.entries(k.entities || {})) nombres[id] = rotuloWD(x);
  }
  return leerEntidad(e, nombres);
}

/* --- Wikipedia: el arranque del artículo --- */
const NOMBRE_DE_IDIOMA = { es: "castellano", ca: "valenciano", en: "inglés" };
function recortarTexto(texto, tope) {
  const t = String(texto || "").replace(/\s+/g, " ").trim();
  if (t.length <= tope) return t;
  const corte = t.slice(0, tope), punto = corte.lastIndexOf(". ");
  return punto > tope * 0.5 ? corte.slice(0, punto + 1) : `${corte.replace(/\s+\S*$/, "")}…`;
}
function pedirArticuloWiki(idioma, titulo) {
  return consultaWiki(`${idioma}.wikipedia.org`, { prop: "extracts|info|pageprops", exintro: "1", explaintext: "1", inprop: "url", ppprop: "wikibase_item", redirects: "1", titles: titulo }, 1).then((paginas) => {
    const p = paginas.find((x) => x.extract);
    if (!p) return null;
    return { idioma, titulo: p.title || titulo, texto: recortarTexto(p.extract, 480), q: soloQ((p.pageprops || {}).wikibase_item),
      url: urlSegura(p.fullurl) || `https://${idioma}.wikipedia.org/wiki/${encodeURIComponent(String(p.title || titulo).replace(/ /g, "_"))}` };
  });
}

/* --- Commons: fotos de alrededor, con el año en que se hicieron ---
   La fecha viene escrita de mil maneras («2022-05-08 12:33», «8 May 2022 (according to Exif data)»): solo se saca el año. */
function anioDeFoto(texto) {
  const m = /\b(1[89]\d\d|20\d\d)\b/.exec(limpio(texto));
  return m && +m[1] <= new Date().getFullYear() ? +m[1] : null;
}
function pedirFotosConFecha(s) {
  const radio = Math.round(Math.max(120, Math.min(400, radioDelSujeto(s) + 100)));
  return consultaWiki("commons.wikimedia.org", { generator: "geosearch", ggsnamespace: "6", ggscoord: `${s.lat}|${s.lon}`, ggsradius: String(radio), ggslimit: "40",
    prop: "imageinfo", iiprop: "url|extmetadata|mime", iiurlwidth: "500", iiextmetadatafilter: "Artist|DateTimeOriginal" }, 2).then((paginas) => paginas.map((p) => {
    const i = (p.imageinfo || [])[0];
    if (!i || !/^image\//.test(i.mime || "image/") || !urlSegura(i.thumburl || i.url) || !urlSegura(i.descriptionurl)) return null;
    const m = i.extmetadata || {};
    return { titulo: String(p.title || "").replace(/^File:/, "").replace(/\.[a-z]+$/i, "").slice(0, 120), miniatura: i.thumburl || i.url, pagina: i.descriptionurl,
      anio: anioDeFoto((m.DateTimeOriginal || {}).value), autor: limpio((m.Artist || {}).value).slice(0, 60) };
  }).filter(Boolean).sort((a, b) => (a.anio || 9999) - (b.anio || 9999)).slice(0, 12));
}

/* --- Catastro: dirección o paraje y para qué consta cada construcción --- */
function pedirFichaCatastro(refcat) {
  return pedirJ(`${DATOS_PARCELA}?RefCat=${encodeURIComponent(refcat)}`, null, 20000).then((d) => {
    const res = d.consulta_dnprcResult || {}, bi = (res.bico || {}).bi;
    if (bi) {
      const dt = bi.dt || {}, rustica = ((dt.locs || {}).lors || {}).lorus || {}, usos = {};
      for (const c of [].concat(res.bico.lcons || [])) { const k = String((c.dvcons || {}).dtip || c.lcd || "").toLowerCase(); if (k) usos[k] = (usos[k] || 0) + (+(c.dfcons || {}).stl || 0); }
      return { direccion: limpio(bi.ldt), paraje: rustica.npa ? enMinusculas(rustica.npa) : "", municipio: dt.nm ? enMinusculas(dt.nm) : "", uso: String((bi.debi || {}).luso || "").toLowerCase(),
        anio: +(bi.debi || {}).ant || null, construcciones: Object.entries(usos).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, m2]) => (m2 ? `${k} (${miles(m2)} m²)` : k)) };
    }
    const varios = [].concat((res.lrcdnp || {}).rcdnp || []);
    if (!varios.length) return null;
    const usos = [...new Set(varios.map((x) => String((x.debi || {}).luso || "").toLowerCase()).filter(Boolean))], anios = varios.map((x) => +(x.debi || {}).ant).filter(Boolean);
    return { direccion: "", paraje: "", municipio: "", uso: usos.join(", "), anio: anios.length ? Math.min(...anios) : null, construcciones: [], inmuebles: varios.length };
  });
}

/* --- La búsqueda entera ---
   Primero se pregunta a la vez por lo que hay alrededor; con eso se decide quién es el sitio (su
   ficha de Wikidata, si la tiene) y entonces se piden la ficha, el artículo y, si detrás está el
   programa del ordenador, las noticias. Cada fuente va por su cuenta: una caída no tumba el resto.
   `avisar(r, esperando)` se llama cada vez que llega algo, para ir pintándolo. */
async function buscarHistoria(s, avisar) {
  const r = { v: VERSION_HISTORIA, t: Date.now(), fuentes: {}, municipio: s.municipio || "", comarca: "", toponimos: [], cerca: [], fotos: [], catastro: null, entidad: null, articulo: null,
    probable: null, paraje: "", noticias: null, consulta: "" };
  const esperando = new Set();
  const paso = (nombre, promesa, poner) => {
    esperando.add(nombre);
    return Promise.resolve(promesa).then(poner).then((v) => { r.fuentes[nombre] = v === false ? "nada" : "bien"; }, () => { r.fuentes[nombre] = "fallo"; })
      .then(() => { esperando.delete(nombre); avisar(r, [...esperando]); });
  };
  const sueltos = [];
  await Promise.all([
    paso("OpenStreetMap", pedirNombresOSM(s), (lista) => {
      const conMunicipio = lista.find((o) => o.municipio);
      if (conMunicipio) { if (!r.municipio) r.municipio = conMunicipio.municipio; r.comarca = conMunicipio.comarca; }
      for (const o of lista) if (o.nombre && o.clase !== "camino" && o.d <= 500) sueltos.push({ nombre: o.nombre, tipo: o.tipo, clase: o.clase, dentro: o.dentro, d: o.d, fuente: "OpenStreetMap" });
      return lista.length > 0;
    }),
    paso("IGN", pedirToponimosIGN(s), (lista) => { sueltos.push(...lista); return lista.length > 0; }),
    enLaComunitat(s) ? paso("ICV", pedirToponimosICV(s), (lista) => { sueltos.push(...lista.filter((t) => t.clase !== "camino")); return lista.length > 0; }) : null,
    paso("Wikidata", pedirWikidataCerca(s), (lista) => { r.cerca = lista; return lista.length > 0; }),
    paso("Commons", pedirFotosConFecha(s), (lista) => { r.fotos = lista; return lista.length > 0; }),
    s.refcat ? paso("Catastro", pedirFichaCatastro(s.refcat), (c) => { r.catastro = c; return !!c; }) : null,
  ].filter(Boolean));
  r.toponimos = juntarToponimos(sueltos);
  if (!r.municipio && r.catastro) r.municipio = r.catastro.municipio;
  const paraje = r.toponimos.find((t) => t.clase === "paraje" && t.dentro) || r.toponimos.find((t) => t.clase === "paraje" && t.d <= 400);
  r.paraje = (paraje && paraje.nombre) || (r.catastro && r.catastro.paraje) || "";

  // ¿Quién es? Por su ficha si la trae; si no, por el nombre; y si no tiene nombre, por lo que tenga encima.
  const radio = radioDelSujeto(s);
  let q = s.wikidata, seguro = true, d = 0;
  if (!q && /^[a-z-]{2,12}:./.test(s.wikipedia || "")) {
    const corte = s.wikipedia.indexOf(":");
    await paso("Wikipedia", pedirArticuloWiki(s.wikipedia.slice(0, corte), s.wikipedia.slice(corte + 1)), (a) => { if (!a) return false; if (!s.conArticulo) r.articulo = a; q = a.q; return true; });
  }
  if (!q && s.nombre) {
    const mejor = r.cerca.map((x) => [x, parecidoDeNombres(s.nombre, x.nombre)]).filter(([x, p]) => p >= 0.6 || (p >= 0.5 && x.d <= 150)).sort((a, b) => b[1] - a[1] || a[0].d - b[0].d)[0];
    if (mejor) { q = mejor[0].q; d = mejor[0].d; }
  }
  if (!s.nombre) {
    r.probable = r.toponimos.find((t) => t.clase === "edificio" && t.d <= Math.max(40, radio + 20)) || null;
    const pegado = !q && r.cerca.find((x) => x.d <= Math.max(25, radio + 10) && esUnSitio(x));
    if (pegado) { q = pegado.q; seguro = false; d = pegado.d; }
  }
  if (q) await paso("Wikidata", pedirEntidadWikidata(q), (ent) => { r.entidad = Object.assign(ent, { seguro, d }); r.cerca = r.cerca.filter((x) => x.q !== q); return true; });
  if (r.entidad && !r.articulo && !s.conArticulo) {
    const w = r.entidad.wikis, idioma = w.es ? "es" : w.ca ? "ca" : w.en ? "en" : "";
    if (idioma) await paso("Wikipedia", pedirArticuloWiki(idioma, w[idioma]), (a) => { if (!a) return false; r.articulo = a; return true; });
  }
  // Las noticias, solo con nombre seguro y con el programa detrás (una página no puede preguntar a Google Noticias).
  const nombre = s.nombre || (r.entidad && r.entidad.seguro ? r.entidad.nombre : "");
  if (conServidor && nombre && r.municipio) await paso("Prensa", pedirNoticias(nombre, r.municipio), (j) => { r.noticias = j.noticias; r.consulta = j.consulta; return j.noticias.length > 0; });
  return r;
}
const noticiaValida = (n) => n && typeof n.titulo === "string" && n.titulo && urlSegura(n.url);
function pedirNoticias(nombre, municipio) {
  return pedirJ(`vivo/noticias?${new URLSearchParams({ nombre, municipio: municipioCorto(municipio) })}`, null, 30000)
    .then((j) => ({ consulta: String(j.consulta || ""), noticias: (j.noticias || []).filter(noticiaValida).slice(0, 10) }));
}

/* ====================== 4. El bloque de la ficha ====================== */
const enlaceFuera = (texto, url, clase) => el("a", { href: url, target: "_blank", rel: "noopener noreferrer", textContent: texto, className: clase || "" });
const enLista = (v) => (v.length <= 1 ? v.join("") : `${v.slice(0, -1).join(", ")} y ${v[v.length - 1]}`);
const metrosCortos = (d) => (d < 1 ? "encima" : `a ${Math.round(d)} m`);

/* El resumen: frases hechas sobre lo que se sabe, cada una con su fuente. Sin datos, no hay frase. */
function resumenDeHistoria(s, h, r, acabada) {
  const p = el("p", { className: "resumen" }), ent = r && r.entidad, seguro = !!(ent && ent.seguro);
  const nombre = s.nombre || (seguro ? ent.nombre : ""), municipio = municipioCorto((r && r.municipio) || s.municipio);
  let tipo = (seguro && ent.tipos.slice(0, 2).join(" y ")) || (s.etiquetas ? tipoDeEtiquetas(s.etiquetas).toLowerCase() : "");
  if (tipo && nombre && sinAcentos(nombre).includes(sinAcentos(tipo.split(" ")[0]).slice(0, 5))) tipo = "";      // «Castillo de X, castillo» sobra
  const frases = [];
  if (nombre) p.append(el("b", { textContent: nombre }), `${tipo ? `, ${tipo}` : ""}${municipio ? `, en ${municipio}` : ""}. `);
  else if (r) {
    if (r.probable) frases.push(`No tiene nombre en los datos. El más cercano en el mapa es «${r.probable.nombre}» (${[r.probable.tipo, metrosCortos(r.probable.d), r.probable.fuente].filter(Boolean).join(", ")}): puede ser el suyo.`);
    else if (ent) frases.push(`No tiene nombre en los datos. Wikidata sitúa ${metrosCortos(ent.d)} «${ent.nombre}»${ent.tipos.length ? ` (${ent.tipos[0]})` : ""}: puede ser el mismo sitio.`);
    else if (acabada) frases.push("No tiene nombre en ninguna de las fuentes consultadas.");
    if (r.paraje || municipio) frases.push(`Está en ${r.paraje ? `«${r.paraje}»` : ""}${r.paraje && municipio ? ", " : ""}${municipio || ""}.`);
  }
  const origen = (seguro && ent.origen) || h.origen;
  if (origen) frases.push(origen.catastro ? `Catastro fecha la construcción ${origen.frase}.` : `${origen.verbo} ${origen.frase} (${origen.fuente}).`);
  if (seguro && ent.proteccion.length) frases.push(`Está protegido como ${enLista(ent.proteccion)}.`);
  for (const { e, d } of h.roja) frases.push(`Hispania Nostra tiene ${metrosCortos(d)} «${e.nombre}» en su Lista ${{ verde: "Verde (recuperado)", negra: "Negra (perdido)" }[e.p.lista] || "Roja (en riesgo de perderse)"}.`);
  const cierre = (seguro && ent.cierre) || h.cierre;
  if (cierre) frases.push(`${cierre.verbo} ${cierre.frase} (${cierre.fuente}).`);
  else if (h.tejado) frases.push(`En las fotos aéreas el tejado deja de verse entre ${h.tejado.desde} y ${h.tejado.hasta}.`);
  else if (seguro && (ent.uso.length || ent.conservacion.length)) frases.push(`Wikidata lo da por ${[ent.uso.length && `«${ent.uso.join(", ")}»`, ent.conservacion.length && `conservación: «${ent.conservacion.join(", ")}»`].filter(Boolean).join("; ")}, sin fecha.`);
  else if (acabada && s.abandonado) frases.push("Ninguna fuente consultada dice cuándo se abandonó: lo más fiable es comparar las fotos aéreas por años.");
  if (s.estado || h.aire) frases.push(`Hoy: ${[s.estado && `consta como ${s.estado}${s.fuentes.length ? ` (${s.fuentes.map((f) => NOMBRE_DE_FUENTE[f] || f).join(", ")})` : ""}`, h.aire && `desde el aire, ${h.aire}`].filter(Boolean).join("; ")}.`);
  p.append(frases.join(" "));
  return p.textContent.trim() ? p : null;
}

/* Adónde ir a seguir buscando: cada enlace abre la búsqueda ya escrita en su portal. */
function enlacesDeBusqueda(nombre, municipio, enCV) {
  const c = encodeURIComponent, q = `"${nombre}"${municipio ? ` "${municipio}"` : ""}`, solo = c(`"${nombre}"`);
  return [["Google Noticias", `https://news.google.com/search?q=${c(q)}&hl=es&gl=ES&ceid=ES%3Aes`],
    ["Google", `https://www.google.com/search?q=${c(`${q} historia`)}`],
    ["Libros", `https://www.google.com/search?tbm=bks&q=${c(q)}`],
    ["Prensa histórica", `https://prensahistorica.mcu.es/es/consulta/resultados_ocr.do?general_ocr=on&busq_general=${solo}`],
    enCV && ["Biblioteca Valenciana", `https://bivaldi.gva.es/es/consulta/resultados_ocr.do?general_ocr=on&busq_general=${solo}`],
    ["BOE", `https://www.google.com/search?q=${c(`${q} site:boe.es`)}`],
    enCV && ["DOGV", `https://www.google.com/search?q=${c(`${q} site:dogv.gva.es`)}`],
    ["Estudios (Dialnet)", `https://dialnet.unirioja.es/buscar/documentos?querysDismax.DOCUMENTAL_TODO=${c(q)}`],
    ["Europeana", `https://www.europeana.eu/es/search?query=${solo}`],
    ["Internet Archive", `https://archive.org/search?query=${solo}&sin=TXT`]].filter(Boolean);
}

function listaDeNoticias(noticias) {
  return el("ul", { className: "noticias" }, ...noticias.map((n) => el("li", { className: n.nombra === false ? "floja" : "" },
    enlaceFuera(n.titulo, n.url), el("small", { textContent: [n.medio, n.fecha && fechaCorta(n.fecha)].filter(Boolean).join(", ") }))));
}

const sigueAbierta = (f) => !!f && f === fichaHistoria && document.body.contains(f.caja)
  && (f.s.sitio ? seleccion === f.s.sitio && !$("ficha").hidden : elementoAbierto === f.s.elemento);

function pintarHistoria() {
  const f = fichaHistoria;
  if (!f) return;
  // Un elemento puede completarse después de abrir su ficha (le llegan la referencia catastral o las etiquetas): se vuelve a leer.
  if (f.s.elemento) Object.assign(f.s, sujetoDeElemento(f.s.elemento));
  const s = f.s, r = f.r || f.parcial || null, acabada = !!f.r, h = hechosLocales(s), partes = [el("h3", { textContent: "Historia" })];
  const ent = r && r.entidad, seguro = !!(ent && ent.seguro);
  const titulo = (texto) => el("h4", { textContent: texto });

  const resumen = resumenDeHistoria(s, h, r, acabada);
  if (resumen) partes.push(resumen);
  else if (!f.buscando) partes.push(el("p", { className: "resumen suave", textContent: "Aún no se ha buscado nada de este sitio. La búsqueda mira si tiene artículo o ficha de patrimonio, qué nombres le da el mapa, qué hay catalogado cerca y si hay fotos con fecha." }));

  // El arranque del artículo, entre comillas y con su fuente.
  if (r && r.articulo) {
    partes.push(el("blockquote", { className: "cita" }, r.articulo.texto,
      el("small", {}, `Wikipedia en ${NOMBRE_DE_IDIOMA[r.articulo.idioma] || r.articulo.idioma}. `, enlaceFuera("Seguir leyendo", r.articulo.url))));
  }

  // Cronología: todo lo que lleva fecha, en fila.
  const fechas = h.fechas.concat(seguro ? ent.fechas : []).sort((a, b) => a.orden - b.orden);
  if (fechas.length) {
    const dl = el("dl", { className: "datos cronologia" });
    for (const x of fechas) dl.append(el("dt", { textContent: x.texto }), el("dd", {}, x.hecho, el("small", { textContent: `${x.fuente}${x.nota ? `: ${x.nota}` : ""}` })));
    partes.push(titulo("Fechas"), dl);
  }

  // Lo que consta, sin fecha.
  const filas = [];
  if (seguro) {
    filas.push(["Qué es", ent.tipos.join(", ")], ["Protección", ent.proteccion.join(", ")], ["Estado de uso", ent.uso.join(", ")], ["Conservación", ent.conservacion.join(", ")], ...ent.datos);
    if (ent.descripcion && !ent.tipos.length) filas.unshift(["Qué es", ent.descripcion]);
  }
  filas.push(...h.datos);
  if (r && r.catastro) {
    filas.push(["Dirección en Catastro", r.catastro.direccion]);
    if (r.catastro.construcciones.length) filas.push(["Consta en Catastro", r.catastro.construcciones.join(", ")]);
    else if (r.catastro.inmuebles) filas.push(["Consta en Catastro", `${r.catastro.inmuebles} inmuebles (${r.catastro.uso})`]);
  }
  const tabla = tablaDatos(filas);
  if (tabla) partes.push(titulo(seguro ? "Lo que consta (Wikidata, OpenStreetMap y Catastro)" : "Lo que consta"), tabla);

  // Cosas sueltas: descripciones de OpenStreetMap, la subasta, la Lista Roja.
  const sueltas = h.curiosidades.map((t) => el("li", { textContent: t }));
  for (const { e } of h.roja) {
    const ver = el("button", { type: "button", className: "como-enlace", textContent: "ver su ficha" });
    ver.addEventListener("click", () => abrirElemento(e, true));
    sueltas.push(el("li", {}, `Lista Roja del Patrimonio, «${e.nombre}»${e.p.resumen ? `: ${e.p.resumen}` : ""} (`, ver, ")"));
  }
  if (h.subasta) {
    const ver = el("button", { type: "button", className: "como-enlace", textContent: "ver la subasta" });
    ver.addEventListener("click", () => abrirElemento(h.subasta, true));
    sueltas.push(el("li", {}, `Está o ha estado en subasta pública en el BOE${h.subasta.p.fin ? ` (termina: ${h.subasta.p.fin})` : ""} (`, ver, ")"));
  }
  if (sueltas.length) partes.push(titulo("Más cosas"), el("ul", { className: "sueltas" }, ...sueltas));

  // Si la ficha de Wikidata se ha cogido solo por cercanía, va aparte y con su aviso.
  if (ent && !seguro) {
    const linea = [ent.tipos.slice(0, 2).join(", "), ent.proteccion.join(", "), ent.origen && `${ent.origen.verbo.toLowerCase()} ${ent.origen.frase}`].filter(Boolean).join("; ");
    partes.push(titulo(`Puede ser «${ent.nombre}» (${metrosCortos(ent.d)})`),
      el("p", { className: "suave", textContent: `${linea ? `${linea.replace(/^./, (c) => c.toUpperCase())}. ` : ""}Se ha emparejado solo por cercanía: comprueba que es el mismo sitio.` }));
  }
  const enlaces = el("div", { className: "enlaces" });
  if (ent) for (const [texto, url] of ent.enlaces) enlaces.append(enlaceFuera(texto, url));
  if (ent && r.articulo) for (const [idioma, tit] of Object.entries(ent.wikis)) if (idioma !== r.articulo.idioma && idioma !== "en") enlaces.append(enlaceFuera(`Wikipedia en ${NOMBRE_DE_IDIOMA[idioma]}`, `https://${idioma}.wikipedia.org/wiki/${encodeURIComponent(tit.replace(/ /g, "_"))}`));
  if (enlaces.children.length) partes.push(titulo("Fichas y artículos"), enlaces);

  // La prensa: lo recién buscado o, si no, lo que guardó el programa.
  const prensa = r && r.noticias ? { noticias: r.noticias, consulta: r.consulta, consultado: new Date(r.t).toISOString().slice(0, 10) } : h.prensa;
  if (prensa && (prensa.noticias || []).filter(noticiaValida).length) {
    partes.push(titulo("En la prensa"), listaDeNoticias(prensa.noticias.filter(noticiaValida)),
      el("p", { className: "suave", textContent: `Google Noticias, buscando ${prensa.consulta || "su nombre"}${prensa.consultado ? ` el ${fechaCorta(prensa.consultado)}` : ""}. Las que no lo nombran en el titular pueden no ir de este sitio.` }));
  } else if (prensa) partes.push(titulo("En la prensa"), el("p", { className: "suave", textContent: `Google Noticias no da nada buscando ${prensa.consulta || "su nombre"}${prensa.consultado ? ` (${fechaCorta(prensa.consultado)})` : ""}.` }));

  // Fotos con año.
  if (r && r.fotos.length) {
    partes.push(titulo("Fotos de alrededor, por año (Wikimedia Commons)"), el("div", { className: "fotos fechadas" }, ...r.fotos.slice(0, 9).map((x) =>
      el("a", { href: x.pagina, target: "_blank", rel: "noopener noreferrer", title: [x.titulo, x.autor].filter(Boolean).join(". ") },
        el("img", { src: x.miniatura, alt: x.titulo || "Foto cercana", loading: "lazy", referrerPolicy: "no-referrer" }), el("span", { textContent: x.anio ? String(x.anio) : "sin fecha" })))));
  }

  // Alrededor: nombres del mapa y patrimonio catalogado.
  if (r) {
    const cerca = [];
    for (const t of r.toponimos.filter((x) => x.d <= 400).slice(0, 7)) cerca.push(el("li", {}, el("b", { textContent: t.nombre }), el("small", { textContent: ` ${[t.tipo, t.dentro ? "aquí mismo" : metrosCortos(t.d), t.fuente].filter(Boolean).join(", ")}` })));
    for (const x of r.cerca.filter(esContexto).slice(0, 7)) {
      const url = x.es || x.ca || x.ficha || `https://www.wikidata.org/wiki/${x.q}`;
      cerca.push(el("li", {}, enlaceFuera(x.nombre, url), el("small", { textContent: ` ${[x.tipos[0], x.cats.join(", "), metrosCortos(x.d)].filter(Boolean).join(", ")}` })));
    }
    if (cerca.length) partes.push(titulo("Alrededor: nombres del mapa y patrimonio catalogado"), el("ul", { className: "sueltas cerca" }, ...cerca));
  }

  // Seguir buscando fuera.
  if (r || s.nombre) {
    const nombre = s.nombre || (ent ? ent.nombre : "") || (r && r.probable ? r.probable.nombre : "") || (r ? r.paraje : ""), municipio = municipioCorto((r && r.municipio) || s.municipio);
    if (nombre) {
      const fuera = el("div", { className: "enlaces" }, ...enlacesDeBusqueda(nombre, municipio, enLaComunitat(s)).map(([texto, url]) => enlaceFuera(texto, url)));
      if (municipio) fuera.append(enlaceFuera(`Historia de ${municipio}`, `https://es.wikipedia.org/w/index.php?search=${encodeURIComponent(municipio)}`));
      partes.push(titulo(`Seguir buscando «${nombre}»`), fuera);
      if (!s.nombre && !seguro) partes.push(el("p", { className: "suave", textContent: "El sitio no tiene nombre propio: se busca por el del mapa más cercano, que puede no ser el suyo." }));
      if (conServidor && acabada && !r.noticias && municipio) {
        const boton = el("button", { type: "button", className: "boton-historia secundario", textContent: `Buscar noticias de «${nombre}»` });
        boton.addEventListener("click", () => {
          boton.disabled = true; boton.textContent = "Buscando noticias…";
          pedirNoticias(nombre, municipio).then((j) => { f.r.noticias = j.noticias; f.r.consulta = j.consulta; f.r.t = Date.now(); guardarHistoria(f); if (sigueAbierta(f)) pintarHistoria(); },
            () => { boton.disabled = false; boton.textContent = "Google Noticias no contesta ahora. Probar otra vez"; });
        });
        partes.push(boton);
      }
    } else if (acabada) partes.push(el("p", { className: "suave", textContent: "Sin un nombre no hay por dónde buscar en la prensa ni en los archivos: ni Catastro ni el mapa le dan ninguno." }));
  }

  // Estado de la búsqueda y sus botones.
  if (f.buscando) partes.push(el("p", { className: "pendiente", textContent: `Buscando${f.esperando && f.esperando.length ? ` en ${enLista(f.esperando)}` : ""}…` }));
  else if (!acabada) {
    const buscar = el("button", { type: "button", className: "boton-historia", textContent: "Buscar su historia" });
    buscar.addEventListener("click", lanzarHistoria);
    partes.push(buscar);
  } else {
    const bien = Object.entries(r.fuentes).filter(([, v]) => v !== "fallo").map(([k]) => k), mal = Object.entries(r.fuentes).filter(([, v]) => v === "fallo").map(([k]) => k);
    const otra = el("button", { type: "button", className: "como-enlace", textContent: "Volver a buscar" });
    otra.addEventListener("click", lanzarHistoria);
    partes.push(el("p", { className: "suave pie-historia" }, `Buscado el ${fechaCorta(r.t)} en ${enLista(bien) || "ninguna fuente"}.${mal.length ? ` No ${mal.length > 1 ? "han" : "ha"} contestado: ${enLista(mal)}.` : ""} `, otra));
  }
  const sola = el("input", { type: "checkbox", checked: quiereHistoriaSola() });
  sola.addEventListener("change", () => { guardarLocal("osintmaps.historia.v1", { sola: sola.checked }); if (sola.checked && !f.r && !f.buscando) lanzarHistoria(); });
  partes.push(el("label", { className: "ajuste-historia" }, sola, "Buscarla sola al abrir cada ficha"));

  f.caja.replaceChildren(...partes);
}

function guardarHistoria(f) {
  historiasVistas.set(f.s.id, f.r);
  memoria.guardar([[`historia|${f.s.id}`, f.r]]);
}
function lanzarHistoria() {
  const f = fichaHistoria;
  if (!f || f.buscando) return;
  f.buscando = true; f.r = null; f.parcial = null; f.esperando = [];
  pintarHistoria();
  let reloj = null;
  const pronto = () => { clearTimeout(reloj); reloj = setTimeout(() => { if (f.buscando && sigueAbierta(f)) pintarHistoria(); }, 120); };
  buscarHistoria(f.s, (parcial, esperando) => { f.parcial = parcial; f.esperando = esperando; pronto(); })
    .then((r) => { f.r = r; guardarHistoria(f); }, () => { /* cada fuente ya atrapa sus fallos: aquí no debería llegar nada */ })
    .then(() => { clearTimeout(reloj); f.buscando = false; f.parcial = null; if (sigueAbierta(f)) pintarHistoria(); });
}

/* El bloque de la ficha. Enseña al momento lo que ya se sabe; lo de internet, cuando se pide (o solo,
   si así se ha dejado dicho) y, si ya se buscó hace poco, lo que se guardó entonces. */
function bloqueHistoria(s) {
  const caja = el("section", { className: "bloque historia" });
  const f = fichaHistoria = { s, caja, r: historiasVistas.get(s.id) || null, parcial: null, buscando: false, esperando: [] };
  pintarHistoria();
  if (!f.r) {
    memoria.leer([`historia|${s.id}`], VIDA_HISTORIA).then(([guardada]) => {
      if (fichaHistoria !== f || f.r || f.buscando) return;
      if (guardada && guardada.v === VERSION_HISTORIA) { f.r = guardada; historiasVistas.set(s.id, guardada); pintarHistoria(); }
      else if (quiereHistoriaSola()) setTimeout(() => { if (sigueAbierta(f) && !f.r && !f.buscando) lanzarHistoria(); }, 900);
    });
  }
  return caja;
}
