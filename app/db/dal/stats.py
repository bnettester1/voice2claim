"""DAL thống kê — KPI dashboard + AI Decision Feed."""
from __future__ import annotations

from app.db.database import db


def dashboard() -> dict:
    with db() as conn:
        def one(sql: str) -> int:
            return int(conn.execute(sql).fetchone()[0])

        counts = {
            "db_ok": True,
            "customers": one("SELECT COUNT(*) FROM customers"),
            "policies_active": one(
                "SELECT COUNT(*) FROM policies WHERE status='active'"),
            "policies_pending": one(
                "SELECT COUNT(*) FROM policies WHERE status IN"
                " ('draft','pending_review','pending_sign')"),
            "claims_open": one(
                "SELECT COUNT(*) FROM claims WHERE status IN"
                " ('received','pending_assignment','investigating','pending_approval')"),
            "claims_paid": one(
                "SELECT COUNT(*) FROM claims WHERE status='paid'"),
            "tasks_open": one(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('open','in_progress')"),
            "tickets": one("SELECT COUNT(*) FROM tickets"),
            "calls": one(
                "SELECT COUNT(*) FROM interactions WHERE kind LIKE 'call%'"),
            "calls_today": one(
                "SELECT COUNT(*) FROM interactions WHERE kind LIKE 'call%'"
                " AND date(created_at) = date('now')"),
            "runs_active": one(
                "SELECT COUNT(*) FROM workflow_runs WHERE status IN"
                " ('running','waiting_event','waiting_task')"),
        }
        feed = [dict(r) for r in conn.execute(
            "SELECT * FROM status_history ORDER BY id DESC LIMIT 25")]
    return {"counts": counts, "feed": feed}
