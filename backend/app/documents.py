"""
Printable documents (open in the browser, Ctrl+P -> Save as PDF):
- PR form, same structure as the paper form, with digital approval records
- Audit pack: everything about one PR or all purchases in one file
"""
import html
from . import rules, store

CSS = """
<style>
 body{font-family:Segoe UI,Arial,sans-serif;color:#1b2b28;margin:32px;max-width:900px}
 h1{font-size:20px;margin:0} h2{font-size:15px;margin:22px 0 8px;color:#1f4e46;border-bottom:2px solid #1f4e46;padding-bottom:4px}
 table{border-collapse:collapse;width:100%;font-size:12.5px;margin-bottom:8px}
 td,th{border:1px solid #9bb3ad;padding:6px 8px;vertical-align:top;text-align:left}
 th{background:#e7efed;width:28%} .head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
 .muted{color:#5b6f6a;font-size:12px} .ok{color:#17803d;font-weight:600} .bad{color:#b42318;font-weight:600}
 .warn{color:#a15c07;font-weight:600} .hash{font-family:Consolas,monospace;font-size:10.5px;color:#5b6f6a}
 .box{border:1px solid #9bb3ad;padding:10px;white-space:pre-wrap;font-size:12.5px}
 @media print{body{margin:12mm}}
</style>"""

DOC_LABELS = {"pr_form": "PR form", "approved_pr": "Approved PR", "quote": "Quotation", "invoice": "Invoice",
              "tech_eval": "Technical evaluation", "justification": "Justification memo",
              "delivery_note": "Delivery note"}


STATUS_TEXT = {"approved": "Approved", "rejected": "Rejected", "pending": "Awaiting decision",
               "waiting": "Not yet reached", "not_reached": "Not reached (returned earlier)"}


def _employee_row(pr):
    emp = store.find_employee((pr.get("extra") or {}).get("employee_id"))
    if not emp:
        return ""
    return (f"<tr><th>Employee (phone/line)</th><td>{e(emp['name'])} · {e(emp['title'])} · grade {e(emp['grade'])}"
            f"</td></tr>")


def _round(a, multi):
    return f"<div class='muted'>Round {a['round']}</div>" if multi else ""


def _title(role):
    return store.company()["people"].get(role, {}).get("title", role)


def e(x):
    return html.escape(str(x if x is not None else ""))


def _check(v, label):
    return f"{'☒' if v else '☐'} {label}"


def pr_form(pr_id):
    pr = store.get_pr(pr_id)
    if not pr:
        return f"<p>{e(pr_id)} not found</p>"
    c = store.company()
    vend = rules.vendors()
    vname = vend.get(pr["preferred_vendor"], {}).get("name", pr["preferred_vendor"])
    gl_name = next((r["name"] for r in store.budget_rows() if r["gl"] == pr["gl_account"]), "")
    lines = "".join(f"<tr><td>{i}</td><td>{e(l['item_code'])}</td><td>{e(l['description'])}</td>"
                    f"<td>{l['qty']:g}</td><td>{l['unit_price']:,.2f}</td><td>{l['qty'] * l['unit_price']:,.2f}</td></tr>"
                    for i, l in enumerate(pr["lines"], 1))
    history = pr.get("approval_history") or pr["approvals"]
    multi = len({a["round"] for a in history}) > 1
    appr = "".join(
        f"<tr><td>{e(_title(a['role']))}{_round(a, multi)}</td>"
        f"<td>{e(a['person'])}</td>"
        f"<td class='{'ok' if a['status'] == 'approved' else 'bad' if a['status'] == 'rejected' else 'muted'}'>"
        f"{e(STATUS_TEXT.get(a['status'], a['status']))}</td><td>{e(a['decided_at'] or '')}</td><td>{e(a['comment'] or '')}</td></tr>"
        for a in history)
    memo = (pr.get("extra") or {}).get("justification_memo")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(pr_id)}</title>{CSS}</head><body>
<div class="head"><div><h1>Procurement Request Form</h1><div class="muted">{e(c['company']['name'])} · {e(c['company']['name_ar'])}</div></div>
<div style="text-align:right"><b>{e(pr_id)}</b><div class="muted">Created {e(pr['created_at'])} · Status: {e(pr['status'].replace('_', ' '))}</div></div></div>
<table>
<tr><th>Nature of requisition</th><td>{e(pr['title'])}</td></tr>
<tr><th>Document type</th><td>{_check(pr['doc_type'] == 'Normal', 'Normal')} &nbsp; {_check(pr['doc_type'] == 'Urgent', 'Urgent')} &nbsp; {_check(pr['doc_type'] == 'Budgetary', 'Budgetary')} &nbsp; {_check(pr['doc_type'] == 'Outline Agreement', 'Outline Agreement')}</td></tr>
<tr><th>Type of request</th><td>{_check(pr['request_type'] == 'New Procurement', 'New Procurement')} &nbsp; {_check(pr['request_type'] == 'Agreement Renewal', 'Agreement Renewal')} &nbsp; {_check(pr['request_type'] == 'Scope Change', 'Scope Change')}</td></tr>
<tr><th>Procurement method</th><td>{_check(pr['method'] == 'Low Value', 'Low Value')} &nbsp; {_check(pr['method'] == 'RFQ', 'RFQ (3 quotes)')} &nbsp; {_check(pr['method'] == 'Competitive Bidding', 'Competitive Bidding')} &nbsp; {_check(pr['method'] == 'Sole Source', 'Sole Source')} &nbsp; {_check(pr['method'] == 'Framework Agreement', 'Framework Agreement')}</td></tr>
<tr><th>Estimated value</th><td><b>{pr['estimated_value']:,.2f} SAR</b></td></tr>
<tr><th>Proponent</th><td>{e(store.person(pr['requester']))} · {e(pr['department'])}</td></tr>
<tr><th>G/L account</th><td>{e(pr['gl_account'])} – {e(gl_name)}</td></tr>
<tr><th>Cost center</th><td>{e(pr['cost_center'])}</td></tr>
<tr><th>Preferred vendor</th><td>{e(vname)}</td></tr>
{_employee_row(pr)}
</table>
<h2>Description / scope of work</h2>
<table><tr><th style="width:4%">#</th><th style="width:16%">Item code</th><th>Description</th><th style="width:7%">Qty</th><th style="width:13%">Unit (SAR)</th><th style="width:14%">Total (SAR)</th></tr>{lines}</table>
<h2>Justification</h2><div class="box">{e(pr['justification'])}</div>
{f'<h2>Justification memo (after initial rejection)</h2><div class="box">{e(memo)}</div>' if memo else ''}
<h2>Digital approvals</h2>
<table><tr><th>Role</th><th>Name</th><th>Decision</th><th>Date / time</th><th>Comment</th></tr>{appr or '<tr><td colspan=5 class=muted>Not submitted yet</td></tr>'}</table>
<p class="muted">Approvals are recorded in Tam's tamper-evident audit log; no wet signatures or scanning required.</p>
</body></html>"""


def audit_pack(pr_id=None):
    """One document with everything an auditor needs, for one PR or the whole year."""
    prs = [store.get_pr(pr_id)] if pr_id else [store.get_pr(p["id"]) for p in store.list_prs()
                                                 if p["status"] in ("approved", "sent_to_procurement")]
    prs = [p for p in prs if p]
    findings = rules.audit_findings()
    if pr_id:
        findings = [f for f in findings if f["pr_id"] == pr_id]
    chain = store.verify_chain()
    total = sum(p["estimated_value"] for p in prs)
    fin_rows = "".join(f"<tr><td>{e(f['pr_id'])}</td><td>{e(f['title'])}</td><td>{f['value']:,.0f}</td>"
                       f"<td class='{'bad' if f['severity'] == 'high' else 'warn'}'>{e(f['severity'].upper())}</td>"
                       f"<td>{e(f['finding'])}</td></tr>" for f in findings)
    sections = []
    for p in prs:
        req = rules.method_for_pr(p)
        ev = store.events_for(p["id"])
        ev_rows = "".join(f"<tr><td>{e(x['ts'])}</td><td>{e(x['actor'])}</td><td>{e(x['action'].replace('_', ' '))}</td>"
                          f"<td class='hash'>{e(x['hash'][:12])}</td></tr>" for x in ev)
        docs = ", ".join(DOC_LABELS.get(d["kind"], d["kind"]) for d in p["documents"]) or "none"
        appr = "; ".join(f"{a['person']} ({_title(a['role'])}) {STATUS_TEXT.get(a['status'], a['status']).lower()} "
                         f"{a['decided_at'] or ''}" for a in (p.get("approval_history") or p["approvals"]))
        sections.append(f"""<h2>{e(p['id'])} — {e(p['title'])}</h2>
<table><tr><th>Value</th><td>{p['estimated_value']:,.2f} SAR</td></tr>
<tr><th>G/L account</th><td>{e(p['gl_account'])}</td></tr>
<tr><th>Method recorded / required</th><td>{e(p['method'])} / {e(req['method'])}</td></tr>
<tr><th>Quotations on file</th><td>{p['quotes_count']} (required: {req['quotes_required']})</td></tr>
<tr><th>Approvals</th><td>{e(appr)}</td></tr>
<tr><th>Documents on file</th><td>{e(docs)}</td></tr></table>
<table><tr><th style="width:18%">Time</th><th style="width:24%">Actor</th><th>Action</th><th style="width:16%">Log hash</th></tr>{ev_rows}</table>""")
    title = f"Audit pack — {pr_id}" if pr_id else "Audit pack — all approved purchases FY2026"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(title)}</title>{CSS}</head><body>
<div class="head"><div><h1>{e(title)}</h1><div class="muted">{e(store.company()['company']['name'])} · generated {e(store.iso(store.now()))} by Tam</div></div></div>
<table><tr><th>Purchases covered</th><td>{len(prs)}</td></tr>
<tr><th>Total value</th><td>{total:,.2f} SAR</td></tr>
<tr><th>Compliance findings</th><td class="{'bad' if findings else 'ok'}">{len(findings)}</td></tr>
<tr><th>Audit log integrity</th><td class="{'ok' if chain['ok'] else 'bad'}">{e(chain['message'])}</td></tr></table>
<h2>Compliance findings</h2>
<table><tr><th style="width:13%">PR</th><th>Title</th><th style="width:10%">SAR</th><th style="width:9%">Severity</th><th>Finding</th></tr>{fin_rows or '<tr><td colspan=5 class=ok>No findings</td></tr>'}</table>
{''.join(sections)}
</body></html>"""
