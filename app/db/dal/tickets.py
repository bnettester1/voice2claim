"""DAL tickets — bền hoá ticket_store (dict gốc giữ nguyên trong payload_json)."""
from __future__ import annotations

import json

from app.db.database import db


def insert_from_dict(t: dict) -> None:
    """Ticket dict từ execute_action (qua listener) → 1 row, idempotent."""
    tid = str(t.get("id") or "")
    if not tid:
        return
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tickets(id, action, action_label, pack,"
            " pack_icon, priority, status, pdf_url, recording_url,"
            " fields_count, payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (tid, str(t.get("action") or ""), str(t.get("action_label") or ""),
             str(t.get("pack") or ""), str(t.get("pack_icon") or ""),
             str(t.get("priority") or "THƯỜNG"), str(t.get("status") or ""),
             str(t.get("pdf") or ""), str(t.get("recording") or ""),
             int(t.get("fields_count") or 0),
             json.dumps(t, ensure_ascii=False, default=str)))


def max_seq() -> int:
    """Số thứ tự TCK lớn nhất đã cấp (khởi điểm lịch sử là 11)."""
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(CAST(substr(id, 5) AS INTEGER)), 11)"
            " FROM tickets WHERE id LIKE 'TCK-%'").fetchone()
        return int(row[0])


def recent_payloads(limit: int = 50) -> list[dict]:
    """Ticket dict gốc, mới nhất trước — hydrate console sau restart."""
    out: list[dict] = []
    with db() as conn:
        for r in conn.execute(
                "SELECT payload_json FROM tickets"
                " ORDER BY created_at DESC LIMIT ?", (limit,)):
            try:
                out.append(json.loads(r["payload_json"]))
            except Exception:  # noqa: BLE001
                continue
    return out


def link_ticket(ticket_id: str, customer_id: str | None = None,
                claim_id: str | None = None, run_id: int | None = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE tickets SET"
            " customer_id = COALESCE(?, customer_id),"
            " claim_id = COALESCE(?, claim_id),"
            " run_id = COALESCE(?, run_id) WHERE id=?",
            (customer_id, claim_id, run_id, ticket_id))


def list_tickets(limit: int = 100) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, created_at, action, action_label, pack, pack_icon,"
            " priority, status, pdf_url, recording_url, fields_count,"
            " customer_id, claim_id, run_id FROM tickets"
            " ORDER BY created_at DESC LIMIT ?", (limit,))]
