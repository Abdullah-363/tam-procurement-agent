"""
Deterministic business rules. The LLM never decides these - it calls them.

- required_method():   which procurement method the value + sourcing demands
- approval_chain():    who must sign, in order
- validate_pr():       every check that used to send a signed PR back for re-signing
- audit_findings():    compliance checks across all purchases (for the auditor)
"""
from . import store

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def catalog():
    return {i["code"]: i for i in store.company()["catalog"]}


def vendors():
    return {v["id"]: v for v in store.company()["vendors"]}


def policy():
    return store.company()["policy"]


def fmt(x):
    return f"{x:,.0f} SAR"


# ------------------------------------------------------------------ method
def required_method(total, sole_source=False):
    p = policy()["procurement_methods"]
    if sole_source:
        return {"method": "Sole Source", "quotes_required": 1, "bidding_required": False,
                "justification_required": True,
                "reason": "Only one supplier can provide this item; sole source is exempt from bidding."}
    if total < p["low_value_max"]:
        return {"method": "Low Value", "quotes_required": 1, "bidding_required": False,
                "justification_required": False,
                "reason": f"Value below {fmt(p['low_value_max'])}: direct purchase with one quote."}
    if total < p["rfq_max"]:
        return {"method": "RFQ", "quotes_required": p["rfq_min_quotes"], "bidding_required": False,
                "justification_required": False,
                "reason": f"Value between {fmt(p['low_value_max'])} and {fmt(p['rfq_max'])}: "
                          f"at least {p['rfq_min_quotes']} quotations must be compared."}
    return {"method": "Competitive Bidding", "quotes_required": p["rfq_min_quotes"], "bidding_required": True,
            "justification_required": False,
            "reason": f"Value of {fmt(p['rfq_max'])} or more: formal competitive bidding is mandatory."}


FRAMEWORK_METHOD = "Framework Agreement"


def is_mobile_request(pr):
    cat = catalog()
    return any(cat.get(l.get("item_code"), {}).get("category") == "telecom" for l in (pr or {}).get("lines") or [])


def framework_of(pr):
    """Framework agreement id if EVERY line is covered by one, else None."""
    cat = catalog()
    lines = (pr or {}).get("lines") or []
    fws = {cat.get(l.get("item_code"), {}).get("framework") for l in lines}
    return fws.pop() if lines and len(fws) == 1 and None not in fws else None


def method_for_pr(pr):
    """Required method for a whole PR (framework call-off, sole source, or by value)."""
    fw = framework_of(pr)
    if fw:
        return {"method": FRAMEWORK_METHOD, "quotes_required": 0, "bidding_required": False,
                "justification_required": False, "framework": fw,
                "reason": f"Covered by framework agreement {fw}: call-off order, no RFQ or bidding needed."}
    cat = catalog()
    codes = [l.get("item_code") for l in (pr.get("lines") or [])]
    sole = bool(pr.get("sole_source")) and not any(len(vendors_for_item(cat[c])) > 1 for c in codes if c in cat)
    if pr.get("source") == "history":
        sole = bool(pr.get("sole_source"))
    return required_method(pr.get("estimated_value") or lines_total(pr.get("lines") or []), sole_source=sole)


# ------------------------------------------------------------------ approvals
def hr_confirmation_reason(pr):
    """Why HR must confirm headcount for this PR, or None."""
    if not pr:
        return None
    if is_mobile_request(pr):
        return "Company phone/line: HR confirms the employee is eligible and the package matches their grade."
    cat = catalog()
    seats = [(l, cat[l["item_code"]]) for l in (pr.get("lines") or [])
             if l.get("item_code") in cat and cat[l["item_code"]].get("per_user")]
    if seats and pr.get("request_type") != "Agreement Renewal":
        n = int(sum(float(l.get("qty", 0)) for l, _ in seats))
        names = ", ".join(sorted({i["name"].split(",")[0] for _, i in seats}))
        return f"{n} new per-user seat(s) ({names}): HR must confirm the headcount."
    if (pr.get("extra") or {}).get("for_new_hires"):
        return "Purchase is for new employees: HR must confirm the hires."
    return None


def approval_chain(total, department="IT", pr=None):
    pol = policy()
    head = pol["department_heads"].get(department, "it_head")
    if pr and is_mobile_request(pr):
        # Mobile: HR (eligibility) -> employee's department head -> Head of IT (fulfils under the STC agreement)
        chain = []
        for r in ["hr_head", head, "it_head"]:
            if r not in chain:
                chain.append(r)
        if total >= pol["procurement_methods"]["low_value_max"]:   # bulk orders also go through finance
            chain.append("accountant")
            for tier in pol["approval_tiers"]:
                if tier["max"] is None or total < tier["max"]:
                    chain.extend(tier["final"])
                    break
        return chain
    chain = []
    for role in pol["approval_prefix"]:
        if role == "department_head":
            chain.append(head)
            if hr_confirmation_reason(pr) and head != "hr_head":
                chain.append("hr_head")
        else:
            chain.append(role)
    for tier in pol["approval_tiers"]:
        if tier["max"] is None or total < tier["max"]:
            for role in tier["final"]:
                # nobody signs twice: if the final approver already signed as department head, go one level up
                while role in chain:
                    role = ESCALATE_IF_DUPLICATE.get(role, role)
                    if role == ESCALATE_IF_DUPLICATE.get(role):
                        break
                if role not in chain:
                    chain.append(role)
            break
    return chain


ESCALATE_IF_DUPLICATE = {"finance_head": "cfo", "cfo": "ceo", "ceo": "ceo"}


def chain_with_names(chain):
    return [{"role": r, "name": store.person(r), "title": store.company()["people"][r]["title"]} for r in chain]


# ------------------------------------------------------------------ budget
def check_budget(gl, amount, exclude_pr=None):
    rows = {r["gl"]: r for r in store.budget_rows()}
    r = rows.get(str(gl))
    if not r:
        return {"ok": False, "message": f"G/L account {gl} does not exist.", "gl": gl}
    after = r["remaining"] - amount
    return {"ok": after >= 0, "gl": r["gl"], "account": r["name"], "department": r["department"],
            "annual": r["annual"], "remaining_before": r["remaining"], "amount": amount,
            "remaining_after": after,
            "message": (f"{r['name']} ({r['gl']}): {fmt(r['remaining'])} available, "
                        f"{fmt(after)} left after this request.") if after >= 0 else
                       (f"Insufficient budget in {r['name']} ({r['gl']}): {fmt(r['remaining'])} available, "
                        f"request needs {fmt(amount)} (short by {fmt(-after)}).")}


# ------------------------------------------------------------------ helpers
def lines_total(lines):
    return round(sum(float(l.get("qty", 0)) * float(l.get("unit_price", 0)) for l in lines), 2)


def vendors_for_item(item):
    if item.get("sole_source_vendor"):
        return [item["sole_source_vendor"]]
    return [v["id"] for v in store.company()["vendors"] if item["category"] in v["categories"]]


def price_check(item_code, unit_price):
    item = catalog().get(item_code)
    if not item:
        return None
    pol = policy()
    ref = item["ref_price"]
    diff_pct = (unit_price - ref) / ref * 100
    status = "ok"
    if diff_pct > pol["price_anomaly_threshold_pct"]:
        status = "high"
    elif unit_price < ref * (1 - pol["price_too_low_threshold_pct"] / 100):
        status = "too_low"
    return {"item_code": item_code, "unit_price": unit_price, "reference_price": ref,
            "diff_pct": round(diff_pct, 1), "status": status}


# ------------------------------------------------------------------ validation
# Ablation switch for evaluation only (evals/run.py --ablation no_validation): turns the rule layer off.
ABLATE_VALIDATION = False


def validate_pr(pr):
    """Return a list of issues. Errors block submission; warnings need a decision."""
    if ABLATE_VALIDATION:
        return []
    issues = []

    def add(sev, field, msg, fix=None):
        issues.append({"severity": sev, "field": field, "message": msg, "suggestion": fix})

    cat = catalog()
    vend = vendors()
    pol = policy()
    lines = pr.get("lines") or []

    # 1. Required fields
    for f, label in [("title", "Title"), ("department", "Proponent department"), ("gl_account", "G/L account"),
                     ("cost_center", "Cost center"), ("justification", "Justification")]:
        if not pr.get(f):
            add("error", f, f"{label} is missing.")
    if not lines:
        add("error", "lines", "No items listed.")

    # 2. Line items: known item, quantity, price sanity
    codes = [l.get("item_code") for l in lines]
    for i, l in enumerate(lines, start=1):
        item = cat.get(l.get("item_code"))
        if not item:
            code = str(l.get("item_code", ""))
            if code.startswith("NEW"):
                # Never bought before: allowed, but procurement must source it and the price is an estimate.
                if not (l.get("description") or "").strip() or float(l.get("unit_price", 0)) <= 0:
                    add("error", f"lines[{i}]", f"Item {i} ({code}) is new: it needs a clear description and an estimated unit price.")
                else:
                    add("warning", f"lines[{i}]",
                        f"Item {i} ({l.get('description')}) has never been purchased: the unit price is an estimate and "
                        f"procurement will source vendors and add it to the catalog.")
                if float(l.get("qty", 0)) <= 0:
                    add("error", f"lines[{i}]", f"Item {i} has an invalid quantity ({l.get('qty')}).")
                continue
            add("error", f"lines[{i}]", f"Item {i} ('{code}') is not in the company catalog.",
                "Use the catalog code, or NEW-<name> with a description and estimated price for an item never bought before.")
            continue
        qty = float(l.get("qty", 0))
        if qty <= 0:
            add("error", f"lines[{i}]", f"Item {i} ({item['code']}) has an invalid quantity ({l.get('qty')}).")
        pc = price_check(item["code"], float(l.get("unit_price", 0)))
        if pc and pc["status"] == "high":
            sole = bool(item.get("sole_source_vendor"))
            add("warning", f"lines[{i}]",
                f"Item {i} ({item['code']}): unit price {fmt(pc['unit_price'])} is {pc['diff_pct']}% above the "
                f"reference price {fmt(pc['reference_price'])} (last purchase).",
                "Negotiate with the vendor using last year's price as the anchor." if sole else
                "Recommend competitive quotes/bidding before approval; finance will question this price.")
        elif pc and pc["status"] == "too_low":
            add("warning", f"lines[{i}]",
                f"Item {i} ({item['code']}): unit price {fmt(pc['unit_price'])} is far below the reference "
                f"{fmt(pc['reference_price'])}; possible typo (missing digit?).",
                "Confirm the unit price with the quotation.")
        # Dependencies: support/license lines must point to an item in the same PR
        if item.get("requires") and item["requires"] not in codes:
            add("error", f"lines[{i}]",
                f"Item {i} ({item['code']}) is a support/license item for {item['requires']}, "
                f"but {item['requires']} is not in this request.",
                f"Add {item['requires']} or correct the part number it refers to.")

    # 3. Totals
    total = lines_total(lines)
    est = float(pr.get("estimated_value") or 0)
    if lines and abs(total - est) > max(1, 0.005 * total):
        add("error", "estimated_value",
            f"Estimated value {fmt(est)} does not match the sum of the items {fmt(total)}.",
            f"Set estimated value to {fmt(total)}.")

    # 4. G/L account vs items
    gls = {cat[c]["gl"] for c in codes if c in cat}
    budget_gls = {r["gl"] for r in store.budget_rows()}
    if pr.get("gl_account") and pr["gl_account"] not in budget_gls:
        add("error", "gl_account", f"G/L account {pr['gl_account']} does not exist in the budget.")
    elif pr.get("gl_account") and gls and pr["gl_account"] not in gls:
        expected = ", ".join(sorted(gls))
        add("error", "gl_account",
            f"G/L account {pr['gl_account']} does not match the items in this request (expected {expected}).",
            f"Change the G/L account to {sorted(gls)[0]}." if len(gls) == 1 else
            "Split the request by G/L account, or charge it to the main account with finance's agreement.")
    elif len(gls) > 1:
        add("warning", "gl_account",
            f"Items belong to several G/L accounts ({', '.join(sorted(gls))}); the PR is charged to {pr.get('gl_account')}.",
            "Confirm with finance or split the request.")

    # 5. Cost center
    if pr.get("cost_center") and pr.get("department") and pr["cost_center"] != pr["department"]:
        add("warning", "cost_center",
            f"Cost center '{pr['cost_center']}' differs from the proponent department '{pr['department']}'.")

    # 6. Procurement method
    sole = bool(pr.get("sole_source"))
    if sole:
        items = [cat[c] for c in codes if c in cat]
        multi = [i for i in items if len(vendors_for_item(i)) > 1]
        if multi:
            names = ", ".join(i["code"] for i in multi)
            n = max(len(vendors_for_item(i)) for i in multi)
            add("error", "method",
                f"Sole Source claimed, but {n} registered vendors can supply {names}.",
                "Use RFQ / competitive quotes, or document why only one supplier is acceptable (single source).")
    req = method_for_pr(pr | {"estimated_value": total})
    if pr.get("method") and pr["method"] != req["method"]:
        add("error", "method",
            f"Procurement method '{pr['method']}' is not allowed for {fmt(total)}. Required: {req['method']}.",
            req["reason"])
    if req["justification_required"] and len(pr.get("justification") or "") < 150:
        add("warning", "justification", "Sole-source purchases need a full justification (why only this supplier).",
            "The agent can draft the justification memo.")

    # 6b. Mobile phones and lines: eligibility by grade (mobile policy)
    if is_mobile_request(pr):
        _validate_mobile(pr, add)

    # 7. Vendor
    pv = pr.get("preferred_vendor")
    if pv:
        v = vend.get(pv) or next((x for x in vend.values() if x["name"].lower() == str(pv).lower()), None)
        if not v:
            add("warning", "preferred_vendor", f"Preferred vendor '{pv}' is not a registered vendor.")
        else:
            needed = {cat[c]["category"] for c in codes if c in cat
                      and not (cat[c].get("sole_source_vendor") and cat[c]["sole_source_vendor"] == v["id"])}
            missing = needed - set(v["categories"])
            if missing:
                add("warning", "preferred_vendor",
                    f"{v['name']} is not registered for: {', '.join(sorted(missing))}.")

    # 8. Justification quality (length heuristic; the agent also rewrites vague text)
    j = (pr.get("justification") or "").strip()
    if j and len(j) < pol["min_justification_chars"]:
        add("warning", "justification",
            f"Justification is too vague ({len(j)} characters): approvers usually send these back.",
            "State the business need, what is being replaced or added, and the impact if not approved.")

    # 9. Budget
    if pr.get("gl_account") and total > 0:
        b = check_budget(pr["gl_account"], total)
        if not b["ok"]:
            add("error", "budget", b["message"], "Reduce the scope, split across fiscal periods, or request a budget transfer.")

    issues.sort(key=lambda x: SEVERITY_ORDER[x["severity"]])
    return issues


def _validate_mobile(pr, add):
    mp = policy()["mobile_policy"]
    emp_ref = (pr.get("extra") or {}).get("employee_id")
    emp = store.find_employee(emp_ref) if emp_ref else None
    if not emp_ref:
        add("error", "employee", "Mobile requests must name the employee who will receive the phone/line.")
        return
    if not emp:
        add("error", "employee", f"'{emp_ref}' is not in the HR directory.",
            "HR must add the employee before a line can be requested.")
        return
    if emp["status"] == "left":
        add("error", "employee", f"{emp['name']} left the company on {emp['left_date']}; no line can be issued.")
        return
    ent = mp.get(emp["grade"])
    if not ent:
        add("error", "employee", f"{emp['name']} ({emp['title']}, grade {emp['grade']}) is not eligible for a "
                                 f"company phone under the mobile policy.")
        return
    codes = {l["item_code"]: l for l in pr.get("lines") or []}
    cat = catalog()
    for code in codes:
        item = cat.get(code, {})
        if item.get("category") != "telecom":
            continue
        is_pkg = bool(item.get("recurring"))
        allowed = ent["package"] if is_pkg else ent["device"]
        if code != allowed:
            add("error", "lines", f"{item['name'].split(',')[0]} is not the {emp['grade']} entitlement. "
                                  f"{emp['name']} ({emp['title']}) gets: {ent['label']}.",
                f"Use {allowed}.")
        if is_pkg and float(codes[code].get("qty", 0)) != mp["commitment_months"]:
            add("warning", "lines", f"Package quantity should be {mp['commitment_months']} months "
                                    f"(annual commitment under the STC agreement).")
    if any(cat.get(c, {}).get("recurring") for c in codes):
        active = [l for l in store.mobile_lines() if l["employee_id"] == emp["id"] and l["status"] == "active"]
        if active:
            add("error", "employee", f"{emp['name']} already has an active line ({active[0]['number']}).",
                "Request a device replacement instead of a new line.")
    if emp["status"] == "joining":
        add("info", "employee", f"{emp['name']} joins on {emp['start_date']}: line will be ready for day one.")


def summarize_issues(issues):
    e = sum(1 for i in issues if i["severity"] == "error")
    w = sum(1 for i in issues if i["severity"] == "warning")
    return {"errors": e, "warnings": w, "can_submit": e == 0}


# ------------------------------------------------------------------ audit
REQUIRED_DOCS = ["pr_form", "quote", "invoice"]


def audit_findings():
    """Compliance checks across every PR in the system (history + live)."""
    findings = []
    for pr in store.list_prs():
        if pr["status"] not in ("approved", "sent_to_procurement"):
            continue
        full = store.get_pr(pr["id"])
        total = pr["estimated_value"]
        sole = bool(pr["sole_source"])
        req = method_for_pr(full)

        def add(kind, sev, msg):
            findings.append({"pr_id": pr["id"], "title": pr["title"], "value": total, "type": kind,
                             "severity": sev, "finding": msg})

        completed = pr["source"] == "history"  # purchase fully closed (quotes + invoice expected)
        if pr["method"] != req["method"]:
            add("wrong_method", "high", f"Recorded as '{pr['method']}' but {fmt(total)} requires {req['method']}.")
        if completed and pr["quotes_count"] < req["quotes_required"]:
            add("insufficient_quotes", "high",
                f"{pr['quotes_count']} quotation(s) on file; {req['quotes_required']} required for {req['method']}.")
        expected = approval_chain(total, pr["department"], full)
        signed = [a["role"] for a in full["approvals"] if a["status"] == "approved"]
        missing = [r for r in expected if r not in signed]
        extra = [r for r in signed if r not in expected]
        if missing:
            add("approval_gap", "high",
                "Missing required approval(s): " + ", ".join(f"{store.person(r)} ({r})" for r in missing) +
                (f"; approved instead by {', '.join(extra)}" if extra else "") + ".")
        kinds = [d["kind"] for d in full["documents"]]
        missing_docs = [d for d in (REQUIRED_DOCS if completed else ["pr_form"]) if d not in kinds]
        if missing_docs:
            add("missing_documents", "medium", "Missing document(s): " + ", ".join(missing_docs) + ".")
        if sole and req["method"] == "Sole Source" and "justification" not in kinds \
                and not full.get("extra", {}).get("justification_memo"):
            add("missing_justification", "medium", "Sole-source purchase without a justification memo.")
    findings.extend(line_findings())
    return findings


def line_findings():
    """Mobile lines still billing for people who have left."""
    from datetime import datetime
    out = []
    now = store.now()
    for l in store.mobile_lines():
        e = l["employee"]
        if l["status"] == "cancelled" or e.get("status") != "left":
            continue
        months = max(1, round((now - datetime.strptime(e["left_date"], "%Y-%m-%d")).days / 30))
        wasted = months * l["monthly"]
        note = (f" Cancellation requested by Tam on {l['cancel_requested_at']}."
                if l["status"] == "cancellation_requested" else "")
        out.append({"pr_id": f"Line {l['number']}", "title": f"{e['name']} ({e['title']})", "value": wasted,
                    "type": "line_after_exit", "severity": "medium" if note else "high",
                    "finding": f"STC line still active {months} month(s) after {e['name']} left on {e['left_date']}: "
                               f"about {fmt(wasted)} billed for nobody.{note}"})
    return out
