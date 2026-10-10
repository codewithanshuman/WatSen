// The build replaces these constants with a content-addressed bundle manifest.
const VERSION = '__WATSEN_BUILD__'
const PRECACHE = ['/', '/index.html', '/manifest.webmanifest', '/assets/logo.png', '/assets/field-camera.png']
const SHELL = `watsen-shell-${VERSION}`
const DATA = `watsen-data-${VERSION}`

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting()))
})
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.filter(key => (key.startsWith('watsen-shell-') || key.startsWith('watsen-data-')) && key !== SHELL && key !== DATA).map(key => caches.delete(key)))
    await self.clients.claim()
  })())
})

async function readEvidence(request) {
  const cache = await caches.open(DATA)
  try {
    const response = await fetch(request, { signal: AbortSignal.timeout(12000) })
    if (response.ok) {
      const headers = new Headers(response.headers)
      headers.set('X-WatSen-Cached-At', new Date().toISOString())
      const copy = new Response(await response.clone().arrayBuffer(), { status: response.status, headers })
      try { await cache.put(request, copy) } catch { /* Full device storage must not hide a successful response. */ }
      return response
    }
    if (response.status < 500) return response
    throw new Error('Server unavailable')
  } catch {
    const cached = await cache.match(request)
    if (cached) {
      const headers = new Headers(cached.headers)
      headers.set('X-WatSen-Cache', 'offline')
      return new Response(await cached.arrayBuffer(), { status: cached.status, headers })
    }
    return new Response(JSON.stringify({ detail: 'No saved evidence for this request. Reconnect to load this reach.' }), { status: 503, headers: { 'Content-Type': 'application/json' } })
  }
}

self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (url.origin !== self.location.origin || request.method !== 'GET') return
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(async response => {
      if (response.ok) return response
      return (await caches.match('/index.html')) || response
    }).catch(() => caches.match('/index.html')))
    return
  }
  if (url.pathname.startsWith('/v1/') || url.pathname === '/health') {
    // Receipt history and review actions must never imply a cached review is current.
    if (url.pathname.endsWith('/receipts') || url.pathname === '/v1/review-queue') return
    event.respondWith(readEvidence(request))
    return
  }
  event.respondWith(caches.match(request).then(cached => cached || fetch(request)))
})
