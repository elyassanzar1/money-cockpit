// Minimal offline shell. App data always comes fresh from the server when online.
const CACHE = "cockpit-v1";
const SHELL = ["/", "/static/styles.css", "/static/app.js", "/manifest.json"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // never cache live financial data
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
