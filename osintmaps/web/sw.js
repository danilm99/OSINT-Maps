/* OSINT Maps: trabajador de servicio. Es un programa pequeño que el navegador deja corriendo
   entre la página y la red. Aquí hace dos cosas:

   - Lo propio de la página (el visor y los ficheros de datos) se pide siempre a la red, para
     tener la última versión de todo a la vez; cada respuesta se guarda, y si no hay conexión se
     sirve la copia.
     Así el mapa arranca aunque el móvil esté sin cobertura (lo ya visto sale de la memoria).
   - Las bibliotecas de fuera (Leaflet, las letras) llevan la versión en su dirección y no
     cambian nunca: se sirven de la copia sin preguntar, que es lo más rápido.

   Solo se instala en la versión web (https); con «osintmaps servir» no hace falta. */
const PROPIO = "osintmaps-propio-v1", FIJO = "osintmaps-fijo-v1";
const BIBLIOTECAS = /^(unpkg\.com|fonts\.googleapis\.com|fonts\.gstatic\.com)$/;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (ev) => ev.waitUntil(
  caches.keys()
    .then((claves) => Promise.all(claves.filter((k) => k.startsWith("osintmaps-") && k !== PROPIO && k !== FIJO).map((k) => caches.delete(k))))
    .then(() => self.clients.claim())));

self.addEventListener("fetch", (ev) => {
  const pedido = ev.request, url = new URL(pedido.url);
  if (pedido.method !== "GET") return;
  if (url.origin === self.location.origin) {
    if (url.pathname.includes("/vivo/")) return;      // lo que es en directo no se guarda
    // «no-cache» no es «sin copia»: es preguntar siempre al servidor si la copia sigue valiendo. Sin esto el
    // navegador se fía de la suya unos minutos y, tras publicar una versión, podría mezclar ficheros de dos.
    ev.respondWith(fetch(pedido, { cache: "no-cache" })
      .then((respuesta) => {
        if (respuesta.ok) { const copia = respuesta.clone(); caches.open(PROPIO).then((c) => c.put(pedido, copia)); }
        return respuesta;
      })
      .catch(() => caches.match(pedido, { ignoreSearch: true }).then((copia) => copia || Response.error())));
  } else if (BIBLIOTECAS.test(url.hostname)) {
    ev.respondWith(caches.open(FIJO).then((c) => c.match(pedido).then((copia) => copia || fetch(pedido).then((nueva) => {
      if (nueva.ok || nueva.type === "opaque") c.put(pedido, nueva.clone());
      return nueva;
    }))));
  }
});
