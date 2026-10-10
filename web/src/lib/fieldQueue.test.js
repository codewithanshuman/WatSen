import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { IDBFactory } from 'fake-indexeddb'
import { queueFieldObservation, listFieldQueue, listFieldReceipts, syncFieldQueue } from './fieldQueue.js'

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { onLine: true } })
})
const assessment = { predicted_taxon: 'Gammaridae', taxon_confidence: .6, model: 'demo-image-assist-1', image_quality: { score: .85 } }
const capture = () => queueFieldObservation({ file: new File(['photo bytes'], 'sample.png', { type: 'image/png' }), segment: { code: 'PT-CBR-01', name: 'Test reach', lat: 40, lon: -8 }, captureQuality: { score: 75 } })
const receipt = payload => ({ observation: { id: 'obs-1', client_submission_id: payload.client_submission_id }, impact_receipt: { receipt_id: 'receipt-1', observation_id: 'obs-1', status: 'pending_review' } })

test('offline capture remains stored without attempting an upload', async () => {
  await capture(); navigator.onLine = false
  const result = await syncFieldQueue({ classify() { throw new Error('Must not upload') } })
  assert.equal(result.offline, true)
  assert.equal((await listFieldQueue()).length, 1)
  assert.equal((await listFieldReceipts()).length, 0)
})

test('lost acknowledgment retries identical payload without reclassification', async () => {
  await capture()
  let classifications = 0, submissions = []
  const api = { classify: async () => { classifications++; return assessment }, submit: async payload => {
    submissions.push(structuredClone(payload))
    if (submissions.length === 1) throw new Error('Connection lost after server commit')
    return receipt(payload)
  } }
  await syncFieldQueue(api)
  assert.equal((await listFieldQueue())[0].state, 'retry')
  assert.equal((await syncFieldQueue(api)).skipped.length, 1)
  await syncFieldQueue(api, { force: true })
  assert.equal(classifications, 1)
  assert.deepEqual(submissions[0], submissions[1])
  assert.equal((await listFieldQueue()).length, 0)
  assert.equal((await listFieldReceipts()).length, 1)
})

test('incomplete receipt never deletes the only photo', async () => {
  await capture()
  await syncFieldQueue({ classify: async () => assessment, submit: async () => ({ observation: { id: 'obs-1' } }) })
  assert.equal((await listFieldQueue()).length, 1)
  assert.equal((await listFieldReceipts()).length, 0)
})

test('concurrent callers share one sync; validation failures stop automatic retry', async () => {
  await capture()
  let submissions = 0
  const api = { classify: async () => assessment, submit: async () => { submissions++; throw Object.assign(new Error('Conflict'), { status: 409 }) } }
  await Promise.all([syncFieldQueue(api), syncFieldQueue(api)])
  assert.equal(submissions, 1)
  assert.equal((await listFieldQueue())[0].state, 'blocked')
  await syncFieldQueue(api, { force: true })
  assert.equal(submissions, 1)
})
