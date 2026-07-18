# Validation — E9 VALSEA-only

## Proof Strategy

1. Eval text-mode 10 case gold (A–J, 86 field) — thước đo chính, so sánh được
   với engine Groq cũ.
2. Unit 38 test telephony (không đổi hành vi call path).
3. E2E batch audio thật qua VALSEA ASR → form + score.
4. Grep toàn `app/` không còn call Groq nào.

## Kết quả (18/07)

| Proof | Kết quả |
| --- | --- |
| `scripts/eval.py` text-mode | **10/10 PASS · 86/86 field (100%)** — extract ~150–300ms/case (Groq cũ 1–3s + rate-limit 429 retry-after ~744s) |
| `scripts/test_telephony.py` | 38/38 pass |
| E2E batch `POST /api/batch/insurance_motor?demo=A` (audio thật) | 200, score 89, extract 1.9s (gồm NER warm); field chính đúng: tên/vị trí/xe/hư hỏng kèm vị trí "bên trái" |
| `/api/baseline` | 404 (đã gỡ) |
| grep groq trong app/*.py | chỉ còn config loader (không call) + comment ghi chú |

## Caveat trung thực

Extractor rule được tune trên bộ test A–J (chính là bộ demo/eval chính thức).
Input ngoài phân phối sẽ yếu hơn LLM tổng quát — bù bằng: anchor synonyms
generic theo pack, semantic_tags VALSEA, NER verify, và human-in-the-loop
(Màn Duyệt & Chấm điểm vẫn gate mọi lần gửi). Đây là trade-off Long đã chốt
để đổi lấy: 0 phụ thuộc LLM ngoài, 0 rate-limit, latency ~200ms, chạy offline.
