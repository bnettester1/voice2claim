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


async def synth(text: str, target: str, client: httpx.AsyncClient) -> tuple[bytes, str]:
    """→ (audio bytes, kind). target: 'twilio' (μ-law 8k) | 'browser' (wav/mp3).

    Ladder: cache → VALSEA TTS (ưu tiên) → ElevenLabs. Lỗi cả 2 vendor thì
    raise — caller quyết định (engine báo degraded + giữ nhịp, không chết).
    """
    kind_v = "ulaw_8000" if target == "twilio" else "wav"
    pv = _cache_path(text, f"valsea:{kind_v}", "valsea-female")
    if pv.exists():
        return pv.read_bytes(), kind_v
    if settings.valsea_key:
        try:
            wav = await valsea.tts(text, client=client)
            data = codec.wav_to_ulaw8k(wav) if target == "twilio" else wav
            pv.write_bytes(data)
            return data, kind_v
        except Exception:  # noqa: BLE001 — rơi xuống ElevenLabs
            pass

    fmt = "ulaw_8000" if target == "twilio" else "mp3_44100_128"
    kind = "ulaw_8000" if target == "twilio" else "mp3"
    voice = settings.eleven_voice or _DEFAULT_VOICE
    pe = _cache_path(text, fmt, voice)
    if pe.exists():
        return pe.read_bytes(), kind
    data = await _elevenlabs(text, fmt, client)
    pe.write_bytes(data)
    return data, kind


def mime_of(kind: str) -> str:
    return _MIME.get(kind, "application/octet-stream")


async def prewarm(texts: list[str], target: str) -> None:
    """Synth trước các câu kịch bản static (chạy nền, lỗi thì thôi)."""
    async with httpx.AsyncClient(timeout=30) as client:
        for t in texts:
            if not t:
                continue
            try:
                await synth(t, target, client)
                await asyncio.sleep(0.2)
            except Exception:  # noqa: BLE001
                return
