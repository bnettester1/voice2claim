# Exec Plan — E9 VALSEA-only: gỡ Groq toàn pilot

## Goal

Chỉ đạo của Long 18/07: **bỏ Groq, dùng toàn bộ API của VALSEA**. Toàn pipeline
(batch + live + outbound call) không còn LLM ngoài; phần hiểu nghĩa chạy local,
tận dụng tối đa VALSEA (ASR + correction + semantic_tags + formatting + TTS).

## Scope

In scope:

- `app/core/extraction_local.py` — engine extraction mới (anchor synonyms,
  domain catalog từ hint_terms pack, semantic_tags VALSEA, NER PyTorch verify).
- `app/core/extraction.py` thành dispatcher (giữ nguyên interface cho callers).
- Gỡ: `_groq_narrative` (→ template), `app/core/baseline.py` + endpoint
  `/api/baseline` + panel đối chứng UI, probe Groq.
- Docs: AGENTS.md, architecture.md, README; decision 0010 supersede phần Groq
  của 0008.

Out of scope:

- Key `GROQ` trong apikey.txt/config (không code nào gọi; giữ config loader
  nguyên để không đụng phiên làm việc song song đang sửa config).
- E8 call path (đã VALSEA-only từ trước — decision 0009 cập nhật).

## Risk Classification

Risk flags: Existing behavior (extraction batch/live đổi engine), Weak proof
ban đầu (extractor mới), Multi-domain (2 pack + call). Hard gate: thay đổi
external provider behavior (bỏ hẳn 1 provider) → **high-risk** (intake #2).

## Work Phases

1. Engine local + dispatcher. 2. Gỡ Groq mọi nơi. 3. Proof: eval 10 case gold
+ E2E batch audio thật + unit 38. 4. Docs + decision + trace.

## Stop Conditions

- Nếu eval tụt sâu không cứu được bằng rule → dừng, báo Long trade-off.
  (Không xảy ra: kết quả 10/10.)
