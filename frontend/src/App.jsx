import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useChat } from './useChat'
import { Logo } from './components'
import RequestView from './views/RequestView'
import ApprovalsView from './views/ApprovalsView'
import TrackerView from './views/TrackerView'
import AuditView from './views/AuditView'

const VIEWS = [
  { id: 'request', label: 'Request', hint: 'Ask Tam for something' },
  { id: 'approvals', label: 'Approvals', hint: 'Sign or reject' },
  { id: 'tracker', label: 'Tracker', hint: 'Where every request is' },
  { id: 'audit', label: 'Audit', hint: 'Records and compliance' },
]

const JUMPS = [
  { label: '+6 hours', h: 6 }, { label: '+1 day', h: 24 }, { label: '+3 days', h: 72 },
]

export default function App() {
  const [view, setView] = useState('request')
  const [state, setState] = useState(null)
  const [tick, setTick] = useState(0)
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [offline, setOffline] = useState(false)
  const [theme, setTheme] = useState(() => document.documentElement.getAttribute('data-theme') || 'light')
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('tam-theme', theme) } catch { /* ignore */ }
  }, [theme])

  const refresh = useCallback(() => setTick((t) => t + 1), [])
  const chat = useChat(refresh)

  useEffect(() => {
    api.state().then((s) => { setState(s); setOffline(false) }).catch(() => setOffline(true))
  }, [tick])

  // light polling so every screen stays in sync during the demo
  useEffect(() => { const t = setInterval(refresh, 5000); return () => clearInterval(t) }, [refresh])

  async function jump(h) {
    const r = await api.advance(h)
    const acts = r.follow_up_actions || []
    setToast({
      title: `Clock moved ${h >= 24 ? `${h / 24} day${h > 24 ? 's' : ''}` : `${h} hours`}`,
      items: acts.length ? acts.map((a) => a.type === 'reminder'
        ? `Reminder sent to ${a.to} (${a.pr_id}, waiting ${a.hours}h)`
        : `${a.pr_id} escalated to ${a.to}: ${a.waiting_on} silent for ${a.hours}h`)
        : ['No approvals overdue.'],
    })
    refresh()
  }

  async function reset() {
    await api.reset(); chat.clear(); setConfirmReset(false); setSelected(null); setToast(null); refresh()
  }

  const openPr = (id) => { setSelected(id); setView('tracker') }
  const pending = state?.counts?.pending_approval || 0

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark"><Logo size={50} /></span>
          <div>
            <p className="brand-name">Tam</p>
            <p className="brand-sub">Procurement agent</p>
          </div>
        </div>
        <nav>
          {VIEWS.map((v) => (
            <button key={v.id} className={`nav ${view === v.id ? 'on' : ''}`} onClick={() => setView(v.id)}>
              <span>{v.label}{v.id === 'request' && chat.busy && <span className="badge">working</span>}{v.id === 'approvals' && pending > 0 && <span className="badge">{pending}</span>}</span>
              <small>{v.hint}</small>
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <p>{state?.company?.name}</p>
          <p className="ar">{state?.company?.name_ar}</p>
          {state && <p className="usage">Model {state.model} · {state.usage.runs} runs · {(state.usage.input_tokens / 1000).toFixed(1)}k tokens in</p>}
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div className="clock">
            <span className="muted small">Company time</span>
            <strong>{state?.now || '—'}</strong>
          </div>
          <div className="row">
            <button className="btn ghost theme-btn" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
              {theme === 'dark' ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
                </svg>
              )}
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
            {JUMPS.map((j) => <button key={j.h} className="btn ghost" onClick={() => jump(j.h)}>{j.label}</button>)}
            {confirmReset
              ? <><button className="btn danger" onClick={reset}>Confirm reset</button><button className="btn ghost" onClick={() => setConfirmReset(false)}>Keep</button></>
              : <button className="btn ghost" onClick={() => setConfirmReset(true)}>Reset demo</button>}
          </div>
        </header>

        {offline && (
          <div className="banner">Can't reach the backend. Start it in the backend folder with <code>python -m uvicorn app.main:app --reload</code></div>
        )}
        {toast && (
          <div className="toast" role="status">
            <div><strong>{toast.title}</strong>{toast.items.map((t, i) => <p key={i}>{t}</p>)}</div>
            <button className="link" onClick={() => setToast(null)}>Dismiss</button>
          </div>
        )}

        <div className="view">
          {view === 'request' && <RequestView chat={chat} openPr={openPr} />}
          {view === 'approvals' && <ApprovalsView tick={tick} onChange={refresh} openPr={openPr} />}
          {view === 'tracker' && <TrackerView tick={tick} onChange={refresh} selected={selected} setSelected={setSelected} />}
          {view === 'audit' && <AuditView tick={tick} />}
        </div>
      </main>
    </div>
  )
}
