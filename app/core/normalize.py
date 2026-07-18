"""Chuẩn hóa transcript theo itn_rules của Domain Pack — chạy TRƯỚC extraction
và trigger. Đây là lớp 'từ điển nghiệp vụ sửa ASR': thuật ngữ code-switch bị
nghe sai (EF→IF, AST/ALT→IST LT, tên thuốc) và ITN số+đơn vị (5 mg → 5mg).
"""
from __future__ import annotations

import re

from app.packs.loader import Pack

# quy tắc chung mọi pack: số + đơn vị viết liền
_UNIT_RE = re.compile(r"(\d)\s+(mg|mcg|g|ml|mmol/L|mmHg|%)\b", re.IGNORECASE)
# "3/8 mmol/L" do ASR đọc "ba chấm tám" thành phân số → 3.8
_DECIMAL_SLASH = re.compile(r"\b(\d)\s*/\s*(\d)\s*(mmol/L)\b")


def apply_itn(pack: Pack, text: str) -> str:
    if not text:
        return text
    out = _UNIT_RE.sub(r"\1\2", text)
    out = _DECIMAL_SLASH.sub(r"\1.\2 \3", out)
    for rule in pack.itn_rules:
        pat, rep = rule.get("pattern", ""), rule.get("replace", "")
        if not pat:
            continue
        try:
            if rule.get("regex"):
                out = re.sub(pat, rep, out, flags=re.IGNORECASE)
            else:
                out = re.sub(re.escape(pat), rep, out, flags=re.IGNORECASE)
        except re.error:
            continue
    return out
