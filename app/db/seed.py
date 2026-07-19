"""Seed idempotent (INSERT OR IGNORE) — chạy mỗi lần khởi động, an toàn lặp.

Dữ liệu khớp fixture cũ trong app/telephony/crm.py + prefill pack
insurance_contract để status_reply/profile_summary đọc y hệt trước E12.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.db.database import REPO_ROOT, db

_EMPLOYEES = [
    # id, name, email, role, claim_groups
    ("NV-01", "Lưu Hải Long", "hailongluu@gmail.com", "assessor", ["xe", "nhan_tho"]),
    ("NV-02", "Trần Kim Phương", "tkphuong132@gmail.com", "assessor", ["y_te"]),
    ("NV-03", "Mai Thị Thanh", "hailongluu@gmail.com", "call_agent", []),
    ("NV-04", "Phạm Quang Dũng", "hailongluu@gmail.com", "director", []),
]

_CUSTOMERS = [
    # id, name, email, phone, national_id
    ("KH-0001", "Nguyễn Tiến Tuấn", "nguyentientuan2052000@gmail.com",
     "+84911961540", "079095001234"),
    ("KH-0002", "Phạm Thị Mai", "", "+84911961540", "079088002345"),
    ("KH-0003", "Trần Văn Hùng", "hailongluu@gmail.com", "+84911961540",
     "079090003456"),
    ("KH-0004", "Vũ Hoàng Nam", "", "+84911961540", "001092004567"),
]

_POLICIES = [
    # id, policy_no, customer, product, status
    ("POL-0001", None, "KH-0001", "bảo hiểm vật chất xe máy", "active"),
    ("POL-0002", None, "KH-0002", "bảo hiểm vật chất ô tô", "active"),
    ("POL-0003", None, "KH-0004", "bảo hiểm sức khỏe", "active"),
    ("POL-0004", "GCN-2025-104729", "KH-0003", "Bảo hiểm vật chất ô tô",
     "pending_review"),
]

_CLAIMS = [
    # id, customer, type, group, status, handler
    ("CL-XE-2607-001", "KH-0001", "motorbike_accident", "xe",
     "investigating", "NV-01"),
    ("CL-XE-2607-002", "KH-0002", "car_accident", "xe",
     "pending_assignment", None),
    ("CL-YT-2607-004", "KH-0004", "health", "y_te", "approved", "NV-02"),
]

_SEQUENCES = {"customer": 4, "policy": 4, "claim:XE:2607": 2, "claim:YT:2607": 4}

# action nền tảng (pack_id='' = global) cho workflow engine dùng từ S3
_PLATFORM_ACTIONS = [
    ("send_email", "send_email", "Gửi email (Brevo)"),
    ("create_task", "create_task", "Giao việc cho nhân sự"),
    ("update_status", "update_status", "Cập nhật trạng thái hồ sơ"),
    ("auto_call", "auto_call", "Tự động gọi điện cho khách"),
    ("wait_event", "wait_event", "Chờ sự kiện (ký/upload)"),
    ("auto_judge", "auto_judge", "Qwen judge async (thử nghiệm)"),
    ("noop", "noop", "Không làm gì"),
]


def _norm(text: str) -> str:
    from app.core.triggers import normalize_vi
    return normalize_vi(text or "")


def run(packs: dict | None = None) -> None:
    with db() as conn:
        for eid, name, email, role, groups in _EMPLOYEES:
            conn.execute(
                "INSERT OR IGNORE INTO employees(id, name, name_norm, email,"
                " role, claim_groups) VALUES(?,?,?,?,?,?)",
                (eid, name, _norm(name), email, role,
                 json.dumps(groups, ensure_ascii=False)))
        for cid, name, email, phone, nid in _CUSTOMERS:
            conn.execute(
                "INSERT OR IGNORE INTO customers(id, name, name_norm, email,"
                " phone, national_id, source) VALUES(?,?,?,?,?,?, 'seed')",
                (cid, name, _norm(name), email, phone, nid))
        for pid, pno, cid, product, status in _POLICIES:
            conn.execute(
                "INSERT OR IGNORE INTO policies(id, policy_no, customer_id,"
                " product_name, status) VALUES(?,?,?,?,?)",
                (pid, pno, cid, product, status))
        conn.execute(
            "INSERT OR IGNORE INTO insured_assets(id, customer_id, policy_id,"
            " kind, make_model) VALUES(1, 'KH-0003', 'POL-0004', 'vehicle',"
            " 'Toyota Vios 2023')")
        for clid, cid, ctype, group, status, handler in _CLAIMS:
            conn.execute(
                "INSERT OR IGNORE INTO claims(id, customer_id, claim_type,"
                " claim_group, status, handler_id) VALUES(?,?,?,?,?,?)",
                (clid, cid, ctype, group, status, handler))
        for name, value in _SEQUENCES.items():
            conn.execute(
                "INSERT OR IGNORE INTO sequences(name, value) VALUES(?,?)",
                (name, value))
        for key, kind, label in _PLATFORM_ACTIONS:
            conn.execute(
                "INSERT OR IGNORE INTO action_catalog(key, pack_id, kind,"
                " label, source) VALUES(?, '', ?, ?, 'seed')",
                (key, kind, label))
        _seed_kb(conn)
    if packs:
        import_pack_actions(packs)


def import_pack_actions(packs: dict) -> None:
    """ActionSpec các pack → action_catalog (kind pdf_ticket). Refresh mỗi
    boot trừ row đã sửa tay (overridden=1) hoặc không còn source pack_import."""
    with db() as conn:
        for pack in packs.values():
            for a in pack.actions:
                cfg = json.dumps(a.model_dump(), ensure_ascii=False)
                conn.execute(
                    "INSERT INTO action_catalog(key, pack_id, kind, label,"
                    " config_json, source) VALUES(?,?,'pdf_ticket',?,?,"
                    " 'pack_import') ON CONFLICT(pack_id, key) DO UPDATE SET"
                    "  label = excluded.label,"
                    "  config_json = excluded.config_json,"
                    "  updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')"
                    " WHERE action_catalog.overridden = 0"
                    "   AND action_catalog.source = 'pack_import'",
                    (a.id, pack.id, a.label, cfg))


def _seed_kb(conn) -> None:
    """Đăng ký 2 file KB gốc làm tài liệu tri thức mẫu (không sửa file)."""
    for fname, summary in (
            ("KB_tainanxe.txt", "Kịch bản gold — quy trình tiếp nhận tai nạn xe"),
            ("KB_khambenh.txt", "Kịch bản gold — quy trình khám bệnh ngoại trú")):
        path = REPO_ROOT / fname
        if not path.exists():
            continue
        sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
        conn.execute(
            "INSERT OR IGNORE INTO kb_documents(filename, mime, kind, path,"
            " size_bytes, sha1, status, summary)"
            " VALUES(?, 'text/plain', 'text', ?, ?, ?, 'uploaded', ?)",
            (fname, fname, path.stat().st_size, sha1, summary))
