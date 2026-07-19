"""Nạp API keys từ apikey.txt (hoặc env). TUYỆT ĐỐI không log/print giá trị key.

Format file chấp nhận linh hoạt, ví dụ:
    {VASEAL_API=xxx
    ELEVENTLAB=yyy
    GROQ=zzz}
Tên khóa được map bao dung (kể cả viết sai chính tả VASEAL/ELEVENTLAB).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY_FILE = REPO_ROOT / "apikey.txt"
NOTIFY_ENV = Path.home() / ".notify.env"   # chứa BREVO_API_KEY (xem memory brevo-email-setup)

# map tên trong file -> tên chuẩn
_ALIASES = {
    "valsea": {"VASEAL_API", "VALSEA_API", "VALSEA", "VASEAL", "VALSEA_API_KEY"},
    "elevenlabs": {"ELEVENTLAB", "ELEVENLABS", "ELEVENT_LAB", "ELEVEN_LABS", "ELEVENLABS_API_KEY"},
    "groq": {"GROQ", "GROQ_API", "GROQ_API_KEY"},
    # telephony (E8) — tuỳ chọn, thiếu thì mode twilio degrade
    "twilio_sid": {"TWILIO_SID", "TWILIO_ACCOUNT_SID", "TWILIO"},
    "twilio_token": {"TWILIO_TOKEN", "TWILIO_AUTH_TOKEN", "TWILIO_SECRET"},
    "twilio_from": {"TWILIO_FROM", "TWILIO_FROM_NUMBER", "TWILIO_NUMBER", "TWILIO_PHONE"},
    "public_base": {"PUBLIC_BASE_URL", "PUBLIC_URL", "NGROK_URL", "TUNNEL_URL"},
    "eleven_voice": {"ELEVENLABS_VOICE_ID", "ELEVEN_VOICE", "ELEVENLABS_VOICE"},
    "brevo": {"BREVO_API_KEY", "BREVO", "BREVO_KEY", "SENDINBLUE_API_KEY"},
    "notify_token": {"MCP_AUTH_TOKEN", "NOTIFY_TOKEN", "NOTIFY_API_TOKEN"},
    "tts_prefer": {"TTS_PREFER", "TTS_VENDOR"},
    # Qwen 3.5 open-weight — lớp LLM ĐỐI CHỨNG thử nghiệm (decision 0012),
    # KHÔNG nằm trên đường demo chính (0010 vẫn giữ cho pipeline chính)
    "qwen": {"QWEN_API", "QWEN_API_KEY", "QWEN", "DASHSCOPE_API_KEY"},
    "qwen_base": {"QWEN_BASE", "QWEN_BASE_URL"},
    "qwen_model": {"QWEN_MODEL"},
}
# env chuẩn (ưu tiên hơn file nếu đặt)
_ENV = {
    "valsea": "VALSEA_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY", "groq": "GROQ_API_KEY",
    "twilio_sid": "TWILIO_ACCOUNT_SID", "twilio_token": "TWILIO_AUTH_TOKEN",
    "twilio_from": "TWILIO_FROM_NUMBER", "public_base": "PUBLIC_BASE_URL",
    "eleven_voice": "ELEVENLABS_VOICE_ID", "brevo": "BREVO_API_KEY",
    "notify_token": "MCP_AUTH_TOKEN",
    "tts_prefer": "TTS_PREFER",
    "qwen": "QWEN_API_KEY", "qwen_base": "QWEN_BASE_URL", "qwen_model": "QWEN_MODEL",
}


@dataclass(frozen=True)
class Settings:
    valsea_key: str
    elevenlabs_key: str
    groq_key: str
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from: str = ""
    public_base: str = ""          # https://xxx (tunnel) — cho webhook/WSS Twilio
    eleven_voice: str = ""         # voice id ElevenLabs (rỗng = default trong tts.py)
    brevo_key: str = ""            # Brevo transactional email
    notify_token: str = ""         # notify REST (lookup khách/handler) — E10
    qwen_key: str = ""             # Qwen 3.5 đối chứng (0012) — apikey.txt/env
    qwen_base: str = ""            # endpoint Anthropic-compatible (workspace riêng)
    qwen_model: str = "qwen3.5-397b-a17b"   # open-weight flagship
    notify_base: str = "https://mcp-endpoint.luuhailong.com"
    tts_prefer: str = "valsea"     # valsea | elevenlabs — đồng nhất giọng cuộc gọi
    valsea_base: str = "https://api.valsea.ai/v1"
    valsea_rtt: str = "wss://api.valsea.ai/v1/realtime"
    groq_base: str = "https://api.groq.com/openai/v1"
    elevenlabs_base: str = "https://api.elevenlabs.io/v1"
    twilio_base: str = "https://api.twilio.com/2010-04-01"

    def __repr__(self) -> str:  # chống lộ key qua repr/log vô tình
        return "Settings(keys=<hidden>)"

    @property
    def twilio_ready(self) -> bool:
        return bool(self.twilio_sid and self.twilio_token and self.twilio_from
                    and self.public_base)

    def status(self) -> dict[str, bool]:
        """Chỉ trả về CÓ/KHÔNG cho từng key — an toàn để in."""
        return {
            "valsea": bool(self.valsea_key),
            "elevenlabs": bool(self.elevenlabs_key),
            "groq": bool(self.groq_key),
            "twilio": bool(self.twilio_sid and self.twilio_token and self.twilio_from),
            "public_url": bool(self.public_base),
            "brevo": bool(self.brevo_key),
            "qwen": bool(self.qwen_key and self.qwen_base),
        }


def _parse_keyfile(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8", errors="ignore")
    out: dict[str, str] = {}
    for line in raw.replace("{", "\n").replace("}", "\n").replace(",", "\n").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().upper()
        value = value.strip().strip('"').strip("'")
        if not value:
            continue
        for canon, aliases in _ALIASES.items():
            if name in aliases:
                out[canon] = value
    return out


def load_settings() -> Settings:
    # ưu tiên: env > apikey.txt (repo) > ~/.notify.env (máy)
    file_keys = {**_parse_keyfile(NOTIFY_ENV), **_parse_keyfile(KEY_FILE)}
    def pick(canon: str) -> str:
        return os.environ.get(_ENV[canon]) or file_keys.get(canon, "")
    return Settings(
        valsea_key=pick("valsea"),
        elevenlabs_key=pick("elevenlabs"),
        groq_key=pick("groq"),
        twilio_sid=pick("twilio_sid"),
        twilio_token=pick("twilio_token"),
        twilio_from=pick("twilio_from"),
        public_base=pick("public_base").rstrip("/"),
        eleven_voice=pick("eleven_voice"),
        brevo_key=pick("brevo"),
        notify_token=pick("notify_token"),
        qwen_key=pick("qwen"),
        qwen_base=pick("qwen_base").rstrip("/"),
        qwen_model=pick("qwen_model") or "qwen3.5-397b-a17b",
        tts_prefer=(pick("tts_prefer") or "valsea").lower(),
    )


settings = load_settings()
