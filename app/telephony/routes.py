"""Routes E8 — outbound agent call: REST start, webhook Twilio, WS transports,
WS monitor cho trang /call. Registry CALLS in-memory (như SESSIONS batch)."""
from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import JSONResponse, Response

from app.batch.routes import PACKS
from app.config import settings
from app.telephony import transports, tts, twilio_client
from app.telephony.engine import CallEngine

router = APIRouter()
CALLS: dict[str, CallEngine] = {}

_DEFAULT_PACK = "insurance_contract"


def _script_texts(pack) -> list[str]:
    if pack.call_script is not None:
        sc = pack.call_script
        return ([sc.greeting, sc.closing, sc.closing_partial]
                + [s.ask for s in sc.steps] + [s.reask for s in sc.steps])
    fl = pack.call_flows
    out = [fl.greeting, fl.lookup_wait, fl.lookup_miss, fl.menu_prompt,
           fl.unknown_intent, fl.ask_more, fl.closing] + list(tts.FILLERS)
    for s in fl.identify:
        out += [s.ask, s.reask]
    for it in fl.intents:
        out.append(it.empathy)
        for s in it.steps:
            out += [s.ask, s.reask]
    return [t for t in out if t]


async def _janitor(engine: CallEngine) -> None:
    await engine.done.wait()
    await asyncio.sleep(60)          # giữ monitor đọc nốt sự kiện cuối
    await engine.shutdown()
    CALLS.pop(engine.sid, None)


@router.post("/call/start")
async def call_start(payload: dict):
    mode = str(payload.get("mode", "replay"))
    phone = str(payload.get("phone", "")).strip()
    pack = PACKS.get(str(payload.get("pack", _DEFAULT_PACK)))
    if pack is None or (pack.call_script is None and pack.call_flows is None):
        return JSONResponse({"error": "thiếu pack kịch bản"}, status_code=500)
    if mode not in ("twilio", "browser", "replay"):
        return JSONResponse({"error": f"mode lạ: {mode}"}, status_code=400)
    if mode == "twilio":
        if not settings.twilio_ready:
            return JSONResponse(
                {"error": "Twilio chưa cấu hình (TWILIO_ACCOUNT_SID/AUTH_TOKEN/"
                          "FROM_NUMBER + PUBLIC_BASE_URL)",
                 "hint": "dùng mode 'browser' hoặc 'replay'"}, status_code=400)
        if not phone.startswith("+"):
            return JSONResponse({"error": "số điện thoại cần dạng E.164 (+84…)"},
                                status_code=400)

    sid = secrets.token_hex(8)
    engine = CallEngine(
        sid, pack, mode,
        customer_email=str(payload.get("customer_email", "")).strip(),
        handler_email=str(payload.get("handler_email", "")).strip(),
    )
    CALLS[sid] = engine
    engine._tasks.append(asyncio.create_task(engine.broadcast_loop()))
    asyncio.create_task(_janitor(engine))
    asyncio.create_task(tts.prewarm(
        _script_texts(pack), "twilio" if mode == "twilio" else "browser"))
    engine.emit_state("starting", f"mode {mode}")

    if mode == "twilio":
        try:
            engine.call_sid = await twilio_client.start_call(sid, phone,
                                                             engine.client)
            engine.emit_state("dialing", twilio_client.mask_phone(phone))
        except Exception as exc:  # noqa: BLE001
            engine.emit_state("failed", "Twilio không tạo được cuộc gọi")
            engine.done.set()
            return JSONResponse({"error": f"Twilio: {str(exc)[:150]}"},
                                status_code=502)
    elif mode == "replay":
        rt = transports.ReplayTransport(
            engine, transports.REPLAY_ANSWERS.get(pack.id, []))
        engine._tasks.append(asyncio.create_task(rt.run()))
    return {"sid": sid, "mode": mode, "pack": pack.id}


@router.post("/call/end")
async def call_end(payload: dict):
    engine = CALLS.get(str(payload.get("sid", "")))
    if engine is None:
        return JSONResponse({"error": "không có phiên"}, status_code=404)
    engine.agent.signal_hangup()
    return {"ok": True}


# ---------------- Twilio webhooks ----------------
@router.api_route("/telephony/twiml", methods=["GET", "POST"])
async def telephony_twiml(request: Request):
    sid = request.query_params.get("sid", "")
    form = dict((await request.form()).items()) if request.method == "POST" else {}
    path_qs = request.url.path + ("?" + request.url.query if request.url.query else "")
    if not twilio_client.valid_signature(
            path_qs, form, request.headers.get("X-Twilio-Signature")):
        return Response(status_code=403)
    if sid not in CALLS:
        return Response(status_code=404)
    return Response(twilio_client.twiml_connect_stream(sid),
                    media_type="text/xml")


@router.api_route("/telephony/inbound", methods=["GET", "POST"])
async def telephony_inbound(request: Request):
    """Chiều GỌI VÀO số Twilio (trial: phát thông báo xong chạy TwiML luôn,
    KHÔNG cần keypress — né gotcha DTMF chiều gọi ra). Mỗi cuộc inbound dựng
    một CallEngine on-the-fly, stream media như outbound."""
    form = dict((await request.form()).items()) if request.method == "POST" else {}
    path_qs = request.url.path + ("?" + request.url.query if request.url.query else "")
    if not twilio_client.valid_signature(
            path_qs, form, request.headers.get("X-Twilio-Signature")):
        return Response(status_code=403)
    pack = (PACKS.get(request.query_params.get("pack", "insurance_callcenter"))
            or PACKS.get(_DEFAULT_PACK))
    if pack is None or (pack.call_script is None and pack.call_flows is None):
        return Response(status_code=500)
    sid = secrets.token_hex(8)
    engine = CallEngine(sid, pack, "twilio")
    engine.direction = "in"                    # E12: interactions ghi call_in
    engine.call_sid = str(form.get("CallSid", ""))
    CALLS[sid] = engine
    engine._tasks.append(asyncio.create_task(engine.broadcast_loop()))
    asyncio.create_task(_janitor(engine))
    asyncio.create_task(tts.prewarm(_script_texts(pack), "twilio"))
    engine.emit_state(
        "in-progress",
        f"inbound từ {twilio_client.mask_phone(str(form.get('From', '')))}")
    return Response(twilio_client.twiml_connect_stream(sid),
                    media_type="text/xml")


_STATUS_MAP = {"initiated": "dialing", "ringing": "ringing",
               "answered": "in-progress", "in-progress": "in-progress",
               "completed": "ended", "busy": "failed", "failed": "failed",
               "no-answer": "failed", "canceled": "failed"}


@router.post("/telephony/status")
async def telephony_status(request: Request):
    sid = request.query_params.get("sid", "")
    form = dict((await request.form()).items())
    path_qs = request.url.path + ("?" + request.url.query if request.url.query else "")
    if not twilio_client.valid_signature(
            path_qs, form, request.headers.get("X-Twilio-Signature")):
        return Response(status_code=403)
    engine = CALLS.get(sid)
    if engine is not None:
        st = _STATUS_MAP.get(str(form.get("CallStatus", "")), "")
        if st:
            engine.emit_state(st, f"twilio: {form.get('CallStatus')}")
        if form.get("CallStatus") in ("completed", "busy", "failed", "no-answer",
                                      "canceled"):
            engine.agent.signal_hangup()
    return Response(status_code=204)


# ---------------- WebSockets ----------------
@router.websocket("/ws/twilio/{sid}")
async def ws_twilio(ws: WebSocket, sid: str):
    engine = CALLS.get(sid)
    if engine is None:
        await ws.close(code=4404)
        return
    await transports.TwilioTransport(ws, engine).run()


@router.websocket("/ws/call/browser/{sid}")
async def ws_browser(ws: WebSocket, sid: str):
    engine = CALLS.get(sid)
    if engine is None or engine.mode != "browser":
        await ws.close(code=4404)
        return
    await transports.BrowserTransport(ws, engine).run()


@router.get("/call/state/{sid}")
async def call_state(sid: str):
    """Snapshot history event của cuộc gọi (share link / quay demo — E12).
    Trang /call?sid=… render qua fetch này rồi mới bám WS monitor."""
    engine = CALLS.get(sid)
    if engine is None:
        return JSONResponse({"error": "không có phiên"}, status_code=404)
    return {"sid": sid, "events": list(engine.history)}


@router.websocket("/ws/callmon/{sid}")
async def ws_monitor(ws: WebSocket, sid: str):
    engine = CALLS.get(sid)
    if engine is None:
        await ws.close(code=4404)
        return
    await engine.add_monitor(ws)
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
    finally:
        engine.monitors.discard(ws)
