const CACHE = 'watsen-shell-v4'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/assets/logo.png', '/assets/watsen-mark.svg', '/assets/field-camera.png']

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE)
    const response = await fetch('/index.html', { cache: 'no-store' })
    const html = await response.clone().text()
    const bundles = [...html.matchAll(/(?:src|href)="(\/assets\/[^"?]+)["?]/g)].map(match => match[1])
    await cache.put('/index.html', response)
    await cache.addAll([...new Set([...SHELL, ...bundles])])
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()))
})

self.addEventListener('fetch', event => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone()
      caches.open(CACHE).then(cache => cache.put('/index.html', copy))
      return response
    }).catch(() => caches.match('/index.html')))
    return
  }
  if (url.pathname.startsWith('/v1/')) {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone()
      caches.open(CACHE).then(cache => cache.put(request, copy))
      return response
    }).catch(() => caches.match(request)))
    return
  }
  event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
    if (response.ok && url.origin === self.location.origin) {
      const copy = response.clone()
      caches.open(CACHE).then(cache => cache.put(request, copy))
    }
    return response
  })))
})
