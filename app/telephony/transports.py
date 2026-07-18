"""3 transport của CallEngine — bậc thang degrade: twilio → browser → replay.

- TwilioTransport : Twilio Media Streams WS (μ-law 8k 2 chiều, mark = ack phát xong)
- BrowserTransport: mic/loa trình duyệt (PCM16 16k binary vào, mp3/wav b64 ra)
- ReplayTransport : khách ảo trả lời canned — không cần mạng/telephony
"""
from __future__ import annotations

import asyncio
import base64
import json

from fastapi import WebSocket, WebSocketDisconnect

from app.telephony import audio as codec
from app.telephony import tts, twilio_client
from app.telephony.engine import CallEngine


class TwilioTransport:
    tts_target = "twilio"

    def __init__(self, ws: WebSocket, engine: CallEngine):
        self.ws, self.e = ws, engine
        self.stream_sid: str | None = None
        self._marks: dict[str, asyncio.Future] = {}
        self._mark_n = 0

    async def run(self) -> None:
        await self.ws.accept()
        try:
            while True:
                raw = await self.ws.receive_text()
                ev = json.loads(raw)
                et = ev.get("event")
                if et == "start":
                    self.stream_sid = ev["start"]["streamSid"]
                    self.e.emit_state("in-progress", "khách đã nghe máy")
                    asyncio.create_task(self.e.attach_transport(self))
                elif et == "media":
                    self.e.push_audio(codec.ulaw8k_to_pcm16k(
                        base64.b64decode(ev["media"]["payload"])))
                elif et == "mark":
                    fut = self._marks.pop(ev["mark"]["name"], None)
                    if fut is not None and not fut.done():
                        fut.set_result(True)
                elif et == "stop":
                    break
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self.e.agent.signal_hangup()

    async def play(self, data: bytes, kind: str, text: str = "") -> None:
        if self.stream_sid is None:
            return
        for i in range(0, len(data), 4000):          # ~500ms μ-law mỗi message
            await self.ws.send_json({
                "event": "media", "streamSid": self.stream_sid,
                "media": {"payload": base64.b64encode(data[i:i + 4000]).decode()},
            })
        name = f"m{self._mark_n}"
        self._mark_n += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._marks[name] = fut
        await self.ws.send_json({"event": "mark", "streamSid": self.stream_sid,
                                 "mark": {"name": name}})
        try:                                          # đợi Twilio phát xong
            await asyncio.wait_for(fut, len(data) / 8000 + 4)
        except asyncio.TimeoutError:
            pass

    async def hangup(self) -> None:
        if self.e.call_sid:
            try:
                await twilio_client.complete_call(self.e.call_sid, self.e.client)
            except Exception:  # noqa: BLE001
                pass
        try:
            await self.ws.close()
        except Exception:  # noqa: BLE001
            pass


class BrowserTransport:
    tts_target = "browser"

    def __init__(self, ws: WebSocket, engine: CallEngine):
        self.ws, self.e = ws, engine
        self._acks: dict[int, asyncio.Future] = {}
        self._n = 0

    async def run(self) -> None:
        await self.ws.accept()
        ok = await self.e.attach_transport(self)
        if not ok:
            await self.ws.close()
            return
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    self.e.push_audio(msg["bytes"])
                elif msg.get("text"):
                    ev = json.loads(msg["text"])
                    t = ev.get("type")
                    if t == "tts.done":
                        fut = self._acks.pop(int(ev.get("id", -1)), None)
                        if fut is not None and not fut.done():
                            fut.set_result(True)
                    elif t == "call.end":
                        break
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self.e.agent.signal_hangup()

    async def play(self, data: bytes, kind: str, text: str = "") -> None:
        n = self._n
        self._n += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._acks[n] = fut
        await self.ws.send_json({"type": "tts.audio", "id": n,
                                 "mime": tts.mime_of(kind),
                                 "b64": base64.b64encode(data).decode()})
        try:
            await asyncio.wait_for(fut, 30)
        except asyncio.TimeoutError:
            pass

    async def hangup(self) -> None:
        try:
            await self.ws.send_json({"type": "call.ended"})
            await self.ws.close()
        except Exception:  # noqa: BLE001
            pass


# câu trả lời khách ảo, khớp thứ tự listen của từng kịch bản
REPLAY_ANSWERS: dict[str, list[str]] = {
    "insurance_contract": [
        "À vâng, anh sinh ngày hai mươi tháng tư năm một nghìn chín trăm tám mươi sáu.",
        "Số căn cước của anh là không bảy chín, không tám ba, không không một, hai ba bốn.",
        "Đúng rồi em.",
        "Biển số xe anh là năm mốt ca, một hai ba chấm bốn lăm.",
        "Chuẩn rồi em.",
        "Anh đang ở số mười hai đường Nguyễn Văn Bảo, phường bốn, quận Gò Vấp, thành phố Hồ Chí Minh.",
    ],
    # case 2 của Long: claim mới — vi_tri tự bắt từ lời kể nên bot KHÔNG hỏi lại
    "insurance_callcenter": [
        "Dạ anh tên là Nguyễn Tiến Tuấn.",
        "Số cuối căn cước của anh là không không một, hai ba bốn.",
        "Em à, hôm qua anh bị đâm xe ở đường Cộng Hòa, em đến giải quyết bồi thường cho anh với.",
        "Khoảng tám giờ tối hôm qua em ạ.",
        "Xe anh vỡ đèn pha trước với móp cản sau, trầy xước khá nhiều.",
        "Anh chỉ bị trầy tay nhẹ thôi, không sao.",
        "Đúng rồi em.",
        "Thôi được rồi, em giải quyết nhanh cho anh nhé, cảm ơn em.",
    ],
}


class ReplayTransport:
    """Khách ảo: đợi agent chuyển sang listening rồi bơm câu trả lời canned.
    Audio agent (nếu synth được) đẩy qua monitor để trang demo phát tiếng."""

    tts_target = "browser"

    def __init__(self, engine: CallEngine, answers: list[str]):
        self.e = engine
        self.answers = list(answers)

    async def run(self) -> None:
        ok = await self.e.attach_transport(self)
        if not ok:
            return
        try:
            seen = 0
            for ans in self.answers:
                # đợi một lượt nghe MỚI bắt đầu (đếm listens, không poll cờ —
                # cờ listening có thể clear+set lại nhanh hơn chu kỳ poll)
                deadline = asyncio.get_running_loop().time() + 120
                while self.e.agent.listens <= seen and not self.e.done.is_set():
                    if asyncio.get_running_loop().time() > deadline:
                        raise asyncio.TimeoutError
                    await asyncio.sleep(0.05)
                if self.e.done.is_set():
                    return
                seen = self.e.agent.listens
                await asyncio.sleep(1.0)              # khách "suy nghĩ"
                self.e.inject_final(ans)
            await asyncio.wait_for(self.e.done.wait(), timeout=300)
        except asyncio.TimeoutError:
            self.e.agent.signal_hangup()

    async def play(self, data: bytes, kind: str, text: str = "") -> None:
        self.e.emit({"type": "tts.audio", "mime": tts.mime_of(kind),
                     "b64": base64.b64encode(data).decode()})
        if kind == "mp3":
            dur = len(data) / 16000                 # 128kbps ≈ 16kB/s
        elif kind == "wav" and len(data) > 44:      # đọc sample rate từ header
            sr = int.from_bytes(data[24:28], "little") or 22050
            dur = (len(data) - 44) / (sr * 2)
        else:
            dur = 0.5 + 0.055 * len(text)
        await asyncio.sleep(min(max(dur, 0.3), 15.0))

    async def hangup(self) -> None:
        return
