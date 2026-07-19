# Validation Report — E10 Autobot tổng đài đa-workflow

Ngày: 2026-07-18 (ghi bù 22:40 cho chuỗi proof trong ngày) · Máy: local dev
(macOS, .venv Python 3.12)

## Unit (offline, không key) — PASS 49/49

`.venv/bin/python scripts/test_telephony.py`

- Kế thừa 38 test E8/E9 (codec, TwiML/signature, agent stub, parse_vi).
- Thêm 11 test E10: intent router 3 case; parse tên hoa/thường;
  CCCD đuôi chữ/số/thiếu; CRM lookup + verify identity đúng/sai.

## E2E replay (key thật) — PASS

- Lần 1 (48s): lookup khớp CCCD, intent đúng, ticket CAO, **2 mail Brevo gửi
  thật thành công** — lộ bug ho_ten bị extraction nền đè ("đầy đủ ạ").
- Fix + lần 2: **HOÀN TẤT 01:20, 7/7 field đúng** (Nguyễn Tiến Tuấn 85%,
  CCCD 001234 95%, vị trí tự bắt từ lời kể — bot bỏ qua câu hỏi thừa),
  ticket TCK + PDF + 2 mail đã gửi.
- Bug vá trong lượt: skip anchor cho field tên (khỏi bắt câu hỏi của bot);
  collect_free lọc kết quả confidence ≤ hiện có; icon field tự sang ✅.

## Gọi thật qua Twilio — INBOUND PASS, outbound tắc trial gate

- **Outbound 17:55** (cuộc thông duy nhất): toàn chuỗi media OK — ghi âm
  `out/recordings/7ac8a2e14d2a.wav` 6.3s, VALSEA transcribe đúng lời Long.
  Server 8322 sập giữa cuộc làm bot đứt lời → launch.json bỏ `--reload`.
- **Outbound ~19h–21h: TẮC** — 4 cuộc cùng chữ ký (completed ~13–14s,
  0 notification, không request TwiML về server) kể cả chiến thuật "bấm mù"
  → carrier VN/VoLTE nuốt DTMF, không vượt được trial press-key gate.
- **Pivot inbound (decision 0011): ĐÃ CHẠY THẬT VỚI LONG 18/07 tối** —
  Long gọi vào +14787588373, `/telephony/inbound` dựng CallEngine on-the-fly,
  bot chạy flow callcenter, không cần keypress.

## Tối ưu trễ turn (đo trên cuộc gọi thật)

Phân rã trễ/lượt: VAD 0.8s + VALSEA final ~0.3–0.8s + GRACE (1.2 → **0.7s**)
+ TTS synth câu động 5–8s (thủ phạm chính — che bằng filler cached phát ngay,
synth chạy nền song song; 3 filler + 6 câu động demo prewarm bằng
`scripts/warm_tts.py`).

## Sự cố tìm thấy & đã xử trong đêm

VALSEA TTS outage: `/v1/audio/speech` 500 "Text-to-speech failed" (fail 0.2s,
ASR/RTT vẫn sống) → câu động rơi fallback ElevenLabs → 2 giọng trộn trong 1
cuộc (Long phản ánh). Xử: `tts.synth` trả vendor + retry VALSEA ×2 + cảnh báo
"giọng dự phòng" lên panel; cờ `TTS_PREFER=elevenlabs` đồng nhất giọng khi
VALSEA sập lâu; `warm_tts.py` poll 60s tự prewarm khi VALSEA hồi.

## Trạng thái cuối ngày 18/07 (~22:30)

Server 8321 + cloudflared tunnel ĐÃ TẮT (Long yêu cầu khi review) →
VoiceUrl +14787588373 đang trỏ tunnel CHẾT. Checklist trước demo kế tiếp:
mở tunnel → cập nhật VoiceUrl (`POST IncomingPhoneNumbers/{PN}.json`) →
chạy server không `--reload` → prewarm TTS (`scripts/warm_tts.py`).
