"""Codec G.711 μ-law + resample (numpy thuần) cho chân Twilio Media Streams.

Twilio gửi/nhận audio/x-mulaw 8kHz mono; VALSEA RTT cần PCM16 16kHz mono.
Không dùng audioop (bị gỡ ở Python 3.13) — tự cài μ-law bằng LUT/vector numpy.
"""
from __future__ import annotations

import io
import wave

import numpy as np

_BIAS = 0x84
_CLIP = 32635

# LUT decode: byte μ-law (0-255) -> int16
_dec = np.empty(256, dtype=np.int16)
for _u in range(256):
    _v = ~_u & 0xFF
    _sign = _v & 0x80
    _exp = (_v >> 4) & 0x07
    _man = _v & 0x0F
    _s = (((_man << 3) + _BIAS) << _exp) - _BIAS
    _dec[_u] = -_s if _sign else _s


def ulaw_decode(data: bytes) -> np.ndarray:
    """bytes μ-law → np.int16."""
    return _dec[np.frombuffer(data, dtype=np.uint8)]


def ulaw_encode(samples: np.ndarray) -> bytes:
    """np.int16 → bytes μ-law (G.711)."""
    x = samples.astype(np.int32)
    sign = np.where(x < 0, 0x80, 0)
    x = np.minimum(np.abs(x), _CLIP) + _BIAS
    exp = np.floor(np.log2(np.maximum(x >> 7, 1))).astype(np.int32)
    man = (x >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | man) & 0xFF).astype(np.uint8).tobytes()


def resample(samples: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Linear-interp resample int16 mono (đủ tốt cho thoại 8k↔16k)."""
    if sr_from == sr_to or samples.size == 0:
        return samples
    n_out = int(round(samples.size * sr_to / sr_from))
    xp = np.arange(samples.size, dtype=np.float64)
    xq = np.linspace(0, samples.size - 1, n_out)
    return np.interp(xq, xp, samples.astype(np.float64)).astype(np.int16)


def ulaw8k_to_pcm16k(data: bytes) -> bytes:
    """Chiều nghe: Twilio μ-law 8k → PCM16 16k cho VALSEA RTT."""
    return resample(ulaw_decode(data), 8000, 16000).tobytes()


def pcm16_to_ulaw8k(pcm: bytes, sr_from: int = 16000) -> bytes:
    """Chiều nói: PCM16 (sr_from) → μ-law 8k cho Twilio."""
    samples = np.frombuffer(pcm, dtype=np.int16)
    return ulaw_encode(resample(samples, sr_from, 8000))


def wav_to_ulaw8k(wav_bytes: bytes) -> bytes:
    """WAV PCM16 mono/stereo bất kỳ sample-rate → μ-law 8k (fallback VALSEA TTS)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise ValueError(f"wav sampwidth {sw} != 2")
    samples = np.frombuffer(raw, dtype=np.int16)
    if ch > 1:
        samples = samples.reshape(-1, ch).mean(axis=1).astype(np.int16)
    return ulaw_encode(resample(samples, sr, 8000))
