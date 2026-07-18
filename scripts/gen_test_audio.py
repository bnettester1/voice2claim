"""Sinh audio test từ kịch bản (ElevenLabs TTS, mỗi vai một giọng).

Dùng:  .venv/bin/python scripts/gen_test_audio.py [--only A,D] [--noisy]
Sinh assets/audio/<ID>.wav (PCM16 16kHz mono). --noisy: thêm biến thể trộn nhiễu
(còi cứu thương/phòng khám) và telephony (bandpass) — hoàn thiện ở P3a.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from app.config import settings

AUDIO_DIR = ROOT / "assets" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
NOISE_DIR = AUDIO_DIR / "noise"
NOISE_DIR.mkdir(exist_ok=True)

CASES = []
for _f in ("kb_af.json", "extended_gj.json"):
    _p = ROOT / "packs" / "testcases" / _f
    if _p.exists():
        CASES += json.loads(_p.read_text(encoding="utf-8"))["cases"]

RATE = 16000
GAP = b"\x00\x00" * int(0.35 * RATE)  # 350ms nghỉ giữa các lượt thoại
# flash_v2_5 + language_code=vi: VALSEA nghe đúng cả biển số (đã A/B test 2026-07-18)
MODEL = "eleven_flash_v2_5"
VOICE_FEMALE, VOICE_MALE = "Sarah", "George"


async def pick_voices(client: httpx.AsyncClient) -> tuple[str, str]:
    r = await client.get(f"{settings.elevenlabs_base}/voices",
                         headers={"xi-api-key": settings.elevenlabs_key})
    r.raise_for_status()
    ids = {v["name"].split(" - ")[0]: v["voice_id"] for v in r.json()["voices"]}
    voices = r.json()["voices"]
    return (ids.get(VOICE_FEMALE, voices[0]["voice_id"]),
            ids.get(VOICE_MALE, voices[-1]["voice_id"]))


async def tts_pcm(client: httpx.AsyncClient, voice_id: str, text: str) -> bytes:
    r = await client.post(
        f"{settings.elevenlabs_base}/text-to-speech/{voice_id}",
        headers={"xi-api-key": settings.elevenlabs_key},
        params={"output_format": "pcm_16000"},
        json={"text": text, "model_id": MODEL, "language_code": "vi"},
    )
    r.raise_for_status()
    return r.content


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


def parse_turns(transcript: str) -> list[tuple[str, str]]:
    turns = []
    for line in transcript.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        speaker, _, text = line.partition(":")
        turns.append((speaker.strip(), text.strip()))
    return turns


async def gen_case(client, case, v_female, v_male) -> Path:
    turns = parse_turns(case["transcript"])
    speakers = list(dict.fromkeys(s for s, _ in turns))
    voice_of = {s: (v_female if i == 0 else v_male) for i, s in enumerate(speakers)}
    pcm_parts: list[bytes] = []
    for speaker, text in turns:
        pcm = await tts_pcm(client, voice_of[speaker], text)
        pcm_parts.append(pcm)
        pcm_parts.append(GAP)
    out = AUDIO_DIR / f"{case['id']}.wav"
    write_wav(out, b"".join(pcm_parts))
    return out


# ---------------------------------------------------------------- variants
def _read_pcm(path: Path) -> "np.ndarray":
    import numpy as np
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)


def _write_pcm(path: Path, x: "np.ndarray") -> None:
    import numpy as np
    x = np.clip(x, -32768, 32767).astype(np.int16)
    write_wav(path, x.tobytes())


async def gen_noise(client: httpx.AsyncClient, prompt: str, secs: float) -> Path:
    """ElevenLabs sound-generation → wav 16k mono (cache theo prompt)."""
    import hashlib
    import subprocess
    key = hashlib.sha1(prompt.encode()).hexdigest()[:12]
    out = NOISE_DIR / f"{key}.wav"
    if out.exists():
        return out
    r = await client.post(
        f"{settings.elevenlabs_base}/sound-generation",
        headers={"xi-api-key": settings.elevenlabs_key},
        json={"text": prompt, "duration_seconds": min(22, max(3, secs)),
              "prompt_influence": 0.4},
    )
    r.raise_for_status()
    mp3 = NOISE_DIR / f"{key}.mp3"
    mp3.write_bytes(r.content)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                    "-ar", str(RATE), "-ac", "1", str(out)], check=True)
    mp3.unlink()
    return out


def mix_noise(speech: "np.ndarray", noise: "np.ndarray", snr_db: float = 12.0) -> "np.ndarray":
    import numpy as np
    if len(noise) < len(speech):  # loop noise cho đủ dài
        noise = np.tile(noise, int(np.ceil(len(speech) / len(noise))))
    noise = noise[: len(speech)]
    rms_s = np.sqrt(np.mean(speech**2)) + 1e-9
    rms_n = np.sqrt(np.mean(noise**2)) + 1e-9
    gain = rms_s / (10 ** (snr_db / 20)) / rms_n
    return speech + noise * gain


def telephony(speech: "np.ndarray") -> "np.ndarray":
    """Giả lập điện thoại: bandpass 300–3400Hz (FFT) + nén nhẹ + méo lượng tử 8k."""
    import numpy as np
    spec = np.fft.rfft(speech)
    freqs = np.fft.rfftfreq(len(speech), 1 / RATE)
    spec[(freqs < 300) | (freqs > 3400)] = 0
    x = np.fft.irfft(spec, n=len(speech))
    x = np.tanh(x / 12000) * 14000          # nén nhẹ kiểu codec
    x8 = x[::2]                              # down 8k rồi up lại (mất chi tiết)
    x = np.repeat(x8, 2)[: len(speech)]
    return x


async def make_variants(client: httpx.AsyncClient, case: dict, tele_ids: set[str]) -> None:
    cid = case["id"]
    base = AUDIO_DIR / f"{cid}.wav"
    if not base.exists():
        return
    speech = _read_pcm(base)
    if case.get("noise"):
        n_path = await gen_noise(client, case["noise"], len(speech) / RATE)
        noisy = mix_noise(speech, _read_pcm(n_path), snr_db=12)
        _write_pcm(AUDIO_DIR / f"{cid}_noisy.wav", noisy)
        print(f"   🔊 {cid}_noisy.wav (SNR 12dB: {case['noise'][:40]}…)")
    if cid in tele_ids:
        _write_pcm(AUDIO_DIR / f"{cid}_telephony.wav", telephony(speech))
        print(f"   ☎️  {cid}_telephony.wav (bandpass 300-3400 + 8k)")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="vd: A,D")
    ap.add_argument("--variants", action="store_true", help="sinh biến thể noisy/telephony")
    ap.add_argument("--tele", default="B,G", help="case sinh bản telephony")
    ap.add_argument("--skip-clean", action="store_true", help="chỉ sinh variants")
    args = ap.parse_args()
    cases = CASES
    if args.only:
        keep = {x.strip().upper() for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in keep]

    async with httpx.AsyncClient(timeout=180) as client:
        if not args.skip_clean:
            vf, vm = await pick_voices(client)
            for case in cases:
                out_path = AUDIO_DIR / f"{case['id']}.wav"
                if out_path.exists():
                    print(f"⏭  {case['id']}: đã có, bỏ qua")
                    continue
                out = await gen_case(client, case, vf, vm)
                secs = out.stat().st_size / 2 / RATE
                print(f"✅ {case['id']}: {out.name} ({secs:.1f}s, {out.stat().st_size//1024}KB)")
        if args.variants:
            tele_ids = {x.strip().upper() for x in args.tele.split(",") if x.strip()}
            for case in cases:
                await make_variants(client, case, tele_ids)


if __name__ == "__main__":
    asyncio.run(main())
