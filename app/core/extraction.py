"""Semantic extraction — engine LOCAL, không LLM ngoài (18/07: all-in VALSEA).

Groq đã được gỡ toàn pilot theo chỉ đạo của Long (decision 0010). `extract()`
giữ nguyên chữ ký cũ cho batch/live/eval (client/model/fast được chấp nhận
nhưng bỏ qua); phần hiểu nghĩa nằm ở `app/core/extraction_local.py`:
anchor synonyms pack + chiến lược domain (catalog từ hint_terms) + VALSEA
semantic_tags + NER local PyTorch. Chạy trong thread để không chặn event loop
(NER inference).
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.extraction_local import extract_local
from app.packs.loader import Pack


def _stringify(v: Any) -> str:
    """dict/list → chuỗi đọc được (fix '[object Object]' trên UI)."""
    if isinstance(v, dict):
        return " — ".join(_stringify(x) for x in v.values() if x not in (None, "", []))
    if isinstance(v, list):
        return "; ".join(_stringify(x) for x in v if x not in (None, "", []))
    return str(v)


def _coerce_value(ftype: str, value: Any) -> Any:
    """Ép kiểu giá trị đúng schema field (list[str] / str / number)."""
    if value in (None, "", []):
        return None
    if ftype == "list":
        items = value if isinstance(value, list) else [value]
        return [_stringify(x) for x in items if x not in (None, "", [])]
    if ftype == "number":
        try:
            f = float(value)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return _stringify(value)
    if isinstance(value, (dict, list)):
        return _stringify(value)
    return value


async def extract(
    pack: Pack,
    transcript: str,
    prev_state: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,   # giữ tương thích chữ ký cũ
    model: str = "",                            # (không dùng — engine local)
    fast: bool = False,                         # (không dùng — local luôn nhanh)
    semantic_tags: list | None = None,          # VALSEA verbose_json (batch)
) -> dict[str, dict]:
    """→ {field_name: {value, confidence, evidence}} (rỗng nếu không bắt được gì)."""
    del client, model, fast
    try:
        fields = await asyncio.to_thread(
            extract_local, pack, transcript, prev_state, semantic_tags)
    except Exception:  # noqa: BLE001 — extraction không bao giờ đánh sập pipeline
        return {}
    out: dict[str, dict] = {}
    for name, v in fields.items():
        spec = pack.field(name)
        if spec is None or not isinstance(v, dict):
            continue
        out[name] = {
            "value": _coerce_value(spec.type, v.get("value")),
            "confidence": float(v.get("confidence") or 0.0),
            "evidence": str(v.get("evidence") or "")[:200],
        }
    return out
