import { useState } from 'react'
import { TOOL_LABELS, sar } from './api'

// Minimal markdown: **bold**, bullet lists, line breaks. Enough for agent replies.
export function Markdown({ text }) {
  if (!text) return null
  const lines = text.split('\n')
  const out = []
  let list = []
  const inline = (s, k) =>
    s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith('**') && part.endsWith('**')
        ? <strong key={`${k}-${i}`}>{part.slice(2, -2)}</strong>
        : <span key={`${k}-${i}`}>{part}</span>)
  const flush = (k) => {
    if (list.length) out.push(<ul key={`ul-${k}`}>{list}</ul>)
    list = []
  }
  lines.forEach((raw, i) => {
    const l = raw.trim()
    const m = l.match(/^([-*•]|\d+\.)\s+(.*)$/)
    if (m) list.push(<li key={i}>{inline(m[2], i)}</li>)
    else {
      flush(i)
      if (l.startsWith('#')) out.push(<p key={i} className="md-h">{inline(l.replace(/^#+\s*/, ''), i)}</p>)
      else if (l) out.push(<p key={i}>{inline(l, i)}</p>)
    }
  })
  flush('end')
  return <div className="md" dir="auto">{out}</div>
}

const STATUS_TONE = {
  draft: 'neutral', needs_fix: 'warn', pending_approval: 'info', rejected: 'bad',
  approved: 'good', sent_to_procurement: 'good',
}
const STATUS_TEXT = {
  draft: 'Draft', needs_fix: 'Needs correction', pending_approval: 'Awaiting approval',
  rejected: 'Rejected', approved: 'Approved', sent_to_procurement: 'Sent to procurement',
}
export function Status({ status }) {
  return <span className={`status tone-${STATUS_TONE[status] || 'neutral'}`}>{STATUS_TEXT[status] || status}</span>
}

// The agent's work, step by step: what it looked at and what it caught.
export function Trace({ trace }) {
  if (!trace?.length) return null
  return (
    <ol className="trace">
      {trace.map((t, i) => {
        if (t.type === 'thought') return <li key={i} className="trace-thought" dir="auto">{t.text}</li>
        if (t.type === 'guard') return <li key={i} className="trace-guard">{t.text}</li>
        const r = t.result || {}
        const issues = Array.isArray(r.validation) ? r.validation : []
        return (
          <li key={i} className={`trace-step ${t.ok ? '' : 'trace-err'}`} style={{ animationDelay: `${i * 90}ms` }}>
            <span className="trace-label">{TOOL_LABELS[t.tool] || t.tool}</span>
            <TraceDetail tool={t.tool} input={t.input} r={r} />
            {issues.length > 0 && (
              <ul className="trace-issues">
                {issues.map((x, j) => (
                  <li key={j} className={`issue-${x.severity}`}>{x.message}</li>
                ))}
              </ul>
            )}
            {!t.ok && <span className="trace-detail">{r.error}</span>}
          </li>
        )
      })}
    </ol>
  )
}

function TraceDetail({ tool, input, r }) {
  const d = (s) => <span className="trace-detail">{s}</span>
  switch (tool) {
    case 'check_budget': return r.message ? d(r.message) : null
    case 'get_procurement_rules':
      return r.method ? d(`${r.method}: ${(r.approval_chain || []).map((a) => a.name.split(' ')[0]).join(' → ')}`) : null
    case 'get_price_history':
      return r.last_purchase_unit_price_sar ? d(`${r.item_code}: last paid ${sar(r.last_purchase_unit_price_sar)}, ${r.vendors?.length} vendor(s)`) : null
    case 'create_pr_draft':
    case 'update_pr_draft':
      return r.id ? d(`${r.id} · ${sar(r.value_sar)} · ${r.summary?.errors} error(s), ${r.summary?.warnings} warning(s)`) : null
    case 'submit_pr':
      return r.submitted ? d(`Routed to ${(r.approval_chain || []).map((a) => a.title).join(' → ')}`) : d('Blocked until errors are fixed')
    case 'search_catalog': return d(`“${input?.query || ''}”`)
    case 'list_renewals_due':
      return Array.isArray(r) ? d(`${r.length} due: ${r.map((x) => `${x.item_code} in ${x.days_left} days`).join(', ')}`) : null
    case 'run_compliance_checks': return d(`${r.findings_count} finding(s)`)
    case 'find_purchases': return d(`${r.count} purchase(s), ${sar(r.total_sar)}`)
    case 'verify_audit_log': return d(r.message)
    case 'check_mobile_eligibility':
      return r.name ? d(r.eligible ? `${r.name}: ${r.grade} → ${r.entitlement?.summary}` : `${r.name}: not eligible. ${r.reason || ''}`) : null
    case 'list_mobile_lines': {
      const bad = (r.lines || []).filter((l) => l.problem).length
      return d(`${r.count} line(s)${bad ? `, ${bad} still active after the employee left` : ''}`)
    }
    case 'request_line_cancellation':
      return r.number ? d(`${r.number} (${r.employee}): saves ${sar(r.monthly_saving)} per month`) : null
    default: return null
  }
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {children && <p className="empty-body">{children}</p>}
    </div>
  )
}

// Text with a pen button. Saving calls onSave(newText); errors (e.g. "Locked") are shown inline.
export function EditableText({ value, onSave, canEdit = true, label = 'Edit', className = 'justif', rows = 5 }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value || '')
  const [err, setErr] = useState(null)
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true); setErr(null)
    try { await onSave(draft); setEditing(false) }
    catch (e) { setErr(e.message) }
    finally { setSaving(false) }
  }

  if (editing) {
    return (
      <div className="edit-box">
        <textarea dir="auto" rows={rows} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
        {err && <p className="issue-error">{err}</p>}
        <div className="row">
          <button className="btn primary" disabled={saving || !draft.trim()} onClick={save}>{saving ? 'Saving…' : 'Save'}</button>
          <button className="btn ghost" onClick={() => { setEditing(false); setDraft(value || ''); setErr(null) }}>Cancel</button>
        </div>
      </div>
    )
  }
  return (
    <div className="editable">
      <p className={className} dir="auto">{value}</p>
      {canEdit && (
        <button className="pen" title={label} aria-label={label}
          onClick={() => { setDraft(value || ''); setEditing(true) }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
          <span>{label}</span>
        </button>
      )}
    </div>
  )
}

// Tam logo: an open ring around a filled disc, with تم in the centre.
// mono: single colour (used inside the green approval stamp).
export function Logo({ size = 40, title, mono = false }) {
  const ring = mono ? 'currentColor' : 'var(--logo-ring)'
  const disc = mono ? 'currentColor' : 'var(--logo-disc)'
  const text = mono ? 'var(--surface)' : '#ffffff'
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" role={title ? 'img' : undefined}
      aria-label={title} aria-hidden={title ? undefined : true}>
      {/* open ring: a 300° arc with the gap at the top right */}
      <path d="M 76.5 16.1 A 43 43 0 1 0 91.5 38.9" fill="none" stroke={ring} strokeWidth="11" strokeLinecap="butt" />
      <circle cx="50" cy="50" r="29" fill={disc} />
      <text x="50" y="45" textAnchor="middle" dominantBaseline="central" fill={text}
        fontFamily="'IBM Plex Sans Arabic', 'Segoe UI', Tahoma, Arial, sans-serif" fontWeight="700" fontSize="36">تم</text>
    </svg>
  )
}
