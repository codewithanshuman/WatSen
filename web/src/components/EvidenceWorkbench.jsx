import { useEffect, useState } from 'react'
import Icon from './Icon'
import { api } from '../lib/api'
import { saveFieldReceipt } from '../lib/fieldQueue'
import './evidence-workbench.css'

const readable = value => (value || '').replaceAll('_', ' ')
const time = value => value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Earlier session'
export function downloadEvidence(value, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, (key, item) => key === 'review_preview' ? undefined : item, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url; link.download = `${name}.json`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function ReceiptLedger({ records, onSelect, onRefresh }) {
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')
  const filtered = records.filter(item => filter === 'all' || item.impact_receipt.status === filter)
  const refresh = async () => {
    setLoading(true); setNotice('')
    let missing = 0, added = 0
    try {
      const ids = [...new Set(records.map(r => r.observation.id))]
      for (const id of ids) {
        try {
          const history = await api.receipts(id)
          for (const receipt of history.receipts) {
            if (records.some(r => r.id === receipt.receipt_id)) continue
            const old = records.find(r => r.observation.id === id)
            await saveFieldReceipt({ observation: { ...old.observation, ...receipt.transition?.after }, impact_receipt: receipt })
            added += 1
          }
        } catch { missing += 1 }
      }
      await onRefresh()
      setNotice(`${added} new decision receipt${added === 1 ? '' : 's'} saved.${missing ? ` ${missing} server record${missing === 1 ? ' is' : 's are'} unavailable; device copies remain available.` : ''}`)
    } catch (error) { setNotice(error.message) }
    finally { setLoading(false) }
  }
  return <section className="panel receipt-ledger" aria-label="Saved evidence receipts">
    <div className="workbench-heading"><div><p className="eyebrow">Your evidence trail</p><h2>Every decision, kept on this device.</h2><p>Return to a receipt, check for a review, or take the full record with you.</p></div><span className="ledger-count">{records.length}<small>receipts</small></span></div>
    <div className="ledger-tools"><label>Show<select value={filter} onChange={e => setFilter(e.target.value)} aria-label="Filter receipts"><option value="all">All decisions</option><option value="pending_review">Awaiting review</option><option value="applied">Applied</option><option value="accepted_no_index_change">Accepted / no change</option><option value="not_applied">Excluded</option><option value="reverted">Reverted</option></select></label><button onClick={refresh} disabled={!records.length || loading || !navigator.onLine}><Icon name="refresh" size={14}/>{loading ? 'Checking…' : 'Check for reviews'}</button><button onClick={() => downloadEvidence({ exported_at: new Date().toISOString(), receipts: records }, 'watsen-evidence-ledger')} disabled={!records.length}><Icon name="diagonal" size={14}/>Export ledger</button></div>
    {notice && <p className="feedback" role="status">{notice}</p>}
    <div className="ledger-records">{filtered.slice(0, 30).map(record => <button className="ledger-record" key={record.id} onClick={() => onSelect(record.impact_receipt)}><span className={`receipt-dot ${record.impact_receipt.status}`}/><span><b>{record.impact_receipt.segment_name || record.segment?.name || record.observation.segment_code}</b><small>{record.observation.predicted_taxon || 'Unclassified'} · {time(record.impact_receipt.created_at || record.saved_at)}</small></span><span className="ledger-status">{readable(record.impact_receipt.status)}<small>{readable(record.impact_receipt.event || 'submission')}</small></span><Icon name="arrow" size={15}/></button>)}{!filtered.length && <div className="ledger-empty"><Icon name="layers" size={25}/><b>{records.length ? 'No receipts match this filter.' : 'Your first receipt starts here.'}</b><p>Synchronize a capture or complete a review. The receipt stays available after you close WatSen.</p></div>}</div>
    {filtered.length > 30 && <p className="panel-subtitle">Showing the latest 30 of {filtered.length}. Export includes every saved receipt.</p>}
    <p className="review-scope">The demonstration server can reset. Receipt history and reduced review photos saved on this device remain until browser data is cleared. Exports contain receipt data only.</p>
  </section>
}

export function ReviewWorkbench({ observations = [], records = [], segment, onReviewed }) {
  const [taxa, setTaxa] = useState([])
  const [filter, setFilter] = useState('needs_review')
  const [selected, setSelected] = useState(null)
  const [note, setNote] = useState('')
  const [correction, setCorrection] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [photoUrl, setPhotoUrl] = useState(null)
  useEffect(() => { api.taxa().then(r => setTaxa(r.taxa)).catch(() => {}) }, [])
  const rows = observations.filter(row => row.segment_code === segment?.code && (filter === 'all' || row.state === filter))
  const current = rows.find(row => row.id === selected) || rows[0]
  const reviewPhoto = records.find(record => record.observation.id === current?.id && record.review_preview)?.review_preview
  useEffect(() => {
    if (!reviewPhoto) { setPhotoUrl(null); return }
    const url = URL.createObjectURL(reviewPhoto); setPhotoUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [reviewPhoto])
  useEffect(() => { setNote(''); setCorrection(''); setMessage('') }, [current?.id])
  const review = async action => {
    if (!current) return
    setBusy(true); setMessage('')
    try {
      const result = await api.review(current.id, { action, reviewer: 'demo-expert', reviewer_note: note, corrected_taxon: action === 'correct' ? correction : undefined })
      try { await saveFieldReceipt(result) } catch { setMessage('Review saved on the server, but this device could not keep a copy. Export the displayed receipt now.') }
      await onReviewed(result)
      setSelected(null)
    } catch (error) { setMessage(error.message) }
    finally { setBusy(false) }
  }
  return <section className="panel review-workbench">
    <div className="workbench-heading"><div><p className="eyebrow">Expert workbench · demonstration role</p><h2>Question the suggestion. Record the decision.</h2><p>Confirm an identification, correct the family, or exclude a record with a reason.</p></div><span className="ledger-count">{observations.filter(o => o.segment_code === segment?.code && o.state === 'needs_review').length}<small>awaiting review</small></span></div>
    <div className="review-filters" role="group" aria-label="Review filter">{[['needs_review', 'Needs review'], ['auto_accepted', 'Audit accepted'], ['all', 'All recent']].map(([key, label]) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{label}</button>)}</div>
    {current ? <div className="review-workspace">
      <div className="review-candidates">{rows.map(row => <button key={row.id} aria-pressed={current.id === row.id} onClick={() => setSelected(row.id)}><b>{row.predicted_taxon || 'Unclassified'}</b><span>{readable(row.state)} · {time(row.observed_at)}</span><small>Quality {Math.round((row.quality_score || 0) * 100)}%</small></button>)}</div>
      <article className="review-inspector">
        <header><span className={`state ${current.state}`}>{readable(current.state)}</span><small>{current.model || 'Citizen observation'}</small></header>
        <h3>{current.predicted_taxon || 'Unclassified sample'}</h3>
        {photoUrl ? <figure className="review-photo"><img src={photoUrl} alt="Captured specimen for identification review"/><figcaption>Reduced photo retained on this device · inspect original evidence before a real-world decision.</figcaption></figure> : <p className="review-scope">No photo is available on this device for this record. Seeded records contain demonstration metadata only.</p>}
        <p>{current.explanation || 'This observation is available for an independent identification check.'}</p>
        <dl><div><dt>Recorded confidence</dt><dd>{Math.round((current.taxon_confidence || 0) * 100)}%</dd></div><div><dt>Quality gate</dt><dd>{current.quality_score} / 0.70 required</dd></div><div><dt>Field note</dt><dd>{current.note || 'No field note'}</dd></div></dl>
        <div className="review-reasons">{current.anomaly_reasons?.map(reason => <span key={reason}>{readable(reason)}</span>)}</div>
        <label>Correct family<select aria-label="Correct family" value={correction} onChange={e => setCorrection(e.target.value)}><option value="">Keep suggestion or choose a correction</option>{taxa.map(taxon => <option key={taxon.family} value={taxon.family}>{taxon.family} · BMWP {taxon.bmwp}</option>)}</select></label>
        <label>Reviewer note<textarea aria-label="Reviewer note" maxLength={2000} value={note} onChange={e => setNote(e.target.value)} placeholder="Describe the identification evidence and why you made this decision."/></label>
        <div className="review-decisions"><button className="primary" disabled={busy || !note.trim() || !navigator.onLine} onClick={() => review(correction ? 'correct' : 'confirm')}>{busy ? 'Saving…' : correction ? 'Save correction' : 'Confirm family'}</button><button disabled={busy || !note.trim() || !navigator.onLine} onClick={() => review('reject')}>Exclude record</button></div>
        <small className="review-scope">Expert confirmation preserves the date and quality gates. The demo role has no sign-in; production reviewer permissions are not configured.</small>
      </article>
    </div> : <div className="ledger-empty"><Icon name="check" size={25}/><b>No records in this view.</b><p>New AI-assisted captures appear here after synchronization.</p></div>}
    {message && <p className="feedback" role="status">{message}</p>}
  </section>
}
