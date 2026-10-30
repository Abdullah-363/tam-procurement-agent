# Tam (تمّ): an autonomous procurement agent

[![tests](https://github.com/Abdullah-363/tam-procurement-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/Abdullah-363/tam-procurement-agent/actions/workflows/tests.yml)

**HUMAIN AI Hackathon · Challenge 3: Autonomous Enterprise**

Tam takes ownership of a company's purchase requests from the employee's first message to procurement's inbox.
It drafts the request from plain Arabic or English, checks it against budget and policy **before anyone signs**,
routes it to the right approvers, chases and escalates, drafts the justification after a rejection, renews
expiring licenses and cancels wasted phone lines on its own, and keeps a tamper-evident audit trail.
Humans only decide.

> In a typical Saudi enterprise today a purchase request is a printed form that collects 4-5 wet signatures,
> 4-12 print/scan cycles and 10-50 emails, takes days to over a month, and about 1 in 3 come back for rework.

## Results (details in [`backend/evals/RESULTS.md`](backend/evals/RESULTS.md))

| | Result |
|---|---|
| Regression tests (36, offline) | 36/36 |
| Dev set (16 cases), after one fix | 16/16 |
| **Held-out set (16 unseen cases), first run** | **15/16 (93.8%)** |
| Held-out repeated 3 times (consistency) | 45/48: same single case each time |
| Held-out with `claude-sonnet-5-5` | 16/16 (100%), ~40% slower |
| Policy-breaking requests reaching approvers (all normal runs, both models) | **0** |
| Ablation, deterministic rules layer off | 1 policy-breaking request got through |
| Ablation, lookup tools off | pass rate falls to 50% |
| Cost | ~0.4 US cents per request (`claude-haiku-5-5`) |

## How it works

```
 Employee (chat, AR/EN)          Approvers (one click)          Auditor (questions, audit pack)
          │                               ▲                                 │
          ▼                               │                                 ▼
 ┌────────────────────────── Tam agent (Claude, tool-calling loop) ──────────────────────────┐
 │  understands the need · plans · writes justifications · decides when to ask vs. act      │
 └───────────────┬───────────────────────────────┬───────────────────────────────┬──────────┘
                 ▼                               ▼                               ▼
     Lookup tools (grounding)         Deterministic rules (code)         Actions (workflow)
     catalog + price history,         procurement method, approval       draft, submit, approve,
     budget per G/L, vendors,         chain, HR confirmation, mobile     remind, escalate, hand off,
     HR directory, phone lines        policy, 11 validation checks       activate / cancel lines
                 └───────────────────────────────┴───────────────────────────────┘
                                                 ▼
                       SQLite + hash-chained audit log (every action, tamper-evident)
```

**Key design decision: the LLM handles judgment and language; code handles policy.** The model never decides
budgets, thresholds or approvers by itself. It calls tools that run deterministic rules, and the rules block any
submission that breaks policy. The ablations show why: without the rules layer, a policy-breaking request
reached approvers; without the lookup tools, the agent mis-priced a request and routed it to the wrong approver.

### What Tam handles
* **Purchase requests:** Low Value / RFQ (3 quotes) / mandatory competitive bidding / sole source /
  framework call-offs, approval tiers up to the CEO, HR headcount confirmation for new seats and new hires.
* **Error catching before signatures:** totals, wrong G/L account, wrong method, vague justification,
  support items without their main item, prices far above the last purchase, false sole-source claims,
  insufficient budget, unknown items.
* **Follow-up:** reminders and escalation by urgency; after a rejection, a six-point justification memo for the
  requester to edit and resubmit; text locked after the first signature; full approval history kept.
* **Proactive scan:** opens renewal requests before licenses expire (Adobe, SAP) and asks IT to cancel STC lines
  still billing for people who left.
* **Company phones:** eligibility by grade (managers: iPhone Pro + unlimited roaming; staff: iPhone, no unlimited
  roaming; interns: not eligible) under an STC framework agreement.
* **Audit:** plain-language questions over the records, automatic compliance findings, one-click audit pack,
  log integrity verification.

## Run it

Requirements: Python 3.11+, Node 18+, a Claude API key.

```
# backend (terminal 1)
cd backend
pip install -r requirements.txt
copy .env.example .env          # then paste your ANTHROPIC_API_KEY into .env
python -m uvicorn app.main:app --reload

# frontend (terminal 2)
cd frontend
npm install
npm run dev                     # open http://localhost:5173
```

Tests and evaluation (from `backend/`):
```
python -m pytest -q                                   # 36 offline regression tests, no API cost
python -m evals.run --set dev                         # 16 dev cases against the real agent
python -m evals.run --set heldout                     # 16 held-out cases
python -m evals.run --set dev --ablation no_validation
python -m evals.run --set dev --ablation no_grounding
```

## Repository map

| Path | Purpose |
|---|---|
| `backend/app/agent.py` | Tool-calling loop (step and token limits), tools, prompts for requester / renewal / justification / audit modes |
| `backend/app/rules.py` | Deterministic policy: methods, approval chains, validation, mobile policy, audit findings |
| `backend/app/workflow.py` | Request lifecycle: drafts, approvals, reminders, escalation, hand-off, renewals, lines |
| `backend/app/store.py` | SQLite, simulated company clock, hash-chained audit log |
| `backend/app/documents.py` | Printable PR form and audit pack |
| `backend/data/make_data.py` | Generates the synthetic company (people, budgets, catalog, vendors, history, phone lines) |
| `backend/tests/` | Regression tests |
| `backend/evals/` | Evaluation cases, runner, results and write-up |
| `frontend/` | React UI: request chat, approvals, tracker, audit |

## Data

All data is synthetic and generated by `backend/data/make_data.py`: a fictional company (Raseen Holding),
fictional people and vendors, budgets per G/L account, a 50-item catalog with last purchase prices, purchase
history with planted compliance problems, and an HR directory. Real product or operator names (SAP, Bloomberg,
STC, Microsoft, Adobe) are used only where they make a policy rule realistic.

## Limitations and next steps
* Integrations are simulated: next would be SAP S/4HANA (PO creation), Microsoft Teams/Outlook (approvals and
  reminders where people already work) and SSO.
* One over-cautious clarification on the held-out set (exhibition booth); the agent sometimes asks when it
  could act. Thresholds for "ask vs. act" could become configurable per company.
* Vendor quotation comparison and technical evaluation forms are designed but not yet built.
