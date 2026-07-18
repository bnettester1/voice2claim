"""CallEngine — lõi cuộc gọi outbound (E8), transport-agnostic, KHÔNG LLM ngoài.

transport (twilio/browser/replay) ──PCM16 16k──▶ audio_q ──▶ VALSEA RTT
VALSEA final (correction + ITN pack) ──▶ dialogue + ScriptedAgent.inbox
agent.say ──▶ tts.synth (VALSEA ưu tiên → ElevenLabs) ──▶ transport.play
collect(field, heard) ──▶ parse_vi rule thuần theo field kịch bản ──▶ FormStore
đủ required ──▶ execute_action (ticket + PDF) ──▶ hangup
UI theo dõi qua monitor WS (/ws/callmon/{sid}) — chỉ đọc.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

import httpx
import numpy as np
import websockets
from fastapi import WebSocket

from app.config import settings
from app.core.actions import execute_action
from app.core.form_state import FieldState, FormStore, _empty
from app.core.normalize import apply_itn
from app.core.scoring import score_form
from app.packs.loader import Pack
from app.telephony import parse_vi, tts
from app.telephony.agent import ScriptedAgent

COMMIT = "__COMMIT__"


class _RmsVad:
    """Fallback end-of-speech khi thiếu silero (PyTorch): RMS + im lặng 800ms."""

    def __init__(self, sr: int = 16000, thr: int = 500):
        self.thr = thr
        self.frame_ms = 0.0
        self.voiced = False
        self.silence_ms = 0.0
        self.sr = sr

    def feed(self, pcm: bytes) -> bool:
        x = np.frombuffer(pcm, dtype=np.int16)
        if x.size == 0:
            return False
        ms = 1000.0 * x.size / self.sr
        rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
        if rms >= self.thr:
            self.voiced, self.silence_ms = True, 0.0
            return False
        if not self.voiced:
            return False
        self.silence_ms += ms
        if self.silence_ms >= 800:
            self.voiced, self.silence_ms = False, 0.0
            return True
        return False


class CallEngine:
    def __init__(self, sid: str, pack: Pack, mode: str,
                 customer_email: str = "", handler_email: str = ""):
        self.sid, self.pack, self.mode = sid, pack, mode
        self.store = FormStore(pack)
        if pack.call_flows is not None:            # E10: tổng đài đa-workflow
            from app.telephony.flow_agent import FlowAgent
            self.agent: ScriptedAgent = FlowAgent(self)
        else:                                      # E8: kịch bản tĩnh
            self.agent = ScriptedAgent(self)
        self.cust: dict | None = None              # hồ sơ CRM sau lookup
        self.handler: dict | None = None
        self.verified = False
        self.customer_email = customer_email
        self.handler_email = handler_email
        self._wav = None                           # ghi âm khách (PCM16 16k)
        self._wav_done = False
        self.transport = None
        self.monitors: set[WebSocket] = set()
        self.history: list[dict] = []          # replay event cho monitor vào trễ
        self.audio_q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.out_q: asyncio.Queue = asyncio.Queue()
        self.dialogue: list[tuple[str, str]] = []   # ("agent"|"customer", text)
        self.client = httpx.AsyncClient(timeout=90)
        self.up = None
        self.up_ready = asyncio.Event()
        self.closing = False
        self.call_sid: str | None = None       # Twilio Call SID (mode twilio)
        self.t0 = time.monotonic()
        self.done = asyncio.Event()
        self.result: dict = {}
        self._tasks: list[asyncio.Task] = []
        try:
            from app.core.ml.vad import EndOfSpeechDetector
            self.vad = EndOfSpeechDetector()
            if not getattr(self.vad, "enabled", False):
                self.vad = _RmsVad()
        except Exception:  # noqa: BLE001
            self.vad = _RmsVad()
        if pack.prefill:                        # hồ sơ gốc lên form ngay
            self.store.merge({k: {"value": v, "confidence": 1.0,
                                  "evidence": "hồ sơ gốc"}
                              for k, v in pack.prefill.items()})

    # ---------------- monitor ----------------
    def emit(self, obj: dict) -> None:
        self.history.append(obj)
        del self.history[:-80]
        try:
            self.out_q.put_nowait(obj)
        except asyncio.QueueFull:
            pass

    def emit_state(self, state: str, detail: str = "") -> None:
        self.emit({"type": "call.state", "state": state, "detail": detail,
                   "t": round(time.monotonic() - self.t0, 1)})

    def emit_step(self, idx: int, fieldname: str, status: str) -> None:
        self.emit({"type": "call.step", "index": idx, "field": fieldname,
                   "status": status})

    async def add_monitor(self, ws: WebSocket) -> None:
        await ws.accept()
        for ev in self.history:
            try:
                await ws.send_json(ev)
            except Exception:  # noqa: BLE001
                return
        self.monitors.add(ws)

    async def broadcast_loop(self) -> None:
        while True:
            obj = await self.out_q.get()
            dead = []
            for ws in self.monitors:
                try:
                    await ws.send_json(obj)
                except Exception:  # noqa: BLE001
                    dead.append(ws)
            for ws in dead:
                self.monitors.discard(ws)

    # ---------------- audio in ----------------
    @property
    def recording_url(self) -> str:
        return f"/rec/{self.sid}" if self._wav is not None else ""

    def _close_wav(self) -> None:
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:  # noqa: BLE001
                pass
            self._wav = None
            self._wav_done = True

    def _record(self, pcm16k: bytes) -> None:
        """Ghi âm lời khách ra WAV (out/recordings/{sid}.wav — route /rec có sẵn)."""
        if self._wav_done:
            return
        try:
            if self._wav is None:
                import wave

                from app.batch.routes import RECORD_DIR
                self._wav = wave.open(str(RECORD_DIR / f"{self.sid}.wav"), "wb")
                self._wav.setnchannels(1)
                self._wav.setsampwidth(2)
                self._wav.setframerate(16000)
                self.emit({"type": "recording", "url": f"/rec/{self.sid}"})
            self._wav.writeframes(pcm16k)
        except Exception:  # noqa: BLE001
            self._wav = None

    def push_audio(self, pcm16k: bytes) -> None:
        self._record(pcm16k)
        try:
            self.audio_q.put_nowait(pcm16k)
        except asyncio.QueueFull:
            pass
        try:
            if self.vad and self.vad.feed(pcm16k):
                self.audio_q.put_nowait(COMMIT)
        except (asyncio.QueueFull, Exception):  # noqa: BLE001
            pass

    def inject_final(self, text: str) -> None:
        """Replay mode / test: coi như VALSEA đã trả transcript.final."""
        self._on_final(text)

    # ---------------- VALSEA RTT ----------------
    async def _connect_upstream(self) -> None:
        self.up = await websockets.connect(
            settings.valsea_rtt,
            additional_headers={"Authorization": f"Bearer {settings.valsea_key}"},
            open_timeout=8, max_size=2**22,
        )
        await self.up.send(json.dumps({
            "type": "session.start", "model": "valsea-rtt",
            "language": "vietnamese", "enable_correction": True,
            "diarize": False, "hint_text": self.pack.hint_text(),
        }))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            msg = await asyncio.wait_for(self.up.recv(), timeout=8)
            if isinstance(msg, (bytes, bytearray)):
                continue
            ev = json.loads(msg)
            if ev.get("type") in ("session.ready", "session.started"):
                self.up_ready.set()
                return
            if ev.get("type") == "error":
                raise RuntimeError(str(ev)[:200])
        raise TimeoutError("không nhận được session.ready")

    async def _upstream_tx(self) -> None:
        while True:
            item = await self.audio_q.get()
            await self.up_ready.wait()
            try:
                if item == COMMIT:
                    await self.up.send(json.dumps({"type": "audio.commit"}))
                else:
                    await self.up.send(item)
            except websockets.ConnectionClosed:
                if self.closing:
                    return

    async def _upstream_rx(self) -> None:
        try:
            async for raw in self.up:
                if isinstance(raw, (bytes, bytearray)):
                    continue
                ev = json.loads(raw)
                t = ev.get("type", "")
                if t == "transcript.partial":
                    self.emit({"type": "transcript.partial",
                               "text": ev.get("text", "")})
                elif t == "transcript.final":
                    self._on_final(ev.get("text", ""))
        except websockets.ConnectionClosed:
            pass
        if not self.closing:
            self.emit_state("degraded", "mất kết nối VALSEA RTT")

    def _on_final(self, text: str) -> None:
        if not text:
            return
        text = apply_itn(self.pack, text)
        self.dialogue.append(("customer", text))
        self.emit({"type": "transcript.final", "text": text})
        self.agent.feed_final(text)

    # ---------------- agent ↔ thế giới ----------------
    async def say(self, text: str) -> None:
        self.emit_state("speaking")
        self.emit({"type": "agent.say", "text": text})
        self.dialogue.append(("agent", text))
        if self.transport is None:
            return
        try:
            data, kind = await tts.synth(text, self.transport.tts_target, self.client)
            await self.transport.play(data, kind, text)
        except Exception as exc:  # noqa: BLE001 — mất giọng vẫn giữ nhịp kịch bản
            self.emit_state("degraded", f"TTS lỗi: {str(exc)[:80]}")
            await asyncio.sleep(min(6.0, 0.5 + 0.055 * len(text)))

    def _dialogue_text(self) -> str:
        return "\n".join(
            f"{'Tổng đài viên' if r == 'agent' else 'Khách'}: {t}"
            for r, t in self.dialogue)

    def _validate(self, fieldname: str, value: object) -> bool:
        if _empty(value):
            return False
        for v in self.pack.scoring.validators:
            if v.field == fieldname and v.rule == "regex":
                return re.fullmatch(str(v.value), str(value)) is not None
        return True

    async def collect(self, fieldname: str, heard: str = "") -> tuple[object, bool]:
        """Parse câu trả lời theo field kịch bản (rule thuần, 0ms, không LLM
        ngoài — VALSEA correction + ITN pack đã chuẩn hoá trước đó)."""
        try:
            value = parse_vi.parse_field(self.pack, fieldname, heard)
        except Exception:  # noqa: BLE001
            value = None
        if value is None or _empty(value):
            return None, False
        has_validator = any(v.field == fieldname
                            for v in self.pack.scoring.validators)
        valid = self._validate(fieldname, value)
        conf = 0.95 if (valid and has_validator) else (0.85 if valid else 0.55)
        patch = self.store.merge({fieldname: {
            "value": value, "confidence": conf, "evidence": heard[:200]}})
        if patch:
            self.emit({"type": "state.patch", "rev": self.store.rev,
                       "fields": patch})
            self.emit({"type": "score.update",
                       **score_form(self.pack, self.store).as_dict()})
        return value, valid

    # ---------------- E10: CRM + flow helpers ----------------
    async def crm_lookup(self) -> bool:
        """Lookup hồ sơ theo tên + xác thực đuôi CCCD → self.cust/handler."""
        from app.telephony import crm
        name = str((self.store.fields.get("ho_ten") or FieldState()).value or "")
        cccd = str((self.store.fields.get("cccd_cuoi") or FieldState()).value or "")
        try:
            self.cust = await crm.lookup_customer(name, self.client)
            self.verified = crm.verify_identity(self.cust, cccd)
            if self.cust:
                self.handler = await crm.lookup_handler(
                    crm.claim_type_of(self.cust), self.client)
        except Exception:  # noqa: BLE001
            self.cust, self.handler = None, None
        claim = (self.cust or {}).get("claim") or {}
        self.emit({"type": "crm.profile",
                   "found": self.cust is not None,
                   "verified": self.verified,
                   "source": "notify-rest" if crm.ready() else "kho local",
                   "name": (self.cust or {}).get("name", ""),
                   "kh_id": (self.cust or {}).get("id", ""),
                   "policy": (self.cust or {}).get("policy", ""),
                   "claim_id": claim.get("id", ""),
                   "claim_status": claim.get("status", ""),
                   "handler": (self.handler or {}).get("name", "")})
        return self.cust is not None

    async def collect_free(self, heard: str) -> None:
        """Câu nói tự do: ghi yeu_cau + extract mọi field bắt được (local)."""
        fs = self.store.fields.get("yeu_cau")
        if fs is not None and _empty(fs.value):
            patch = self.store.merge({"yeu_cau": {
                "value": heard.strip(), "confidence": 0.9,
                "evidence": heard[:200]}})
            if patch:
                self.emit({"type": "state.patch", "rev": self.store.rev,
                           "fields": patch})
        try:
            from app.core.extraction_local import extract_local
            result = await asyncio.to_thread(
                extract_local, self.pack, self._dialogue_text(),
                self.store.snapshot(), None)
        except Exception:  # noqa: BLE001
            result = {}
        result.pop("yeu_cau", None)          # đã ghi nguyên văn ở trên
        patch = self.store.merge(result)
        if patch:
            self.emit({"type": "state.patch", "rev": self.store.rev,
                       "fields": patch})
            self.emit({"type": "score.update",
                       **score_form(self.pack, self.store).as_dict()})

    def fields_summary(self) -> str:
        """Tóm tắt đọc lại cho khách: field đã điền + liên hệ từ hồ sơ CRM."""
        parts: list[str] = []
        for f in self.pack.all_fields():
            v = self.store.fields.get(f.name)
            if v is None or _empty(v.value) or f.name in ("yeu_cau",):
                continue
            val = "; ".join(map(str, v.value)) if isinstance(v.value, list) else v.value
            parts.append(f"{f.label.lower()} {val}")
        cust = self.cust or {}
        if cust.get("phone"):
            parts.append(f"số điện thoại {cust['phone']}")
        email = str(cust.get("email") or "")
        if email and "example.com" not in email:
            parts.append(f"email {email}")
        return ", ".join(parts[:7]) or "các thông tin em vừa ghi nhận"

    async def fire_flow_action(self, intent) -> None:
        """Ticket + PDF + email nhân sự/khách (Brevo) cho workflow có action."""
        action = self.pack.action(intent.action)
        if action is None:
            return
        self._close_wav()      # chốt file ghi âm để link trong mail nghe được
        try:
            res = await execute_action(
                self.pack, action, self.store,
                transcript=self._dialogue_text(),
                reviewer="AI callcenter", client=self.client,
                score=score_form(self.pack, self.store).total,
            )
        except Exception as exc:  # noqa: BLE001
            self.emit({"type": "error", "code": "action",
                       "message": str(exc)[:150]})
            return
        self.result["ticket"] = res["ticket"]
        self.emit({"type": "ticket", **res["ticket"], "pdf_url": res["pdf_url"]})
        try:
            from app.core.mailer import send_ticket_emails
            cust_mail = self.customer_email or str((self.cust or {}).get("email") or "")
            if "example.com" in cust_mail:
                cust_mail = "hailongluu@gmail.com"
            handler_mail = self.handler_email or str(
                (self.handler or {}).get("email") or "long@luuhailong.com")
            statuses = await send_ticket_emails(
                self.pack, res["ticket"], self.store.snapshot(),
                transcript=self._dialogue_text(),
                pdf_url=res["pdf_url"], recording_url=self.recording_url,
                base_url=settings.public_base or "http://localhost:8322",
                customer_email=cust_mail or "hailongluu@gmail.com",
                handler_email=handler_mail,
                narrative=res.get("narrative", ""),
                service_log=res.get("service_log"),
            )
            self.emit({"type": "mail.status", "statuses": statuses})
        except Exception as exc:  # noqa: BLE001
            self.emit({"type": "error", "code": "mail",
                       "message": str(exc)[:150]})

    async def hangup_done(self, detail: str, hungup: bool = False) -> None:
        """Kết thúc flow-call: KHÔNG tự fire action (fire_flow_action lo rồi)."""
        if self.result.get("done"):
            return
        self.result["done"] = True
        self._close_wav()
        self.result["hungup"] = hungup
        if self.recording_url:
            self.emit({"type": "recording", "url": self.recording_url})
        self.emit_state("done", detail)
        if self.transport is not None:
            try:
                await self.transport.hangup()
            except Exception:  # noqa: BLE001
                pass
        self.done.set()

    def reset_field(self, name: str) -> None:
        """Khách bảo sai → xoá để hỏi lại (không dính rule never-regress)."""
        if name in self.store.fields:
            self.store.fields[name] = FieldState()
            self.store.rev += 1
            self.emit({"type": "state.patch", "rev": self.store.rev,
                       "fields": {name: {"value": None, "confidence": 0.0,
                                         "evidence": ""}}})

    async def finish(self, complete: bool, hungup: bool = False) -> None:
        if self.result:
            return
        self.result = {"complete": complete, "hungup": hungup}
        if complete:
            action = self.pack.actions[0]
            try:
                res = await execute_action(
                    self.pack, action, self.store,
                    transcript=self._dialogue_text(),
                    reviewer="AI outbound call",
                    score=score_form(self.pack, self.store).total,
                    client=self.client,
                )
                self.result["ticket"] = res["ticket"]
                self.emit({"type": "ticket", **res["ticket"],
                           "pdf_url": res["pdf_url"]})
            except Exception as exc:  # noqa: BLE001
                self.emit({"type": "error", "code": "action",
                           "message": str(exc)[:150]})
        self.emit_state("done", "hoàn tất — đã gửi ticket" if complete
                        else ("khách cúp máy" if hungup else "thiếu thông tin"))
        if self.transport is not None:
            try:
                await self.transport.hangup()
            except Exception:  # noqa: BLE001
                pass
        self.done.set()

    # ---------------- lifecycle ----------------
    async def attach_transport(self, transport) -> bool:
        """Transport gọi khi kênh audio sẵn sàng → nối VALSEA + thả agent chạy."""
        self.transport = transport
        if self.mode != "replay":
            try:
                await self._connect_upstream()
            except Exception as exc:  # noqa: BLE001
                self.emit({"type": "error", "code": "rtt_connect",
                           "message": str(exc)[:200]})
                self.emit_state("failed", "VALSEA RTT không kết nối được")
                self.done.set()
                return False
            self._tasks += [asyncio.create_task(self._upstream_tx()),
                            asyncio.create_task(self._upstream_rx())]
        self._tasks.append(asyncio.create_task(self.agent.run()))
        return True

    async def shutdown(self) -> None:
        self.closing = True
        self._close_wav()
        for t in self._tasks:
            t.cancel()
        if self.up is not None:
            try:
                await self.up.close()
            except Exception:  # noqa: BLE001
                pass
        await self.client.aclose()
