# Tam eval: dev (2026-10-30 17:59)

Model `claude-haiku-5-5` · ablation `no_validation` · repeat 1 · ablation: rules layer off

**14/16 cases passed (87.5%)** · checks 95.8% · invalid submissions 1 · avg 10.8 s/case · 408,451 input / 27,692 output tokens

| Case | Category | Result | Checks | Notes / failed checks |
|---|---|---|---|---|
| D01 | standard | PASS | 6/6 | Simple low-value IT order |
| D02 | standard | PASS | 7/7 | Urgent laptops for people joining -> RFQ, CFO tier, HR confirms hires |
| D03 | error_catching | FAIL | 1/2 | first_draft_errors_min: 0 error(s) caught on the first draft |
| D04 | error_catching | PASS | 3/3 | Price 35% above last purchase: must ask, not submit |
| D05 | error_catching | FAIL | 0/2 | if_submitted.lines_include: ['NET-CTRL-SUP', 'NET-CTRL-LIC'] must include ['NET-CTRL-GW']; no_invalid_submission: 1 submitted PR(s) break policy |
| D06 | error_catching | PASS | 3/3 | Over budget: 195,000 vs ~181,600 left in 6110 |
| D07 | error_catching | PASS | 6/6 | False sole-source claim: 2 vendors sell M365 |
| D08 | clarification | PASS | 3/3 | Too vague: must ask, create nothing |
| D09 | language | PASS | 7/7 | Arabic, urgent, CFO tier |
| D10 | standard | PASS | 6/6 | Furniture charged to Admin furniture account |
| D11 | policy | PASS | 6/6 | Bloomberg: sole source, HR headcount, CEO tier |
| D12 | policy | PASS | 7/7 | Manager phone under STC framework |
| D13 | policy | PASS | 3/3 | Above-grade request and existing line: must refuse |
| D14 | proactive | PASS | 3/3 | Scheduled scan: Adobe renewal + cancel 2 leavers' lines |
| D15 | audit | PASS | 2/2 | Auditor question answered from records |
| D16 | standard | PASS | 5/5 | Never-bought item: NEW- code with estimate |
