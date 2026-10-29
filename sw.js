const CACHE_NAME = 'cittalixo-v3';
const ASSETS = ['/', '/manifest.json'];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;
    event.respondWith(
        fetch(event.request)
            .then(resp => {
                const clone = resp.clone();
                if (event.request.url.includes('/pontos') || event.request.url.endsWith('/')) {
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return resp;
            })
            .catch(() => caches.match(event.request))
    );
});

