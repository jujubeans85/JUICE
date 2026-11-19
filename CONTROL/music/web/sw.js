/* Cache only the public UI shell. API, audio, requests and personal drafts never enter this cache. */
'use strict';
const CACHE = 'juice-music-shell-v1';
const SHELL = ['/music/', '/music/index.html', '/music/style.css', '/music/app.js', '/music/icon.svg', '/music/icon-180.png', '/music/icon-192.png', '/music/icon-512.png', '/music/manifest.webmanifest'];
const PUBLIC_PATHS = new Set(SHELL);
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith('juice-music-shell-') && key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.search || !PUBLIC_PATHS.has(url.pathname)) return;
  event.respondWith(fetch(event.request).then((response) => {
    if (response.ok && response.type === 'basic') {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then((cache) => cache.put(url.pathname, copy)));
    }
    return response;
  }).catch(() => caches.match(url.pathname).then((cached) => cached || Response.error())));
});
