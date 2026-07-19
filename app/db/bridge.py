"""Cầu nối duy nhất giữa core cũ (in-memory) và DB E12 — mọi ghi đều
fire-and-forget, lỗi DB không bao giờ được chặn demo (degrade sạch).

- install(ticket_store): hydrate seq + console từ DB, gắn listener bền hoá ticket.
- after_flow_action(engine, intent, res): sau khi tổng đài fire action —
  upsert khách, mở claim / bổ sung hợp đồng, link ticket, ghi quyết định AI.
- record_interaction(engine): 1 row interactions mỗi cuộc gọi lúc hangup.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db.database import db, record_history, run_db
from app.db.dal import crm as dal_crm
from app.db.dal import tickets as dal_tickets

_installed = False


# ---------------------------------------------------------------- install
def install(ticket_store) -> None:
    """Gọi 1 lần trong lifespan, SAU migrate+seed."""
    global _installed
    if _installed:
        return
    _installed = True
    try:
        ticket_store._seq = max(ticket_store._seq, dal_tickets.max_seq())
        if not ticket_store.tickets:
            ticket_store.tickets.extend(dal_tickets.recent_payloads(50))
    except Exception:  # noqa: BLE001
        pass
    ticket_store.listeners.append(_on_ticket)


def _on_ticket(kind: str, data: dict) -> None:
    """Listener của TicketStore._emit — chạy giữa execute_action, phải rẻ."""
    if kind != "ticket":
        return
    payload = dict(data)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_db(dal_tickets.insert_from_dict, payload))
    except RuntimeError:                       # ngữ cảnh sync (test/script)
        try:
            dal_tickets.insert_from_dict(payload)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- telephony hooks
async def after_flow_action(engine, intent, res: dict) -> None:
    """Hook sau fire_flow_action (E10) — gom dữ liệu trên loop, ghi trong thread."""
    try:
        snap = {
            "pack_id": engine.pack.id,
            "sid": engine.sid,
            "intent_id": getattr(intent, "id", ""),
            "intent_label": getattr(intent, "label", ""),
            "action_id": getattr(intent, "action", ""),
            "workflow": getattr(intent, "workflow", ""),
            "ticket": dict(res.get("ticket") or {}),
            "pdf_url": str(res.get("pdf_url") or ""),
            "fields": engine.store.snapshot(),
            "cust": dict(engine.cust) if engine.cust else None,
            "verified": bool(engine.verified),
            "handler": dict(engine.handler) if engine.handler else None,
            "transcript": engine._dialogue_text(),
            "recording_url": str(getattr(engine, "recording_url", "") or ""),
        }
        customer_id = await run_db(_after_flow_action_sync, snap)
        # E12: intent gắn workflow → khởi động run SAU khi khách đã vào DB
        # (fire-and-forget, cuộc gọi không chờ — zero độ trễ thêm)
        if snap["workflow"]:
            from app.workflow.runner import runner
            cust = dict(snap["cust"] or {})
            if customer_id:
                cust.setdefault("id", customer_id)
                cust.setdefault("name", str(snap["fields"].get("ho_ten") or ""))
            await runner.start(snap["workflow"], {
                "fields": snap["fields"], "customer": cust or None,
                "verified": snap["verified"], "ticket": snap["ticket"],
                "transcript": snap["transcript"],
                "recording_url": snap["recording_url"],
                "claim_group": "xe",
            }, channel="call")
    except Exception:  # noqa: BLE001
        pass


def _after_flow_action_sync(s: dict) -> str:
    fields: dict = s["fields"]
    ticket_id = str(s["ticket"].get("id") or "")

    # 1) khách hàng: từ hồ sơ CRM hoặc dựng mới từ lời khai trong cuộc gọi
    customer_id = ""
    if s["cust"]:
        src = "notify_import" if s["cust"].get("id") else "call"
        customer_id = dal_crm.upsert_customer_legacy(s["cust"], source=src)
    elif str(fields.get("ho_ten") or "").strip():
        customer_id = dal_crm.upsert_customer_legacy(
            {"name": str(fields["ho_ten"])}, source="call")

    # 2) quyết định AI của tổng đài — vào Decision Feed
    with db() as conn:
        record_history(
            conn, "call", s["sid"], f"intent:{s['intent_id']}",
            actor_kind="ai",
            note=f"Định tuyến cuộc gọi → {s['intent_label'] or s['intent_id']}"
                 f" · action {s['action_id']} · ticket {ticket_id or '—'}")

    claim_id = None
    action = s["action_id"]
    if s.get("workflow"):
        # workflow sẽ tự mở claim/policy (tránh tạo đúp) — chỉ link ticket
        if ticket_id:
            dal_tickets.link_ticket(ticket_id, customer_id or None)
            if s["pdf_url"]:
                dal_crm.add_document(
                    kind="pdf", path=f"out/{Path(s['pdf_url']).name}",
                    url=s["pdf_url"], owner_kind="ticket", owner_id=ticket_id,
                    label=s["ticket"].get("action_label") or "")
        return customer_id
    if action == "SUBMIT_CALLCENTER_CLAIM" and customer_id:
        handler_id = _employee_id_by_name(
            (s["handler"] or {}).get("name") or "")
        claim_id = dal_crm.create_claim(
            customer_id=customer_id, claim_group="xe",
            claim_type="car_accident", status="received",
            incident_at=str(fields.get("thoi_diem") or ""),
            location=str(fields.get("vi_tri") or ""),
            description=str(fields.get("mo_ta_thiet_hai") or ""),
            injury=str(fields.get("thuong_tich") or ""),
            handler_id=handler_id, ticket_id=ticket_id or None,
            data=fields, actor_kind="ai",
            note=f"Claim mở từ cuộc gọi {s['sid']} (ticket {ticket_id})")
    elif action == "SUBMIT_CONTRACT_UPDATE" and customer_id:
        pol = dal_crm.find_policy(
            customer_id=customer_id,
            policy_no=str(fields.get("so_gcn") or ""))
        if pol:
            dal_crm.merge_policy_data(pol["id"], fields)
            with db() as conn:
                record_history(
                    conn, "policy", pol["id"], pol["status"], pol["status"],
                    actor_kind="ai",
                    note=f"Bổ sung hồ sơ hợp đồng qua cuộc gọi {s['sid']}"
                         f" ({len(fields)} field)")
        else:
            dal_crm.create_policy(
                customer_id=customer_id,
                product_name=str(fields.get("san_pham") or "hợp đồng bảo hiểm"),
                status="pending_review", data=fields, actor_kind="ai",
                note=f"Hợp đồng nháp từ cuộc gọi {s['sid']}")

    # 3) link ticket + tài liệu PDF
    if ticket_id:
        dal_tickets.link_ticket(ticket_id, customer_id or None, claim_id)
        if s["pdf_url"]:
            dal_crm.add_document(
                kind="pdf", path=f"out/{Path(s['pdf_url']).name}",
                url=s["pdf_url"], owner_kind="ticket", owner_id=ticket_id,
                label=s["ticket"].get("action_label") or "")
    return customer_id


def _employee_id_by_name(name: str) -> str | None:
    if not name.strip():
        return None
    from app.core.triggers import normalize_vi
    with db() as conn:
        r = conn.execute("SELECT id FROM employees WHERE name_norm=? LIMIT 1",
                         (normalize_vi(name),)).fetchone()
        return r["id"] if r else None


async def record_interaction(engine) -> None:
    """Hook trong hangup_done — mỗi cuộc gọi đúng 1 row interactions."""
    try:
        elapsed = max(0.0, time.monotonic() - engine.t0)
        started = datetime.now(timezone.utc) - timedelta(seconds=elapsed)
        snap = {
            "sid": engine.sid,
            "direction": getattr(engine, "direction", "out"),
            "mode": engine.mode,
            "cust_id": (engine.cust or {}).get("id") or None,
            "cust_name": (engine.cust or {}).get("name") or "",
            "transcript": engine._dialogue_text(),
            "recording_url": str(getattr(engine, "recording_url", "") or ""),
            "ticket_id": str((engine.result.get("ticket") or {}).get("id") or ""),
            "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hungup": bool(engine.result.get("hungup")),
        }
        await run_db(_record_interaction_sync, snap)
    except Exception:  # noqa: BLE001
        pass


def _record_interaction_sync(s: dict) -> None:
    claim_id = None
    if s["ticket_id"]:
        with db() as conn:
            r = conn.execute("SELECT id FROM claims WHERE ticket_id=?",
                             (s["ticket_id"],)).fetchone()
            claim_id = r["id"] if r else None
    customer_id = s["cust_id"]
    if customer_id:                            # chỉ link khi row tồn tại (FK)
        if dal_crm.get_customer(customer_id) is None:
            customer_id = None
    iid = dal_crm.add_interaction(
        kind="call_in" if s["direction"] == "in" else "call_out",
        customer_id=customer_id, claim_id=claim_id,
        channel_ref=s["sid"], transcript=s["transcript"],
        summary=f"Cuộc gọi {s['mode']}"
                f"{' (khách cúp máy)' if s['hungup'] else ''}"
                f"{' — ' + s['cust_name'] if s['cust_name'] else ''}",
        recording_url=s["recording_url"], started_at=s["started_at"],
        ended_at=None, data={"mode": s["mode"], "ticket": s["ticket_id"]})
    wav = Path(__file__).resolve().parent.parent.parent / "out" / "recordings" / f"{s['sid']}.wav"
    if wav.exists():
        dal_crm.add_document(
            kind="recording", path=f"out/recordings/{wav.name}",
            url=s["recording_url"] or f"/rec/{s['sid']}",
            owner_kind="interaction", owner_id=str(iid),
            size_bytes=wav.stat().st_size, label="Ghi âm cuộc gọi")
