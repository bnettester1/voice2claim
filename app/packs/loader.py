"""Domain Pack loader — validate bằng Pydantic, build hint_text cho VALSEA RTT."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field as PField

PACKS_DIR = Path(__file__).resolve().parent.parent.parent / "packs"


class FieldSpec(BaseModel):
    name: str
    label: str
    type: Literal["text", "number", "date", "enum", "list", "textarea"]
    required: bool = False
    synonyms: list[str] = []
    options: list[str] = []          # cho enum
    itn: bool = False
    item_hint: str = ""              # cho list


class SectionSpec(BaseModel):
    title: str
    fields: list[FieldSpec]


class FormSpec(BaseModel):
    title: str
    sections: list[SectionSpec]


class ActionSpec(BaseModel):
    id: str
    label: str
    triggers: list[str]
    confirm: Literal["auto", "click"] = "click"
    required_fields: list[str] = []
    tts_confirm: str = ""
    template: str = ""


class SpecialtySpec(BaseModel):
    label: str
    hint_terms: list[str] = []


class ValidatorSpec(BaseModel):
    field: str
    rule: Literal["regex", "unit"]
    value: object


class ScoringSpec(BaseModel):
    submit_threshold: int = 85
    validators: list[ValidatorSpec] = []


class FewShot(BaseModel):
    transcript: str
    expected: dict


class CallStep(BaseModel):
    """Một lượt hỏi trong kịch bản gọi ra (outbound agent call)."""
    field: str
    ask: str
    reask: str = ""            # câu hỏi lại khi im lặng/không bắt được giá trị
    confirm_tpl: str = ""      # "" = không đọc xác nhận; {value} được thay thế


class CallScriptSpec(BaseModel):
    greeting: str
    closing: str
    closing_partial: str = ""  # khi kết thúc mà vẫn thiếu field
    steps: list[CallStep]
    reask_after_secs: float = 6.0


class IntentSpec(BaseModel):
    """Một workflow nghiệp vụ trong tổng đài — chọn bằng keyword router."""
    id: str
    label: str
    keywords: list[str]                 # match fuzzy trên câu trả lời tự do
    empathy: str = ""                   # câu mở lời trước khi hỏi tiếp
    steps: list[CallStep] = []          # field cần thu thập (chỉ hỏi cái TRỐNG)
    reply_tpl: str = ""                 # trả lời từ hồ sơ lookup ({claim_id}…)
    confirm_tpl: str = ""               # đọc xác nhận cuối ({summary})
    action: str = ""                    # action id trong pack.actions để fire


class CallFlowsSpec(BaseModel):
    """Tổng đài đa-workflow (E10): identify → lookup → intent → steps → action."""
    greeting: str
    identify: list[CallStep] = []
    lookup_wait: str = ""
    lookup_found_tpl: str = ""          # {ten}, {summary}
    lookup_miss: str = ""
    menu_prompt: str = ""               # hỏi "anh cần hỗ trợ gì"
    unknown_intent: str = ""
    ask_more: str = ""                  # "anh cần gì thêm không ạ?"
    closing: str = ""
    intents: list[IntentSpec] = []
    reask_after_secs: float = 7.0


class Pack(BaseModel):
    id: str
    name: str
    icon: str = "📋"
    form: FormSpec
    actions: list[ActionSpec]
    specialties: dict[str, SpecialtySpec] = {}
    hint_terms: list[str] = []
    itn_rules: list[dict] = []
    few_shots: list[FewShot] = []
    extraction_instructions: str = ""
    scoring: ScoringSpec = ScoringSpec()
    call_script: Optional[CallScriptSpec] = None   # kịch bản outbound call (E8)
    call_flows: Optional[CallFlowsSpec] = None     # tổng đài đa-workflow (E10)
    prefill: dict[str, object] = {}                # dữ liệu hồ sơ gốc (demo)

    # ---- helpers ----
    def all_fields(self) -> list[FieldSpec]:
        return [f for s in self.form.sections for f in s.fields]

    def field(self, name: str) -> Optional[FieldSpec]:
        for f in self.all_fields():
            if f.name == name:
                return f
        return None

    def required_fields(self) -> list[str]:
        return [f.name for f in self.all_fields() if f.required]

    def action(self, action_id: str) -> Optional[ActionSpec]:
        for a in self.actions:
            if a.id == action_id:
                return a
        return None

    def hint_text(self, max_chars: int = 950) -> str:
        """Từ điển nghiệp vụ → chuỗi hint cho VALSEA RTT (ưu tiên trigger + thuật ngữ)."""
        parts: list[str] = []
        seen: set[str] = set()

        def add(term: str) -> None:
            t = term.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                parts.append(t)

        for a in self.actions:
            for t in a.triggers[:2]:
                add(t)
        for t in self.hint_terms:
            add(t)
        for sp in self.specialties.values():
            for t in sp.hint_terms:
                add(t)
        for f in self.all_fields():
            add(f.label)
        out = ", ".join(parts)
        return out[:max_chars]


def load_pack(pack_id: str) -> Pack:
    path = PACKS_DIR / f"{pack_id}.json"
    return Pack.model_validate(json.loads(path.read_text(encoding="utf-8")))


_PACK_ORDER = ["insurance_motor", "healthcare_exam", "insurance_contract",
               "insurance_callcenter"]


def load_all() -> dict[str, Pack]:
    packs: dict[str, Pack] = {}
    for p in sorted(PACKS_DIR.glob("*.json")):
        pack = Pack.model_validate(json.loads(p.read_text(encoding="utf-8")))
        packs[pack.id] = pack
    order = {pid: i for i, pid in enumerate(_PACK_ORDER)}
    return dict(sorted(packs.items(), key=lambda kv: order.get(kv[0], 99)))
