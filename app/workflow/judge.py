"""Qwen judge — second opinion ASYNC sau ai_assess (0012/0013).

TUYỆT ĐỐI ngoài đường nóng: fire-and-forget, latency ~8s không chặn run;
thiếu key → im lặng không làm gì. Kết quả vào evaluations (rater qwen_judge)
để so trên bảng metrics — KHÔNG đổi routing của run.
"""
from __future__ import annotations

import json

from app.core import llm_qwen
from app.db.database import db, record_history, run_db
from app.db.dal import flywheel as dal_fw

_SYSTEM = (
    "Bạn là thẩm định viên bảo hiểm cấp cao, đóng vai trò ý kiến thứ hai "
    "(second opinion) cho hệ chấm rủi ro rule-based. Chỉ trả về JSON.")


def _prompt(fields: dict, assessment: dict) -> str:
    return (
        "Hồ sơ (field đã thu thập):\n"
        + json.dumps(fields, ensure_ascii=False, indent=1)
        + "\n\nHệ rule-based chấm: "
        + json.dumps(assessment, ensure_ascii=False)
        + "\n\nĐánh giá lại một cách độc lập. Trả về DUY NHẤT JSON:\n"
          '{"score_1_5": <1-5, 5 = hệ chấm rất hợp lý>, '
          '"risk_opinion": "<thấp|trung bình|cao>", '
          '"notes": "<2-3 câu tiếng Việt: đồng ý/khác biệt ở đâu, '
          'thiếu dữ kiện gì>"}')


async def second_opinion(run_id: int, fields: dict, assessment: dict) -> None:
    if not llm_qwen.ready():
        return
    try:
        msg = await llm_qwen.messages_create(
            system=_SYSTEM,
            messages=[{"role": "user",
                       "content": _prompt(fields, assessment)}],
            max_tokens=400, temperature=0.2)
        raw = llm_qwen.text_of(msg)
        data = llm_qwen._parse_json(raw)
        score = int(data.get("score_1_5") or 3)
        score = max(1, min(5, score))
        await run_db(
            dal_fw.upsert_evaluation, run_id, "qwen_judge", score,
            str(data.get("notes") or "")[:400], "qwen3.5",
            {"risk_opinion": data.get("risk_opinion"),
             "rule_based": assessment})
        def _note():
            with db() as conn:
                record_history(
                    conn, "run", str(run_id), "qwen_judge", "", "ai", "qwen3.5",
                    f"Qwen second-opinion: {score}/5 — "
                    f"{str(data.get('notes') or '')[:80]}")
        await run_db(_note)
    except Exception:  # noqa: BLE001 — judge lỗi không được ảnh hưởng run
        pass
