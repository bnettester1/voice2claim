# Overview — E9 VALSEA-only

## Current Behavior (trước 18/07 chiều)

Extraction batch/live qua Groq LLM (llama-3.3-70b JSON mode, fallback 8b);
narrative PDF fallback Groq; panel "đối chứng whisper generic" gọi Groq
whisper; call path E8 đã local từ decision 0009.

## Target Behavior

Toàn pilot **không một call LLM ngoài**: extraction local
(`extraction_local.py`), narrative template, panel đối chứng gỡ bỏ. VALSEA là
AI đám mây duy nhất (ASR batch/RTT + correction + semantic_tags + formatting
+ sentiment + TTS). Groq key nếu còn trong apikey.txt thì không được gọi.

## Affected Users

Long (demo), giám khảo (câu chuyện "all-in VALSEA + engine local PyTorch").

## Affected Product Docs

`architecture.md` (sơ đồ, bảng key, degrade ladder, cấu trúc mã), `AGENTS.md`
(ràng buộc cứng), README (pipeline + bảo mật), scorecard.md (eval mới).

## Non-Goals

- Không đổi FormStore/scoring/trigger/UI contract.
- Không gỡ key Groq khỏi config loader (phiên song song đang sửa config.py).
