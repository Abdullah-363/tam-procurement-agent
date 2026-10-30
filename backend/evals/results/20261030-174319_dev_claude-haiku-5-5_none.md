# Tam eval: dev (2026-10-30 17:43)

Model `claude-haiku-5-5` · ablation `none` · repeat 1 · after sole-source fix

**16/16 cases passed (100.0%)** · checks 100.0% · invalid submissions 0 · avg 10.7 s/case · 409,192 input / 26,415 output tokens

| Case | Category | Result | Checks | Notes / failed checks |
|---|---|---|---|---|
| D01 | standard | PASS | 6/6 | Simple low-value IT order |
| D02 | standard | PASS | 7/7 | Urgent laptops for people joining -> RFQ, CFO tier, HR confirms hires |
| D03 | error_catching | PASS | 2/2 | Filled form with 4 planted mistakes must be caught and corrected (never submitted as given) |
| D04 | error_catching | PASS | 3/3 | Price 35% above last purchase: must ask, not submit |
| D05 | error_catching | PASS | 1/1 | Support/licenses without the controller they belong to |
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
