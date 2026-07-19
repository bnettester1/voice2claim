"""KB extraction — Qwen đọc tài liệu nghiệp vụ → draft workflow (0012/0013).

CHỈ là công cụ admin offline/async: chạy nền sau khi bấm nút, không nằm trên
đường batch/live/call. Thiếu key Qwen → API trả 'không khả dụng', UI ẩn nút.
v1 đọc file text/txt; audio phải transcribe trước (ngoài phạm vi nút này).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core import llm_qwen
from app.db.database import run_db
from app.db.dal import kb as dal_kb
from app.workflow.defs import NODE_TYPES, validate_graph

_SYSTEM = (
    "Bạn là kiến trúc sư quy trình nghiệp vụ. Đọc tài liệu và bóc tách thành "
    "MỘT workflow dạng đồ thị. Chỉ trả về JSON hợp lệ, không giải thích.")


def _prompt(text: str) -> str:
    types = ", ".join(NODE_TYPES.keys())
    return f"""Tài liệu nghiệp vụ (tiếng Việt):
---
{text[:6000]}
---
Bóc tách thành workflow đồ thị JSON đúng schema sau (node type CHỈ được dùng:
{types}):
{{"summary": "<3-4 câu tóm tắt nghiệp vụ>",
 "name": "<tên workflow tiếng Việt>",
 "key": "<key_snake_case>",
 "graph": {{
   "nodes": [{{"id": "start", "type": "start", "label": "…", "config": {{}}}},
             …,
             {{"id": "end_ok", "type": "end", "label": "…",
               "config": {{"outcome": "done"}}}}],
   "edges": [{{"from": "start", "to": "…"}}, …]
 }}}}
Bắt buộc: đúng 1 node start, ≥1 node end, mọi node (trừ end) có edge ra,
rẽ nhánh thì đặt điều kiện vào edge dạng {{"when": "path op value"}} hoặc
{{"else": true}}. Human task dùng type human_task với config
{{"role": "assessor|director|call_agent", "title": "…"}}."""


async def extract_document(doc_id: int) -> dict:
    """→ {ok, extraction_id?, error?} — gọi từ background task của route."""
    doc = await run_db(dal_kb.get_document, doc_id)
    if doc is None:
        return {"ok": False, "error": "không có tài liệu"}
    if not llm_qwen.ready():
        return {"ok": False, "error": "Qwen chưa cấu hình (0012)"}
    path = Path(doc["path"])
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent.parent / doc["path"]
    if doc["kind"] not in ("text",) or not path.exists():
        await run_db(dal_kb.set_doc_status, doc_id, "failed",
                     "v1 chỉ bóc tách file text")
        return {"ok": False, "error": "v1 chỉ hỗ trợ file text"}
    await run_db(dal_kb.set_doc_status, doc_id, "extracting")
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        msg = await llm_qwen.messages_create(
            system=_SYSTEM,
            messages=[{"role": "user", "content": _prompt(text)}],
            max_tokens=2500, temperature=0.2)
        data = llm_qwen._parse_json(llm_qwen.text_of(msg))
        graph = data.get("graph") or {}
        errors = validate_graph(graph)
        notes = "; ".join(errors) if errors else "graph hợp lệ"
        ext_id = await run_db(dal_kb.add_extraction, doc_id, data, "qwen",
                              notes)
        await run_db(dal_kb.set_doc_status, doc_id, "extracted",
                     str(data.get("summary") or "")[:400])
        return {"ok": True, "extraction_id": ext_id, "valid": not errors,
                "errors": errors}
    except Exception as exc:  # noqa: BLE001
        await run_db(dal_kb.set_doc_status, doc_id, "failed",
                     f"lỗi {type(exc).__name__}")
        return {"ok": False, "error": str(exc)[:150]}
