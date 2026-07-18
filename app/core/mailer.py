"""Gửi mail ticket qua Brevo transactional API (POST /v3/smtp/email).

Theo phương án đã chốt: template Jinja2 NHÚNG trong server — engine chỉ truyền
data có cấu trúc, không tự soạn nội dung mail. Sender dùng địa chỉ đã verify
trên Brevo. Key đọc qua app/config.py (không bao giờ in/log).

Lưu ý vận hành (đã gặp thật):
- Tài khoản Brevo bật Authorised IPs → gọi từ IP lạ bị 401 "unrecognised IP"
  → trả status rõ ràng kèm hướng dẫn whitelist, không làm vỡ flow gửi form.
- Mail transactional KHÔNG bị chặn bởi unsubscribe marketing.
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx
from jinja2 import Template

from app.config import settings
from app.packs.loader import Pack

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
SENDER = {"name": "Speech-to-Meaning Pilot", "email": "long@luuhailong.com"}

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "out"

_CUSTOMER_TPL = Template("""\
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#1c2340">
  <h2 style="color:#2b4ecc">Đã tiếp nhận yêu cầu của quý khách</h2>
  <p>Kính gửi quý khách,</p>
  <p>Hệ thống đã tiếp nhận và lập hồ sơ từ cuộc trao đổi với nhân viên:</p>
  <table style="border-collapse:collapse;width:100%;font-size:14px">
    <tr><td style="padding:6px;border:1px solid #d8ddf0;width:38%"><b>Mã hồ sơ</b></td>
        <td style="padding:6px;border:1px solid #d8ddf0">{{ ticket_id }}</td></tr>
    <tr><td style="padding:6px;border:1px solid #d8ddf0"><b>Loại yêu cầu</b></td>
        <td style="padding:6px;border:1px solid #d8ddf0">{{ action_label }}</td></tr>
    <tr><td style="padding:6px;border:1px solid #d8ddf0"><b>Thời gian</b></td>
        <td style="padding:6px;border:1px solid #d8ddf0">{{ ts }}</td></tr>
  </table>
  {% if summary %}<p><b>Tóm tắt:</b> {{ summary }}</p>{% endif %}
  <p>Chi tiết hồ sơ trong file PDF đính kèm.
  {% if recording_link %}Quý khách có thể nghe lại đoạn trao đổi
  <a href="{{ recording_link }}">tại đây</a>.{% endif %}</p>
  <p style="color:#667">Email tự động từ hệ thống Voice-to-Form (VALSEA ASR) —
  vui lòng không trả lời email này.</p>
</div>""")

_HANDLER_TPL = Template("""\
<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;color:#1c2340">
  <h2 style="color:#b3261e">[{{ priority }}] Ticket mới {{ ticket_id }} — {{ action_id }}</h2>
  <table style="border-collapse:collapse;width:100%;font-size:13.5px">
    <tr><td style="padding:6px;border:1px solid #d8ddf0;width:30%"><b>Pack</b></td>
        <td style="padding:6px;border:1px solid #d8ddf0">{{ pack_name }}</td></tr>
    <tr><td style="padding:6px;border:1px solid #d8ddf0"><b>Điểm form / người duyệt</b></td>
        <td style="padding:6px;border:1px solid #d8ddf0">{{ score }} · {{ reviewer }}</td></tr>
    {% for label, val in rows %}
    <tr><td style="padding:6px;border:1px solid #d8ddf0"><b>{{ label }}</b></td>
        <td style="padding:6px;border:1px solid #d8ddf0">{{ val }}</td></tr>
    {% endfor %}
  </table>
  {% if service_log %}<p style="font-size:13px"><b>Service log (AI):</b> {{ service_log }}</p>{% endif %}
  <p>
    {% if recording_link %}🎧 <a href="{{ recording_link }}">Nghe lại băng ghi âm</a> · {% endif %}
    📄 PDF đính kèm · 🖥️ <a href="{{ console_link }}">Mở Console</a>
  </p>
  <details><summary style="cursor:pointer"><b>Transcript đầy đủ</b></summary>
    <p style="font-size:12.5px;white-space:pre-wrap;background:#f4f6ff;padding:10px;border-radius:8px">{{ transcript }}</p>
  </details>
  <p style="color:#667;font-size:12px">Hồ sơ lập tự động từ giọng nói — kênh Voice-to-Form (VALSEA ASR).</p>
</div>""")


def _fmt(v) -> str:
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


async def _send_one(client: httpx.AsyncClient, to: str, subject: str,
                    html: str, attachments: list[dict]) -> dict:
    if not to:
        return {"to": "-", "ok": False, "detail": "thiếu địa chỉ"}
    if not settings.brevo_key:
        return {"to": to, "ok": False,
                "detail": "thiếu BREVO_API_KEY (~/.notify.env hoặc apikey.txt)"}
    payload = {
        "sender": SENDER,
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html,
    }
    if attachments:
        payload["attachment"] = attachments
    try:
        r = await client.post(BREVO_URL, json=payload,
                              headers={"api-key": settings.brevo_key,
                                       "accept": "application/json"},
                              timeout=15)
    except httpx.HTTPError as e:
        return {"to": to, "ok": False, "detail": f"lỗi mạng: {str(e)[:80]}"}
    if r.status_code in (200, 201):
        return {"to": to, "ok": True, "detail": "đã gửi"}
    body = r.text[:160]
    if r.status_code == 401 and "ip" in body.lower():
        return {"to": to, "ok": False,
                "detail": "Brevo chặn IP lạ — thêm IP này tại app.brevo.com/security/authorised_ips"}
    return {"to": to, "ok": False, "detail": f"HTTP {r.status_code}: {body}"}


async def send_ticket_emails(
    pack: Pack, ticket: dict, values: dict, transcript: str,
    pdf_url: str, recording_url: str, base_url: str,
    customer_email: str, handler_email: str,
    narrative: str = "", service_log: dict | None = None,
) -> list[dict]:
    base = (base_url or "").rstrip("/")
    rec_link = f"{base}{recording_url}" if (recording_url and base) else ""
    console_link = f"{base}/" if base else "#"

    attachments: list[dict] = []
    if pdf_url:
        pdf_path = OUT_DIR / Path(pdf_url).name
        if pdf_path.exists():
            attachments.append({
                "name": pdf_path.name,
                "content": base64.b64encode(pdf_path.read_bytes()).decode(),
            })

    rows = []
    for f in pack.all_fields():
        v = values.get(f.name)
        if v not in (None, "", []):
            rows.append((f.label, _fmt(v)))

    statuses: list[dict] = []
    async with httpx.AsyncClient() as client:
        if customer_email:
            html = _CUSTOMER_TPL.render(
                ticket_id=ticket["id"], action_label=ticket["action_label"],
                ts=ticket["ts"], summary=narrative[:400],
                recording_link=rec_link)
            statuses.append(await _send_one(
                client, customer_email,
                f"[{ticket['id']}] Xác nhận tiếp nhận — {ticket['action_label']}",
                html, attachments))
        if handler_email:
            sl = ""
            if service_log:
                sl = "; ".join(f"{k}: {v}" for k, v in list(service_log.items())[:6]
                               if not isinstance(v, (dict, list)))
            html = _HANDLER_TPL.render(
                ticket_id=ticket["id"], action_id=ticket["action"],
                priority=ticket.get("priority", "—"), pack_name=pack.name,
                score=(ticket.get("audit") or {}).get("score", "—"),
                reviewer=(ticket.get("audit") or {}).get("reviewer", "—"),
                rows=rows, service_log=sl, transcript=transcript[:6000],
                recording_link=rec_link, console_link=console_link)
            statuses.append(await _send_one(
                client, handler_email,
                f"[{ticket.get('priority','')}] {ticket['id']} {ticket['action']} — cần xử lý",
                html, attachments))
    return statuses
