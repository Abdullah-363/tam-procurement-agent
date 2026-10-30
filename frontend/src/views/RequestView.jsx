import { useEffect, useRef, useState } from 'react'
import { Markdown, Trace } from '../components'

const SAMPLES = [
  { label: 'Laptops, urgent', text: 'I need 10 developer laptops for the new software team joining next month, urgent. Preferred vendor Zawaya.' },
  {
    label: 'A filled form with mistakes',
    text: `Please submit this PR as I filled it:
Title: Developer laptops for new hires
G/L account: 6120
Method: Low Value
Estimated value: 6,500 SAR
Items: 10 x LAP-DEV-14 at 6,500 SAR each, 2 x NET-AP6-SUP at 900 SAR
Justification: need laptops
Vendor: V-ZAW`,
  },
  { label: 'Phone for a new manager', text: 'Abeer Al-Juhani, our new Marketing Manager, starts this Sunday. Please arrange her company phone and line.' },
  { label: 'بالعربي', text: 'نحتاج ٥ شاشات ٢٧ بوصة و٥ محطات توصيل لفريق المالية الجديد' },
]

export default function RequestView({ chat, openPr }) {
  const { messages, busy, lastTrace, send, clear } = chat
  const [input, setInput] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  function submit(text) {
    const msg = (text ?? input).trim()
    if (!msg || busy) return
    setInput('')
    send(msg)
  }

  return (
    <div className="split">
      <section className="panel chat">
        <header className="panel-head chat-tools">
          <div>
            <h2>New request</h2>
            <p className="sub">Describe what you need. Tam drafts, checks and routes the purchase request. You can ask for several in one chat.</p>
          </div>
          {messages.length > 0 && (confirmClear ? (
            <div className="row">
              <button className="btn danger" onClick={() => { clear(); setConfirmClear(false) }}>Clear chat</button>
              <button className="btn ghost" onClick={() => setConfirmClear(false)}>Keep</button>
            </div>
          ) : (
            <button className="btn ghost" disabled={busy} onClick={() => setConfirmClear(true)}>Clear chat</button>
          ))}
        </header>
        <div className="chat-log">
          {messages.length === 0 && (
            <div className="chat-intro">
              <p>Try one of these:</p>
              <div className="chips">
                {SAMPLES.map((s) => (
                  <button key={s.label} className="chip" onClick={() => submit(s.text)}>{s.label}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`bubble bubble-${m.role}`}>
              {m.role === 'agent' ? <Markdown text={m.text} /> : <p dir="auto" style={{ whiteSpace: 'pre-wrap' }}>{m.text}</p>}
              {m.prs?.length > 0 && (
                <div className="bubble-links">
                  {m.prs.map((id) => <button key={id} className="link" onClick={() => openPr(id)}>Open {id}</button>)}
                </div>
              )}
            </div>
          ))}
          {busy && <div className="bubble bubble-agent working"><span className="dots"><i /><i /><i /></span> Tam is working on it</div>}
          <div ref={endRef} />
        </div>
        <form className="composer" onSubmit={(e) => { e.preventDefault(); submit() }}>
          <textarea
            dir="auto"
            value={input}
            placeholder={messages.length ? 'Ask for another purchase, or reply to Tam' : 'e.g. We need 5 monitors for the finance team'}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
            rows={2}
          />
          <button className="btn primary" disabled={busy || !input.trim()}>Send</button>
        </form>
      </section>

      <section className="panel work">
        <header className="panel-head">
          <h2>What Tam did</h2>
          <p className="sub">Every check and action for the latest message, in order.</p>
        </header>
        {lastTrace ? <Trace trace={lastTrace} /> : (
          <p className="muted pad">{busy ? 'Checking catalog, budget and policy…' : 'Steps appear here after each request.'}</p>
        )}
      </section>
    </div>
  )
}
