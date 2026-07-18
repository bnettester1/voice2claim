# Cơ chế Text Normalization & Từ điển NER — giải thích chi tiết (as-built)

> Tài liệu kỹ thuật cho team + giám khảo. Mọi snippet dưới đây trích **nguyên văn
> từ code đang chạy** (18/07/2026, sau decision 0010 — engine local, không LLM
> ngoài). File nguồn ghi ở đầu mỗi mục.

---

## 0. Bức tranh tổng — chữ đi qua 6 tầng chuẩn hóa, nghĩa lấy từ 4 nguồn từ điển

```
                      ┌──────────────── TỪ ĐIỂN NGHIỆP VỤ (packs/*.json) ────────────────┐
                      │  hint_terms · synonyms · itn_rules · triggers · validators · specialties │
                      └──┬────────────┬──────────────┬───────────────┬─────────────────┬─┘
                         │(0)         │(2)           │(B2)           │(B4)             │(B2)
Giọng nói ──► VALSEA ASR ─┴─► transcript ─► apply_itn ─► extraction_local ─► TriggerMatcher ─► FormScorer
              (1) correction  (giữ dấu)    (sửa theo     (anchor+domain+     (fuzzy, bỏ dấu)   (validator
              + ITN nội bộ                 từ điển)      tags+NER)                             nâng conf)
                                              │                │
                                        (3) normalize_vi  (4) parse_vi        (5) coercion đầu ra
                                        (bản BỎ DẤU để    (số đọc chữ →       (_stringify list/str)
                                         match)            chữ số)
```

**Nguyên tắc xuyên suốt:** giữ **hai bản thể của text** — *display-form* (giữ
nguyên dấu tiếng Việt, dùng để hiển thị/điền form/làm evidence) và
*match-form* (bỏ dấu, lowercase, dùng để so khớp chịu lỗi ASR). Không bao giờ
match trên bản display, không bao giờ hiển thị bản match.

---

# PHẦN A — TEXT NORMALIZATION (6 tầng)

## Tầng 0 · Chuẩn hóa "từ tai" — `hint_text` bơm từ điển vào ASR
*File: `app/packs/loader.py` → dùng ở `app/realtime/session.py` (`session.start`)*

Cách chống lỗi ASR rẻ nhất là **đừng để ASR nghe sai ngay từ đầu**. Loader gom
từ điển của pack thành chuỗi ~950 ký tự gửi kèm khi mở phiên VALSEA RTT:

```python
def hint_text(self, max_chars: int = 950) -> str:
    """Từ điển nghiệp vụ → chuỗi hint cho VALSEA RTT (ưu tiên trigger + thuật ngữ)."""
    parts, seen = [], set()
    def add(term):
        t = term.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower()); parts.append(t)
    for a in self.actions:
        for t in a.triggers[:2]: add(t)      # câu lệnh "bấm nút..." — quan trọng nhất
    for t in self.hint_terms: add(t)         # Wave Alpha, 59A-987.65, EF, Esomeprazole...
    for sp in self.specialties.values():
        for t in sp.hint_terms: add(t)       # module chuyên khoa (tiêu hóa/chỉnh hình/tim mạch)
    for f in self.all_fields(): add(f.label)
    return ", ".join(parts)[:max_chars]
```

Kết quả đo được: cùng câu TTS, transcribe **không hint** nghe "59A-908.7365";
qua RTT **có hint** ra đúng "59A-987.65".

## Tầng 1 · VALSEA correction + ITN nội bộ
Batch dùng `enable_correction=true` (`response_format=verbose_json` trả cả
`raw_transcript` lẫn `text` đã sửa); ASR tự ITN số cơ bản ("năm chín A chín
trăm tám mươi bảy chấm sáu lăm" → "59A-987.65"). Đây là nền — nhưng **không đủ**
với thuật ngữ ngành, dẫn tới tầng 2.

## Tầng 2 · `apply_itn` — từ điển sửa ASR theo pack ⭐ (tầng "ăn tiền" nhất)
*File: `app/core/normalize.py` — chạy TRƯỚC extraction + trigger, cả batch lẫn live-final*

```python
# quy tắc chung mọi pack: số + đơn vị viết liền
_UNIT_RE = re.compile(r"(\d)\s+(mg|mcg|g|ml|mmol/L|mmHg|%)\b", re.IGNORECASE)
# "3/8 mmol/L" do ASR đọc "ba chấm tám" thành phân số → 3.8
_DECIMAL_SLASH = re.compile(r"\b(\d)\s*/\s*(\d)\s*(mmol/L)\b")

def apply_itn(pack: Pack, text: str) -> str:
    out = _UNIT_RE.sub(r"\1\2", text)          # "40 mg" → "40mg"
    out = _DECIMAL_SLASH.sub(r"\1.\2 \3", out) # "3/8 mmol/L" → "3.8 mmol/L"
    for rule in pack.itn_rules:                # ← TỪ ĐIỂN của doanh nghiệp
        pat, rep = rule.get("pattern", ""), rule.get("replace", "")
        if rule.get("regex"):
            out = re.sub(pat, rep, out, flags=re.IGNORECASE)
        else:
            out = re.sub(re.escape(pat), rep, out, flags=re.IGNORECASE)
    return out
```

`itn_rules` thật trong `packs/healthcare_exam.json` — **được thêm từ lỗi ASR
quan sát trong eval audio**, đây chính là vòng lặp "doanh nghiệp dạy hệ thống":

```json
[
  {"pattern": "\\bIF (\\d+\\s*%)", "replace": "EF \\1", "regex": true},
  {"pattern": "phân suất tổng máu", "replace": "phân suất tống máu"},
  {"pattern": "mèn gần",            "replace": "men gan"},
  {"pattern": "\\bIST[,\\s]+(và\\s+)?LT\\b", "replace": "AST/ALT", "regex": true},
  {"pattern": "alpha[- ]?chloine",  "replace": "Alpha Choay", "regex": true},
  {"pattern": "hát pê",             "replace": "HP"},
  {"pattern": "ê ép",               "replace": "EF"}
]
```

Hiệu quả đo được (eval audio, case F & G): trước tầng này **FAIL** vì "IF 60%",
"mèn gần IST, LT", "alpha-chloine" — sau khi thêm rules: **PASS 100% cả bản
nhiễu SNR 12dB**.

## Tầng 3 · `normalize_vi` — match-form bỏ dấu (xương sống của mọi phép so khớp)
*File: `app/core/triggers.py` — dùng bởi trigger, extraction_local, NER agreement, eval*

```python
def normalize_vi(s: str) -> str:
    """NFC → lower → đ→d → bỏ dấu → bỏ punctuation → gộp space."""
    s = unicodedata.normalize("NFC", s).lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)                     # tách dấu khỏi chữ
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # bỏ combining marks
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()
```

Vì sao bỏ dấu: ASR tiếng Việt sai dấu là lỗi phổ biến nhất ("hông nặng lắm" ~
"hỏng nặng lắm") — match trên bản bỏ dấu sống sót qua lỗi này; và trigger
phrase ≥4 từ nên bỏ dấu không gây nhầm nghĩa. Chú ý `đ→d` phải làm **trước**
NFD vì "đ" không phải chữ+dấu tổ hợp. Ngoại lệ có chủ đích: extraction_local
match **domain keyword trên bản CÓ dấu** (`s.low`) khi cần phân biệt nghĩa
("của" ≠ "cửa") — xem chú thích trong `Sent.low`.

## Tầng 4 · `parse_vi` — ITN chiều sâu cho số đọc chữ (đường thoại)
*File: `app/telephony/parse_vi.py` — dùng cho outbound call + tái dụng trong extraction_local (`_typed_value`, `_duration_phrase`)*

```python
_DIGIT = {"khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4,
          "nam": 5, "lam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9}

def digits_only(text: str) -> str:
    """"không bảy chín, không tám ba" → "079083" (SĐT/CCCD đọc rời từng số)."""
    out = []
    for t in _toks(text):                    # _toks = normalize_vi().split()
        if t.isdigit(): out.append(t)
        elif t in _DIGIT and t != "muoi": out.append(str(_DIGIT[t]))
    return "".join(out)

def _small_number(toks, i):
    """0-99: hiểu "mười lăm", "hai mươi", "hai mươi mốt", số rời, digits."""
    # ... (xử lý "muoi" làm chục, "lam/tu" biến thể của 5/4)
```

Kèm `_year()` hiểu cả "một nghìn chín trăm tám mươi sáu", "một chín tám sáu"
lẫn "tám sáu" (→ 1986). Toàn bộ chạy trên match-form nên chịu được biến thể
ASR ("năm" viết không dấu = "nam" vẫn ra 5).

## Tầng 5 · Coercion đầu ra — chống "[object Object]"
*File: `app/core/extraction.py` (dispatcher) — bug thật gặp 18/07 khi test mic*

```python
def _stringify(v):
    if isinstance(v, dict):
        return " — ".join(_stringify(x) for x in v.values() if x not in (None, "", []))
    if isinstance(v, list):
        return "; ".join(_stringify(x) for x in v if x not in (None, "", []))
    return str(v)

def _coerce_value(ftype, value):
    if ftype == "list":
        items = value if isinstance(value, list) else [value]
        return [_stringify(x) for x in items if x not in (None, "", [])]
    if ftype == "number":
        f = float(value); return int(f) if f.is_integer() else f
    if isinstance(value, (dict, list)): return _stringify(value)
    return value
```

Mọi giá trị trước khi vào FormStore đều bị ép đúng schema field (`list[str]`
/ `str` / `number`) — extractor nào (local hôm nay, LLM nếu bật lại sau này)
trả object cũng không làm vỡ UI/PDF/mail.

---

# PHẦN B — TỪ ĐIỂN NER: từ chữ ra NGHĨA nghiệp vụ (không LLM ngoài)

Sau decision 0010, toàn bộ "hiểu nghĩa" là **engine local xếp chồng 5 pass**,
mỗi pass đổ *ứng viên* `(value, confidence, evidence)` vào rổ `Cands`, cuối
cùng chọn ứng viên tốt nhất per field. *File: `app/core/extraction_local.py`.*

## B1. Tiền xử lý câu + suy đoán vai người nói

```python
_SPEAKER_RE = re.compile(r"^\s*([^:\n]{2,30}):\s*")
_CUSTOMER_HINTS = ("khách", "chủ xe", "người bị nạn", "bệnh nhân", "người khai")
_AGENT_HINTS    = ("giám định", "tổng đài", "bác sĩ", "bac si", "điều dưỡng")

class Sent:
    def __init__(self, speaker, text):
        self.text = text.strip()
        self.low  = self.text.lower()   # CÓ dấu — match domain kw ("của"≠"cửa")
        self.norm = [normalize_vi(t) for t in self.text.split()]  # BỎ dấu — match anchor
        self.is_agent = any(h in speaker.lower() for h in _AGENT_HINTS)
```

Vai trò quyết định độ chính xác: **triệu chứng chỉ lấy từ lời bệnh nhân**,
**chẩn đoán chỉ lấy từ lời bác sĩ**, câu recap nhiều biển số của giám định
viên bị bỏ qua khi gán biển số.

## B2. Pass anchor — synonyms của pack là "mỏ neo" chỉ chỗ giá trị

```python
def _pass_anchor(pack, sents, cands):
    for f in pack.all_fields():
        if f.name.startswith("ten_"):   # tên người: synonyms "anh/chị" match bừa
            continue                    # → nhường cho chiến lược riêng + NER
        phrases = [f.label] + list(f.synonyms)          # ← TỪ ĐIỂN
        for s in sents:
            if s.text.rstrip().endswith("?"):
                continue                # câu HỎI hiếm khi chứa giá trị
            i = _find_phrase(s.norm, phrase_norm)       # so token đã bỏ dấu
            raw = _span_after(s, i + len(phrase_norm))  # giá trị đứng SAU anchor
            val = _typed_value(f, raw, s)               # ép kiểu theo field.type
            if f.name in validators:                    # field có regex validator
                m = re.search(validators[f.name], f"{raw} {s.text}")
                val = m.group(0) if m else None         # → chỉ nhận phần khớp regex
            cands.add(f.name, val, 0.68, s.text)
```

`_span_after` bỏ từ nối đầu ("là", "của", "ở"…) và cắt ở dấu câu — ví dụ câu
*"biển số **là 51H-123.45**, anh đang…"* → anchor "biển số" → giá trị
"51H-123.45".

## B3. Pass domain — catalog sinh từ chính `hint_terms` của pack

Điểm mấu chốt: **danh mục nhận diện không hard-code trong engine mà rút từ
từ điển pack**, ví dụ catalog phụ tùng xe:

```python
def _vehicle_parts(pack):
    """Catalog phụ tùng từ hint_terms pack (lọc cụm danh từ vật lý)."""
    hints = [t for t in pack.hint_terms
             if any(w in normalize_vi(t) for w in
                    ("yem", "guong", "can", "den", "kinh", "nep", "capo", ...))]
    return sorted(dedupe(hints + generic), key=lambda x: -len(x))  # cụm dài match trước
```

Vài luật domain tiêu biểu (bảo hiểm):

```python
# động từ hỏng đứng GẦN NHẤT trước phụ tùng (≤5 token) → "vỡ yếm xe", "gãy gương…"
verb = _verb_near_part(low_toks, part_idx)
# phân biệt XE KHÁCH vs XE ĐỐI PHƯƠNG bằng ngữ cảnh sát mỗi xe:
attacker = re.search(r"(?:bị|một)\s*(?:chiếc|xe)?\s*$", pre) or \
           re.search(r"^\s*...(?:tông|đâm|va|húc)", post)   # "bị một xe SH ... tông"
# biển số lấy cái đứng NGAY SAU tên xe đó (≤30 ký tự) → "SH — 59T1-888.22"
# enum nguyen_nhan: đếm keyword có dấu ("đâm/tông"→va chạm, "ngập/thủy kích"→ngập nước)
```

Y tế tương tự: `_MED_RE` bắt *Tên thuốc + liều*, phân 3 nhóm bằng ngữ cảnh
(`kê` → thuốc mới · `như cũ` → duy trì · `tăng liều/từ X lên Y` →
`"Amlodipine 5mg → 10mg"`); `_METRIC_RE` bắt chỉ số *EF/LDL-C/AST…+giá trị*;
lexicon bệnh lấy từ `specialties[].hint_terms` để nhận chẩn đoán nói gián tiếp.

## B4. Pass semantic_tags (VALSEA) + Pass NER (PyTorch) — 2 nguồn đối chiếu độc lập

```python
# VALSEA semantic_tags {tag, phrase, meaning} → field khớp label/synonyms (fuzzy ≥70)
score = fuzz.token_set_ratio(normalize_vi(label), normalize_vi(field_name_or_syn))

# NER local (app/core/ml/ner_local.py): NlpHUST/ner-vietnamese-electra-base, CPU
FIELD_LABELS = {"ten_khach_hang": {"PERSON"}, "ten_benh_nhan": {"PERSON"},
                "vi_tri": {"LOCATION"}, "xe_khach": {"MISCELLANEOUS"}, ...}
def agreement(transcript, field_values):
    ents = _pipe()(transcript)          # transformers token-classification
    # field khớp entity nếu normalize_vi hai bên chứa nhau / giao token
    ...
    return matched/total, {field: bool}  # → FormScorer (trọng số 0.15) + cờ
                                         #   "NER local không xác nhận" ở Màn Duyệt
```

NER ở đây đóng **hai vai**: (1) bổ khuyết tên người/địa điểm khi rule trượt
(conf 0.55–0.6, thấp hơn rule chủ đích); (2) **verifier độc lập** — đối chiếu
với giá trị đã trích để cộng/trừ điểm tin cậy. Thiếu torch → `available()=False`
→ degrade sạch, FormScorer tự phân bổ lại trọng số.

### ❓ PhoBERT có được dùng không? — KHÔNG (làm rõ lựa chọn model)

**Model NER đang chạy là `NlpHUST/ner-vietnamese-electra-base` (kiến trúc
ELECTRA, ~110M tham số, 4 nhãn PER/LOC/ORG/MISC), KHÔNG phải PhoBERT.**

```python
# app/core/ml/ner_local.py — model thật đang chạy
MODEL_ID = "NlpHUST/ner-vietnamese-electra-base"

@lru_cache(maxsize=1)
def _pipe():
    from transformers import pipeline
    return pipeline("token-classification", model=MODEL_ID,
                    aggregation_strategy="simple", device=-1)   # CPU
```

Lý do chọn ELECTRA thay vì PhoBERT cho pilot 48h:

| Tiêu chí | NlpHUST electra (đang dùng) | PhoBERT (vinai/phobert-base) |
| --- | --- | --- |
| Head NER có sẵn | ✅ checkpoint token-classification dùng ngay qua `pipeline()` | ❌ là pretrained LM thuần (RoBERTa) — muốn NER phải fine-tune hoặc tìm checkpoint bên thứ ba |
| Tiền xử lý | Tokenizer chạy thẳng trên câu thô | Yêu cầu **tách từ tiếng Việt trước** (VnCoreNLP/underthesea — thêm dependency nặng, có cả Java) không phù hợp đường live |
| Vai trò trong pipeline | Chỉ cần PER/LOC/MISC làm *verifier + bổ khuyết* — electra đủ chất lượng, đã smoke test (PERSON "Tuấn", LOCATION "đường Cộng Hòa", MISC "Toyota Vios", agreement 1.0) | Sức mạnh của PhoBERT nằm ở fine-tune chuyên sâu — chưa cần ở tầng này |

**PhoBERT nằm ở đâu trong lộ trình:** giai đoạn nâng cấp từ điển lên *lexicon
sense-entry* (mục C.3), nếu tầng rule bão hòa thì mới cân nhắc **lexicon-enhanced
NER kiểu SoftLexicon/FLAT fine-tune trên nền PhoBERT** với dữ liệu ngành thu
từ pilot — lúc đó PhoBERT mới xứng chi phí (fine-tune + word segmentation).
Kết luận: hôm nay PhoBERT = 0 dòng code chạy; chỉ là ứng viên đã ghi trong
roadmap.

## B5. Chọn ứng viên + validator nâng điểm

```python
best = max(cands, key=lambda t: t[1])            # scalar: conf cao nhất thắng
# list: gộp mọi nguồn, dedupe theo normalize_vi(item)
for v in pack.scoring.validators:                # biển số khớp regex trọn vẹn
    if re.fullmatch(v.value, str(x)): conf = max(conf, 0.92)   # → viền xanh UI
```

Confidence chảy tiếp vào: màu viền field trên UI → FormScorer (0.35 trọng số,
field bắt buộc ×2) → gate GỬI ≥85/60 → audit trail.

## B6. Từ điển TRIGGER (action) — người anh em của NER dictionary
*File: `app/core/triggers.py`*

```python
al = fuzz.partial_ratio_alignment(trigger_norm, haystack_norm)   # fuzzy ≥85
# dominance filter: 2 action khớp CHỒNG LẤN cùng đoạn text ("cứu hộ ô tô" vs
# "cứu hộ xe máy" chung tiền tố dài) → chỉ giữ action điểm cao nhất
if inter / span > 0.5 and k.score > c.score: dominated = True
```

Partial chỉ quét **cửa sổ đuôi** (`max_variant_tokens + 3` từ — partial lớn
dần, chỉ phần đuôi là mới), final quét cả câu (bắt trigger nằm giữa câu dài).
Đo thật: arm 0.2–0.9ms. *Bản vá worktree US-101 (chờ merge) bổ sung: chặn
phủ định `đừng|khoan|chưa cần|không cần` đứng ngay trước trigger + enforce
`required_fields` trước khi fire.*

---

## C. Hạn chế trung thực & lộ trình

1. **Extractor local tune theo bộ A–J** (eval gold 10/10 case, 86/86 field,
   ~200ms/lượt) — ngoài phân phối sẽ yếu hơn LLM; bù bằng: từ điển pack mở
   rộng được không cần code, NER verifier, và human gate ở Màn Duyệt.
2. Luật phủ định hiện là blacklist từ — chưa hiểu điều kiện phức
   ("nếu 30 phút nữa chưa ai tới thì gửi"). Phương án LLM-judge đã đề xuất,
   **chưa chốt** (mâu thuẫn decision 0010).
3. Bước kế của từ điển NER (đã tư vấn, chưa build): nâng `hint_terms` phẳng
   lên **lexicon sense-entry** (concept–sense–surface, cờ `standalone` /
   `require_context` / `block_context` / `asr_variants`), match bằng
   **trie leftmost-longest + cổng ngữ cảnh** trong `app/core/lexicon.py`
   — O(độ dài câu), vẫn pure Python cho live path; `hint_text` sinh tự động
   từ lexicon. ML nặng hơn (SoftLexicon/PhoBERT fine-tune) chỉ cân nhắc khi
   tầng rule bão hòa.

## D. Bản đồ file

> 📦 Tài liệu này là **standalone guide**: toàn bộ mã nguồn các file dưới đây được nhúng nguyên văn ở **Phụ lục E** cuối tài liệu.

| Cơ chế | File |
| --- | --- |
| hint_text builder (từ điển → ASR) | `app/packs/loader.py` |
| ITN theo pack + đơn vị liều | `app/core/normalize.py` + `itn_rules` trong `packs/*.json` |
| match-form bỏ dấu | `app/core/triggers.py::normalize_vi` |
| Số đọc chữ → chữ số (SĐT/năm sinh/biển số) | `app/telephony/parse_vi.py` |
| Engine hiểu nghĩa 5-pass | `app/core/extraction_local.py` (dispatcher: `extraction.py`) |
| NER PyTorch + agreement | `app/core/ml/ner_local.py` → `app/core/scoring.py` |
| Trigger dictionary + dominance | `app/core/triggers.py` |
| Coercion đầu ra | `app/core/extraction.py::_coerce_value` |
| Bộ kiểm chứng | `scripts/eval.py` (gold: `packs/testcases/*.json`) → `docs/product/scorecard.md` |

---

# PHỤ LỤC E — MÃ NGUỒN ĐẦY ĐỦ (standalone, không cần mở repo)

> Nhúng nguyên văn từ working tree lúc build tài liệu (18/07/2026). Nếu code
> trong repo đổi sau thời điểm này, chạy lại phần build ở cuối phụ lục để làm mới.

**Mục lục phụ lục:**

- E.1 [`app/packs/loader.py`](#e1-apppacksloaderpy) — Schema Domain Pack (Pydantic) + builder `hint_text` — điểm xuất phát của mọi từ điển (155 dòng)
- E.2 [`packs/insurance_motor.json`](#e2-packsinsurancemotorjson) — VÍ DỤ TỪ ĐIỂN HOÀN CHỈNH — pack bảo hiểm: form schema, actions+triggers, hint_terms, itn_rules, validators (pack y tế cùng cấu trúc, xem repo) (359 dòng)
- E.3 [`app/core/normalize.py`](#e3-appcorenormalizepy) — Tầng 2 — ITN theo từ điển pack (đơn vị liều, decimal-slash, itn_rules) (34 dòng)
- E.4 [`app/core/triggers.py`](#e4-appcoretriggerspy) — Tầng 3 (normalize_vi) + từ điển TRIGGER: fuzzy match, dominance filter, arm/fire state machine (146 dòng)
- E.5 [`app/telephony/parse_vi.py`](#e5-apptelephonyparsevipy) — Tầng 4 — parser số đọc chữ / ngày / SĐT / biển số (field-aware, không LLM) (240 dòng)
- E.6 [`app/core/extraction.py`](#e6-appcoreextractionpy) — Dispatcher extraction + Tầng 5 coercion (_stringify/_coerce_value) chống [object Object] (75 dòng)
- E.7 [`app/core/extraction_local.py`](#e7-appcoreextractionlocalpy) — TRÁI TIM PHẦN B — engine hiểu nghĩa 5-pass: sentences+speaker, anchor, semantic_tags, domain (bảo hiểm/y tế), NER pass, chọn ứng viên + validator boost (756 dòng)
- E.8 [`app/core/ml/ner_local.py`](#e8-appcoremlnerlocalpy) — NER local PyTorch (NlpHUST electra) — entities + agreement verifier (80 dòng)
- E.9 [`app/core/scoring.py`](#e9-appcorescoringpy) — FormScorer — nơi confidence/agreement/validator của từ điển đổ về thành điểm 0–100 (120 dòng)
- E.10 [`scripts/eval.py`](#e10-scriptsevalpy) — Bộ kiểm chứng: matcher fuzzy khoan dung đơn vị, chấm field-level vs gold, text/audio mode (218 dòng)

## E.1 `app/packs/loader.py`

*Vai trò: Schema Domain Pack (Pydantic) + builder `hint_text` — điểm xuất phát của mọi từ điển.*

````python
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


_PACK_ORDER = ["insurance_motor", "healthcare_exam", "insurance_contract"]


def load_all() -> dict[str, Pack]:
    packs: dict[str, Pack] = {}
    for p in sorted(PACKS_DIR.glob("*.json")):
        pack = Pack.model_validate(json.loads(p.read_text(encoding="utf-8")))
        packs[pack.id] = pack
    order = {pid: i for i, pid in enumerate(_PACK_ORDER)}
    return dict(sorted(packs.items(), key=lambda kv: order.get(kv[0], 99)))
````

## E.2 `packs/insurance_motor.json`

*Vai trò: VÍ DỤ TỪ ĐIỂN HOÀN CHỈNH — pack bảo hiểm: form schema, actions+triggers, hint_terms, itn_rules, validators (pack y tế cùng cấu trúc, xem repo).*

````json
{
  "id": "insurance_motor",
  "name": "Bảo hiểm — Giám định tai nạn xe",
  "icon": "🛡️",
  "form": {
    "title": "Phiếu ghi nhận tổn thất hiện trường",
    "sections": [
      {
        "title": "Thông tin khai báo",
        "fields": [
          {
            "name": "ten_khach_hang",
            "label": "Tên khách hàng",
            "type": "text",
            "required": true,
            "synonyms": [
              "người khai",
              "chủ xe",
              "người bị nạn",
              "tài xế"
            ]
          },
          {
            "name": "vi_tri",
            "label": "Vị trí sự cố",
            "type": "text",
            "required": true,
            "synonyms": [
              "địa điểm",
              "hiện trường",
              "nơi xảy ra"
            ]
          },
          {
            "name": "thoi_diem",
            "label": "Thời điểm sự cố",
            "type": "text",
            "required": false,
            "synonyms": [
              "lúc",
              "khi nào",
              "thời gian"
            ]
          },
          {
            "name": "nguyen_nhan",
            "label": "Nguyên nhân sơ bộ",
            "type": "enum",
            "required": false,
            "options": [
              "va chạm",
              "ngập nước",
              "trộm cắp bộ phận",
              "cháy nổ",
              "khác"
            ],
            "synonyms": [
              "lý do",
              "do đâu"
            ]
          },
          {
            "name": "so_gcn",
            "label": "Số GCN bảo hiểm / hợp đồng",
            "type": "text",
            "required": false,
            "synonyms": [
              "giấy chứng nhận",
              "số hợp đồng",
              "số thẻ bảo hiểm"
            ]
          }
        ]
      },
      {
        "title": "Phương tiện",
        "fields": [
          {
            "name": "xe_khach",
            "label": "Xe của khách (hãng/mẫu)",
            "type": "text",
            "required": true,
            "synonyms": [
              "xe của anh",
              "xe của chị",
              "phương tiện"
            ]
          },
          {
            "name": "bien_so_xe_khach",
            "label": "Biển số xe khách",
            "type": "text",
            "required": false,
            "itn": true,
            "synonyms": [
              "biển kiểm soát",
              "biển số"
            ]
          },
          {
            "name": "xe_lien_quan",
            "label": "Xe liên quan (mẫu — biển số)",
            "type": "list",
            "required": false,
            "synonyms": [
              "xe đối phương",
              "xe bên kia",
              "xe thứ hai",
              "xe thứ ba"
            ],
            "item_hint": "mỗi phần tử: '<hãng/mẫu xe> — <biển số>' nếu có biển số"
          }
        ]
      },
      {
        "title": "Tổn thất & thương tích",
        "fields": [
          {
            "name": "hu_hong_xe_khach",
            "label": "Hư hỏng xe khách",
            "type": "list",
            "required": true,
            "synonyms": [
              "thiệt hại",
              "hỏng chỗ nào",
              "tổn thất xe"
            ]
          },
          {
            "name": "hu_hong_xe_lien_quan",
            "label": "Hư hỏng xe liên quan",
            "type": "list",
            "required": false
          },
          {
            "name": "hang_muc_mat_cap",
            "label": "Hạng mục mất cắp/bị phá",
            "type": "list",
            "required": false,
            "synonyms": [
              "bị trộm",
              "bị gỡ",
              "bị cạy",
              "mất"
            ]
          },
          {
            "name": "thuong_tich",
            "label": "Thương tích / tình trạng người",
            "type": "textarea",
            "required": false,
            "synonyms": [
              "bị thương",
              "sức khỏe",
              "có ai bị sao không"
            ]
          },
          {
            "name": "bang_chung",
            "label": "Bằng chứng hiện có",
            "type": "list",
            "required": false,
            "synonyms": [
              "camera",
              "hình ảnh",
              "clip",
              "nhân chứng"
            ]
          }
        ]
      }
    ]
  },
  "actions": [
    {
      "id": "REQUEST_MOTORBIKE_TOWING",
      "label": "Gửi yêu cầu cứu hộ xe máy",
      "triggers": [
        "bấm vào nút gửi yêu cầu cứu hộ xe máy",
        "bấm nút gửi yêu cầu cứu hộ xe máy",
        "gửi yêu cầu cứu hộ xe máy"
      ],
      "confirm": "auto",
      "required_fields": [
        "vi_tri",
        "xe_khach"
      ],
      "tts_confirm": "Đã ghi nhận. Yêu cầu cứu hộ xe máy đang được gửi đi, xe cứu hộ sẽ đến trong khoảng hai mươi phút.",
      "template": "towing_request"
    },
    {
      "id": "REQUEST_CAR_TOWING",
      "label": "Gửi yêu cầu cứu hộ ô tô",
      "triggers": [
        "bấm nút gửi yêu cầu cứu hộ ô tô",
        "gửi yêu cầu cứu hộ ô tô",
        "yêu cầu cứu hộ ô tô giúp"
      ],
      "confirm": "auto",
      "required_fields": [
        "vi_tri",
        "xe_khach"
      ],
      "tts_confirm": "Đã ghi nhận. Yêu cầu cứu hộ ô tô đang được gửi đi. Anh chị vui lòng không nổ máy lại để tránh thủy kích nặng hơn.",
      "template": "towing_request"
    },
    {
      "id": "CONFIRM_PERSONAL_INJURY",
      "label": "Xác nhận có người bị thương",
      "triggers": [
        "bấm nút xác nhận có người bị thương",
        "xác nhận có người bị thương trên hệ thống",
        "xác nhận có người bị thương"
      ],
      "confirm": "auto",
      "required_fields": [
        "thuong_tich"
      ],
      "tts_confirm": "Đã xác nhận có người bị thương. Quy trình bồi thường nhân thân được kích hoạt, tổng đài y tế sẽ liên hệ ngay.",
      "template": "injury_confirmation"
    },
    {
      "id": "SUBMIT_MULTI_VEHICLE_COLLISION_REPORT",
      "label": "Gửi biên bản va chạm liên hoàn",
      "triggers": [
        "bấm nút gửi biên bản va chạm liên hoàn",
        "gửi biên bản va chạm liên hoàn"
      ],
      "confirm": "click",
      "required_fields": [
        "ten_khach_hang",
        "vi_tri",
        "xe_khach",
        "xe_lien_quan"
      ],
      "tts_confirm": "Biên bản va chạm liên hoàn đã được gửi cho bộ phận pháp chế xử lý.",
      "template": "multi_vehicle_report"
    },
    {
      "id": "SUBMIT_THEFT_PARTS_REPORT",
      "label": "Gửi báo cáo mất cắp phụ tùng",
      "triggers": [
        "bấm nút gửi báo cáo mất cắp phụ tùng",
        "gửi báo cáo mất cắp phụ tùng",
        "gửi hồ sơ mất cắp bộ phận xe"
      ],
      "confirm": "click",
      "required_fields": [
        "ten_khach_hang",
        "vi_tri",
        "hang_muc_mat_cap"
      ],
      "tts_confirm": "Báo cáo mất cắp phụ tùng đã được gửi. Bộ phận giám định sẽ đối chiếu camera trong hai mươi bốn giờ.",
      "template": "theft_report"
    },
    {
      "id": "SCHEDULE_SURVEYOR_VISIT",
      "label": "Hẹn giám định viên tới hiện trường",
      "triggers": [
        "bấm nút hẹn giám định viên tới hiện trường",
        "hẹn giám định viên xuống hiện trường",
        "đặt lịch giám định hiện trường"
      ],
      "confirm": "click",
      "required_fields": [
        "vi_tri"
      ],
      "tts_confirm": "Đã đặt lịch. Giám định viên sẽ có mặt tại hiện trường trong thời gian sớm nhất.",
      "template": "surveyor_visit"
    }
  ],
  "hint_terms": [
    "giám định viên",
    "cứu hộ",
    "hiện trường",
    "bồi thường",
    "giấy chứng nhận bảo hiểm",
    "Wave Alpha",
    "Toyota Vios",
    "Honda CR-V",
    "Ford Ranger",
    "Honda SH",
    "Mazda CX-5",
    "Toyota Camry",
    "xe buýt",
    "xe tải",
    "59A-987.65",
    "51F-555.88",
    "51C-111.22",
    "59-S1 345.67",
    "51B-234.56",
    "51H-368.24",
    "30G-555.12",
    "yếm xe",
    "gương chiếu hậu",
    "cản sau",
    "cản trước",
    "đèn sương mù",
    "lưới tản nhiệt",
    "kính chắn gió",
    "kính cửa sổ",
    "nẹp cốp",
    "capo",
    "la giăng",
    "thủy kích",
    "ngập nước",
    "chết máy",
    "không khởi động được",
    "trầy xước",
    "móp",
    "va quệt",
    "va chạm liên hoàn",
    "camera hành trình",
    "camera bãi xe",
    "bãi giữ xe",
    "đường Cộng Hòa",
    "cao tốc Long Thành - Dầu Giây",
    "cầu Sài Gòn",
    "hầm chung cư"
  ],
  "itn_rules": [
    {
      "pattern": "năm mốt hát",
      "replace": "51H"
    },
    {
      "pattern": "năm chín a",
      "replace": "59A"
    }
  ],
  "few_shots": [
    {
      "transcript": "Giám định viên: Em chào anh Bình, anh báo xe bị sự cố ở hầm gửi xe tòa nhà Sunrise đúng không ạ? Chủ xe: Đúng rồi em, mưa lớn quá nước tràn vô hầm, chiếc Kia Morning biển số 51G-234.56 của anh chết máy luôn, anh không dám đề lại. Giám định viên: Dạ anh làm đúng rồi, đề lại là dễ thủy kích lắm. Em ghi nhận nhé, anh bấm nút gửi yêu cầu cứu hộ ô tô giúp em.",
      "expected": {
        "ten_khach_hang": "Bình",
        "vi_tri": "hầm gửi xe tòa nhà Sunrise",
        "nguyen_nhan": "ngập nước",
        "xe_khach": "Kia Morning",
        "bien_so_xe_khach": "51G-234.56",
        "hu_hong_xe_khach": [
          "chết máy do ngập nước, chưa đề lại"
        ],
        "xe_lien_quan": null,
        "thuong_tich": null
      }
    }
  ],
  "extraction_instructions": "Đây là hội thoại giám định bảo hiểm xe. Phân biệt rõ XE CỦA KHÁCH và XE LIÊN QUAN (đối phương): 'xe tôi/xe anh/xe chị' là xe khách; xe đâm vào/bị đâm là xe liên quan. Biển số viết dạng chuẩn '59A-987.65' (2 số + serie + 3 số chấm 2 số, xe máy có thể '59-S1 345.67'). Hư hỏng tách thành từng mục ngắn. Thương tích của NGƯỜI ghi vào thuong_tich, không lẫn với hư hỏng xe. nguyen_nhan chọn đúng một giá trị enum. Không suy diễn thông tin không được nói.",
  "scoring": {
    "submit_threshold": 85,
    "validators": [
      {
        "field": "bien_so_xe_khach",
        "rule": "regex",
        "value": "^\\d{2}[A-Z]{1,2}\\d?\\s?-?\\s?\\d{3}\\.?\\d{2}$|^\\d{2}-?[A-Z]\\d\\s?\\d{3}\\.?\\d{2}$"
      }
    ]
  }
}
````

## E.3 `app/core/normalize.py`

*Vai trò: Tầng 2 — ITN theo từ điển pack (đơn vị liều, decimal-slash, itn_rules).*

````python
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
````

## E.4 `app/core/triggers.py`

*Vai trò: Tầng 3 (normalize_vi) + từ điển TRIGGER: fuzzy match, dominance filter, arm/fire state machine.*

````python
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
````

## E.5 `app/telephony/parse_vi.py`

*Vai trò: Tầng 4 — parser số đọc chữ / ngày / SĐT / biển số (field-aware, không LLM).*

````python
"""Parser tiếng Việt field-aware cho outbound call — KHÔNG LLM.

Kịch bản có sẵn nên engine biết đang hỏi field nào → parse câu trả lời của
khách bằng rule thuần (số đọc chữ → chữ số, ngày sinh, CCCD, biển số, địa
chỉ). Chạy trên text ĐÃ qua VALSEA correction + apply_itn của pack.
So khớp trên dạng bỏ dấu (normalize_vi) để chịu được biến thể ASR.
"""
from __future__ import annotations

import re

from app.core.triggers import normalize_vi
from app.packs.loader import Pack

# chữ số đọc rời (dạng bỏ dấu) — "nam"/"lam" = 5, "tu" = 4, "muoi" xử lý riêng
_DIGIT = {
    "khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4,
    "nam": 5, "lam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9,
}
_TENS_WORD = "muoi"          # "hai mươi", "mười lăm"


def _toks(text: str) -> list[str]:
    return normalize_vi(text).split()


# ---------------------------------------------------------------- số rời
def digits_only(text: str) -> str:
    """Gom MỌI chữ số trong câu (đọc rời từng số hoặc ASR đã ra số).
    "không bảy chín, không tám ba" → "079083"; "079 083" → "079083"."""
    out: list[str] = []
    for t in _toks(text):
        if t.isdigit():
            out.append(t)
        elif t in _DIGIT and t != _TENS_WORD:
            out.append(str(_DIGIT[t]))
    return "".join(out)


# ---------------------------------------------------------------- số 0-99
def _small_number(toks: list[str], i: int) -> tuple[int | None, int]:
    """Đọc một số 0-99 từ vị trí i → (giá trị, vị trí kế). Hiểu 'mười lăm',
    'hai mươi', 'hai mươi mốt', 'ba mươi', số rời, và digits ('20')."""
    if i >= len(toks):
        return None, i
    t = toks[i]
    if t.isdigit():
        return int(t), i + 1
    if t == _TENS_WORD:                      # "mười", "mười lăm"
        val, j = 10, i + 1
        if j < len(toks) and toks[j] in _DIGIT:
            val += _DIGIT[toks[j]]
            j += 1
        return val, j
    if t in _DIGIT:
        val, j = _DIGIT[t], i + 1
        if j < len(toks) and toks[j] == _TENS_WORD:      # "hai mươi (mốt)"
            val, j = val * 10, j + 1
            if j < len(toks) and toks[j] in _DIGIT:
                val += _DIGIT[toks[j]]
                j += 1
        return val, j
    return None, i


def _year(toks: list[str], i: int) -> int | None:
    """Năm sau từ 'năm': '1986' | 'một nghìn chín trăm tám mươi sáu' |
    'một chín tám sáu' | 'tám sáu' (→ 19xx/20xx)."""
    if i < len(toks) and toks[i].isdigit() and len(toks[i]) == 4:
        return int(toks[i])
    # dạng đầy đủ có nghìn/trăm
    if any(t in ("nghin", "ngan") for t in toks[i:i + 6]):
        val = 0
        j = i
        while j < len(toks):
            t = toks[j]
            if t in _DIGIT:
                d = _DIGIT[t]
                if j + 1 < len(toks) and toks[j + 1] in ("nghin", "ngan"):
                    val += d * 1000
                    j += 2
                    continue
                if j + 1 < len(toks) and toks[j + 1] == "tram":
                    val += d * 100
                    j += 2
                    continue
                if j + 1 < len(toks) and toks[j + 1] == _TENS_WORD:
                    val += d * 10
                    j += 2
                    if j < len(toks) and toks[j] in _DIGIT:
                        val += _DIGIT[toks[j]]
                        j += 1
                    continue
                val += d
                j += 1
            elif t in (_TENS_WORD, "linh", "le"):
                j += 1
            else:
                break
        return val if 1900 <= val <= 2099 else None
    # dãy chữ số rời: 'một chín tám sáu' / 'tám sáu'
    ds: list[str] = []
    j = i
    while j < len(toks) and (toks[j] in _DIGIT or toks[j].isdigit()):
        ds.append(str(_DIGIT.get(toks[j], toks[j])))
        j += 1
    s = "".join(ds)
    if len(s) == 4:
        return int(s)
    if len(s) == 2:
        yy = int(s)
        return 1900 + yy if yy >= 30 else 2000 + yy
    return None


# ---------------------------------------------------------------- fields
def parse_date(text: str) -> str | None:
    """'hai mươi tháng tư năm một nghìn chín trăm tám mươi sáu' → 20/04/1986.
    Chấp nhận cả dạng ITN sẵn '20/04/1986' hoặc '20 tháng 4 năm 1986'."""
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{d:02d}/{mo:02d}/{y}"
    toks = _toks(text)
    try:
        i_th = toks.index("thang")
    except ValueError:
        return None
    # ngày: số 0-99 kết thúc NGAY TRƯỚC 'tháng' — thử cửa sổ dài trước để
    # "hai mươi tháng" ra 20 chứ không bắt cụt "mươi" = 10
    day = None
    for back in (3, 2, 1):
        j = i_th - back
        if j < 0:
            continue
        val, nxt = _small_number(toks, j)
        if val is not None and nxt == i_th and 1 <= val <= 31:
            day = val
            break
    month, j = _small_number(toks, i_th + 1)
    if day is None or month is None or not 1 <= month <= 12:
        return None
    year = None
    for k in range(j, min(j + 4, len(toks))):
        if toks[k] == "nam":
            year = _year(toks, k + 1)
            if year:
                break
    if year is None:
        return None
    return f"{day:02d}/{month:02d}/{year}"


def parse_id_number(text: str, length: int = 12) -> str | None:
    """CCCD: gom mọi chữ số trong câu trả lời; đúng `length` số thì nhận.
    Dài hơn → lấy dãy `length` số cuối cùng liên tiếp trong chuỗi gom được."""
    s = digits_only(text)
    if len(s) == length:
        return s
    if len(s) > length:
        return s[-length:]
    return None


def parse_plate(text: str) -> str | None:
    """Biển số: '51K, một hai ba chấm bốn lăm' → '51K-123.45'.
    Ưu tiên dạng đã chuẩn trong text; không thì ghép serie + 5 số quanh 'chấm'."""
    flat = re.sub(r"\s+", " ", text.upper())
    m = re.search(r"\b(\d{2}[A-Z]{1,2}\d?)\s*[- ]?\s*(\d{3})[.\s]?(\d{2})\b", flat)
    if m:
        return f"{m.group(1)}-{m.group(2)}.{m.group(3)}"
    m = re.search(r"\b(\d{2}[A-Z]{1,2}\d?)\b", flat)
    if not m:
        return None
    serie = m.group(1)
    tail = text[m.end():]
    toks = _toks(tail)
    ds: list[str] = []
    dot_at = -1
    for t in toks:
        if t == "cham":
            dot_at = len(ds)
        elif t.isdigit():
            ds.extend(list(t))
        elif t in _DIGIT and t != _TENS_WORD:
            ds.append(str(_DIGIT[t]))
        if len(ds) >= 5:
            break
    if len(ds) < 5:
        return None
    if dot_at not in (3,):               # mặc định 3+2
        dot_at = 3
    return f"{serie}-{''.join(ds[:dot_at])}.{''.join(ds[dot_at:dot_at + 2])}"


_ADDR_LEAD = re.compile(
    r"^(?:dạ|vâng|à|ừ|anh|chị|em|tôi|mình)?\s*(?:đang|hiện)?\s*(?:ở|tại|là)\s*",
    re.IGNORECASE)


def parse_address(text: str) -> str | None:
    """Địa chỉ: giữ nguyên văn, chỉ bỏ filler mở đầu ('anh đang ở…') và chuyển
    cụm số đọc chữ sau 'số/phường/quận' thành chữ số."""
    s = text.strip().strip(".。")
    s = _ADDR_LEAD.sub("", s, count=1).strip()
    if len(s) < 6:
        return None

    def _num_after(m: re.Match) -> str:
        kw, words = m.group(1), m.group(2)
        val, nxt = _small_number(_toks(words), 0)
        if val is None or nxt < len(_toks(words)):
            return m.group(0)
        return f"{kw} {val} "

    # "số mười hai" → "số 12"; "phường bốn" → "phường 4"; "quận ba" → "quận 3"
    s = re.sub(
        r"(?i)\b(số|phường|quận)\s+((?:[a-zà-ỹ]+\s?){1,3}?)(?=\s*(?:đường|phố|phường|quận|huyện|thành|tỉnh|,|$))",
        _num_after, s)
    s = re.sub(r"\s+,", ",", re.sub(r"\s+", " ", s)).strip()
    return s[0].upper() + s[1:] if s else None


def parse_field(pack: Pack, fieldname: str, heard: str) -> object | None:
    """Điểm vào duy nhất: field kịch bản + câu khách nói → giá trị chuẩn hoá."""
    spec = pack.field(fieldname)
    if spec is None or not heard.strip():
        return None
    if fieldname == "ngay_sinh" or spec.type == "date":
        return parse_date(heard)
    if fieldname == "so_cccd":
        return parse_id_number(heard, 12)
    if fieldname == "bien_so_xe":
        return parse_plate(heard)
    if fieldname == "dia_chi_lien_he":
        return parse_address(heard)
    v = heard.strip().strip(".。")
    return v if v else None
````

## E.6 `app/core/extraction.py`

*Vai trò: Dispatcher extraction + Tầng 5 coercion (_stringify/_coerce_value) chống [object Object].*

````python
"""Semantic extraction — engine LOCAL, không LLM ngoài (18/07: all-in VALSEA).

Groq đã được gỡ toàn pilot theo chỉ đạo của Long (decision 0010). `extract()`
giữ nguyên chữ ký cũ cho batch/live/eval (client/model/fast được chấp nhận
nhưng bỏ qua); phần hiểu nghĩa nằm ở `app/core/extraction_local.py`:
anchor synonyms pack + chiến lược domain (catalog từ hint_terms) + VALSEA
semantic_tags + NER local PyTorch. Chạy trong thread để không chặn event loop
(NER inference).
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.extraction_local import extract_local
from app.packs.loader import Pack


def _stringify(v: Any) -> str:
    """dict/list → chuỗi đọc được (fix '[object Object]' trên UI)."""
    if isinstance(v, dict):
        return " — ".join(_stringify(x) for x in v.values() if x not in (None, "", []))
    if isinstance(v, list):
        return "; ".join(_stringify(x) for x in v if x not in (None, "", []))
    return str(v)


def _coerce_value(ftype: str, value: Any) -> Any:
    """Ép kiểu giá trị đúng schema field (list[str] / str / number)."""
    if value in (None, "", []):
        return None
    if ftype == "list":
        items = value if isinstance(value, list) else [value]
        return [_stringify(x) for x in items if x not in (None, "", [])]
    if ftype == "number":
        try:
            f = float(value)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return _stringify(value)
    if isinstance(value, (dict, list)):
        return _stringify(value)
    return value


async def extract(
    pack: Pack,
    transcript: str,
    prev_state: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,   # giữ tương thích chữ ký cũ
    model: str = "",                            # (không dùng — engine local)
    fast: bool = False,                         # (không dùng — local luôn nhanh)
    semantic_tags: list | None = None,          # VALSEA verbose_json (batch)
) -> dict[str, dict]:
    """→ {field_name: {value, confidence, evidence}} (rỗng nếu không bắt được gì)."""
    del client, model, fast
    try:
        fields = await asyncio.to_thread(
            extract_local, pack, transcript, prev_state, semantic_tags)
    except Exception:  # noqa: BLE001 — extraction không bao giờ đánh sập pipeline
        return {}
    out: dict[str, dict] = {}
    for name, v in fields.items():
        spec = pack.field(name)
        if spec is None or not isinstance(v, dict):
            continue
        out[name] = {
            "value": _coerce_value(spec.type, v.get("value")),
            "confidence": float(v.get("confidence") or 0.0),
            "evidence": str(v.get("evidence") or "")[:200],
        }
    return out
````

## E.7 `app/core/extraction_local.py`

*Vai trò: TRÁI TIM PHẦN B — engine hiểu nghĩa 5-pass: sentences+speaker, anchor, semantic_tags, domain (bảo hiểm/y tế), NER pass, chọn ứng viên + validator boost.*

````python
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
````

## E.8 `app/core/ml/ner_local.py`

*Vai trò: NER local PyTorch (NlpHUST electra) — entities + agreement verifier.*

````python
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
````

## E.9 `app/core/scoring.py`

*Vai trò: FormScorer — nơi confidence/agreement/validator của từ điển đổ về thành điểm 0–100.*

````python
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
````

## E.10 `scripts/eval.py`

*Vai trò: Bộ kiểm chứng: matcher fuzzy khoan dung đơn vị, chấm field-level vs gold, text/audio mode.*

````python
"""Eval engine vs gold labels (KB A–F + testcase mở rộng).

Text-mode:  .venv/bin/python scripts/eval.py
Audio-mode: .venv/bin/python scripts/eval.py --audio   (cần assets/audio/*.wav — task P3a)

Chấm:
- Field text/textarea: token_set_ratio(normalize) ≥ 75.
- Field list: TỪNG mục gold phải khớp 1 mục extracted (≥75); biển số so exact alnum.
- Field enum: bằng nhau sau normalize.
- Action: gold action phải được arm khi scan_full; action khác KHÔNG được arm (false positive).
Ghi docs/product/scorecard.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from rapidfuzz import fuzz

from app.core.extraction import extract
from app.core.form_state import FormStore
from app.core.triggers import TriggerMatcher, normalize_vi
from app.packs.loader import load_all

CASE_FILES = [ROOT / "packs" / "testcases" / "kb_af.json",
              ROOT / "packs" / "testcases" / "extended_gj.json"]
AUDIO_DIR = ROOT / "assets" / "audio"
SCORECARD = ROOT / "docs" / "product" / "scorecard.md"

PLATE_RE = re.compile(r"\d{2}[-\s]?[A-Za-z]{1,2}\d?[-\s]?\d{3}[.\s]?\d{2}")
_UNIT_COLLAPSE = re.compile(r"(\d)\s+(mg|mcg|g|ml|mmol|mmhg|%)", re.IGNORECASE)


def _norm(s: str) -> str:
    """normalize_vi + gộp '5 mg'→'5mg' để so công bằng đơn vị liều."""
    return normalize_vi(_UNIT_COLLAPSE.sub(r"\1\2", str(s)))


def norm_plate(s: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", s.upper())


def has_plate(s: str) -> bool:
    return bool(PLATE_RE.search(s or ""))


def match_scalar(gold: str, got) -> bool:
    if got is None:
        return False
    got_s = str(got)
    if has_plate(str(gold)):
        gp = PLATE_RE.search(str(gold)).group()
        return norm_plate(gp) in norm_plate(got_s)
    return fuzz.token_set_ratio(_norm(gold), _norm(got_s)) >= 75


def match_list(gold_items: list, got) -> tuple[int, int]:
    if not isinstance(got, list):
        got = [got] if got not in (None, "") else []
    got_s = [str(x) for x in got]
    hit = 0
    for g in gold_items:
        ok = False
        for x in got_s:
            if has_plate(str(g)):
                gp = PLATE_RE.search(str(g)).group()
                base = normalize_vi(re.sub(re.escape(gp), " ", str(g)))
                plate_ok = norm_plate(gp) in norm_plate(x)
                text_ok = (not base.strip()) or fuzz.token_set_ratio(base, _norm(x)) >= 60
                ok = plate_ok and text_ok
            else:
                ok = fuzz.token_set_ratio(_norm(g), _norm(x)) >= 75
            if ok:
                break
        hit += int(ok)
    return hit, len(gold_items)


async def run_case(case: dict, packs, client, audio_variant: str = "") -> dict:
    """audio_variant: '' = text-mode; 'clean'|'noisy'|'telephony' = ASR trước."""
    from app.core import valsea

    pack = packs[case["pack_id"]]
    transcript, asr_ms = case["transcript"], 0
    if audio_variant:
        suffix = "" if audio_variant == "clean" else f"_{audio_variant}"
        wav = AUDIO_DIR / f"{case['id']}{suffix}.wav"
        if not wav.exists():
            return {"id": case["id"], "variant": audio_variant, "skipped": True}
        t0 = time.monotonic()
        verbose = await valsea.transcribe(wav.read_bytes(), wav.name, client=client)
        asr_ms = int((time.monotonic() - t0) * 1000)
        from app.core.normalize import apply_itn
        transcript = apply_itn(pack, verbose.get("text") or "")
    case = {**case, "transcript_used": transcript}
    t0 = time.monotonic()
    extraction = await extract(pack, transcript, client=client)
    extract_ms = int((time.monotonic() - t0) * 1000)

    store = FormStore(pack)
    store.merge(extraction)
    values = store.snapshot()

    field_hits, field_total, misses = 0, 0, []
    for name, gold in case["gold_fields"].items():
        got = values.get(name)
        if isinstance(gold, list):
            h, t = match_list(gold, got)
            field_hits += h
            field_total += t
            if h < t:
                misses.append(f"{name}: {h}/{t} (got={got})")
        else:
            field_total += 1
            if match_scalar(gold, got):
                field_hits += 1
            else:
                misses.append(f"{name}: gold='{gold}' got='{got}'")

    matcher = TriggerMatcher(pack)
    t0 = time.perf_counter()
    events = matcher.scan_full(transcript)
    trig_ms = (time.perf_counter() - t0) * 1000
    armed = {e.action.id for e in events if e.kind == "armed"}
    gold_actions = set(case["gold_actions"])
    action_ok = gold_actions <= armed
    false_pos = armed - gold_actions

    return {
        "id": case["id"], "title": case["title"], "pack": pack.id,
        "variant": audio_variant or "text",
        "field_hits": field_hits, "field_total": field_total,
        "misses": misses, "action_ok": action_ok,
        "false_pos": sorted(false_pos), "armed": sorted(armed),
        "asr_ms": asr_ms, "extract_ms": extract_ms, "trig_ms": round(trig_ms, 2),
        "passed": field_hits == field_total and action_ok and not false_pos,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", action="store_true", help="chạy qua VALSEA ASR từ assets/audio")
    ap.add_argument("--variants", default="clean",
                    help="audio-mode: clean,noisy,telephony (bỏ qua nếu thiếu file)")
    ap.add_argument("--only", default="", help="chỉ chạy các case id, vd A,B")
    args = ap.parse_args()

    packs = load_all()
    cases = []
    for f in CASE_FILES:
        if f.exists():
            cases += json.loads(f.read_text(encoding="utf-8"))["cases"]
    if args.only:
        keep = {x.strip().upper() for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in keep]

    variants = [v.strip() for v in args.variants.split(",") if v.strip()] if args.audio else [""]

    async with httpx.AsyncClient(timeout=180) as client:
        results = []
        for c in cases:  # tuần tự — tránh 429 rate-limit
            for v in variants:
                try:
                    r = await run_case(c, packs, client, audio_variant=v)
                except Exception as e:  # noqa: BLE001 — mạng đứt giữa chừng vẫn ghi scorecard
                    print(f"[CRASH] {c['id']}/{v or 'text'}: {str(e)[:120]}")
                    results.append({"id": c["id"], "title": c["title"],
                                    "pack": c["pack_id"], "variant": v or "text",
                                    "field_hits": 0,
                                    "field_total": len(c["gold_fields"]),
                                    "misses": [f"CRASH: {str(e)[:80]}"],
                                    "action_ok": False, "false_pos": [], "armed": [],
                                    "asr_ms": 0, "extract_ms": 0, "trig_ms": 0,
                                    "passed": False})
                    continue
                if r.get("skipped"):
                    continue
                results.append(r)
                print(f"[{ 'PASS' if r['passed'] else 'FAIL' }] {r['id']}/{r['variant']}: "
                      f"fields {r['field_hits']}/{r['field_total']}, "
                      f"action={'ok' if r['action_ok'] else 'MISS'}, fp={r['false_pos']}, "
                      f"asr={r['asr_ms']}ms extract={r['extract_ms']}ms trigger={r['trig_ms']}ms")
                for m in r["misses"]:
                    print(f"       miss → {m}")

    mode = "audio-mode (VALSEA ASR)" if args.audio else "text-mode"
    lines = [f"# Scorecard — eval {mode}", "",
             "| Case | Variant | Pack | Fields | Action | FalsePos | ASR | Extract | KQ |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    n_pass = 0
    for r in results:
        n_pass += int(r["passed"])
        lines.append(
            f"| {r['id']} {r['title'][:26]} | {r['variant']} | {r['pack']} "
            f"| {r['field_hits']}/{r['field_total']} "
            f"| {'✅' if r['action_ok'] else '❌'} | {','.join(r['false_pos']) or '—'} "
            f"| {r['asr_ms']}ms | {r['extract_ms']}ms | {'✅ PASS' if r['passed'] else '❌ FAIL'} |")
    total_fields = sum(r["field_total"] for r in results)
    hit_fields = sum(r["field_hits"] for r in results)
    lines += ["", f"**Tổng: {n_pass}/{len(results)} case PASS · field-level "
                  f"{hit_fields}/{total_fields} ({100*hit_fields/max(1,total_fields):.0f}%)**"]
    SCORECARD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n== {n_pass}/{len(results)} PASS · fields {hit_fields}/{total_fields} ==  → {SCORECARD}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
````

---

*Cách làm mới phụ lục khi code đổi:* chạy lại đoạn script Python đã dùng để build phần này (đọc các file trong Bản đồ mục D rồi nhúng lại), hoặc yêu cầu agent "rebuild phụ lục E".
