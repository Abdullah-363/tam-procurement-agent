"""
The Tam agent: a plain tool-calling loop around the Claude API.

The model reads the request, plans, and calls tools. The tools run OUR
deterministic code (rules.py, workflow.py), so the model never invents
budgets, thresholds or approvers. Guards: max steps, max tokens, and a
token counter per run.
"""
import json
import os
from datetime import datetime

from dotenv import load_dotenv

from . import rules, store, workflow as wf

load_dotenv()
MODEL = os.getenv("TAM_MODEL") or os.getenv("MUTAMAD_MODEL") or "claude-haiku-5-5"
MAX_STEPS = int(os.getenv("TAM_MAX_STEPS") or os.getenv("MUTAMAD_MAX_STEPS") or 14)
MAX_TOKENS = int(os.getenv("TAM_MAX_TOKENS") or os.getenv("MUTAMAD_MAX_TOKENS") or 4000)

_client = None
SESSIONS = {}           # session_id -> message history (kept in memory)
USAGE = {"input_tokens": 0, "output_tokens": 0, "runs": 0}


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment / .env
    return _client


def set_client(c):
    """Used by tests to plug in a scripted fake client."""
    global _client
    _client = c


# ====================================================================== tools
def _pr_brief(pr):
    return {"id": pr["id"], "title": pr["title"], "status": pr["status"], "value_sar": pr["estimated_value"],
            "method": pr["method"], "gl_account": pr["gl_account"], "doc_type": pr["doc_type"],
            "lines": pr["lines"], "preferred_vendor": pr["preferred_vendor"],
            "justification": pr["justification"],
            "validation": pr["validation"], "summary": rules.summarize_issues(pr["validation"])}


def t_search_catalog(query=""):
    q = query.lower()
    raw = [w for w in q.replace(",", " ").replace("-", " ").split() if len(w) > 2]
    # simple plural handling so "desks" finds "desk", "chairs" finds "chair", "supplies" finds "supply"
    words = []
    for w in raw:
        words.append(w)
        if w.endswith("ies"):
            words.append(w[:-3] + "y")
        elif w.endswith("es") and len(w) > 4:
            words.append(w[:-2])
        if w.endswith("s") and len(w) > 3:
            words.append(w[:-1])
    out = []
    for i in store.company()["catalog"]:
        hay = (i["code"] + " " + i["name"] + " " + i["category"]).lower()
        if not words or any(w in hay for w in words):
            out.append({"item_code": i["code"], "name": i["name"], "category": i["category"],
                        "gl_account": i["gl"], "reference_price_sar": i["ref_price"],
                        "requires_item": i.get("requires"),
                        "vendors_available": len(rules.vendors_for_item(i))})
    if not out:
        return {"items": [], "catalog_size": len(store.company()["catalog"]),
                "note": "No catalog match. Try other words (search by category too: furniture, office_supplies, "
                        "facilities, hardware, network, software, training, printing, events). If the company has "
                        "truly never bought it, use item_code NEW-<NAME> with a description and a realistic market "
                        "estimate in SAR."}
    return {"items": out, "catalog_size": len(store.company()["catalog"])}


def t_get_price_history(item_code):
    item = rules.catalog().get(item_code.upper())
    if not item:
        return {"error": f"Unknown item {item_code}"}
    vs = rules.vendors()
    return {"item_code": item["code"], "name": item["name"], "last_purchase_unit_price_sar": item["ref_price"],
            "gl_account": item["gl"],
            "vendors": [{"id": v, "name": vs[v]["name"], "rating": vs[v]["rating"]} for v in rules.vendors_for_item(item)],
            "sole_source": bool(item.get("sole_source_vendor"))}


def t_check_budget(gl_account, amount):
    return rules.check_budget(str(gl_account), float(amount))


def t_get_procurement_rules(amount, sole_source=False, department="IT", new_user_seats=False, for_new_hires=False):
    m = rules.required_method(float(amount), bool(sole_source))
    probe = {"lines": [], "extra": {"for_new_hires": bool(new_user_seats or for_new_hires)}}
    out = m | {"approval_chain": rules.chain_with_names(rules.approval_chain(float(amount), department, probe))}
    if new_user_seats or for_new_hires:
        out["hr_confirmation"] = "HR (Head of HR) confirms the headcount after the department head."
    return out


def t_create_pr_draft(**fields):
    renewal_id = fields.pop("renewal_id", None)
    source = "agent-renewal" if renewal_id else "requester"
    if renewal_id:
        fields.setdefault("extra", {})["renewal_id"] = renewal_id
    pr = wf.create_draft(fields, source=source)
    return _pr_brief(pr)


def t_update_pr_draft(pr_id, changes):
    return _pr_brief(wf.update_draft(pr_id, changes))


def t_submit_pr(pr_id):
    return wf.submit(pr_id)


def t_get_pr(pr_id):
    pr = store.get_pr(pr_id)
    if not pr:
        return {"error": f"{pr_id} not found"}
    b = _pr_brief(pr)
    b["approvals"] = [{"step": a["step"], "name": a["person"], "role": a["role"], "status": a["status"],
                       "requested_at": a["requested_at"], "decided_at": a["decided_at"], "comment": a["comment"]}
                      for a in pr["approvals"]]
    b["justification_memo"] = (pr.get("extra") or {}).get("justification_memo")
    return b


def t_list_open_prs():
    return [{"id": p["id"], "title": p["title"], "status": p["status"], "value_sar": p["estimated_value"]}
            for p in store.list_prs() if p["source"] != "history"]


def t_save_justification_memo(pr_id, memo):
    return wf.save_justification(pr_id, memo)


def t_list_renewals_due(within_days=45):
    return wf.renewals_due(int(within_days))


# ---- mobile phones and lines
def t_check_mobile_eligibility(employee):
    emp = store.find_employee(employee)
    if not emp:
        names = [e["name"] for e in store.employees()]
        return {"error": f"No unique employee matches '{employee}'.", "directory": names}
    mp = rules.policy()["mobile_policy"]
    ent = mp.get(emp["grade"])
    lines = [l for l in store.mobile_lines() if l["employee_id"] == emp["id"] and l["status"] != "cancelled"]
    cat = rules.catalog()
    out = {"employee_id": emp["id"], "name": emp["name"], "title": emp["title"], "department": emp["department"],
           "grade": emp["grade"], "status": emp["status"], "start_date": emp.get("start_date"),
           "left_date": emp.get("left_date"),
           "existing_lines": [{"number": l["number"], "status": l["status"], "package": l["package"]} for l in lines]}
    if emp["status"] == "left":
        out["eligible"] = False
        out["reason"] = "Employee has left the company."
    elif not ent:
        out["eligible"] = False
        out["reason"] = f"Grade '{emp['grade']}' is not eligible for a company phone."
    else:
        out["eligible"] = True
        out["entitlement"] = {
            "summary": ent["label"],
            "device": {"item_code": ent["device"], "name": cat[ent["device"]]["name"], "unit_price": cat[ent["device"]]["ref_price"]},
            "package": {"item_code": ent["package"], "name": cat[ent["package"]]["name"],
                        "monthly_price": cat[ent["package"]]["ref_price"], "qty_months": mp["commitment_months"]},
            "gl_account": cat[ent["device"]]["gl"], "method": rules.FRAMEWORK_METHOD,
            "framework_agreement": "FA-STC-2026 (STC)", "preferred_vendor": "V-STC",
            "approval_chain": "Head of HR (eligibility) -> department head -> Head of IT (fulfils)"}
    return out


def t_list_mobile_lines(only_problems=False):
    rows = []
    for l in store.mobile_lines():
        e = l["employee"]
        problem = l["status"] == "active" and e.get("status") == "left"
        if only_problems and not problem:
            continue
        rows.append({"number": l["number"], "employee": e.get("name"), "employee_status": e.get("status"),
                     "left_date": e.get("left_date"), "package": l["package"], "monthly_sar": l["monthly"],
                     "status": l["status"], "problem": "employee left, line still active" if problem else None})
    return {"count": len(rows), "monthly_total_sar": sum(r["monthly_sar"] for r in rows if r["status"] == "active"),
            "lines": rows}


def t_request_line_cancellation(number, reason=""):
    return wf.request_line_cancellation(number, reason)


# ---- audit tools
def t_find_purchases(department=None, gl_account=None, min_value=None, max_value=None,
                     method=None, status=None, since_days=None):
    out = []
    now = store.now()
    for p in store.list_prs():
        if department and p["department"] != department: continue
        if gl_account and p["gl_account"] != str(gl_account): continue
        if min_value is not None and p["estimated_value"] < float(min_value): continue
        if max_value is not None and p["estimated_value"] > float(max_value): continue
        if method and p["method"].lower() != method.lower(): continue
        if status and p["status"] != status: continue
        if since_days and (now - datetime.strptime(p["created_at"], "%Y-%m-%d %H:%M")).days > int(since_days): continue
        full = store.get_pr(p["id"])
        out.append({"id": p["id"], "title": p["title"], "date": p["created_at"][:10], "value_sar": p["estimated_value"],
                    "gl_account": p["gl_account"], "method": p["method"], "quotes": p["quotes_count"],
                    "status": p["status"],
                    "approved_by": [f"{a['person']} ({a['role']})" for a in full["approvals"] if a["status"] == "approved"],
                    "documents": [d["kind"] for d in full["documents"]]})
    return {"count": len(out), "total_sar": sum(o["value_sar"] for o in out), "purchases": out}


def t_run_compliance_checks():
    f = rules.audit_findings()
    return {"findings_count": len(f), "findings": f}


def t_get_audit_trail(pr_id):
    ev = store.events_for(pr_id)
    return {"pr_id": pr_id, "entries": [{"ts": e["ts"], "actor": e["actor"], "action": e["action"],
                                         "details": e["details"]} for e in ev]}


def t_spend_summary(group_by="gl_account"):
    sums = {}
    for p in store.list_prs():
        if p["status"] not in ("approved", "sent_to_procurement"):
            continue
        k = p.get(group_by) or "n/a"
        sums[k] = sums.get(k, 0) + p["estimated_value"]
    budget = {r["gl"]: r for r in store.budget_rows()}
    return {"group_by": group_by, "approved_spend_sar": sums,
            "budget": {gl: {"name": r["name"], "annual": r["annual"], "spent_ytd": r["spent"],
                            "committed_by_agent": r["committed"], "remaining": r["remaining"]}
                       for gl, r in budget.items()}}


def t_verify_audit_log():
    return store.verify_chain()


# ---------------------------------------------------------------- schemas
LINES_SCHEMA = {"type": "array", "items": {"type": "object", "properties": {
    "item_code": {"type": "string"}, "qty": {"type": "number"},
    "unit_price": {"type": "number", "description": "SAR per unit"},
    "description": {"type": "string"}}, "required": ["item_code", "qty", "unit_price"]}}

PR_FIELDS = {
    "title": {"type": "string"},
    "department": {"type": "string", "description": "e.g. IT"},
    "doc_type": {"type": "string", "enum": ["Normal", "Urgent", "Budgetary", "Outline Agreement"]},
    "request_type": {"type": "string", "enum": ["New Procurement", "Agreement Renewal", "Scope Change"]},
    "method": {"type": "string", "enum": ["Low Value", "RFQ", "Competitive Bidding", "Sole Source", "Framework Agreement"]},
    "gl_account": {"type": "string"},
    "cost_center": {"type": "string"},
    "preferred_vendor": {"type": "string", "description": "vendor id, e.g. V-ZAW"},
    "justification": {"type": "string", "description": "business need, what is replaced/added, impact if not approved"},
    "sole_source": {"type": "boolean"},
    "lines": LINES_SCHEMA,
    "estimated_value": {"type": "number", "description": "SAR; omit to use the sum of lines"},
    "employee_id": {"type": "string", "description": "for phones/lines: the employee receiving it (from check_mobile_eligibility)"},
    "for_new_hires": {"type": "boolean", "description": "true when the purchase is for new employees (HR confirms headcount)"},
}

TOOLS = {
    "search_catalog": (t_search_catalog, "Search the company item catalog. Returns item codes, G/L account and reference (last purchase) price.",
                       {"query": {"type": "string"}}, []),
    "get_price_history": (t_get_price_history, "Last purchase price and registered vendors for an item.",
                          {"item_code": {"type": "string"}}, ["item_code"]),
    "check_budget": (t_check_budget, "Remaining budget for a G/L account and what is left after an amount.",
                     {"gl_account": {"type": "string"}, "amount": {"type": "number"}}, ["gl_account", "amount"]),
    "get_procurement_rules": (t_get_procurement_rules, "Required procurement method and approval chain for an amount (company policy).",
                              {"amount": {"type": "number"}, "sole_source": {"type": "boolean"},
                               "department": {"type": "string"},
                               "new_user_seats": {"type": "boolean", "description": "new per-user licenses/subscriptions"},
                               "for_new_hires": {"type": "boolean", "description": "purchase is for new employees"}}, ["amount"]),
    "create_pr_draft": (t_create_pr_draft, "Create a purchase request draft. It is validated automatically; the result lists errors/warnings.",
                        PR_FIELDS | {"renewal_id": {"type": "string", "description": "only for renewals"}},
                        ["title", "department", "gl_account", "lines", "justification"]),
    "update_pr_draft": (t_update_pr_draft, "Change fields of a draft; it is re-validated.",
                        {"pr_id": {"type": "string"}, "changes": {"type": "object", "properties": PR_FIELDS}},
                        ["pr_id", "changes"]),
    "submit_pr": (t_submit_pr, "Submit a draft with no validation errors into the approval chain.",
                  {"pr_id": {"type": "string"}}, ["pr_id"]),
    "get_pr": (t_get_pr, "Full status of a PR including approvals.", {"pr_id": {"type": "string"}}, ["pr_id"]),
    "list_open_prs": (t_list_open_prs, "List current (non-historical) PRs.", {}, []),
    "save_justification_memo": (t_save_justification_memo, "Save a justification memo on a PR for the requester to review.",
                                {"pr_id": {"type": "string"}, "memo": {"type": "string"}}, ["pr_id", "memo"]),
    "list_renewals_due": (t_list_renewals_due, "Licenses/contracts expiring within N days, with the renewal quote price.",
                          {"within_days": {"type": "integer"}}, []),
    "check_mobile_eligibility": (t_check_mobile_eligibility, "HR directory + mobile policy: is this employee eligible for a "
                                 "company phone/line, which device and package their grade gets, and any existing line.",
                                 {"employee": {"type": "string", "description": "name or employee id"}}, ["employee"]),
    "list_mobile_lines": (t_list_mobile_lines, "All company STC lines with the holder and status.",
                          {"only_problems": {"type": "boolean"}}, []),
    "request_line_cancellation": (t_request_line_cancellation, "Ask IT to cancel an STC line (e.g. the employee left).",
                                  {"number": {"type": "string"}, "reason": {"type": "string"}}, ["number"]),
    "find_purchases": (t_find_purchases, "Search all purchases (historical and current) with filters.",
                       {"department": {"type": "string"}, "gl_account": {"type": "string"},
                        "min_value": {"type": "number"}, "max_value": {"type": "number"},
                        "method": {"type": "string"}, "status": {"type": "string"},
                        "since_days": {"type": "integer"}}, []),
    "run_compliance_checks": (t_run_compliance_checks, "Check every purchase against policy: method, quotes, approval chain, documents.", {}, []),
    "get_audit_trail": (t_get_audit_trail, "Complete time-stamped audit trail of one PR.", {"pr_id": {"type": "string"}}, ["pr_id"]),
    "spend_summary": (t_spend_summary, "Approved spend grouped by a field, plus budget per G/L account.",
                      {"group_by": {"type": "string", "enum": ["gl_account", "method", "department", "preferred_vendor"]}}, []),
    "verify_audit_log": (t_verify_audit_log, "Verify the tamper-evident hash chain of the audit log.", {}, []),
}

TOOLSETS = {
    "requester": ["search_catalog", "get_price_history", "check_budget", "get_procurement_rules", "check_mobile_eligibility",
                  "create_pr_draft", "update_pr_draft", "submit_pr", "get_pr", "list_open_prs",
                  "save_justification_memo"],
    "renewal": ["list_renewals_due", "list_mobile_lines", "request_line_cancellation", "search_catalog", "get_price_history", "check_budget",
                "get_procurement_rules", "create_pr_draft", "update_pr_draft", "submit_pr",
                "save_justification_memo"],
    "justify": ["get_pr", "get_price_history", "check_budget", "get_procurement_rules", "save_justification_memo"],
    "audit": ["find_purchases", "run_compliance_checks", "get_audit_trail", "spend_summary", "list_mobile_lines",
              "verify_audit_log", "get_procurement_rules"],
}


# Ablation switch for evaluation only (evals/run.py --ablation no_grounding): hides the lookup tools,
# so the model must rely on its own knowledge for items, prices, budget and policy.
ABLATE_GROUNDING = False
GROUNDING_TOOLS = {"search_catalog", "get_price_history", "check_budget", "get_procurement_rules",
                   "check_mobile_eligibility"}


def tool_specs(names):
    return [{"name": n, "description": TOOLS[n][1],
             "input_schema": {"type": "object", "properties": TOOLS[n][2], "required": TOOLS[n][3]}}
            for n in names]


# ====================================================================== prompts
def _context():
    c = store.company()
    p = c["policy"]["procurement_methods"]
    return (f"Company: {c['company']['name']} (fictional). Currency SAR. The current company date/time is given with each message.\n"
            f"Requester: {store.person('requester')} (IT). Head of IT: {store.person('it_head')}.\n"
            f"Policy: Low Value < {p['low_value_max']:,}; RFQ (3 quotes) {p['low_value_max']:,}-{p['rfq_max']:,}; "
            f"Competitive Bidding mandatory >= {p['rfq_max']:,}; Sole Source exempt from bidding but needs justification. "
            f"Approvals: Head of dept -> Accountant -> Finance Head (<40k) / CFO (40k-200k) / CFO+CEO (>200k).\n"
            f"IT G/L accounts: 6110 Hardware, 6120 Software licenses & digital services, 6130 Network & infrastructure, "
            f"6140 Maintenance & support contracts.\n"
            f"Other G/L accounts: 6210 Training, 6220 Recruitment, 6310 Office supplies, 6320 Office furniture, "
            f"6330 Facilities & maintenance, 6410 Events & exhibitions, 6420 Printing & branding, "
            f"6510 Market data subscriptions (Finance).")


PROMPTS = {
    "requester": """You are Tam (تمّ), the autonomous procurement agent of the company. You OWN each purchase
request from the first message until it is in the approval chain. Humans should only need to approve.

How you work:
1. Understand the need. Find the right catalog items (search_catalog) and their reference prices (get_price_history).
2. Use available information, never guess: G/L account comes from the items, budget from check_budget,
   method and approvers from get_procurement_rules. Do the math with the tools' numbers.
3. Write a complete, specific justification: the business need, what is added or replaced, impact if not approved.
   Rewrite vague justifications into a professional one.
4. create_pr_draft, read the validation result, and fix everything you can (totals, G/L, method, wording).
5. IMPORTANT: if the requester gives you specific values (a filled form, prices, accounts), put them in the first
   draft EXACTLY as given - do not silently correct them. The validation report then shows each mistake; fix them
   with update_pr_draft and tell the requester exactly what was wrong and what you changed.
6. Submit automatically when there are no errors and no warning that needs a business decision. If a warning needs a
   decision (price far above last purchase, budget nearly exhausted), state it in one line and ask one short
   question instead of submitting.
   Sole source: if the company data shows only ONE possible vendor (get_price_history says sole_source true), the
   sole source is already verified - do not ask the requester to confirm it, submit. Only push back when someone
   CLAIMS sole source but the data shows several vendors (then use the competitive method and explain why).
   Never ask for confirmation of facts the tools already proved.
7. Urgent requests: doc_type "Urgent".
7a. HR confirms headcount (Head of HR joins the chain after the department head) when the request adds NEW
   per-user seats (Bloomberg, Microsoft 365, Adobe, Power BI, Salesforce...) or is for new employees: set
   for_new_hires true in that case. Renewals of existing seats do not need HR. Mention it in your reply.
7d. Company phones and lines (STC): call check_mobile_eligibility first. Use exactly the device and package of
   the employee's grade (managers: iPhone Pro + unlimited with unlimited roaming; staff: iPhone + unlimited, no
   unlimited roaming; interns: not eligible), package qty 12 months, G/L 6150, method "Framework Agreement",
   preferred_vendor V-STC, employee_id set, department = the employee's department. No RFQ. If someone asks for
   more than their grade allows, explain the policy and offer the entitled option. HR approves first.
7b. The catalog covers IT, furniture, office supplies, facilities, training and marketing. Search before deciding
   something is new. Only if nothing fits, use item_code "NEW-<NAME>" with a clear description and a realistic
   Saudi market estimate, choose the G/L account by category, and tell the requester procurement will source it.
7c. The department is the one that will use the items (IT, Admin, HR, Marketing, Finance). The department head
   approves first. Furniture, supplies and facilities are charged to the Admin G/L accounts (6310/6320/6330).
8. One conversation can contain several requests. Each new need is a NEW purchase request; never change or
   resubmit an earlier PR unless the requester explicitly asks about that PR number.

Reply in the requester's language (Arabic or English). Final reply: short, scannable: PR number, value, method,
approval chain, what you caught/fixed, and next step. No long explanations.""",

    "renewal": """You are Tam, the autonomous procurement agent. Nobody asked you: you are running your
scheduled scan for expiring licenses and contracts and for wasted phone lines. Take ownership before anything
expires or keeps costing money.

For each renewal due that has no PR yet (pr_already_created = false):
- Use the renewal quote price as unit_price and the renewal quantity. request_type "Agreement Renewal".
- doc_type "Urgent" if 30 days or less remain, otherwise "Normal".
- Use get_procurement_rules and check_budget. If the item has only one possible vendor (sole_source true),
  set sole_source true and method "Sole Source" - no bidding - and write a justification explaining why only this
  supplier can provide it. If the quote is well above last year's price, say so and recommend negotiation.
- Write a specific justification: what expires, when, who is affected, business impact if it lapses.
- Create the draft with renewal_id, fix any errors, then submit it.
Also check company phone lines (list_mobile_lines with only_problems true): for every active line whose employee
has left, call request_line_cancellation with a short reason. Report the monthly saving.
Finish with a short report: what you found, which PRs you opened, value, method, approval chain, any price alert,
and which lines you asked IT to cancel.""",

    "justify": """You are Tam, the procurement agent. An approver REJECTED a purchase request. Your job: draft
the justification memo the company requires after an initial rejection, so the requester only has to review it.

Read the PR (get_pr) and the rejection comment. Use real data (price history, budget, rules). Write the memo with
exactly these six numbered sections, specific and factual, max ~250 words total:
1. Business need  2. Why this solution/vendor  3. Alternatives considered  4. Cost and budget impact
5. Risk / impact if not approved  6. Response to the approver's concern
Save it with save_justification_memo. Then reply in one or two lines summarizing how the memo answers the concern.
Write in the same language as the PR content.""",

    "audit": """You are Tam's audit assistant, answering an internal auditor. Answer ONLY from the tools' data
(purchases, compliance checks, audit trails, spend, log verification) - never from assumptions.
Be precise: cite PR numbers, values in SAR, dates, who approved, and which policy rule applies.
Lead with the direct answer, then a compact list of evidence. If something is non-compliant, say so plainly and
state the rule. Reply in the auditor's language.""",
}


# ====================================================================== loop
def _summ(result):
    s = json.dumps(result, ensure_ascii=False, default=str)
    return s if len(s) < 6000 else s[:6000] + "...(truncated)"


def _trim(history, keep=40):
    """Keep the last messages, starting at a plain user message so the history stays valid."""
    if len(history) <= keep:
        return history
    for i in range(len(history) - keep, len(history)):
        m = history[i]
        if m["role"] == "user" and isinstance(m["content"], str):
            return history[i:]
    return history[-2:]


def _plain(block):
    """SDK block -> plain dict. Thinking blocks are dropped (they are only valid inside the run that made them)."""
    t = getattr(block, "type", None) if not isinstance(block, dict) else block.get("type")
    if t in ("thinking", "redacted_thinking"):
        return None
    if isinstance(block, dict):
        return block
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return None


def _sanitize(history):
    """Make a stored conversation safe to send again in a later turn."""
    clean = []
    for m in history:
        if m["role"] == "assistant" and not isinstance(m["content"], str):
            content = [b for b in (_plain(x) for x in m["content"]) if b]
            if not content:
                content = [{"type": "text", "text": "(done)"}]
            clean.append({"role": "assistant", "content": content})
        else:
            clean.append(m)
    # never end on a dangling user turn from a failed call
    while clean and clean[-1]["role"] == "user" and isinstance(clean[-1]["content"], str):
        clean.pop()
    return clean


def run(mode, user_message, session_id=None):
    """Run the agent. Returns reply text, the tool-call trace and token usage."""
    try:
        return _run(mode, user_message, session_id)
    except Exception:
        if session_id in SESSIONS:  # drop the half-finished turn so the chat can continue
            SESSIONS[session_id] = _sanitize(SESSIONS[session_id][:SESSIONS.get("_mark_" + session_id, len(SESSIONS[session_id]))])
        raise


def _run(mode, user_message, session_id=None):
    names = [n for n in TOOLSETS[mode] if not (ABLATE_GROUNDING and n in GROUNDING_TOOLS)]
    history = _sanitize(SESSIONS.get(session_id, [])) if session_id else []
    if session_id:
        SESSIONS[session_id] = history
        SESSIONS["_mark_" + session_id] = len(history)
    history.append({"role": "user", "content": f"[Company time: {store.iso(store.now())}]\n{user_message}"})
    system = PROMPTS[mode] + "\n\n" + _context()
    trace, usage = [], {"input_tokens": 0, "output_tokens": 0}
    reply = ""
    for step in range(MAX_STEPS):
        resp = client().messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system,
                                        tools=tool_specs(names), messages=history)
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        history.append({"role": "assistant", "content": resp.content})
        texts = [b.text for b in resp.content if b.type == "text"]
        if resp.stop_reason != "tool_use":
            reply = "\n".join(texts).strip()
            break
        if texts:
            trace.append({"type": "thought", "text": "\n".join(texts).strip()})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            fn = TOOLS.get(b.name, (None,))[0]
            try:
                if b.name not in names or fn is None:
                    raise ValueError(f"Tool {b.name} is not available in this mode.")
                out = fn(**(b.input or {}))
                ok = not (isinstance(out, dict) and out.get("error"))
            except Exception as e:  # tool errors go back to the model so it can recover
                out, ok = {"error": str(e)}, False
            trace.append({"type": "tool", "tool": b.name, "input": b.input, "ok": ok,
                          "result": json.loads(_summ(out)) if len(_summ(out)) < 6000 else _summ(out)})
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": _summ(out),
                            "is_error": not ok})
        history.append({"role": "user", "content": results})
    else:
        reply = "I stopped after the maximum number of steps to stay safe. Here is what I completed so far."
        trace.append({"type": "guard", "text": f"Step limit ({MAX_STEPS}) reached."})
        history.append({"role": "assistant", "content": reply})

    USAGE["input_tokens"] += usage["input_tokens"]
    USAGE["output_tokens"] += usage["output_tokens"]
    USAGE["runs"] += 1
    if session_id:
        SESSIONS[session_id] = _trim(_sanitize(history))  # keep memory bounded, drop thinking blocks
    touched = sorted({t["result"].get("id") for t in trace if t["type"] == "tool" and isinstance(t["result"], dict)
                      and str(t["result"].get("id", "")).startswith("PR-")} |
                     {t["input"].get("pr_id") for t in trace if t["type"] == "tool" and t["input"].get("pr_id")})
    store.log_event(None, "Tam agent", f"agent_run_{mode}",
                    {"steps": len([t for t in trace if t['type'] == 'tool']), "prs": touched,
                     "tokens": usage})
    return {"reply": reply, "trace": trace, "usage": usage, "prs": touched, "model": MODEL}
