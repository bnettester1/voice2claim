# Kịch bản demo & đặc tả UI

Mockup: `docs/product/mockup/demo-mockup.html` (mở trực tiếp bằng browser).
UI thật (Alpine.js) phải bám mockup đã được duyệt.

## 1. Bố cục màn hình

**Header (mọi màn):** logo pilot + **Domain Pack switcher** (🛡️ Bảo hiểm ⇄
🩺 Y tế) + chỉ báo chế độ (LIVE / BATCH / REPLAY) + trạng thái kết nối
(live · reconnecting · fallback · degraded) + stopwatch time-to-output.

**Màn 1 — Live Call (màn đinh):** 2 cột.
- Trái: thanh trạng thái cuộc gọi (mic level), transcript streaming (partial
  chữ mờ nghiêng → final chữ đậm, giữ nguyên thuật ngữ code-switch highlight),
  badge `arm_latency_ms` khi trigger bắn.
- Phải: **Action Form** render động từ pack schema — field điền dần, viền màu
  theo confidence (xanh ≥0.8 / vàng 0.5–0.8 / xám <0.5), tooltip evidence
  quote, click để sửa (user-lock 🔒). Dưới form: dãy **Action buttons** —
  mặc định mờ; khi armed thì sáng + pulse; fired thì ✅ + toast kết quả
  (PDF link, ticket id) + audio TTS đáp lại.

**Màn 2 — Batch:** khu upload/ghi âm (drag-drop + nút 🎙️) + sau xử lý hiện
transcript có semantic_tags + form kết quả (cùng component màn 1) + panel
**Hard-case Side-by-Side**: 2 cột transcript VALSEA vs ASR generic, diff
highlight đỏ các đoạn sai (biển số, EF/LDL-C, tên thuốc). Nút phụ **"Xuất
SRT"** (VALSEA formatting `subtitles`) — thêm một loại workflow-ready output.

**Màn 3 — Core System Console (mô phỏng hệ lõi doanh nghiệp):** bảng ticket
đến real-time (id, thời gian, action call, priority từ sentiment +
frustration_level, trạng thái), mỗi ticket mở rộng được khối **service_log**
do VALSEA formatting sinh (loại sự cố, nguyên nhân gốc, việc tiếp theo),
preview PDF sinh ra (bảng field + đoạn tường thuật), log webhook. Mục đích: chứng minh Workflow-Readiness —
output cắm thẳng hệ thống, không phải print text.

**Màn 4 — Duyệt & Chấm điểm (human-in-the-loop gate trước khi gửi):** 2 cột.
- Trái: **FormScorer** — vòng điểm tổng 0–100 + grade (SẴN SÀNG GỬI / CẦN ĐỌC
  KỸ / NÊN SỬA), breakdown 4 tiêu chí (độ phủ field bắt buộc · confidence
  trích xuất · đối chiếu NER local PyTorch · validator định dạng ITN/biển
  số), danh sách **"Cần chú ý"** (field vàng kèm evidence + nút ▶ nghe lại
  đúng đoạn audio + ✏️ sửa), dòng audit (người duyệt, thời gian đọc lại).
- Phải: bảng **đọc lại toàn bộ form** từng field (giá trị · confidence · nút
  sửa inline — sửa xong score tính lại live) + thanh quyết định:
  `✏️ Sửa lại form` · `▶ Nghe lại audio` · **`📤 GỬI FORM ĐI`**.
- Gate gửi: score ≥85 → gửi thẳng; 60–84 → gửi kèm checkbox "tôi đã đọc
  lại"; <60 → disable trừ khi override có lý do. **Chỉ khi bấm GỬI, Action
  Executor mới chạy** (PDF + ticket + webhook + audit trail điểm số).

## 2. Kịch bản sân khấu 4 màn (~6 phút)

| # | Màn | Diễn tiến | Điểm chấm nhắm tới |
| --- | --- | --- | --- |
| 1 | Batch (pack Bảo hiểm) | Bấm stopwatch → phát clip kịch bản B (có còi cứu thương + trẻ khóc) → form điền dần → nói "bấm nút Xác nhận có người bị thương" → nút sáng <500ms → **Màn 4: score 87, giám khảo thấy 1 field vàng → sửa 3s → GỬI** → PDF biên bản + ticket priority HIGH + TTS xác nhận → dừng đồng hồ ~50s (máy ~40s + người duyệt ~10s), so bảng "15 phút ghi tay" | Time-to-output, Workflow-Readiness, human-in-the-loop |
| 2 | Hard-case | Cùng clip B bản telephony: transcript VALSEA vs whisper generic side-by-side — generic sai biển số 51F-555.88 + rớt từ khi trẻ khóc | Outcome #2, Technical Execution |
| 3 | Pack switcher | Đổi 🛡️→🩺 ngay trên UI → phát clip kịch bản J (tim mạch, chỉnh liều Amlodipine) → cùng engine ra đơn thuốc + phiếu chỉ định Holter | AI-Native Architecture, Startup Potential |
| 4 | Live Call | Mic thật: giám định viên đọc kịch bản G (ngập nước) → transcript partial chạy chữ, form điền trước mắt giám khảo, "bấm nút gửi yêu cầu cứu hộ ô tô" → armed tức thì (badge ms hiển thị) → agent đáp giọng VALSEA TTS | Best Use of VALSEA API (RTT + hint_text + TTS) |

Dự phòng: mỗi màn có bản REPLAY (`?mode=replay`) đã thu sẵn — mất mạng/hết
credits vẫn chạy được liền mạch.

## 2b. Runbook sân khấu (đúc kết từ chạy thật)

1. **Warm-up bắt buộc** trước giờ demo: chạy 1 lượt `?demo=A` — VALSEA batch
   cold-start đo được 122s, warm ~10–14s; RTT luôn nhanh (ready 1.1–1.4s).
2. **Ưu tiên đường Live/RTT** trên sân khấu (có hint_text, partial <1s, arm
   <1ms); batch dùng cho màn stopwatch với clip demo có sẵn (chip A–F).
3. **Replay chips (▶ A, ▶ J)** = phao cứu sinh: phát lại bản ghi thật, 0 call
   API — dùng khi mạng hội trường sập hoặc hết credits. Ghi thêm bản replay
   mới bằng `scripts/test_live.py <ID> --record`.
4. Kịch bản kể chuyện khi ASR nghe sai biển số (đã gặp: "30G-555.2" thiếu 1
   số): validator regex bắn cảnh báo đỏ ở Màn 4 → người duyệt bấm ▶ nghe lại
   → sửa 3 giây → chính là human-in-the-loop có chủ đích, biến lỗi thành demo
   feature.
5. Giữ tab demo focus (background tab bị throttle timer → replay/stopwatch
   chậm); tắt notification máy; mic rời nếu hội trường ồn (VAD + noisy đã
   test SNR 12dB).
6. Eval scorecard chạy lại được 1 lệnh trước giờ chấm:
   `.venv/bin/python scripts/eval.py --audio --variants clean,noisy,telephony`.

## 3. Nguyên tắc UI

- Không mockup dữ liệu ở bản chạy thật — mọi giá trị đến từ pipeline.
- **Máy điền — người quyết**: không có gì rời hệ thống (PDF/ticket/webhook)
  mà chưa qua Màn 4; điểm số + audit trail là bằng chứng compliance
  (bảo hiểm/y tế đều cần người ký).
- Font hỗ trợ đầy đủ dấu tiếng Việt; thuật ngữ EN giữ nguyên, không phiên âm.
- Một trang một mục đích; giám khảo phải hiểu màn hình trong 5 giây.
- Số đo (latency, stopwatch, confidence) luôn nhìn thấy — biến demo thành
  bằng chứng.

## 4. Màn phụ: Outbound Agent Call (E8) — trang `/call`

AI tổng đài viên **gọi ra** bổ sung hợp đồng (pack `insurance_contract`):
hợp đồng nền bên trái (4 field thiếu đổi trạng thái ⚪→🔵→✅ theo cuộc gọi),
hội thoại 2 chiều bên phải, ticket + PDF hiện khi đủ thông tin.

Kịch bản demo 60–90s (mode Replay — đã verify end-to-end 66s):

1. Mở `/call`, chỉ vào 4 field thiếu — "hợp đồng này thẩm định chưa xong".
2. Bấm **Gọi cho khách** — giọng Mai (VALSEA TTS) chào + hỏi lần lượt; khách
   trả lời bằng số đọc chữ ("không bảy chín…", "năm mốt ca…") → form hiện
   `079083001234`, `51K-123.45` chuẩn hoá — luận điểm VALSEA correction + ITN
   pack + parser field-aware thuần rule (không LLM ngoài trong cuộc gọi).
3. Chỉ câu xác nhận đọc lại từng chữ số + khách "đúng rồi" — human-in-the-loop
   bằng giọng nói.
4. Kết màn: ticket TCK-xxxx + PDF phiếu bổ sung mở tức thì.

Mode 🎧 Browser để giám khảo tự đóng vai khách (mic thật, VALSEA RTT thật).
Mode ☎️ Twilio gọi số thật khi có creds + tunnel (runbook trong README).
