const isLocalDevServer = ['localhost', '127.0.0.1'].includes(window.location.hostname)
  && ['3000', '4173', '5173'].includes(window.location.port)
const BASE = import.meta.env.VITE_API_BASE || (isLocalDevServer ? 'http://localhost:8000' : '')

async function get(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

export const api = {
  health: () => get('/health'),
  scenarios: () => get('/v1/scenarios'),
  segments: (scenario) => get('/v1/segments', { scenario }),
  geojson: (scenario, horizon = 0) => get('/v1/segments.geojson', { scenario, horizon }),
  segment: (code, scenario) => get(`/v1/segments/${code}`, { scenario }),
  history: (code, hours, scenario) => get(`/v1/segments/${code}/history`, { hours, scenario }),
  liveContext: (code, refresh = false) => get(`/v1/segments/${code}/live-context`, { refresh }),
  forecast: (code, scenario) => get(`/v1/segments/${code}/forecast`, { scenario }),
  brief: (code, scenario) => get(`/v1/segments/${code}/brief`, { scenario }),
  alerts: (scenario) => get('/v1/alerts', { scenario }),
  observations: (segment_code) => get('/v1/observations', { segment_code, limit: 60 }),
  contributor: (handle) => get(`/v1/contributors/${handle}`),
  hotspots: (scenario) => get('/v1/hotspots', { scenario }),
  failureChain: (code, scenario) => get(`/v1/segments/${code}/failure-chain`, { scenario }),
  interventions: (code, scenario, weights = null) => get(`/v1/segments/${code}/interventions`, {
    scenario,
    ...Object.fromEntries(Object.entries(weights || {}).map(([key, value]) => [`weight_${key}`, value])),
  }),
  evidenceGraph: (code, scenario) => get(`/v1/segments/${code}/evidence-graph`, { scenario }),
  sufficiency: (code, scenario) => get(`/v1/segments/${code}/data-sufficiency`, { scenario }),
  oneHealth: (code, scenario) => get(`/v1/segments/${code}/one-health`, { scenario }),
  incident: (code, scenario) => get(`/v1/segments/${code}/incident`, { scenario }),
  modelCard: () => get('/v1/models/watforecast'),
  reviewQueue: () => get('/v1/review-queue'),
  fhirValidation: (code, scenario) => get(`/v1/segments/${code}/fhir/validate`, { scenario }),
  fhirUrl: (code, scenario) => `${BASE}/v1/segments/${code}/fhir?scenario=${scenario}`,
  submit: async (payload) => {
    const res = await fetch(`${BASE}/v1/observations`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json()
    if (!res.ok) throw new Error(body.detail || 'Submission failed')
    return body
  },
  classify: async (file) => {
    const form = new FormData()
    form.append('image', file)
    const res = await fetch(`${BASE}/v1/classify`, { method: 'POST', body: form })
    const body = await res.json()
    if (!res.ok) throw new Error(body.detail || 'Image assessment failed')
    return body
  },
  review: async (id, payload) => {
    const res = await fetch(`${BASE}/v1/observations/${id}/review`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json()
    if (!res.ok) throw new Error(body.detail || 'Review failed')
    return body
  },
}

export const BAND = {
  good:    { label: 'Good',    color: '#1688d4' },
  fair:    { label: 'Fair',    color: '#e79a2d' },
  poor:    { label: 'Poor',    color: '#e35f56' },
  severe:  { label: 'Severe',  color: '#a83150' },
  unknown: { label: 'No data', color: '#8294ad' },
}
