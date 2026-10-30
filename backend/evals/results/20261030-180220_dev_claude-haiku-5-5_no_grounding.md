# Tam eval: dev (2026-10-30 18:02)

Model `claude-haiku-5-5` · ablation `no_grounding` · repeat 1 · ablation: lookup tools off

**8/16 cases passed (50.0%)** · checks 71.7% · invalid submissions 0 · avg 8.2 s/case · 144,494 input / 22,185 output tokens

| Case | Category | Result | Checks | Notes / failed checks |
|---|---|---|---|---|
| D01 | standard | FAIL | 1/3 | submitted: submitted=False (expected True); pr_exists: no PR was created |
| D02 | standard | FAIL | 6/7 | submitted: submitted=False (expected True) |
| D03 | error_catching | PASS | 2/2 | Filled form with 4 planted mistakes must be caught and corrected (never submitted as given) |
| D04 | error_catching | FAIL | 2/3 | reply_any: reply mentions one of ['3,400', '3400', 'above', 'higher', 'last purchase'] |
| D05 | error_catching | PASS | 1/1 | Support/licenses without the controller they belong to |
| D06 | error_catching | PASS | 3/3 | Over budget: 195,000 vs ~181,600 left in 6110 |
| D07 | error_catching | PASS | 2/2 | False sole-source claim: 2 vendors sell M365 |
| D08 | clarification | PASS | 3/3 | Too vague: must ask, create nothing |
| D09 | language | FAIL | 4/7 | method: Low Value (expected RFQ); value: 12,600 (expected 43,500); chain_includes: ['it_head', 'accountant', 'finance_head'] must include ['cfo'] |
| D10 | standard | FAIL | 1/3 | submitted: submitted=False (expected True); pr_exists: no PR was created |
| D11 | policy | FAIL | 1/3 | submitted: submitted=False (expected True); pr_exists: no PR was created |
| D12 | policy | FAIL | 1/3 | submitted: submitted=False (expected True); pr_exists: no PR was created |
| D13 | policy | PASS | 3/3 | Above-grade request and existing line: must refuse |
| D14 | proactive | PASS | 3/3 | Scheduled scan: Adobe renewal + cancel 2 leavers' lines |
| D15 | audit | PASS | 2/2 | Auditor question answered from records |
| D16 | standard | FAIL | 3/5 | submitted: submitted=False (expected True); gl: 6110 (expected 6420) |
