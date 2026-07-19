"""DAL CRM — customers / policies / assets / claims / interactions / documents.

Hợp đồng quan trọng nhất: to_crm_dict() trả ĐÚNG shape dict cũ của crm.py
({id,name,email,phone,national_id,policy,claim{id,type,status,handler}})
để verify_identity/profile_summary/status_reply/engine/flow_agent không đổi.
"""
from __future__ import annotations

import json
import sqlite3
import time

from app.db.database import db, next_code, record_history

_GROUP_CODE = {"xe": "XE", "y_te": "YT", "nhan_tho": "NT"}


def _norm(text: str) -> str:
    from app.core.triggers import normalize_vi
    return normalize_vi(text or "")


# ---------------------------------------------------------------- customers
def to_crm_dict(conn: sqlite3.Connection, c: sqlite3.Row | dict) -> dict:
    """Row customers (+policy/claim mới nhất) → dict legacy cho tổng đài."""
    out = {"id": c["id"], "name": c["name"], "email": c["email"] or "",
           "phone": c["phone"] or "", "national_id": c["national_id"] or ""}
    pol = conn.execute(
        "SELECT product_name FROM policies WHERE customer_id=? AND status NOT IN"
        " ('cancelled','expired','rejected') ORDER BY created_at DESC LIMIT 1",
        (c["id"],)).fetchone()
    if pol:
        out["policy"] = pol["product_name"]
    cl = conn.execute(
        "SELECT cl.id, cl.claim_type, cl.status, e.name AS handler"
        " FROM claims cl LEFT JOIN employees e ON e.id = cl.handler_id"
        " WHERE cl.customer_id=? ORDER BY cl.created_at DESC LIMIT 1",
        (c["id"],)).fetchone()
    if cl:
        out["claim"] = {"id": cl["id"], "type": cl["claim_type"] or "",
                        "status": cl["status"], "handler": cl["handler"] or ""}
    return out


def search_customer_legacy(query: str) -> dict | None:
    """Fuzzy theo name_norm (token LIKE + re-rank như _local_lookup cũ)."""
    q = _norm(query)
    if not q:
        return None
    toks = [t for t in q.split() if t]
    if not toks:
        return None
    with db() as conn:
        seen: dict[str, sqlite3.Row] = {}
        for t in toks:
            for r in conn.execute(
                    "SELECT * FROM customers WHERE name_norm LIKE ? LIMIT 20",
                    (f"%{t}%",)):
                seen[r["id"]] = r
        best, best_score = None, 0
        for r in seen.values():
            name = r["name_norm"]
            score = len(set(toks) & set(name.split()))
            if q in name or name in q:
                score += 2
            if score > best_score:
                best, best_score = r, score
        if best is None or best_score < 1:
            return None
        return to_crm_dict(conn, best)


def update_customer(customer_id: str, name: str = "", email: str | None = None,
                    phone: str | None = None,
                    national_id: str | None = None) -> bool:
    """Sửa liên hệ khách (đổi người demo). Chỉ đổi cột được gửi; đổi tên thì
    name_norm cập nhật theo (lookup cuộc gọi dựa vào đây)."""
    sets: list[str] = []
    vals: list = []
    if name.strip():
        sets += ["name=?", "name_norm=?"]
        vals += [name.strip(), _norm(name)]
    for col, v in (("email", email), ("phone", phone),
                   ("national_id", national_id)):
        if v is not None:
            sets.append(f"{col}=?")
            vals.append(str(v).strip())
    if not sets:
        return False
    with db() as conn:
        cur = conn.execute(
            f"UPDATE customers SET {', '.join(sets)},"
            f" updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (*vals, customer_id))
        if cur.rowcount:
            record_history(conn, "customer", customer_id, "contact_updated",
                           "", "employee", "",
                           "Cập nhật liên hệ khách (demo)")
        return cur.rowcount > 0


def get_customer(customer_id: str) -> dict | None:
    with db() as conn:
        r = conn.execute("SELECT * FROM customers WHERE id=?",
                         (customer_id,)).fetchone()
        return dict(r) if r else None


def upsert_customer_legacy(cust: dict, source: str = "notify_import") -> str:
    """Dict legacy (REST notify / kho local / call) → row customers (+claim).

    Trả về customer_id. Không đè field đã có bằng giá trị rỗng.
    """
    name = str(cust.get("name") or cust.get("ten") or "").strip()
    if not name:
        return ""
    cid = str(cust.get("id") or "").strip()
    with db() as conn:
        if not cid:
            row = conn.execute(
                "SELECT id FROM customers WHERE name_norm=? LIMIT 1",
                (_norm(name),)).fetchone()
            cid = row["id"] if row else next_code(conn, "customer", "KH-")
        conn.execute(
            "INSERT INTO customers(id, name, name_norm, email, phone,"
            " national_id, source) VALUES(?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            "  name = excluded.name, name_norm = excluded.name_norm,"
            "  email = CASE WHEN excluded.email <> '' THEN excluded.email ELSE customers.email END,"
            "  phone = CASE WHEN excluded.phone <> '' THEN excluded.phone ELSE customers.phone END,"
            "  national_id = CASE WHEN excluded.national_id <> '' THEN excluded.national_id ELSE customers.national_id END,"
            "  updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')",
            (cid, name, _norm(name), str(cust.get("email") or ""),
             str(cust.get("phone") or ""), str(cust.get("national_id") or ""),
             source))
        pol = cust.get("policy")
        if isinstance(pol, str) and pol.strip():
            row = conn.execute(
                "SELECT id FROM policies WHERE customer_id=? AND product_name=?",
                (cid, pol.strip())).fetchone()
            if row is None:
                pid = next_code(conn, "policy", "POL-")
                conn.execute(
                    "INSERT INTO policies(id, customer_id, product_name, status)"
                    " VALUES(?,?,?,'active')", (pid, cid, pol.strip()))
        claim = cust.get("claim")
        if isinstance(claim, dict) and claim.get("id"):
            handler_row = None
            hname = str(claim.get("handler") or "").strip()
            if hname:
                handler_row = conn.execute(
                    "SELECT id FROM employees WHERE name_norm=? LIMIT 1",
                    (_norm(hname),)).fetchone()
            conn.execute(
                "INSERT INTO claims(id, customer_id, claim_type, claim_group,"
                " status, handler_id) VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET status = excluded.status",
                (str(claim["id"]), cid, str(claim.get("type") or ""),
                 _group_of_claim_id(str(claim["id"])),
                 str(claim.get("status") or "received"),
                 handler_row["id"] if handler_row else None))
    return cid


def _group_of_claim_id(claim_id: str) -> str:
    if "-YT-" in claim_id:
        return "y_te"
    if "-NT-" in claim_id:
        return "nhan_tho"
    return "xe"


# ---------------------------------------------------------------- claims
def create_claim(customer_id: str, claim_group: str = "xe",
                 claim_type: str = "car_accident", status: str = "received",
                 incident_at: str = "", location: str = "", description: str = "",
                 injury: str = "", handler_id: str | None = None,
                 ticket_id: str | None = None, policy_id: str | None = None,
                 data: dict | None = None,
                 actor_kind: str = "ai", actor_id: str = "",
                 note: str = "") -> str:
    ddmm = time.strftime("%d%m")
    code = _GROUP_CODE.get(claim_group, "XE")
    with db() as conn:
        cid = next_code(conn, f"claim:{code}:{ddmm}", f"CL-{code}-{ddmm}-", 3)
        conn.execute(
            "INSERT INTO claims(id, customer_id, policy_id, claim_type,"
            " claim_group, status, incident_at, location, description, injury,"
            " handler_id, ticket_id, data_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, customer_id, policy_id, claim_type, claim_group, status,
             incident_at, location, description, injury, handler_id, ticket_id,
             json.dumps(data or {}, ensure_ascii=False)))
        record_history(conn, "claim", cid, status, "", actor_kind, actor_id,
                       note or f"Mở hồ sơ claim ({claim_group})")
    return cid


def set_claim_status(claim_id: str, to_status: str, actor_kind: str = "system",
                     actor_id: str = "", note: str = "",
                     amount_approved_vnd: int | None = None) -> bool:
    with db() as conn:
        row = conn.execute("SELECT status FROM claims WHERE id=?",
                           (claim_id,)).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE claims SET status=?, amount_approved_vnd="
            " COALESCE(?, amount_approved_vnd),"
            " updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (to_status, amount_approved_vnd, claim_id))
        record_history(conn, "claim", claim_id, to_status, row["status"],
                       actor_kind, actor_id, note)
    return True


def update_claim(claim_id: str, **cols) -> None:
    allowed = {"handler_id", "policy_id", "run_id", "incident_at", "location",
               "description", "injury", "amount_claimed_vnd", "data_json"}
    sets = {k: v for k, v in cols.items() if k in allowed}
    if not sets:
        return
    with db() as conn:
        frag = ", ".join(f"{k}=?" for k in sets)
        conn.execute(
            f"UPDATE claims SET {frag},"
            " updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (*sets.values(), claim_id))


# ---------------------------------------------------------------- policies
def create_policy(customer_id: str, product_name: str, status: str = "draft",
                  policy_no: str | None = None, data: dict | None = None,
                  actor_kind: str = "ai", note: str = "") -> str:
    with db() as conn:
        pid = next_code(conn, "policy", "POL-")
        conn.execute(
            "INSERT INTO policies(id, policy_no, customer_id, product_name,"
            " status, data_json) VALUES(?,?,?,?,?,?)",
            (pid, policy_no, customer_id, product_name, status,
             json.dumps(data or {}, ensure_ascii=False)))
        record_history(conn, "policy", pid, status, "", actor_kind, "", note)
    return pid


def set_policy_status(policy_id: str, to_status: str, actor_kind: str = "system",
                      actor_id: str = "", note: str = "",
                      signed_at: str | None = None) -> bool:
    with db() as conn:
        row = conn.execute("SELECT status FROM policies WHERE id=?",
                           (policy_id,)).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE policies SET status=?, signed_at=COALESCE(?, signed_at),"
            " updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (to_status, signed_at, policy_id))
        record_history(conn, "policy", policy_id, to_status, row["status"],
                       actor_kind, actor_id, note)
    return True


def merge_policy_data(policy_id: str, patch: dict) -> None:
    with db() as conn:
        row = conn.execute("SELECT data_json FROM policies WHERE id=?",
                           (policy_id,)).fetchone()
        if row is None:
            return
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        data.update({k: v for k, v in patch.items() if v not in (None, "")})
        conn.execute(
            "UPDATE policies SET data_json=?,"
            " updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (json.dumps(data, ensure_ascii=False), policy_id))


def find_policy(customer_id: str = "", policy_no: str = "") -> dict | None:
    with db() as conn:
        if policy_no:
            r = conn.execute("SELECT * FROM policies WHERE policy_no=?",
                             (policy_no,)).fetchone()
            if r:
                return dict(r)
        if customer_id:
            r = conn.execute(
                "SELECT * FROM policies WHERE customer_id=?"
                " ORDER BY created_at DESC LIMIT 1", (customer_id,)).fetchone()
            if r:
                return dict(r)
    return None


# ---------------------------------------------------------------- interactions & documents
def add_interaction(kind: str, customer_id: str | None = None,
                    claim_id: str | None = None, policy_id: str | None = None,
                    channel_ref: str = "", transcript: str = "",
                    summary: str = "", recording_url: str = "",
                    started_at: str | None = None, ended_at: str | None = None,
                    data: dict | None = None) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO interactions(kind, customer_id, claim_id, policy_id,"
            " channel_ref, transcript, summary, recording_url, started_at,"
            " ended_at, data_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (kind, customer_id, claim_id, policy_id, channel_ref, transcript,
             summary, recording_url, started_at, ended_at,
             json.dumps(data or {}, ensure_ascii=False)))
        return int(cur.lastrowid)


def add_document(kind: str, path: str, owner_kind: str, owner_id: str,
                 url: str = "", mime: str = "", size_bytes: int | None = None,
                 label: str = "") -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO documents(kind, path, url, mime, size_bytes,"
            " owner_kind, owner_id, label) VALUES(?,?,?,?,?,?,?,?)",
            (kind, path, url, mime, size_bytes, owner_kind, str(owner_id), label))
        return int(cur.lastrowid)


# ---------------------------------------------------------------- list/360 (UI)
def list_customers(limit: int = 100) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT c.*,"
            " (SELECT COUNT(*) FROM policies p WHERE p.customer_id=c.id) AS n_policies,"
            " (SELECT COUNT(*) FROM claims cl WHERE cl.customer_id=c.id) AS n_claims"
            " FROM customers c ORDER BY c.created_at DESC LIMIT ?", (limit,))]


def list_policies(limit: int = 100) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT p.*, c.name AS customer_name FROM policies p"
            " JOIN customers c ON c.id = p.customer_id"
            " ORDER BY p.created_at DESC LIMIT ?", (limit,))]


def list_claims(limit: int = 100) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT cl.*, c.name AS customer_name, e.name AS handler_name"
            " FROM claims cl JOIN customers c ON c.id = cl.customer_id"
            " LEFT JOIN employees e ON e.id = cl.handler_id"
            " ORDER BY cl.updated_at DESC LIMIT ?", (limit,))]


def customer_360(customer_id: str) -> dict | None:
    with db() as conn:
        c = conn.execute("SELECT * FROM customers WHERE id=?",
                         (customer_id,)).fetchone()
        if c is None:
            return None
        return {
            "customer": dict(c),
            "policies": [dict(r) for r in conn.execute(
                "SELECT * FROM policies WHERE customer_id=?"
                " ORDER BY created_at DESC", (customer_id,))],
            "claims": [dict(r) for r in conn.execute(
                "SELECT cl.*, e.name AS handler_name FROM claims cl"
                " LEFT JOIN employees e ON e.id = cl.handler_id"
                " WHERE cl.customer_id=? ORDER BY cl.created_at DESC",
                (customer_id,))],
            "assets": [dict(r) for r in conn.execute(
                "SELECT * FROM insured_assets WHERE customer_id=?",
                (customer_id,))],
            "interactions": [dict(r) for r in conn.execute(
                "SELECT * FROM interactions WHERE customer_id=?"
                " ORDER BY created_at DESC LIMIT 10", (customer_id,))],
            "documents": [dict(r) for r in conn.execute(
                "SELECT * FROM documents WHERE owner_kind='customer'"
                " AND owner_id=? ORDER BY created_at DESC LIMIT 20",
                (customer_id,))],
            "history": [dict(r) for r in conn.execute(
                "SELECT h.* FROM status_history h WHERE"
                " (h.entity_kind='claim' AND h.entity_id IN"
                "   (SELECT id FROM claims WHERE customer_id=?))"
                " OR (h.entity_kind='policy' AND h.entity_id IN"
                "   (SELECT id FROM policies WHERE customer_id=?))"
                " ORDER BY h.created_at DESC LIMIT 30",
                (customer_id, customer_id))],
        }
