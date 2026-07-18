"""FormStore — trạng thái form + merge rules.

Rules:
1. Field user đã sửa (source="user") là bất khả xâm phạm (tới khi unlock).
2. Không bao giờ regress giá trị đã có về rỗng/null.
3. Mỗi field: value + confidence + evidence; rev tăng khi có patch thật.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.packs.loader import Pack


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


@dataclass
class FieldState:
    value: Any = None
    confidence: float = 0.0
    evidence: str = ""
    source: str = ""          # "" | "asr" | "user"


@dataclass
class FormStore:
    pack: Pack
    fields: dict[str, FieldState] = field(default_factory=dict)
    rev: int = 0

    def __post_init__(self) -> None:
        for f in self.pack.all_fields():
            self.fields[f.name] = FieldState()

    # ---------- merge từ extraction ----------
    def merge(self, extraction: dict[str, dict]) -> dict[str, dict]:
        """extraction: {name: {value, confidence, evidence}} → patch đã áp dụng."""
        patch: dict[str, dict] = {}
        for name, new in (extraction or {}).items():
            cur = self.fields.get(name)
            if cur is None or not isinstance(new, dict):
                continue
            if cur.source == "user":                      # rule 1
                continue
            nval = new.get("value")
            nconf = float(new.get("confidence") or 0.0)
            nev = str(new.get("evidence") or "")[:200]
            if _empty(nval):                              # rule 2
                continue
            if cur.value == nval:
                if nconf > cur.confidence:
                    cur.confidence = nconf
                continue
            cur.value, cur.confidence, cur.evidence, cur.source = nval, nconf, nev, "asr"
            patch[name] = {"value": nval, "confidence": nconf, "evidence": nev}
        if patch:
            self.rev += 1
        return patch

    # ---------- user edit ----------
    def set_user(self, name: str, value: Any) -> bool:
        cur = self.fields.get(name)
        if cur is None:
            return False
        cur.value, cur.confidence, cur.source = value, 1.0, "user"
        self.rev += 1
        return True

    def unlock(self, name: str) -> bool:
        cur = self.fields.get(name)
        if cur is None or cur.source != "user":
            return False
        cur.source = "asr"
        return True

    # ---------- views ----------
    def snapshot(self) -> dict[str, Any]:
        """Chỉ value — làm anchor cho lần extract sau."""
        return {n: fs.value for n, fs in self.fields.items() if not _empty(fs.value)}

    def full_state(self) -> dict[str, dict]:
        return {
            n: {"value": fs.value, "confidence": fs.confidence,
                "evidence": fs.evidence, "source": fs.source}
            for n, fs in self.fields.items()
        }

    def filled_required(self) -> tuple[int, int]:
        req = self.pack.required_fields()
        filled = sum(1 for n in req if not _empty(self.fields[n].value))
        return filled, len(req)
