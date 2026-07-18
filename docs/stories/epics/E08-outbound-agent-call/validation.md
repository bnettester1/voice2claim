# Validation — E8 Outbound Agent Call

## Proof Strategy

Chứng minh 3 tầng, tầng nào không cần credential thì phải pass trong repo:

1. Unit (offline, không key): codec μ-law/resample roundtrip; agent state
   machine chạy hết kịch bản với extraction stub; TwiML + signature.
2. E2E local (key VALSEA/Groq/ElevenLabs qua probe OK/FAIL): mode `replay`
   chạy từ trang `/call` → form điền đủ → ticket xuất hiện; mode `browser`
   smoke bằng preview.
3. E2E telephony (cần Twilio creds + tunnel của Long): runbook từng bước;
   không tự động hoá trong CI.

## Test Plan

| Layer | Cases |
| --- | --- |
| Unit | mulaw enc→dec sai số ≤ tolerance; resample 8k↔16k độ dài đúng; agent hỏi đúng thứ tự field thiếu, re-ask khi im lặng, confirm rồi mới sang field kế; ticket chỉ fire khi đủ required |
| Integration | /call/start thiếu Twilio creds → 400 kèm hint mode khác; twiml endpoint trả XML đúng wss URL; signature sai → 403 |
| E2E | replay mode: transcript canned → form đủ → ticket TCK-xxxx trên UI |
| Logs/Audit | log call sid/mode/duration; số điện thoại mask; không key nào bị in |

## Fixtures

- Khách demo cố định trong pack: hợp đồng `GCN-2025-104729`, khách "Trần Văn
  Hùng", xe "Toyota Vios 2023" — thiếu: ngày sinh, số CCCD, biển số xe, địa
  chỉ liên hệ.
- Câu trả lời canned cho replay (kèm 1 câu trả lời nhiễu để test re-ask).

## Commands

- `python3 scripts/test_telephony.py` (unit, offline — verify command của E8).
- Chạy app + mở `/call?mode=replay` (E2E local).
