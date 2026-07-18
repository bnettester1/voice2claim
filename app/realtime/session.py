"""LiveSession — relay browser WS ↔ VALSEA RTT + engine live.

browser ──binary PCM16 16k──▶ audio_q ──▶ VALSEA wss /v1/realtime (hint_text từ pack)
VALSEA ──partial/final──▶ TriggerMatcher.feed (arm <500ms) + transcript buffer
transcript.final ──debounce 0.5s single-flight──▶ extraction local ──▶ FormStore.merge
──▶ state.patch + score.update ──▶ browser
Action auto fire ──▶ execute_action (PDF/ticket/TTS) ──▶ action.result
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import websockets
from fastapi import WebSocket

from app.config import settings
from app.core.actions import execute_action
from app.core.extraction import extract
from app.core.form_state import FormStore
from app.core.scoring import score_form
from app.core.triggers import TriggerMatcher
from app.packs.loader import ActionSpec, Pack

COMMIT = "__COMMIT__"


class LiveSession:
    def __init__(self, ws: WebSocket, pack: Pack):
        import uuid
        import wave

        from app.batch.routes import RECORD_DIR

        self.ws = ws
        self.pack = pack
        self.sid = uuid.uuid4().hex[:12]
        self.recording_url = f"/rec/{self.sid}"
        try:  # ghi WAV tăng dần từ PCM frames — người xử lý nghe lại được băng
            self._wav = wave.open(str(RECORD_DIR / f"{self.sid}.wav"), "wb")
            self._wav.setnchannels(1)
            self._wav.setsampwidth(2)
            self._wav.setframerate(16000)
        except Exception:  # noqa: BLE001
            self._wav = None
        self.store = FormStore(pack)
        self.matcher = TriggerMatcher(pack)
        self.audio_q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.out_q: asyncio.Queue = asyncio.Queue()
        self.finals: list[str] = []
        self.extract_signal = asyncio.Event()
        self.up = None
        self.up_ready = asyncio.Event()
        self.closing = False
        self.fired: set[str] = set()
        self.client = httpx.AsyncClient(timeout=90)
        self.t_start = time.monotonic()
        self.agreement: float | None = None
        self.ner_verdict: dict = {}
        try:  # VAD (PyTorch) — degrade sạch nếu thiếu
            from app.core.ml.vad import EndOfSpeechDetector
            self.vad = EndOfSpeechDetector()
        except Exception:  # noqa: BLE001
            self.vad = None

    # ---------------- helpers ----------------
    def emit(self, obj: dict) -> None:
        try:
            self.out_q.put_nowait(obj)
        except asyncio.QueueFull:
            pass

    def _score(self) -> dict:
        return score_form(self.pack, self.store, agreement=self.agreement,
                          ner_verdict=self.ner_verdict).as_dict()

    # ---------------- upstream ----------------
    async def _connect_upstream_once(self) -> None:
        self.up = await websockets.connect(
            settings.valsea_rtt,
            additional_headers={"Authorization": f"Bearer {settings.valsea_key}"},
            open_timeout=8, max_size=2**22,
        )
        await self.up.send(json.dumps({
            "type": "session.start",
            "model": "valsea-rtt",
            "language": "vietnamese",
            "enable_correction": True,
            "diarize": False,
            "hint_text": self.pack.hint_text(),
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

    async def _reconnect(self) -> bool:
        self.up_ready.clear()
        for i, delay in enumerate((0.5, 1.0), 1):
            self.emit({"type": "status", "state": "reconnecting", "detail": f"lần {i}"})
            await asyncio.sleep(delay)
            try:
                await self._connect_upstream_once()
                self.emit({"type": "status", "state": "live", "detail": "đã kết nối lại"})
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    # ---------------- tasks ----------------
    async def browser_rx(self) -> None:
        while True:
            msg = await self.ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes"):
                if self._wav is not None:
                    try:
                        self._wav.writeframes(msg["bytes"])
                    except Exception:  # noqa: BLE001
                        self._wav = None
                try:
                    self.audio_q.put_nowait(msg["bytes"])
                except asyncio.QueueFull:
                    pass  # upstream nghẽn — bỏ frame (chấp nhận hụt tiếng)
                if self.vad is not None and self.vad.enabled:
                    try:  # silero-VAD: hết lượt nói → commit sớm cho RTT
                        if self.vad.feed(msg["bytes"]):
                            self.audio_q.put_nowait(COMMIT)
                            self.emit({"type": "status", "state": "live",
                                       "detail": "VAD chốt lượt nói (auto commit)"})
                    except (asyncio.QueueFull, Exception):  # noqa: BLE001
                        pass
            elif msg.get("text"):
                ev = json.loads(msg["text"])
                t = ev.get("type")
                if t == "mic.stop":
                    try:
                        self.audio_q.put_nowait(COMMIT)
                    except asyncio.QueueFull:
                        pass
                    self._save_batch_session()
                elif t == "session.end":
                    return
                elif t == "field.edit":
                    if self.store.set_user(ev.get("field", ""), ev.get("value")):
                        self.emit({"type": "state.patch", "rev": self.store.rev,
                                   "fields": {ev["field"]: self.store.full_state()[ev["field"]]}})
                        self.emit({"type": "score.update", **self._score()})
                elif t == "action.confirm":
                    aid = ev.get("action", "")
                    action = self.pack.action(aid)
                    if action and self.matcher.confirm_click(aid):
                        asyncio.create_task(self._fire(action, None))

    async def upstream_tx(self) -> None:
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

    async def upstream_rx(self) -> None:
        while True:
            try:
                async for raw in self.up:
                    if isinstance(raw, (bytes, bytearray)):
                        continue
                    ev = json.loads(raw)
                    t = ev.get("type", "")
                    if t == "transcript.partial":
                        self.on_text(ev.get("text", ""), final=False, ts=ev.get("timestampMs"))
                    elif t == "transcript.final":
                        self.on_text(ev.get("text", ""), final=True, ts=ev.get("timestampMs"))
            except websockets.ConnectionClosed:
                pass
            if self.closing:
                return
            if not await self._reconnect():
                self.emit({"type": "status", "state": "error",
                           "detail": "mất kết nối VALSEA RTT — dùng chế độ Batch"})
                return

    def on_text(self, text: str, final: bool, ts=None) -> None:
        if not text:
            return
        if final:
            from app.core.normalize import apply_itn
            text = apply_itn(self.pack, text)
        for e in self.matcher.feed(text, final):
            if e.kind == "armed":
                self.emit({"type": "action.armed", "action": e.action.id,
                           "score": e.score, "arm_latency_ms": round(e.latency_ms, 1)})
            else:
                asyncio.create_task(self._fire(e.action, e.latency_ms))
        self.emit({"type": "transcript.final" if final else "transcript.partial",
                   "text": text, "ts": ts})
        if final:
            self.finals.append(text)
            self.extract_signal.set()

    async def extract_worker(self) -> None:
        while True:
            await self.extract_signal.wait()
            self.extract_signal.clear()
            await asyncio.sleep(0.5)          # debounce — final mới chỉ re-set event
            self.extract_signal.clear()
            snapshot = " ".join(self.finals)
            if not snapshot.strip():
                continue
            try:
                result = await extract(self.pack, snapshot, self.store.snapshot(),
                                       client=self.client)
            except Exception:  # noqa: BLE001
                continue
            patch = self.store.merge(result)
            if patch:
                try:
                    from app.core.ml import ner_local
                    self.agreement, self.ner_verdict = await asyncio.to_thread(
                        ner_local.agreement, snapshot, self.store.snapshot())
                except Exception:  # noqa: BLE001
                    pass
                self.emit({"type": "state.patch", "rev": self.store.rev, "fields": patch})
                self.emit({"type": "score.update", **self._score()})

    async def browser_tx(self) -> None:
        while True:
            obj = await self.out_q.get()
            await self.ws.send_json(obj)

    async def _fire(self, action: ActionSpec, arm_ms: float | None) -> None:
        if action.id in self.fired:
            return
        self.fired.add(action.id)
        self.emit({"type": "action.fired", "action": action.id})
        try:
            res = await execute_action(
                self.pack, action, self.store,
                transcript=" ".join(self.finals),
                arm_ms=arm_ms, client=self.client,
                score=score_form(self.pack, self.store).total,
                recording_url=self.recording_url,
            )
            self.emit({"type": "action.result", "action": action.id,
                       "ticket": res["ticket"], "pdf_url": res["pdf_url"],
                       "tts_b64": res["tts_b64"]})
        except Exception as e:  # noqa: BLE001
            self.emit({"type": "error", "code": "action", "message": str(e)[:150]})

    def _save_batch_session(self) -> None:
        """Đăng ký state vào SESSIONS để màn Duyệt & Gửi (REST) dùng sau cuộc gọi."""
        from app.batch.routes import SESSIONS, Session as BatchSession

        if self._wav is not None:  # chốt file WAV để /rec/{sid} phát được ngay
            try:
                self._wav.close()
            except Exception:  # noqa: BLE001
                pass
            self._wav = None
        sid = self.sid
        bs = BatchSession(
            sid=sid, pack=self.pack, store=self.store, matcher=self.matcher,
            transcript=" ".join(self.finals),
        )
        bs.recording_url = self.recording_url
        bs.agreement, bs.ner_verdict = self.agreement, self.ner_verdict
        bs.armed = {
            aid: {"score": st.armed_score, "latency_ms": 0.0}
            for aid, st in self.matcher.state.items() if st.armed_at > 0
        }
        bs.fired = list(self.fired)
        SESSIONS[sid] = bs
        self.emit({"type": "session.saved", "sid": sid,
                   "recording_url": self.recording_url})

    # ---------------- lifecycle ----------------
    async def run(self) -> None:
        await self.ws.accept()
        try:
            await self._connect_upstream_once()
        except Exception as e:  # noqa: BLE001
            await self.ws.send_json({"type": "error", "code": "rtt_connect",
                                     "message": str(e)[:200]})
            await self.ws.close()
            await self.client.aclose()
            return
        self.emit({"type": "session.ready", "mode": "live",
                   "hint_chars": len(self.pack.hint_text())})
        tasks = [asyncio.create_task(fn()) for fn in (
            self.browser_rx, self.upstream_tx, self.upstream_rx,
            self.extract_worker, self.browser_tx)]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.closing = True
            for t in tasks:
                t.cancel()
            if self._wav is not None:  # đóng file nếu user thoát không bấm Kết thúc
                try:
                    self._wav.close()
                except Exception:  # noqa: BLE001
                    pass
                self._wav = None
            try:
                if self.up:
                    await self.up.close()
            except Exception:  # noqa: BLE001
                pass
            await self.client.aclose()
