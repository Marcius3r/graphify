// Service worker de Chapita Admin: guarda la "carcasa" de la app para que abra rápido.
// Los datos de pedidos NUNCA se guardan en caché: siempre se piden al servidor con tu sesión.
const CACHE = "chapita-admin-v1";
const SHELL = ["/admin/", "/admin/index.html", "/admin/manifest.webmanifest", "/admin/icon-192.png", "/img/zonas-huella.webp", "/img/zonas-nfc.webp"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return; // API y Supabase: siempre red
  e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request)));
});
self.addEventListener("notificationclick", (e) => { e.notification.close(); e.waitUntil(self.clients.openWindow("/admin/")); });
