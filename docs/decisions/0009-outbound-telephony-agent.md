# 0009 Outbound Telephony Agent — Twilio + VALSEA + ElevenLabs

Date: 2026-07-18

## Status

Accepted

## Context

Cần demo tổng đài viên AI **gọi ra** hỏi bổ sung thông tin hợp đồng bảo hiểm
theo kịch bản, tương tác realtime, rồi gửi ticket. VALSEA ASR là bắt buộc cho
speech-to-text; VALSEA không làm telephony; Twilio không có ASR tiếng Việt đạt
yêu cầu; cần giọng agent tự nhiên tiếng Việt.

## Decision

- **Twilio Media Streams (bidirectional `<Connect><Stream>`)** làm chân
  telephony: audio khách μ-law 8k → server; server bơm audio agent ngược lại.
  REST qua httpx, không thêm SDK.
- **VALSEA RTT giữ nguyên vai trò ASR** (kể cả trong cuộc gọi Twilio): μ-law
  8k → PCM16 16k → `wss /v1/realtime` với `hint_text` từ pack. Đúng ràng buộc
  "VALSEA bắt buộc cho pipeline chính".
- **Giọng tổng đài viên: VALSEA TTS ƯU TIÊN** (wav → transcode μ-law 8k nội
  bộ cho Twilio, wav thẳng cho browser), **ElevenLabs làm dự phòng**
  (`ulaw_8000`/mp3, flash v2.5). Câu kịch bản static được **pre-synthesize +
  cache**. *(Cập nhật 18/07 theo chỉ đạo của Long — bản đầu để ElevenLabs
  chính; đổi chiều để tối đa "Best Use of VALSEA API" và giảm phụ thuộc
  vendor ngoài.)*
- **KHÔNG LLM ngoài trong đường cuộc gọi** *(cập nhật 18/07, chỉ đạo của
  Long: bỏ Groq)*: hiểu câu trả lời bằng `app/telephony/parse_vi.py` — parser
  rule thuần field-aware (kịch bản có sẵn nên engine biết đang hỏi field nào):
  số đọc chữ → chữ số, ngày sinh, CCCD 12 số, biển số, địa chỉ; chạy trên
  text đã qua VALSEA `enable_correction` + ITN pack. 0ms, không rate-limit —
  nguyên nhân trực tiếp: Groq free tier trả 429 `retry-after` ~744s giữa cuộc
  gọi. Batch/Live (E4/E5) vẫn dùng Groq theo 0008 — chưa đổi.
- **Kịch bản nằm trong pack** (`call_script` của `insurance_contract`):
  greeting/closing/steps per-field — không hardcode trong engine.
- **Bậc thang degrade 3 mode**: `twilio` (cần creds + tunnel do Long cấp) →
  `browser` (mic/loa trình duyệt, không cần telephony) → `replay` (canned,
  không mạng). Demo không bao giờ chết — nhất quán quyết định 0008.
- Twilio creds + PUBLIC_BASE_URL đi qua `app/config.py` (env/apikey.txt),
  không bao giờ log; webhook validate `X-Twilio-Signature` khi có token.

## Alternatives Considered

1. TwiML `<Gather>`/`<Say>` IVR — mất VALSEA ASR + giọng máy kém.
2. ElevenLabs Conversational AI trọn gói — mất kiểm soát pipeline + không dùng
   VALSEA.
3. Stringee (đã có tài khoản) — giữ làm phương án telephony VN (số VN, gọi
   trong nước); E8 chọn Twilio vì Media Streams + tài liệu bidirectional tốt
   hơn cho hackathon; kiến trúc transport tách rời nên thay chân telephony
   sau được.

## Consequences

Positive:

- Có chiều outbound call hoàn chỉnh trên đúng stack pilot; engine
  transport-agnostic tái dùng cho Stringee/khác về sau.

Tradeoffs:

- Mode twilio phụ thuộc tunnel public (ngrok/cloudflared) + số from Twilio;
  trial Twilio chỉ gọi số đã verify, có câu thông báo trial đầu cuộc gọi.
- Thêm 1 đường resample 8k↔16k (suy hao nhẹ chất lượng ASR so với mic 16k).

## Follow-Up

- Long cấp: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`,
  `PUBLIC_BASE_URL` (tunnel) — xem runbook trong README.
- Cân nhắc kéo recording Twilio (dual-channel) về chạy lại batch pipeline làm
  bằng chứng sau cuộc gọi.
