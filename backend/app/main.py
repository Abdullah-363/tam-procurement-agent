"""
Tam API.  Run from the backend folder:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs to try every endpoint.
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import agent, documents, rules, store, workflow as wf

@asynccontextmanager
async def lifespan(_app):
    _startup()
    yield


app = FastAPI(title="Tam - autonomous procurement agent", version="0.2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _startup():
    if not store.DB_PATH.exists():
        store.reset()
        return
    with store.conn() as c:  # database from an older version -> rebuild it
        cols = [r["name"] for r in c.execute("PRAGMA table_info(approvals)").fetchall()]
        has_lines = c.execute("SELECT 1 FROM sqlite_master WHERE name='mobile_lines'").fetchone()
    if "round" not in cols or not has_lines:
        store.reset()


# ------------------------------------------------------------------ models
class ChatIn(BaseModel):
    message: str
    session_id: str = "requester-1"


class DecisionIn(BaseModel):
    role: str
    decision: str            # "approve" | "reject"
    comment: str = ""


class ClockIn(BaseModel):
    hours: float


class AskIn(BaseModel):
    question: str
    session_id: str = "auditor-1"


class EditIn(BaseModel):
    role: str                       # "requester" | "it_head"
    justification: Optional[str] = None
    memo: Optional[str] = None


class RenewalIn(BaseModel):
    within_days: int = 30


def _agent_error(e):
    msg = str(e)
    if "authentication" in msg.lower() or "api-key" in msg.lower() or "api_key" in msg.lower():
        msg = "Claude API key missing or invalid. Check ANTHROPIC_API_KEY in backend/.env"
    raise HTTPException(status_code=502, detail=f"Agent error: {msg}")


# ------------------------------------------------------------------ system
@app.post("/api/reset")
def reset():
    store.reset()
    agent.SESSIONS.clear()
    return {"ok": True, "now": store.iso(store.now())}


@app.get("/api/state")
def state():
    prs = [p for p in store.list_prs() if p["source"] != "history"]
    return {"company": store.company()["company"], "now": store.iso(store.now()),
            "model": agent.MODEL, "usage": agent.USAGE,
            "counts": {s: sum(1 for p in prs if p["status"] == s) for s in wf.STATUS_LABELS},
            "people": store.company()["people"]}


@app.post("/api/clock/advance")
def advance(body: ClockIn):
    store.advance_clock(body.hours)
    store.log_event(None, "system", "clock_advanced", {"hours": body.hours})
    actions = wf.run_follow_ups()
    return {"now": store.iso(store.now()), "follow_up_actions": actions}


@app.get("/api/mobile/lines")
def lines():
    return store.mobile_lines()


@app.get("/api/budget")
def budget():
    return store.budget_rows()


@app.get("/api/catalog")
def catalog():
    return store.company()["catalog"]


# ------------------------------------------------------------------ agent
@app.post("/api/agent/chat")
def chat(body: ChatIn):
    try:
        return agent.run("requester", body.message, body.session_id)
    except Exception as e:
        _agent_error(e)


@app.post("/api/agent/renewals")
def renewals(body: RenewalIn):
    due = wf.renewals_due(body.within_days)
    wasted = wf.departed_active_lines()
    if not any(not r["pr_already_created"] for r in due) and not wasted:
        return {"reply": f"Scan complete: no new renewals due within {body.within_days} days and no phone lines "
                         f"to cancel.", "trace": [], "due": due, "prs": []}
    try:
        out = agent.run("renewal", f"Scheduled scan: check renewals due within {body.within_days} days and phone "
                                   f"lines of employees who left; take ownership of anything that needs action.")
        out["due"] = due
        return out
    except Exception as e:
        _agent_error(e)


@app.post("/api/audit/ask")
def audit_ask(body: AskIn):
    try:
        return agent.run("audit", body.question, body.session_id)
    except Exception as e:
        _agent_error(e)


# ------------------------------------------------------------------ PRs
@app.get("/api/prs")
def prs(include_history: bool = False):
    out = []
    for p in store.list_prs():
        if p["source"] == "history" and not include_history:
            continue
        full = store.get_pr(p["id"])
        cur = next((a for a in full["approvals"] if a["status"] == "pending"), None)
        out.append({"id": p["id"], "title": p["title"], "status": p["status"],
                    "status_label": wf.STATUS_LABELS.get(p["status"], p["status"]),
                    "value": p["estimated_value"], "method": p["method"], "doc_type": p["doc_type"],
                    "source": p["source"], "created_at": p["created_at"],
                    "waiting_on": cur["person"] if cur else None,
                    "summary": rules.summarize_issues(p["validation"] or [])})
    return out


@app.get("/api/prs/{pr_id}")
def pr_detail(pr_id: str):
    pr = store.get_pr(pr_id)
    if not pr:
        raise HTTPException(404, f"{pr_id} not found")
    pr["events"] = store.events_for(pr_id)
    pr["approval_chain_named"] = rules.chain_with_names(pr["approval_chain"] or [])
    pr["required_method"] = rules.method_for_pr(pr)
    pr["budget"] = rules.check_budget(pr["gl_account"], 0) if pr["gl_account"] else None
    return pr


@app.post("/api/prs/{pr_id}/decision")
def decision(pr_id: str, body: DecisionIn):
    try:
        result = wf.decide(pr_id, body.role, body.decision, body.comment)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if result["status"] == "rejected":
        # The agent takes ownership of the rejection: drafts the justification memo.
        try:
            out = agent.run("justify", f"{pr_id} was rejected by {result['by']}. Comment: "
                                       f"\"{body.comment or 'no comment'}\". Draft the justification memo.")
            result["agent"] = {"reply": out["reply"], "trace": out["trace"]}
        except Exception as e:
            result["agent"] = {"reply": f"Could not draft memo automatically: {e}", "trace": []}
    return result


@app.patch("/api/prs/{pr_id}/text")
def edit_text(pr_id: str, body: EditIn):
    try:
        return wf.edit_text(pr_id, body.role, body.justification, body.memo)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/prs/{pr_id}/resubmit")
def resubmit(pr_id: str):
    try:
        return wf.resubmit(pr_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/inbox/{role}")
def inbox(role: str):
    with store.conn() as c:
        pend = c.execute("SELECT pr_id FROM approvals WHERE role=? AND status='pending'", (role,)).fetchall()
        notes = [dict(n) for n in c.execute(
            "SELECT * FROM notifications WHERE to_role=? ORDER BY id DESC LIMIT 30", (role,)).fetchall()]
    items = []
    for r in pend:
        pr = store.get_pr(r["pr_id"])
        if pr and pr["status"] == "pending_approval":
            items.append({"id": pr["id"], "title": pr["title"], "value": pr["estimated_value"],
                          "method": pr["method"], "doc_type": pr["doc_type"], "gl_account": pr["gl_account"],
                          "justification": pr["justification"], "lines": pr["lines"],
                          "warnings": [i["message"] for i in pr["validation"] if i["severity"] == "warning"],
                          "why_you": rules.hr_confirmation_reason(pr) if role == "hr_head" else None,
                          "requested_at": next(a["requested_at"] for a in pr["approvals"] if a["status"] == "pending")})
    return {"role": role, "person": store.company()["people"].get(role, {}), "pending": items, "notifications": notes}


@app.get("/api/notifications")
def notifications(limit: int = 50):
    with store.conn() as c:
        return [dict(n) for n in c.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


@app.get("/api/events")
def events(pr_id: Optional[str] = None, limit: int = 200):
    return store.events_for(pr_id)[-limit:]


# ------------------------------------------------------------------ audit + documents
@app.get("/api/audit/findings")
def findings():
    return rules.audit_findings()


@app.get("/api/audit/verify")
def verify():
    return store.verify_chain()


@app.get("/api/prs/{pr_id}/document", response_class=HTMLResponse)
def pr_document(pr_id: str):
    return documents.pr_form(pr_id)


@app.get("/api/audit/pack", response_class=HTMLResponse)
def pack(pr_id: Optional[str] = None):
    store.log_event(pr_id, "auditor", "audit_pack_generated", {"scope": pr_id or "all"})
    return documents.audit_pack(pr_id)


@app.post("/api/demo/tamper")
def tamper():
    """Demo only: secretly edit one historical log entry, to show verify_chain() catching it."""
    with store.conn() as c:
        c.execute("UPDATE events SET details=? WHERE id=(SELECT id FROM events WHERE action='approved' LIMIT 1)",
                  ('{"role": "cfo", "note": "edited after the fact"}',))
    return store.verify_chain()
