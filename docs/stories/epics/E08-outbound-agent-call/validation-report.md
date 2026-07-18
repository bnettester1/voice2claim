# Validation Report — E8 Outbound Agent Call

Ngày: 2026-07-18 · Máy: local dev (macOS, .venv Python 3.12)

## Unit (offline, không key) — PASS 21/21

`.venv/bin/python scripts/test_telephony.py`

- codec: μ-law roundtrip mean err < 300 (thực đo ~hàng chục), resample 8k↔16k
  đúng độ dài, wav→ulaw8k.
- twilio: TwiML chứa đúng `wss://…/ws/twilio/{sid}`; `X-Twilio-Signature`
  valid/invalid/missing; mask số điện thoại.
- agent (engine stub): happy path 4/4 field + closing đủ; im lặng → reask ×3
  → skip toàn bộ → closing_partial, không ticket; khách bác xác nhận CCCD →
  reset + hỏi lại → giá trị đúng thắng.

## E2E local (key thật, mode replay) — PASS

Trang `/call` → Gọi cho khách: **66 giây**, 4/4 field điền đúng và chuẩn hoá
(`20/04/1986`, `079083001234`, `51K-123.45`, địa chỉ nguyên văn), 2 lượt xác
nhận giọng nói hoạt động, ITN `năm mốt ca → 51K` chạy trên final, ticket
**TCK-0012** + `contract_update_TCK-0012.pdf` (40KB, HTTP 200).

## Sự cố tìm thấy & đã vá trong lượt

Groq trả **429 với `retry-after: 744s`** cho llama-3.3-70b (json mode);
retry ladder cũ tôn trọng nguyên giá trị → extract treo ~12 phút giữa cuộc
gọi (đứng hình đúng nghĩa). Vá `app/core/extraction.py`: cap sleep (batch
15s), model bị khoá dài → bỏ qua và nhảy fallback 8b ngay; thêm `fast=True`
(thoại/live: timeout 12s/call, sleep cap 2s, ngân sách ~15s) — engine gọi
`fast=True`, LiveSession (E5) cũng chuyển sang fast. Đã kiểm chứng 8b thoát
khoá (200/0.6s, extract đúng) và cuộc gọi lần 2 chạy trơn.

## Chưa kiểm (cần input của Long)

Mode `twilio` end-to-end cần TWILIO_* + PUBLIC_BASE_URL (tunnel) — runbook
trong README. Mode `browser` mới smoke qua code path chung (transport +
worklet tái dùng từ E5); nên tập dượt bằng mic thật trước demo.

## Addendum 18/07 chiều — bỏ Groq khỏi call path (chỉ đạo của Long)

Thay đổi: extraction Groq → `parse_vi.py` (rule field-aware, không LLM ngoài);
TTS đổi chiều ưu tiên VALSEA → ElevenLabs dự phòng.

- Unit: **38/38 pass** (thêm 17 test parser: ngày sinh 7 biến thể kể cả
  "hai nghìn lẻ một", CCCD chống nhiễu "mười hai số", biển số đọc chữ,
  địa chỉ chuẩn hoá "số mười hai → số 12"; 2 case cố tình không parse được
  → None để agent re-ask).
- E2E replay lần 2 (sau thay đổi): **HOÀN TẤT 01:44**, 4/4 field —
  confidence 95% cho 3 field có validator, 85% địa chỉ; ticket + PDF OK;
  toàn cuộc gọi không một call Groq nào (Groq đang bị khoá 429 vẫn chạy mượt
  — chính là điều kiện lỗi đã làm treo bản đầu).
- Lưu ý còn lại: `compose_narrative` trong Action Executor (dùng chung với
  batch) vẫn có nhánh Groq fallback cho đoạn tường thuật PDF — ngoài đường
  realtime, lỗi thì PDF bỏ trống narrative, không chặn ticket.
