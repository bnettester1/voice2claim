"""P0 probe: kiểm tra sống/chết + độ trễ của VALSEA / Groq / ElevenLabs.

Chạy:  .venv/bin/python scripts/probe.py
In OK/FAIL từng dịch vụ — KHÔNG BAO GIỜ in giá trị key.
Ghi kết quả (không secrets) vào docs/product/probe-report.md
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import struct
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import websockets

from app.config import settings

AUDIO_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
REPORT = Path(__file__).resolve().parent.parent / "docs" / "product" / "probe-report.md"

PROBE_TEXT = (
    "Xin chào, tôi tên Tuấn. Xe tôi là Wave Alpha, "
    "biển số năm chín A, chín trăm tám mươi bảy chấm sáu lăm."
)
FORMAT_TRANSCRIPT = (
    "Giám định viên: Em chào anh Tuấn, em nhận được thông báo anh vừa bị tai nạn "
    "ở đường Cộng Hòa. Người bị nạn: Anh bị trầy xước tay, xe Wave Alpha vỡ yếm, "
    "gãy gương chiếu hậu bên trái. Xe kia là Toyota Vios biển số 59A-987.65. "
    "Giám định viên: Em ghi nhận rồi, anh bấm nút Gửi yêu cầu cứu hộ xe máy giúp em nhé."
)

results: list[dict] = []


def record(name: str, ok: bool, ms: int | None, note: str = ""):
    results.append({"name": name, "ok": ok, "ms": ms, "note": note[:300]})
    state = "✅ OK " if ok else "❌ FAIL"
    lat = f"{ms:>5}ms" if ms is not None else "     —"
    print(f"{state} {lat}  {name}  {note[:120]}")


def pcm16_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def sine_wav(seconds: float = 1.0, rate: int = 16000) -> bytes:
    import math
    n = int(seconds * rate)
    pcm = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(n)
    )
    return pcm16_to_wav(pcm, rate)


def looks_vietnamese(text: str) -> bool:
    return bool(re.search(r"[àáảãạăâđèéẻẽẹêìíỉĩịòóỏõọôơùúủũụưỳýỷỹỵ]", text.lower()))


async def probe_elevenlabs(client: httpx.AsyncClient) -> bytes | None:
    """Trả về WAV bytes của câu probe nếu TTS được, else None."""
    if not settings.elevenlabs_key:
        record("ElevenLabs voices", False, None, "thiếu key")
        return None
    h = {"xi-api-key": settings.elevenlabs_key}
    t0 = time.monotonic()
    try:
        r = await client.get(f"{settings.elevenlabs_base}/voices", headers=h)
        r.raise_for_status()
        voices = r.json().get("voices", [])
        record("ElevenLabs voices", True, int((time.monotonic() - t0) * 1000),
               f"{len(voices)} voices")
    except Exception as e:  # noqa: BLE001
        record("ElevenLabs voices", False, int((time.monotonic() - t0) * 1000), str(e))
        return None
    voice_id = None
    for v in voices:  # ưu tiên voice đa ngôn ngữ bất kỳ
        voice_id = v.get("voice_id")
        if voice_id:
            break
    if not voice_id:
        record("ElevenLabs TTS", False, None, "không có voice nào")
        return None
    t0 = time.monotonic()
    try:
        r = await client.post(
            f"{settings.elevenlabs_base}/text-to-speech/{voice_id}",
            headers=h,
            params={"output_format": "pcm_16000"},
            json={"text": PROBE_TEXT, "model_id": "eleven_multilingual_v2"},
        )
        r.raise_for_status()
        wav = pcm16_to_wav(r.content)
        (AUDIO_DIR / "probe.wav").write_bytes(wav)
        record("ElevenLabs TTS vi", True, int((time.monotonic() - t0) * 1000),
               f"probe.wav {len(wav)//1024}KB")
        return wav
    except Exception as e:  # noqa: BLE001
        record("ElevenLabs TTS vi", False, int((time.monotonic() - t0) * 1000), str(e))
        return None


async def probe_valsea_batch(client: httpx.AsyncClient, wav: bytes) -> None:
    if not settings.valsea_key:
        record("VALSEA transcribe", False, None, "thiếu key")
        return
    t0 = time.monotonic()
    try:
        r = await client.post(
            f"{settings.valsea_base}/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.valsea_key}"},
            files={"file": ("probe.wav", wav, "audio/wav")},
            data={
                "model": "valsea-transcribe",
                "language": "vietnamese",
                "response_format": "verbose_json",
            },
        )
        r.raise_for_status()
        j = r.json()
        text = (j.get("text") or "")[:80]
        keys = ",".join(sorted(j.keys()))
        record("VALSEA transcribe", True, int((time.monotonic() - t0) * 1000),
               f"text='{text}' keys={keys}")
    except Exception as e:  # noqa: BLE001
        record("VALSEA transcribe", False, int((time.monotonic() - t0) * 1000), str(e))


async def probe_valsea_rtt() -> None:
    if not settings.valsea_key:
        record("VALSEA RTT ws", False, None, "thiếu key")
        return
    t0 = time.monotonic()
    try:
        async with websockets.connect(
            settings.valsea_rtt,
            additional_headers={"Authorization": f"Bearer {settings.valsea_key}"},
            open_timeout=8,
        ) as ws:
            await ws.send(json.dumps({
                "type": "session.start",
                "model": "valsea-rtt",
                "language": "vietnamese",
                "enable_correction": True,
            }))
            deadline = time.monotonic() + 8
            got = ""
            while time.monotonic() < deadline:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
                if isinstance(msg, (bytes, bytearray)):
                    continue
                ev = json.loads(msg)
                got = ev.get("type", "")
                if got in ("session.ready", "session.started", "error"):
                    break
            ok = got in ("session.ready", "session.started")
            record("VALSEA RTT ws", ok, int((time.monotonic() - t0) * 1000), f"event={got or 'none'}")
    except Exception as e:  # noqa: BLE001
        record("VALSEA RTT ws", False, int((time.monotonic() - t0) * 1000), str(e))


async def probe_valsea_formatting(client: httpx.AsyncClient) -> None:
    if not settings.valsea_key:
        record("VALSEA formatting", False, None, "thiếu key")
        return
    for output_type in ("service_log", "meeting_minutes"):
        t0 = time.monotonic()
        try:
            r = await client.post(
                f"{settings.valsea_base}/formatting",
                headers={"Authorization": f"Bearer {settings.valsea_key}"},
                json={
                    "model": "valsea-format",
                    "transcript": FORMAT_TRANSCRIPT,
                    "output_type": output_type,
                },
            )
            r.raise_for_status()
            j = r.json()
            blob = json.dumps(j, ensure_ascii=False)
            vi = looks_vietnamese(blob)
            record(f"VALSEA formatting {output_type}", True,
                   int((time.monotonic() - t0) * 1000),
                   f"lang={'VI' if vi else 'EN?'} keys={','.join(sorted(j.keys()))[:80]}")
            (AUDIO_DIR.parent / f"formatting_{output_type}.json").write_text(
                json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            record(f"VALSEA formatting {output_type}", False,
                   int((time.monotonic() - t0) * 1000), str(e))


async def probe_valsea_tts(client: httpx.AsyncClient) -> None:
    if not settings.valsea_key:
        record("VALSEA TTS", False, None, "thiếu key")
        return
    t0 = time.monotonic()
    try:
        r = await client.post(
            f"{settings.valsea_base}/audio/speech",
            headers={"Authorization": f"Bearer {settings.valsea_key}"},
            json={"model": "valsea-tts", "input": "Đã ghi nhận. Yêu cầu cứu hộ đang được gửi đi.",
                  "voice": "valsea-female", "language": "vietnamese",
                  "response_format": "wav"},
        )
        r.raise_for_status()
        (AUDIO_DIR / "valsea_tts_probe.bin").write_bytes(r.content)
        ct = r.headers.get("content-type", "?")
        record("VALSEA TTS", True, int((time.monotonic() - t0) * 1000),
               f"{len(r.content)//1024}KB {ct}")
    except Exception as e:  # noqa: BLE001
        record("VALSEA TTS", False, int((time.monotonic() - t0) * 1000), str(e))


async def main() -> None:
    print("== P0 PROBE ==  keys:", settings.status())
    async with httpx.AsyncClient(timeout=60) as client:
        wav = await probe_elevenlabs(client)
        if wav is None:
            wav = sine_wav()
            print("   (dùng sine clip fallback cho ASR probe)")
        await probe_valsea_batch(client, wav)
        await probe_valsea_rtt()
        await probe_valsea_formatting(client)
        await probe_valsea_tts(client)

    ok = sum(1 for r in results if r["ok"])
    print(f"\n== TỔNG: {ok}/{len(results)} OK ==")
    lines = ["# P0 Probe Report", "",
             f"Tổng: **{ok}/{len(results)} OK**", "",
             "| Probe | KQ | Latency | Ghi chú |", "| --- | --- | --- | --- |"]
    for r in results:
        lines.append(
            f"| {r['name']} | {'OK' if r['ok'] else 'FAIL'} | "
            f"{r['ms'] if r['ms'] is not None else '—'}ms | {r['note'].replace('|', '/')} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report → {REPORT}")


if __name__ == "__main__":
    asyncio.run(main())
