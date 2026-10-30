import { useEffect, useState } from 'react'
import { ROLES, api, sar } from '../api'
import { EditableText, Empty, Markdown } from '../components'

export default function ApprovalsView({ tick, onChange, openPr }) {
  const [role, setRole] = useState('it_head')
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)
  const [rejecting, setRejecting] = useState(null)
  const [comment, setComment] = useState('')
  const [agentNote, setAgentNote] = useState(null)

  useEffect(() => { api.inbox(role).then(setData).catch(() => {}) }, [role, tick])

  async function decide(id, decision) {
    setBusy(id)
    try {
      const r = await api.decide(id, role, decision, decision === 'reject' ? comment : '')
      if (r.agent) setAgentNote({ id, text: r.agent.reply })
      setRejecting(null); setComment('')
      onChange()
      setData(await api.inbox(role))
    } catch (e) { alert(e.message) } finally { setBusy(null) }
  }

  const pending = data?.pending || []
  const notes = data?.notifications || []

  return (
    <div className="split">
      <section className="panel">
        <header className="panel-head">
          <h2>Approvals</h2>
          <p className="sub">Viewing as</p>
          <div className="roles" role="tablist">
            {ROLES.map((r) => (
              <button key={r.id} role="tab" aria-selected={role === r.id}
                className={`role ${role === r.id ? 'on' : ''}`} onClick={() => setRole(r.id)}>{r.label}</button>
            ))}
          </div>
          {data?.person?.name && <p className="who">{data.person.name}, {data.person.title}</p>}
        </header>

        {agentNote && (
          <div className="callout">
            <p className="callout-title">Tam drafted a justification for {agentNote.id}</p>
            <Markdown text={agentNote.text} />
            <button className="link" onClick={() => openPr(agentNote.id)}>Review it in {agentNote.id}</button>
          </div>
        )}

        {pending.length === 0 ? (
          <Empty title="Nothing waiting for you">Requests appear here when it is your turn to sign.</Empty>
        ) : pending.map((p) => (
          <article key={p.id} className="approval">
            <div className="approval-top">
              <div>
                <button className="link strong" onClick={() => openPr(p.id)}>{p.id}</button>
                {p.doc_type === 'Urgent' && <span className="status tone-bad">Urgent</span>}
                <h3 dir="auto">{p.title}</h3>
              </div>
              <div className="amount">{sar(p.value)}</div>
            </div>
            <dl className="facts">
              <div><dt>Method</dt><dd>{p.method}</dd></div>
              <div><dt>G/L</dt><dd>{p.gl_account}</dd></div>
              <div><dt>Waiting since</dt><dd>{p.requested_at}</dd></div>
            </dl>
            <ul className="lines">
              {p.lines.map((l, i) => <li key={i}>{l.qty} × {l.description} <span className="muted">@ {sar(l.unit_price)}</span></li>)}
            </ul>
            <EditableText value={p.justification} canEdit={['it_head', 'admin_head', 'hr_head', 'marketing_head'].includes(role)} label="Edit justification"
              onSave={async (t) => { await api.editText(p.id, role, { justification: t }); setData(await api.inbox(role)); onChange() }} />
            {p.why_you && <p className="why-you">Why you: {p.why_you}</p>}
            <p className="checked">Checked by Tam: budget, totals, G/L account, method and approval chain.</p>
            {p.warnings.map((w, i) => <p key={i} className="issue-warning">{w}</p>)}

            {rejecting === p.id ? (
              <div className="reject-box">
                <textarea dir="auto" placeholder="Reason for rejecting (Tam uses it to draft the justification)"
                  value={comment} onChange={(e) => setComment(e.target.value)} rows={2} />
                <div className="row">
                  <button className="btn danger" disabled={busy === p.id} onClick={() => decide(p.id, 'reject')}>
                    {busy === p.id ? 'Rejecting…' : 'Reject request'}
                  </button>
                  <button className="btn ghost" onClick={() => setRejecting(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <div className="row">
                <button className="btn primary" disabled={busy === p.id} onClick={() => decide(p.id, 'approve')}>
                  {busy === p.id ? 'Approving…' : 'Approve'}
                </button>
                <button className="btn ghost" onClick={() => setRejecting(p.id)}>Reject</button>
              </div>
            )}
          </article>
        ))}
      </section>

      <section className="panel">
        <header className="panel-head">
          <h2>Messages from Tam</h2>
          <p className="sub">Requests, reminders and escalations sent to this person.</p>
        </header>
        {notes.length === 0 ? <p className="muted pad">No messages yet.</p> : (
          <ul className="notes">
            {notes.map((n) => (
              <li key={n.id} className={`note note-${n.kind}`}>
                <div className="note-top"><span className="note-kind">{n.kind.replace('_', ' ')}</span><span className="muted">{n.ts}</span></div>
                <p className="note-subj">{n.subject}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
