"""DAL ERP-lite — employees + tasks (hộp công việc theo vai)."""
from __future__ import annotations

import json

from app.db.database import db, record_history


# ---------------------------------------------------------------- employees
def handler_for_group(claim_group: str) -> dict | None:
    """Thẩm định viên active phụ trách nhóm claim (thay _LOCAL_HANDLERS)."""
    with db() as conn:
        r = conn.execute(
            "SELECT id, name, email FROM employees WHERE active=1"
            " AND role='assessor' AND claim_groups LIKE ?"
            " ORDER BY id LIMIT 1", (f'%"{claim_group}"%',)).fetchone()
        return dict(r) if r else None


def employees_by_role(role: str) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM employees WHERE active=1 AND role=? ORDER BY id",
            (role,))]


def list_employees() -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM employees ORDER BY id")]


def update_employee(employee_id: str, name: str = "",
                    email: str | None = None,
                    phone: str | None = None) -> bool:
    """Sửa người xử lý (đổi người nhận mail giao việc khi demo)."""
    from app.db.dal.crm import _norm
    sets: list[str] = []
    vals: list = []
    if name.strip():
        sets += ["name=?", "name_norm=?"]
        vals += [name.strip(), _norm(name)]
    for col, v in (("email", email), ("phone", phone)):
        if v is not None:
            sets.append(f"{col}=?")
            vals.append(str(v).strip())
    if not sets:
        return False
    with db() as conn:
        cur = conn.execute(
            f"UPDATE employees SET {', '.join(sets)} WHERE id=?",
            (*vals, employee_id))
        if cur.rowcount:
            record_history(conn, "customer", employee_id, "contact_updated",
                           "", "employee", "",
                           f"Cập nhật hồ sơ nhân sự {employee_id}")
        return cur.rowcount > 0


# ---------------------------------------------------------------- tasks
def create_task(title: str, task_type: str, assignee_role: str,
                assignee_id: str | None = None, description: str = "",
                priority: str = "THƯỜNG", customer_id: str | None = None,
                claim_id: str | None = None, policy_id: str | None = None,
                run_id: int | None = None, step_run_id: int | None = None,
                data: dict | None = None, actor_kind: str = "ai",
                note: str = "") -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO tasks(title, description, task_type, assignee_id,"
            " assignee_role, priority, customer_id, claim_id, policy_id,"
            " run_id, step_run_id, data_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, description, task_type, assignee_id, assignee_role,
             priority, customer_id, claim_id, policy_id, run_id, step_run_id,
             json.dumps(data or {}, ensure_ascii=False)))
        task_id = int(cur.lastrowid)
        record_history(conn, "task", str(task_id), "open", "", actor_kind, "",
                       note or f"Giao việc: {title} → {assignee_id or assignee_role}")
        return task_id


def task_inbox(role: str = "", employee_id: str = "",
               status: str = "open,in_progress", limit: int = 50) -> list[dict]:
    statuses = [s.strip() for s in status.split(",") if s.strip()]
    ph = ",".join("?" * len(statuses))
    with db() as conn:
        rows = conn.execute(
            f"SELECT t.*, c.name AS customer_name, cl.status AS claim_status,"
            f" e.name AS assignee_name"
            f" FROM tasks t LEFT JOIN customers c ON c.id = t.customer_id"
            f" LEFT JOIN claims cl ON cl.id = t.claim_id"
            f" LEFT JOIN employees e ON e.id = t.assignee_id"
            f" WHERE t.status IN ({ph})"
            f" AND (? = '' OR t.assignee_id = ? OR"
            f"      (t.assignee_id IS NULL AND t.assignee_role = ?))"
            f" ORDER BY CASE t.priority WHEN 'CAO' THEN 0"
            f"  WHEN 'TRUNG BÌNH' THEN 1 ELSE 2 END, t.created_at LIMIT ?",
            (*statuses, employee_id or role, employee_id, role, limit))
        return [dict(r) for r in rows]


def get_task(task_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute(
            "SELECT t.*, c.name AS customer_name FROM tasks t"
            " LEFT JOIN customers c ON c.id = t.customer_id"
            " WHERE t.id=?", (task_id,)).fetchone()
        return dict(r) if r else None


def complete_task(task_id: int, outcome: str = "completed",
                  outcome_note: str = "", payload: dict | None = None,
                  actor_id: str = "") -> dict | None:
    """Đóng task (idempotent qua guard status) → trả row đã cập nhật.

    Việc bắn event 'task.completed' để resume workflow do tầng gọi lo
    (app/workflow) — DAL giữ thuần dữ liệu.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?",
                           (task_id,)).fetchone()
        if row is None or row["status"] == "done":
            return dict(row) if row else None
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        if payload:
            data["result"] = payload
        conn.execute(
            "UPDATE tasks SET status='done', outcome=?, outcome_note=?,"
            " data_json=?, completed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
            " updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            " WHERE id=? AND status <> 'done'",
            (outcome, outcome_note,
             json.dumps(data, ensure_ascii=False), task_id))
        record_history(conn, "task", str(task_id), f"done:{outcome}",
                       row["status"], "employee", actor_id, outcome_note)
        r2 = conn.execute("SELECT * FROM tasks WHERE id=?",
                          (task_id,)).fetchone()
        return dict(r2) if r2 else None
