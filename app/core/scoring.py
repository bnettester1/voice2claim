"""FormScorer — chấm điểm form 0–100 + attention list + gate gửi.

score = 100 × (W_c·completeness + W_f·confidence + W_a·agreement + W_v·format)
- Thiếu field bắt buộc → cap 79.
- agreement (NER local PyTorch) chưa bật → phân bổ lại trọng số (degrade sạch).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.form_state import FormStore, _empty
from app.packs.loader import Pack


@dataclass
class ScoreResult:
    total: int
    grade: str                    # SAN_SANG | CAN_DOC_KY | NEN_SUA
    breakdown: dict = field(default_factory=dict)
    attention: list = field(default_factory=list)
    can_submit: bool = False
    needs_ack: bool = False

    def as_dict(self) -> dict:
        return {
            "total": self.total, "grade": self.grade, "breakdown": self.breakdown,
            "attention": self.attention, "can_submit": self.can_submit,
            "needs_ack": self.needs_ack,
        }


def _check_validator(rule: str, value, val) -> bool:
    if _empty(val):
        return True  # validator chỉ chấm khi có giá trị
    if rule == "regex":
        return bool(re.search(str(value), str(val)))
    if rule == "unit":
        items = val if isinstance(val, list) else [val]
        units = [str(u).lower() for u in (value or [])]
        return all(any(u in str(it).lower() for u in units) for it in items)
    return True


def score_form(pack: Pack, store: FormStore, agreement: float | None = None,
               ner_verdict: dict[str, bool] | None = None) -> ScoreResult:
    req = pack.required_fields()
    filled_req = [n for n in req if not _empty(store.fields[n].value)]
    completeness = len(filled_req) / len(req) if req else 1.0

    confs, missing_req = [], [n for n in req if n not in filled_req]
    for name, fs in store.fields.items():
        if _empty(fs.value):
            continue
        w = 2.0 if name in req else 1.0
        confs.append((min(1.0, fs.confidence), w))
    confidence = (
        sum(c * w for c, w in confs) / sum(w for _, w in confs) if confs else 0.0
    )

    v_total, v_pass, v_fails = 0, 0, []
    for v in pack.scoring.validators:
        val = store.fields.get(v.field)
        if val is None or _empty(val.value):
            continue
        v_total += 1
        if _check_validator(v.rule, v.value, val.value):
            v_pass += 1
        else:
            v_fails.append(v.field)
    format_ok = v_pass / v_total if v_total else 1.0

    if agreement is None:  # ML layer tắt → reweight
        w_c, w_f, w_a, w_v = 0.45, 0.40, 0.0, 0.15
        agreement = 0.0
    else:
        w_c, w_f, w_a, w_v = 0.40, 0.35, 0.15, 0.10

    total = round(100 * (w_c * completeness + w_f * confidence + w_a * agreement + w_v * format_ok))
    if missing_req:
        total = min(total, 79)

    attention = []
    for n in missing_req:
        f = pack.field(n)
        attention.append({"field": n, "label": f.label if f else n,
                          "reason": "Thiếu field bắt buộc", "level": "high"})
    for n in v_fails:
        f = pack.field(n)
        attention.append({"field": n, "label": f.label if f else n,
                          "reason": "Sai định dạng (validator)", "level": "high",
                          "evidence": store.fields[n].evidence})
    for n, fs in store.fields.items():
        if not _empty(fs.value) and fs.source != "user" and fs.confidence < 0.7:
            f = pack.field(n)
            attention.append({"field": n, "label": f.label if f else n,
                              "reason": f"Confidence thấp ({fs.confidence:.2f})",
                              "level": "warn", "evidence": fs.evidence})
    for n, ok_flag in (ner_verdict or {}).items():
        if not ok_flag and store.fields.get(n) and store.fields[n].source != "user":
            f = pack.field(n)
            attention.append({"field": n, "label": f.label if f else n,
                              "reason": "NER local (PyTorch) không xác nhận",
                              "level": "warn", "evidence": store.fields[n].evidence})

    th = pack.scoring.submit_threshold
    grade = "SAN_SANG" if total >= th else ("CAN_DOC_KY" if total >= 60 else "NEN_SUA")
    return ScoreResult(
        total=total, grade=grade,
        breakdown={
            "completeness": {"value": round(completeness * 100), "detail": f"{len(filled_req)}/{len(req)}"},
            "confidence": {"value": round(confidence * 100), "detail": f"{confidence:.2f}"},
            "agreement": {"value": round(agreement * 100), "detail": "ML off" if w_a == 0 else f"{agreement:.2f}"},
            "format": {"value": round(format_ok * 100), "detail": f"{v_pass}/{v_total}" if v_total else "—"},
        },
        attention=attention,
        can_submit=total >= 60,
        needs_ack=60 <= total < th,
    )
