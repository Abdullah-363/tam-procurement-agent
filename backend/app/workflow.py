r"""
PR lifecycle: draft -> validated -> pending_approval -> approved -> sent_to_procurement
                                     \-> rejected (agent drafts justification) -> resubmitted

Deterministic code: the agent calls these functions through tools, and the
approver UI calls decide() directly. Everything is written to the audit log.
"""
from datetime import datetime, timedelta

from . import rules, store

AGENT = "Tam agent"

STATUS_LABELS = {
    "draft": "Draft", "needs_fix": "Needs correction", "pending_approval": "Awaiting approval",
    "rejected": "Rejected", "approved": "Approved", "sent_to_procurement": "Sent to procurement",
}

EDITABLE = ["title", "department", "doc_type", "request_type", "method", "gl_account", "cost_center",
            "preferred_vendor", "justification", "lines", "estimated_value", "sole_source"]


def _now():
    return store.iso(store.now())


def _normalize_lines(lines):
    cat = rules.catalog()
    out = []
    for l in lines or []:
        code = str(l.get("item_code", "")).strip().upper()
        item = cat.get(code, {})
        out.append({"item_code": code,
                    "description": l.get("description") or item.get("name", ""),
                    "qty": float(l.get("qty", 0)),
                    "unit_price": float(l.get("unit_price", item.get("ref_price", 0)))})
    return out


def create_draft(fields: dict, requester="requester", source="requester", actor=None):
    pr_id = store.next_pr_id()
    lines = _normalize_lines(fields.get("lines"))
    total = rules.lines_total(lines)
    pr = {
        "id": pr_id, "title": fields.get("title", ""), "department": fields.get("department", "IT"),
        "requester": requester, "status": "draft",
        "doc_type": fields.get("doc_type", "Normal"),
        "request_type": fields.get("request_type", "New Procurement"),
        "method": fields.get("method"),
        "gl_account": str(fields.get("gl_account", "")), "cost_center": fields.get("cost_center", fields.get("department", "IT")),
        "preferred_vendor": fields.get("preferred_vendor", ""),
        "justification": fields.get("justification", ""),
        "lines": lines,
        "estimated_value": float(fields["estimated_value"]) if fields.get("estimated_value") is not None else total,
        "source": source, "quotes_count": 0, "sole_source": 1 if fields.get("sole_source") else 0,
        "approval_chain": [], "validation": [],
        "extra": (fields.get("extra") or {}) | ({"for_new_hires": True} if fields.get("for_new_hires") else {})
                 | ({"employee_id": fields["employee_id"]} if fields.get("employee_id") else {}),
        "created_at": _now(), "updated_at": _now(),
    }
    if not pr["method"]:
        pr["method"] = rules.method_for_pr(pr)["method"]
    pr["validation"] = rules.validate_pr(pr)
    pr["status"] = "draft" if rules.summarize_issues(pr["validation"])["can_submit"] else "needs_fix"
    store.save_pr(pr)
    store.log_event(pr_id, actor or AGENT, "pr_drafted",
                    {"value": pr["estimated_value"], "source": source, "title": pr["title"]})
    store.log_event(pr_id, AGENT, "pr_validated", rules.summarize_issues(pr["validation"]) |
                    {"issues": [i["message"] for i in pr["validation"]]})
    return pr


def update_draft(pr_id, changes: dict, actor=None):
    pr = store.get_pr(pr_id)
    if not pr:
        raise ValueError(f"{pr_id} not found")
    if pr["status"] not in ("draft", "needs_fix", "rejected"):
        raise ValueError(f"{pr_id} is {pr['status']} and can no longer be edited.")
    if "for_new_hires" in changes:
        pr["extra"] = (pr.get("extra") or {}) | {"for_new_hires": bool(changes["for_new_hires"])}
    if changes.get("employee_id"):
        pr["extra"] = (pr.get("extra") or {}) | {"employee_id": changes["employee_id"]}
    before = {k: pr.get(k) for k in changes if k in EDITABLE}
    for k, v in changes.items():
        if k not in EDITABLE:
            continue
        if k == "lines":
            v = _normalize_lines(v)
        if k == "sole_source":
            v = 1 if v else 0
        if k in ("gl_account",):
            v = str(v)
        pr[k] = v
    if "lines" in changes and "estimated_value" not in changes:
        pr["estimated_value"] = rules.lines_total(pr["lines"])
    pr["validation"] = rules.validate_pr(pr)
    if pr["status"] != "rejected":
        pr["status"] = "draft" if rules.summarize_issues(pr["validation"])["can_submit"] else "needs_fix"
    pr["updated_at"] = _now()
    store.save_pr({k: v for k, v in pr.items() if k not in ("approvals", "documents")})
    store.log_event(pr_id, actor or AGENT, "pr_corrected",
                    {"fields": list(before.keys()), "before": {k: str(v)[:120] for k, v in before.items()}})
    return pr


def submit(pr_id, actor=None):
    pr = store.get_pr(pr_id)
    if not pr:
        raise ValueError(f"{pr_id} not found")
    pr["validation"] = rules.validate_pr(pr)
    summary = rules.summarize_issues(pr["validation"])
    if not summary["can_submit"]:
        store.log_event(pr_id, AGENT, "submission_blocked", {"errors": [i["message"] for i in pr["validation"]
                                                                          if i["severity"] == "error"]})
        return {"submitted": False, "reason": "Validation errors must be fixed first.",
                "errors": [i for i in pr["validation"] if i["severity"] == "error"]}
    chain = rules.approval_chain(pr["estimated_value"], pr["department"], pr)
    hr_reason = rules.hr_confirmation_reason(pr)
    pr["approval_chain"] = chain
    pr["status"] = "pending_approval"
    pr["updated_at"] = _now()
    store.save_pr({k: v for k, v in pr.items() if k not in ("approvals", "documents")})
    with store.conn() as c:
        # Earlier rounds stay on record (audit); steps never reached are closed.
        c.execute("UPDATE approvals SET status='not_reached' WHERE pr_id=? AND status IN ('pending','waiting')", (pr_id,))
        rnd = (c.execute("SELECT MAX(round) m FROM approvals WHERE pr_id=?", (pr_id,)).fetchone()["m"] or 0) + 1
        for i, role in enumerate(chain):
            c.execute("INSERT INTO approvals (pr_id, step, role, person, status, requested_at, round) VALUES (?,?,?,?,?,?,?)",
                      (pr_id, i, role, store.person(role), "pending" if i == 0 else "waiting",
                       _now() if i == 0 else None, rnd))
    if not any(d["kind"] == "pr_form" for d in pr["documents"]):
        store.add_document(pr_id, "pr_form", f"Purchase Request {pr_id}")
    store.log_event(pr_id, actor or AGENT, "pr_submitted",
                    {"value": pr["estimated_value"], "method": pr["method"],
                     "approval_chain": [f"{store.person(r)} ({r})" for r in chain],
                     "warnings": [i["message"] for i in pr["validation"] if i["severity"] == "warning"]})
    if hr_reason:
        store.log_event(pr_id, AGENT, "hr_confirmation_added", {"reason": hr_reason})
    _request_approval(pr, chain[0])
    return {"submitted": True, "hr_confirmation": hr_reason, "approval_chain": rules.chain_with_names(chain), "status": "pending_approval"}


def _request_approval(pr, role):
    urgent = pr["doc_type"] == "Urgent"
    hr_reason = rules.hr_confirmation_reason(pr) if role == "hr_head" else None
    what = "Headcount confirmation needed" if hr_reason else "Approval needed"
    subj = f"{'[URGENT] ' if urgent else ''}{what}: {pr['id']} - {pr['title']} ({rules.fmt(pr['estimated_value'])})"
    body = (f"Dear {store.person(role)},\n\n{pr['id']} needs your approval.\n"
            f"Item: {pr['title']}\nValue: {rules.fmt(pr['estimated_value'])} | Method: {pr['method']} | "
            f"G/L: {pr['gl_account']}\nAll checks passed (budget, totals, method, account).\n"
            f"{('Why you: ' + hr_reason + chr(10)) if hr_reason else ''}\n"
            f"Approve or reject with one click in your Tam inbox.\n\n- Tam")
    store.notify(role, pr["id"], "approval_request", subj, body)
    store.log_event(pr["id"], AGENT, "approval_requested", {"to": store.person(role), "role": role, "urgent": urgent})


def decide(pr_id, role, decision, comment="", actor_name=None):
    """An approver approves or rejects the current step."""
    pr = store.get_pr(pr_id)
    if not pr or pr["status"] != "pending_approval":
        raise ValueError(f"{pr_id} is not awaiting approval.")
    current = next((a for a in pr["approvals"] if a["status"] == "pending"), None)
    if not current:
        raise ValueError("No pending approval step.")
    if role != current["role"]:
        raise ValueError(f"This step is waiting for {current['person']} ({current['role']}), not {role}.")
    who = actor_name or store.person(role)
    with store.conn() as c:
        c.execute("UPDATE approvals SET status=?, decided_at=?, decided_by=?, comment=? WHERE id=?",
                  ("approved" if decision == "approve" else "rejected", _now(), who, comment, current["id"]))
    store.log_event(pr_id, who, "approved" if decision == "approve" else "rejected",
                    {"role": role, "step": current["step"], "comment": comment})

    if decision != "approve":
        _set_status(pr_id, "rejected")
        store.notify("requester", pr_id, "rejected", f"{pr_id} rejected by {who}",
                     f"Reason: {comment or '(none given)'}\nTam is preparing a justification draft for your review.")
        return {"status": "rejected", "by": who, "comment": comment}

    nxt = next((a for a in pr["approvals"] if a["step"] == current["step"] + 1), None)
    if nxt:
        with store.conn() as c:
            c.execute("UPDATE approvals SET status='pending', requested_at=? WHERE id=?", (_now(), nxt["id"]))
        _request_approval(pr, nxt["role"])
        return {"status": "pending_approval", "next": nxt["person"]}

    # Final approval -> hand over to procurement
    _set_status(pr_id, "approved")
    store.log_event(pr_id, AGENT, "fully_approved", {"value": pr["estimated_value"],
                                                      "budget_committed_to": pr["gl_account"]})
    handoff(pr_id)
    return {"status": "sent_to_procurement"}


def handoff(pr_id):
    pr = store.get_pr(pr_id)
    req = rules.method_for_pr(pr)
    if rules.is_mobile_request(pr):
        _activate_line(pr)
    store.add_document(pr_id, "approved_pr", f"Approved Purchase Request {pr_id} (all signatures)")
    body = (f"Dear {store.person('procurement_head')},\n\n{pr_id} - {pr['title']} is fully approved.\n"
            f"Value: {rules.fmt(pr['estimated_value'])}\nRequired method: {req['method']} - {req['reason']}\n"
            f"Preferred vendor: {pr.get('preferred_vendor') or 'none'}\n"
            f"CC: {store.person('it_head')} (Head of IT)\n\nThe approved PR document and the full approval "
            f"trail are attached.\n\n- Tam")
    store.notify("procurement_head", pr_id, "handoff", f"Approved PR {pr_id} for processing", body)
    _set_status(pr_id, "sent_to_procurement")
    store.log_event(pr_id, AGENT, "sent_to_procurement",
                    {"to": store.person("procurement_head"), "cc": [store.person("it_head")],
                     "required_method": req["method"]})


def _activate_line(pr):
    """Mobile request approved: order the line under the STC framework and record who holds it."""
    cat = rules.catalog()
    emp = store.find_employee((pr.get("extra") or {}).get("employee_id"))
    pkg = next((l for l in pr["lines"] if cat.get(l["item_code"], {}).get("recurring")), None)
    dev = next((l for l in pr["lines"] if cat.get(l["item_code"], {}).get("category") == "telecom"
                and not cat[l["item_code"]].get("recurring")), None)
    number = None
    if pkg and emp:
        number = store.next_line_number()
        with store.conn() as c:
            c.execute("INSERT INTO mobile_lines (number, employee_id, package, device, monthly, status, activated_at, pr_id) "
                      "VALUES (?,?,?,?,?,?,?,?)", (number, emp["id"], pkg["item_code"], dev["item_code"] if dev else None,
                                                  pkg["unit_price"], "active", _now(), pr["id"]))
    who = emp["name"] if emp else "the employee"
    body = (f"Dear {store.person('it_head')},\n\n{pr['id']} is approved. Call-off order under STC framework "
            f"agreement FA-STC-2026:\n- Employee: {who}" + (f" ({emp['title']}, starts {emp['start_date']})" if emp and emp.get('start_date') else "") +
            (f"\n- New line: {number} ({cat[pkg['item_code']]['name']})" if number else "") +
            (f"\n- Device: {cat[dev['item_code']]['name']}" if dev else "") +
            "\n\nPlease hand over the device and SIM and confirm in Tam.\n\n- Tam")
    store.notify("it_head", pr["id"], "handoff", f"Activate mobile line for {who} ({pr['id']})", body)
    store.log_event(pr["id"], AGENT, "line_ordered", {"employee": who, "number": number,
                                                      "framework": "FA-STC-2026"})


def request_line_cancellation(number, reason="", actor=None):
    lines = {l["number"]: l for l in store.mobile_lines()}
    l = lines.get(number) or next((x for k, x in lines.items() if k.replace(" ", "") == str(number).replace(" ", "")), None)
    if not l:
        raise ValueError(f"Line {number} not found")
    if l["status"] != "active":
        return {"number": l["number"], "status": l["status"], "note": "No action: line is not active."}
    with store.conn() as c:
        c.execute("UPDATE mobile_lines SET status='cancellation_requested', cancel_requested_at=? WHERE number=?",
                  (_now(), l["number"]))
    e = l["employee"]
    store.notify("it_head", None, "cancellation", f"Cancel STC line {l['number']} ({e.get('name')})",
                 f"Dear {store.person('it_head')},\n\nPlease cancel STC line {l['number']} assigned to {e.get('name')}, "
                 f"who left on {e.get('left_date')}. It still costs {rules.fmt(l['monthly'])} per month.\n"
                 f"Reason: {reason or 'employee left the company'}\nPlease also recover the device.\n\n- Tam")
    store.log_event(None, actor or AGENT, "line_cancellation_requested",
                    {"number": l["number"], "employee": e.get("name"), "monthly_saving": l["monthly"]})
    return {"number": l["number"], "status": "cancellation_requested", "employee": e.get("name"),
            "monthly_saving": l["monthly"]}


def departed_active_lines():
    return [l for l in store.mobile_lines() if l["status"] == "active" and l["employee"].get("status") == "left"]


def _set_status(pr_id, status):
    with store.conn() as c:
        c.execute("UPDATE prs SET status=?, updated_at=? WHERE id=?", (status, _now(), pr_id))


def save_justification(pr_id, memo: str, actor=None):
    pr = store.get_pr(pr_id)
    extra = pr.get("extra") or {}
    extra["justification_memo"] = memo
    extra["justification_status"] = "awaiting_requester_review"
    with store.conn() as c:
        import json
        c.execute("UPDATE prs SET extra=?, updated_at=? WHERE id=?", (json.dumps(extra, ensure_ascii=False), _now(), pr_id))
    store.add_document(pr_id, "justification", "Justification memo (draft)")
    store.log_event(pr_id, actor or AGENT, "justification_drafted", {"chars": len(memo)})
    store.notify("requester", pr_id, "review_needed", f"Review justification for {pr_id}",
                 "A justification memo was drafted. Review it, then resubmit with one click.")
    return {"saved": True}


def resubmit(pr_id, actor=None):
    """After rejection: requester approved the memo -> PR goes back into the chain."""
    pr = store.get_pr(pr_id)
    extra = pr.get("extra") or {}
    # The memo stays a separate attachment; it is not copied into the justification.
    if extra.get("justification_memo"):
        extra["justification_status"] = "approved_by_requester"
        pr["extra"] = extra
    pr["status"] = "draft"
    store.save_pr({k: v for k, v in pr.items() if k not in ("approvals", "documents")})
    store.log_event(pr_id, actor or store.person("requester"), "resubmitted_with_justification", {})
    return submit(pr_id)


def edit_text(pr_id, role, justification=None, memo=None):
    """Human edit of the justification or memo. Who may edit depends on where the PR is:
    - requester: while it is a draft, after a rejection, or before anyone has approved it
    - a department head: while it is waiting for that head's signature
    After the first approval the text is locked: what was signed must not change silently."""
    pr = store.get_pr(pr_id)
    if not pr:
        raise ValueError(f"{pr_id} not found")
    approved_any = any(a["status"] == "approved" for a in pr["approvals"]) and pr["status"] == "pending_approval"
    cur = next((a for a in pr["approvals"] if a["status"] == "pending"), None)
    if role == "requester":
        allowed = pr["status"] in ("draft", "needs_fix", "rejected") or (
            pr["status"] == "pending_approval" and not approved_any)
    elif role in rules.policy()["department_heads"].values() and role != "finance_head":
        # a department head may edit while the request waits for their own signature
        allowed = pr["status"] == "pending_approval" and cur is not None and cur["role"] == role
    else:
        allowed = False
    if not allowed:
        raise ValueError("Locked: this request already has approvals, so its text can't change. "
                         "Reject it to send it back for edits.")
    who = store.person(role)
    changes = {}
    if justification is not None and justification.strip() != (pr["justification"] or "").strip():
        changes["justification"] = {"before": pr["justification"], "after": justification.strip()}
        with store.conn() as c:
            c.execute("UPDATE prs SET justification=?, updated_at=? WHERE id=?", (justification.strip(), _now(), pr_id))
    if memo is not None:
        extra = pr.get("extra") or {}
        if memo.strip() != (extra.get("justification_memo") or "").strip():
            changes["memo"] = {"before": extra.get("justification_memo"), "after": memo.strip()}
            extra["justification_memo"] = memo.strip()
            extra["memo_edited_by"] = who
            import json
            with store.conn() as c:
                c.execute("UPDATE prs SET extra=?, updated_at=? WHERE id=?", (json.dumps(extra, ensure_ascii=False), _now(), pr_id))
    if changes:
        # keep the re-validation in sync (vague-justification warning etc.)
        fresh = store.get_pr(pr_id)
        fresh["validation"] = rules.validate_pr(fresh)
        with store.conn() as c:
            import json
            c.execute("UPDATE prs SET validation=? WHERE id=?", (json.dumps(fresh["validation"], ensure_ascii=False), pr_id))
        store.log_event(pr_id, who, "text_edited", {"role": role, "fields": list(changes.keys()),
                                                    "before": {k: (v["before"] or "")[:300] for k, v in changes.items()}})
    return {"edited": list(changes.keys()), "by": who}


# ------------------------------------------------------------------ follow-ups
def run_follow_ups():
    """Called after the clock moves. Sends reminders and escalates overdue approvals."""
    pol = rules.policy()
    actions = []
    now = store.now()
    with store.conn() as c:
        pending = c.execute(
            "SELECT a.*, p.doc_type, p.title, p.estimated_value FROM approvals a JOIN prs p ON p.id=a.pr_id "
            "WHERE a.status='pending' AND p.status='pending_approval'").fetchall()
    for a in pending:
        sla = pol["follow_up_hours"].get(a["doc_type"], pol["follow_up_hours"]["Normal"])
        waited = (now - datetime.strptime(a["requested_at"], "%Y-%m-%d %H:%M")).total_seconds() / 3600
        if waited >= sla["escalate_after"] and not a["escalated"]:
            target = pol["escalation_target"].get(a["role"], "cfo")
            store.notify(target, a["pr_id"], "escalation",
                         f"Escalation: {a['pr_id']} waiting {waited:.0f}h on {a['person']}",
                         f"{a['pr_id']} ({a['title']}, {rules.fmt(a['estimated_value'])}) has waited "
                         f"{waited:.0f} hours for {a['person']}. Please follow up or delegate.")
            store.notify(a["role"], a["pr_id"], "reminder", f"Final reminder: {a['pr_id']} escalated",
                         f"This request has been escalated to {store.person(target)}.")
            with store.conn() as c:
                c.execute("UPDATE approvals SET escalated=1 WHERE id=?", (a["id"],))
            store.log_event(a["pr_id"], AGENT, "escalated",
                            {"waiting_on": a["person"], "hours": round(waited), "escalated_to": store.person(target)})
            actions.append({"type": "escalated", "pr_id": a["pr_id"], "waiting_on": a["person"],
                            "to": store.person(target), "hours": round(waited)})
        elif waited >= sla["remind_after"] * (a["reminders"] + 1) and waited < sla["escalate_after"]:
            store.notify(a["role"], a["pr_id"], "reminder",
                         f"Reminder: {a['pr_id']} awaiting your approval ({waited:.0f}h)",
                         f"Dear {a['person']}, {a['pr_id']} - {a['title']} has been waiting {waited:.0f} hours. "
                         f"One click in your inbox approves or rejects it.")
            with store.conn() as c:
                c.execute("UPDATE approvals SET reminders=reminders+1 WHERE id=?", (a["id"],))
            store.log_event(a["pr_id"], AGENT, "reminder_sent", {"to": a["person"], "hours": round(waited)})
            actions.append({"type": "reminder", "pr_id": a["pr_id"], "to": a["person"], "hours": round(waited)})
    return actions


# ------------------------------------------------------------------ renewals
def renewals_due(within_days=45):
    start = datetime.fromisoformat(_clock_base())
    out = []
    existing = {(pr.get("extra") or {}).get("renewal_id") for pr in store.list_prs()}
    for r in store.company()["renewals"]:
        expiry = start + timedelta(days=r["days_to_expiry"])
        days_left = (expiry - store.now()).days
        if days_left <= within_days:
            out.append(r | {"expiry_date": expiry.strftime("%Y-%m-%d"), "days_left": days_left,
                            "pr_already_created": r["id"] in existing})
    return out


def _clock_base():
    with store.conn() as c:
        return c.execute("SELECT value FROM meta WHERE key='clock_base'").fetchone()["value"]
