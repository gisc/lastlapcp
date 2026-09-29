const CACHE = 'lastlapcp-v2';
const ASSETS = ['/static/style.css', '/static/icon.svg', '/static/manifest.json',
  '/static/pyodide/pyodide.js', '/static/pyodide/pyodide.asm.js', '/static/pyodide/pyodide.asm.wasm',
  '/static/pyodide/python_stdlib.zip', '/static/pyodide/pyodide-lock.json'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))); self.skipWaiting();
});
self.addEventListener('activate', e => { e.waitUntil(clients.claim()); });
self.addEventListener('fetch', e => {
  if (e.request.url.includes('/static/')) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
