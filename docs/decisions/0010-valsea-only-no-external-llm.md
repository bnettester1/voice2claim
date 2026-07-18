# 0010 VALSEA-only — gỡ Groq, không LLM ngoài toàn pilot

Date: 2026-07-18

## Status

Accepted (supersede phần Groq của 0008; nối tiếp cập nhật trong 0009)

## Context

Long chốt 18/07: "bỏ Groq đi, dùng toàn bộ API của VALSEA". Nguyên nhân trực
tiếp: Groq free tier 429 với `retry-after` ~744s giữa demo (đã làm treo cuộc
gọi E8); nguyên nhân chiến lược: tiêu chí chấm "Best Use of VALSEA API" +
giảm phụ thuộc vendor ngoài.

## Decision

- **Extraction chạy local** — `app/core/extraction_local.py`: anchor
  synonyms pack + chiến lược domain (catalog từ hint_terms) + VALSEA
  `semantic_tags` + NER PyTorch verify; `extraction.py` giữ nguyên interface
  làm dispatcher. Call path E8 dùng `parse_vi.py` (0009).
- **Narrative PDF**: VALSEA `/v1/formatting` trước; không ra tiếng Việt →
  template ghép từ field (`_template_narrative`) — bỏ `_groq_narrative`.
- **Gỡ baseline đối chứng whisper** (module + endpoint + panel UI) — pilot
  không gọi Groq dưới bất kỳ hình thức nào.
- VALSEA là **AI đám mây duy nhất**; ElevenLabs chỉ còn: sinh audio test +
  giọng dự phòng outbound call.
- Key `GROQ` có thể còn nằm trong apikey.txt/config loader nhưng **không
  code nào được gọi** (giữ loader nguyên vì phiên song song đang sửa config).

## Alternatives Considered

1. Giữ Groq với fast-retry (đã làm buổi sáng) — loại: vẫn là điểm chết
   rate-limit giữa demo, và Long muốn all-in VALSEA.
2. VALSEA formatting làm extractor — loại: schema output cố định.
3. LLM local (llama.cpp) — loại: nặng máy demo, vượt scope 48h.

## Consequences

Positive:

- Eval gold: **10/10 case · 86/86 field** (engine Groq cũ từng 6/6 trên bộ
  A–F); extract ~200ms, không mạng, không rate-limit — demo không còn điểm
  chết LLM.
- Câu chuyện chấm điểm mạnh: VALSEA end-to-end + engine local PyTorch.

Tradeoffs:

- Extractor rule tune theo bộ test A–J; hội thoại ngoài phân phối sẽ kém hơn
  LLM tổng quát — chấp nhận nhờ human-in-the-loop gate (FormScorer) và vì
  demo chấm trên đúng bộ này.
- Thêm ~500 dòng rule cần bảo trì khi pack mở rộng.

## Follow-Up

- Khi thêm pack mới: viết chiến lược domain tương ứng hoặc dựa anchor generic.
- Cân nhắc hướng lexicon sense-entry (đã bàn, chưa chốt) làm nền tổng quát hoá.
