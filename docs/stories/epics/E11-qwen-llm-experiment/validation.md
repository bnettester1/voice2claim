# Validation — E11 Qwen 3.5 đối chứng

Chạy: `.venv/bin/python scripts/eval_qwen.py` (full A–J + N1q–N4q, có local
đối chứng). Report chi tiết: `eval-report-397b.md`, `eval-report-35b.md`.

## Kết quả 19/07

| Engine | Field (A–J) | Action sạch (14 case) | Chặn phủ định (4 case) | Latency median |
| --- | --- | --- | --- | --- |
| **Qwen qwen3.5-397b-a17b** | 78/86 (90%) | **14/14** | **4/4 ✅** | ~8.1s |
| Qwen qwen3.5-35b-a3b | 79/86 (91%) | 13/14 (1 FP case D) | 4/4 ✅ | ~6.8s |
| Local (extraction_local + TriggerMatcher, main) | **86/86 (100%)** | 10/14 | 0/4 ❌ (arm nhầm cả 4) | ~0.24s |

## Đọc số

- **Action là chỗ LLM thắng tuyệt đối**: 397b bắt đủ mọi gold action A–J và
  chặn cả 4 câu phủ định — đúng năng lực cần cho tầng "judge" mà Long đang
  cân nhắc (local trên main thua cả 4 vì US-101 chưa merge; kể cả merge,
  negation guard rule chỉ phủ từ điển phủ định cố định).
- **Field là chỗ local thắng**: 100% vs 90% — nhưng local được tune theo chính
  bộ A–J; miss của Qwen tập trung case D/F/J (field list nhiều mục kiểu đơn
  thuốc/chỉ số — xem q_miss trong report). Ngoài phân phối, kỳ vọng đảo chiều.
- **Latency ~7–8s**: KHÔNG realtime được (trần trigger 500ms) → nếu làm judge
  thì chạy ASYNC sau khi rule ARM (double-check trước fire hoặc audit sau
  fire), không nằm trên đường nóng.
- Bản 35b không đáng đổi: không nhanh hơn bao nhiêu, thêm 1 FP.

## Chưa kiểm

- Chưa đo trên transcript NGOÀI bộ gold (điểm yếu tune-theo-bộ của local sẽ
  lộ ở đây — cần bộ case mới nếu Long muốn quyết hybrid).
- Chưa nối judge vào đường live/call (đúng non-goal — chờ Long chốt).
