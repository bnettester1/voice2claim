"""Trigger phrase spotting — thuần CPU, chạy trên MỌI partial, đích <500ms.

Hai chế độ:
- feed(text, final):  cho live mode — chỉ nhìn ĐUÔI partial (partial lớn dần).
- scan_full(text):    cho batch mode — quét toàn transcript.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.packs.loader import ActionSpec, Pack

ARM_THRESHOLD = 85
ARM_TTL_S = 8.0
REFIRE_SUPPRESS_S = 10.0

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_vi(s: str) -> str:
    """NFC → lower → đ→d → bỏ dấu → bỏ punctuation → gộp space."""
    s = unicodedata.normalize("NFC", s).lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


@dataclass
class _ActionState:
    armed_at: float = 0.0
    fired_at: float = 0.0
    armed_score: int = 0

    def is_armed(self, now: float) -> bool:
        return now - self.armed_at <= ARM_TTL_S

    def recently_fired(self, now: float) -> bool:
        return self.fired_at > 0 and now - self.fired_at <= REFIRE_SUPPRESS_S


@dataclass
class TriggerEvent:
    kind: str            # "armed" | "fire"
    action: ActionSpec
    score: int
    matched_text: str
    latency_ms: float = 0.0


@dataclass
class TriggerMatcher:
    pack: Pack
    state: dict[str, _ActionState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._variants: list[tuple[ActionSpec, str]] = []
        max_tokens = 4
        for a in self.pack.actions:
            self.state[a.id] = _ActionState()
            for v in a.triggers:
                nv = normalize_vi(v)
                if nv:
                    self._variants.append((a, nv))
                    max_tokens = max(max_tokens, len(nv.split()))
        self._tail_tokens = max_tokens + 3

    # ---------- live: partial tail / final toàn câu ----------
    def feed(self, text: str, final: bool, now: float | None = None) -> list[TriggerEvent]:
        t0 = time.perf_counter()
        now = now if now is not None else time.monotonic()
        norm = normalize_vi(text)
        # partial: chỉ nhìn đuôi (text lớn dần); final: cả câu đã chốt
        hay = norm if final else " ".join(norm.split()[-self._tail_tokens:])
        return self._match(hay, final, now, t0, full=final)

    # ---------- batch: toàn văn ----------
    def scan_full(self, text: str, now: float | None = None) -> list[TriggerEvent]:
        t0 = time.perf_counter()
        now = now if now is not None else time.monotonic()
        return self._match(normalize_vi(text), final=True, now=now, t0=t0, full=True)

    def _match(self, haystack: str, final: bool, now: float, t0: float,
               full: bool = False) -> list[TriggerEvent]:
        events: list[TriggerEvent] = []
        if not haystack:
            return events

        # 1) gom ứng viên tốt nhất theo từng action, kèm vị trí khớp
        cands: dict[str, tuple[ActionSpec, int, int, int]] = {}
        for action, nv in self._variants:
            if not full and len(haystack) < 0.6 * len(nv):
                continue
            al = fuzz.partial_ratio_alignment(nv, haystack)
            if al is None or al.score < ARM_THRESHOLD:
                continue
            score = int(al.score)
            cur = cands.get(action.id)
            if cur is None or score > cur[1]:
                cands[action.id] = (action, score, al.dest_start, al.dest_end)

        # 2) dominance filter: 2 action khớp CHỒNG LẤN cùng đoạn text
        #    (vd "cứu hộ ô tô" vs "cứu hộ xe máy") → chỉ giữ action điểm cao nhất
        kept: list[tuple[ActionSpec, int, int, int]] = []
        for c in sorted(cands.values(), key=lambda x: -x[1]):
            dominated = False
            for k in kept:
                inter = min(c[3], k[3]) - max(c[2], k[2])
                span = max(1, min(c[3] - c[2], k[3] - k[2]))
                if inter / span > 0.5 and k[1] > c[1]:
                    dominated = True
                    break
            if not dominated:
                kept.append(c)

        # 3) arm / fire
        for action, score, _s, _e in kept:
            st = self.state[action.id]
            if st.recently_fired(now):
                continue
            latency = (time.perf_counter() - t0) * 1000
            if not st.is_armed(now):
                st.armed_at, st.armed_score = now, score
                events.append(TriggerEvent("armed", action, score, "", latency))
            elif score > st.armed_score:
                st.armed_score = score
            if final and st.fired_at == 0.0 and action.confirm == "auto":
                st.fired_at = now
                events.append(TriggerEvent("fire", action, score, "", latency))
        return events

    def confirm_click(self, action_id: str, now: float | None = None) -> bool:
        """User bấm nút action đang armed (policy click)."""
        now = now if now is not None else time.monotonic()
        st = self.state.get(action_id)
        if st and st.is_armed(now) and not st.recently_fired(now):
            st.fired_at = now
            return True
        return False
