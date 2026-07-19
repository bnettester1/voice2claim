"""DAL flywheel — evaluations (★ theo vai) + metrics so sánh per version."""
from __future__ import annotations

import json

from app.db.database import db


def upsert_evaluation(run_id: int, rater_kind: str, score: int | None,
                      comment: str = "", rater_id: str = "",
                      criteria: dict | None = None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO evaluations(run_id, rater_kind, rater_id, score,"
            " comment, criteria_json) VALUES(?,?,?,?,?,?)"
            " ON CONFLICT(run_id, rater_kind, rater_id) DO UPDATE SET"
            " score = excluded.score, comment = excluded.comment,"
            " criteria_json = excluded.criteria_json",
            (run_id, rater_kind, rater_id, score, comment,
             json.dumps(criteria or {}, ensure_ascii=False)))


def run_evaluations(run_id: int) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM evaluations WHERE run_id=? ORDER BY id", (run_id,))]


def metrics_by_key(key: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT m.*, "
            " (SELECT ROUND(AVG(e.score),2) FROM evaluations e"
            "   JOIN workflow_runs r ON r.id = e.run_id"
            "   JOIN workflow_defs d2 ON d2.id = r.def_id"
            "   WHERE d2.key = m.key AND d2.version = m.version"
            "     AND e.rater_kind = 'customer') AS avg_customer,"
            " (SELECT ROUND(AVG(e.score),2) FROM evaluations e"
            "   JOIN workflow_runs r ON r.id = e.run_id"
            "   JOIN workflow_defs d2 ON d2.id = r.def_id"
            "   WHERE d2.key = m.key AND d2.version = m.version"
            "     AND e.rater_kind IN ('handler','director','agent')) AS avg_staff"
            " FROM v_workflow_metrics m WHERE m.key=? ORDER BY m.version",
            (key,)).fetchall()
        return [dict(r) for r in rows]
