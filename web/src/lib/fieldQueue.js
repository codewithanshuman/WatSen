const DB_NAME = 'watsen-field-v1'
let inFlight = null

function openQueue() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 2)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains('observations')) db.createObjectStore('observations', { keyPath: 'id' })
      if (!db.objectStoreNames.contains('receipts')) db.createObjectStore('receipts', { keyPath: 'id' })
    }
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close()
      resolve(request.result)
    }
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('Close other WatSen tabs to finish the field storage upgrade.'))
  })
}

async function transaction(stores, mode, operation) {
  const db = await openQueue()
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(stores, mode)
      let result
      tx.oncomplete = () => resolve(result)
      tx.onabort = () => reject(tx.error || new Error('Device storage transaction interrupted.'))
      tx.onerror = () => reject(tx.error)
      const request = operation(tx)
      if (request) request.onsuccess = () => { result = request.result }
    })
  } finally { db.close() }
}

const put = record => transaction(['observations'], 'readwrite', tx => tx.objectStore('observations').put(record))
export async function queueFieldObservation({ file, segment, captureQuality, reviewPreview = null, id = crypto.randomUUID(), note = '', observedAt = new Date().toISOString(), assessment = null }) {
  const existing = await transaction(['observations'], 'readonly', tx => tx.objectStore('observations').get(id))
  if (existing) return existing
  const record = {
    id, created_at: new Date().toISOString(), observed_at: observedAt, state: 'queued', attempts: 0,
    segment: { code: segment.code, name: segment.name, city: segment.city, lat: segment.lat, lon: segment.lon },
    file, file_name: file.name, file_type: file.type, capture_quality: captureQuality,
    note, assessment, review_preview: reviewPreview, last_error: null, next_retry_at: null,
  }
  await put(record)
  return record
}

export async function listFieldQueue() {
  const records = await transaction(['observations'], 'readonly', tx => tx.objectStore('observations').getAll())
  return records.sort((a, b) => a.created_at.localeCompare(b.created_at))
}

export async function listFieldReceipts() {
  const records = await transaction(['receipts'], 'readonly', tx => tx.objectStore('receipts').getAll())
  return records.sort((a, b) => b.saved_at.localeCompare(a.saved_at))
}

export function removeFieldObservation(id) {
  return transaction(['observations'], 'readwrite', tx => tx.objectStore('observations').delete(id))
}

function receiptRecord(result) {
  const receipt = result.impact_receipt
  if (!receipt?.receipt_id || receipt.observation_id !== result.observation?.id) throw new Error('Server acknowledgment is incomplete. Your capture remains on this device.')
  return { id: receipt.receipt_id, saved_at: new Date().toISOString(), ...result }
}

export function saveFieldReceipt(result) {
  const record = receiptRecord(result)
  return transaction(['receipts'], 'readwrite', tx => tx.objectStore('receipts').put(record))
}

async function drainQueue(api, { force = false } = {}) {
  const outcome = { receipts: [], failed: [], skipped: [], offline: !navigator.onLine }
  if (outcome.offline) return outcome
  for (const original of await listFieldQueue()) {
    if (!navigator.onLine) { outcome.offline = true; break }
    if (original.state === 'blocked' || (!force && Date.parse(original.next_retry_at) > Date.now())) {
      outcome.skipped.push(original); continue
    }
    const record = { ...original, state: 'syncing', attempts: original.attempts + 1, last_error: null }
    await put(record)
    try {
      if (!record.assessment) {
        record.assessment = await api.classify(new File([record.file], record.file_name, { type: record.file_type }))
        await put(record)
      }
      if (!record.payload) {
        record.payload = {
          client_submission_id: record.id, segment_code: record.segment.code,
          observed_at: record.observed_at || record.created_at, lat: record.segment.lat, lon: record.segment.lon,
          contributor: 'offline-field-user', note: record.note || 'Field capture synchronized from WatSen.',
          predicted_taxon: record.assessment.predicted_taxon,
          taxon_confidence: record.assessment.taxon_confidence, n_photos: 1, model: record.assessment.model,
          image_quality: { ...record.assessment.image_quality, client_capture_score: record.capture_quality?.score ?? null },
        }
        await put(record)
      }
      const result = await api.submit(record.payload)
      const saved = receiptRecord({ ...result, queue_id: record.id, segment: record.segment, review_preview: record.review_preview })
      // Proof and photo deletion commit together, so an interrupted write retains the image.
      await transaction(['observations', 'receipts'], 'readwrite', tx => {
        tx.objectStore('receipts').put(saved)
        tx.objectStore('observations').delete(record.id)
      })
      outcome.receipts.push(saved)
    } catch (error) {
      const blocked = error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)
      const delay = Math.min(300000, 5000 * 2 ** Math.min(record.attempts - 1, 6))
      const failed = { ...record, state: blocked ? 'blocked' : 'retry', last_error: error.message,
        next_retry_at: blocked ? null : new Date(Date.now() + delay).toISOString() }
      await put(failed)
      outcome.failed.push(failed)
    }
  }
  return outcome
}

export function syncFieldQueue(api, options = {}) {
  if (inFlight) return inFlight
  const run = () => drainQueue(api, options)
  inFlight = (navigator.locks
    ? navigator.locks.request('watsen-field-sync', { ifAvailable: true }, lock => lock ? run() : { receipts: [], failed: [], skipped: [], locked: true })
    : run()).finally(() => { inFlight = null })
  return inFlight
}
