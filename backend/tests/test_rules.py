"""
Offline regression tests for Tam's deterministic business rules (no API calls, no cost).
Run from the backend folder:   python -m pytest -q
"""
import pytest

from app import rules, store, workflow as wf


@pytest.fixture(autouse=True)
def fresh_db():
    store.reset()
    yield


def draft(**kw):
    base = {"title": "Test", "department": "IT", "justification":
            "A specific business justification that clearly explains the need and the impact if not approved."}
    return wf.create_draft(base | kw)


def errors(pr):
    return [i["message"] for i in pr["validation"] if i["severity"] == "error"]


def warnings(pr):
    return [i["message"] for i in pr["validation"] if i["severity"] == "warning"]


# ---------------------------------------------------------------- procurement method thresholds
@pytest.mark.parametrize("total,method", [
    (19_999, "Low Value"), (20_000, "RFQ"), (199_999, "RFQ"), (200_000, "Competitive Bidding"),
])
def test_method_thresholds(total, method):
    assert rules.required_method(total)["method"] == method


def test_sole_source_is_exempt_from_bidding():
    m = rules.required_method(500_000, sole_source=True)
    assert m["method"] == "Sole Source" and not m["bidding_required"] and m["justification_required"]


# ---------------------------------------------------------------- approval chains
@pytest.mark.parametrize("total,dept,chain", [
    (9_500, "IT", ["it_head", "accountant", "finance_head"]),
    (39_999, "IT", ["it_head", "accountant", "finance_head"]),
    (40_000, "IT", ["it_head", "accountant", "cfo"]),
    (200_000, "IT", ["it_head", "accountant", "cfo", "ceo"]),
    (5_000, "Admin", ["admin_head", "accountant", "finance_head"]),
    (5_000, "Marketing", ["marketing_head", "accountant", "finance_head"]),
    # regression: the Head of Finance must not sign twice on Finance's own requests
    (21_000, "Finance", ["finance_head", "accountant", "cfo"]),
    (250_000, "Finance", ["finance_head", "accountant", "cfo", "ceo"]),
])
def test_approval_chain(total, dept, chain):
    assert rules.approval_chain(total, dept) == chain


def test_nobody_signs_twice_anywhere():
    for dept in ["IT", "Admin", "HR", "Marketing", "Finance"]:
        for total in [1_000, 30_000, 100_000, 300_000]:
            for new_hires in [False, True]:
                pr = {"lines": [], "extra": {"for_new_hires": new_hires}}
                chain = rules.approval_chain(total, dept, pr)
                assert len(chain) == len(set(chain)), (dept, total, chain)


# ---------------------------------------------------------------- HR confirmation
def test_hr_added_for_new_per_user_seats():
    pr = draft(gl_account="6120", lines=[{"item_code": "LIC-M365-E3", "qty": 20, "unit_price": 1450}])
    assert rules.approval_chain(pr["estimated_value"], "IT", pr)[:2] == ["it_head", "hr_head"]


def test_hr_not_added_for_renewals():
    pr = draft(gl_account="6120", request_type="Agreement Renewal",
               lines=[{"item_code": "LIC-ADOBE-CC", "qty": 12, "unit_price": 3100}])
    assert "hr_head" not in rules.approval_chain(pr["estimated_value"], "IT", pr)


def test_hr_added_for_new_hires_flag():
    pr = draft(gl_account="6110", for_new_hires=True, lines=[{"item_code": "LAP-DEV-14", "qty": 2, "unit_price": 6500}])
    assert "hr_head" in rules.approval_chain(pr["estimated_value"], "IT", pr)


# ---------------------------------------------------------------- validation catches the classic PR mistakes
def test_catches_wrong_total_gl_method_and_vague_text():
    pr = draft(gl_account="6120", method="Low Value", estimated_value=6500, justification="need laptops",
               lines=[{"item_code": "LAP-DEV-14", "qty": 10, "unit_price": 6500}])
    e = " | ".join(errors(pr))
    assert "does not match the sum" in e and "G/L account 6120" in e and "not allowed" in e
    assert any("too vague" in w for w in warnings(pr))
    assert pr["status"] == "needs_fix"


def test_catches_support_without_main_item():
    pr = draft(gl_account="6140", lines=[{"item_code": "NET-CTRL-SUP", "qty": 1, "unit_price": 2600}])
    assert any("NET-CTRL-GW is not in this request" in m for m in errors(pr))


def test_price_anomaly_warning():
    pr = draft(gl_account="6130", lines=[{"item_code": "NET-AP6", "qty": 8, "unit_price": 4600}])
    assert any("above the reference price" in w for w in warnings(pr))


def test_price_typo_warning():
    pr = draft(gl_account="6110", lines=[{"item_code": "LAP-DEV-14", "qty": 2, "unit_price": 650}])
    assert any("possible typo" in w for w in warnings(pr))


def test_false_sole_source_rejected():
    pr = draft(gl_account="6120", sole_source=True, method="Sole Source",
               lines=[{"item_code": "LIC-M365-E3", "qty": 20, "unit_price": 1450}])
    assert any("Sole Source claimed" in m for m in errors(pr))


def test_insufficient_budget_blocks():
    pr = draft(gl_account="6110", lines=[{"item_code": "LAP-DEV-14", "qty": 30, "unit_price": 6500}])
    assert any("Insufficient budget" in m for m in errors(pr))
    assert wf.submit(pr["id"])["submitted"] is False


def test_unknown_item_blocked_but_new_item_allowed():
    bad = draft(gl_account="6110", lines=[{"item_code": "XYZ-123", "qty": 1, "unit_price": 100}])
    assert any("not in the company catalog" in m for m in errors(bad))
    new = draft(gl_account="6420", lines=[{"item_code": "NEW-MIC", "description": "Podcast microphone kit",
                                           "qty": 2, "unit_price": 1200}])
    assert not errors(new) and any("never been purchased" in w for w in warnings(new))


def test_clean_request_has_no_errors():
    pr = draft(gl_account="6110", lines=[{"item_code": "MON-27", "qty": 5, "unit_price": 1250}])
    assert errors(pr) == [] and pr["method"] == "Low Value"


# ---------------------------------------------------------------- mobile policy
def mobile(emp, device, pkg, dept="Marketing", qty=12):
    cat = rules.catalog()
    return draft(department=dept, gl_account="6150", employee_id=emp,
                 lines=[{"item_code": device, "qty": 1, "unit_price": cat[device]["ref_price"]},
                        {"item_code": pkg, "qty": qty, "unit_price": cat[pkg]["ref_price"]}])


def test_manager_phone_entitlement_and_chain():
    pr = mobile("E-1010", "MOB-IPH-PRO", "PKG-MGR")
    assert errors(pr) == [] and pr["method"] == "Framework Agreement" and pr["estimated_value"] == 10_600
    assert rules.approval_chain(pr["estimated_value"], "Marketing", pr) == ["hr_head", "marketing_head", "it_head"]


def test_staff_cannot_get_manager_package():
    pr = mobile("E-1011", "MOB-IPH-PRO", "PKG-MGR", dept="IT")
    assert any("not the staff entitlement" in m for m in errors(pr))


def test_intern_and_leaver_not_eligible_and_no_duplicate_line():
    assert any("not eligible" in m for m in errors(mobile("E-1012", "MOB-IPH", "PKG-STAFF", dept="IT")))
    assert any("left the company" in m for m in errors(mobile("E-1013", "MOB-IPH", "PKG-STAFF")))
    assert any("already has an active line" in m for m in errors(mobile("E-1009", "MOB-IPH", "PKG-STAFF")))


def test_line_activated_after_final_approval():
    pr = mobile("E-1010", "MOB-IPH-PRO", "PKG-MGR")
    wf.submit(pr["id"])
    for role in ["hr_head", "marketing_head", "it_head"]:
        wf.decide(pr["id"], role, "approve")
    assert any(l["employee_id"] == "E-1010" and l["status"] == "active" for l in store.mobile_lines())


# ---------------------------------------------------------------- workflow, editing, audit
def test_full_approval_commits_budget():
    before = rules.check_budget("6110", 0)["remaining_before"]
    pr = draft(gl_account="6110", lines=[{"item_code": "MON-27", "qty": 4, "unit_price": 1250}])
    wf.submit(pr["id"])
    for role in ["it_head", "accountant", "finance_head"]:
        wf.decide(pr["id"], role, "approve")
    assert store.get_pr(pr["id"])["status"] == "sent_to_procurement"
    assert rules.check_budget("6110", 0)["remaining_before"] == before - 5_000


def test_wrong_approver_cannot_sign():
    pr = draft(gl_account="6110", lines=[{"item_code": "MON-27", "qty": 1, "unit_price": 1250}])
    wf.submit(pr["id"])
    with pytest.raises(ValueError):
        wf.decide(pr["id"], "cfo", "approve")


def test_text_locked_after_first_signature():
    pr = draft(gl_account="6110", lines=[{"item_code": "MON-27", "qty": 1, "unit_price": 1250}])
    wf.submit(pr["id"])
    wf.decide(pr["id"], "it_head", "approve")
    with pytest.raises(ValueError):
        wf.edit_text(pr["id"], "requester", justification="changed after signing " * 4)


def test_rejection_keeps_history_round():
    pr = draft(gl_account="6110", lines=[{"item_code": "MON-27", "qty": 1, "unit_price": 1250}])
    wf.submit(pr["id"])
    wf.decide(pr["id"], "it_head", "reject", "why?")
    wf.resubmit(pr["id"])
    p = store.get_pr(pr["id"])
    assert p["approval_round"] == 2 and any(a["status"] == "rejected" for a in p["approval_history"])


def test_reminder_then_escalation_for_urgent():
    pr = draft(gl_account="6110", doc_type="Urgent", lines=[{"item_code": "MON-27", "qty": 1, "unit_price": 1250}])
    wf.submit(pr["id"])
    store.advance_clock(7)
    assert [a["type"] for a in wf.run_follow_ups()] == ["reminder"]
    store.advance_clock(20)
    assert [a["type"] for a in wf.run_follow_ups()] == ["escalated"]


def test_audit_findings_on_seeded_history():
    kinds = {(f["pr_id"], f["type"]) for f in rules.audit_findings()}
    assert ("PR-2026-0204", "wrong_method") in kinds          # 212k recorded as RFQ, needed bidding
    assert ("PR-2026-0204", "approval_gap") in kinds          # CEO missing
    assert ("PR-2026-0148", "insufficient_quotes") in kinds
    assert ("PR-2026-0166", "missing_documents") in kinds     # no invoice
    assert sum(1 for k in kinds if k[1] == "line_after_exit") == 2


def test_audit_log_detects_tampering():
    assert store.verify_chain()["ok"]
    with store.conn() as c:
        c.execute("UPDATE events SET actor='someone else' WHERE id=2")
    assert not store.verify_chain()["ok"]
