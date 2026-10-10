import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
function worker(fetchImpl) {
  const handlers = {}, saved = new Map(), deleted = []
  const cache = { match: async req => saved.get(typeof req === 'string' ? req : req.url)?.clone(), put: async (req, res) => saved.set(typeof req === 'string' ? req : req.url, res.clone()), addAll: async () => {} }
  const context = { self: { location: { origin: 'https://test.watsen' }, addEventListener: (type, fn) => { handlers[type] = fn }, clients: { claim: async () => {} }, skipWaiting: async () => {} }, caches: { open: async () => cache, match: cache.match, keys: async () => ['other-app-cache', 'watsen-shell-old'], delete: async key => { deleted.push(key) } }, fetch: fetchImpl, URL, Headers, Response, AbortSignal, Date }
  vm.runInNewContext(source, context)
  const request = (path, mode) => {
    let result
    handlers.fetch({ request: { url: `https://test.watsen${path}`, method: 'GET', mode }, respondWith: p => { result = p } })
    return result
  }
  return { handlers, saved, deleted, request }
}

test('offline API returns saved response with age; failures cannot overwrite it', async () => {
  let fail = false
  const app = worker(async () => fail ? new Response('unavailable', { status: 500 }) : new Response('{"segments":[]}', { headers: { 'Content-Type': 'application/json' } }))
  const online = await app.request('/v1/segments')
  assert.equal(online.status, 200)
  fail = true
  const offline = await app.request('/v1/segments')
  assert.equal(offline.headers.get('X-WatSen-Cache'), 'offline')
  assert.ok(offline.headers.get('X-WatSen-Cached-At'))
  assert.deepEqual(await offline.json(), { segments: [] })
  assert.equal((await app.request('/v1/unknown')).status, 503)
})

test('navigation falls back to shell and review receipts are not cached', async () => {
  const app = worker(async () => { throw new Error('offline') })
  app.saved.set('/index.html', new Response('<div>WatSen</div>'))
  assert.equal(await (await app.request('/', 'navigate')).text(), '<div>WatSen</div>')
  assert.equal(app.request('/v1/observations/id/receipts'), undefined)
  let activation
  app.handlers.activate({ waitUntil: promise => { activation = promise } })
  await activation
  assert.deepEqual(app.deleted, ['watsen-shell-old'])
})

test('production worker precaches every generated JS and CSS chunk', () => {
  const built = readFileSync(new URL('../dist/sw.js', import.meta.url), 'utf8')
  assert.doesNotMatch(built, /__WATSEN_BUILD__/)
  const paths = JSON.parse(built.match(/const PRECACHE = (\[[^\n]+\])/)[1])
  assert.ok(paths.some(path => /Dashboard-.*\.js$/.test(path)), 'Offline workspace chunk missing')
  for (const path of paths.filter(path => path !== '/')) assert.ok(existsSync(new URL(`../dist${path}`, import.meta.url)), path)
})
