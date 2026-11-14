// Court app service worker, served at /court/sw.js with scope /court/.
// The server replaces __VERSION__ and __FILES__; a new release therefore
// installs a new worker with its own cache. The new worker waits until the
// app tells it no match is being scored (see main.js), so code never
// changes in the middle of a match.
const VERSION = "__VERSION__";
const FILES = __FILES__;
const CACHE = `sf-court-${VERSION}`;

self.addEventListener("install", (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE);
        // Bypass the HTTP cache so the new release is stored, not an old copy.
        await Promise.all(FILES.map(async (url) => {
            const response = await fetch(url, { cache: "reload", credentials: "same-origin" });
            if (!response.ok) throw new Error(`Could not store ${url}`);
            await cache.put(url, response);
        }));
    })());
});

self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
        for (const name of await caches.keys()) {
            if (name.startsWith("sf-court-") && name !== CACHE) await caches.delete(name);
        }
        await self.clients.claim();
    })());
});

self.addEventListener("message", (event) => {
    if (event.data?.type === "activate-update") self.skipWaiting();
    if (event.data?.type === "version") event.ports[0]?.postMessage({ version: VERSION });
});

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);
    if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
    // Data never comes from the cache: the app keeps its own copy in IndexedDB.
    if (url.pathname.startsWith("/court/api/")) return;
    if (url.pathname === "/court/app") {
        event.respondWith((async () => {
            try {
                const response = await fetch(event.request);
                if (response.ok) (await caches.open(CACHE)).put("/court/app", response.clone());
                return response;
            } catch {
                return (await caches.match("/court/app")) || Response.error();
            }
        })());
        return;
    }
    if (FILES.includes(url.pathname)) {
        event.respondWith((async () => (await caches.match(url.pathname)) || fetch(event.request))());
    }
});
