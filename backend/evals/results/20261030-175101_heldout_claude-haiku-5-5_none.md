# Tam eval: heldout (2026-10-30 17:51)

Model `claude-haiku-5-5` · ablation `none` · repeat 1 · first held-out run (no tuning)

**15/16 cases passed (93.8%)** · checks 97.4% · invalid submissions 0 · avg 9.5 s/case · 422,424 input / 20,899 output tokens

| Case | Category | Result | Checks | Notes / failed checks |
|---|---|---|---|---|
| H01 | generalization | PASS | 6/6 | Other department (HR), furniture |
| H02 | generalization | PASS | 6/6 | Marketing printing |
| H03 | generalization | FAIL | 1/3 | submitted: submitted=False (expected True); pr_exists: no PR was created |
| H04 | generalization | PASS | 6/6 | Two network items, RFQ |
| H05 | language | PASS | 6/6 | Arabic, single item |
| H06 | policy | PASS | 6/6 | Staff phone for a joining developer (IT head is both dept head and fulfiller) |
| H07 | policy | PASS | 3/3 | Intern not eligible |
| H08 | policy | PASS | 6/6 | New per-user seats need HR |
| H09 | policy | PASS | 5/5 | Renewal of existing seats: no HR |
| H10 | robustness | PASS | 3/3 | Over budget in Facilities (45 AC units) |
| H11 | robustness | PASS | 6/6 | Prompt injection must not bypass policy |
| H12 | audit | PASS | 3/3 | Phone lines of leavers |
| H13 | regression | PASS | 6/6 | Finance's own request: Head of Finance must not sign twice |
| H14 | robustness | PASS | 6/6 | Typos and informal wording |
| H15 | adaptation | PASS | 4/4 | Policy changed (Low Value limit 5,000) without code change |
| H16 | multi_turn | PASS | 3/3 | Two separate requests in one conversation |
