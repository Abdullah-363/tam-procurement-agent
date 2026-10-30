// Thin wrapper around the FastAPI backend (proxied at /api by Vite).
async function call(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

export const api = {
  state: () => call('/state'),
  reset: () => call('/reset', { method: 'POST' }),
  advance: (hours) => call('/clock/advance', { method: 'POST', body: { hours } }),
  chat: (message, session_id) => call('/agent/chat', { method: 'POST', body: { message, session_id } }),
  renewals: (within_days) => call('/agent/renewals', { method: 'POST', body: { within_days } }),
  prs: () => call('/prs'),
  pr: (id) => call(`/prs/${id}`),
  decide: (id, role, decision, comment) =>
    call(`/prs/${id}/decision`, { method: 'POST', body: { role, decision, comment } }),
  editText: (id, role, fields) => call(`/prs/${id}/text`, { method: 'PATCH', body: { role, ...fields } }),
  resubmit: (id) => call(`/prs/${id}/resubmit`, { method: 'POST' }),
  inbox: (role) => call(`/inbox/${role}`),
  budget: () => call('/budget'),
  findings: () => call('/audit/findings'),
  verify: () => call('/audit/verify'),
  tamper: () => call('/demo/tamper', { method: 'POST' }),
  ask: (question, session_id) => call('/audit/ask', { method: 'POST', body: { question, session_id } }),
}

export const sar = (n) =>
  `${Number(n || 0).toLocaleString('en-US', { maximumFractionDigits: 0 })} SAR`

export const ROLES = [
  { id: 'it_head', label: 'Head of IT' },
  { id: 'admin_head', label: 'Head of Admin' },
  { id: 'hr_head', label: 'Head of HR' },
  { id: 'marketing_head', label: 'Head of Marketing' },
  { id: 'accountant', label: 'Accountant' },
  { id: 'finance_head', label: 'Head of Finance' },
  { id: 'cfo', label: 'CFO' },
  { id: 'ceo', label: 'CEO' },
  { id: 'procurement_head', label: 'Procurement' },
]

export const TOOL_LABELS = {
  search_catalog: 'Searched the item catalog',
  get_price_history: 'Checked last purchase price and vendors',
  check_budget: 'Checked the budget',
  get_procurement_rules: 'Applied procurement policy',
  create_pr_draft: 'Drafted the purchase request',
  update_pr_draft: 'Corrected the draft',
  submit_pr: 'Submitted into the approval chain',
  get_pr: 'Read the purchase request',
  list_open_prs: 'Listed open requests',
  save_justification_memo: 'Saved the justification memo',
  list_renewals_due: 'Scanned licenses and contracts for expiry',
  find_purchases: 'Searched purchase records',
  run_compliance_checks: 'Checked every purchase against policy',
  get_audit_trail: 'Pulled the audit trail',
  spend_summary: 'Summarized spend against budget',
  verify_audit_log: 'Verified the audit log',
  check_mobile_eligibility: 'Checked mobile eligibility (HR directory and policy)',
  list_mobile_lines: 'Checked company phone lines',
  request_line_cancellation: 'Asked IT to cancel a phone line',
}
