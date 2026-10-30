"""
Storage layer: SQLite database, simulated clock, and the tamper-evident audit log.

Every important action is written to `events`. Each event stores the SHA-256
hash of the previous event, so editing or deleting any past entry breaks the
chain and verify_chain() reports exactly where.
"""
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "tam.db"

_lock = threading.RLock()
_company = None


def company():
    """company.json, loaded once (people, policy, catalog, vendors, renewals, history)."""
    global _company
    if _company is None:
        _company = json.loads((DATA_DIR / "company.json").read_text(encoding="utf-8"))
    return _company


@contextmanager
def conn():
    """Open, commit and always CLOSE the connection (Windows keeps files locked otherwise)."""
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS budget (
    gl TEXT PRIMARY KEY, department TEXT, name TEXT, annual REAL, spent REAL);
CREATE TABLE IF NOT EXISTS prs (
    id TEXT PRIMARY KEY, title TEXT, department TEXT, requester TEXT,
    status TEXT, doc_type TEXT, request_type TEXT, method TEXT,
    gl_account TEXT, cost_center TEXT, preferred_vendor TEXT,
    justification TEXT, lines TEXT, estimated_value REAL,
    source TEXT, quotes_count INTEGER DEFAULT 0, sole_source INTEGER DEFAULT 0,
    approval_chain TEXT, validation TEXT, extra TEXT,
    created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pr_id TEXT, step INTEGER, role TEXT,
    person TEXT, status TEXT, requested_at TEXT, decided_at TEXT, decided_by TEXT,
    comment TEXT, reminders INTEGER DEFAULT 0, escalated INTEGER DEFAULT 0, round INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pr_id TEXT, kind TEXT, title TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, to_role TEXT, pr_id TEXT,
    kind TEXT, subject TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS mobile_lines (
    number TEXT PRIMARY KEY, employee_id TEXT, package TEXT, device TEXT, monthly REAL,
    status TEXT, activated_at TEXT, pr_id TEXT, cancel_requested_at TEXT);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, pr_id TEXT, actor TEXT,
    action TEXT, details TEXT, prev_hash TEXT, hash TEXT);
"""


# ------------------------------------------------------------------ clock
def now() -> datetime:
    """Simulated 'now' = real start time of the demo + hours fast-forwarded."""
    with conn() as c:
        base = c.execute("SELECT value FROM meta WHERE key='clock_base'").fetchone()
        off = c.execute("SELECT value FROM meta WHERE key='clock_offset_h'").fetchone()
    base_dt = datetime.fromisoformat(base["value"]) if base else datetime.now().replace(microsecond=0)
    return base_dt + timedelta(hours=float(off["value"]) if off else 0)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def advance_clock(hours: float):
    with _lock, conn() as c:
        off = c.execute("SELECT value FROM meta WHERE key='clock_offset_h'").fetchone()
        new = (float(off["value"]) if off else 0) + hours
        c.execute("INSERT OR REPLACE INTO meta VALUES ('clock_offset_h', ?)", (str(new),))


# ------------------------------------------------------------------ audit log
def _hash(prev_hash, ts, pr_id, actor, action, details_json):
    raw = "|".join([prev_hash, ts, pr_id or "", actor, action, details_json])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def log_event(pr_id, actor, action, details=None, ts=None):
    """Append one entry to the hash-chained audit log."""
    with _lock, conn() as c:
        last = c.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else "GENESIS"
        ts = ts or iso(now())
        dj = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)
        h = _hash(prev, ts, pr_id, actor, action, dj)
        c.execute("INSERT INTO events (ts, pr_id, actor, action, details, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
                  (ts, pr_id, actor, action, dj, prev, h))
        return h


def verify_chain():
    """Recompute every hash. Returns ok + the first broken entry if any."""
    with conn() as c:
        rows = c.execute("SELECT * FROM events ORDER BY id").fetchall()
    prev = "GENESIS"
    for r in rows:
        expected = _hash(prev, r["ts"], r["pr_id"], r["actor"], r["action"], r["details"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"ok": False, "entries_checked": len(rows), "broken_at_event": r["id"],
                    "message": f"Log entry #{r['id']} was modified or a previous entry was removed."}
        prev = r["hash"]
    return {"ok": True, "entries_checked": len(rows), "last_hash": prev[:16],
            "message": f"All {len(rows)} log entries verified; no tampering detected."}


def events_for(pr_id=None):
    with conn() as c:
        q = "SELECT * FROM events" + (" WHERE pr_id=?" if pr_id else "") + " ORDER BY id"
        rows = c.execute(q, (pr_id,) if pr_id else ()).fetchall()
    return [dict(r, details=json.loads(r["details"])) for r in rows]


# ------------------------------------------------------------------ helpers
def notify(to_role, pr_id, kind, subject, body):
    with conn() as c:
        c.execute("INSERT INTO notifications (ts, to_role, pr_id, kind, subject, body) VALUES (?,?,?,?,?,?)",
                  (iso(now()), to_role, pr_id, kind, subject, body))


def add_document(pr_id, kind, title, ts=None):
    with conn() as c:
        c.execute("INSERT INTO documents (pr_id, kind, title, created_at) VALUES (?,?,?,?)",
                  (pr_id, kind, title, ts or iso(now())))


def person(role):
    p = company()["people"].get(role, {"name": role, "title": role})
    return p["name"]


_JSON_COLS = ("lines", "approval_chain", "validation", "extra")


def row_to_pr(r):
    d = dict(r)
    for k in _JSON_COLS:
        d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "extra" else {})
    return d


def get_pr(pr_id):
    with conn() as c:
        r = c.execute("SELECT * FROM prs WHERE id=?", (pr_id,)).fetchone()
        if not r:
            return None
        pr = row_to_pr(r)
        allrows = [dict(a) for a in c.execute(
            "SELECT * FROM approvals WHERE pr_id=? ORDER BY round, step", (pr_id,)).fetchall()]
        cur = max((a["round"] for a in allrows), default=1)
        pr["approvals"] = [a for a in allrows if a["round"] == cur]      # current approval round
        pr["approval_history"] = allrows                                 # every round, for audit
        pr["approval_round"] = cur
        pr["documents"] = [dict(d) for d in c.execute(
            "SELECT * FROM documents WHERE pr_id=? ORDER BY id", (pr_id,)).fetchall()]
    return pr


def list_prs():
    with conn() as c:
        rows = c.execute("SELECT * FROM prs ORDER BY created_at DESC").fetchall()
    return [row_to_pr(r) for r in rows]


def save_pr(pr: dict):
    cols = ["id", "title", "department", "requester", "status", "doc_type", "request_type", "method",
            "gl_account", "cost_center", "preferred_vendor", "justification", "lines", "estimated_value",
            "source", "quotes_count", "sole_source", "approval_chain", "validation", "extra",
            "created_at", "updated_at"]
    vals = []
    for k in cols:
        v = pr.get(k)
        if k in _JSON_COLS:
            v = json.dumps(v if v is not None else ([] if k != "extra" else {}), ensure_ascii=False)
        vals.append(v)
    with _lock, conn() as c:
        c.execute(f"INSERT OR REPLACE INTO prs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)


def next_pr_id():
    with _lock, conn() as c:
        r = c.execute("SELECT value FROM meta WHERE key='pr_seq'").fetchone()
        n = int(r["value"]) + 1 if r else 301
        c.execute("INSERT OR REPLACE INTO meta VALUES ('pr_seq', ?)", (str(n),))
    return f"PR-2026-{n:04d}"


# ------------------------------------------------------------------ budget
def budget_rows():
    """Budget per G/L = baseline from the Excel sheet minus commitments of approved PRs."""
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM budget ORDER BY gl").fetchall()]
        committed = {r["gl_account"]: r["s"] for r in c.execute(
            "SELECT gl_account, SUM(estimated_value) s FROM prs "
            "WHERE status IN ('approved','sent_to_procurement') AND source!='history' GROUP BY gl_account")}
    for r in rows:
        r["committed"] = committed.get(r["gl"], 0) or 0
        r["remaining"] = r["annual"] - r["spent"] - r["committed"]
    return rows


# ------------------------------------------------------------------ reset / seed
def reset():
    """Wipe and rebuild the database from data/company.json and data/budget.xlsx."""
    global _company
    _company = None
    with _lock:
        with conn() as c:
            # Empty the database in place instead of deleting the file (works even if Windows has it open).
            for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                     "AND name NOT LIKE 'sqlite_%'").fetchall():
                c.execute(f'DROP TABLE IF EXISTS "{name}"')
            c.executescript(SCHEMA)
            start = datetime.now().replace(minute=0, second=0, microsecond=0)
            c.execute("INSERT INTO meta VALUES ('clock_base', ?)", (start.isoformat(),))
            c.execute("INSERT INTO meta VALUES ('clock_offset_h', '0')")
            c.execute("INSERT INTO meta VALUES ('pr_seq', '300')")

            # Budget baseline comes from the same kind of Excel sheet finance keeps.
            ws = load_workbook(DATA_DIR / "budget.xlsx").active
            for row in ws.iter_rows(min_row=4, values_only=True):
                if row[0] and row[1]:
                    c.execute("INSERT INTO budget VALUES (?,?,?,?,?)",
                              (str(row[1]), row[0], row[2], float(row[3]), float(row[4])))

        log_event(None, "system", "system_initialized", {"note": "Demo data loaded; audit log started."})
        _seed_history(start)
        _seed_lines(start)


def _seed_history(start):
    data = company()
    for h in data["history"]:
        created = start - timedelta(days=h["days_ago"])
        ts = iso(created)
        pr = {
            "id": h["id"], "title": h["title"], "department": h.get("department", "IT"), "requester": "requester",
            "status": "sent_to_procurement", "doc_type": "Normal", "request_type": "New Procurement",
            "method": h["method"], "gl_account": h["gl"], "cost_center": h.get("department", "IT"),
            "preferred_vendor": h["vendor"], "justification": "(historical record)",
            "lines": [], "estimated_value": h["total"], "source": "history",
            "quotes_count": h["quotes"], "sole_source": 1 if h["method"] == "Sole Source" else 0,
            "approval_chain": h["approvers"], "validation": [], "extra": {},
            "created_at": ts, "updated_at": ts,
        }
        save_pr(pr)
        log_event(h["id"], person("requester"), "pr_submitted", {"value": h["total"], "method": h["method"]}, ts=ts)
        with conn() as c:
            for i, role in enumerate(h["approvers"]):
                dts = iso(created + timedelta(days=2 * (i + 1)))
                c.execute("INSERT INTO approvals (pr_id, step, role, person, status, requested_at, decided_at, decided_by, comment) "
                          "VALUES (?,?,?,?,?,?,?,?,?)",
                          (h["id"], i, role, person(role), "approved", ts, dts, person(role), ""))
        for i, role in enumerate(h["approvers"]):
            log_event(h["id"], person(role), "approved", {"role": role},
                      ts=iso(created + timedelta(days=2 * (i + 1))))
        for d in h["docs"]:
            add_document(h["id"], d, d.replace("_", " ").title(), ts=ts)


# ------------------------------------------------------------------ employees and mobile lines
def _clock_start():
    with conn() as c:
        return datetime.fromisoformat(c.execute("SELECT value FROM meta WHERE key='clock_base'").fetchone()["value"])


def employees():
    """HR directory with real dates: joining employees get a start date, leavers a leaving date."""
    start = _clock_start()
    out = []
    for e in company().get("employees", []):
        e = dict(e)
        if e["status"] == "joining":
            e["start_date"] = (start + timedelta(days=e.get("days", 0))).strftime("%Y-%m-%d")
        if e["status"] == "left":
            e["left_date"] = (start - timedelta(days=e.get("days", 0))).strftime("%Y-%m-%d")
        e.pop("days", None)
        out.append(e)
    return out


def find_employee(query):
    q = (query or "").strip().lower()
    if not q:
        return None
    emps = employees()
    for e in emps:
        if e["id"].lower() == q or e["name"].lower() == q:
            return e
    matches = [e for e in emps if q in e["name"].lower() or all(w in e["name"].lower() for w in q.split())]
    return matches[0] if len(matches) == 1 else None


def mobile_lines(include_cancelled=True):
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM mobile_lines ORDER BY number").fetchall()]
    emps = {e["id"]: e for e in employees()}
    for r in rows:
        r["employee"] = emps.get(r["employee_id"], {})
    return rows if include_cancelled else [r for r in rows if r["status"] != "cancelled"]


def _seed_lines(start):
    with conn() as c:
        for l in company().get("mobile_lines", []):
            c.execute("INSERT INTO mobile_lines (number, employee_id, package, device, monthly, status, activated_at) "
                      "VALUES (?,?,?,?,?,?,?)", (l["number"], l["employee_id"], l["package"], l["device"], l["monthly"],
                                                "active", iso(start - timedelta(days=400))))


def next_line_number():
    with conn() as c:
        nums = [r["number"] for r in c.execute("SELECT number FROM mobile_lines").fetchall()]
    last = max(int(n.replace(" ", "")[-3:]) for n in nums) if nums else 200
    return f"0550 114 {last + 1:03d}"
