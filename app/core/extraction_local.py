"""Semantic extraction LOCAL — không LLM ngoài (18/07 Long chốt: all-in VALSEA).

Nguồn tín hiệu, chồng lớp:
1. VALSEA semantic_tags (batch verbose_json) — map tag→field qua label/synonyms.
2. Anchor-window: label/synonyms của field (pack) → span giá trị đứng sau.
3. Chiến lược domain — catalog lấy từ chính pack (hint_terms: model xe, phụ
   tùng, thuốc, chỉ số...) + luật tiếng Việt (parse_vi: số đọc chữ, ngày).
4. NER local PyTorch (PER/LOC) khi có — bổ khuyết tên người / địa điểm.

Regex validators của pack dùng để nâng confidence. Output cùng format với
extraction cũ: {field: {value, confidence, evidence}} — FormStore lo merge.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from rapidfuzz import fuzz

from app.core.triggers import normalize_vi
from app.packs.loader import FieldSpec, Pack
from app.telephony import parse_vi

PLATE_RE = re.compile(r"\b\d{2}[A-Z]{1,2}\d?\s?-?\s?\d{3}\.?\d{2}\b|\b\d{2}-?[A-Z]\d\s?\d{3}\.?\d{2}\b")
NUM_UNIT_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(mg|mcg|g|ml|mmol/?l?|mmhg|%|ui|viên|độ|kg|cm)\b",
    re.IGNORECASE)
_SPEAKER_RE = re.compile(r"^\s*([^:\n]{2,30}):\s*")
_CONNECT = {"la", "cua", "toi", "anh", "chi", "em", "minh", "o", "tai", "bi",
            "vi", "thi", "da", "dang", "se", "vua", "moi", "rat", "cai", "chiec"}

_CUSTOMER_HINTS = ("khách", "chủ xe", "người bị nạn", "bệnh nhân", "người khai")
_AGENT_HINTS = ("giám định", "tổng đài", "bác sĩ", "bac si", "điều dưỡng")


# ---------------------------------------------------------------- câu & token
class Sent:
    __slots__ = ("speaker", "text", "low", "toks", "norm", "is_customer",
                 "is_agent")

    def __init__(self, speaker: str, text: str):
        self.speaker = speaker
        self.text = text.strip()
        self.low = self.text.lower()      # có dấu — match domain kw ("của"≠"cửa")
        self.toks = self.text.split()
        self.norm = [normalize_vi(t) for t in self.toks]
        sp = speaker.lower()
        self.is_agent = any(h in sp for h in _AGENT_HINTS)
        self.is_customer = any(h in sp for h in _CUSTOMER_HINTS) or (
            bool(speaker) and not self.is_agent)


def _sentences(transcript: str) -> list[Sent]:
    out: list[Sent] = []
    for line in transcript.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SPEAKER_RE.match(line)
        speaker = m.group(1).strip() if m else ""
        body = line[m.end():] if m else line
        for seg in re.split(r"(?<=[.!?])\s+", body):
            if seg.strip():
                out.append(Sent(speaker, seg))
    return out


def _find_phrase(norm_toks: list[str], phrase_norm: list[str]) -> int:
    """Vị trí bắt đầu của cụm (token đã normalize) trong câu, -1 nếu không có."""
    n, m = len(norm_toks), len(phrase_norm)
    if m == 0 or n < m:
        return -1
    for i in range(n - m + 1):
        if norm_toks[i:i + m] == phrase_norm:
            return i
    return -1


def _span_after(s: Sent, start: int, max_tokens: int = 14) -> str:
    """Giá trị sau anchor: bỏ từ nối đầu, cắt ở dấu phẩy/chấm hỏi."""
    toks = s.toks[start:]
    while toks and normalize_vi(toks[0]) in _CONNECT:
        toks = toks[1:]
    out: list[str] = []
    for t in toks[:max_tokens]:
        out.append(t)
        if t.endswith((",", ".", "?", "!", ";")):
            break
    val = " ".join(out).strip(" ,.?!;")
    return val


# ---------------------------------------------------------------- candidates
class Cands:
    def __init__(self) -> None:
        self.by_field: dict[str, list[tuple[Any, float, str]]] = {}

    def add(self, field: str, value: Any, conf: float, evidence: str) -> None:
        if value in (None, "", []):
            return
        self.by_field.setdefault(field, []).append(
            (value, conf, evidence.strip()[:200]))

    def best(self, spec: FieldSpec) -> tuple[Any, float, str] | None:
        cands = self.by_field.get(spec.name)
        if not cands:
            return None
        if spec.type == "list":
            items: list[str] = []
            seen: set[str] = set()
            conf, ev = 0.0, ""
            for v, c, e in cands:
                for item in (v if isinstance(v, list) else [v]):
                    key = normalize_vi(str(item))
                    if key and key not in seen:
                        seen.add(key)
                        items.append(str(item))
                conf, ev = max(conf, c), ev or e
            return (items, conf, ev) if items else None
        return max(cands, key=lambda t: t[1])


# ---------------------------------------------------------------- pass 1: tags
def _pass_semantic_tags(pack: Pack, tags: list | None, cands: Cands) -> None:
    """VALSEA semantic_tags {tag, phrase, meaning} → field khớp label/synonyms."""
    for tag in tags or []:
        if not isinstance(tag, dict):
            continue
        phrase = str(tag.get("phrase") or "").strip()
        label = f"{tag.get('tag', '')} {tag.get('meaning', '')}".strip()
        if not phrase or not label:
            continue
        best_f, best_s = None, 0
        for f in pack.all_fields():
            names = [f.label] + list(f.synonyms)
            score = max(fuzz.token_set_ratio(normalize_vi(label),
                                             normalize_vi(x)) for x in names)
            if score > best_s:
                best_f, best_s = f, score
        if best_f is not None and best_s >= 70:
            val = [phrase] if best_f.type == "list" else phrase
            cands.add(best_f.name, val, 0.72, f"[tag] {label}: {phrase}")


# ---------------------------------------------------------------- pass 2: anchor
def _typed_value(spec: FieldSpec, raw: str, sent: Sent) -> Any:
    if spec.type == "date":
        return parse_vi.parse_date(sent.text)
    if spec.type == "number":
        m = re.search(r"\d+(?:[.,]\d+)?", raw)
        if m:
            v = float(m.group().replace(",", "."))
            return int(v) if v.is_integer() else v
        val, nxt = parse_vi._small_number([normalize_vi(t) for t in raw.split()], 0)
        return val
    if spec.type == "enum":
        return _match_enum(spec, sent.text)
    if spec.type == "list":
        parts = re.split(r",| và | với | rồi |;", raw)
        return [p.strip(" .") for p in parts if len(p.strip()) > 2]
    return raw or None


def _match_enum(spec: FieldSpec, text: str) -> str | None:
    n = normalize_vi(text)
    best, best_s = None, 0
    for opt in spec.options:
        words = [w for w in normalize_vi(opt).split() if len(w) > 2]
        hits = sum(1 for w in words if w in n)
        score = hits / max(len(words), 1)
        if score > best_s:
            best, best_s = opt, score
    return best if best_s >= 0.5 else None


def _pass_anchor(pack: Pack, sents: list[Sent], cands: Cands) -> None:
    validators = {v.field: str(v.value) for v in pack.scoring.validators
                  if v.rule == "regex"}
    for f in pack.all_fields():
        if f.name.startswith("ten_"):
            continue    # tên người: synonyms kiểu "anh/chị" match bừa — dùng
                        # chiến lược _first_name/NER, không anchor
        phrases = [p for p in ([f.label] + list(f.synonyms)) if len(p) >= 2]
        phrase_norms = [[t for t in normalize_vi(p).split() if t]
                        for p in phrases]
        for s in sents:
            if s.text.rstrip().endswith("?"):
                continue                     # câu HỎI hiếm khi chứa giá trị
            for pn in phrase_norms:
                if not pn:
                    continue
                i = _find_phrase(s.norm, pn)
                if i < 0:
                    continue
                raw = _span_after(s, i + len(pn))
                val = _typed_value(f, raw, s)
                if val not in (None, "", []) and f.name in validators:
                    # field có validator → chỉ nhận đúng phần khớp regex
                    m = re.search(validators[f.name], f"{raw} {s.text}")
                    val = m.group(0) if m else None
                if val not in (None, "", []):
                    cands.add(f.name, val, 0.68, s.text)
                break


# ---------------------------------------------------------------- domain: chung
_NAME_RE = re.compile(
    r"(?:chào|gặp|là)\s+(?:anh|chị|chú|cô|bác|em|ông|bà)\s+"
    r"([A-ZĐÀ-Ỹ][a-zà-ỹ]+(?:\s[A-ZĐÀ-Ỹ][a-zà-ỹ]+){0,2})")
_LOC_RE = re.compile(
    r"(?:ở|tại|trên|xảy ra (?:ở|tại)|đang đứng (?:ở|tại))\s+"
    r"((?:đường|cao tốc|cầu|hầm|bãi|ngã \w+|quận|phường|khu|tòa nhà|chung cư|"
    r"đại lộ|xa lộ|vòng xoay|km\s?\d+|số \d+)[^,.\n?!]{0,45})", re.IGNORECASE)


_HONORIFIC_NAME_RE = re.compile(
    r"\b(?:anh|chị|chú|cô|bác|em|ông|bà)\s+([A-ZĐÀ-Ỹ][a-zà-ỹ]+)\b")
_NOT_NAME = {"wave", "vios", "morning", "camry", "ranger", "alpha", "honda",
             "toyota", "kia", "mazda", "ford", "vision", "lead", "sh"}


def _first_name(sents: list[Sent]) -> tuple[str, str] | None:
    """Tên người: ưu tiên câu chào; không có thì tên sau kính ngữ xuất hiện
    NHIỀU LẦN nhất trong hội thoại (anh Phúc à / bác Loan ơi…)."""
    for s in sents:
        m = _NAME_RE.search(s.text)
        if m and m.group(1).lower() not in _NOT_NAME:
            return m.group(1), s.text
    freq: dict[str, tuple[int, str]] = {}
    for s in sents:
        for m in _HONORIFIC_NAME_RE.finditer(s.text):
            name = m.group(1)
            if name.lower() in _NOT_NAME:
                continue
            n, _ = freq.get(name, (0, ""))
            freq[name] = (n + 1, s.text)
    if freq:
        name, (n, ev) = max(freq.items(), key=lambda kv: kv[1][0])
        if n >= 1:
            return name, ev
    return None


def _ner_entities(transcript: str) -> list[dict]:
    try:
        from app.core.ml import ner_local
        if ner_local.available():
            return ner_local.entities(transcript[:3000])
    except Exception:  # noqa: BLE001
        pass
    return []


# ---------------------------------------------------------------- domain: bảo hiểm
_DMG_VERBS = ["vỡ", "bể", "gãy", "móp", "trầy", "xước", "trầy xước", "hỏng",
              "nứt", "thủng", "cong", "rách", "bung", "lệch", "chết máy",
              "không khởi động", "không đề"]
# hư hỏng đứng một mình, không cần phụ tùng đi kèm
_STANDALONE_DMG = ["chết máy", "không khởi động được", "không đề được",
                   "thủy kích", "ngập nước nội thất", "ngập sàn xe",
                   "nước vào sàn", "nước tràn vào", "ngập tới yên"]
_DMG_PATTERNS = [re.compile(r"ngập(?: nước)? tới [^,.;\n]{2,18}"),
                 re.compile(r"đề(?: máy)? không nổ(?: nữa)?"),
                 re.compile(r"không nổ máy"),
                 re.compile(r"sàn xe (?:còn )?ướt[^,.;\n]{0,10}")]
# enum nguyen_nhan: option → từ khoá nhận diện (match trên chữ thường có dấu)
_CAUSE_KW = {
    "va chạm": ["đâm", "tông", "va quệt", "quệt", "va chạm", "húc"],
    "ngập nước": ["ngập", "nước tràn", "thủy kích", "mưa lớn"],
    "trộm cắp bộ phận": ["trộm", "mất cắp", "cạy", "gỡ mất", "bẻ trộm", "mất gương"],
    "cháy nổ": ["cháy", "bốc khói", "nổ"],
}
_TIME_TAIL_RE = re.compile(r"\s+(?:đêm|hôm|sáng|chiều|tối|trưa)\s?(?:qua|nay|kia)?$")
_THEFT_VERBS = ["mất", "trộm", "cạy", "gỡ", "bẻ", "tháo"]
_INJURY_KW = ["bị thương", "trầy xước", "đau", "chảy máu", "chóng mặt", "gãy",
              "va đầu", "bất tỉnh", "khóc", "sưng", "bong gân", "choáng"]
_OTHER_VEHICLE_KW = ["đâm", "tông", "va vào", "quệt", "xe kia", "đối phương",
                     "bên kia", "xe tải", "xe buýt", "xe khách", "container",
                     "xe thứ"]
_OWN_KW = ["của anh", "của chị", "của tôi", "của em", "của mình", "xe anh",
           "xe chị", "xe tôi", "xe mình", "xe em"]
_EVIDENCE_KW = ["camera hành trình", "camera bãi xe", "camera", "clip",
                "video", "hình ảnh", "chụp hình", "nhân chứng"]

_BRAND_RE = re.compile(
    r"\b(Toyota|Honda|Kia|Mazda|Ford|Hyundai|Suzuki|Yamaha|Piaggio|VinFast|"
    r"Mercedes|BMW|Mitsubishi|Nissan|Chevrolet|Isuzu|Wave|Vision|Lead|SH|"
    r"Exciter|Sirius|Airblade|Air Blade|Vios|Morning|CR-V|CX-5|Camry|Ranger)"
    r"(?-i:(?:\s(?:[A-Z][\w.-]*|\d[\w.-]*)){0,2})", re.IGNORECASE)
_GENERIC_VEHICLE_RE = re.compile(
    r"\bxe\s(?:buýt|tải|khách|bồn|ba gác|container|taxi)\b", re.IGNORECASE)
# danh từ chỉ XE ĐỐI PHƯƠNG (gán hư hỏng/biển số cho xe kia cần DANH TỪ,
# động từ đâm/tông chỉ nói về cú va — không đủ)
_OTHER_NOUNS = ["xe kia", "xe đối phương", "đối phương", "bên kia", "xe tải",
                "xe buýt", "xe khách", "container", "xe thứ hai", "xe thứ ba",
                "xe con kia"]
_OTHER_ASK = ["đâm vào", "tông vào", "va vào", "xe nào", "xe gì", "biển số xe ô tô",
              "xe đối phương", "xe kia"]


def _vehicle_parts(pack: Pack) -> list[str]:
    """Catalog phụ tùng từ hint_terms pack (lọc cụm danh từ vật lý)."""
    generic = ["yếm xe", "yếm", "gương chiếu hậu", "gương", "cản trước",
               "cản sau", "cản", "đèn sương mù", "đèn pha", "đèn", "kính chắn gió",
               "kính cửa sổ", "kính", "nẹp cốp", "cốp", "capo", "la giăng",
               "lưới tản nhiệt", "cửa", "bánh", "lốp", "sơn", "thân xe", "đuôi xe"]
    hints = [t for t in pack.hint_terms
             if any(w in normalize_vi(t) for w in
                    ("yem", "guong", "can", "den", "kinh", "nep", "capo",
                     "la giang", "luoi", "cop", "banh", "lop"))]
    seen, out = set(), []
    for t in hints + generic:
        k = normalize_vi(t)
        if k not in seen:
            seen.add(k)
            out.append(t)
    return sorted(out, key=lambda x: -len(x))     # cụm dài match trước


def _side_suffix(low: str, part: str) -> str:
    m = re.search(re.escape(part.lower()) +
                  r"[^,.;]{0,6}?(bên trái|bên phải|phía trước|phía sau)", low)
    return m.group(1) if m else ""


def _verb_near_part(low_toks: list[str], part_idx: int) -> str:
    """Động từ hỏng gần NHẤT đứng trước phụ tùng (≤5 token, xuyên filler)."""
    lo = max(0, part_idx - 5)
    window = low_toks[lo:part_idx]
    for i in range(len(window) - 1, -1, -1):
        for v in _DMG_VERBS:
            vt = v.split()
            if window[i:i + len(vt)] == vt or window[i].strip(",.") == vt[0]:
                if v in " ".join(window[i:i + 2]):
                    return v
    return ""


def _extract_insurance(pack: Pack, sents: list[Sent], cands: Cands) -> None:
    parts = _vehicle_parts(pack)
    got_name = _first_name(sents)
    if got_name:
        cands.add("ten_khach_hang", got_name[0], 0.85, got_name[1])

    full_low = "\n".join(s.low for s in sents)
    best_cause, best_hits = None, 0
    for opt, kws in _CAUSE_KW.items():
        hits = sum(full_low.count(k) for k in kws)
        if hits > best_hits:
            best_cause, best_hits = opt, hits
    if best_cause and pack.field("nguyen_nhan") is not None:
        cands.add("nguyen_nhan", best_cause, 0.75, f"[cause kw ×{best_hits}]")

    for si, s in enumerate(sents):
        text, low = s.text, s.low
        prev_low = " ".join(x.low for x in sents[max(0, si - 2):si])

        # pattern CHÍNH XÁC chạy cả trên câu hỏi (giám định viên hay nhắc lại
        # thông tin trong câu hỏi: "anh bị tai nạn ở đường Cộng Hòa, có sao không?")
        m = _LOC_RE.search(text)
        if m:
            loc = _TIME_TAIL_RE.sub("", m.group(1).strip(" ,."))
            # cùng conf thì ưu tiên vị trí mô tả dài hơn (bonus nhỏ theo độ dài)
            cands.add("vi_tri", loc, 0.85 + min(len(loc), 40) / 1000, text)
        for dmg in _STANDALONE_DMG:
            if dmg in low:
                cands.add("hu_hong_xe_khach", [dmg], 0.78, text)
        for pat in _DMG_PATTERNS:
            dm = pat.search(low)
            if dm:
                cands.add("hu_hong_xe_khach", [dm.group(0).strip()], 0.78, text)

        if text.rstrip().endswith("?"):
            continue                          # phần còn lại: chỉ lấy từ câu trả lời

        own = any(k in low for k in _OWN_KW)
        other_noun = any(k in low for k in _OTHER_NOUNS)
        # câu trước hỏi về xe đối phương ("biển số xe đâm vào mình?") → câu
        # trả lời hiện tại nói về XE KIA dù không có danh từ đối phương
        other_ctx = other_noun or any(k in prev_low for k in _OTHER_ASK) or \
            any(k in low for k in ("đâm vào", "tông vào", "va vào"))

        # xe + biển số — xét NGỮ CẢNH SÁT MỖI XE ("bị một xe SH … tông" = xe kia
        # dù câu có 'xe anh' ở vế khác); biển số lấy cái đứng NGAY SAU xe đó
        mentions = list(_BRAND_RE.finditer(text)) + list(_GENERIC_VEHICLE_RE.finditer(text))
        used_plates: set[str] = set()
        for vm in mentions:
            v = vm.group(0).strip()
            pre, post = text[max(0, vm.start() - 25):vm.start()], text[vm.end():vm.end() + 40]
            pm = PLATE_RE.search(post)
            plate = pm.group(0) if pm and pm.start() < 30 else ""
            if plate:
                used_plates.add(plate)
            attacker = bool(re.search(r"(?:bị|một)\s*(?:chiếc|xe)?\s*$", pre)) or \
                bool(re.search(r"^\s*(?:biển(?:\s?số)?\s?[\w.\s-]{0,14})?\s*(?:tông|đâm|va|húc)", post))
            is_generic_other = vm.re is _GENERIC_VEHICLE_RE
            if attacker or is_generic_other or (other_ctx and not own):
                item = f"{v} — {plate}" if plate else v
                cands.add("xe_lien_quan", [item], 0.82, text)
            else:
                cands.add("xe_khach", v, 0.8 if own else 0.62, text)
                if plate:
                    cands.add("bien_so_xe_khach", plate, 0.85, text)
        leftover = [p.group(0) for p in PLATE_RE.finditer(text)
                    if p.group(0) not in used_plates]
        if leftover and not mentions and len(leftover) == 1 and not s.is_agent:
            # 1 biển số trơ trong lời KHÁCH (câu recap nhiều biển của GĐV bỏ qua)
            (cands.add("xe_lien_quan", [leftover[0]], 0.6, text)
             if (other_ctx and not own)
             else cands.add("bien_so_xe_khach", leftover[0], 0.7, text))

        # hư hỏng: động từ gần part nhất; gán xe kia CHỈ khi có danh từ đối phương
        dmg_field = ("hu_hong_xe_lien_quan" if (other_noun and not own)
                     else "hu_hong_xe_khach")
        low_toks = low.split()
        low_scan = low
        for part in parts:
            pl = part.lower()
            pos = low_scan.find(pl)
            if pos < 0:
                continue
            part_idx = len(low_scan[:pos].split())
            verb = _verb_near_part(low_toks, part_idx) or next(
                (v for v in _DMG_VERBS if v in low), "")
            theft = next((v for v in _THEFT_VERBS
                          if re.search(rf"\b{v}\b", low)), "")
            side = _side_suffix(low, pl)
            label = (part + (" " + side if side else "")).strip()
            if theft and not verb:
                cands.add("hang_muc_mat_cap", [label], 0.78, text)
            elif verb:
                cands.add(dmg_field, [f"{verb} {label}"], 0.78, text)
            low_scan = low_scan.replace(pl, " " * len(pl), 1)  # chống match cụm con

        # thương tích (câu nói về NGƯỜI)
        if not s.is_agent:
            inj = [kw for kw in _INJURY_KW if kw in low]
            if inj:
                segs = [c for c in re.split(r"[.;]", text)
                        if any(k in c.lower() for k in inj)
                        and not any(p.lower() in c.lower() for p in parts[:10])]
                if segs:
                    cands.add("thuong_tich", min(segs, key=len).strip(" ,."),
                              0.72, text)

        for kw in _EVIDENCE_KW:
            if kw in low:
                cands.add("bang_chung", [kw], 0.72, text)
                break

    # ghép "xe trơ" + "biển số trơ" thành 1 mục "Xe — biển" (nhắc ở 2 câu gần nhau)
    items = cands.by_field.get("xe_lien_quan", [])
    if items:
        flat = [str(x) for v, _, _ in items for x in (v if isinstance(v, list) else [v])]
        bare_vehicles = [x for x in flat if "—" not in x and not PLATE_RE.search(x)]
        bare_plates = [x for x in flat if PLATE_RE.fullmatch(x.strip())]
        merged = [x for x in flat if x not in bare_vehicles and x not in bare_plates]
        for v, p in zip(bare_vehicles, bare_plates):
            merged.append(f"{v} — {p}")
        merged += bare_vehicles[len(bare_plates):]
        if merged != flat:
            cands.by_field["xe_lien_quan"] = [(merged, 0.82, items[0][2])]


# ---------------------------------------------------------------- domain: y tế
_MED_RE = re.compile(
    r"\b([A-Z][A-Za-z]{2,}(?:\s[A-Z][a-z]+)?)\s(?:[a-zà-ỹ]+\s){0,3}?"
    r"(\d+\s?(?:mg|mcg|g|ml|UI|viên)\b)",
    re.UNICODE)
_KQ_PATTERN = re.compile(
    r"kết quả\s+([^,.;:]{2,30}?)\s*(?:cho thấy|ra là|:)\s*([^.;\n]{3,80})",
    re.IGNORECASE)
_BP_RE = re.compile(r"\b(1\d{2}|9\d)\s*(?:trên|/)\s*(\d{2,3})\b")
_DUR_RE = re.compile(r"(\d+\s*(?:ngày|tuần|tháng))\s*(?:nữa|sau|tới)?")
# chỉ số xét nghiệm + giá trị: "LDL 4.9 mmol/L", "EF 55%", "HbA1c 8.2%"
_METRIC_RE = re.compile(
    r"\b(EF|LDL(?:-C)?|HDL|HbA1c|AST|ALT|GGT|creatinin|cholesterol|"
    r"triglyceride|men gan|đường huyết|glucose)\b[^,.;\n]{0,20}?"
    r"(\d+(?:[.,]\d+)?\s*(?:%|mmol/?[lL]?|mg/d[lL]|U/L)?)", re.IGNORECASE)
_RESULT_WORDS = ("âm tính", "dương tính", "viêm", "nhẹ", "trung bình", "nặng",
                 "bình thường", "cao", "thấp", "tăng", "giảm")
_CLS_KW = ["nội soi", "siêu âm", "x-quang", "xquang", "x quang", "chụp",
           "xét nghiệm", "điện tim", "điện tâm đồ", "mri", "ct", "đo",
           "hba1c", "ldl", "hdl", "ef", "men gan", "công thức máu", "holter",
           "chức năng thận", "điện giải", "lipid"]
_NEW_MED_KW = ["kê", "kê đơn", "kê cho", "thêm", "bắt đầu", "cho thuốc", "cho em thuốc", "cho anh thuốc"]
_KEEP_MED_KW = ["tiếp tục", "duy trì", "như cũ", "giữ nguyên", "uống tiếp"]
_ADJ_MED_KW = ["tăng liều", "giảm liều", "tăng lên", "giảm xuống", "đổi sang",
               "chỉnh", "sẽ tăng", "sẽ giảm", "nâng liều", "hạ liều"]
_DOSE_CHANGE_RE = re.compile(r"từ\s?(\d+\s?mg)\s?(?:lên|xuống)\s?(\d+\s?mg)",
                             re.IGNORECASE)
_WORD_NUM = r"(?:hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|một|mươi|mốt|lăm|tư|\d+)"
_DUR_WORD_RE = re.compile(
    rf"({_WORD_NUM}(?:\s{_WORD_NUM})?)\s*(ngày|tuần|tháng)\b", re.IGNORECASE)


def _duration_phrase(text: str) -> str | None:
    """'Hai tuần nữa' / '2 tuần' / 'mười ngày' → '2 tuần' / '10 ngày'."""
    for m in _DUR_WORD_RE.finditer(text):
        words, unit = m.group(1), m.group(2)
        if words.strip().isdigit():
            return f"{int(words)} {unit}"
        toks = [normalize_vi(t) for t in words.split()]
        val, nxt = parse_vi._small_number(toks, 0)
        if val is not None and nxt == len(toks) and 1 <= val <= 60:
            return f"{val} {unit}"
    return None
_TREAT_KW = ["bó bột", "nẹp", "vật lý trị liệu", "phẫu thuật", "mổ", "tiêm",
             "truyền", "băng", "khâu"]
_SYMPTOM_KW = ["đau", "sốt", "ho", "mệt", "chóng mặt", "buồn nôn", "nôn",
               "tiêu chảy", "táo bón", "khó thở", "tức ngực", "ợ chua", "ợ hơi",
               "chán ăn", "mất ngủ", "sưng", "tê", "hồi hộp", "đánh trống ngực",
               "nóng rát"]


def _med_schedule(text: str, after: int) -> str:
    m = re.search(r"((?:ngày|sáng|trưa|chiều|tối)\s[^,.;]{0,25}?(?:viên|lần|gói))",
                  text[after:after + 60], re.IGNORECASE)
    return f" ({m.group(1).strip()})" if m else ""


def _disease_terms(pack: Pack) -> list[str]:
    """Lexicon bệnh/chẩn đoán từ hint_terms các chuyên khoa của pack."""
    out: list[str] = []
    for sp in pack.specialties.values():
        out.extend(t for t in sp.hint_terms if len(t) >= 4)
    return out


def _extract_healthcare(pack: Pack, sents: list[Sent], cands: Cands) -> None:
    got_name = _first_name(sents)
    if got_name:
        cands.add("ten_benh_nhan", got_name[0], 0.85, got_name[1])

    full = "\n".join(s.text for s in sents)
    full_low = full.lower()
    m = re.search(r"(\d{1,3})\s*tuổi", full)
    if m:
        cands.add("tuoi", int(m.group(1)), 0.85, m.group(0))

    # chuyên khoa: đếm hint_terms từng specialty của pack, nhiều hit nhất thắng
    spec_field = pack.field("chuyen_khoa")
    if spec_field is not None and pack.specialties:
        best_label, best_hits = None, 0
        for sp in pack.specialties.values():
            hits = sum(full_low.count(t.lower()) for t in sp.hint_terms if t)
            if hits > best_hits:
                best_label, best_hits = sp.label, hits
        if best_label and best_hits >= 2:
            opt = _match_enum(spec_field, best_label) or best_label
            cands.add("chuyen_khoa", opt, 0.78, f"[specialty ×{best_hits}]")

    # lý do khám: tái khám + tên bệnh trong cùng câu (nếu có)
    diseases = _disease_terms(pack)
    for s in sents[:6]:
        if "tái khám" in s.low:
            dis = next((d for d in diseases if d.lower() in s.low), "")
            cands.add("ly_do_kham", ("tái khám " + dis).strip(), 0.7, s.text)
            break

    for s in sents:
        text, low = s.text, s.low
        is_question = text.rstrip().endswith("?")

        # thuốc + liều ("tăng Amlodipine từ 5mg lên 10mg" → "Amlodipine 5mg → 10mg")
        for mm in _MED_RE.finditer(text):
            name, dose = mm.group(1).strip(), mm.group(2).replace(" ", "")
            if name.lower() in _NOT_NAME:
                continue
            chg = _DOSE_CHANGE_RE.search(text)
            dose_part = (f"{chg.group(1).replace(' ', '')} → "
                         f"{chg.group(2).replace(' ', '')}") if chg else dose
            item = f"{name} {dose_part}{_med_schedule(text, mm.end())}"
            if chg or any(k in low for k in _ADJ_MED_KW):
                cands.add("thuoc_dieu_chinh", [item], 0.82, text)
            elif any(k in low for k in _KEEP_MED_KW):
                cands.add("thuoc_duy_tri", [item], 0.8, text)
            else:
                cands.add("thuoc_moi", [item], 0.75, text)

        # cận lâm sàng — bỏ câu hỏi và câu nói về NÚT bấm (trigger phrase)
        if not is_question and "nút" not in low:
            for km in _KQ_PATTERN.finditer(text):     # "kết quả X cho thấy Y"
                cands.add("ket_qua_cls",
                          [f"{km.group(1).strip()}: {km.group(2).strip(' ,.')}"],
                          0.82, text)
            for mm in _METRIC_RE.finditer(text):      # "LDL 4.9 mmol/L"
                cands.add("ket_qua_cls",
                          [f"{mm.group(1)} {mm.group(2).strip()}"], 0.8, text)
            bp = _BP_RE.search(text)
            if bp and any(w in low for w in ("huyết áp", "đo", "toàn")):
                cands.add("ket_qua_cls",
                          [f"huyết áp {bp.group(1)}/{bp.group(2)}"], 0.8, text)
            # duyệt TỪNG mệnh đề chứa từ khoá CLS ("đeo Holter…, và làm thêm
            # điện giải đồ…" = 2 chỉ định riêng)
            order_ctx = any(w in low for w in
                            ("làm thêm", "chỉ định", "chụp thêm", "đo thêm",
                             "đi làm", "cần làm", "đeo", "quay lại xét nghiệm",
                             "sau quay lại", "tháng sau", "tuần sau", "sẽ"))
            result_ctx = any(w in low for w in ("kết quả", "cho thấy",
                                                "phát hiện", "ra là",
                                                "âm tính", "dương tính"))
            for seg in re.split(r"[,;]| và ", text):
                segl = seg.lower()
                if not any(k in segl for k in _CLS_KW):
                    continue
                seg = seg.strip(" ,.")
                if len(seg) < 5:
                    continue
                if order_ctx and not result_ctx:
                    cands.add("chi_dinh_cls_moi", [seg], 0.75, text)
                elif result_ctx and not _KQ_PATTERN.search(text):
                    unit = NUM_UNIT_RE.search(text)
                    if unit and unit.group(0).lower() not in seg.lower():
                        seg = f"{seg} {unit.group(0)}"
                    # item kết quả phải mang giá trị/kết luận, không câu suông
                    if (re.search(r"\d", seg)
                            or any(w in seg.lower() for w in _RESULT_WORDS)):
                        cands.add("ket_qua_cls", [seg], 0.72, text)

        # triệu chứng (lời bệnh nhân)
        if not s.is_agent:
            for kw in _SYMPTOM_KW:
                if kw in low:
                    seg = min((c for c in re.split(r"[,;.]", text)
                               if kw in c.lower()),
                              key=len, default="").strip(" ,.")
                    if 3 < len(seg) < 60:
                        cands.add("trieu_chung", [seg], 0.7, text)

        # chẩn đoán (lời bác sĩ): "chẩn đoán/kết luận …" hoặc "bị/mắc <bệnh
        # trong lexicon chuyên khoa>"
        if (s.is_agent or not s.speaker) and not is_question:
            dm = re.search(r"(?:chẩn đoán|kết luận)(?:\s+là|\s+của\s+\w+)?\s*[:là]*\s*([^,.;\n]{4,80})",
                           text, re.IGNORECASE)
            if dm:
                cands.add("chan_doan", dm.group(1).strip(), 0.85, text)
            else:
                bm = re.search(r"(?:bị|mắc|có dấu hiệu|nguy cơ)\s+([^.;\n]{4,140})",
                               text)
                if bm and any(d.lower() in bm.group(1).lower()
                              for d in _disease_terms(pack)):
                    cands.add("chan_doan", bm.group(1).strip(" ,."), 0.74, text)

        for kw in _TREAT_KW:
            if kw in low:
                cands.add("chi_dinh_dieu_tri", [kw], 0.72, text)

        lm = re.search(r"(?:uống|điều trị|dùng)\s(?:thuốc\s)?(?:trong|kéo dài)?\s*(\d+\s*(?:ngày|tuần|tháng))",
                       text, re.IGNORECASE)
        if lm:
            cands.add("lieu_trinh", lm.group(1), 0.8, text)

        # tái khám: tìm THỜI LƯỢNG (số hoặc CHỮ: "hai tuần nữa") quanh từ khoá
        if any(k in low for k in ("tái khám", "khám lại", "quay lại")):
            dur = _duration_phrase(text)
            if dur:
                cands.add("tai_kham", f"sau {dur}", 0.8, text)

        if any(w in low for w in ("kiêng", "hạn chế", "tránh", "không nên",
                                  "nghỉ ngơi", "lưu ý")):
            if s.is_agent or not s.speaker:
                cands.add("dan_do", text.strip(" ,."), 0.68, text)

    # fallback chẩn đoán: chưa bắt được → ghép mệnh đề bác sĩ chứa thuật ngữ
    # bệnh + từ đánh giá ("LDL-cholesterol đang cao", "nguy cơ tim mạch")
    if "chan_doan" not in cands.by_field:
        judge = ("cao", "tăng", "giảm", "nguy cơ", "xơ vữa", "suy", "viêm",
                 "vượt", "rối loạn", "gãy", "rách")
        for s in sents:
            if not (s.is_agent or not s.speaker) or s.text.rstrip().endswith("?"):
                continue
            sl = s.low
            if not (any(d.lower() in sl for d in diseases)
                    and any(j in sl for j in judge)):
                continue
            cls_parts = [c.strip(" ,.") for c in re.split(r"[,;.]", s.text)]
            dis_cl = next((c for c in cls_parts
                           if any(d.lower() in c.lower() for d in diseases)), "")
            # mệnh đề "nguy cơ …" có thể nằm Ở CÂU KHÁC của bác sĩ
            risk_cl = ""
            for s2 in sents:
                if s2.is_agent or not s2.speaker:
                    rm = re.search(r"(?:làm tăng |có |tăng )?(nguy cơ [^,.;\n]{3,40})",
                                   s2.text, re.IGNORECASE)
                    if rm:
                        risk_cl = rm.group(1).strip(" ,.")
                        break
            jd_cl = risk_cl or next(
                (c for c in cls_parts
                 if c != dis_cl and any(j in c.lower() for j in judge)), "")
            picked = ", ".join(x for x in (dis_cl, jd_cl) if x)
            if picked:
                cands.add("chan_doan", picked, 0.66, s.text)
                break


# ---------------------------------------------------------------- NER pass
def _pass_ner(pack: Pack, transcript: str, cands: Cands) -> None:
    ents = _ner_entities(transcript)
    for e in ents:
        label = str(e.get("entity_group") or e.get("entity") or "").upper()
        word = str(e.get("word") or "").strip()
        if len(word) < 2 or word.startswith("##"):
            continue
        if "PER" in label:
            for fname in ("ten_khach_hang", "ten_benh_nhan"):
                if pack.field(fname) is not None:
                    cands.add(fname, word, 0.6, f"[NER] {word}")
        elif "LOC" in label:
            for fname in ("vi_tri", "dia_chi_lien_he"):
                if pack.field(fname) is not None:
                    cands.add(fname, word, 0.55, f"[NER] {word}")


# ---------------------------------------------------------------- entry
def extract_local(
    pack: Pack,
    transcript: str,
    prev_state: dict[str, Any] | None = None,
    semantic_tags: list | None = None,
) -> dict[str, dict]:
    sents = _sentences(transcript)
    if not sents:
        return {}
    cands = Cands()

    _pass_anchor(pack, sents, cands)
    _pass_semantic_tags(pack, semantic_tags, cands)
    if pack.id.startswith("insurance"):
        _extract_insurance(pack, sents, cands)
    if pack.id.startswith("healthcare"):
        _extract_healthcare(pack, sents, cands)
    if pack.call_script is not None:        # pack kịch bản gọi: tái dùng parse_vi
        for step in pack.call_script.steps:
            for s in sents:
                v = parse_vi.parse_field(pack, step.field, s.text)
                if v is not None:
                    cands.add(step.field, v, 0.8, s.text)
    _pass_ner(pack, transcript, cands)

    out: dict[str, dict] = {}
    for f in pack.all_fields():
        best = cands.best(f)
        if best is None:
            continue
        value, conf, ev = best
        for v in pack.scoring.validators:      # validator pass → nâng conf
            if v.field == f.name and v.rule == "regex":
                vals = value if isinstance(value, list) else [value]
                if all(re.fullmatch(str(v.value), str(x)) for x in vals):
                    conf = max(conf, 0.92)
        out[f.name] = {"value": value, "confidence": round(min(conf, 0.98), 2),
                       "evidence": ev}
    return out
