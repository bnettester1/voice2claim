# Overview — E10 Autobot tổng đài

## Current Behavior (E8)

Bot gọi ra theo kịch bản TĨNH: hỏi lần lượt field cố định của 1 form, không
xác thực, không tra cứu hồ sơ, không phân loại yêu cầu, không email.

## Target Behavior

Bot tổng đài CSKH: xác thực (tên + đuôi CCCD) → tra cứu hồ sơ khách qua notify
server (fallback kho local) → đọc tổng quan → nghe yêu cầu TỰ DO → bộ lọc
intent chọn workflow (tra cứu tiến độ / claim mới) → hỏi đúng phần còn thiếu →
xác nhận → ticket + PDF + email nhân sự & khách + ghi âm nghe lại được.
Chạy 3 mode: replay (đã verify) / browser / twilio.

**Cập nhật 18/07 tối (decision 0011):** đường gọi thật chuyển sang **INBOUND**
— khách gọi vào số +14787588373, route `/telephony/inbound` dựng CallEngine
on-the-fly. Đã chạy thật với Long. Outbound giữ nguyên code làm đường phụ
(tắc trial gate DTMF với nhà mạng VN — chi tiết trong 0011).

## Affected Users

Long (demo), giám khảo, "khách" demo nghe máy (+84911961540).

## Affected Product Docs

README (mục Agent Call), demo.md màn phụ, decisions 0009/0010 (không
đổi — E10 tuân thủ), **decision 0011 (pivot inbound)**, story này.

## Non-Goals

Không thay E8 (2 kịch bản song song trên /call); không LLM trong router
(chờ Long chốt riêng vụ LLM judge). ~~Không inbound số thật~~ — **đã bỏ
non-goal này 18/07 tối**: outbound trial tắc DTMF nên inbound thành đường
gọi thật CHÍNH (decision 0011). Non-goal còn lại: không outbound trả phí,
không tự động cập nhật VoiceUrl khi tunnel đổi (backlog).
