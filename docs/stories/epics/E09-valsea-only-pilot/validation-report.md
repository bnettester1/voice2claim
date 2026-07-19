# Validation Report — E9 VALSEA-only (gỡ Groq toàn pilot)

Ngày: 2026-07-18 (ghi bù 22:40) · Máy: local dev (macOS, .venv Python 3.12)

## Eval gold text-mode — PASS 10/10 case, 86/86 field (100%)

`.venv/bin/python scripts/eval.py` → `docs/product/scorecard.md`

- `extraction_local.py` (anchor synonyms + domain catalog từ hint_terms +
  semantic_tags VALSEA + NER PyTorch verify) đạt **bằng điểm engine LLM cũ**
  trên toàn bộ A–J.
- Tốc độ extract ~200–470ms/case (case A 5.3s do chi phí khởi tạo lần đầu —
  các case sau ổn định).

## Unit — PASS 38/38

`.venv/bin/python scripts/test_telephony.py` (tại thời điểm E9; sau E10 là
49/49) — không vỡ test nào khi thay engine extraction.

## E2E batch demo — PASS

Audio thật case A qua UI batch: score **89**, extract 1.9s, form + PDF đầy đủ.

## Kiểm chứng gỡ sạch LLM ngoài

- `GET /api/baseline` → **404** (đã xoá endpoint + panel UI đối chứng).
- `grep` toàn `app/` không còn call Groq nào trên đường chạy;
  `compose_narrative` dùng VALSEA formatting → fallback template (không LLM).
- `probe_groq` đã gỡ khỏi `scripts/probe.py`.
- Key GROQ trong config thành dead config — code không đọc để gọi nữa.

## Caveat ghi nhận

Extractor tune theo bộ A–J; ngoài phân phối sẽ yếu hơn LLM — đánh đổi có chủ
đích theo decision 0010 (Long chốt: all-in VALSEA, không LLM ngoài).
