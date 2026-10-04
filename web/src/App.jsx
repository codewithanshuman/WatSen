import { lazy, Suspense, useEffect, useState } from 'react'
import LandingPage from './LandingPage'

const Dashboard = lazy(() => import('./Dashboard'))
const views = ['Network', 'Evidence', 'One Health', 'Standards']
function currentRoute() {
  let hash
  try { hash = decodeURIComponent(window.location.hash) } catch { return null }
  if (!hash.startsWith('#/workspace')) return null
  const candidate = hash.split('/')[2]
  return views.includes(candidate) ? candidate : 'Network'
}

export default function App() {
  const [route, setRoute] = useState(currentRoute)
  useEffect(() => {
    const change = () => setRoute(currentRoute())
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])
  const enter = (view = 'Network') => {
    window.location.hash = `/workspace/${encodeURIComponent(view)}`
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
  const home = () => {
    window.location.hash = '/'
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
  return route ? <Suspense fallback={<div className="page-loader"><img src="/assets/logo.png" alt="" /><span>Opening your workspace…</span><i /></div>}><Dashboard initialView={route} onHome={home} onNavigate={enter} /></Suspense> : <LandingPage onEnter={enter} />
}
