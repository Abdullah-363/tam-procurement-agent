"""
Tam evaluation runner.

Each case starts from a fresh company database, sends the case's message(s) to the real agent, then scores
the OUTCOME in the database (method, G/L account, value, approval chain, submitted or not, lines cancelled...)
instead of judging the wording. Results are saved as JSON + Markdown and appended to results/history.csv,
so every iteration leaves evidence.

Examples (run from the backend folder):
    python -m evals.run --set dev                       # the set we iterate on
    python -m evals.run --set heldout                   # run only for final reporting
    python -m evals.run --set dev --ablation no_validation
    python -m evals.run --set dev --ablation no_grounding
    python -m evals.run --set dev --only D03,D04 --repeat 3
    python -m evals.run --set dev --model claude-sonnet-5-5
"""
import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from app import agent, rules, store

HERE = Path(__file__).parent
RESULTS = HERE / "results"
TOL = 0.01  # values must match within 1%


# ------------------------------------------------------------------ helpers
def deep_merge(base, override):
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


def arabic_ratio(text):
    ar = len(re.findall(r"[؀-ۿ]", text or ""))
    lat = len(re.findall(r"[A-Za-z]", text or ""))
    return ar / max(1, ar + lat)


def close(a, b):
    return a is not None and abs(float(a) - float(b)) <= max(1.0, TOL * float(b))


def live_prs():
    return [store.get_pr(p["id"]) for p in sorted(store.list_prs(), key=lambda p: p["id"]) if p["source"] != "history"]


def is_submitted(pr):
    return pr["status"] in ("pending_approval", "approved", "sent_to_procurement")


def true_errors(pr):
    """Re-validate with the real rules (even during an ablation) to count submissions that break policy."""
    saved = rules.ABLATE_VALIDATION
    rules.ABLATE_VALIDATION = False
    try:
        return [i["message"] for i in rules.validate_pr(pr) if i["severity"] == "error"]
    finally:
        rules.ABLATE_VALIDATION = saved


def pr_checks(pr, exp, prefix=""):
    """Field checks against one PR."""
    out = []

    def chk(name, ok, detail):
        out.append({"check": prefix + name, "ok": bool(ok), "detail": detail})

    chain = pr.get("approval_chain") or rules.approval_chain(pr["estimated_value"], pr["department"], pr)
    codes = {l["item_code"]: l["qty"] for l in pr["lines"]}
    if "method" in exp:
        chk("method", pr["method"] == exp["method"], f"{pr['method']} (expected {exp['method']})")
    if "gl" in exp:
        chk("gl", pr["gl_account"] == exp["gl"], f"{pr['gl_account']} (expected {exp['gl']})")
    if "value" in exp:
        chk("value", close(pr["estimated_value"], exp["value"]), f"{pr['estimated_value']:,.0f} (expected {exp['value']:,})")
    if "value_min" in exp or "value_max" in exp:
        lo, hi = exp.get("value_min", 0), exp.get("value_max", 1e12)
        chk("value_range", lo <= pr["estimated_value"] <= hi, f"{pr['estimated_value']:,.0f} (expected {lo:,}-{hi:,})")
    if "doc_type" in exp:
        chk("doc_type", pr["doc_type"] == exp["doc_type"], f"{pr['doc_type']} (expected {exp['doc_type']})")
    if "chain" in exp:
        chk("chain", chain == exp["chain"], f"{chain} (expected {exp['chain']})")
    if "chain_includes" in exp:
        chk("chain_includes", all(r in chain for r in exp["chain_includes"]), f"{chain} must include {exp['chain_includes']}")
    if "chain_excludes" in exp:
        chk("chain_excludes", not any(r in chain for r in exp["chain_excludes"]), f"{chain} must exclude {exp['chain_excludes']}")
    if "lines" in exp:
        ok = all(c in codes and float(codes[c]) == float(q) for c, q in exp["lines"].items())
        chk("lines", ok, f"{codes} (expected {exp['lines']})")
    if "lines_include" in exp:
        chk("lines_include", all(c in codes for c in exp["lines_include"]), f"{list(codes)} must include {exp['lines_include']}")
    if "lines_exclude" in exp:
        chk("lines_exclude", not any(c in codes for c in exp["lines_exclude"]), f"{list(codes)} must exclude {exp['lines_exclude']}")
    if exp.get("new_item"):
        chk("new_item", any(c.startswith("NEW") for c in codes), f"{list(codes)} should contain a NEW- item")
    return out


def score(case, replies, traces):
    exp = case["expect"]
    prs = live_prs()
    submitted = [p for p in prs if is_submitted(p)]
    main = submitted[-1] if submitted else (prs[-1] if prs else None)
    reply = "\n".join(replies)
    checks = []

    def chk(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if "submitted" in exp:
        chk("submitted", bool(submitted) == exp["submitted"], f"submitted={bool(submitted)} (expected {exp['submitted']})")
    if "max_prs" in exp:
        chk("max_prs", len(prs) <= exp["max_prs"], f"{len(prs)} PR(s) created (max {exp['max_prs']})")
    if "submitted_count" in exp:
        chk("submitted_count", len(submitted) == exp["submitted_count"], f"{len(submitted)} submitted (expected {exp['submitted_count']})")
    if "values" in exp:
        got = sorted(p["estimated_value"] for p in submitted)
        ok = len(got) == len(exp["values"]) and all(close(a, b) for a, b in zip(got, sorted(exp["values"])))
        chk("values", ok, f"{got} (expected {sorted(exp['values'])})")
    if "not_method" in exp:
        chk("not_method", all(p["method"] != exp["not_method"] for p in submitted), f"no submitted PR may use {exp['not_method']}")
    if "no_status" in exp:
        chk("no_status", not any(p["status"] in exp["no_status"] for p in prs), f"no PR may reach {exp['no_status']} by itself")

    field_keys = {"method", "gl", "value", "value_min", "value_max", "doc_type", "chain", "chain_includes",
                  "chain_excludes", "lines", "lines_include", "lines_exclude", "new_item"}
    direct = {k: v for k, v in exp.items() if k in field_keys}
    if direct:
        if main:
            checks += pr_checks(main, direct)
        else:
            chk("pr_exists", False, "no PR was created")
    if "if_submitted" in exp and submitted:
        checks += pr_checks(submitted[-1], exp["if_submitted"], prefix="if_submitted.")

    if "first_draft_errors_min" in exp:
        first = next((t for tr in traces for t in tr if t["type"] == "tool" and t["tool"] == "create_pr_draft"
                      and isinstance(t["result"], dict)), None)
        n = (first or {}).get("result", {}).get("summary", {}).get("errors", 0) if first else 0
        chk("first_draft_errors_min", n >= exp["first_draft_errors_min"], f"{n} error(s) caught on the first draft")
    if "reply_any" in exp:
        chk("reply_any", any(k.lower() in reply.lower() for k in exp["reply_any"]), f"reply mentions one of {exp['reply_any']}")
    if "reply_all" in exp:
        miss = [k for k in exp["reply_all"] if k.lower() not in reply.lower()]
        chk("reply_all", not miss, f"missing {miss}" if miss else "all mentioned")
    if "reply_all_any" in exp:
        miss = [g for g in exp["reply_all_any"] if not any(k.lower() in reply.lower() for k in g)]
        chk("reply_all_any", not miss, f"missing {miss}" if miss else "all groups mentioned")
    if exp.get("reply_arabic"):
        r = arabic_ratio(reply)
        chk("reply_arabic", r > 0.5, f"Arabic share of letters {r:.0%}")
    if "renewal_ids" in exp:
        got = {(p.get("extra") or {}).get("renewal_id") for p in submitted}
        chk("renewal_ids", all(r in got for r in exp["renewal_ids"]), f"renewal PRs submitted: {sorted(x for x in got if x)}")
    if "lines_cancel_requested" in exp:
        req = {l["number"] for l in store.mobile_lines() if l["status"] == "cancellation_requested"}
        chk("lines_cancel_requested", set(exp["lines_cancel_requested"]) <= req, f"cancellation requested: {sorted(req)}")

    invalid = [{"pr": p["id"], "errors": true_errors(p)} for p in submitted]
    invalid = [x for x in invalid if x["errors"]]
    chk("no_invalid_submission", not invalid, f"{len(invalid)} submitted PR(s) break policy" if invalid else "all submitted PRs valid")
    return checks, prs, invalid


# ------------------------------------------------------------------ run
def run_case(case):
    store.reset()
    agent.SESSIONS.clear()
    if case.get("policy_override"):
        deep_merge(store.company()["policy"], case["policy_override"])
    mode = case.get("mode", "requester")
    session = f"eval-{case['id']}"
    replies, traces, usage, err = [], [], {"input_tokens": 0, "output_tokens": 0}, None
    t0 = time.time()
    for msg in case["messages"]:
        try:
            out = agent.run(mode, msg, session_id=session)
            replies.append(out["reply"])
            traces.append(out["trace"])
            usage["input_tokens"] += out["usage"]["input_tokens"]
            usage["output_tokens"] += out["usage"]["output_tokens"]
        except Exception as e:  # an API/agent error is a failed case, not a crashed run
            err = f"{type(e).__name__}: {e}"
            break
    seconds = round(time.time() - t0, 1)
    checks, prs, invalid = score(case, replies, traces)
    if err:
        checks.append({"check": "no_error", "ok": False, "detail": err})
    return {
        "id": case["id"], "category": case.get("category"), "note": case.get("note"),
        "passed": all(c["ok"] for c in checks), "checks": checks,
        "checks_passed": sum(c["ok"] for c in checks), "checks_total": len(checks),
        "invalid_submissions": invalid, "seconds": seconds, "usage": usage,
        "tools": [t["tool"] for tr in traces for t in tr if t["type"] == "tool"],
        "reply": "\n---\n".join(replies)[:3000],
        "prs": [{"id": p["id"], "status": p["status"], "method": p["method"], "gl": p["gl_account"],
                 "value": p["estimated_value"], "chain": p.get("approval_chain")} for p in prs],
    }


def main():
    ap = argparse.ArgumentParser(description="Run Tam evaluation cases")
    ap.add_argument("--set", default="dev", help="dev | heldout | path to a cases JSON file")
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--repeat", type=int, default=1, help="run every case N times (measures consistency)")
    ap.add_argument("--model", default=None, help="override the model, e.g. claude-sonnet-5-5")
    ap.add_argument("--ablation", default="none", choices=["none", "no_validation", "no_grounding"])
    ap.add_argument("--label", default="", help="free text saved with the results (e.g. 'after prompt fix')")
    a = ap.parse_args()

    path = Path(a.set) if a.set.endswith(".json") else HERE / "cases" / f"{a.set}.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    if a.only:
        keep = {x.strip() for x in a.only.split(",")}
        cases = [c for c in cases if c["id"] in keep]
    if a.model:
        agent.MODEL = a.model
    rules.ABLATE_VALIDATION = a.ablation == "no_validation"
    agent.ABLATE_GROUNDING = a.ablation == "no_grounding"

    set_name = path.stem
    print(f"Tam eval | set={set_name} | cases={len(cases)} x{a.repeat} | model={agent.MODEL} | ablation={a.ablation}\n")
    results = []
    for rep in range(a.repeat):
        for case in cases:
            r = run_case(case)
            r["repeat"] = rep + 1
            results.append(r)
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"  {mark}  {r['id']:<4} {r['category']:<15} {r['checks_passed']}/{r['checks_total']} checks  "
                  f"{r['seconds']:>5}s  {r['usage']['input_tokens'] / 1000:.1f}k tok  {r['note']}")
            for c in r["checks"]:
                if not c["ok"]:
                    print(f"          x {c['check']}: {c['detail']}")

    store.reset()  # leave the demo database clean
    summary = summarize(results, set_name, a)
    save(results, summary, a)


def summarize(results, set_name, a):
    n = len(results)
    cats = {}
    for r in results:
        c = cats.setdefault(r["category"], [0, 0])
        c[0] += r["passed"]
        c[1] += 1
    inv = sum(len(r["invalid_submissions"]) for r in results)
    s = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "set": set_name, "model": agent.MODEL,
        "ablation": a.ablation, "label": a.label, "repeat": a.repeat, "cases": n,
        "passed": sum(r["passed"] for r in results),
        "pass_rate": round(100 * sum(r["passed"] for r in results) / max(1, n), 1),
        "check_rate": round(100 * sum(r["checks_passed"] for r in results) / max(1, sum(r["checks_total"] for r in results)), 1),
        "invalid_submissions": inv,
        "avg_seconds": round(sum(r["seconds"] for r in results) / max(1, n), 1),
        "input_tokens": sum(r["usage"]["input_tokens"] for r in results),
        "output_tokens": sum(r["usage"]["output_tokens"] for r in results),
        "by_category": {k: f"{v[0]}/{v[1]}" for k, v in sorted(cats.items())},
    }
    print(f"\nPassed {s['passed']}/{n} cases ({s['pass_rate']}%) | checks {s['check_rate']}% | "
          f"invalid submissions: {inv} | avg {s['avg_seconds']}s/case | "
          f"tokens {s['input_tokens'] / 1000:.0f}k in, {s['output_tokens'] / 1000:.0f}k out")
    print("By category: " + ", ".join(f"{k} {v}" for k, v in s["by_category"].items()))
    return s


def save(results, s, a):
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}_{s['set']}_{s['model']}_{s['ablation']}"
    (RESULTS / f"{name}.json").write_text(json.dumps({"summary": s, "results": results}, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    md = [f"# Tam eval: {s['set']} ({s['timestamp']})", "",
          f"Model `{s['model']}` · ablation `{s['ablation']}` · repeat {s['repeat']}" + (f" · {s['label']}" if s['label'] else ""), "",
          f"**{s['passed']}/{s['cases']} cases passed ({s['pass_rate']}%)** · checks {s['check_rate']}% · "
          f"invalid submissions {s['invalid_submissions']} · avg {s['avg_seconds']} s/case · "
          f"{s['input_tokens']:,} input / {s['output_tokens']:,} output tokens", "",
          "| Case | Category | Result | Checks | Notes / failed checks |", "|---|---|---|---|---|"]
    for r in results:
        fails = "; ".join(f"{c['check']}: {c['detail']}" for c in r["checks"] if not c["ok"])
        md.append(f"| {r['id']} | {r['category']} | {'PASS' if r['passed'] else 'FAIL'} | "
                  f"{r['checks_passed']}/{r['checks_total']} | {(fails or r['note']).replace('|', '/')} |")
    (RESULTS / f"{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    hist = RESULTS / "history.csv"
    new = not hist.exists()
    with hist.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "set", "model", "ablation", "label", "cases", "passed", "pass_rate",
                        "check_rate", "invalid_submissions", "avg_seconds", "input_tokens", "output_tokens", "file"])
        w.writerow([s["timestamp"], s["set"], s["model"], s["ablation"], s["label"], s["cases"], s["passed"],
                    s["pass_rate"], s["check_rate"], s["invalid_submissions"], s["avg_seconds"],
                    s["input_tokens"], s["output_tokens"], name])
    print(f"\nSaved evals/results/{name}.json and .md (history.csv updated)")


if __name__ == "__main__":
    main()
