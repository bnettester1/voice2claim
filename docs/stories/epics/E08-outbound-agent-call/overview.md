# Overview — E8 Outbound Agent Call

## Current Behavior

Pilot đã có: batch (upload → form → ticket) và live mic browser → VALSEA RTT →
form + trigger. Chưa có chiều **máy chủ động gọi khách** và chưa có giọng nói
agent hội thoại.

## Target Behavior

Từ trang `/call`: chọn khách demo (hợp đồng thiếu thông tin) → bấm **Gọi**.

- Mode `twilio`: Twilio gọi số thật; khách nghe tổng đài viên AI (ElevenLabs)
  chào + hỏi lần lượt từng field thiếu theo kịch bản; khách trả lời — VALSEA
  RTT nhận dạng; engine extract điền form; xác nhận lại giá trị; đủ field →
  đọc lời chào kết thúc, gửi ticket, cúp máy.
- Mode `browser`: y hệt nhưng "cuộc gọi" chạy ngay trên mic/loa trình duyệt
  (không cần Twilio/tunnel) — dùng để tập dượt và demo interactive.
- Mode `replay`: khách ảo trả lời theo kịch bản canned — không mạng vẫn demo.

Trang hiển thị đơn giản: thẻ hợp đồng (field có sẵn + field thiếu đổi màu khi
điền được), transcript 2 chiều (agent nói / khách nói), trạng thái cuộc gọi,
panel ticket sau khi gửi.

## Affected Users

- Long (demo hackathon), giám khảo xem demo, khách demo nghe máy.

## Affected Product Docs

- `docs/product/architecture.md` (thêm nhánh outbound call — bổ sung sau khi
  chạy được), `docs/product/demo.md` (kịch bản demo mới).

## Non-Goals

- Không thay pipeline batch/live hiện có; không đổi contract WS `/ws/live`.
- Không cam kết chất lượng thoại production (echo/jitter tuning).
