# How Tam is evaluated

## Two layers of testing

| Layer | What it checks | Cost | Command (from `backend/`) |
|---|---|---|---|
| **Regression tests** (`tests/test_rules.py`, 36 tests) | Every deterministic business rule: method thresholds, approval chains, HR confirmation, validation of the classic PR mistakes, mobile policy, budget commitment, editing locks, reminders/escalation, audit findings, tamper detection | Free (no API) | `python -m pytest -q` |
| **Agent evaluation** (`evals/run.py`) | The real agent end to end: given a request in natural language, does the right purchase request come out? | API tokens | `python -m evals.run --set dev` |

## Agent evaluation method

* Every case starts from a **fresh company database** (same seed data), sends the case's message(s) to the
  agent, then scores the **outcome stored in the database**, not the wording: was a PR submitted or not,
  procurement method, G/L account, value (±1%), approval chain, items, lines cancelled, Arabic reply, etc.
* A case passes only if **all** its checks pass. Every case also checks that **no submitted PR breaks policy**
  (re-validated with the real rules, even during ablations).
* **Dev set** (`cases/dev.json`, 16 cases): used while improving prompts and rules.
* **Held-out set** (`cases/heldout.json`, 16 cases): written before tuning and run only for final reporting.
  It uses different departments, items and phrasing, plus robustness cases:
  Arabic, typos, prompt injection, over-budget in another account, a **policy change applied at run time
  without code changes** (adaptation), a multi-request conversation, and a regression case for a bug the
  regression tests found (Head of Finance signing twice on Finance's own requests).
* `--repeat N` runs each case N times to measure consistency (LLM outputs vary).

## Ablations (do the components matter?)

| Flag | What is removed | Question it answers |
|---|---|---|
| `--ablation no_validation` | The deterministic rule layer (validation feedback and submission blocking) | Does the rule layer prevent policy-breaking submissions, or would the LLM alone get it right? |
| `--ablation no_grounding` | The lookup tools (catalog, price history, budget, policy, HR directory) | Does grounding in company data matter, or can the model guess items, prices and policy? |

The key metric for ablations is **invalid submissions**: PRs that reached approvers while breaking policy.

## Outputs

Each run writes `results/<time>_<set>_<model>_<ablation>.json` (full detail: checks, tools used, replies,
tokens, seconds) and a `.md` table, and appends one line to `results/history.csv`, so every iteration
leaves a before/after record.
