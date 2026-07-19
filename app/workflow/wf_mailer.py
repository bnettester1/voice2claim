"""Email workflow (Brevo qua mailer._send_one) — 6 template nghiệp vụ nhúng.

Mọi biến render từ run context bằng dotted path {customer.name}. Thiếu Brevo
key → trả status skipped, run vẫn chạy tiếp (degrade sạch).
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx
from jinja2 import Template

from app.core.mailer import _send_one
from app.workflow.expr import get_path

_BASE_CSS = """
  body{font-family:Arial,Helvetica,sans-serif;background:#f2f4fb;margin:0;padding:24px}
  .card{max-width:620px;margin:0 auto;background:#fff;border-radius:14px;
        padding:28px 30px;border:1px solid #e3e7f5}
  h2{margin:0 0 6px;color:#1f2a56}
  p{color:#333;line-height:1.65;font-size:14.5px}
  .muted{color:#7a83ab;font-size:12px}
  .btn{display:inline-block;background:#4f7cff;color:#fff!important;font-weight:700;
       padding:12px 26px;border-radius:10px;text-decoration:none;margin:14px 0}
  .row{padding:7px 0;border-bottom:1px dashed #e3e7f5;font-size:13.5px}
  .row b{color:#1f2a56}
  .stars a{font-size:26px;text-decoration:none;margin-right:4px}
"""

_TEMPLATES: dict[str, dict] = {
    "esign_request": {
        "subject": "[Voice2Claim] Hợp đồng {{ policy_no }} — mời {{ name }} ký điện tử",
        "body": """
<h2>Kính gửi {{ name }},</h2>
<p>Hồ sơ mở hợp đồng <b>{{ product }}</b> của mình đã được thẩm định
<b>ĐẠT</b>{% if risk_score %} (điểm rủi ro {{ risk_score }}/100){% endif %}.
Hợp đồng đính kèm email này, mời anh/chị xem lại và ký điện tử:</p>
<p style="text-align:center"><a class="btn" href="{{ sign_url }}">✍️ Xem &amp; ký hợp đồng</a></p>
<p class="muted">Link ký dùng một lần, dành riêng cho anh/chị. Nếu không thực
hiện yêu cầu này, vui lòng bỏ qua email.</p>""",
    },
    "esign_confirmed": {
        "subject": "[Voice2Claim] Hợp đồng {{ policy_no }} đã có hiệu lực 🎉",
        "body": """
<h2>Chúc mừng {{ name }}!</h2>
<p>Hợp đồng <b>{{ product }}</b> (số <b>{{ policy_no }}</b>) đã được ký lúc
{{ signed_at }} và <b>chính thức có hiệu lực</b>. Bản PDF đính kèm email.</p>
{% if rate_url %}<p>Anh/chị chấm điểm trải nghiệm mở hợp đồng giúp công ty nhé:</p>
<p class="stars">{% for s in range(1,6) %}<a href="{{ rate_url }}?stars={{ s }}">⭐</a>{% endfor %}</p>{% endif %}
<p class="muted">Cảm ơn anh/chị đã tin tưởng.</p>""",
    },
    "decision_result": {
        "subject": "[Voice2Claim] Kết quả hồ sơ {{ ref }} — {{ 'ĐƯỢC DUYỆT' if approved else 'TỪ CHỐI' }}",
        "body": """
<h2>Kính gửi {{ name }},</h2>
{% if approved %}
<p>Hồ sơ <b>{{ ref }}</b> đã được <b style="color:#1fa863">DUYỆT</b>.
{% if amount %}Số tiền chi trả: <b>{{ amount }} VNĐ</b> sẽ đến tài khoản của
anh/chị trong 5 ngày làm việc.{% endif %}</p>
{% else %}
<p>Rất tiếc, hồ sơ <b>{{ ref }}</b> ở trạng thái <b style="color:#c0392b">TỪ CHỐI</b>.
{% if reason %}Lý do: {{ reason }}.{% endif %} Bộ phận phúc tra sẽ liên hệ nếu
anh/chị cần giải thích thêm.</p>
{% endif %}
{% if rate_url %}<p>Chấm điểm quy trình xử lý giúp công ty cải tiến:</p>
<p class="stars">{% for s in range(1,6) %}<a href="{{ rate_url }}?stars={{ s }}">⭐</a>{% endfor %}</p>{% endif %}""",
    },
    "claim_update": {
        "subject": "[Voice2Claim] Hồ sơ {{ ref }} — đã giám định hiện trường",
        "body": """
<h2>Kính gửi {{ name }},</h2>
<p>Thẩm định viên đã hoàn tất giám định hiện trường cho hồ sơ <b>{{ ref }}</b>.
Biên bản giám định (kèm bóc băng ghi âm bằng AI) đính kèm email này.</p>
<p>Hồ sơ chuyển sang bước <b>trình duyệt chi trả</b> — công ty sẽ thông báo
kết quả trong thời gian sớm nhất.</p>""",
    },
    "task_assigned": {
        "subject": "[Voice2Claim] Việc mới: {{ title }}",
        "body": """
<h2>Chào {{ assignee }},</h2>
<p>Bạn vừa được giao: <b>{{ title }}</b>{% if ref %} — hồ sơ <b>{{ ref }}</b>{% endif %}.</p>
{% if summary %}<div class="row">{{ summary }}</div>{% endif %}
<p style="text-align:center"><a class="btn" href="{{ task_url }}">📥 Mở hộp công việc</a></p>""",
    },
    "rating_request": {
        "subject": "[Voice2Claim] {{ name }} ơi, chấm điểm trải nghiệm giúp công ty nhé",
        "body": """
<h2>Kính gửi {{ name }},</h2>
<p>Quy trình <b>{{ wf_name }}</b> của anh/chị vừa hoàn tất. Một cú click của
anh/chị giúp công ty tự cải tiến quy trình (flywheel):</p>
<p class="stars">{% for s in range(1,6) %}<a href="{{ rate_url }}?stars={{ s }}">⭐</a>{% endfor %}</p>""",
    },
}


def render(template_id: str, vars: dict) -> tuple[str, str]:
    tpl = _TEMPLATES.get(template_id)
    if tpl is None:
        raise KeyError(f"không có template email '{template_id}'")
    subject = Template(tpl["subject"]).render(**vars)
    body = Template(tpl["body"]).render(**vars)
    html = f"<html><head><style>{_BASE_CSS}</style></head><body>" \
           f"<div class='card'>{body}" \
           f"<p class='muted' style='margin-top:18px'>Email tự động từ" \
           f" Voice2Claim — hệ thống giám định thông minh bằng giọng nói.</p></div>" \
           f"</body></html>"
    return subject, html


def resolve_to(ctx: dict, to_spec: str) -> str:
    """'customer.email' (path) | 'role:assessor' | địa chỉ literal."""
    to_spec = str(to_spec or "").strip()
    if not to_spec:
        return ""
    if to_spec.startswith("role:"):
        from app.db.dal import erp as dal_erp
        rows = dal_erp.employees_by_role(to_spec.split(":", 1)[1])
        return rows[0]["email"] if rows else ""
    if "@" in to_spec:
        return to_spec
    val = get_path(ctx, to_spec)
    return str(val or "")


def attachment_from_path(path: str) -> dict | None:
    p = Path(path)
    if not p.exists() or p.stat().st_size > 8_000_000:
        return None
    return {"name": p.name,
            "content": base64.b64encode(p.read_bytes()).decode()}


async def send(client: httpx.AsyncClient, template_id: str, to: str,
               vars: dict, attach_paths: list[str] | None = None) -> dict:
    if not to:
        return {"to": "-", "ok": False, "detail": "không resolve được người nhận"}
    subject, html = render(template_id, vars)
    attachments = []
    for path in attach_paths or []:
        a = attachment_from_path(path)
        if a:
            attachments.append(a)
    return await _send_one(client, to, subject, html, attachments)
