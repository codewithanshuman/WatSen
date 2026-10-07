import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Area, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, BAND } from './lib/api'
import Icon from './components/Icon'

const HOURS = 168
const VIEWS = [
  { id: 'Network', label: 'Overview', icon: 'grid' },
  { id: 'Evidence', label: 'Field studio', icon: 'camera' },
  { id: 'One Health', label: 'One Health', icon: 'health' },
  { id: 'Standards', label: 'Evidence & export', icon: 'layers' },
]

export default function Dashboard({ initialView = 'Network', onHome, onNavigate }) {
  const [view, setView] = useState(initialView)
  const [refresh, setRefresh] = useState(0)
  const [detailLoading, setDetailLoading] = useState(true)
  const [connection, setConnection] = useState(null)
  const [alerts, setAlerts] = useState(null)
  useEffect(() => setView(initialView), [initialView])
  const navigate = next => { setView(next); onNavigate?.(next); window.scrollTo({ top: 0, behavior: 'instant' }) }
  const [scenario, setScenario] = useState('storm')
  const [scenarios, setScenarios] = useState([])
  const [segments, setSegments] = useState([])
  const [active, setActive] = useState(null)
  const [history, setHistory] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [brief, setBrief] = useState(null)
  const [observations, setObservations] = useState([])
  const [geojson, setGeojson] = useState(null)
  const [horizon, setHorizon] = useState(0)
  const [hotspots, setHotspots] = useState([])
  const [failure, setFailure] = useState(null)
  const [interventions, setInterventions] = useState(null)
  const [sufficiency, setSufficiency] = useState(null)
  const [oneHealth, setOneHealth] = useState(null)
  const [graph, setGraph] = useState(null)
  const [incident, setIncident] = useState(null)
  const [reviewQueue, setReviewQueue] = useState(null)
  const [fhirCheck, setFhirCheck] = useState(null)
  const [modelCard, setModelCard] = useState(null)
  const [liveContext, setLiveContext] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.scenarios(), api.modelCard(), api.health()]).then(([s, m, h]) => {
      if (cancelled) return
      setScenarios(s.scenarios); setModelCard(m); setConnection(h)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [refresh])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([api.segments(scenario), api.alerts(scenario)])
      .then(([s, a]) => {
        if (cancelled) return
        setSegments(s.segments); setAlerts(a.alerts)
        setActive(cur => cur && s.segments.some(x => x.code === cur) ? cur : s.segments[0]?.code)
        setError(null)
      })
      .catch(() => { if (!cancelled) setError('The water network is unavailable. Check the connection, then refresh.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    api.hotspots(scenario).then(h => { if (!cancelled) setHotspots(h.hotspots) }).catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [scenario, refresh])

  useEffect(() => {
    let cancelled = false
    api.geojson(scenario, horizon).then(g => { if (!cancelled) setGeojson(g) }).catch(() => {})
    return () => { cancelled = true }
  }, [scenario, horizon, refresh])

  useEffect(() => {
    if (!active) return
    let cancelled = false
    setDetailLoading(true); setBrief(null)
    setForecast(null); setHistory(null); setFailure(null); setInterventions(null)
    setSufficiency(null); setOneHealth(null); setGraph(null); setIncident(null); setFhirCheck(null); setObservations([]); setReviewQueue(null); setLiveContext(null)
    Promise.all([
      api.history(active, HOURS, scenario), api.forecast(active, scenario),
      api.observations(active), api.failureChain(active, scenario),
      api.interventions(active, scenario), api.sufficiency(active, scenario),
      api.oneHealth(active, scenario), api.evidenceGraph(active, scenario),
      api.incident(active, scenario), api.fhirValidation(active, scenario), api.reviewQueue(),
    ]).then(([h, f, o, fc, it, ds, oh, eg, inc, fv, rq]) => {
      if (cancelled) return
      setHistory(h); setForecast(f); setObservations(o.observations)
      setFailure(fc); setInterventions(it); setSufficiency(ds); setOneHealth(oh)
      setGraph(eg); setIncident(inc); setFhirCheck(fv); setReviewQueue(rq)
    }).catch(e => { if (!cancelled) setError(e.message) }).finally(() => { if (!cancelled) setDetailLoading(false) })
    api.brief(active, scenario).then(b => { if (!cancelled) setBrief(b) }).catch(() => {})
    api.liveContext(active).then(context => { if (!cancelled) setLiveContext(context) }).catch(() => {
      if (!cancelled) setLiveContext({ mode: 'unavailable', status: 'unavailable', current: [], next_24h: {}, source: { name: 'Open-Meteo Forecast API' }, limitations: ['Live context could not be reached. No demo value was substituted.'] })
    })
    return () => { cancelled = true }
  }, [active, scenario, refresh])

  const refreshEvidence = async () => setRefresh(value => value + 1)

  const seg = segments.find(s => s.code === active)
  const networkHealth = segments.length ? Math.round(100 - segments.reduce((a, s) => a + s.stress, 0) / segments.length) : 0
  const activeAlerts = alerts?.length ?? '—'
  const emerging = hotspots.filter(h => h.emerging).length
  const predictedPeak = forecast?.points?.length ? Math.max(...forecast.points.map(point => point.value)) : null

  const commands = [
    ...VIEWS.map(v => ({ label: `Open ${v.label}`, action: () => navigate(v.id), meta: 'Workspace' })),
    ...segments.map(s => ({ label: `Inspect ${s.name}`, action: () => { setActive(s.code); navigate('Network') }, meta: s.city })),
    ...scenarios.map(s => ({ label: `Simulate ${s.key}`, action: () => setScenario(s.key), meta: 'Scenario' })),
  ]

  const titles = { Network: ['Your water. In focus.', 'A connected view of your catchment, from today’s signals to tomorrow’s decisions.'], Evidence: ['Small observations. Big picture.', 'Capture a sample, review the evidence and strengthen the biological record.'], 'One Health': ['One water system. Shared health.', 'Connect environmental changes to ecosystem, animal and human wellbeing.'], Standards: ['Every insight has a source.', 'Explore the model, trace the evidence and take your data with you.'] }
  return <div className="app-shell">
    <a className="skip-link" href="#workspace-content" onClick={event => { event.preventDefault(); document.getElementById('workspace-content')?.focus() }}>Skip to workspace</a>
    <header className="workspace-header">
      <button className="brand" onClick={onHome} aria-label="WatSen home"><img src="/assets/logo.png" alt=""/><b>WatSen<span> / workspace</span></b></button>
      <nav className="main-nav" aria-label="Workspace navigation">{VIEWS.map(v => <button key={v.id} aria-current={view === v.id ? 'page' : undefined} className={view === v.id ? 'active' : ''} onClick={() => navigate(v.id)}><Icon name={v.icon} size={18}/><span>{v.label}</span></button>)}</nav>
      <button className="home-link" onClick={onHome}>Back to home <Icon name="diagonal" size={16}/></button>
    </header>
    <div className="workspace-toolbar">
      <div className="connection-state"><i className={error ? 'offline-dot' : 'live-dot'}/><span>{error ? 'Connection interrupted' : connection?.backend === 'mock' ? 'Demo environment' : connection ? 'Connected' : 'Connecting'}</span></div>
      <CommandSearch items={commands}/>
      <button className="icon-button" title="Refresh evidence" aria-label="Refresh evidence" disabled={loading || detailLoading} onClick={refreshEvidence}><Icon name="refresh"/></button>
    </div>
    <main className="workspace-main" id="workspace-content" tabIndex={-1}>
      <div className="page-head"><div><p className="eyebrow"><span/> {VIEWS.find(v => v.id === view)?.label}</p><h1>{titles[view][0]}</h1><p>{titles[view][1]}</p></div><button className="primary" onClick={() => navigate(view === 'Evidence' ? 'Network' : 'Evidence')}><Icon name={view === 'Evidence' ? 'grid' : 'camera'} size={17}/>{view === 'Evidence' ? 'View catchment' : 'Add observation'}<Icon name="arrow" size={17}/></button></div>
      <section className="reach-toolbar" aria-label="Reach and scenario selection">
        <label className="reach-select"><span className="select-icon"><Icon name="pin"/></span><span><small>Selected reach</small><select aria-label="Selected reach" value={active || ''} onChange={e => setActive(e.target.value)}>{!segments.length && <option value="">Loading reaches…</option>}{segments.map(s => <option key={s.code} value={s.code}>{s.name} · {s.city}</option>)}</select></span></label>
        <div className="scenario-controls"><span>Scenario</span><div role="group" aria-label="Scenario">{(scenarios.length ? scenarios : [{ key: 'none' }, { key: 'storm' }, { key: 'heatwave' }, { key: 'spill' }]).map(s => <button key={s.key} aria-pressed={scenario === s.key} className={scenario === s.key ? 'selected' : ''} onClick={() => setScenario(s.key)}>{s.key === 'none' ? 'Baseline' : s.key}</button>)}</div></div>
      </section>
      {scenario !== 'none' && <div className="scenario-banner"><Icon name="layers" size={15}/><b>{scenario} simulation</b><p>{scenarios.find(s => s.key === scenario)?.description}</p></div>}
      {error && <div className="error-banner" role="alert"><Icon name="alert"/>{error}<button onClick={refreshEvidence}>Try again</button></div>}
      {loading && !seg ? <div className="workspace-loading" role="status"><span className="loading-orb"/><h2>Bringing your catchment into focus</h2><p>Connecting the sensor and biological evidence.</p></div> : <div className="view-content" key={view}>
        {detailLoading && <div className="sync-note" role="status"><span/> Updating the selected reach…</div>}
        {view === 'Network' && <CommandCentre {...{seg, segments, networkHealth, activeAlerts, emerging, predictedPeak, geojson, horizon, setHorizon, setActive, hotspots, history, forecast, failure, interventions, sufficiency, liveContext}} onEvidence={() => navigate('Evidence')} />}
        {view === 'Evidence' && <EvidenceLoop key={active} {...{seg, observations, reviewQueue, graph, incident, refreshEvidence}} />}
        {view === 'One Health' && <OneHealthView {...{oneHealth, brief}} />}
        {view === 'Standards' && <InteropView {...{seg, scenario, fhirCheck, modelCard, forecast}} />}
      </div>}
      <footer className="workspace-footer"><span><Icon name="wave" size={16}/> WatSen · Clarity for every catchment.</span><button onClick={onHome}>Explore WatSen <Icon name="arrow" size={14}/></button><span>Built with care for water.</span></footer>
    </main>
  </div>
}

function CommandCentre({ seg, segments, networkHealth, activeAlerts, emerging, predictedPeak, geojson, horizon, setHorizon, setActive, hotspots, history, forecast, failure, interventions, sufficiency, liveContext, onEvidence }) {
  const [chosen, setChosen] = useState(null)
  useEffect(() => setChosen(null), [interventions?.segment_code, interventions?.scenario])
  const recommendation = chosen || interventions?.recommended
  const intervention = interventions?.interventions.find(x => x.key === recommendation)
  const chart = useForecastChart(history, forecast, intervention)
  const accepted = segments.reduce((a, s) => a + (s.biological_evidence?.n_observations || 0), 0)
  const liveValues = Object.fromEntries((liveContext?.current || []).map(item => [item.key, item]))
  return <>
    <section className="catchment-summary">
      <div className="summary-copy"><p className="eyebrow"><Icon name="wave" size={15}/> Catchment intelligence</p><h2>{seg?.name || 'Your catchment'}</h2><p>{failure?.primary_driver ? <>Watch for <strong>{failure.primary_driver.toLowerCase()}</strong>. Explore the forecast and compare possible responses below.</> : 'Connecting the latest environmental signals with the biological record.'}</p><div className="summary-tags"><span><Icon name="pin" size={14}/>{seg?.city || 'European network'}</span><span><Icon name="clock" size={14}/>72-hour outlook</span><span>{seg?.code}</span></div></div>
      <div className="summary-readings">
        <div><span>Current stress</span><strong>{seg ? Math.round(seg.stress) : '—'}<small>/100</small></strong><p className={seg?.band}>{BAND[seg?.band]?.label || 'Loading'} condition</p></div>
        <Icon name="arrow" size={24}/>
        <div><span>Forecast peak</span><strong>{predictedPeak == null ? '—' : Math.round(predictedPeak)}<small>/100</small></strong><p>Within 72 hours</p></div>
      </div>
    </section>
    <section className={`live-context ${liveContext?.mode || 'loading'}`} aria-label="Live environmental context">
      <div className="live-context-title">
        <span className="live-context-icon"><Icon name="spark" size={18}/></span>
        <span><small>External evidence layer</small><b>Live climate context</b></span>
        <em>{liveContext?.mode === 'live' ? 'LIVE' : liveContext ? 'UNAVAILABLE' : 'CONNECTING'}</em>
      </div>
      <div className="live-context-values">
        <span><small>Air temperature</small><b>{liveValues.temperature_2m ? `${liveValues.temperature_2m.value}${liveValues.temperature_2m.unit}` : '—'}</b></span>
        <span><small>Current precipitation</small><b>{liveValues.precipitation ? `${liveValues.precipitation.value} ${liveValues.precipitation.unit}` : '—'}</b></span>
        <span><small>Next 24 h</small><b>{liveContext?.next_24h?.precipitation_sum_mm == null ? '—' : `${liveContext.next_24h.precipitation_sum_mm} mm`}</b></span>
        <span><small>Peak rain chance</small><b>{liveContext?.next_24h?.precipitation_probability_max_pct == null ? '—' : `${liveContext.next_24h.precipitation_probability_max_pct}%`}</b></span>
      </div>
      <div className="live-context-source">
        <span><Icon name="clock" size={14}/>{liveContext?.observed_at ? `${new Date(liveContext.observed_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })} · ${liveContext.timezone}` : 'No live timestamp'}</span>
        <span>{liveContext?.source?.name || 'Connecting to source'}</span>
        <p>{liveContext?.limitations?.[0] || 'Loading source and provenance details…'}</p>
      </div>
    </section>
    <section className="metric-strip" aria-label="Network indicators">
      <Metric label="Network health" value={networkHealth} note="100 − average stress" icon="wave" suffix="/100"/>
      <Metric label="Forecast alerts" value={activeAlerts} note="Across the next 72 hours" icon="alert" tone={activeAlerts > 0 ? 'amber' : ''}/>
      <Metric label="Emerging risks" value={emerging} note="Reaches with a future peak" icon="trend" tone={emerging ? 'red' : ''}/>
      <Metric label="Accepted evidence" value={accepted} note="Citizen records · 30 days" icon="people"/>
    </section>

    <div className="network-layout">
      <section className="panel map-panel">
        <PanelTitle title="Your connected water network" tag={horizon ? '+' + horizon + 'h forecast' : 'Current state'}/>
        <ResilienceMap geojson={geojson} active={seg?.code} onSelect={setActive}/>
        <div className="timeline"><span>Now</span><input aria-label="Forecast horizon" type="range" min="0" max="72" step="12" value={horizon} onChange={e => setHorizon(Number(e.target.value))}/><span>+72h</span><b>{horizon === 0 ? 'Current state' : '+' + horizon + ' hours'}</b></div>
      </section>
      <section className="panel radar-panel">
        <PanelTitle title="Reach watchlist" tag={hotspots.length + ' reaches'}/>
        <p className="panel-subtitle">Current stress → stress at +72h</p>
        <div className="hotspot-list">{hotspots.map((h, i) => <button key={h.segment_code} className={h.segment_code === seg?.code ? 'selected' : ''} onClick={() => setActive(h.segment_code)}><span className="rank">{String(i + 1).padStart(2, '0')}</span><span><b>{h.city}</b><small>{h.segment_code}{h.emerging ? ' · emerging' : ''}</small></span><span className="risk-shift"><b>{Math.round(h.current)}</b><Icon name="arrow" size={13}/><strong>{Math.round(h.at_72h)}</strong></span></button>)}</div>
        <div className="watchlist-note"><Icon name="spark" size={16}/><p>A reach can peak before hour 72. Open its forecast to see the full trajectory.</p></div>
      </section>
    </div>

    <section className="panel forecast-panel">
      <PanelTitle title="A clearer view of what comes next" tag="72-hour forecast"/>
      <div className="forecast-heading"><div><span className="panel-subtitle">Stress trajectory</span><p><b>{predictedPeak == null ? '—' : Math.round(predictedPeak)}</b> forecast peak <span>· {forecast?.interval_label || 'Calculating uncertainty'}</span></p></div><div className="chart-legend"><span><i/>Current evidence</span><span><i/>Forecast</span><span><i/>With intervention</span></div></div>
      <div className="forecast-chart"><ResponsiveContainer width="100%" height={280}><ComposedChart data={chart} margin={{ top: 15, right: 16, bottom: 0, left: -20 }}><defs><linearGradient id="forecast-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5ebaff" stopOpacity={.25}/><stop offset="100%" stopColor="#5ebaff" stopOpacity={.02}/></linearGradient></defs><XAxis dataKey="label" tick={{ fontSize: 11, fill: '#7a94a5' }} interval={Math.max(1, Math.ceil(chart.length / 7))} tickLine={false} axisLine={false} dy={12}/><YAxis domain={[0,100]} tick={{ fontSize: 11, fill: '#7a94a5' }} tickLine={false} axisLine={false}/><Tooltip content={<ChartTip/>}/><ReferenceLine y={50} stroke="#e7eff4" strokeDasharray="4 6"/><ReferenceLine y={75} stroke="#e7eff4" strokeDasharray="4 6"/><Area dataKey="band" stroke="none" fill="url(#forecast-fill)"/><Line dataKey="observed" stroke="#226889" strokeWidth={2.5} dot={false}/><Line dataKey="predicted" stroke="#2fa8ed" strokeWidth={2.5} strokeDasharray="5 5" dot={false}/>{intervention && <Line dataKey="intervention" stroke="#76bca8" strokeWidth={2.5} dot={false}/>}</ComposedChart></ResponsiveContainer></div>
      <div className="forecast-bottom"><Icon name="layers" size={16}/><span>Selected response: <b>{intervention?.name || 'Loading intervention scenarios'}</b></span><a href="#intervention-lab" onClick={event => { event.preventDefault(); document.getElementById('intervention-lab')?.focus() }}>Compare responses <Icon name="arrow" size={14}/></a></div>
    </section>

    <div className="decision-layout">
      <section className="panel failure-panel">
        <PanelTitle title="Follow the evidence" tag={(failure?.confidence ?? '—') + '% confidence'}/>
        <div className="failure-meta"><div><small>Likely driver</small><b>{failure?.primary_driver || 'Connecting evidence'}</b></div><div><small>Onset window</small><b>{failure?.onset_window_h?.join('–') || '—'} hours</b></div></div>
        <SignalTrace nodes={failure?.nodes || []}/>
      </section>
      <aside className="sampling-column">
        <section className="mission-card">
          <span className="mission-icon"><Icon name="camera" size={23}/></span><p className="eyebrow">Your next best measurement</p><h2>{sufficiency?.next_measurements?.[0]?.measurement || 'A closer look at the water'}</h2><p>{sufficiency?.next_measurements?.[0]?.reason || 'Field observations bring the picture into focus.'}</p>
          <div className="mission-box"><b>{sufficiency?.mission?.title || 'Community sampling mission'}</b>{sufficiency?.mission?.needed?.map(n => <span key={n}><Icon name="check" size={15}/>{n}</span>)}</div>
          <button className="primary" onClick={onEvidence}>Open field studio <Icon name="arrow" size={17}/></button>
          <img src="/assets/field-camera.png" alt="" loading="lazy"/>
        </section>
        <section className="confidence-card"><div><Icon name="spark" size={20}/><b>Evidence confidence</b><strong>{sufficiency?.confidence_pct ?? '—'}%</strong></div><div className="confidence-track"><span style={{ width: (sufficiency?.confidence_pct || 0) + '%' }}/></div><p>More independent measurements help reduce uncertainty.</p></section>
      </aside>
    </div>

    <section className="panel intervention-lab" id="intervention-lab" tabIndex={-1}>
      <PanelTitle title="Explore a better outcome" tag="Intervention lab"/>
      <p className="panel-subtitle">Compare simulated responses. Select a card to update the trajectory above.</p>
      <div className="baseline-bar"><span><Icon name="layers" size={17}/>Without intervention</span><b>{interventions?.baseline.critical_stress_hours ?? '—'} <small>critical hours</small></b><b>{interventions?.baseline.peak_stress ?? '—'} <small>peak stress</small></b><b>{interventions?.baseline.minimum_do_mgl ?? '—'} <small>mg/L minimum DO</small></b></div>
      <div className="intervention-grid">{interventions?.interventions.map(x => <button key={x.key} onClick={() => setChosen(x.key)} aria-pressed={recommendation === x.key} className={'intervention ' + (recommendation === x.key ? 'selected' : '')}><span className="intervention-top"><small>{x.key === interventions.recommended ? 'Suggested scenario' : 'Compare response'}</small><i>{recommendation === x.key && <Icon name="check" size={13}/>}</i></span><b>{x.name}</b><span className="intervention-result">{x.ecological_improvement_pct}%<small>estimated improvement</small></span><footer><span>{x.critical_stress_hours} critical hours</span><span>Peak {x.peak_stress}</span></footer></button>)}</div>
      <p className="simulation-note">These estimates support comparison; local ecological conditions and field verification guide the decision.</p>
    </section>
  </>
}

function EvidenceLoop({ seg, observations, reviewQueue, graph, incident, refreshEvidence }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [assessment, setAssessment] = useState(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [reviewing, setReviewing] = useState(null)
  const [reviewMessage, setReviewMessage] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const pending = reviewQueue?.observations.filter(o => o.state === 'needs_review' && o.segment_code === seg?.code) || []
  useEffect(() => {
    if (!file) { setPreview(null); return }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  const chooseFile = event => {
    const selected = event.target.files?.[0]
    setAssessment(null); setSubmitted(false); setMessage('')
    if (!selected) { setFile(null); return }
    if (!['image/jpeg', 'image/png'].includes(selected.type) || selected.size > 12 * 1024 * 1024) {
      setFile(null); event.target.value = ''; setMessage('Choose a JPG or PNG image under 12 MB.'); return
    }
    setFile(selected)
  }
  const classify = async () => {
    if (!file) return
    setBusy(true); setMessage('')
    try { setAssessment(await api.classify(file)) } catch (e) { setMessage(e.message) } finally { setBusy(false) }
  }
  const submit = async () => {
    if (!assessment || !seg || submitted) return
    setBusy(true)
    try {
      const result = await api.submit({
        segment_code: seg.code, observed_at: new Date().toISOString(), lat: seg.lat, lon: seg.lon,
        contributor: 'demo-citizen', note: 'Image-assisted kick sample submitted from the evidence loop.',
        predicted_taxon: assessment.predicted_taxon, taxon_confidence: assessment.taxon_confidence,
        n_photos: 1, model: assessment.model, image_quality: assessment.image_quality,
      })
      setMessage(`${result.validation.explanation} ASPT is now ${result.biological_index.aspt}.`)
      setSubmitted(true)
      await refreshEvidence()
    } catch (e) { setMessage(e.message) } finally { setBusy(false) }
  }
  const review = async (id, action) => {
    setReviewing(id); setReviewMessage('')
    try { await api.review(id, { action, reviewer: 'demo-expert' }); await refreshEvidence(); setReviewMessage('Review saved. The evidence window is being updated.') }
    catch (error) { setReviewMessage(error.message) }
    finally { setReviewing(null) }
  }
  return <>
    <section className="loop-hero"><p className="eyebrow">Closed evidence loop</p><h2>Citizen → AI suggestion → human review → BMWP / ASPT → stream stress</h2><p>Every accepted family changes the biological evidence window. Uncertain records are routed to people, not silently discarded.</p></section>
    <div className="two-col wide-left">
      <section className="panel upload-card"><PanelTitle title="New biological observation" tag="MULTIMODAL" /><div className="upload-zone">{preview ? <img className="upload-preview" src={preview} alt="Uploaded specimen preview" /> : <div className="upload-empty"><img src="/assets/field-camera.png" alt="Illustrated field camera" /><span><b>Choose a macroinvertebrate photo</b><small>JPG or PNG · up to 12 MB</small></span></div>}<input type="file" accept="image/jpeg,image/png" aria-label="Choose a specimen photo" disabled={busy} onChange={chooseFile} /></div><button className="primary" disabled={!file || busy} onClick={classify}>{busy ? 'Assessing…' : 'Run AI assessment'}</button>{assessment && <div className="assessment"><div><Badge kind="inferred" /><h3>{assessment.predicted_taxon}</h3><strong>{Math.round(assessment.taxon_confidence * 100)}%</strong></div><dl><dt>Ecological sensitivity</dt><dd>{assessment.ecological_sensitivity}</dd><dt>BMWP contribution</dt><dd>{assessment.bmwp_contribution}</dd><dt>Image quality</dt><dd>{assessment.image_quality.label} ({assessment.image_quality.score})</dd><dt>Decision</dt><dd>Human confirmation required</dd></dl><p>{assessment.disclaimer}</p><button className="primary" onClick={submit} disabled={busy || submitted}>{submitted ? 'Submitted for validation' : 'Submit for validation'}</button></div>}{message && <p className="feedback" role="status">{message}</p>}</section>
      <section className="panel"><PanelTitle title="Biological state" tag={seg?.biological_evidence?.source?.toUpperCase()} /><div className="bio-score"><strong>{seg?.aspt}</strong><span>ASPT</span></div><dl className="facts"><dt>BMWP total</dt><dd>{seg?.bmwp}</dd><dt>Scoring families</dt><dd>{seg?.biological_evidence?.n_taxa}</dd><dt>Accepted observations</dt><dd>{seg?.biological_evidence?.n_observations}</dd><dt>Evidence confidence</dt><dd>{Math.round((seg?.biological_evidence?.confidence || 0) * 100)}%</dd></dl><div className="taxa-cloud">{seg?.biological_evidence?.families?.map(t => <span key={t}>{t}</span>)}</div></section>
    </div>

    <section className="panel"><PanelTitle title="Expert review queue" tag={`${pending.length} FOR THIS REACH`} /><div className="review-grid">{pending.slice(0, 8).map(o => <article key={o.id}><Badge kind="citizen" /><h3>{o.predicted_taxon || 'Unclassified'}</h3><p>AI confidence {Math.round((o.taxon_confidence || 0) * 100)}% · quality {o.quality_score}</p><small>{o.explanation}</small><div><button disabled={reviewing !== null} onClick={() => review(o.id, 'confirm')}>Confirm</button><button disabled={reviewing !== null} onClick={() => review(o.id, 'reject')}>Reject</button></div></article>)}{!pending.length && <p className="empty">{reviewQueue ? 'No uncertain records are waiting for review in this reach.' : 'Loading the review queue…'}</p>}</div>{reviewMessage && <p className="feedback" role="status">{reviewMessage}</p>}</section>

    <section className="evidence-layout"><div className="panel"><PanelTitle title="Evidence graph" tag="TRACEABLE" /><div className="evidence-graph">{graph?.nodes.map(n => <article key={n.id} className={n.kind}><Badge kind={n.kind} /><b>{n.label}</b><small>{n.evidence}</small><em>{n.source}</em></article>)}</div></div><ContextCards observations={observations} segment={seg} /></section>
    <section className="panel"><PanelTitle title={`Incident replay · ${incident?.id || ''}`} tag="AUDIT TRAIL" /><div className="incident">{incident?.events.map((e, i) => <div key={`${e.at}-${i}`}><time>{fmtTime(e.at)}</time><i /><article><Badge kind={e.type} /><b>{e.title}</b></article></div>)}</div></section>
    <section className="panel"><PanelTitle title="Recent citizen evidence" tag={`${observations.length} RECORDS`} /><ObservationTable rows={observations.slice(0, 12)} /></section>
  </>
}

function OneHealthView({ oneHealth, brief }) {
  return <>
    <section className={`attention ${oneHealth?.attention_level || 'low'}`}><div><p className="eyebrow">One Health attention level</p><h2>{oneHealth?.attention_level}</h2></div><p>{oneHealth?.reason}<small>{oneHealth?.disclaimer}</small></p><img src="/assets/water-bottle.png" alt="Illustrated water bottle" /></section>
    <section className="living-water"><picture><source media="(prefers-reduced-motion: reduce)" srcSet="/assets/landing-water.png"/><img src="/assets/water-loop.gif" alt="Ocean water" loading="lazy"/></picture><div><span>ONE LIVING SYSTEM</span><h2>Water connects ecosystem, animal and human health.</h2><p>WatSen keeps those domains linked without presenting environmental signals as a clinical diagnosis.</p></div></section>
    <section className="domain-grid">{oneHealth && Object.entries(oneHealth.domains).map(([key, values]) => <article className="panel" key={key}><PanelTitle title={key.replaceAll('_', ' / ')} tag="ENVIRONMENTAL SIGNALS" /><dl className="facts">{Object.entries(values).map(([k, v]) => <FragmentPair key={k} label={k.replaceAll('_', ' ')} value={v ?? 'unavailable'} />)}</dl></article>)}</section>
    <section className="panel brief-panel"><PanelTitle title="Evidence-grounded One Health brief" tag={brief?.generator?.toUpperCase() || 'GENERATING'} />{!brief ? <p className="muted">Generating…</p> : <><h2>{brief.headline}</h2><p className="riskline">Risk level <b>{brief.risk_level}</b></p>{['ecosystem', 'animal', 'human', 'what_changes'].map(k => <article key={k}><h3>{k === 'what_changes' ? 'What to watch' : k}</h3><p>{cite(brief[k])}</p></article>)}<details><summary>View evidence and provenance ({brief.evidence?.length || 0})</summary>{brief.evidence?.map(e => <div className="evidence-row" key={e.id}><code>{e.id}</code><span>{e.text}<small>{e.source && `Source: ${e.source}`}</small></span><Badge kind={e.kind} /></div>)}</details></>}</section>
  </>
}

function InteropView({ seg, scenario, fhirCheck, modelCard, forecast }) {
  return <>
    <section className="interop-hero"><div><p className="eyebrow">Interoperability</p><h2>Evidence that can leave the dashboard</h2><p>FHIR R4 resources declare the current OneAquaHealth draft profiles and preserve simulation provenance.</p></div><a className="primary link" href={seg ? api.fhirUrl(seg.code, scenario) : '#'} target="_blank" rel="noreferrer">View FHIR JSON ↗</a></section>
    <div className="two-col">
      <section className="panel"><PanelTitle title="FHIR preflight" tag={fhirCheck?.status?.toUpperCase()} /><div className={`validation ${fhirCheck?.status}`}><strong>{fhirCheck ? fhirCheck.errors.length : '—'}</strong><span>structural errors</span></div>{fhirCheck && !fhirCheck.errors.length ? <ul className="checklist"><li>✓ HL7 FHIR R4 transaction Bundle</li><li>✓ OneAquaHealth Location profile declared</li><li>✓ OAH component Observation profile declared</li><li>✓ OAH Specimen linkage</li><li>✓ Provenance for observed vs simulated data</li></ul> : <p className="muted">{fhirCheck ? fhirCheck.errors.join('; ') : 'Waiting for preflight results…'}</p>}<p className="warning">{fhirCheck?.warnings?.[0]}</p><div className="resource-counts">{fhirCheck && Object.entries(fhirCheck.counts).map(([k, v]) => <span key={k}><b>{v}</b>{k}</span>)}</div></section>
      <section className="panel"><PanelTitle title="Provenance snapshot" tag="FAIR" /><div className="provenance-card"><Badge kind={scenario === 'none' ? 'observed' : 'simulated'} /><h3>{scenario === 'none' ? 'Sensor-derived monitoring state' : `${scenario} scenario output`}</h3><dl><dt>Source</dt><dd>Mechanistically inspired synthetic development dataset</dd><dt>Timestamp</dt><dd>{seg?.updated_at}</dd><dt>Quality</dt><dd>Development evidence</dd><dt>ASPT source</dt><dd>{seg?.biological_evidence?.source}</dd><dt>Forecast model</dt><dd>{forecast?.model_version}</dd></dl></div></section>
    </div>
    <section className="panel model-card"><PanelTitle title={modelCard?.name || 'Model card'} tag="RESPONSIBLE AI" /><div className="model-layout"><div><h3>Purpose</h3><p>{modelCard?.purpose}</p><h3>Intended use</h3><p>{modelCard?.intended_use}</p><h3>Training set</h3><p>{modelCard?.training_set}</p></div><div><h3>Inputs</h3><div className="taxa-cloud">{modelCard?.inputs?.map(x => <span key={x}>{x}</span>)}</div><h3>Known limitations</h3><ul>{modelCard?.known_limitations?.map(x => <li key={x}>{x}</li>)}</ul></div><div><h3>Evaluation</h3>{modelCard && Object.entries(modelCard.evaluation).map(([k, v]) => <div className="eval" key={k}><span>{k.replaceAll('_', ' ')}</span><b>{v}</b></div>)}</div></div></section>
  </>
}

function CommandSearch({ items }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(0)
  const root = useRef(null)
  const results = (query ? items.filter(item => (item.label + ' ' + item.meta).toLowerCase().includes(query.toLowerCase())) : items).slice(0, 7)
  const run = item => { if (!item) return; item.action(); setQuery(''); setOpen(false); root.current?.querySelector('input')?.blur() }
  useEffect(() => {
    const close = event => { if (!root.current?.contains(event.target)) setOpen(false) }
    const shortcut = event => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); root.current?.querySelector('input')?.focus(); setOpen(true)
      }
    }
    document.addEventListener('mousedown', close); document.addEventListener('keydown', shortcut)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', shortcut) }
  }, [])
  const handleKey = event => {
    if (event.key === 'Escape') { setOpen(false); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); setOpen(true)
      setSelected(value => results.length ? (value + (event.key === 'ArrowDown' ? 1 : results.length - 1)) % results.length : 0)
    }
    if (event.key === 'Enter' && open) { event.preventDefault(); run(results[selected]) }
  }
  return <div className="command-search" ref={root} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <span className="search-icon"><Icon name="search" size={17}/></span>
    <input value={query} onFocus={() => { setOpen(true); setSelected(0) }} onChange={e => { setQuery(e.target.value); setSelected(0); setOpen(true) }} onKeyDown={handleKey} placeholder="Search reaches, evidence, actions…" aria-label="Search WatSen" role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls="command-options" aria-activedescendant={open && results[selected] ? 'command-' + selected : undefined}/>
    {query ? <button onClick={() => { setQuery(''); setSelected(0); root.current?.querySelector('input')?.focus() }} aria-label="Clear search"><Icon name="close" size={13}/></button> : <kbd>Ctrl K</kbd>}
    {open && <div className="search-results">
      <header><span>{query ? 'Matching commands' : 'Suggested actions'}</span><b>{results.length}</b></header>
      <div id="command-options" role="listbox" aria-label="Commands">{results.map((item, index) => <button id={'command-' + index} role="option" aria-selected={index === selected} tabIndex={-1} className={index === selected ? 'highlighted' : ''} key={item.label} onMouseDown={event => event.preventDefault()} onClick={() => run(item)}><i><Icon name={item.label.includes('Inspect') ? 'pin' : item.label.includes('Simulate') ? 'layers' : 'arrow'} size={16}/></i><span>{item.label}<small>{item.meta}</small></span><kbd>↵</kbd></button>)}</div>
      {!results.length && <div className="search-empty" role="status"><Icon name="search"/><b>No matching results</b><span>Try a reach, city or workspace.</span></div>}
    </div>}
  </div>
}

function SignalTrace({ nodes }) {
  const [shown, setShown] = useState(0)
  const [expanded, setExpanded] = useState(null)
  useEffect(() => {
    setShown(0)
    if (!nodes.length) return
    const timer = setInterval(() => setShown(value => {
      if (value >= nodes.length) { clearInterval(timer); return value }
      return value + 1
    }), 170)
    return () => clearInterval(timer)
  }, [nodes])
  return <div className="signal-trace">
    <div className="trace-spine" />
    {nodes.map((node, index) => <button key={node.id} className={`trace-node ${index < shown ? 'shown' : ''} ${expanded === node.id ? 'expanded' : ''}`} onClick={() => setExpanded(expanded === node.id ? null : node.id)}>
      <span className="trace-index">{String(index + 1).padStart(2, '0')}</span>
      <span className="trace-pulse"><i /></span>
      <span className="trace-copy"><small>{node.kind}</small><b>{node.label}</b><em>{node.evidence}</em>{expanded === node.id && <p><strong>{Math.round(node.confidence * 100)}%</strong> confidence · {node.source}. This inference remains linked to its source evidence and can be challenged by a new measurement.</p>}</span>
      <span className="trace-confidence">{Math.round(node.confidence * 100)}% <i>{expanded === node.id ? '−' : '+'}</i></span>
    </button>)}
  </div>
}

function ContextCards({ observations = [], segment }) {
  const [chipsShown, setChipsShown] = useState(false)
  useEffect(() => { const timer = setTimeout(() => setChipsShown(true), 500); return () => clearTimeout(timer) }, [])
  const chunks = [
    { title: 'Biological evidence window', chars: `${segment?.biological_evidence?.n_observations || 0} records`, body: `BMWP ${segment?.bmwp ?? '—'} and ASPT ${segment?.aspt ?? '—'} are recomputed from accepted macroinvertebrate families.`, source: 'WatSen evidence ledger', badge: 'BIO', tone: 'blue' },
    { title: 'Latest field contribution', chars: observations[0] ? fmtShort(observations[0].observed_at) : 'Awaiting sample', body: observations[0]?.predicted_taxon ? `${observations[0].predicted_taxon} · confidence ${Math.round((observations[0].taxon_confidence || 0) * 100)}% · ${observations[0].state.replaceAll('_', ' ')}.` : 'No citizen observation is available for this reach yet.', source: 'Citizen science stream', badge: 'OBS', tone: 'cyan' },
  ]
  return <aside className="context-cards">
    <header><span>Evidence context</span><b>{chunks.length}</b></header>
    {chunks.map((chunk, index) => <article key={chunk.title} style={{ animationDelay: `${index * 90}ms` }}>
      <div><span>≡</span><b>{chunk.title}</b><small>{chunk.chars}</small></div>
      <p>{chunk.body}</p>
      <footer style={{ opacity: chipsShown ? 1 : 0, transform: chipsShown ? 'scale(1)' : 'scale(.95)', transitionDelay: `${index * 80}ms` }}><i className={chunk.tone}>{chunk.badge}</i>{chunk.source}<span>↗</span></footer>
    </article>)}
  </aside>
}

function ResilienceMap({ geojson, active, onSelect }) {
  const features = geojson?.features || []
  const coords = features.flatMap(f => f.geometry.coordinates)
  const xs = coords.map(c => c[0]), ys = coords.map(c => c[1])
  const minX = Math.min(...xs, -10), maxX = Math.max(...xs, 28), minY = Math.min(...ys, 38), maxY = Math.max(...ys, 54)
  const point = ([x, y]) => [50 + (x - minX) / (maxX - minX) * 700, 250 - (y - minY) / (maxY - minY) * 205]
  return <div className="map-wrap"><svg viewBox="0 0 800 280" role="group" aria-label="European reach schematic. Select a reach to inspect."><defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#e1edf5" strokeWidth="1" /></pattern><filter id="glow"><feGaussianBlur stdDeviation="5" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs><rect width="800" height="280" fill="url(#grid)" rx="12" /><path className="europe-line" d="M95 180 C180 80, 310 25, 430 85 S650 30, 730 120 M120 210 C260 170, 390 230, 690 170" />{features.map(f => { const pts = f.geometry.coordinates.map(point); const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]} ${p[1]}`).join(' '); const mid = point(f.geometry.coordinates[Math.floor(f.geometry.coordinates.length / 2)]); if (f.properties.code === 'PT-CBR-02') { mid[0] += 12; mid[1] += 40 } const color = (BAND[f.properties.band] || BAND.unknown).color; return <g key={f.properties.code} role="button" tabIndex={0} aria-label={f.properties.city + ', stress ' + Math.round(f.properties.stress) + '. Inspect reach.'} aria-pressed={active === f.properties.code} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(f.properties.code) } }} onClick={() => onSelect(f.properties.code)} className={active === f.properties.code ? 'map-active' : ''}><circle cx={mid[0]} cy={mid[1]} r="22" fill="transparent"/><path d={d} stroke={color} strokeWidth={active === f.properties.code ? 9 : 6} fill="none" strokeLinecap="round" filter={active === f.properties.code ? 'url(#glow)' : undefined} /><circle cx={mid[0]} cy={mid[1]} r={active === f.properties.code ? 9 : 6} fill={color} stroke="#fff" strokeWidth="3" /><text x={mid[0] + 12} y={mid[1] - 9}>{f.properties.city}{f.properties.code === 'PT-CBR-02' ? ' · north' : ''}</text><text className="map-score" x={mid[0] + 12} y={mid[1] + 8}>{Math.round(f.properties.stress)}</text></g>})}</svg><div className="map-layers"><span>Geographic schematic · not to scale</span><span>● Colour indicates stress</span><span>Select a reach to explore</span></div></div>
}

function SegmentButton({ segment: s, active, onClick }) { const band = BAND[s.band] || BAND.unknown; return <button className={`segment-button ${active ? 'active' : ''}`} onClick={onClick}><i style={{ background: band.color }} /><span><b>{s.name}</b><small>{s.city} · ASPT {s.aspt}</small></span><strong style={{ color: band.color }}>{Math.round(s.stress)}</strong></button> }
function Metric({ label, value, note, tone = '', icon = 'wave', suffix }) { return <article className={`metric ${tone}`}><div className="metric-top"><span>{label}</span><i className="metric-icon"><Icon name={icon} size={17}/></i></div><strong>{value}{suffix && <em>{suffix}</em>}</strong><small>{note}</small></article> }
function PanelTitle({ title, tag }) { return <div className="panel-title"><h2>{title}</h2>{tag && <span>{tag}</span>}</div> }
function Badge({ kind = 'observed' }) { return <span className={`badge ${kind}`}>{kind.replaceAll('_', ' ')}</span> }
function FragmentPair({ label, value }) { return <><dt>{label}</dt><dd>{String(value)}</dd></> }

function useForecastChart(history, forecast, intervention) {
  return useMemo(() => {
    if (!history || !forecast) return []
    const past = history.t.map((t, i) => ({ t, label: fmtShort(t), observed: history.stress[i] })).slice(-72)
    const join = past[past.length - 1]
    const fut = forecast.points.map((p, i) => ({ t: p.valid_at, label: fmtShort(p.valid_at), predicted: p.value, band: [p.lower, p.upper], intervention: intervention?.points?.[i]?.value }))
    if (join) fut.unshift({ ...join, predicted: join.observed, band: [join.observed, join.observed], intervention: join.observed })
    return [...past, ...fut]
  }, [history, forecast, intervention])
}

function ChartTip({ active, payload, label }) { if (!active || !payload?.length) return null; const p = payload.reduce((a, x) => ({ ...a, [x.dataKey]: x.value }), {}); return <div className="chart-tip"><b>{label}</b>{p.observed != null && <div>Observed {Number(p.observed).toFixed(1)}</div>}{p.predicted != null && <div>Forecast {Number(p.predicted).toFixed(1)}</div>}{p.intervention != null && <div>With intervention {Number(p.intervention).toFixed(1)}</div>}{Array.isArray(p.band) && <small>Likely range {p.band[0].toFixed(0)}–{p.band[1].toFixed(0)}</small>}</div> }
function ObservationTable({ rows }) { return <div className="table-wrap"><table><thead><tr><th>Time</th><th>Family</th><th>Confidence</th><th>BMWP</th><th>Quality</th><th>State</th></tr></thead><tbody>{rows.map(o => <tr key={o.id}><td>{fmtShort(o.observed_at)}</td><td><b>{o.predicted_taxon || '—'}</b></td><td>{o.taxon_confidence?.toFixed(2) || '—'}</td><td>{o.bmwp_contribution ?? '—'}</td><td>{o.quality_score?.toFixed(2) || '—'}</td><td><span className={`state ${o.state}`}>{o.state.replaceAll('_', ' ')}</span></td></tr>)}</tbody></table></div> }
function cite(text = '') { return text.split(/(\[[A-Z0-9-]+\])/g).map((part, i) => /^\[[A-Z0-9-]+\]$/.test(part) ? <sup key={i}>{part.slice(1, -1)}</sup> : part) }
function fmtShort(iso) { return new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' }) }
function fmtTime(iso) { return new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) }
