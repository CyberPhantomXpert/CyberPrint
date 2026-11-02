// CyberPrint Pay - Service Worker for PWA installability
const CACHE_NAME = 'cyberprint-v3';
const ASSETS = [
  './',
  './index.html',
  './admin.html',
  './config.js?v=3',
  './manifest.json',
  './manifest-admin.json',
  './icon-192.png',
  './icon-512.png',
  './lottie_light.min.js',
  './printer-printing.json'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((k) => {
          if (k !== CACHE_NAME) return caches.delete(k);
        })
      );
    })
  );
  return self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  // CRITICAL: NEVER intercept cross-origin requests (e.g. Supabase Storage / REST API)
  // or non-GET requests (file upload POSTs, update PATCHes).
  if (e.request.method !== 'GET') return;
  if (!e.request.url.startsWith(self.location.origin)) return;

  e.respondWith(
    fetch(e.request).catch(() => {
      return caches.match(e.request);
    })
  );
});
