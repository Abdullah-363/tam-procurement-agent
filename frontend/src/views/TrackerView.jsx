import { useEffect, useState } from 'react'
import { ROLES, api, sar } from '../api'
import { EditableText, Empty, Logo, Markdown, Status, Trace } from '../components'

const ACTION_TEXT = {
  pr_drafted: 'Draft created', pr_validated: 'Checked against policy', pr_corrected: 'Draft corrected',
  submission_blocked: 'Submission blocked', pr_submitted: 'Submitted', approval_requested: 'Approval requested',
  approved: 'Approved', rejected: 'Rejected', reminder_sent: 'Reminder sent', escalated: 'Escalated',
  justification_drafted: 'Justification drafted', line_ordered: 'Line ordered from STC',
  hr_confirmation_added: 'HR confirmation added', text_edited: 'Text edited', resubmitted_with_justification: 'Resubmitted',
  fully_approved: 'Fully approved', sent_to_procurement: 'Sent to procurement', audit_pack_generated: 'Audit pack generated',
}

export default function TrackerView({ tick, onChange, selected, setSelected }) {
  const [prs, setPrs] = useState([])
  const [scan, setScan] = useState(null)
  const [scanning, setScanning] = useState(false)

  useEffect(() => { api.prs().then(setPrs).catch(() => {}) }, [tick])
  useEffect(() => { if (!selected && prs.length) setSelected(prs[0].id) }, [prs, selected, setSelected])

  async function runScan(days) {
    setScanning(true); setScan(null)
    try {
      const r = await api.renewals(days)
      setScan(r); onChange()
      if (r.prs?.[0]) setSelected(r.prs[0])
    } catch (e) { setScan({ reply: e.message, trace: [] }) } finally { setScanning(false) }
  }

  return (
    <div className="split tracker">
      <section className="panel list">
        <header className="panel-head">
          <h2>Purchase requests</h2>
          <div className="row">
            <button className="btn" disabled={scanning} onClick={() => runScan(30)}>
              {scanning ? 'Scanning…' : 'Run scheduled scan (30 days)'}
            </button>
            <button className="btn ghost" disabled={scanning} onClick={() => runScan(90)}>90 days</button>
          </div>
        </header>
        {scan && (
          <div className="callout">
            <p className="callout-title">Scheduled scan: renewals and phone lines</p>
            <Markdown text={scan.reply} />
            <details><summary>Steps</summary><Trace trace={scan.trace} /></details>
          </div>
        )}
        {prs.length === 0 ? <Empty title="No requests yet">Start one on the Request page, or scan for renewals.</Empty> : (
          <ul className="pr-list">
            {prs.map((p) => (
              <li key={p.id}>
                <button className={`pr-item ${selected === p.id ? 'on' : ''}`} onClick={() => setSelected(p.id)}>
                  <span className="pr-id">{p.id}{p.source === 'agent-renewal' && <span className="by-agent">started by Tam</span>}</span>
                  <span className="pr-title" dir="auto">{p.title}</span>
                  <span className="pr-meta"><Status status={p.status} /><span className="amount-sm">{sar(p.value)}</span></span>
                  {p.waiting_on && <span className="muted small">Waiting on {p.waiting_on}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="panel detail">
        {selected ? <PrDetail id={selected} tick={tick} onChange={onChange} /> : <Empty title="Select a request" />}
      </section>
    </div>
  )
}

function PrDetail({ id, tick, onChange }) {
  const [pr, setPr] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.pr(id).then(setPr).catch(() => setPr(null)) }, [id, tick])
  if (!pr) return <p className="muted pad">Loading…</p>

  const done = pr.status === 'sent_to_procurement'
  const memo = pr.extra?.justification_memo
  const chain = pr.approvals?.length ? pr.approvals : (pr.approval_chain_named || [])
  const earlier = (pr.approval_history || []).filter((a) => a.round < pr.approval_round && a.status === 'rejected')
  const approvedCount = (pr.approvals || []).filter((a) => a.status === 'approved').length
  // requester may edit while nobody has signed yet, or after a rejection
  const requesterCanEdit = ['draft', 'needs_fix', 'rejected'].includes(pr.status) ||
    (pr.status === 'pending_approval' && approvedCount === 0)
  const saveText = async (fields) => { await api.editText(id, 'requester', fields); onChange() }

  async function resubmit() {
    setBusy(true)
    try { await api.resubmit(id); onChange() } finally { setBusy(false) }
  }

  return (
    <div className="pr-detail">
      <header className="detail-head">
        <div>
          <p className="pr-id">{pr.id} · {pr.doc_type} · {pr.request_type}</p>
          <h2 dir="auto">{pr.title}</h2>
          <Status status={pr.status} />
        </div>
        <div className="detail-amount">
          <span className="amount">{sar(pr.estimated_value)}</span>
          <span className="muted small">{pr.method} · G/L {pr.gl_account}</span>
        </div>
        {done && <div className="stamp" aria-label="Approved"><Logo size={46} mono /><small>Approved</small></div>}
      </header>

      <h3 className="sec">Approval journey{pr.approval_round > 1 ? ` (round ${pr.approval_round})` : ''}</h3>
      {earlier.length > 0 && (
        <div className="rounds">
          {earlier.map((a, i) => (
            <p key={i} dir="auto">Round {a.round}: returned by {a.person} on {a.decided_at}{a.comment ? `: “${a.comment}”` : ''}</p>
          ))}
        </div>
      )}
      {chain.length === 0 ? <p className="muted">Not submitted yet.</p> : (
        <ol className="journey">
          {chain.map((a, i) => (
            <li key={i} className={`step step-${a.status || 'waiting'}`}>
              <span className="step-num">{i + 1}</span>
              <span className="step-name">{a.person || a.name}</span>
              <span className="step-role muted small">{a.title || ROLES.find((r) => r.id === a.role)?.label || a.role}</span>
              <span className="step-state small">
                {a.status === 'approved' && `Approved ${a.decided_at?.slice(5) || ''}`}
                {a.status === 'rejected' && 'Rejected'}
                {a.status === 'pending' && `Waiting since ${a.requested_at?.slice(5)}`}
                {(!a.status || a.status === 'waiting') && 'Next'}
                {a.reminders > 0 && ` · ${a.reminders} reminder${a.reminders > 1 ? 's' : ''}`}
                {a.escalated ? ' · escalated' : ''}
              </span>
              {a.comment && <span className="step-comment" dir="auto">“{a.comment}”</span>}
            </li>
          ))}
        </ol>
      )}

      {memo && (
        <div className="callout">
          <p className="callout-title">Justification memo drafted by Tam</p>
          <EditableText value={memo} className="memo" rows={12} canEdit={pr.status === 'rejected'}
            label="Edit memo" onSave={(t) => saveText({ memo: t })} />
          {pr.extra?.memo_edited_by && <p className="edit-note">Edited by {pr.extra.memo_edited_by}</p>}
          {pr.status === 'rejected' && (
            <button className="btn primary" disabled={busy} onClick={resubmit}>
              {busy ? 'Resubmitting…' : 'Approve memo and resubmit'}
            </button>
          )}
        </div>
      )}

      {pr.validation?.length > 0 && (
        <>
          <h3 className="sec">Checks</h3>
          <ul className="trace-issues">
            {pr.validation.map((v, i) => <li key={i} className={`issue-${v.severity}`}>{v.message}</li>)}
          </ul>
        </>
      )}

      <h3 className="sec">Items</h3>
      <table className="tbl">
        <thead><tr><th>Item</th><th>Qty</th><th className="num">Unit</th><th className="num">Total</th></tr></thead>
        <tbody>
          {pr.lines.map((l, i) => (
            <tr key={i}><td dir="auto">{l.description}<span className="muted small block">{l.item_code}</span></td>
              <td>{l.qty}</td><td className="num">{sar(l.unit_price)}</td><td className="num">{sar(l.qty * l.unit_price)}</td></tr>
          ))}
        </tbody>
      </table>
      <h3 className="sec">Justification</h3>
      <EditableText value={pr.justification} canEdit={requesterCanEdit} label="Edit justification"
        onSave={(t) => saveText({ justification: t })} />
      {!requesterCanEdit && pr.status === 'pending_approval' && (
        <p className="edit-note">Locked after the first signature. A rejection sends it back for edits.</p>
      )}

      <div className="row">
        <a className="btn" href={`/api/prs/${pr.id}/document`} target="_blank" rel="noreferrer">Open PR form</a>
        <a className="btn ghost" href={`/api/audit/pack?pr_id=${pr.id}`} target="_blank" rel="noreferrer">Audit pack for this PR</a>
      </div>

      <h3 className="sec">Audit trail</h3>
      <ol className="timeline">
        {pr.events.map((e) => (
          <li key={e.id}>
            <span className="muted small">{e.ts}</span>
            <span><strong>{ACTION_TEXT[e.action] || e.action.replaceAll('_', ' ')}</strong> · {e.actor}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
