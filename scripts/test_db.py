#!/usr/bin/env python3
"""Test S1 — DB layer E12: adapter legacy, lookup DB-first, bền hoá ticket.

Chạy trên DB tạm (APP_DB_PATH) — không đụng data/app.db thật.
  .venv/bin/python scripts/test_db.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP = tempfile.mkdtemp(prefix="e12db-")
os.environ["APP_DB_PATH"] = str(Path(_TMP) / "test.db")

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def main() -> int:
    from app.db import database, seed
    from app.db.dal import crm as dal_crm
    from app.db.dal import erp as dal_erp
    from app.db.dal import tickets as dal_tickets

    print(f"DB test tại {os.environ['APP_DB_PATH']}")
    database.migrate()
    seed.run()
    seed.run()                                   # idempotent lần 2

    # ---- 1. adapter to_crm_dict giữ nguyên shape legacy (fixture crm.py)
    print("\n[1] to_crm_dict — shape legacy")
    hit = dal_crm.search_customer_legacy("Nguyễn Tiến Tuấn")
    check("tìm thấy KH-0001", bool(hit) and hit["id"] == "KH-0001", str(hit))
    if hit:
        check("policy đúng fixture",
              hit.get("policy") == "bảo hiểm vật chất xe máy", str(hit.get("policy")))
        cl = hit.get("claim") or {}
        check("claim id/status/handler đúng fixture",
              cl.get("id") == "CL-XE-2607-001"
              and cl.get("status") == "investigating"
              and cl.get("handler") == "Lưu Hải Long", str(cl))
        check("national_id đủ để verify_identity",
              hit.get("national_id") == "079095001234")
        from app.telephony.crm import profile_summary, status_reply, verify_identity
        check("verify_identity đuôi CCCD", verify_identity(hit, "1234"))
        check("profile_summary chạy", bool(profile_summary(hit)))
        reply = status_reply("{ten}: {claim_id} {status} — {handler}. {eta}",
                             hit, {"name": "Lưu Hải Long"})
        check("status_reply nói 'đang giám định'", "đang giám định" in reply, reply)

    # ---- 2. lookup DB-first (không cần notify REST)
    print("\n[2] lookup_customer/handler — DB-first")
    from app.telephony import crm as crm_mod

    async def _lookups():
        class _NoClient:                        # REST không được đụng tới
            async def get(self, *a, **k):
                raise AssertionError("REST called — DB-first FAILED")
        c = await crm_mod.lookup_customer("Phạm Thị Mai", _NoClient())
        h = await crm_mod.lookup_handler("y_te", _NoClient())
        h2 = await crm_mod.lookup_handler("nhan_tho", _NoClient())
        return c, h, h2

    cust, handler, handler2 = asyncio.run(_lookups())
    check("KH-0002 từ DB", bool(cust) and cust["id"] == "KH-0002", str(cust))
    check("handler y_te = Trần Kim Phương",
          bool(handler) and handler["name"] == "Trần Kim Phương", str(handler))
    check("handler nhan_tho = Lưu Hải Long (email cũ giữ nguyên)",
          bool(handler2) and handler2["name"] == "Lưu Hải Long"
          and handler2["email"] == "hailongluu@gmail.com", str(handler2))

    # ---- 3. upsert từ dict legacy (REST/call) + không đè bằng rỗng
    print("\n[3] upsert_customer_legacy")
    cid = dal_crm.upsert_customer_legacy(
        {"name": "Đỗ Văn Mới", "phone": "+84900000001",
         "policy": "bảo hiểm nhà tư nhân",
         "claim": {"id": "CL-NT-1907-001", "type": "life",
                   "status": "received", "handler": "Lưu Hải Long"}},
        source="notify_import")
    check("sinh mã KH mới (KH-0005)", cid == "KH-0005", cid)
    dal_crm.upsert_customer_legacy({"id": cid, "name": "Đỗ Văn Mới",
                                    "email": "", "phone": ""})
    row = dal_crm.get_customer(cid)
    check("không đè phone bằng rỗng", row["phone"] == "+84900000001", str(row))
    hit2 = dal_crm.search_customer_legacy("Đỗ Văn Mới")
    check("claim NT import + handler map NV-01",
          (hit2.get("claim") or {}).get("id") == "CL-NT-1907-001"
          and (hit2.get("claim") or {}).get("handler") == "Lưu Hải Long",
          str(hit2))

    # ---- 4. tickets bền hoá + hydrate seq
    print("\n[4] tickets persistence")
    t = {"id": "TCK-0099", "ts": "10:00:00", "action": "TEST", "action_label":
         "Test", "pack": "insurance_callcenter", "pack_icon": "🛡️",
         "priority": "CAO", "status": "webhook 200", "pdf": "/pdf/x.pdf",
         "recording": "", "fields_count": 5,
         "audit": {"score": 90, "arm_ms": 1, "reviewer": "test"}}
    dal_tickets.insert_from_dict(t)
    dal_tickets.insert_from_dict(t)              # idempotent (OR REPLACE)
    check("max_seq đọc 99", dal_tickets.max_seq() == 99,
          str(dal_tickets.max_seq()))
    back = dal_tickets.recent_payloads(5)
    check("payload giữ nguyên dict gốc",
          back and back[0]["id"] == "TCK-0099"
          and back[0]["audit"]["score"] == 90, str(back[:1]))
    dal_tickets.link_ticket("TCK-0099", customer_id="KH-0001")
    rows = dal_tickets.list_tickets(5)
    check("link customer vào ticket", rows[0]["customer_id"] == "KH-0001")

    # ---- 5. bridge listener qua TicketStore thật (ngữ cảnh sync)
    print("\n[5] bridge install + listener")
    from app.core.actions import TicketStore
    from app.db import bridge
    store = TicketStore()
    bridge._installed = False
    bridge.install(store)
    check("hydrate _seq từ DB (99)", store._seq == 99, str(store._seq))
    check("hydrate console từ DB", store.tickets
          and store.tickets[0]["id"] == "TCK-0099")
    nid = store.next_id()
    check("next_id nối tiếp TCK-0100", nid == "TCK-0100", nid)
    store.add({"id": nid, "action": "TEST2", "action_label": "Test 2",
               "pack": "insurance_motor", "pack_icon": "🛡️",
               "priority": "THƯỜNG", "status": "webhook 200", "pdf": "",
               "recording": "", "fields_count": 1})
    check("listener ghi DB (sync path)", dal_tickets.max_seq() == 100,
          str(dal_tickets.max_seq()))

    # ---- 6. claim/policy flow phụ trợ (bridge sẽ dùng)
    print("\n[6] create_claim / policy helpers")
    clid = dal_crm.create_claim("KH-0002", claim_group="xe",
                                incident_at="19/07 09:00", location="Cầu Giấy",
                                description="va chạm nhẹ", ticket_id="TCK-0099",
                                note="test claim")
    check("mã claim đúng format CL-XE-ddmm-001",
          clid.startswith("CL-XE-") and clid.endswith("-001"), clid)
    ok = dal_crm.set_claim_status(clid, "investigating", actor_kind="ai",
                                  note="test chuyển trạng thái")
    check("set_claim_status + history", ok)
    pol = dal_crm.find_policy(policy_no="GCN-2025-104729")
    check("find_policy theo GCN", bool(pol) and pol["customer_id"] == "KH-0003")
    dal_crm.merge_policy_data(pol["id"], {"bien_so_xe": "51F-555.88"})
    pol2 = dal_crm.find_policy(policy_no="GCN-2025-104729")
    check("merge_policy_data", "51F-555.88" in pol2["data_json"])
    inbox = dal_erp.task_inbox(role="assessor")
    check("task_inbox rỗng chạy được", inbox == [], str(inbox))
    tid = dal_erp.create_task("Test task", "assessor_visit", "assessor",
                              claim_id=clid, customer_id="KH-0002")
    inbox = dal_erp.task_inbox(role="assessor")
    check("task vào hàng đợi theo vai", len(inbox) == 1
          and inbox[0]["customer_name"] == "Phạm Thị Mai", str(inbox[:1]))
    done = dal_erp.complete_task(tid, "completed", "xong", {"x": 1})
    check("complete_task idempotent-ready", done["status"] == "done")

    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
