"""Batch path: upload/ghi âm → VALSEA transcribe → extraction → form + score
→ trigger scan → action executor. Session giữ FormStore server-side."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core import valsea
from app.core.actions import execute_action, ticket_store
from app.core.extraction import extract
from app.core.form_state import FormStore
from app.core.scoring import score_form
from app.core.triggers import TriggerMatcher
from app.packs.loader import ActionSpec, Pack, load_all

router = APIRouter(prefix="/api")

PACKS: dict[str, Pack] = load_all()


RECORD_DIR = Path(__file__).resolve().parent.parent.parent / "out" / "recordings"
RECORD_DIR.mkdir(parents=True, exist_ok=True)

_AUDIO_MIME = {".wav": "audio/wav", ".webm": "audio/webm", ".mp3": "audio/mpeg",
               ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".flac": "audio/flac"}


@dataclass
class Session:
    sid: str
    pack: Pack
    store: FormStore
    matcher: TriggerMatcher
    transcript: str = ""
    verbose: dict = field(default_factory=dict)
    armed: dict = field(default_factory=dict)      # action_id -> {score, latency_ms}
    fired: list = field(default_factory=list)
    review_started: float = 0.0
    agreement: float | None = None                 # NER local (PyTorch) đối chiếu
    ner_verdict: dict = field(default_factory=dict)
    recording_url: str = ""                        # /rec/{sid} — băng ghi âm gốc


SESSIONS: dict[str, Session] = {}

SUBMIT_ACTION = ActionSpec(
    id="FORM_SUBMISSION", label="Gửi hồ sơ", triggers=[],
    confirm="click", template="form_submission",
    tts_confirm="Hồ sơ đã được gửi vào hệ thống thành công.",
)


def _session(sid: str) -> Session:
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "session không tồn tại")
    return s


def _score_payload(s: Session) -> dict:
    return score_form(s.pack, s.store, agreement=s.agreement,
                      ner_verdict=s.ner_verdict).as_dict()


async def _update_agreement(s: Session) -> None:
    """Đối chiếu NER local (PyTorch) — chạy thread, degrade sạch nếu thiếu ML."""
    import asyncio

    from app.core.ml import ner_local

    try:
        ag, verdict = await asyncio.to_thread(
            ner_local.agreement, s.transcript, s.store.snapshot())
        s.agreement, s.ner_verdict = ag, verdict
    except Exception:  # noqa: BLE001
        s.agreement, s.ner_verdict = None, {}


# ---------------------------------------------------------------- pack info
@router.get("/packs")
def list_packs():
    return [{"id": p.id, "name": p.name, "icon": p.icon} for p in PACKS.values()]


@router.get("/pack/{pack_id}")
def pack_schema(pack_id: str):
    p = PACKS.get(pack_id)
    if not p:
        raise HTTPException(404, "pack không tồn tại")
    return p.model_dump()


# ---------------------------------------------------------------- demo audio
DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "audio"
CASES_META = {
    c["id"]: {"title": c["title"], "pack_id": c["pack_id"]}
    for c in json.loads(
        (Path(__file__).resolve().parent.parent.parent / "packs" / "testcases" / "kb_af.json")
        .read_text(encoding="utf-8"))["cases"]
}


@router.get("/demo-audios")
def demo_audios():
    out = []
    for cid, meta in CASES_META.items():
        f = DEMO_DIR / f"{cid}.wav"
        if f.exists():
            out.append({"id": cid, "title": meta["title"], "pack_id": meta["pack_id"],
                        "secs": round(f.stat().st_size / 2 / 16000)})
    return out


# ---------------------------------------------------------------- batch run
@router.post("/batch/{pack_id}")
async def run_batch(pack_id: str, file: UploadFile | None = File(None), demo: str = ""):
    pack = PACKS.get(pack_id)
    if not pack:
        raise HTTPException(404, "pack không tồn tại")
    if demo:
        f = DEMO_DIR / f"{demo.upper()}.wav"
        if not f.exists():
            raise HTTPException(404, "demo audio chưa được sinh")
        audio = f.read_bytes()
        file_name = f.name
    elif file is not None:
        audio = await file.read()
        file_name = file.filename or "audio.webm"
    else:
        raise HTTPException(400, "cần file hoặc ?demo=<id>")
    if len(audio) > 10 * 1024 * 1024:
        raise HTTPException(413, "file quá 10MB")

    t_all = time.monotonic()
    async with httpx.AsyncClient(timeout=180) as client:
        t0 = time.monotonic()
        try:
            verbose = await valsea.transcribe(audio, file_name, client=client)
        except httpx.HTTPStatusError as e:
            raise HTTPException(502, f"VALSEA transcribe lỗi {e.response.status_code}")
        asr_ms = int((time.monotonic() - t0) * 1000)
        from app.core.normalize import apply_itn
        transcript = apply_itn(pack, verbose.get("text") or "")

        t0 = time.monotonic()
        extraction = await extract(pack, transcript, client=client,
                                   semantic_tags=verbose.get("semantic_tags"))
        extract_ms = int((time.monotonic() - t0) * 1000)

        s = Session(
            sid=uuid.uuid4().hex[:12], pack=pack,
            store=FormStore(pack), matcher=TriggerMatcher(pack),
            transcript=transcript, verbose=verbose,
        )
        # lưu băng ghi âm gốc để nghe lại (màn Duyệt + mail người xử lý)
        ext = Path(file_name).suffix.lower() or ".webm"
        if ext not in _AUDIO_MIME:
            ext = ".webm"
        (RECORD_DIR / f"{s.sid}{ext}").write_bytes(audio)
        s.recording_url = f"/rec/{s.sid}"

        s.store.merge(extraction)
        await _update_agreement(s)

        events = s.matcher.scan_full(transcript)
        fired_payloads = []
        for e in events:
            if e.kind == "armed":
                s.armed[e.action.id] = {"score": e.score, "latency_ms": round(e.latency_ms, 1)}
            elif e.kind == "fire":  # action auto (khẩn cấp) chạy ngay
                res = await execute_action(
                    pack, e.action, s.store, transcript=transcript,
                    arm_ms=e.latency_ms, client=client,
                    score=score_form(pack, s.store).total,
                    recording_url=s.recording_url,
                )
                s.fired.append(e.action.id)
                fired_payloads.append(res)

    SESSIONS[s.sid] = s
    return {
        "sid": s.sid,
        "recording_url": s.recording_url,
        "transcript": transcript,
        "raw_transcript": verbose.get("raw_transcript"),
        "detected_languages": verbose.get("detected_languages"),
        "semantic_tags": verbose.get("semantic_tags"),
        "fields": s.store.full_state(),
        "score": _score_payload(s),
        "armed": s.armed,
        "fired": fired_payloads,
        "timing": {"asr_ms": asr_ms, "extract_ms": extract_ms,
                   "total_ms": int((time.monotonic() - t_all) * 1000)},
    }


# (endpoint /baseline đối chứng whisper đã gỡ 18/07 — pilot không dùng Groq)


# ---------------------------------------------------------------- edits
class FieldEdit(BaseModel):
    name: str
    value: object


@router.post("/session/{sid}/field")
async def edit_field(sid: str, body: FieldEdit):
    s = _session(sid)
    if not s.store.set_user(body.name, body.value):
        raise HTTPException(400, "field không tồn tại")
    await _update_agreement(s)
    return {"fields": s.store.full_state(), "score": _score_payload(s)}


@router.post("/session/{sid}/unlock")
def unlock_field(sid: str, body: FieldEdit):
    s = _session(sid)
    s.store.unlock(body.name)
    return {"fields": s.store.full_state(), "score": _score_payload(s)}


@router.post("/session/{sid}/review-start")
def review_start(sid: str):
    s = _session(sid)
    if not s.review_started:
        s.review_started = time.monotonic()
    return {"ok": True}


# ---------------------------------------------------------------- actions & submit
class SubmitBody(BaseModel):
    reviewer: str = "Người duyệt demo"
    ack: bool = False
    override_reason: str = ""
    customer_email: str = ""
    handler_email: str = ""
    base_url: str = ""          # để link trong mail trỏ đúng host người nhận mở được


async def _send_mails(s: Session, res: dict, body: SubmitBody) -> list[dict]:
    """Gửi mail khách + người xử lý qua Brevo (nếu có email + key). Không chặn flow."""
    if not (body.customer_email or body.handler_email):
        return []
    from app.core.mailer import send_ticket_emails

    try:
        statuses = await send_ticket_emails(
            pack=s.pack, ticket=res["ticket"], values=s.store.snapshot(),
            transcript=s.transcript, pdf_url=res.get("pdf_url", ""),
            recording_url=s.recording_url, base_url=body.base_url,
            customer_email=body.customer_email.strip(),
            handler_email=body.handler_email.strip(),
            narrative=res.get("narrative", ""),
            service_log=res.get("service_log"),
        )
    except Exception as e:  # noqa: BLE001
        statuses = [{"to": "-", "ok": False, "detail": f"mailer lỗi: {str(e)[:120]}"}]
    for st in statuses:
        ticket_store.log(
            f"MAIL → {st['to']}: {'✔ đã gửi' if st['ok'] else '✘ ' + st['detail']}",
            "info" if st["ok"] else "warn")
    return statuses


@router.post("/session/{sid}/action/{action_id}")
async def fire_action(sid: str, action_id: str, body: SubmitBody):
    s = _session(sid)
    action = s.pack.action(action_id)
    if not action:
        raise HTTPException(404, "action không tồn tại")
    if action_id not in s.armed and action.confirm == "click":
        raise HTTPException(409, "action chưa được armed bằng giọng nói")
    if action_id in s.fired:
        raise HTTPException(409, "action đã chạy rồi")
    sc = score_form(s.pack, s.store)
    res = await execute_action(
        s.pack, action, s.store, transcript=s.transcript,
        arm_ms=(s.armed.get(action_id) or {}).get("latency_ms"),
        reviewer=body.reviewer, score=sc.total,
        recording_url=s.recording_url,
    )
    s.fired.append(action_id)
    res["mail"] = await _send_mails(s, res, body)
    return res


@router.post("/session/{sid}/submit")
async def submit_form(sid: str, body: SubmitBody):
    s = _session(sid)
    sc = score_form(s.pack, s.store)
    if not sc.can_submit and not body.override_reason:
        raise HTTPException(409, f"score {sc.total} < 60 — cần sửa hoặc override có lý do")
    if sc.needs_ack and not body.ack and not body.override_reason:
        raise HTTPException(409, "score 60-84 — cần tick 'tôi đã đọc lại'")
    review_secs = int(time.monotonic() - s.review_started) if s.review_started else None
    res = await execute_action(
        s.pack, SUBMIT_ACTION, s.store, transcript=s.transcript,
        reviewer=body.reviewer, score=sc.total,
        recording_url=s.recording_url,
    )
    res["review_secs"] = review_secs
    if body.override_reason:
        ticket_store.log(f"OVERRIDE gửi form score={sc.total}: {body.override_reason}", "warn")
    res["mail"] = await _send_mails(s, res, body)
    return res


# ---------------------------------------------------------------- recording
def find_recording(sid: str) -> tuple[Path, str] | None:
    for p in RECORD_DIR.glob(f"{sid}.*"):
        return p, _AUDIO_MIME.get(p.suffix.lower(), "application/octet-stream")
    return None


# ---------------------------------------------------------------- replay
REPLAY_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "replay"


@router.get("/replay-list")
def replay_list():
    if not REPLAY_DIR.exists():
        return []
    return sorted(p.stem for p in REPLAY_DIR.glob("*.json"))


@router.get("/replay/{case_id}")
def replay_file(case_id: str):
    f = REPLAY_DIR / f"{case_id.upper()}.json"
    if not f.exists():
        raise HTTPException(404, "chưa có bản ghi replay — chạy scripts/test_live.py --record")
    return json.loads(f.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- console
@router.get("/tickets")
def tickets():
    return {"tickets": ticket_store.tickets, "logs": ticket_store.logs}
