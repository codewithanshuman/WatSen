const DB_NAME = 'watsen-field-v1'
const STORE = 'observations'

function openQueue() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore(STORE, { keyPath: 'id' })
      store.createIndex('created_at', 'created_at')
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function transaction(mode, operation) {
  const database = await openQueue()
  try {
    return await new Promise((resolve, reject) => {
      const tx = database.transaction(STORE, mode)
      const store = tx.objectStore(STORE)
      const request = operation(store)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
  } finally {
    database.close()
  }
}

export async function queueFieldObservation({ file, segment, captureQuality }) {
  const id = crypto.randomUUID?.() || `field-${Date.now()}-${Math.random().toString(16).slice(2)}`
  const record = {
    id, created_at: new Date().toISOString(), state: 'queued', attempts: 0,
    segment: { code: segment.code, name: segment.name, city: segment.city, lat: segment.lat, lon: segment.lon },
    file, file_name: file.name, file_type: file.type, capture_quality: captureQuality,
    last_error: null,
  }
  await transaction('readwrite', store => store.put(record))
  return record
}

export async function listFieldQueue() {
  const records = await transaction('readonly', store => store.getAll())
  return records.sort((a, b) => b.created_at.localeCompare(a.created_at))
}

export async function removeFieldObservation(id) {
  await transaction('readwrite', store => store.delete(id))
}

async function updateRecord(record) {
  await transaction('readwrite', store => store.put(record))
}

export async function syncFieldQueue(api) {
  if (!navigator.onLine) return { receipts: [], failed: [], offline: true }
  const records = await listFieldQueue()
  const receipts = [], failed = []
  for (const record of records) {
    const syncing = { ...record, state: 'syncing', attempts: record.attempts + 1, last_error: null }
    await updateRecord(syncing)
    try {
      const file = new File([record.file], record.file_name, { type: record.file_type })
      const assessment = await api.classify(file)
      const result = await api.submit({
        segment_code: record.segment.code, observed_at: record.created_at,
        lat: record.segment.lat, lon: record.segment.lon, contributor: 'offline-field-user',
        note: 'Offline field capture synchronized after connectivity returned.',
        predicted_taxon: assessment.predicted_taxon,
        taxon_confidence: assessment.taxon_confidence, n_photos: 1,
        model: assessment.model,
        image_quality: { ...assessment.image_quality, client_capture_score: record.capture_quality.score },
      })
      receipts.push({ queue_id: record.id, segment: record.segment, assessment, ...result })
      await removeFieldObservation(record.id)
    } catch (error) {
      const failedRecord = { ...syncing, state: 'retry', last_error: error.message || 'Synchronization failed' }
      await updateRecord(failedRecord)
      failed.push(failedRecord)
    }
  }
  return { receipts, failed, offline: false }
}
