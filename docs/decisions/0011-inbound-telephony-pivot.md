# 0011 Inbound Telephony — đảo chiều demo gọi thật (outbound → inbound)

Date: 2026-07-18

## Status

Accepted

## Context

Outbound qua Twilio **trial** bắt người nghe bấm một phím TRONG LÚC câu thông
báo trial đang phát thì mới chạy TwiML của mình. Thực chiến 18/07 tối: 4 cuộc
liên tiếp cùng chữ ký lỗi (status=completed, duration ~13–14s, 0 notification,
server không nhận request TwiML nào) kể cả khi "bấm mù" ngay lúc nhấc máy —
kết luận DTMF bị nhà mạng VN/VoLTE nuốt → **chiều gọi ra tắc hẳn** trên trial
với số đích của Long. Cuộc 17:55 thành công duy nhất đã chứng minh toàn chuỗi
media hoạt động (ghi âm 6.3s + VALSEA transcribe đúng) — điểm chết chỉ là cái
gate bấm phím, không phải pipeline.

## Decision

- Thêm route `GET/POST /telephony/inbound` (`app/telephony/routes.py`):
  khách **gọi vào** số Twilio +14787588373. Trial inbound chỉ phát câu thông
  báo rồi chạy TwiML luôn, **không cần keypress** → né hoàn toàn gate DTMF.
- Mỗi cuộc inbound dựng một `CallEngine` on-the-fly (pack mặc định
  `insurance_callcenter`, đổi qua `?pack=`), validate `X-Twilio-Signature`
  (403 nếu sai/thiếu), stream media 2 chiều y như outbound, prewarm TTS ngay
  khi nhận cuộc.
- VoiceUrl của số +14787588373 trỏ `{PUBLIC_BASE_URL}/telephony/inbound`.
  **Ràng buộc vận hành:** tunnel quick đổi URL thì phải cập nhật **cả**
  VoiceUrl trên Twilio (`POST IncomingPhoneNumbers/{PN}.json`), không chỉ
  `~/.notify.env`.
- **Outbound giữ nguyên code** — thành đường phụ; dùng lại được ngay khi nâng
  tài khoản trả phí (hết trial gate).
- Kèm gói tối ưu trễ turn cho cuộc gọi thật (đúc kết từ inbound chạy thật với
  Long 18/07 tối):
  - `ScriptedAgent.GRACE` 1.2s → **0.7s** (gom final sát nhau).
  - `engine.say(text, filler=…)`: phát **câu đệm đã cache** tức thì để che
    synth câu động 5–8s chạy nền song song (3 filler trong `tts.FILLERS`).
  - `scripts/warm_tts.py` chạy nền poll 60s: VALSEA TTS hồi là prewarm toàn bộ
    câu tĩnh 2 pack + filler + 6 câu động demo (kho local hữu hạn nên
    pre-synth được).
  - `tts.synth` trả thêm vendor + retry VALSEA ×2; cờ `TTS_PREFER=elevenlabs`
    trong `~/.notify.env` để đồng nhất giọng tức thì khi VALSEA TTS sập lâu.

## Alternatives Considered

1. Tiếp tục outbound với chiến thuật "bấm mù" — thất bại 4/4 cuộc, không kiểm
   soát được carrier nuốt DTMF.
2. Nâng Twilio trả phí (~$20, Long tự nạp) để bỏ trial gate — vẫn là đường
   thoát nếu cần outbound mượt cho demo chính thức; chưa làm.
3. Stringee số VN cho outbound trong nước — kiến trúc transport-agnostic cho
   phép thay chân telephony, để sau pilot (đã ghi ở 0009).

## Consequences

Positive:

- Demo gọi thật chạy ổn định: **inbound đã chạy thật với Long 18/07 tối**.
- Không còn phụ thuộc may rủi DTMF; khách chủ động gọi vào — giống tổng đài
  CSKH thật hơn cả kịch bản outbound.

Tradeoffs:

- Phụ thuộc VoiceUrl luôn trỏ đúng tunnel đang sống — quên cập nhật là cuộc
  gọi chết im lặng (khó chẩn đoán từ phía máy chủ vì không có request nào về).
- Mỗi lần demo phải: mở tunnel → cập nhật VoiceUrl → server chạy sẵn **trước**
  khi khách gọi (18/07 ~22:30 server + tunnel đã tắt sau phiên review — trước
  demo kế tiếp phải làm lại đủ 3 bước).

## Follow-Up

- Script tự động cập nhật VoiceUrl khi tunnel đổi URL (ứng viên backlog).
- Cân nhắc nâng tài khoản trả phí nếu demo chính thức cần chiều outbound.
