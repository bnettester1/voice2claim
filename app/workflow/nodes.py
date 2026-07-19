"""Executor cho từng node type — nhận (node, ctx, deps) → NodeResult.

Quy ước:
- Node chỉ ĐỌC/GHI context qua patch trả về (runner merge + persist).
- Side-effect (pdf/email/task/action/record) phải idempotent-being-guarded:
  runner check step done trước khi chạy lại (crash recovery).
- Mọi quyết định đáng kể ghi status_history actor 'ai' → Decision Feed.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.db.database import db, record_history, run_db
from app.db.dal import crm as dal_crm
from app.db.dal import erp as dal_erp
from app.db.dal import workflow as dal_wf
from app.workflow import assess as assess_mod
from app.workflow import wf_mailer
from app.workflow.defs import NodeDef
from app.workflow.expr import get_path


class NodeError(Exception):
    """Lỗi nghiệp vụ của node — runner set run failed với message này."""


@dataclass
class NodeResult:
    kind: str                       # 'next' | 'wait' | 'end'
    patch: dict = field(default_factory=dict)
    wait_status: str = ""           # 'waiting_event' | 'waiting_task'
    wait_event: str = ""
    outcome: str = ""
    note: str = ""                  # 1 dòng cho Decision Feed (nếu có)


@dataclass
class Deps:
    client: httpx.AsyncClient
    base_url: str
    run_id: int
    step_id: int


def _fields(ctx: dict) -> dict:
    return dict(ctx.get("fields") or {})


def _empty(v) -> bool:
    return v in (None, "", [], {})


def _ai_note(run_id: int, note: str) -> None:
    with db() as conn:
        record_history(conn, "run", str(run_id), "step", "", "ai", "", note)


# ---------------------------------------------------------------- executors
async def n_start(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    expects = node.config.get("expects") or []
    missing = [f for f in expects if _empty(_fields(ctx).get(f))]
    return NodeResult("next", patch={"missing_expected": missing})


async def n_collect_form(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    wanted = node.config.get("fields") or []
    fields = _fields(ctx)
    missing = [f for f in wanted if _empty(fields.get(f))]
    if missing and node.config.get("mode") == "require":
        raise NodeError(f"thiếu field bắt buộc: {', '.join(missing)}")
    if missing and node.config.get("mode") == "task_if_missing":
        task_id = await run_db(
            dal_erp.create_task,
            title=f"Bổ sung hồ sơ: thiếu {', '.join(missing)}",
            task_type="complete_form",
            assignee_role=node.config.get("role", "call_agent"),
            description=node.config.get("title", ""),
            customer_id=(ctx.get("customer") or {}).get("id"),
            run_id=deps.run_id, step_run_id=deps.step_id,
            data={"missing": missing, "out": "fields",
                  "form": [{"name": f, "label": f, "type": "text"}
                           for f in missing]},
            note=f"AI phát hiện phiếu thiếu {len(missing)} field → giao CSR")
        return NodeResult("wait", patch={"missing_fields": missing,
                                         f"_task_{node.id}": task_id},
                          wait_status="waiting_task",
                          wait_event="task.completed",
                          note=f"Chờ CSR bổ sung {len(missing)} field (task #{task_id})")
    return NodeResult("next", patch={"missing_fields": missing})


async def n_crm_lookup(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    from app.telephony import crm
    out = node.config.get("out", "customer")
    query = str(get_path(ctx, node.config.get("query_from", "fields.ho_ten")) or "")
    if not query:
        return NodeResult("next", patch={out: None, "verified": False},
                          note="CRM lookup: không có tên để tra")
    cust = await crm.lookup_customer(query, deps.client)
    tail = str(get_path(ctx, node.config.get("verify_from", "")) or "")
    verified = crm.verify_identity(cust, tail) if (cust and tail) else False
    if cust:
        cid = await run_db(dal_crm.upsert_customer_legacy, dict(cust),
                           "notify_import" if cust.get("id") else "call")
        cust = dict(cust)
        cust.setdefault("id", cid)
    note = (f"Đối chiếu CRM: {'khớp ' + cust['id'] if cust else 'không thấy hồ sơ'}"
            f"{' · CCCD xác thực' if verified else ''}")
    _ai_note(deps.run_id, note)
    return NodeResult("next", patch={out: cust, "verified": verified}, note=note)


async def n_ai_assess(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    out = node.config.get("out", "assessment")
    res = assess_mod.score(ctx, node.config)
    note = (f"AI thẩm định: {res['risk_score']}/100 — "
            + "; ".join(res["reasons"][:3]))
    _ai_note(deps.run_id, note)
    patch = {out: res}
    if node.config.get("second_opinion"):
        try:                # Qwen judge ASYNC (0012) — không chặn/đổi routing
            from app.workflow import judge
            asyncio.create_task(judge.second_opinion(
                deps.run_id, dict(_fields(ctx)), dict(res)))
        except Exception:  # noqa: BLE001
            pass
    return NodeResult("next", patch=patch, note=note)


async def n_branch(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    return NodeResult("next")


async def n_gen_pdf(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    from app.core.actions import render_pdf
    from app.packs.loader import load_pack
    pack = load_pack(node.config.get("pack_id", "insurance_contract"))
    template = node.config.get("template", "form_submission")
    values = _fields(ctx)
    doc_no = str(ctx.get("policy_no")
                 or get_path(ctx, "customer.policy_no")
                 or f"RUN-{deps.run_id}")
    narrative = ""
    src = node.config.get("extra_narrative_from")
    if src:
        narrative = str(get_path(ctx, src) or "")
    path = await asyncio.to_thread(
        render_pdf, pack, template, values, doc_no, narrative,
        {"reviewer": f"Workflow run #{deps.run_id}"})
    url = f"/pdf/{path.name}"
    await run_db(dal_crm.add_document,
                 kind=node.config.get("doc_kind", "contract"),
                 path=f"out/{path.name}", url=url, owner_kind="run",
                 owner_id=str(deps.run_id),
                 label=node.label or template)
    out = node.config.get("out", "document")
    return NodeResult("next",
                      patch={out: {"name": path.name, "path": str(path),
                                   "url": url}},
                      note=f"Soạn tài liệu {path.name}")


def _common_vars(ctx: dict, deps: Deps) -> dict:
    cust = ctx.get("customer") or {}
    fields = _fields(ctx)
    return {
        "name": cust.get("name") or fields.get("ho_ten") or "quý khách",
        "product": fields.get("san_pham") or cust.get("policy")
                   or "hợp đồng bảo hiểm",
        "policy_no": ctx.get("policy_no") or fields.get("so_gcn") or "",
        "risk_score": get_path(ctx, "assessment.risk_score"),
        "ref": ctx.get("claim_id") or ctx.get("policy_no")
               or f"RUN-{deps.run_id}",
        "signed_at": ctx.get("signed_at", ""),
        "amount": get_path(ctx, "director.so_tien"),
        "reason": get_path(ctx, "director.ly_do")
                  or get_path(ctx, "underwriter.ghi_chu") or "",
        "approved": get_path(ctx, "director.decision") == "approve"
                    or get_path(ctx, "underwriter.decision") == "approve",
        "wf_name": ctx.get("_wf_name", "quy trình"),
    }


async def n_send_email(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    cfg = node.config
    patch: dict = {}
    vars = _common_vars(ctx, deps)
    for k, v in (cfg.get("vars") or {}).items():
        vars[k] = get_path(ctx, v[5:]) if (isinstance(v, str)
                                           and v.startswith("path:")) else v
    for link in cfg.get("links") or []:
        kind = link.get("kind")
        if kind == "sign":
            token = await run_db(dal_wf.mint_token, "esign.signed", deps.run_id)
            patch["_sign_token"] = token
            vars["sign_url"] = f"{deps.base_url}/sign/{token}"
        elif kind == "rate":
            token = await run_db(dal_wf.mint_token, "rating", deps.run_id)
            patch["_rate_token"] = token
            vars["rate_url"] = f"{deps.base_url}/rate/{token}"
        elif kind == "task":
            vars["task_url"] = f"{deps.base_url}/tasks"
    attach_paths = []
    for src in cfg.get("attach") or []:
        doc = get_path(ctx, src)
        if isinstance(doc, dict) and doc.get("path"):
            attach_paths.append(doc["path"])
    to = wf_mailer.resolve_to(ctx, cfg.get("to", "customer.email"))
    if to and "example.com" in to:
        to = "hailongluu@gmail.com"            # demo inbox (pattern engine cũ)
    status = await wf_mailer.send(deps.client, cfg.get("template_id", ""),
                                  to, vars, attach_paths)
    mails = list(ctx.get("mails") or [])
    mails.append({"node": node.id, "template": cfg.get("template_id"),
                  **status})
    patch["mails"] = mails
    note = (f"Gửi email '{cfg.get('template_id')}' → {status.get('to')}"
            f" — {'OK' if status.get('ok') else status.get('detail', 'lỗi')}")
    _ai_note(deps.run_id, note)
    return NodeResult("next", patch=patch, note=note)


async def n_wait_event(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    event = node.config.get("event", "custom")
    patch = {}
    if event == "esign.signed" and not ctx.get("_sign_token"):
        token = await run_db(dal_wf.mint_token, event, deps.run_id)
        patch["_sign_token"] = token
    return NodeResult("wait", patch=patch, wait_status="waiting_event",
                      wait_event=event,
                      note=f"Chờ sự kiện {event}")


async def n_human_task(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    cfg = node.config
    cust = ctx.get("customer") or {}
    ref = ctx.get("claim_id") or ctx.get("policy_no") or f"RUN-{deps.run_id}"
    title = cfg.get("title", node.label or "Xử lý hồ sơ")
    task_type = {"assessor": "assessor_visit", "director": "director_approval",
                 "tham_dinh_vien": "assessor_visit",
                 "giam_doc": "director_approval"}.get(
                     cfg.get("role", ""), cfg.get("task_type", "other"))
    role = {"tham_dinh_vien": "assessor", "giam_doc": "director",
            "csr": "call_agent"}.get(cfg.get("role", ""),
                                     cfg.get("role", "assessor"))
    task_id = await run_db(
        dal_erp.create_task, title=f"{title} — {ref}", task_type=task_type,
        assignee_role=role, description=cfg.get("description", ""),
        priority=str(get_path(ctx, "priority") or "TRUNG BÌNH"),
        customer_id=cust.get("id"), claim_id=ctx.get("claim_id"),
        policy_id=ctx.get("policy_id"), run_id=deps.run_id,
        step_run_id=deps.step_id,
        data={"form": cfg.get("form") or [], "decision": cfg.get("decision"),
              "uploads": bool(cfg.get("uploads")), "out": cfg.get("out", "task"),
              "context_excerpt": {
                  "khach": cust.get("name"),
                  "fields": {k: v for k, v in _fields(ctx).items() if v}}},
        note=f"AI giao việc '{title}' cho vai {role}")
    if cfg.get("notify", True):
        emp = await run_db(dal_erp.employees_by_role, role)
        if emp:
            await wf_mailer.send(
                deps.client, "task_assigned", emp[0]["email"],
                {"assignee": emp[0]["name"], "title": title, "ref": ref,
                 "summary": cfg.get("description", ""),
                 "task_url": f"{deps.base_url}/tasks"})
    note = f"Giao việc '{title}' → vai {role} (task #{task_id})"
    _ai_note(deps.run_id, note)
    return NodeResult("wait", patch={f"_task_{node.id}": task_id},
                      wait_status="waiting_task", wait_event="task.completed",
                      note=note)


async def n_update_record(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    cfg = node.config
    entity = cfg.get("entity", "policies")
    sets = cfg.get("set") or {}
    fields = _fields(ctx)
    patch: dict = {}
    note = ""

    if entity == "policies":
        policy_id = ctx.get("policy_id")
        if not policy_id and cfg.get("insert_if_missing"):
            cust = ctx.get("customer") or {}
            customer_id = cust.get("id")
            if not customer_id:
                customer_id = await run_db(
                    dal_crm.upsert_customer_legacy,
                    {"name": fields.get("ho_ten", "Khách mới"),
                     "email": fields.get("email", ""),
                     "phone": fields.get("so_dien_thoai", ""),
                     "national_id": fields.get("so_cccd", "")}, "call")
                patch["customer"] = {**cust, "id": customer_id,
                                     "name": fields.get("ho_ten", "")}
            policy_no = (fields.get("so_gcn")
                         or f"GCN-{time.strftime('%Y')}-{secrets.randbelow(900000) + 100000}")
            policy_id = await run_db(
                dal_crm.create_policy, customer_id=customer_id,
                product_name=fields.get("san_pham")
                or cfg.get("product", "Bảo hiểm vật chất ô tô"),
                status=sets.get("status", "draft"), policy_no=policy_no,
                data=fields, actor_kind="ai",
                note=f"Workflow run #{deps.run_id} lập hợp đồng")
            patch.update({"policy_id": policy_id, "policy_no": policy_no})
            note = f"Lập hợp đồng {policy_no} ({sets.get('status', 'draft')})"
        elif policy_id and sets.get("status"):
            signed = ctx.get("signed_at") if sets["status"] == "active" else None
            await run_db(dal_crm.set_policy_status, policy_id, sets["status"],
                         "ai", "", f"Workflow run #{deps.run_id}", signed)
            note = f"Hợp đồng {ctx.get('policy_no') or policy_id} → {sets['status']}"

    elif entity == "claims":
        claim_id = ctx.get("claim_id")
        if not claim_id and cfg.get("insert_if_missing"):
            cust = ctx.get("customer") or {}
            customer_id = cust.get("id")
            if not customer_id:
                customer_id = await run_db(
                    dal_crm.upsert_customer_legacy,
                    {"name": fields.get("ho_ten", "Khách mới")}, "call")
            claim_id = await run_db(
                dal_crm.create_claim, customer_id=customer_id,
                claim_group=str(ctx.get("claim_group") or "xe"),
                claim_type=cfg.get("claim_type", "car_accident"),
                status=sets.get("status", "received"),
                incident_at=str(fields.get("thoi_diem") or ""),
                location=str(fields.get("vi_tri") or ""),
                description=str(fields.get("mo_ta_thiet_hai") or ""),
                injury=str(fields.get("thuong_tich") or ""),
                ticket_id=(ctx.get("ticket") or {}).get("id"),
                data=fields, actor_kind="ai",
                note=f"Workflow run #{deps.run_id} mở claim")
            patch["claim_id"] = claim_id
            note = f"Mở hồ sơ claim {claim_id}"
        elif claim_id and sets.get("status"):
            amount = get_path(ctx, "director.so_tien")
            await run_db(dal_crm.set_claim_status, claim_id, sets["status"],
                         "ai", "", f"Workflow run #{deps.run_id}",
                         int(amount) if amount else None)
            note = f"Claim {claim_id} → {sets['status']}"

    elif entity == "customers":
        cid = await run_db(dal_crm.upsert_customer_legacy,
                           {"name": fields.get("ho_ten", ""),
                            "email": fields.get("email", ""),
                            "phone": fields.get("so_dien_thoai", ""),
                            "national_id": fields.get("so_cccd", "")}, "call")
        patch["customer"] = {**(ctx.get("customer") or {}), "id": cid}
        note = f"Cập nhật hồ sơ khách {cid}"

    if note:
        _ai_note(deps.run_id, note)
    return NodeResult("next", patch=patch, note=note)


async def n_fire_action(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    from app.core.actions import execute_action
    from app.core.form_state import FormStore
    from app.packs.loader import load_pack
    pack = load_pack(node.config.get("pack_id", "insurance_callcenter"))
    action = pack.action(node.config.get("action_id", ""))
    if action is None:
        raise NodeError(f"pack không có action '{node.config.get('action_id')}'")
    store = FormStore(pack)
    store.merge({k: {"value": v, "confidence": 1.0, "evidence": "workflow"}
                 for k, v in _fields(ctx).items() if not _empty(v)})
    res = await execute_action(pack, action, store,
                               transcript=str(ctx.get("transcript") or ""),
                               reviewer=f"Workflow run #{deps.run_id}",
                               client=deps.client)
    note = f"Fire action {action.id} → ticket {res['ticket']['id']}"
    _ai_note(deps.run_id, note)
    return NodeResult("next", patch={"ticket": res["ticket"]}, note=note)


async def n_transcribe_media(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    """Bóc băng ghi âm thẩm định bằng VALSEA (off-call, 10-15s chấp nhận được)
    + compose_narrative dựng draft biên bản. Không file/không key → đi tiếp."""
    out = node.config.get("out", "report_transcript")
    src = node.config.get("media_from", "report.recording")
    media = get_path(ctx, src)
    path = media.get("path") if isinstance(media, dict) else media
    if not path or not Path(str(path)).exists():
        note = "Không có băng ghi âm hiện trường — biên bản dùng lời khai gốc"
        _ai_note(deps.run_id, note)
        return NodeResult("next", patch={out: {"text": "", "narrative": ""}},
                          note=note)
    from app.core import valsea
    audio = Path(str(path)).read_bytes()
    text = ""
    try:
        verbose = await valsea.transcribe(audio, Path(str(path)).name,
                                          client=deps.client)
        text = str(verbose.get("text") or "")
    except Exception as exc:  # noqa: BLE001 — degrade: vẫn ra biên bản
        _ai_note(deps.run_id, f"VALSEA transcribe lỗi ({type(exc).__name__})"
                              " — biên bản không kèm bóc băng")
    narrative = ""
    if text and node.config.get("narrative", True):
        try:
            from app.core.actions import compose_narrative
            from app.packs.loader import load_pack
            pack = load_pack(node.config.get("pack_id", "insurance_callcenter"))
            narrative, _ = await compose_narrative(pack, text, _fields(ctx),
                                                   deps.client)
        except Exception:  # noqa: BLE001
            narrative = ""
    if text and not narrative:                 # fallback: đính nguyên văn
        narrative = "Bóc băng hiện trường (VALSEA ASR):\n" + text[:1500]
    note = (f"AI bóc băng hiện trường: {len(text)} ký tự"
            + (" + dựng draft biên bản" if narrative else ""))
    _ai_note(deps.run_id, note)
    return NodeResult("next",
                      patch={out: {"text": text, "narrative": narrative}},
                      note=note)


async def n_auto_call(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    """Workflow tự GỌI ĐIỆN cho khách (NotifyAgent — chỉ thông báo, không action).

    mode: replay (mặc định demo — outbound Twilio trial đang tắc DTMF carrier
    VN, quyết định 0011) | twilio (khi account sẵn sàng + config allow_twilio).
    Ghi âm + interactions row tự có nhờ hook hangup_done của engine.
    """
    from app.config import settings
    from app.packs.loader import load_pack
    from app.telephony import transports
    from app.telephony.agent import NotifyAgent
    from app.telephony.engine import CallEngine
    from app.telephony.routes import CALLS, _janitor

    cfg = node.config
    vars = _common_vars(ctx, deps)
    amount = vars.get("amount")
    if amount:
        try:
            vars["amount"] = f"{int(amount):,}".replace(",", ".")
        except (TypeError, ValueError):
            pass
    lines = []
    for tpl in cfg.get("say") or []:
        line = str(tpl)
        for k, v in vars.items():
            line = line.replace("{" + k + "}", str(v if v is not None else ""))
        lines.append(line)
    if not lines:
        return NodeResult("next", note="auto_call: không có câu nào để đọc")

    mode = cfg.get("mode", "replay")
    if mode == "twilio" and not (settings.twilio_ready
                                 and cfg.get("allow_twilio")):
        mode = "replay"                        # degrade sạch về replay

    import secrets as _secrets
    sid = _secrets.token_hex(8)
    pack = load_pack(cfg.get("pack_id", "insurance_callcenter"))
    engine = CallEngine(sid, pack, "twilio" if mode == "twilio" else "replay")
    engine.agent = NotifyAgent(engine, lines,
                               listen_secs=float(cfg.get("listen_secs", 6)))
    if ctx.get("customer"):
        engine.cust = dict(ctx["customer"])    # interactions link đúng khách
    CALLS[sid] = engine
    engine._tasks.append(asyncio.create_task(engine.broadcast_loop()))
    asyncio.create_task(_janitor(engine))
    if mode == "twilio":
        from app.telephony import twilio_client
        phone = str((ctx.get("customer") or {}).get("phone") or "")
        try:
            engine.call_sid = await twilio_client.start_call(
                sid, phone, engine.client)
        except Exception as exc:  # noqa: BLE001
            _ai_note(deps.run_id, f"Autocall twilio lỗi ({str(exc)[:60]})"
                                  " — chuyển replay")
            mode = "replay"
    if mode == "replay":
        rt = transports.ReplayTransport(
            engine, cfg.get("replay_answers")
            or ["dạ em nhận được rồi, cảm ơn công ty ạ"])
        engine._tasks.append(asyncio.create_task(rt.run()))

    note = (f"Autocall ({mode}) → {vars.get('name')}: "
            f"“{lines[0][:70]}…”")
    _ai_note(deps.run_id, note)
    patch = {"autocall": {"sid": sid, "mode": mode,
                          "monitor": f"/rec/{sid}", "lines": lines}}
    if cfg.get("wait"):
        try:
            await asyncio.wait_for(engine.done.wait(), timeout=180)
            patch["autocall"]["done"] = True
        except asyncio.TimeoutError:
            patch["autocall"]["done"] = False
    return NodeResult("next", patch=patch, note=note)


async def n_end(node: NodeDef, ctx: dict, deps: Deps) -> NodeResult:
    return NodeResult("end", outcome=node.config.get("outcome", "done"))


EXECUTORS = {
    "start": n_start, "collect_form": n_collect_form,
    "crm_lookup": n_crm_lookup, "ai_assess": n_ai_assess, "branch": n_branch,
    "gen_pdf": n_gen_pdf, "send_email": n_send_email,
    "wait_event": n_wait_event, "human_task": n_human_task,
    "transcribe_media": n_transcribe_media, "auto_call": n_auto_call,
    "fire_action": n_fire_action, "update_record": n_update_record,
    "end": n_end,
}
