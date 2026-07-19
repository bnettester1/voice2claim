#!/usr/bin/env python3
"""Test S3 — WF1 mở hợp đồng chạy headless cả 2 nhánh trên DB tạm.

Email Brevo được stub (không gửi thật). Không đụng data/app.db.
  .venv/bin/python scripts/test_workflow.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP = tempfile.mkdtemp(prefix="e12wf-")
os.environ["APP_DB_PATH"] = str(Path(_TMP) / "test.db")

PASS = FAIL = 0
SENT: list[dict] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


async def _wait_status(dal_wf, run_id: int, statuses: tuple[str, ...],
                       timeout: float = 30) -> dict:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        run = await asyncio.to_thread(dal_wf.get_run, run_id, False)
        if run and run["status"] in statuses:
            return run
        await asyncio.sleep(0.1)
    raise TimeoutError(f"run {run_id} không tới {statuses} "
                       f"(đang {run and run['status']}/{run and run['current_node']})")


async def main() -> int:
    from app.db import database, seed
    from app.db.dal import crm as dal_crm
    from app.db.dal import erp as dal_erp
    from app.db.dal import workflow as dal_wf
    from app.workflow import wf_mailer
    from app.workflow.seeds import seed_defs
    from app.workflow.runner import complete_task_and_resume, runner

    print(f"WF test tại {os.environ['APP_DB_PATH']}")
    database.migrate()
    seed.run()
    seed_defs()

    async def fake_send(client, to, subject, html, attachments):
        SENT.append({"to": to, "subject": subject,
                     "attachments": len(attachments)})
        return {"to": to, "ok": True, "detail": "stub"}
    wf_mailer._send_one = fake_send            # không gửi Brevo thật

    # ============ Nhánh 1: rủi ro thấp — tự duyệt → ký → phát hành ============
    print("\n[1] WF1 nhánh rủi ro thấp (khách seed, có ảnh, CCCD khớp)")
    run_id = await runner.start("wf_contract_open", {
        "fields": {"ho_ten": "Trần Văn Hùng", "so_cccd": "079090003456",
                   "email": "khach@test.local", "xe_khach": "Toyota Vios 2023",
                   "bien_so_xe": "51F-555.88",
                   "san_pham": "Bảo hiểm vật chất ô tô"},
        "photos": [{"name": "xe1.jpg", "url": "/uploads/xe1.jpg"}],
    }, channel="test")
    run = await _wait_status(dal_wf, run_id, ("waiting_event", "failed"))
    check("chạy tới wait_sign (waiting_event)",
          run["status"] == "waiting_event" and run["current_node"] == "wait_sign",
          f"{run['status']}/{run['current_node']}/{run['error']}")
    ctx = run["context"]
    check("risk_score thấp (<50) — đường tự duyệt",
          (ctx.get("assessment") or {}).get("risk_score", 99) < 50,
          str(ctx.get("assessment")))
    check("đã lập hợp đồng pending_sign + policy_no GCN",
          str(ctx.get("policy_no", "")).startswith("GCN-"), str(ctx.get("policy_no")))
    pdf = ctx.get("contract_doc") or {}
    check("PDF hợp đồng tồn tại", pdf.get("path") and Path(pdf["path"]).exists(),
          str(pdf))
    check("mail ký đã 'gửi' (stub) đúng người nhận",
          any(s["to"] == "khach@test.local" and s["attachments"] == 1
              for s in SENT), str(SENT))
    token = ctx.get("_sign_token", "")
    check("đã mint token ký", bool(token))

    r1 = await runner.resume_token(token, {"signed_name": "Trần Văn Hùng",
                                           "signed_at": "19/07/2026 03:00"})
    check("resume bằng token OK", r1 == run_id, str(r1))
    run = await _wait_status(dal_wf, run_id, ("done", "failed"))
    check("run DONE outcome=issued",
          run["status"] == "done" and run["outcome"] == "issued",
          f"{run['status']}/{run['outcome']}/{run['error']}")
    pol = await asyncio.to_thread(dal_crm.find_policy, "",
                                  run["context"].get("policy_no", ""))
    check("policy ACTIVE trong DB + signed_at",
          pol and pol["status"] == "active" and pol["signed_at"], str(pol))
    r2 = await runner.resume_token(token, {"signed_name": "Ký lần 2"})
    check("double-click link ký = no-op idempotent", r2 is None, str(r2))
    evals = await asyncio.to_thread(
        lambda: __import__("app.db.dal.flywheel", fromlist=["x"]).run_evaluations(run_id))
    check("auto-metrics evaluation đã ghi",
          any(e["rater_kind"] == "auto" for e in evals), str(evals))

    # ============ Nhánh 2: rủi ro cao → thẩm định thủ công → TỪ CHỐI ============
    print("\n[2] WF1 nhánh rủi ro cao (khách lạ, không ảnh) → reject")
    SENT.clear()
    run_id2 = await runner.start("wf_contract_open", {
        "fields": {"ho_ten": "Người Lạ Mặt", "so_cccd": "111222333444",
                   "email": "la@test.local", "xe_khach": "Kia Morning 2015",
                   "bien_so_xe": "29A-111.22"},
    }, channel="test")
    run2 = await _wait_status(dal_wf, run_id2, ("waiting_task", "failed"))
    check("chạy tới human_task thẩm định (waiting_task)",
          run2["status"] == "waiting_task" and run2["current_node"] == "manual",
          f"{run2['status']}/{run2['current_node']}/{run2['error']}")
    check("risk_score cao (>=50)",
          (run2["context"].get("assessment") or {}).get("risk_score", 0) >= 50,
          str(run2["context"].get("assessment")))
    inbox = await asyncio.to_thread(dal_erp.task_inbox, "assessor")
    task = next((t for t in inbox if t["run_id"] == run_id2), None)
    check("task vào hộp việc thẩm định viên", task is not None, str(inbox))
    check("mail giao việc cho thẩm định viên (stub)",
          any("hailongluu" in s["to"] for s in SENT), str(SENT))

    await complete_task_and_resume(task["id"], "rejected",
                                   "Hồ sơ thiếu minh chứng",
                                   {"ghi_chu": "không đạt"}, "NV-01")
    run2 = await _wait_status(dal_wf, run_id2, ("done", "failed"))
    check("run DONE outcome=rejected",
          run2["status"] == "done" and run2["outcome"] == "rejected",
          f"{run2['status']}/{run2['outcome']}/{run2['error']}")
    check("mail từ chối đã 'gửi'",
          any(s["to"] == "la@test.local" for s in SENT), str(SENT))
    check("KHÔNG lập policy ở nhánh reject",
          not run2["context"].get("policy_no"), str(run2["context"].get("policy_no")))

    # ============ Nhánh 3: rủi ro cao → thẩm định DUYỆT → ký → phát hành ======
    print("\n[3] WF1 nhánh thẩm định duyệt (approve)")
    run_id3 = await runner.start("wf_contract_open", {
        "fields": {"ho_ten": "Khách Được Duyệt", "so_cccd": "999888777666",
                   "email": "duyet@test.local", "xe_khach": "Mazda 3 2019",
                   "bien_so_xe": "30G-999.88"},
    }, channel="test")
    run3 = await _wait_status(dal_wf, run_id3, ("waiting_task", "failed"))
    inbox = await asyncio.to_thread(dal_erp.task_inbox, "assessor")
    task3 = next(t for t in inbox if t["run_id"] == run_id3)
    await complete_task_and_resume(task3["id"], "approved", "OK",
                                   {"ghi_chu": "đủ điều kiện"}, "NV-01")
    run3 = await _wait_status(dal_wf, run_id3, ("waiting_event", "failed"))
    check("sau approve → tới wait_sign",
          run3["current_node"] == "wait_sign",
          f"{run3['status']}/{run3['current_node']}/{run3['error']}")
    tok3 = run3["context"].get("_sign_token", "")
    await runner.resume_token(tok3, {"signed_name": "Khách Được Duyệt"})
    run3 = await _wait_status(dal_wf, run_id3, ("done", "failed"))
    check("phát hành sau khi duyệt tay",
          run3["outcome"] == "issued", f"{run3['status']}/{run3['outcome']}")

    # ============ Nhánh 4: WF2 claim — giám định + bóc băng + duyệt chi trả ====
    print("\n[4] WF2 claim: hiện trường → bóc băng (stub) → biên bản → duyệt paid")
    SENT.clear()
    from app.core import valsea as valsea_mod

    async def fake_transcribe(audio, name, client=None):
        return {"text": "Hiện trường xe va chạm nhẹ tại cầu vượt, trầy cản trước,"
                        " ước tính sửa chữa khoảng năm triệu đồng."}
    valsea_mod.transcribe = fake_transcribe    # không gọi VALSEA thật trong test

    wav = Path(_TMP) / "hien_truong.wav"
    wav.write_bytes(b"RIFF0000WAVEfmt ")       # file giả — chỉ cần tồn tại

    run_id4 = await runner.start("wf_claim", {
        "fields": {"ho_ten": "Nguyễn Tiến Tuấn", "vi_tri": "cầu vượt Sóng Thần",
                   "thoi_diem": "sáng nay 8 giờ",
                   "mo_ta_thiet_hai": "va chạm, trầy cản trước"},
        "customer": {"id": "KH-0001", "name": "Nguyễn Tiến Tuấn",
                     "email": "tuan@test.local"},
        "claim_group": "xe", "transcript": "khách báo tai nạn qua tổng đài",
    }, channel="call")
    run4 = await _wait_status(dal_wf, run_id4, ("waiting_task", "failed"))
    check("WF2 tới task giám định hiện trường",
          run4["status"] == "waiting_task" and run4["current_node"] == "dispatch",
          f"{run4['status']}/{run4['current_node']}/{run4['error']}")
    check("claim đã mở investigating",
          str(run4["context"].get("claim_id") or "").startswith("CL-XE-"),
          str(run4["context"].get("claim_id")))
    inbox = await asyncio.to_thread(dal_erp.task_inbox, "assessor")
    t4 = next(t for t in inbox if t["run_id"] == run_id4)
    await complete_task_and_resume(
        t4["id"], "completed", "đã giám định",
        {"thiet_hai_uoc_tinh": 5000000, "ghi_chu": "trầy cản trước",
         "recording": str(wav),
         "files": [{"name": wav.name, "path": str(wav)}]}, "NV-01")
    run4 = await _wait_status(dal_wf, run_id4, ("waiting_task", "failed"))
    check("bóc băng + biên bản xong → tới giám đốc duyệt",
          run4["current_node"] == "director",
          f"{run4['status']}/{run4['current_node']}/{run4['error']}")
    check("transcript bóc băng vào context",
          "cầu vượt" in str((run4["context"].get("report_transcript") or {}).get("text")),
          str(run4["context"].get("report_transcript"))[:80])
    bb = run4["context"].get("bien_ban_doc") or {}
    check("biên bản PDF tồn tại", bb.get("path") and Path(bb["path"]).exists(),
          str(bb))
    check("mail báo khách đã 'gửi'",
          any(s["to"] == "tuan@test.local" and s["attachments"] == 1
              for s in SENT), str(SENT))
    inbox_d = await asyncio.to_thread(dal_erp.task_inbox, "director")
    td = next(t for t in inbox_d if t["run_id"] == run_id4)
    await complete_task_and_resume(td["id"], "approved", "đồng ý chi trả",
                                   {"so_tien": 5000000, "ly_do": "hợp lệ"},
                                   "NV-04")
    run4 = await _wait_status(dal_wf, run_id4, ("done", "failed"))
    check("WF2 DONE outcome=paid",
          run4["status"] == "done" and run4["outcome"] == "paid",
          f"{run4['status']}/{run4['outcome']}/{run4['error']}")
    cl = await asyncio.to_thread(
        lambda: __import__("app.db.dal.crm", fromlist=["x"]).list_claims(10))
    row = next(c for c in cl if c["id"] == run4["context"]["claim_id"])
    check("claim PAID + số tiền duyệt trong DB",
          row["status"] == "paid" and row["amount_approved_vnd"] == 5000000,
          str({k: row[k] for k in ('status', 'amount_approved_vnd')}))

    # ============ Nhánh 5: WF2 giám đốc TỪ CHỐI ============
    print("\n[5] WF2 claim: giám đốc từ chối")
    run_id5 = await runner.start("wf_claim", {
        "fields": {"ho_ten": "Phạm Thị Mai", "vi_tri": "hầm Thủ Thiêm",
                   "thoi_diem": "trưa nay", "mo_ta_thiet_hai": "xe bị cháy khoang máy"},
        "customer": {"id": "KH-0002", "name": "Phạm Thị Mai",
                     "email": "mai@test.local"},
        "claim_group": "xe",
    }, channel="call")
    run5 = await _wait_status(dal_wf, run_id5, ("waiting_task", "failed"))
    check("mức độ nặng (cháy) cộng điểm",
          (run5["context"].get("assessment") or {}).get("risk_score", 0) >= 55,
          str(run5["context"].get("assessment")))
    inbox = await asyncio.to_thread(dal_erp.task_inbox, "assessor")
    t5 = next(t for t in inbox if t["run_id"] == run_id5)
    await complete_task_and_resume(t5["id"], "completed", "",
                                   {"thiet_hai_uoc_tinh": 90000000}, "NV-01")
    run5 = await _wait_status(dal_wf, run_id5, ("waiting_task", "failed"))
    inbox_d = await asyncio.to_thread(dal_erp.task_inbox, "director")
    td5 = next(t for t in inbox_d if t["run_id"] == run_id5)
    await complete_task_and_resume(td5["id"], "rejected",
                                   "nghi ngờ trục lợi, chuyển điều tra",
                                   {"ly_do": "hồ sơ bất thường"}, "NV-04")
    run5 = await _wait_status(dal_wf, run_id5, ("done", "failed"))
    check("WF2 DONE outcome=rejected + claim rejected",
          run5["outcome"] == "rejected",
          f"{run5['status']}/{run5['outcome']}/{run5['error']}")

    print(f"\nKẾT QUẢ: {PASS} PASS / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
