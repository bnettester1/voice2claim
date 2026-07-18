"""Twilio REST tối thiểu qua httpx (không SDK) + TwiML + validate chữ ký.

Chỉ 2 thao tác: tạo outbound call trỏ TwiML về server mình, và kết thúc call.
Creds nạp từ app.config (env/apikey.txt) — không bao giờ log.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

import httpx

from app.config import settings


def _acc_base() -> str:
    return f"{settings.twilio_base}/Accounts/{settings.twilio_sid}"


def wss_base() -> str:
    return settings.public_base.replace("https://", "wss://").replace(
        "http://", "ws://")


def twiml_connect_stream(sid: str) -> str:
    """TwiML: nối audio 2 chiều cuộc gọi vào WS /ws/twilio/{sid} của mình."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Connect><Stream url="{wss_base()}/ws/twilio/{sid}"/>'
        "</Connect></Response>"
    )


async def start_call(sid: str, to: str, client: httpx.AsyncClient) -> str:
    """POST /Calls.json → Call SID. TwiML + status callback trỏ về public_base."""
    base = settings.public_base
    r = await client.post(
        f"{_acc_base()}/Calls.json",
        auth=(settings.twilio_sid, settings.twilio_token),
        data={
            "To": to,
            "From": settings.twilio_from,
            "Url": f"{base}/telephony/twiml?sid={sid}",
            "Method": "POST",
            "StatusCallback": f"{base}/telephony/status?sid={sid}",
            "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
        },
    )
    r.raise_for_status()
    return r.json()["sid"]


async def complete_call(call_sid: str, client: httpx.AsyncClient) -> None:
    r = await client.post(
        f"{_acc_base()}/Calls/{call_sid}.json",
        auth=(settings.twilio_sid, settings.twilio_token),
        data={"Status": "completed"},
    )
    r.raise_for_status()


def valid_signature(url_path_qs: str, form: dict[str, str],
                    signature: str | None) -> bool:
    """Kiểm tra X-Twilio-Signature (HMAC-SHA1). Không có token → cho qua (dev)."""
    if not settings.twilio_token:
        return True
    if not signature:
        return False
    base = settings.public_base + url_path_qs
    payload = base + "".join(k + str(v) for k, v in sorted(form.items()))
    digest = base64.b64encode(
        hmac.new(settings.twilio_token.encode(), payload.encode(),
                 hashlib.sha1).digest()).decode()
    return hmac.compare_digest(digest, signature)


def mask_phone(phone: str) -> str:
    return ("•" * max(0, len(phone) - 4)) + phone[-4:] if phone else ""
