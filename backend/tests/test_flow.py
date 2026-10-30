"""
Offline test of the whole backend: a scripted fake model drives the agent,
so no API credits are used.  Run:  python -m tests.test_flow
"""
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from app import agent, store
from app.main import app


class FakeClient:
    """Replays a scripted list of turns. Each turn: list of ("text", str) / ("tool", name, input)."""
    def __init__(self, turns):
        self.turns = list(turns)
        self.messages = self

    def create(self, **kw):
        turn = self.turns.pop(0)
        blocks = []
        for i, b in enumerate(turn):
            if b[0] == "text":
                blocks.append(NS(type="text", text=b[1]))
            else:
                blocks.append(NS(type="tool_use", name=b[1], input=b[2], id=f"tu_{len(self.turns)}_{i}"))
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return NS(content=blocks, stop_reason=stop, usage=NS(input_tokens=100, output_tokens=50))


def main():
    c = TestClient(app)
    c.post("/api/reset")

    # 1) Requester pastes a filled PR with mistakes -> agent drafts exactly, validation catches, agent fixes, submits
    agent.set_client(FakeClient([
        [("tool", "create_pr_draft", {"title": "Developer laptops", "department": "IT", "gl_account": "6120",
                                      "doc_type": "Urgent", "method": "Low Value", "preferred_vendor": "V-ZAW",
                                      "justification": "need laptops", "estimated_value": 6500,
                                      "lines": [{"item_code": "LAP-DEV-14", "qty": 10, "unit_price": 6500}]})],
        [("text", "Found 4 problems, fixing."),
         ("tool", "update_pr_draft", {"pr_id": "PR-2026-0301", "changes": {
             "gl_account": "6110", "method": "RFQ", "estimated_value": 65000,
             "justification": "Ten developer laptops for the new software team starting in November; the spare pool is empty and contractors cannot be onboarded without devices."}})],
        [("tool", "submit_pr", {"pr_id": "PR-2026-0301"})],
        [("text", "PR-2026-0301 submitted: 65,000 SAR, RFQ, Khalid -> Sara -> Reem (CFO).")],
    ]))
    r = c.post("/api/agent/chat", json={"message": "check my PR"}).json()
    print("CHAT:", r["reply"])
    for t in r["trace"]:
        if t["type"] == "tool":
            v = t["result"].get("validation") if isinstance(t["result"], dict) else None
            print("  tool", t["tool"], "ok" if t["ok"] else "ERR", [i["message"][:70] for i in v] if v else "")
    assert store.get_pr("PR-2026-0301")["status"] == "pending_approval"

    # 2) Approvals with fast-forward (urgent -> reminder at 6h, escalation at 24h)
    print(c.get("/api/inbox/it_head").json()["pending"][0]["id"])
    c.post("/api/prs/PR-2026-0301/decision", json={"role": "it_head", "decision": "approve"})
    c.post("/api/prs/PR-2026-0301/decision", json={"role": "accountant", "decision": "approve"})
    print("FF 8h:", c.post("/api/clock/advance", json={"hours": 8}).json()["follow_up_actions"])
    print("FF 20h:", c.post("/api/clock/advance", json={"hours": 20}).json()["follow_up_actions"])

    # 3) CFO rejects -> agent drafts six-point memo -> resubmit -> approve
    agent.set_client(FakeClient([
        [("tool", "get_pr", {"pr_id": "PR-2026-0301"})],
        [("tool", "save_justification_memo", {"pr_id": "PR-2026-0301", "memo": "1. Business need ...\n6. Response ..."})],
        [("text", "Memo drafted; it shows the price equals last purchase.")],
    ]))
    r = c.post("/api/prs/PR-2026-0301/decision",
               json={"role": "cfo", "decision": "reject", "comment": "Why 32GB laptops? Justify the spec."}).json()
    print("REJECT:", r["status"], "|", r["agent"]["reply"])
    print("RESUBMIT:", c.post("/api/prs/PR-2026-0301/resubmit").json()["status"])
    for role in ["it_head", "accountant", "cfo"]:
        c.post("/api/prs/PR-2026-0301/decision", json={"role": role, "decision": "approve"})
    d = c.get("/api/prs/PR-2026-0301").json()
    print("FINAL:", d["status"], "| docs:", [x["kind"] for x in d["documents"]])
    print("BUDGET 6110:", [b for b in c.get("/api/budget").json() if b["gl"] == "6110"][0])

    # 4) Renewal scan (proactive) - sole source SAP within 90 days
    agent.set_client(FakeClient([
        [("tool", "list_renewals_due", {"within_days": 90})],
        [("tool", "create_pr_draft", {"title": "SAP S/4HANA maintenance renewal 2027", "department": "IT",
                                      "gl_account": "6140", "request_type": "Agreement Renewal", "method": "Sole Source",
                                      "sole_source": True, "preferred_vendor": "V-SAP", "renewal_id": "RN-02",
                                      "justification": "SAP S/4HANA is the company ERP; maintenance can only be provided by SAP as the OEM. Lapse removes security patches and legal-change updates (ZATCA e-invoicing) for finance and procurement. Quote is 23% above last year: negotiation recommended.",
                                      "lines": [{"item_code": "SAP-S4-MAINT", "qty": 1, "unit_price": 228000}]})],
        [("tool", "submit_pr", {"pr_id": "PR-2026-0302"})],
        [("text", "Opened PR-2026-0302 for SAP (sole source, 228,000 SAR, CFO+CEO). Price +23%: negotiate.")],
    ]))
    r = c.post("/api/agent/renewals", json={"within_days": 90}).json()
    print("RENEWAL:", r["reply"])
    pr = store.get_pr("PR-2026-0302")
    print("  ", pr["status"], pr["method"], pr["approval_chain"], [i["message"][:80] for i in pr["validation"]])

    # 5) Audit
    print("FINDINGS:", len(c.get("/api/audit/findings").json()))
    print("VERIFY:", c.get("/api/audit/verify").json()["message"])
    html = c.get("/api/audit/pack").text
    print("PACK bytes:", len(html), "| PR doc bytes:", len(c.get("/api/prs/PR-2026-0301/document").text))
    print("TAMPER:", c.post("/api/demo/tamper").json()["message"])
    print("USAGE:", c.get("/api/state").json()["usage"])
    open("audit_pack_sample.html", "w", encoding="utf-8").write(html)
    open("pr_sample.html", "w", encoding="utf-8").write(c.get("/api/prs/PR-2026-0301/document").text)
    c.post("/api/reset")
    print("ALL OK")


if __name__ == "__main__":
    main()
