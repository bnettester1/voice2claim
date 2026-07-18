"""VALSEA client — transcribe (batch), TTS, formatting. Key chỉ ở server."""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

_HEADERS = {"Authorization": f"Bearer {settings.valsea_key}"}


async def transcribe(
    audio: bytes,
    filename: str = "audio.wav",
    client: httpx.AsyncClient | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """POST /v1/audio/transcriptions → dict (text, raw_transcript, semantic_tags?...)."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=120)
    try:
        r = await client.post(
            f"{settings.valsea_base}/audio/transcriptions",
            headers=_HEADERS,
            files={"file": (filename, audio, "application/octet-stream")},
            data={
                "model": "valsea-transcribe",
                "language": "vietnamese",
                "response_format": "verbose_json" if verbose else "json",
                "enable_correction": "true",
                "enable_tags": "true",
            },
        )
        r.raise_for_status()
        return r.json()
    finally:
        if own:
            await client.aclose()


async def tts(
    text: str,
    voice: str = "valsea-female",
    client: httpx.AsyncClient | None = None,
) -> bytes:
    """POST /v1/audio/speech → wav bytes."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=60)
    try:
        r = await client.post(
            f"{settings.valsea_base}/audio/speech",
            headers=_HEADERS,
            json={
                "model": "valsea-tts",
                "input": text,
                "voice": voice,
                "language": "vietnamese",
                "response_format": "wav",
            },
        )
        r.raise_for_status()
        return r.content
    finally:
        if own:
            await client.aclose()


async def formatting(
    transcript: str,
    output_type: str,
    semantic_tags: list | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST /v1/formatting — output_type: meeting_minutes|sales_summary|service_log|subtitles."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=60)
    try:
        payload: dict[str, Any] = {
            "model": "valsea-format",
            "transcript": transcript,
            "output_type": output_type,
        }
        if semantic_tags:
            payload["semantic_tags"] = semantic_tags
        r = await client.post(
            f"{settings.valsea_base}/formatting", headers=_HEADERS, json=payload
        )
        r.raise_for_status()
        return r.json()
    finally:
        if own:
            await client.aclose()
