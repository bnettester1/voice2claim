"""AI thẩm định rule-based — minh bạch, giải thích được từng điểm cộng/trừ.

config = {"base": 20, "out": "assessment",
          "rules": [{"when": {"path","op","value"}, "score": ±n, "reason": "…"}]}
→ {"risk_score": int 0-100, "reasons": ["Thiếu ảnh xe (+25)", …]}
Qwen second-opinion (nếu bật) chạy async Ở NGOÀI node này — không đổi routing.
"""
from __future__ import annotations

from app.workflow import expr


def score(ctx: dict, config: dict) -> dict:
    total = int(config.get("base", 50))
    reasons: list[str] = []
    for rule in config.get("rules", []):
        when = rule.get("when") or {}
        try:
            hit = expr.compare(expr.get_path(ctx, str(when.get("path", ""))),
                               str(when.get("op", "exists")),
                               when.get("value"))
        except Exception:  # noqa: BLE001 — rule hỏng thì bỏ qua, không chặn flow
            continue
        if hit:
            pts = int(rule.get("score", 0))
            total += pts
            reasons.append(f"{rule.get('reason', when.get('path'))}"
                           f" ({'+' if pts >= 0 else ''}{pts})")
    total = max(0, min(100, total))
    if not reasons:
        reasons.append(f"Không rule nào khớp — giữ điểm nền {config.get('base', 50)}")
    return {"risk_score": total, "reasons": reasons}
