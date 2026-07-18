# Exec Plan — E8 Outbound Agent Call

## Goal

Trang demo `/call`: tổng đài viên AI **gọi ra** cho khách (Twilio), hỏi các
thông tin còn thiếu của hợp đồng bảo hiểm theo **kịch bản có sẵn**, nghe khách
trả lời (VALSEA RTT), điền dần vào form, đủ thì **gửi ticket** bổ sung hợp
đồng. Giọng nói tổng đài viên: ElevenLabs TTS.

## Scope

In scope:

- Pack mới `insurance_contract` (hợp đồng nền + field thiếu + kịch bản câu hỏi
  + action ticket).
- `app/telephony/`: bridge Twilio Media Streams ↔ VALSEA RTT ↔ ElevenLabs,
  agent state machine, 3 transport: `twilio` / `browser` (mic loopback) /
  `replay` (canned).
- Trang `/call` đơn giản: hợp đồng + field thiếu, transcript 2 chiều, trạng
  thái cuộc gọi, ticket kết quả.
- Config server-side cho Twilio creds + public URL (tunnel), probe OK/FAIL.

Out of scope:

- Inbound call, IVR, queue, nhiều cuộc gọi song song quy mô thật.
- Barge-in hoàn chỉnh (chỉ mức tối thiểu: clear playback khi khách nói).
- Ghi âm cuộc gọi Twilio về phân tích lại (để sau).

## Risk Classification

Risk flags: External systems (Twilio webhook + Media Streams, ElevenLabs),
Public contracts (endpoint webhook mới), Weak proof (vùng mới), Existing
behavior (tái dùng extraction/FormStore/actions).

Hard gates: External provider behavior → lane **high-risk** (intake #1).

## Work Phases

1. Story + decision 0009 (tài liệu này).
2. Pack + loader schema kịch bản.
3. Lõi telephony (codec, TTS, agent, engine, transports, twilio client).
4. Routes + trang demo.
5. Verification: unit script + chạy replay/browser mode end-to-end local.
6. Trace + runbook Twilio (creds/tunnel do Long cấp — chưa có thì mode
   twilio degrade sạch, page vẫn demo được).

## Stop Conditions

- Twilio creds/số from/tunnel là input của Long — KHÔNG tự tạo tài khoản.
- Không đọc/in/log `apikey.txt`; key mới cũng đi qua `app/config.py`.
- Nếu cần đổi kiến trúc relay VALSEA đã chốt (5.2 architecture.md) → dừng hỏi.
