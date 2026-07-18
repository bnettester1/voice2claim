"""Unit test offline cho E8 (verify command của story) — không cần API key.

Chạy: python3 scripts/test_telephony.py
Kiểm: codec μ-law/resample, TwiML + chữ ký Twilio, ScriptedAgent 3 kịch bản
(đủ thông tin / im lặng / khách bác xác nhận) với engine stub.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# creds giả CHỈ cho test chữ ký/twiml — đặt trước khi import app.config
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "testtoken")
os.environ.setdefault("TWILIO_FROM_NUMBER", "+15550000000")
os.environ.setdefault("PUBLIC_BASE_URL", "https://demo.example.com")

import numpy as np  # noqa: E402

from app.core.form_state import FieldState, FormStore  # noqa: E402
from app.packs.loader import load_pack  # noqa: E402
from app.telephony import audio as codec  # noqa: E402
from app.telephony import twilio_client  # noqa: E402
from app.telephony.agent import ScriptedAgent  # noqa: E402

PASS = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        print(f"FAIL  {name}  {detail}")
        sys.exit(1)
    PASS.append(name)
    print(f"pass  {name}")


# ---------------------------------------------------------------- codec
def test_codec() -> None:
    t = np.arange(16000, dtype=np.float64) / 16000
    sine = (10000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)

    enc = codec.ulaw_encode(sine)
    dec = codec.ulaw_decode(enc)
    err = np.abs(dec.astype(np.int32) - sine.astype(np.int32))
    ok("codec.roundtrip_err", float(err.mean()) < 300,
       f"mean err {err.mean():.1f}")

    down = codec.resample(sine, 16000, 8000)
    ok("codec.resample_len", abs(down.size - 8000) <= 1, f"{down.size}")
    up = codec.resample(down, 8000, 16000)
    ok("codec.resample_roundtrip_len", abs(up.size - 16000) <= 2, f"{up.size}")

    pcm16k = codec.ulaw8k_to_pcm16k(codec.ulaw_encode(down).ljust(160, b"\x00"))
    ok("codec.ulaw8k_to_pcm16k", len(pcm16k) % 2 == 0 and len(pcm16k) > 0)

    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(sine.tobytes())
    ulaw = codec.wav_to_ulaw8k(buf.getvalue())
    ok("codec.wav_to_ulaw8k", abs(len(ulaw) - 8000) <= 2, f"{len(ulaw)}")


# ---------------------------------------------------------------- twilio
def test_twilio() -> None:
    xml = twilio_client.twiml_connect_stream("abc123")
    ok("twiml.wss_url", 'url="wss://demo.example.com/ws/twilio/abc123"' in xml, xml)

    path_qs = "/telephony/twiml?sid=abc123"
    form = {"CallSid": "CA1", "CallStatus": "in-progress"}
    payload = "https://demo.example.com" + path_qs + "".join(
        k + v for k, v in sorted(form.items()))
    sig = base64.b64encode(
        hmac.new(b"testtoken", payload.encode(), hashlib.sha1).digest()).decode()
    ok("sig.valid", twilio_client.valid_signature(path_qs, form, sig))
    ok("sig.invalid", not twilio_client.valid_signature(path_qs, form, "x" + sig))
    ok("sig.missing", not twilio_client.valid_signature(path_qs, form, None))

    ok("mask.phone", twilio_client.mask_phone("+84912345678") == "••••••••5678")


# ---------------------------------------------------------------- parse_vi
def test_parser() -> None:
    from app.telephony import parse_vi as P
    pack = load_pack("insurance_contract")
    cases = [
        ("ngay_sinh", "À vâng, anh sinh ngày hai mươi tháng tư năm một nghìn chín trăm tám mươi sáu.", "20/04/1986"),
        ("ngay_sinh", "hai mươi tháng tư năm tám sáu", "20/04/1986"),
        ("ngay_sinh", "mười lăm tháng ba năm một chín chín hai", "15/03/1992"),
        ("ngay_sinh", "sinh ngày 20 tháng 4 năm 1986 nhé", "20/04/1986"),
        ("ngay_sinh", "20/04/1986", "20/04/1986"),
        ("ngay_sinh", "ba mươi mốt tháng mười hai năm hai nghìn lẻ một", "31/12/2001"),
        ("ngay_sinh", "ờ để anh nhớ đã", None),                      # không parse được → reask
        ("so_cccd", "Số căn cước của anh là không bảy chín, không tám ba, không không một, hai ba bốn.", "079083001234"),
        ("so_cccd", "079 083 001 234", "079083001234"),
        ("so_cccd", "căn cước mười hai số của anh là không bảy chín không tám ba không không một hai ba bốn", "079083001234"),
        ("so_cccd", "anh không nhớ rõ nữa", None),                   # chỉ 1 chữ số 0 → None
        ("bien_so_xe", "Biển số xe anh là 51K, một hai ba chấm bốn lăm.", "51K-123.45"),
        ("bien_so_xe", "biển số 51K-123.45 em nhé", "51K-123.45"),
        ("bien_so_xe", "51K 123 45", "51K-123.45"),
        ("bien_so_xe", "59A chín tám bảy chấm sáu lăm", "59A-987.65"),
        ("dia_chi_lien_he", "Anh đang ở số mười hai đường Nguyễn Văn Bảo, phường bốn, quận Gò Vấp, thành phố Hồ Chí Minh.",
         "Số 12 đường Nguyễn Văn Bảo, phường 4, quận Gò Vấp, thành phố Hồ Chí Minh"),
        ("dia_chi_lien_he", "ở 25 Lê Lợi, quận Một, Đà Nẵng", "25 Lê Lợi, quận 1, Đà Nẵng"),
    ]
    for f, text, want in cases:
        got = P.parse_field(pack, f, text)
        ok(f"parse.{f}.{text[:18]}", got == want, f"got={got!r} want={want!r}")


# ---------------------------------------------------------------- agent
class StubEngine:
    """Engine giả: collect trả giá trị theo hàng đợi mỗi field, không mạng."""

    def __init__(self, pack, fill: dict[str, list]):
        self.pack = pack
        self.store = FormStore(pack)
        self.fill = {k: list(v) for k, v in fill.items()}
        self.said: list[str] = []
        self.steps: list[tuple[str, str]] = []
        self.finished: tuple | None = None
        self.agent = ScriptedAgent(self)

    def emit(self, obj) -> None:
        pass

    def emit_state(self, *a, **k) -> None:
        pass

    def emit_step(self, idx, fieldname, status) -> None:
        self.steps.append((fieldname, status))

    async def say(self, text: str) -> None:
        self.said.append(text)

    async def collect(self, fieldname: str, heard: str = ""):
        q = self.fill.get(fieldname) or []
        if q:
            v = q.pop(0)
            self.store.merge({fieldname: {"value": v, "confidence": 0.9,
                                          "evidence": heard or "stub"}})
        fs = self.store.fields[fieldname]
        val = None if fs.value in (None, "") else fs.value
        return val, val is not None

    def reset_field(self, name: str) -> None:
        self.store.fields[name] = FieldState()

    async def finish(self, complete: bool, hungup: bool = False) -> None:
        self.finished = (complete, hungup)


async def _drive(eng: StubEngine, answers: list[str], timeout=15.0) -> None:
    """Mô phỏng khách: đợi mỗi lượt nghe MỚI (đếm listens) rồi bơm trả lời."""
    task = asyncio.create_task(eng.agent.run())
    try:
        seen = 0
        for ans in answers:
            deadline = asyncio.get_running_loop().time() + timeout
            while eng.agent.listens <= seen:
                if task.done():
                    raise RuntimeError(f"agent kết thúc sớm trước: {ans[:30]}")
                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError(f"không tới lượt nghe cho: {ans[:30]}")
                await asyncio.sleep(0.005)
            seen = eng.agent.listens
            eng.agent.feed_final(ans)
        await asyncio.wait_for(task, timeout)
    finally:
        if not task.done():
            task.cancel()


def test_agent() -> None:
    pack = load_pack("insurance_contract")
    pack.call_script.reask_after_secs = 0.3
    ScriptedAgent.GRACE = 0.05
    sc = pack.call_script

    # A. đủ thông tin — 2 field có confirm, khách gật
    eng = StubEngine(pack, {
        "ngay_sinh": ["20/04/1986"],
        "so_cccd": ["079083001234"],
        "bien_so_xe": ["51K-123.45"],
        "dia_chi_lien_he": ["12 Nguyễn Văn Bảo, Gò Vấp, TP.HCM"],
    })
    asyncio.run(_drive(eng, [
        "anh sinh hai mươi tháng tư năm tám sáu",
        "không bảy chín không tám ba không không một hai ba bốn",
        "đúng rồi em",
        "năm mốt ca một hai ba chấm bốn lăm",
        "chuẩn luôn",
        "mười hai Nguyễn Văn Bảo Gò Vấp",
    ]))
    ok("agent.happy_finished", eng.finished == (True, False), str(eng.finished))
    ok("agent.happy_closing", eng.said[-1] == sc.closing)
    ok("agent.happy_greeting_first", eng.said[0] == sc.greeting)
    filled = [f for f, st in eng.steps if st == "filled"]
    ok("agent.happy_all_filled", set(filled) == {s.field for s in sc.steps},
       str(eng.steps))
    f2, t2 = eng.store.filled_required()
    ok("agent.happy_required", (f2, t2) == (4, 4), f"{f2}/{t2}")

    # B. khách im lặng hoàn toàn — reask rồi skip, đóng máy partial
    eng2 = StubEngine(pack, {})
    asyncio.run(asyncio.wait_for(eng2.agent.run(), 30))
    ok("agent.silence_finished", eng2.finished == (False, False),
       str(eng2.finished))
    ok("agent.silence_partial_closing",
       eng2.said[-1] == (sc.closing_partial or sc.closing))
    skipped = [f for f, st in eng2.steps if st == "skipped"]
    ok("agent.silence_all_skipped", len(skipped) == len(sc.steps), str(skipped))
    n_ask = len([s for s in eng2.said if s not in (sc.greeting, sc.closing,
                                                   sc.closing_partial)])
    ok("agent.silence_reask_count", n_ask == 3 * len(sc.steps), str(n_ask))

    # C. khách bác xác nhận CCCD → agent xoá + hỏi lại → lần 2 đúng
    eng3 = StubEngine(pack, {
        "ngay_sinh": ["20/04/1986"],
        "so_cccd": ["079083009999", "079083001234"],
        "bien_so_xe": ["51K-123.45"],
        "dia_chi_lien_he": ["12 Nguyễn Văn Bảo"],
    })
    asyncio.run(_drive(eng3, [
        "hai mươi tháng tư năm tám sáu",
        "không bảy chín ... chín chín chín chín",
        "không phải em ơi, sai rồi",
        "đọc lại nè: không bảy chín không tám ba không không một hai ba bốn",
        "đúng rồi",
        "năm mốt ca một hai ba chấm bốn lăm",
        "ok em",
        "mười hai Nguyễn Văn Bảo",
    ]))
    ok("agent.reject_then_fix", eng3.finished == (True, False),
       str(eng3.finished))
    ok("agent.reject_final_value",
       eng3.store.fields["so_cccd"].value == "079083001234",
       str(eng3.store.fields["so_cccd"].value))


if __name__ == "__main__":
    test_codec()
    test_twilio()
    test_parser()
    test_agent()
    print(f"\nOK — {len(PASS)} test pass")
