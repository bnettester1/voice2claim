"""Giọng tổng đài viên — VALSEA TTS ƯU TIÊN, ElevenLabs dự phòng (18/07 Long chốt).

- VALSEA `/v1/audio/speech` trả wav → Twilio: transcode μ-law 8k nội bộ
  (audio.wav_to_ulaw8k); browser: phát wav trực tiếp (decodeAudioData).
- ElevenLabs chỉ chạy khi VALSEA lỗi/hết credits (`ulaw_8000` / mp3).
- Câu kịch bản static được cache đĩa để cuộc gọi không chờ synth.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx

from app.config import settings
from app.core import valsea
from app.telephony import audio as codec

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# voice đa ngôn ngữ có sẵn của ElevenLabs; đổi qua ELEVENLABS_VOICE_ID nếu muốn
_DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"
_MODEL = "eleven_flash_v2_5"          # rẻ + trễ thấp, hỗ trợ tiếng Việt

# câu đệm cache sẵn — phát NGAY trong lúc synth câu động chạy nền (che im lặng)
FILLER_CHECKED = "Dạ em kiểm tra được rồi ạ."
FILLER_FOUND = "Dạ em thấy hồ sơ của mình rồi ạ."
FILLER_NOTED = "Dạ em ghi nhận đầy đủ rồi ạ."
FILLERS = [FILLER_CHECKED, FILLER_FOUND, FILLER_NOTED]

_MIME = {"ulaw_8000": "audio/x-mulaw", "mp3_44100_128": "audio/mpeg", "wav": "audio/wav"}


def _cache_path(text: str, fmt: str, voice: str) -> Path:
    h = hashlib.sha1(f"{voice}|{fmt}|{text}".encode()).hexdigest()[:20]
    return CACHE_DIR / f"call_{h}.bin"


async def _elevenlabs(text: str, fmt: str, client: httpx.AsyncClient) -> bytes:
    voice = settings.eleven_voice or _DEFAULT_VOICE
    r = await client.post(
        f"{settings.elevenlabs_base}/text-to-speech/{voice}",
        params={"output_format": fmt},
        headers={"xi-api-key": settings.elevenlabs_key},
        json={"text": text, "model_id": _MODEL},
        timeout=30,
    )
    r.raise_for_status()
    return r.content


async def synth(text: str, target: str,
                client: httpx.AsyncClient) -> tuple[bytes, str, str]:
    """→ (audio bytes, kind, vendor). target: 'twilio' (μ-law 8k) | 'browser'.

    Ladder: cache → VALSEA TTS (ưu tiên, RETRY 2 lần — giữ GIỌNG ĐỒNG NHẤT
    trong cuộc gọi) → ElevenLabs chỉ là đường sống cuối. Lỗi cả 2 thì raise —
    caller quyết định (engine báo degraded + giữ nhịp, không chết)."""
    async def _try_valsea() -> tuple[bytes, str, str] | None:
        kind_v = "ulaw_8000" if target == "twilio" else "wav"
        pv = _cache_path(text, f"valsea:{kind_v}", "valsea-female")
        if pv.exists():
            return pv.read_bytes(), kind_v, "valsea"
        if not settings.valsea_key:
            return None
        for attempt in range(2):
            try:
                wav = await valsea.tts(text, client=client)
                data = codec.wav_to_ulaw8k(wav) if target == "twilio" else wav
                pv.write_bytes(data)
                return data, kind_v, "valsea"
            except Exception:  # noqa: BLE001
                if attempt == 0:
                    await asyncio.sleep(0.8)
        return None

    async def _try_eleven() -> tuple[bytes, str, str] | None:
        fmt = "ulaw_8000" if target == "twilio" else "mp3_44100_128"
        kind = "ulaw_8000" if target == "twilio" else "mp3"
        voice = settings.eleven_voice or _DEFAULT_VOICE
        pe = _cache_path(text, fmt, voice)
        if pe.exists():
            return pe.read_bytes(), kind, "elevenlabs"
        if not settings.elevenlabs_key:
            return None
        try:
            data = await _elevenlabs(text, fmt, client)
        except Exception:  # noqa: BLE001
            return None
        pe.write_bytes(data)
        return data, kind, "elevenlabs"

    # TTS_PREFER=elevenlabs (trong ~/.notify.env) → đồng nhất giọng bằng
    # ElevenLabs khi VALSEA TTS sự cố; mặc định VALSEA trước (decision 0009/0010)
    order = ([_try_eleven, _try_valsea] if settings.tts_prefer == "elevenlabs"
             else [_try_valsea, _try_eleven])
    for fn in order:
        got = await fn()
        if got is not None:
            return got
    raise RuntimeError("cả hai vendor TTS đều lỗi")


def mime_of(kind: str) -> str:
    return _MIME.get(kind, "application/octet-stream")


async def prewarm(texts: list[str], target: str) -> None:
    """Synth trước các câu kịch bản static (chạy nền, lỗi thì thôi)."""
    async with httpx.AsyncClient(timeout=45) as client:
        for t in texts:
            if not t:
                continue
            try:
                await synth(t, target, client)
                await asyncio.sleep(0.2)
            except Exception:  # noqa: BLE001
                return
