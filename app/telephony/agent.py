"""ScriptedAgent — máy trạng thái tổng đài viên theo kịch bản pack.call_script.

Vòng đời: greeting → [ask → listen → (confirm) → filled/skipped]* → closing →
ticket (khi đủ required) → hangup. Agent chỉ nói câu trong kịch bản; giá trị
nghe được do CallEngine.collect() (VALSEA final + parse_vi rule) đảm nhiệm.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.triggers import normalize_vi

if TYPE_CHECKING:  # tránh vòng import
    from app.telephony.engine import CallEngine

_HANGUP = object()   # sentinel inbox: bên kia cúp máy / transport đóng

# so khớp trên chuỗi đã normalize (bỏ dấu) — NEG xét trước, cụm dài trước
_NEG = ("khong dung", "khong phai", "chua dung", "sai roi", "sai", "nham", "khong")
_POS = ("dung roi", "dung", "phai", "chuan", "chinh xac", "ok", "oke", "vang", "da", "u")


class CallEnded(Exception):
    pass


def speakable(field: str, value: object) -> str:
    """Giá trị → dạng TTS đọc tự nhiên (số đọc từng chữ số)."""
    s = str(value)
    if field == "so_cccd" and s.isdigit():
        return " ".join(s)
    if field == "bien_so_xe":
        return s.replace("-", " ").replace(".", " chấm ")
    if field == "ngay_sinh":
        return s.replace("/", " tháng ", 1).replace("/", " năm ", 1) \
            if s.count("/") == 2 else s
    return s


class ScriptedAgent:
    GRACE = 1.2   # giây gom các final sát nhau thành 1 câu trả lời

    def __init__(self, engine: "CallEngine"):
        self.e = engine
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.listening = asyncio.Event()   # trạng thái UI "đang nghe"
        self.listens = 0                   # đếm lượt nghe ĐÃ BẮT ĐẦU — replay/test bám số này

    # ---- input từ engine ----
    def feed_final(self, text: str) -> None:
        self.inbox.put_nowait(text)

    def signal_hangup(self) -> None:
        self.inbox.put_nowait(_HANGUP)

    # ---- nghe 1 lượt ----
    async def _listen(self, timeout: float) -> str | None:
        """Đợi final đầu tiên (timeout → None), gom các final sát nhau (GRACE)."""
        self.listens += 1
        self.listening.set()
        self.e.emit_state("listening")
        try:
            try:
                first = await asyncio.wait_for(self.inbox.get(), timeout)
            except asyncio.TimeoutError:
                return None
            if first is _HANGUP:
                raise CallEnded()
            parts = [str(first)]
            while True:
                try:
                    nxt = await asyncio.wait_for(self.inbox.get(), self.GRACE)
                except asyncio.TimeoutError:
                    break
                if nxt is _HANGUP:
                    raise CallEnded()
                parts.append(str(nxt))
            return " ".join(parts)
        finally:
            self.listening.clear()

    async def _confirm(self, step, value) -> bool:
        await self.e.say(step.confirm_tpl.replace("{value}", speakable(step.field, value)))
        heard = await self._listen(6)
        if heard is None:
            return True                      # im lặng — coi như đồng ý (demo)
        n = f" {normalize_vi(heard)} "
        for kw in _NEG:
            if f" {kw}" in n:
                return False
        for kw in _POS:
            if f" {kw}" in n:
                return True
        await self.e.collect(step.field, heard)  # khách có thể vừa đọc lại giá trị
        return True

    async def _do_step(self, idx: int, step, reask_secs: float) -> None:
        e = self.e
        e.emit_step(idx, step.field, "asking")
        await e.say(step.ask)
        for attempt in range(3):
            heard = await self._listen(reask_secs + (2 if attempt else 0))
            if heard is not None:
                value, valid = await e.collect(step.field, heard)
                if value is not None:
                    if step.confirm_tpl and not await self._confirm(step, value):
                        e.reset_field(step.field)
                    else:
                        e.emit_step(idx, step.field,
                                    "filled" if valid else "filled_low")
                        return
            if attempt >= 2:
                break
            e.emit_step(idx, step.field, "asking")
            await e.say(step.reask or step.ask)
        e.emit_step(idx, step.field, "skipped")

    def _complete(self) -> bool:
        filled, total = self.e.store.filled_required()
        return filled >= total

    # ---- vòng đời ----
    async def run(self) -> None:
        sc = self.e.pack.call_script
        try:
            await self.e.say(sc.greeting)
            for idx, step in enumerate(sc.steps):
                self.e.emit({"type": "call.step.total", "total": len(sc.steps)})
                await self._do_step(idx, step, sc.reask_after_secs)
            complete = self._complete()
            await self.e.say(sc.closing if complete
                             else (sc.closing_partial or sc.closing))
            await self.e.finish(complete)
        except CallEnded:
            await self.e.finish(self._complete(), hungup=True)
        except Exception as exc:  # noqa: BLE001 — không để agent chết im lặng
            self.e.emit({"type": "error", "code": "agent", "message": str(exc)[:150]})
            await self.e.finish(False)
