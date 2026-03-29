/** Bump this when shell assets (icons, manifest) change so clients drop stale cache. */
const CACHE_NAME = "cheer-tracker-shell-v5";
const ICON_QUERY = "?v=5";

const APP_SHELL = [
  "/",
  `/manifest.webmanifest${ICON_QUERY}`,
  `/icon-192.png${ICON_QUERY}`,
  `/icon-512.png${ICON_QUERY}`,
  `/apple-touch-icon.png${ICON_QUERY}`,
];

function isShellAssetUrl(url) {
  const p = url.pathname;
  if (p === "/manifest.webmanifest") return true;
  if (p === "/apple-touch-icon.png") return true;
  if (p.startsWith("/icon-") && p.endsWith(".png")) return true;
  return false;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(async () => {
          const cachedPage = await caches.match(event.request);
          return cachedPage || caches.match("/");
        }),
    );
    return;
  }

  // Icons & manifest: network-first so new artwork ships without waiting for cache expiry.
  if (isShellAssetUrl(url)) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request)),
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      });
    }),
  );
});
