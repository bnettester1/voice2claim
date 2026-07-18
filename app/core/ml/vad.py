"""silero-VAD (PyTorch) — phát hiện end-of-speech trên stream PCM16 16kHz.

Dùng trong LiveSession: feed từng frame; khi chuyển speech→silence đủ lâu
(END_SILENCE_MS) → trả True một lần để relay gửi audio.commit cho VALSEA RTT
(final transcript về sớm → extraction sớm).

Degrade sạch: thiếu torch/silero → available() = False, relay bỏ qua VAD.
"""
from __future__ import annotations

CHUNK = 512               # silero yêu cầu 512 mẫu @16k mỗi lần
END_SILENCE_MS = 800
SPEECH_PROB = 0.5

_model = None
_ok: bool | None = None


def available() -> bool:
    global _ok, _model
    if _ok is not None:
        return _ok
    try:
        from silero_vad import load_silero_vad
        _model = load_silero_vad()
        _ok = True
    except Exception:  # noqa: BLE001
        _ok = False
    return _ok


class EndOfSpeechDetector:
    def __init__(self) -> None:
        import numpy as np  # noqa: F401
        self.buf = b""
        self.in_speech = False
        self.silence_ms = 0.0
        self.enabled = available()

    def feed(self, pcm_frame: bytes) -> bool:
        """→ True đúng MỘT lần khi phát hiện kết thúc lượt nói."""
        if not self.enabled:
            return False
        import numpy as np
        import torch

        self.buf += pcm_frame
        fire = False
        need = CHUNK * 2
        while len(self.buf) >= need:
            chunk, self.buf = self.buf[:need], self.buf[need:]
            x = torch.from_numpy(
                np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0)
            prob = float(_model(x, 16000).item())
            dur_ms = CHUNK / 16000 * 1000
            if prob >= SPEECH_PROB:
                self.in_speech = True
                self.silence_ms = 0.0
            elif self.in_speech:
                self.silence_ms += dur_ms
                if self.silence_ms >= END_SILENCE_MS:
                    self.in_speech = False
                    self.silence_ms = 0.0
                    fire = True
        return fire
