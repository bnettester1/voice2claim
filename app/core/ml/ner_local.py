"""NER tiếng Việt local (PyTorch/transformers) — hybrid verifier.

Model: NlpHUST/ner-vietnamese-electra-base (PER/LOC/ORG/MISC, chạy CPU).
Vai trò: đối chiếu độc lập với LLM extraction → agreement đưa vào FormScorer
(0.15 trọng số) + cờ "NER không xác nhận" trong attention list.

Degrade sạch: thiếu torch/transformers/model → available() False → scorer
tự phân bổ lại trọng số (architecture.md §5.6).
"""
from __future__ import annotations

from functools import lru_cache

from app.core.triggers import normalize_vi

MODEL_ID = "NlpHUST/ner-vietnamese-electra-base"

# field → nhãn NER đối chiếu được
FIELD_LABELS = {
    "ten_khach_hang": {"PERSON", "PER"},
    "ten_benh_nhan": {"PERSON", "PER"},
    "vi_tri": {"LOCATION", "LOC"},
    "xe_khach": {"MISCELLANEOUS", "MISC"},
    "xe_lien_quan": {"MISCELLANEOUS", "MISC"},
}

_ok: bool | None = None


def available() -> bool:
    global _ok
    if _ok is not None:
        return _ok
    try:
        _pipe()
        _ok = True
    except Exception:  # noqa: BLE001
        _ok = False
    return _ok


@lru_cache(maxsize=1)
def _pipe():
    from transformers import pipeline
    return pipeline("token-classification", model=MODEL_ID,
                    aggregation_strategy="simple", device=-1)


def entities(text: str) -> list[dict]:
    """→ [{label, text}] (đã gộp subword)."""
    out = []
    for e in _pipe()(text[:4000]):
        out.append({"label": e["entity_group"].upper(), "text": e["word"].strip()})
    return out


def agreement(transcript: str, field_values: dict) -> tuple[float | None, dict[str, bool]]:
    """So field ↔ entity NER. → (tỉ lệ khớp 0..1 hoặc None nếu không so được,
    {field: khớp?})."""
    checkable = {n: v for n, v in field_values.items()
                 if n in FIELD_LABELS and v not in (None, "", [])}
    if not checkable or not available():
        return None, {}
    ents = entities(transcript)
    verdict: dict[str, bool] = {}
    for name, value in checkable.items():
        want = FIELD_LABELS[name]
        val_norm = normalize_vi(str(value))
        hit = False
        for e in ents:
            if e["label"] in want:
                ent_norm = normalize_vi(e["text"])
                if ent_norm and (ent_norm in val_norm or val_norm in ent_norm
                                 or any(t in val_norm.split() for t in ent_norm.split())):
                    hit = True
                    break
        verdict[name] = hit
    score = sum(verdict.values()) / len(verdict)
    return score, verdict
