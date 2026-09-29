const CACHE = 'lastlapcp-v3';
// Precache + cache-first ONLY the big immutable Pyodide bundle (school WiFi).
// App assets (style.css, sw.js, icons) must always come from the network,
// otherwise a deploy never reaches installed clients.
const PYODIDE = ['/static/pyodide/pyodide.js', '/static/pyodide/pyodide.asm.js', '/static/pyodide/pyodide.asm.wasm',
  '/static/pyodide/python_stdlib.zip', '/static/pyodide/pyodide-lock.json'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PYODIDE))); self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.url.includes('/static/pyodide/')) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
