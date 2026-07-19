"""DAL workflow — defs version hoá, runs/steps, events/token (CAS exactly-once)."""
from __future__ import annotations

import json
import secrets
import sqlite3

from app.db.database import db, record_history


# ---------------------------------------------------------------- defs
def insert_def(key: str, name: str, graph: dict, trigger: dict | None = None,
               description: str = "", version: int = 1, status: str = "active",
               source: str = "seed", note: str = "",
               source_extraction_id: int | None = None) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO workflow_defs(key, version, name, description,"
            " status, graph_json, trigger_json, source, note,"
            " source_extraction_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (key, version, name, description, status,
             json.dumps(graph, ensure_ascii=False),
             json.dumps(trigger or {}, ensure_ascii=False), source, note,
             source_extraction_id))
        return int(cur.lastrowid)


def get_def(def_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute("SELECT * FROM workflow_defs WHERE id=?",
                         (def_id,)).fetchone()
        return _def_dict(r)


def get_def_by_key(key: str, version: int | None = None) -> dict | None:
    with db() as conn:
        if version is None:
            r = conn.execute(
                "SELECT * FROM workflow_defs WHERE key=? AND status='active'",
                (key,)).fetchone()
            if r is None:                      # chưa active → bản mới nhất
                r = conn.execute(
                    "SELECT * FROM workflow_defs WHERE key=?"
                    " ORDER BY version DESC LIMIT 1", (key,)).fetchone()
        else:
            r = conn.execute(
                "SELECT * FROM workflow_defs WHERE key=? AND version=?",
                (key, version)).fetchone()
        return _def_dict(r)


def _def_dict(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    d["graph"] = json.loads(d.pop("graph_json") or "{}")
    d["trigger"] = json.loads(d.pop("trigger_json") or "{}")
    return d


def list_defs() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT d.id, d.key, d.version, d.name, d.description, d.status,"
            " d.source, d.created_at,"
            " (SELECT COUNT(*) FROM workflow_runs r WHERE r.def_id = d.id) AS runs"
            " FROM workflow_defs d ORDER BY d.key, d.version DESC").fetchall()
        return [dict(r) for r in rows]


def list_versions(key: str) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, version, status, note, source, created_at,"
            " (SELECT COUNT(*) FROM workflow_runs r WHERE r.def_id = workflow_defs.id) AS runs"
            " FROM workflow_defs WHERE key=? ORDER BY version DESC", (key,))]


def next_version(key: str) -> int:
    with db() as conn:
        r = conn.execute("SELECT COALESCE(MAX(version),0) FROM workflow_defs"
                         " WHERE key=?", (key,)).fetchone()
        return int(r[0]) + 1


def activate(key: str, version: int) -> bool:
    with db() as conn:
        row = conn.execute("SELECT id FROM workflow_defs WHERE key=? AND"
                           " version=?", (key, version)).fetchone()
        if row is None:
            return False
        conn.execute("UPDATE workflow_defs SET status='archived'"
                     " WHERE key=? AND status='active'", (key,))
        conn.execute("UPDATE workflow_defs SET status='active' WHERE id=?",
                     (row["id"],))
        record_history(conn, "run", f"def:{key}", f"active:v{version}",
                       actor_kind="employee", note=f"Kích hoạt {key} v{version}")
    return True


def active_defs_full() -> list[dict]:
    """Bản active của mọi key (kèm trigger) — cho orchestrator dispatch."""
    with db() as conn:
        rows = conn.execute(
            "SELECT id, key, name, trigger_json FROM workflow_defs"
            " WHERE status='active' ORDER BY id").fetchall()
    out = []
    for r in rows:
        out.append({"id": r["id"], "key": r["key"], "name": r["name"],
                    "trigger": json.loads(r["trigger_json"] or "{}")})
    return out


def active_flows() -> list[dict]:
    """Cho sidebar: các flow đang active (key, name, icon từ trigger)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT key, name, trigger_json FROM workflow_defs"
            " WHERE status='active' ORDER BY id").fetchall()
    out = []
    for r in rows:
        trig = json.loads(r["trigger_json"] or "{}")
        out.append({"key": r["key"], "name": r["name"],
                    "icon": trig.get("icon", "🔀")})
    return out


# ---------------------------------------------------------------- runs
def create_run(def_id: int, context: dict, channel: str = "api",
               customer_id: str | None = None, claim_id: str | None = None,
               policy_id: str | None = None, ticket_id: str | None = None,
               current_node: str = "") -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO workflow_runs(def_id, status, current_node, channel,"
            " customer_id, claim_id, policy_id, ticket_id, context_json)"
            " VALUES(?, 'running', ?, ?, ?, ?, ?, ?, ?)",
            (def_id, current_node, channel, customer_id, claim_id, policy_id,
             ticket_id, json.dumps(context, ensure_ascii=False)))
        run_id = int(cur.lastrowid)
        record_history(conn, "run", str(run_id), "running", "",
                       "ai", "", f"Khởi động workflow run #{run_id} ({channel})")
        return run_id


def get_run(run_id: int, with_steps: bool = True) -> dict | None:
    with db() as conn:
        r = conn.execute(
            "SELECT r.*, d.key AS def_key, d.version AS def_version,"
            " d.name AS def_name, d.graph_json FROM workflow_runs r"
            " JOIN workflow_defs d ON d.id = r.def_id WHERE r.id=?",
            (run_id,)).fetchone()
        if r is None:
            return None
        run = dict(r)
        run["graph"] = json.loads(run.pop("graph_json") or "{}")
        run["context"] = json.loads(run.pop("context_json") or "{}")
        if with_steps:
            run["steps"] = [dict(s) for s in conn.execute(
                "SELECT * FROM step_runs WHERE run_id=? ORDER BY id",
                (run_id,))]
        return run


def list_runs(def_key: str = "", status: str = "", limit: int = 50) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT r.id, r.status, r.current_node, r.channel, r.outcome,"
            " r.customer_id, r.claim_id, r.policy_id, r.started_at, r.ended_at,"
            " d.key AS def_key, d.version AS def_version, d.name AS def_name,"
            " c.name AS customer_name"
            " FROM workflow_runs r JOIN workflow_defs d ON d.id = r.def_id"
            " LEFT JOIN customers c ON c.id = r.customer_id"
            " WHERE (? = '' OR d.key = ?) AND (? = '' OR r.status = ?)"
            " ORDER BY r.id DESC LIMIT ?",
            (def_key, def_key, status, status, limit)).fetchall()
        return [dict(r) for r in rows]


def cas_run_status(run_id: int, from_statuses: tuple[str, ...],
                   to_status: str) -> bool:
    """Compare-and-set — nền tảng idempotency của resume (double-click an toàn)."""
    ph = ",".join("?" * len(from_statuses))
    with db() as conn:
        cur = conn.execute(
            f"UPDATE workflow_runs SET status=?,"
            f" updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            f" WHERE id=? AND status IN ({ph})",
            (to_status, run_id, *from_statuses))
        return cur.rowcount > 0


def set_run(run_id: int, **cols) -> None:
    allowed = {"status", "current_node", "context", "outcome", "error",
               "ended_at", "customer_id", "claim_id", "policy_id",
               "ticket_id", "correlation_key", "interaction_id"}
    sets: dict = {}
    for k, v in cols.items():
        if k not in allowed:
            continue
        if k == "context":
            sets["context_json"] = json.dumps(v, ensure_ascii=False)
        else:
            sets[k] = v
    if not sets:
        return
    frag = ", ".join(f"{k}=?" for k in sets)
    with db() as conn:
        conn.execute(
            f"UPDATE workflow_runs SET {frag},"
            f" updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (*sets.values(), run_id))


def finish_run(run_id: int, status: str, outcome: str = "",
               error: str = "") -> None:
    with db() as conn:
        conn.execute(
            "UPDATE workflow_runs SET status=?, outcome=?, error=?,"
            " updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
            " ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (status, outcome, error[:300], run_id))
        record_history(conn, "run", str(run_id), f"{status}:{outcome or '-'}",
                       "running", "ai", "",
                       f"Run #{run_id} kết thúc — {outcome or status}"
                       + (f" ({error[:80]})" if error else ""))


# ---------------------------------------------------------------- steps
def start_step(run_id: int, node_id: str, action_key: str = "",
               attempt: int = 1, input_data: dict | None = None) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO step_runs(run_id, node_id, action_key, attempt,"
            " input_json) VALUES(?,?,?,?,?)",
            (run_id, node_id, action_key, attempt,
             json.dumps(input_data or {}, ensure_ascii=False, default=str)))
        return int(cur.lastrowid)


def finish_step(step_id: int, status: str, output: dict | None = None,
                error: str = "", waiting_event: str = "") -> None:
    with db() as conn:
        conn.execute(
            "UPDATE step_runs SET status=?, output_json=?, error=?,"
            " waiting_event=?, ended_at=CASE WHEN ? IN"
            " ('completed','failed','skipped')"
            " THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE ended_at END"
            " WHERE id=?",
            (status, json.dumps(output or {}, ensure_ascii=False, default=str),
             error[:300], waiting_event, status, step_id))


def latest_step(run_id: int, node_id: str) -> dict | None:
    with db() as conn:
        r = conn.execute(
            "SELECT * FROM step_runs WHERE run_id=? AND node_id=?"
            " ORDER BY id DESC LIMIT 1", (run_id, node_id)).fetchone()
        return dict(r) if r else None


def waiting_step(run_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute(
            "SELECT * FROM step_runs WHERE run_id=? AND status='waiting'"
            " ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
        return dict(r) if r else None


def max_attempt(run_id: int, node_id: str) -> int:
    with db() as conn:
        r = conn.execute(
            "SELECT COALESCE(MAX(attempt),0) FROM step_runs"
            " WHERE run_id=? AND node_id=?", (run_id, node_id)).fetchone()
        return int(r[0])


def interrupt_running_steps(run_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE step_runs SET status='interrupted',"
                     " ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"
                     " WHERE run_id=? AND status='running'", (run_id,))


def runs_to_recover() -> list[int]:
    with db() as conn:
        return [int(r[0]) for r in conn.execute(
            "SELECT id FROM workflow_runs WHERE status='running'")]


# ---------------------------------------------------------------- events / tokens
def mint_token(key: str, run_id: int, payload: dict | None = None) -> str:
    """Token single-use gắn (run, event key) — dùng cho link ký/đánh giá."""
    token = secrets.token_urlsafe(16)
    with db() as conn:
        conn.execute(
            "INSERT INTO events(key, run_id, correlation_key, payload_json,"
            " source, status) VALUES(?,?,?,?, 'system', 'minted')",
            (key, run_id, token,
             json.dumps(payload or {}, ensure_ascii=False)))
        conn.execute("UPDATE workflow_runs SET correlation_key=? WHERE id=?",
                     (token, run_id))
    return token


def get_token(token: str) -> dict | None:
    with db() as conn:
        r = conn.execute(
            "SELECT * FROM events WHERE correlation_key=?"
            " ORDER BY id DESC LIMIT 1", (token,)).fetchone()
        return dict(r) if r else None


def consume_token(token: str, payload: dict | None = None,
                  step_run_id: int | None = None) -> dict | None:
    """CAS minted→consumed. rowcount 0 = đã dùng/không tồn tại → None."""
    with db() as conn:
        r = conn.execute(
            "SELECT * FROM events WHERE correlation_key=? AND status='minted'"
            " ORDER BY id DESC LIMIT 1", (token,)).fetchone()
        if r is None:
            return None
        cur = conn.execute(
            "UPDATE events SET status='consumed', payload_json=?,"
            " consumed_by_step_run_id=?,"
            " consumed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            " WHERE id=? AND status='minted'",
            (json.dumps(payload or {}, ensure_ascii=False), step_run_id,
             r["id"]))
        if cur.rowcount == 0:
            return None
        return dict(r)


def push_event(key: str, run_id: int | None = None, payload: dict | None = None,
               source: str = "system",
               step_run_id: int | None = None) -> int:
    """Sự kiện đã xử lý xong (audit trail) — task.completed, call.finished…"""
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO events(key, run_id, payload_json, source, status,"
            " consumed_by_step_run_id, consumed_at)"
            " VALUES(?,?,?,?, 'consumed', ?,"
            " strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (key, run_id, json.dumps(payload or {}, ensure_ascii=False,
                                     default=str), source, step_run_id))
        return int(cur.lastrowid)
