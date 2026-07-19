# Kịch bản video demo Voice2Claim (2 đoạn)

Video: `out/demo/voice2claim_demo.mp4` — dựng bằng `scripts/make_demo_video.py`
(cảnh chụp app thật + caption + thuyết minh giọng **VALSEA TTS**).


---

## 🎬 VOICE2CLAIM

*Hệ thống giám định thông minh bằng giọng nói · VALSEA Hackathon 2026*

- **Thuyết minh (VALSEA):** “Xin chào ban giám khảo. Đây là Voice2Claim — nền tảng vận hành bảo hiểm điều khiển bằng giọng nói, xây trên VALSEA Speech API. Video gồm hai đoạn demo: một, tổng đài AI xử lý cuộc gọi của khách; hai, nền tảng tự động vận hành hồ sơ sau cuộc gọi.”

### Cảnh 01 — Tổng quan — trung tâm điều hành

- **Màn hình:** `out/demo/shots/test_dash.png`
- **Caption:** KPI vận hành thời gian thực · AI Decision Feed: mọi quyết định của AI đều được ghi lại, giải thích được
- **Thuyết minh (VALSEA):** “Đây là màn hình Tổng quan. Bên trái là số liệu vận hành thời gian thực. Ở giữa là Decision Feed — nơi AI Điều hành ghi lại từng quyết định: định tuyến cuộc gọi, chấm điểm rủi ro, giao việc cho nhân sự. Ban giám khảo có thể kiểm chứng mọi bước tại đây.”

---

## 🎬 DEMO 1 — TỔNG ĐÀI AI

*Outbound Agent Call · Tổng đài workflow · chế độ Replay (bản ghi thật)*

- **Thuyết minh (VALSEA):** “Đoạn demo thứ nhất: tổng đài AI. Chúng tôi dùng pack Tổng đài workflow với chế độ Replay — phát lại bản ghi khách thật — để ban giám khảo xem trọn chuỗi xử lý mà không phụ thuộc sóng điện thoại. Toàn bộ giọng nói dùng VALSEA: nghe, hiểu, và đáp lời.”

### Cảnh 03 — Trang Demo Cuộc gọi — chọn Tổng đài workflow + Replay

- **Màn hình:** `out/demo/shots/d1_00_idle.png`
- **Caption:** Phiếu tiếp nhận 7 trường bên trái sẽ được AI tự điền trong lúc trò chuyện
- **Thuyết minh (VALSEA):** “Đây là trang cuộc gọi. Chúng tôi chọn Tổng đài workflow, chế độ Replay, rồi bấm Gọi cho khách. Phiếu tiếp nhận bên trái đang trống — AI sẽ tự điền trong lúc nói chuyện với khách.”

### Cảnh 04 — AI xác thực khách và tra hồ sơ CRM

- **Màn hình:** `out/demo/shots/d1_02.png`
- **Caption:** Hỏi tên + số cuối CCCD → đối chiếu database → đọc tổng quan hợp đồng, hồ sơ đang có
- **Thuyết minh (VALSEA):** “Mở đầu, tổng đài viên AI tên Mai hỏi họ tên và sáu số cuối căn cước để xác thực. Hệ thống tra hồ sơ trong CRM, xác nhận khớp giấy tờ, rồi đọc lại cho khách tổng quan hợp đồng và hồ sơ bồi thường đang có.”

### Cảnh 05 — Khách kể tự do — AI hiểu ý định, tự điền form

- **Màn hình:** `out/demo/shots/d1_04.png`
- **Caption:** Intent router <1ms chọn workflow 'Tiếp nhận sự cố mới' · extraction local điền từng trường kèm độ tin cậy
- **Thuyết minh (VALSEA):** “Khách kể bị đâm xe ở đường Cộng Hòa. Bộ định tuyến ý định chọn đúng quy trình tiếp nhận sự cố mới, và lời kể được bóc thành từng trường dữ liệu — vị trí, thời điểm, mô tả thiệt hại, thương tích — kèm phần trăm độ tin cậy.”

### Cảnh 06 — AI chỉ hỏi phần còn thiếu, đọc xác nhận lại

- **Màn hình:** `out/demo/shots/d1_06.png`
- **Caption:** 'AI tự quyết câu hỏi' — trường nào đã bắt được từ lời kể thì bỏ qua, rút ngắn cuộc gọi
- **Thuyết minh (VALSEA):** “AI chỉ hỏi những trường còn trống, sau đó đọc lại toàn bộ thông tin để khách xác nhận lần cuối. Cách này rút ngắn cuộc gọi đáng kể mà hồ sơ vẫn chính xác.”

### Cảnh 07 — Kết thúc cuộc gọi: Ticket + PDF + Email + Ghi âm — tự động toàn bộ

- **Màn hình:** `out/demo/shots/d1_15_final.png`
- **Caption:** Ticket TCK-0015 ưu tiên CAO · PDF chuẩn ngành · mail khách & nhân sự · băng ghi âm lưu hồ sơ
- **Thuyết minh (VALSEA):** “Cuộc gọi kết thúc: hệ thống tự tạo ticket ưu tiên cao, sinh PDF phiếu tiếp nhận, gửi email cho khách và nhân sự, lưu băng ghi âm. Và quan trọng nhất — một workflow xử lý claim vừa được AI khởi động chạy phía sau.”

---

## 🎬 DEMO 2 — NỀN TẢNG VẬN HÀNH

*CRM 360 · Hộp công việc theo vai · Workflow trực quan · Flywheel tự cải tiến*

- **Thuyết minh (VALSEA):** “Đoạn demo thứ hai: nền tảng vận hành. Cuộc gọi vừa rồi đã tạo hồ sơ claim trong CRM và kích hoạt workflow. Chúng ta theo chân hồ sơ này qua từng vai: thẩm định viên, giám đốc, và vòng lặp tự cải tiến của hệ thống.”

### Cảnh 09 — AI Decision Feed — chuỗi quyết định của cuộc gọi vừa rồi

- **Màn hình:** `out/demo/shots/d2_01_dash.png`
- **Caption:** Định tuyến intent → mở claim → chấm rủi ro kèm lý do → giao việc thẩm định — tất cả có dấu vết
- **Thuyết minh (VALSEA):** “Quay lại Tổng quan: Decision Feed hiện chuỗi quyết định AI vừa thực hiện — định tuyến cuộc gọi, mở hồ sơ claim, chấm điểm rủi ro kèm lý do từng điểm cộng trừ, và giao việc cho thẩm định viên.”

### Cảnh 10 — CRM — Khách hàng 360

- **Màn hình:** `out/demo/shots/d2_02_crm.png`
- **Caption:** Hợp đồng · Claims · Tương tác kèm băng ghi âm · Dòng thời gian — một nguồn dữ liệu SQLite
- **Thuyết minh (VALSEA):** “Trong CRM, hồ sơ khách hàng ba trăm sáu mươi độ: hợp đồng, các claim, lịch sử tương tác kèm băng ghi âm từng cuộc gọi, và dòng thời gian mọi biến động. Claim mới từ cuộc gọi đã nằm ở trạng thái tiếp nhận.”

### Cảnh 11 — Workflow run — sơ đồ tiến trình thời gian thực

- **Màn hình:** `out/demo/shots/d2_03_run_wait.png`
- **Caption:** Node xanh: đã xong · node vàng: đang chờ thẩm định viên đi hiện trường
- **Thuyết minh (VALSEA):** “Đây là run của workflow xử lý claim, nhìn thẳng trên sơ đồ: các bước đã hoàn thành màu xanh, bước đang chờ màu vàng — thẩm định viên phải ra hiện trường, chụp ảnh và ghi âm lời khai.”

### Cảnh 12 — Hộp công việc — vai Thẩm định viên

- **Màn hình:** `out/demo/shots/d2_04_task_assessor.png`
- **Caption:** Hồ sơ AI thu thập sẵn · nhập thiệt hại ước tính · đính băng ghi âm hiện trường · chấm ★ flywheel
- **Thuyết minh (VALSEA):** “Trong hộp công việc của thẩm định viên, mọi thông tin AI thu thập đã sẵn. Thẩm định viên nhập thiệt hại ước tính, đính kèm băng ghi âm hiện trường, chấm sao chất lượng quy trình, và bấm hoàn tất — workflow lập tức chạy tiếp.”

### Cảnh 13 — VALSEA bóc băng ghi âm → Biên bản giám định PDF

- **Màn hình:** `out/demo/shots/d2_05_run_transcribed.png`
- **Caption:** transcribe_media dưới 5 giây · dựng biên bản tự động · email cập nhật cho khách
- **Thuyết minh (VALSEA):** “VALSEA bóc băng ghi âm hiện trường chỉ trong vài giây. Hệ thống dựng biên bản giám định PDF kèm nguyên văn lời khai, gửi email cập nhật cho khách, rồi chuyển hồ sơ lên bàn giám đốc.”

### Cảnh 14 — Giám đốc phê duyệt — một cú click

- **Màn hình:** `out/demo/shots/d2_06_task_director.png`
- **Caption:** Duyệt / Từ chối + số tiền + lý do · mọi ngã rẽ đều nằm sẵn trong sơ đồ workflow
- **Thuyết minh (VALSEA):** “Giám đốc xem toàn bộ hồ sơ và biên bản, nhập số tiền chi trả và bấm duyệt. Nếu từ chối, workflow tự rẽ nhánh gửi thư giải thích — mọi ngã rẽ đều được vẽ sẵn trong sơ đồ.”

### Cảnh 15 — Chi trả + AI tự động GỌI ĐIỆN báo kết quả

- **Màn hình:** `out/demo/shots/d2_07_run_done.png`
- **Caption:** auto_call node — giọng VALSEA đọc đúng tên khách, mã hồ sơ, số tiền · claim → ĐÃ CHI TRẢ
- **Thuyết minh (VALSEA):** “Sau khi duyệt, claim chuyển sang đã chi trả, email kết quả được gửi, và AI tự động gọi điện thông báo cho khách — đọc đúng tên, mã hồ sơ và số tiền tám triệu rưỡi bằng giọng VALSEA.”

### Cảnh 16 — Workflow là cấu hình trong DB + Flywheel chất lượng theo version

- **Màn hình:** `out/demo/shots/d2_08_wf.png`
- **Caption:** Sơ đồ node-edge · bảng so sánh v1 vs v2 · ★ khách · ★ nhân sự · Qwen judge · editor JSON
- **Thuyết minh (VALSEA):** “Toàn bộ quy trình là cấu hình trong database — nhìn thấy được, sửa được. Bảng flywheel so sánh chất lượng từng phiên bản: thời gian xử lý, điểm khách và nhân sự chấm, cùng ý kiến thứ hai của mô hình Qwen. Sửa cấu hình là ra phiên bản mới, phiên bản cũ bất biến.”

### Cảnh 17 — Bên dưới: engine Speech-to-Meaning (pilot gốc)

- **Màn hình:** `out/demo/shots/d2_09_pilot.png`
- **Caption:** Batch · Live mic · Chấm điểm hồ sơ — 10/10 kịch bản gold, 86/86 trường, trigger <500ms
- **Thuyết minh (VALSEA):** “Bên dưới nền tảng là engine Speech-to-Meaning: xử lý file ghi âm, mic trực tiếp, chấm điểm hồ sơ trước khi gửi — đạt mười trên mười kịch bản chuẩn với tám mươi sáu trên tám mươi sáu trường dữ liệu, thời gian kích hoạt lệnh nói dưới nửa giây.”

### Cảnh 18 — Flow thứ hai: Mở hợp đồng — voice prefill + ký điện tử

- **Màn hình:** `out/demo/shots/d2_10_contract.png`
- **Caption:** Kể bằng giọng nói → AI điền form → thẩm định rủi ro → hợp đồng PDF → ký qua email → autocall
- **Thuyết minh (VALSEA):** “Nền tảng còn flow mở hợp đồng: khách kể nhu cầu bằng giọng nói, AI điền form và chấm rủi ro — hồ sơ rủi ro cao tự rẽ sang thẩm định thủ công. Hợp đồng PDF được gửi email để khách ký điện tử.”

### Cảnh 19 — Ký điện tử — link một lần qua email

- **Màn hình:** `out/demo/shots/d2_11_sign.png`
- **Caption:** Token single-use · double-click an toàn · ký xong hợp đồng ACTIVE ngay trong CRM + autocall chúc mừng
- **Thuyết minh (VALSEA):** “Đây là trang ký khách nhận qua email — link dùng một lần, bấm hai lần không tạo bản ghi kép. Ký xong, hợp đồng có hiệu lực ngay trong CRM và AI gọi điện chúc mừng khách.”

### Cảnh 20 — Kho tri thức — tài liệu nghiệp vụ thành workflow

- **Màn hình:** `out/demo/shots/d2_12_kb.png`
- **Caption:** Upload tài liệu → Qwen bóc tách quy trình (offline, 17 giây) → promote thành workflow nháp 12 node
- **Thuyết minh (VALSEA):** “Cuối cùng, kho tri thức: doanh nghiệp upload tài liệu nghiệp vụ, AI bóc tách thành workflow nháp — như quy trình giám định mười hai bước này — rồi admin duyệt đưa vào vận hành. Đó là cách nền tảng nhân rộng sang mọi nghiệp vụ của doanh nghiệp.”

---

## 🎬 VOICE2CLAIM — Từ giọng nói đến hành động

*VALSEA ASR · Realtime · TTS + Workflow engine + AI Điều hành + Flywheel · Cảm ơn ban giám khảo!*

- **Thuyết minh (VALSEA):** “Voice2Claim: từ giọng nói đến hành động — tổng đài AI, CRM, workflow trực quan và vòng lặp tự cải tiến, tất cả chạy thật trên VALSEA Speech API. Cảm ơn ban giám khảo đã theo dõi.”