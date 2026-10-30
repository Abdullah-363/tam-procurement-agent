# Tam (تمّ) — backend

Autonomous procurement agent: owns a purchase request from "we need laptops" to "sent to procurement",
catches errors before anyone signs, chases approvers, drafts justifications after rejection, renews expiring
licenses on its own, and keeps a tamper-evident audit trail.

## Run (Windows, from this `backend` folder)

```
pip install -r requirements.txt
copy .env.example .env          # then put your key in .env
python try_agent.py             # one real agent run in the terminal
uvicorn app.main:app --reload   # start the API
```

Open http://127.0.0.1:8000/docs to try every endpoint in the browser.
Offline test (no credits used): `python -m tests.test_flow`

## Layout

| File | What it does |
|---|---|
| `data/make_data.py` | Fictional company data: people, policy, catalog, vendors, renewals, history; writes `budget.xlsx` |
| `app/rules.py` | Deterministic rules: procurement method, approval chain, validation, budget, audit findings |
| `app/workflow.py` | PR lifecycle: draft, submit, approve/reject, reminders, escalation, handoff, renewals |
| `app/store.py` | SQLite, simulated clock, hash-chained audit log |
| `app/agent.py` | Claude tool-calling loop + tools + prompts (requester / renewal / justify / audit) |
| `app/documents.py` | Printable PR form and audit pack (HTML → Ctrl+P → PDF) |
| `app/main.py` | FastAPI endpoints |

## Key endpoints

- `POST /api/agent/chat` `{message}` — requester talks to the agent
- `POST /api/agent/renewals` `{within_days}` — proactive scan (try 30, then 90 for SAP)
- `GET /api/inbox/{role}` — roles: it_head, accountant, finance_head, cfo, ceo, procurement_head
- `POST /api/prs/{id}/decision` `{role, decision: approve|reject, comment}` — rejection triggers the memo
- `POST /api/prs/{id}/resubmit`
- `POST /api/clock/advance` `{hours}` — fast-forward; reminders and escalations fire
- `POST /api/audit/ask` `{question}` · `GET /api/audit/findings` · `GET /api/audit/verify`
- `GET /api/audit/pack` and `GET /api/prs/{id}/document` — open in the browser
- `POST /api/reset` — start the demo fresh · `POST /api/demo/tamper` — show the log catching an edit

## Policy (SAR, fictional company)

Low Value < 20,000 (1 quote) · RFQ 20,000–200,000 (3 quotes) · Competitive Bidding ≥ 200,000 (mandatory) ·
Sole Source exempt from bidding, needs justification · Price > 20% above last purchase → flagged.
Approvals: Head of dept → Accountant → Finance Head (< 40k) / CFO (40k–200k) / CFO + CEO (> 200k).
Urgent: reminder after 6h, escalation after 24h (Normal: 48h / 96h).
