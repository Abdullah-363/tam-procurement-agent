import { useEffect, useState } from 'react'
import { api, sar } from '../api'
import { Markdown, Trace } from '../components'

const QUESTIONS = [
  'Which purchases this year broke procurement policy?',
  'Show IT purchases over 40,000 SAR and who approved each one.',
  'How much have we committed against each IT G/L account?',
  'Which phone lines are we still paying for people who left?',
]

export default function AuditView({ tick }) {
  const [findings, setFindings] = useState([])
  const [verify, setVerify] = useState(null)
  const [q, setQ] = useState('')
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [session] = useState(() => `audit-${Date.now()}`)

  useEffect(() => { api.findings().then(setFindings).catch(() => {}) }, [tick])

  async function ask(text) {
    const question = (text ?? q).trim()
    if (!question) return
    setQ(question); setBusy(true); setAnswer(null)
    try { setAnswer(await api.ask(question, session)) }
    catch (e) { setAnswer({ reply: e.message, trace: [] }) }
    finally { setBusy(false) }
  }

  return (
    <div className="split audit-split">
      <section className="panel">
        <header className="panel-head">
          <h2>Ask the records</h2>
          <p className="sub">Answers come only from purchase records and the audit log.</p>
        </header>
        <form className="composer" onSubmit={(e) => { e.preventDefault(); ask() }}>
          <textarea dir="auto" rows={2} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. Which purchases were approved without the CFO?" />
          <button className="btn primary" disabled={busy || !q.trim()}>{busy ? 'Checking…' : 'Ask'}</button>
        </form>
        <div className="chips pad-x">
          {QUESTIONS.map((x) => <button key={x} className="chip" disabled={busy} onClick={() => ask(x)}>{x}</button>)}
        </div>
        {answer && (
          <div className="answer">
            <Markdown text={answer.reply} />
            <details><summary>Evidence Tam used</summary><Trace trace={answer.trace} /></details>
          </div>
        )}
      </section>

      <section className="panel">
        <header className="panel-head">
          <h2>Compliance findings</h2>
          <p className="sub">Every approved purchase, checked against policy.</p>
          <div className="row">
            <a className="btn primary" href="/api/audit/pack" target="_blank" rel="noreferrer">Generate audit pack</a>
            <button className="btn" onClick={async () => setVerify(await api.verify())}>Verify audit log</button>
            <button className="btn ghost" title="Demo: secretly edit one past log entry"
              onClick={async () => setVerify(await api.tamper())}>Simulate tampering</button>
          </div>
          {verify && <p className={`verify ${verify.ok ? 'ok' : 'bad'}`}>{verify.message}</p>}
        </header>
        <table className="tbl">
          <thead><tr><th>PR</th><th className="num">Value</th><th>Finding</th></tr></thead>
          <tbody>
            {findings.map((f, i) => (
              <tr key={i}>
                <td><strong>{f.pr_id}</strong><span className="muted small block" dir="auto">{f.title}</span></td>
                <td className="num">{sar(f.value)}</td>
                <td><span className={`sev sev-${f.severity}`}>{f.severity}</span> {f.finding}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
