# Design — E9 VALSEA-only Semantic Engine

## Domain Model

`extraction_local.extract_local(pack, transcript, prev_state, semantic_tags)`
→ `{field: {value, confidence, evidence}}` — cùng contract với engine cũ,
FormStore/scoring/UI không đổi.

## Các lớp tín hiệu (chồng, chọn candidate conf cao nhất; list thì merge dedupe)

1. **Anchor-window** (generic mọi pack): label/synonyms của field → span giá
   trị đứng sau, ép kiểu theo `type` (date qua `parse_vi`, number, enum match
   options, list split). Bỏ qua câu hỏi "?"; field có validator regex thì chỉ
   nhận phần khớp regex; field `ten_*` không dùng anchor (synonym "anh/chị"
   match bừa) — dùng chiến lược tên riêng.
2. **VALSEA semantic_tags** (batch verbose_json): tag/meaning fuzzy-match
   label+synonyms ≥70 → phrase làm candidate (0.72).
3. **Chiến lược domain** — catalog lấy từ chính pack:
   - Bảo hiểm: tên sau kính ngữ (tần suất), vị trí (regex đường/cao tốc/hầm…,
     chạy cả trên câu hỏi vì GĐV hay nhắc lại), xe & biển số với ngữ cảnh
     SÁT MỖI XE ("bị một xe SH … tông" = xe đối phương; biển số lấy cái đứng
     ngay sau xe; danh từ xe kia/xe tải/xe buýt; câu recap nhiều biển của GĐV
     bỏ qua), hư hỏng = động từ gần phụ tùng nhất (+ "bên trái/phải"),
     hư hỏng standalone (chết máy, ngập tới…, đề không nổ), thương tích,
     bằng chứng, enum nguyên nhân qua keyword map.
   - Y tế: thuốc+liều (kể cả "từ 5mg lên 10mg" → "5mg → 10mg"), phân loại
     mới/duy trì/điều chỉnh theo động từ; CLS tách kết quả vs chỉ định theo
     ngữ cảnh mệnh đề (loại câu hỏi + câu nói về NÚT); chỉ số "LDL 4.9
     mmol/L", huyết áp "150 trên 95" → "150/95"; chuyên khoa = specialty
     nhiều hint_terms hit nhất; chẩn đoán ("chẩn đoán/kết luận", "bị/mắc" +
     lexicon bệnh từ specialties, fallback ghép mệnh đề bệnh + "nguy cơ…");
     tái khám = thời lượng số HOẶC CHỮ ("hai tuần nữa") quanh từ khoá.
   - Pack có `call_script`: tái dùng `parse_vi.parse_field` từng field.
4. **NER local PyTorch** (PhoBERT): PER→ten_*, LOC→vi_tri/dia_chi (conf thấp,
   chỉ bổ khuyết). Thiếu torch → bỏ lớp này, degrade sạch.

Matching domain trên chữ thường CÓ DẤU (bài học: "của"≠"cửa" khi bỏ dấu);
anchor match trên normalize_vi (chịu biến thể ASR). Validator pass → conf 0.92+.

## Narrative (actions.py)

VALSEA formatting (service_log/meeting_minutes) như cũ; không ra tiếng Việt →
`_template_narrative` ghép biên bản từ field đã điền — không LLM ngoài.

## Alternatives Considered

1. VALSEA formatting làm extractor — loại: output_type cố định, không map
   schema pack tuỳ ý.
2. NER local làm extractor chính — loại: không cover số liệu/liều/enum;
   giữ vai verifier.
