"""Qwen 3.5 open-weight qua CHUẨN ANTHROPIC Messages API (decision 0012).

Lớp LLM ĐỐI CHỨNG thử nghiệm theo chỉ đạo Long 19/07 — KHÔNG nằm trên đường
demo chính: extraction_local (decision 0010) vẫn là engine mặc định của
batch/live/call. Module này phục vụ eval so sánh (scripts/eval_qwen.py) và là
ứng viên tầng "LLM judge" cho action-fire nếu Long chốt hybrid sau này.

Endpoint: workspace MaaS riêng của Long, path `/v1/messages` đúng format
Anthropic (content blocks, stop_reason, usage); khác gốc ở auth — dùng
`Authorization: Bearer` (x-api-key bị 401, đã probe 19/07). Key/base/model
nạp qua app/config.py (apikey.txt / env) — TUYỆT ĐỐI không log key.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx

from app.config import settings
from app.packs.loader import Pack

TIMEOUT = 90.0          # model MoE lớn + transcript dài: cho trần thoáng
MAX_TOKENS = 2500       # đủ cho JSON ~15 field + actions


class QwenError(RuntimeError):
    pass


def ready() -> bool:
    return bool(settings.qwen_key and settings.qwen_base)


async def messages_create(
    *,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int = MAX_TOKENS,
    temperature: float = 0.0,
    model: str = "",
    client: httpx.AsyncClient | None = None,
) -> dict:
    """POST /v1/messages theo chuẩn Anthropic — trả Message object (dict)."""
    if not ready():
        raise QwenError("Thiếu QWEN_API/QWEN_BASE (apikey.txt hoặc env)")
    body = {
        "model": model or settings.qwen_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {settings.qwen_key}",
        "anthropic-version": "2023-06-01",
    }
    url = f"{settings.qwen_base}/v1/messages"
    own = client is None
    cl = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        for attempt in (1, 2):
            try:
                r = await cl.post(url, headers=headers, json=body, timeout=TIMEOUT)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise QwenError(f"Mạng: {type(e).__name__}") from e
                await asyncio.sleep(1.5)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503) and attempt == 1:
                await asyncio.sleep(2.0)
                continue
            raise QwenError(f"HTTP {r.status_code}: {r.text[:200]}")
        raise QwenError("unreachable")
    finally:
        if own:
            await cl.aclose()


def text_of(msg: dict) -> str:
    return "".join(
        b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text")


def _parse_json(raw: str) -> dict:
    """JSON robust: bóc ```fence```, cắt từ '{' đầu đến '}' cân bằng."""
    s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw.strip())
    start = s.find("{")
    if start < 0:
        raise QwenError("Không thấy JSON trong output")
    depth = 0
    for i, ch in enumerate(s[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(s[start:i + 1])
    return json.loads(s[start:])  # để json bắn lỗi chi tiết


def _prompt(pack: Pack, transcript: str) -> tuple[str, str]:
    fl: list[str] = []
    for spec in pack.all_fields():
        extra = ""
        if spec.type == "enum" and spec.options:
            extra = f" — chọn 1 trong: {spec.options}"
        elif spec.type == "list":
            extra = " — trả list[str]"
        elif spec.synonyms:
            extra = f" (gợi ý cách gọi: {', '.join(spec.synonyms[:4])})"
        fl.append(f"- {spec.name} ({spec.type}): {spec.label}{extra}")
    al: list[str] = []
    for a in pack.actions:
        al.append(f"- {a.id}: {a.label} | câu kích hoạt kiểu: {a.triggers[:3]}")
    system = (
        "Bạn là engine phân tích hội thoại nghiệp vụ tiếng Việt (call center "
        "bảo hiểm / khám bệnh). Chỉ trả về MỘT object JSON hợp lệ, không văn "
        "bản nào ngoài JSON, không markdown fence.")
    user = f"""Phân tích transcript và trả JSON đúng schema:
{{"fields": {{"<tên_field>": {{"value": <giá trị>, "confidence": <0..1>, "evidence": "<trích ngắn từ transcript>"}}}},
 "actions": [{{"id": "<action_id>", "fire": true|false, "reason": "<vì sao>"}}]}}

FIELD cần bắt (chỉ đưa field có trong transcript, đúng tên; number trả số; date dd/mm/yyyy):
{chr(10).join(fl)}

ACTION cần phán định (liệt kê ĐỦ mọi action dưới đây trong "actions"):
{chr(10).join(al)}

LUẬT nhận action (semantic của hệ thống call center — cụm kích hoạt là LỆNH điều khiển):
1. "fire": true khi trong transcript CÓ NGƯỜI NÓI RA cụm kích hoạt của action — dưới mọi dạng: ra lệnh, nhờ, hay nhắc thao tác ("bấm nút X giúp em", "nhớ bấm nút X", "gửi yêu cầu X nhé"). Người nói thường là giám định viên/bác sĩ điều khiển hệ thống.
2. NGOẠI LỆ DUY NHẤT → "fire": false: ngay trước/trong cụm đó có phủ định hoặc trì hoãn tường minh (đừng, khoan, thôi, chưa cần, không cần, để sau, hỏi ... đã).
3. Không ai nói cụm kích hoạt tương ứng (chỉ kể sự việc) → "fire": false.

TRANSCRIPT:
{transcript}"""
    return system, user


async def analyze(
    pack: Pack,
    transcript: str,
    *,
    model: str = "",
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Phân tích + nhận action bằng Qwen. → {fields, actions, latency_ms, model}

    fields: {name: {value, confidence, evidence}} — cùng shape extraction.extract()
    actions: [{id, fire, reason}] — đủ mọi action của pack.
    """
    system, user = _prompt(pack, transcript)
    t0 = time.perf_counter()
    msg = await messages_create(
        system=system,
        messages=[{"role": "user", "content": user}],
        model=model,
        client=client,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    data = _parse_json(text_of(msg))
    fields_out: dict[str, dict] = {}
    for name, v in (data.get("fields") or {}).items():
        if pack.field(name) is None:
            continue
        if isinstance(v, dict):
            fields_out[name] = {
                "value": v.get("value"),
                "confidence": float(v.get("confidence") or 0.0),
                "evidence": str(v.get("evidence") or "")[:200],
            }
        elif v not in (None, "", []):
            fields_out[name] = {"value": v, "confidence": 0.5, "evidence": ""}
    known = {a.id for a in pack.actions}
    actions_out = [
        {"id": a.get("id"), "fire": bool(a.get("fire")),
         "reason": str(a.get("reason") or "")[:200]}
        for a in (data.get("actions") or [])
        if isinstance(a, dict) and a.get("id") in known
    ]
    usage = msg.get("usage") or {}
    return {
        "fields": fields_out,
        "actions": actions_out,
        "latency_ms": latency_ms,
        "model": msg.get("model") or (model or settings.qwen_model),
        "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens")},
    }
