# Validation — E10 Autobot tổng đài

## Kết quả 18/07 tối

| Proof | Kết quả |
| --- | --- |
| Unit `scripts/test_telephony.py` | **49/49** (thêm 11: router 3 case, parse tên hoa/thường, CCCD đuôi chữ/số/thiếu, CRM lookup + verify đúng/sai) |
| Eval regression | 10/10 · 86/86 (extraction_local không vỡ sau guard mới) |
| E2E replay callcenter lần 1 | Chạy hết flow 48s: lookup khớp CCCD, intent đúng, ticket CAO, **2 mail Brevo gửi thành công thật** — lộ bug ho_ten bị extraction nền đè ("đầy đủ ạ") |
| Fix + E2E lần 2 | **HOÀN TẤT 01:20, 7/7 field đúng** (Nguyễn Tiến Tuấn 85%, CCCD 001234 95%, vị trí tự bắt từ lời kể — bot bỏ qua câu hỏi thừa), ticket TCK + PDF + 2 mail "đã gửi" |
| Twilio hạ tầng | account Trial active $15.5, from +14787588373 đã mua, tunnel 200 qua trycloudflare, `twilio_ready=True` |

Bug đã vá trong lượt: (1) anchor pass bắt cả câu HỎI của bot cho field ho_ten
→ skip anchor với field tên; (2) FormStore.merge cho phép giá trị conf thấp đè
giá trị tốt → collect_free lọc kết quả conf ≤ hiện có; (3) icon field tự sang
✅ khi có giá trị.

## ~~BLOCKED~~ ĐÃ THÔNG — gọi thật + record (cập nhật 18/07 tối)

Block cũ (`apikey.txt` bị xoá khi làm export public → mất key VALSEA/
ElevenLabs) đã gỡ: Long khôi phục key ~18h, TTS 200, RTT ok.

| Proof gọi thật | Kết quả |
| --- | --- |
| Outbound 17:55 (cuộc thông duy nhất) | Toàn chuỗi media OK: Long nhấc máy + bấm phím → media về tunnel → ghi âm `out/recordings/7ac8a2e14d2a.wav` 6.3s → VALSEA transcribe đúng lời |
| Outbound các cuộc sau (~19h–21h) | **TẮC trial gate**: 4 cuộc cùng chữ ký (completed ~13–14s, 0 notification, không request TwiML) kể cả "bấm mù" — carrier VN nuốt DTMF |
| **INBOUND (decision 0011)** | **ĐÃ CHẠY THẬT VỚI LONG 18/07 tối** — Long gọi vào +14787588373, bot chạy flow callcenter qua `/telephony/inbound` |
| Unit sau các fix inbound + trễ | **49/49** (`scripts/test_telephony.py`) |
| Trễ turn | GRACE 1.2→0.7s + filler cached che synth câu động 5–8s; phân rã còn lại: VAD 0.8 + VALSEA final ~0.3–0.8 + GRACE 0.7 |

Sự cố trong đêm: VALSEA TTS outage (500 "Text-to-speech failed", fail 0.2s;
ASR/RTT vẫn sống) → câu động rơi fallback ElevenLabs → 2 giọng trộn 1 cuộc.
Đã xử: retry ×2 + vendor tracking + cờ `TTS_PREFER` + `scripts/warm_tts.py`
prewarm khi VALSEA hồi (chi tiết ở design.md).

Trạng thái 18/07 ~22:30: server 8321 + tunnel ĐÃ TẮT (Long yêu cầu) →
**VoiceUrl đang trỏ tunnel chết**. Trước demo kế tiếp: mở tunnel → cập nhật
VoiceUrl → chạy server (không `--reload`) → prewarm TTS.
