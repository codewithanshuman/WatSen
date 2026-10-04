import { useEffect, useRef, useState } from 'react'
import './landing.css'

const productTabs = [
  { key: 'forecast', label: 'See what comes next', icon: 'wave', title: 'A little foresight. A lot of possibility.', description: 'Explore a 72-hour view of freshwater stress. Follow each forecast back to its evidence, and compare what might change with an intervention.', eyebrow: 'FORECAST & EXPLAIN', view: 'Network' },
  { key: 'evidence', label: 'Connect the evidence', icon: 'layers', title: 'Small observations. A fuller picture.', description: 'Bring field photographs, biological indicators and sensor measurements into the same view. Human review keeps uncertain observations visible.', eyebrow: 'CAPTURE & VERIFY', view: 'Evidence' },
  { key: 'action', label: 'Explore your next move', icon: 'route', title: 'Understand the options. Then act.', description: 'Compare intervention scenarios, see where another measurement would help, and share evidence with the teams who need it.', eyebrow: 'COMPARE & SHARE', view: 'Network' },
]

function Icon({ name = 'arrow', size = 20, ...props }) {
  const paths = {
    arrow: <><path d="M4 12h15M13 6l6 6-6 6" /></>,
    diagonal: <><path d="M6 18 18 6M6 6h12v12" /></>,
    wave: <><path d="M2 12h4l3-7 5 14 3-7h5" /></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5" /></>,
    route: <><circle cx="6" cy="5" r="2" /><circle cx="18" cy="19" r="2" /><path d="M8 5h8a4 4 0 0 1 0 8H8a3 3 0 0 0 0 6h8" /></>,
    drop: <><path d="M12 2S5 10 5 15a7 7 0 1 0 14 0C19 10 12 2 12 2Z" /><path d="M8 15a4 4 0 0 0 4 4" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    plus: <path d="M12 5v14M5 12h14" />,
    leaf: <><path d="M20 4C8 2 2 8 6 16s16 2 14-12Z" /><path d="M4 21 15 10" /></>,
    heart: <path d="M20.7 5.8a5.5 5.5 0 0 0-7.8 0l-.9.9-.9-.9a5.5 5.5 0 0 0-7.8 7.8L12 22l8.7-8.4a5.5 5.5 0 0 0 0-7.8Z" />,
    scan: <><path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5M7 12h10" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.arrow}</svg>
}

export default function LandingPage({ onEnter }) {
  const root = useRef(null)
  const [tab, setTab] = useState('forecast')
  const product = productTabs.find(item => item.key === tab)

  useEffect(() => {
    if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.add('lp-visible'); observer.unobserve(entry.target) }
    }), { threshold: 0.08 })
    root.current?.querySelectorAll('[data-lp-reveal]').forEach(element => {
      if (element.getBoundingClientRect().top > window.innerHeight) element.classList.add('lp-will-reveal')
      observer.observe(element)
    })
    return () => observer.disconnect()
  }, [])

  const enter = view => onEnter(view)

  return <div className="landing-page" ref={root}>
    <a className="lp-skip" href="#lp-main">Skip to content</a>
    <header className="lp-header">
      <a className="lp-brand" href="#lp-main" aria-label="WatSen home"><img src="/assets/logo.png" alt="" /><span>WatSen<span className="lp-brand-dot">.</span></span></a>
      <nav className="lp-nav" aria-label="Main navigation"><a href="#lp-product">Platform</a><a href="#lp-workflow">How it works</a><a href="#lp-one-health">One Health</a></nav>
      <button className="lp-button lp-button-small lp-button-outline" onClick={() => enter('Network')}>Open workspace <Icon name="diagonal" size={16} /></button>
    </header>

    <main id="lp-main">
      <section className="lp-hero lp-container" aria-labelledby="lp-headline">
        <div className="lp-hero-copy">
          <span className="lp-eyebrow"><span className="lp-tiny-drop" /> FRESH PERSPECTIVES ON FRESHWATER</span>
          <h1 id="lp-headline">A clearer future.<br />Starts with <span>water.</span></h1>
          <p>Read the signals. Understand the change.<br className="lp-desktop-break" /> Protect the life that flows through it all.</p>
          <div className="lp-hero-actions"><button className="lp-button lp-button-primary" onClick={() => enter('Network')}>Explore WatSen <span><Icon name="arrow" size={18} /></span></button><a className="lp-text-link" href="#lp-product">Meet the platform <Icon name="diagonal" size={15} /></a></div>
          <div className="lp-hero-footnote"><div className="lp-mini-symbols"><Icon name="wave" /><Icon name="leaf" /><Icon name="heart" /></div><span>Water. Ecosystems. People.<br /><b>One connected picture.</b></span></div>
        </div>
        <div className="lp-hero-scene">
          <div className="lp-scene-image"><img src="/assets/landing-sky.png" alt="Glass wind chime and translucent fish floating through a bright blue sky" fetchpriority="high" /><div className="lp-scene-topline"><span><i /> A living water system</span><Icon name="plus" size={19} /></div><div className="lp-scene-caption">EVERY SIGNAL<br /><b>has a ripple effect.</b></div></div>
          <div className="lp-floating-signal" aria-label="Illustrative product preview"><div className="lp-signal-title"><span className="lp-icon-tile"><Icon name="wave" size={18} /></span><div><b>From signal to clarity</b><small>Illustrative forecast preview</small></div><span className="lp-preview-label">DEMO</span></div><svg className="lp-signal-chart" viewBox="0 0 340 76" role="img" aria-label="Illustrative forecast curve with uncertainty band"><defs><linearGradient id="lp-chart-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#4dbaff" stopOpacity=".24" /><stop offset="100%" stopColor="#4dbaff" stopOpacity="0" /></linearGradient></defs><path d="M1 66H339M1 38H339M1 10H339" stroke="#e6eff5" strokeDasharray="3 5" /><path d="M144 35C170 24 183 9 206 12S245 24 268 21 305 3 338 7L338 40C303 35 289 51 265 47S228 42 205 40 166 53 144 47Z" fill="#d9f0ff" /><path d="M1 52C22 51 26 65 44 54S67 55 82 38 108 48 121 42 137 45 144 40L144 76H1Z" fill="url(#lp-chart-fill)" /><path d="M1 52C22 51 26 65 44 54S67 55 82 38 108 48 121 42 137 45 144 40" stroke="#269dec" strokeWidth="2.5" fill="none" /><path d="M144 40C170 35 183 22 206 26S245 35 268 34 305 20 338 24" stroke="#269dec" strokeWidth="2.5" strokeDasharray="5 5" fill="none" /><circle cx="144" cy="40" r="4.5" fill="#269dec" stroke="white" strokeWidth="3" /></svg><div className="lp-chart-legend"><span><i />Observed evidence</span><span><i />72-hour outlook</span></div></div>
          <span className="lp-scene-coordinate">FRESHWATER INTELLIGENCE / WATSEN</span>
        </div>
      </section>

      <section className="lp-intro-band lp-container" aria-label="Platform capabilities"><span>Built around<br /><b>the whole picture.</b></span><div><Icon name="wave" /><span>Sensor intelligence</span></div><div><Icon name="scan" /><span>Citizen science</span></div><div><Icon name="layers" /><span>Traceable evidence</span></div><div><Icon name="heart" /><span>One Health</span></div></section>

      <section id="lp-product" className="lp-product lp-container lp-section" data-lp-reveal>
        <div className="lp-section-heading"><div><span className="lp-eyebrow">01 / THE PLATFORM</span><h2>Less noise.<br /><span>More understanding.</span></h2></div><p>Bring the river, the field and the forecast together. A thoughtful workspace for seeing what matters — and understanding why.</p></div>
        <div className="lp-product-shell">
          <div className="lp-product-tabs" role="tablist" aria-label="Explore WatSen capabilities">{productTabs.map(item => <button id={`lp-tab-${item.key}`} role="tab" aria-selected={tab === item.key} aria-controls="lp-product-panel" tabIndex={tab === item.key ? 0 : -1} key={item.key} onClick={() => setTab(item.key)} onKeyDown={event => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return; event.preventDefault(); const current = productTabs.findIndex(entry => entry.key === tab); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (current + (event.key === 'ArrowRight' ? 1 : 2)) % 3; setTab(productTabs[next].key); document.getElementById(`lp-tab-${productTabs[next].key}`)?.focus() }}><Icon name={item.icon} size={19} />{item.label}</button>)}</div>
          <div id="lp-product-panel" className="lp-product-panel" role="tabpanel" aria-labelledby={`lp-tab-${tab}`} key={tab} tabIndex={0}>
            <div className="lp-product-copy"><span className="lp-eyebrow">{product.eyebrow}</span><h3>{product.title}</h3><p>{product.description}</p><button className="lp-text-link" onClick={() => enter(product.view)}>Open this workspace <Icon name="arrow" size={17} /></button><span className="lp-product-note">Explore with the included demonstration dataset.</span></div>
            <div className="lp-product-visual"><ProductPreview tab={tab} /></div>
          </div>
        </div>
      </section>

      <section id="lp-workflow" className="lp-workflow lp-container lp-section" data-lp-reveal>
        <div className="lp-workflow-intro"><span className="lp-eyebrow">02 / HOW IT WORKS</span><h2>A clear path.<br />From field to <span>foresight.</span></h2><p>Every layer adds context. Every insight keeps a connection to where it came from.</p><button className="lp-text-link" onClick={() => enter('Network')}>Follow the evidence <Icon name="arrow" size={17} /></button></div>
        <ol className="lp-steps"><li><span className="lp-step-number">01</span><div><h3>Listen to the water.</h3><p>Combine sensor readings, environmental pressure and observations from the people closest to the stream.</p><span className="lp-step-tag">Sensors + field evidence</span></div></li><li><span className="lp-step-number">02</span><div><h3>See the connections.</h3><p>Trace biological changes and emerging stress. Explore the sources, confidence and uncertainty behind each signal.</p><span className="lp-step-tag">Forecasts + explanations</span></div></li><li><span className="lp-step-number">03</span><div><h3>Make the next move count.</h3><p>Compare possible interventions, identify the next useful sample and carry the evidence into a shared decision.</p><span className="lp-step-tag">Scenarios + shared decisions</span></div></li></ol>
      </section>

      <section className="lp-field lp-container" data-lp-reveal>
        <div className="lp-field-art"><div className="lp-field-rings" aria-hidden="true" /><span className="lp-field-label"><Icon name="scan" size={17} /> A new perspective starts here</span><img src="/assets/field-camera.png" alt="Playful sky-blue field camera decorated with water-inspired stickers" loading="lazy" /><span className="lp-capture-tag"><Icon name="check" size={16} /> Every observation has a place.</span></div>
        <div className="lp-field-copy"><span className="lp-eyebrow">SCIENCE, WITH A HUMAN SIDE</span><h2>Your perspective.<br /><span>Part of the picture.</span></h2><p>A photograph can open a new line of inquiry. Contribute a field observation, explore an AI-assisted assessment and bring a human reviewer into the loop.</p><div className="lp-field-flow"><span>Capture</span><Icon name="arrow" size={14} /><span>Review</span><Icon name="arrow" size={14} /><span>Connect</span></div><button className="lp-button lp-button-primary" onClick={() => enter('Evidence')}>Explore field evidence <span><Icon name="arrow" size={18} /></span></button></div>
      </section>

      <section id="lp-one-health" className="lp-health lp-container lp-section" data-lp-reveal>
        <div className="lp-section-heading"><div><span className="lp-eyebrow">03 / ONE HEALTH</span><h2>Connected by water.<br /><span>Responsible for more.</span></h2></div><p>The health of a stream reaches beyond its banks. WatSen brings ecosystem, animal and human health into one evidence-linked view.</p></div>
        <div className="lp-health-landscape"><img src="/assets/landing-water.png" alt="Sunlight tracing ripples across clear blue water" loading="lazy" /><div className="lp-health-caption"><span>ONE WATER SYSTEM.</span><h3>A shared future.</h3><button className="lp-button lp-button-white" onClick={() => enter('One Health')}>Explore One Health <Icon name="diagonal" size={17} /></button></div><div className="lp-health-domains"><span><Icon name="leaf" size={20} />Ecosystems</span><i /><span><Icon name="wave" size={20} />Animal life</span><i /><span><Icon name="heart" size={20} />Communities</span></div></div>
      </section>

      <section className="lp-closing lp-container" data-lp-reveal><span className="lp-eyebrow">LET’S LOOK A LITTLE CLOSER.</span><h2>Good decisions<br />start with <span>clear water.</span></h2><button className="lp-button lp-button-primary" onClick={() => enter('Network')}>Step into WatSen <span><Icon name="arrow" size={18} /></span></button><p>Explore the platform · Follow the evidence · See the possibilities</p></section>
    </main>

    <footer className="lp-footer"><div className="lp-container"><div className="lp-footer-main"><a className="lp-brand" href="#lp-main"><img src="/assets/logo.png" alt="" /><span>WatSen<span className="lp-brand-dot">.</span></span></a><p>Clarity for the water.<br />Care for everything it connects.</p><nav aria-label="Footer navigation"><a href="#lp-product">Platform</a><a href="#lp-workflow">How it works</a><button onClick={() => enter('Standards')}>Evidence & standards <Icon name="diagonal" size={14} /></button></nav></div><div className="lp-footer-bottom"><span>WatSen · Freshwater intelligence</span><span>Designed for a more connected future.</span><a href="#lp-main">Back to the surface ↑</a></div></div><img className="lp-footer-art" src="/assets/footer-ice.png" alt="" loading="lazy" /></footer>
  </div>
}

function ProductPreview({ tab }) {
  return <div className="lp-demo-window"><header><span className="lp-demo-brand"><img src="/assets/logo.png" alt="" /> WatSen</span><span className="lp-preview-label">PRODUCT PREVIEW</span><span className="lp-window-dots"><i /><i /><i /></span></header><div className="lp-demo-content"><div className="lp-demo-heading"><span>{tab === 'forecast' ? 'Catchment overview' : tab === 'evidence' ? 'Evidence collection' : 'Intervention workspace'}</span><span>Demonstration</span></div>
    {tab === 'forecast' ? <><div className="lp-preview-map"><svg viewBox="0 0 510 185" role="img" aria-label="Illustrative connected river monitoring network"><defs><pattern id="lp-map-grid" width="25" height="25" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#cfe3ee" /></pattern></defs><rect width="510" height="185" fill="url(#lp-map-grid)" /><path d="M-20 135C90 190 98 8 192 66S297 164 327 87 414 19 540 59" stroke="#d5eefb" strokeWidth="32" fill="none" /><path d="M-20 135C90 190 98 8 192 66S297 164 327 87 414 19 540 59" stroke="#6bc5fa" strokeWidth="2.5" fill="none" /><path d="M152 55C162 6 216 17 234-10M278 126C270 170 328 160 344 207" stroke="#8fd3fa" strokeWidth="2" fill="none" /><g fill="#fff" stroke="#329fde" strokeWidth="2"><circle cx="136" cy="61" r="6" /><circle cx="261" cy="121" r="6" /><circle cx="395" cy="39" r="6" /></g><circle className="lp-map-pulse" cx="261" cy="121" r="13" fill="none" stroke="#48b8f6" strokeOpacity=".35" /><g fontFamily="inherit" fontSize="11" fill="#4f6b7b"><text x="152" y="47">Upstream</text><text x="276" y="147">Monitoring reach</text><text x="357" y="23">Downstream</text></g></svg><div className="lp-preview-map-key"><i /> Connected monitoring reaches</div></div><div className="lp-preview-bottom"><div><span>Forecast horizon</span><b>72 hours <Icon name="arrow" size={15} /></b></div><div><span>Signals in context</span><b>Weather + biology</b></div><span className="lp-mini-chip">Evidence linked</span></div></> : tab === 'evidence' ? <div className="lp-evidence-preview"><div className="lp-evidence-preview-title"><span className="lp-icon-tile"><Icon name="layers" size={21} /></span><div><b>Biological observation</b><span>From the field to the evidence ledger</span></div></div>{[['Field photograph', 'Captured', 'check'], ['AI-assisted suggestion', 'Needs confirmation', 'scan'], ['Human review', 'Review queue', 'layers']].map(([title, status, icon], index) => <div className="lp-evidence-preview-row" key={title}><span>0{index + 1}</span><b>{title}</b><small>{status}</small><Icon name={icon} size={16} /></div>)}<p><Icon name="route" size={15} /> Source and review status stay attached.</p></div> : <div className="lp-action-preview"><div className="lp-action-preview-top"><span className="lp-icon-tile"><Icon name="route" size={20} /></span><div><b>Compare possible pathways</b><span>Counterfactual scenario explorer</span></div></div><div className="lp-action-line"><span>Baseline</span><div><i style={{ width: '82%' }} /></div><b>Reference</b></div><div className="lp-action-line lp-action-alternate"><span>Intervention</span><div><i style={{ width: '55%' }} /></div><b>Scenario</b></div><div className="lp-action-summary"><Icon name="layers" size={18} /><span>Inspect assumptions, uncertainty<br />and supporting observations.</span><Icon name="diagonal" size={18} /></div><small className="lp-preview-disclaimer">Illustrative comparison · Explore calculated scenarios in the workspace.</small></div>}
    </div></div>
}
