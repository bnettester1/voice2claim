# Pilot & Deployment Roadmap — Speech-to-Meaning

*Deliverable theo Problem Brief VALSEA (1–2 trang). Trạng thái hiện tại: prototype
chạy thật đủ 2 vertical, eval 10 kịch bản × 3 biến thể audio, live call RTT.*

## Giai đoạn 0 — Hackathon (đã xong trong 48h)

| Hạng mục | Trạng thái |
| --- | --- |
| Engine domain-agnostic + 2 Domain Pack (bảo hiểm xe, y tế ngoại trú + 3 chuyên khoa) | ✅ |
| VALSEA transcribe + RTT (hint_text từ từ điển) + TTS + formatting | ✅ |
| Live call: form điền real-time, trigger arm <1ms (đích 500ms), VAD PyTorch | ✅ |
| FormScorer + màn Duyệt (human-in-the-loop gate) + PDF/ticket/webhook | ✅ |
| Bộ test 10 kịch bản (6 KB + 4 mở rộng) × clean/noisy/telephony + scorecard tự động | ✅ |
| NER local PyTorch đối chiếu (agreement) + itn_rules từ điển sửa ASR | ✅ |
| Replay mode (demo không cần mạng/credits) | ✅ |

## Giai đoạn 1 — Pilot doanh nghiệp đầu tiên (tuần 1–4)

**Mục tiêu:** 1 công ty bảo hiểm phi nhân thọ, đội giám định 10–20 người, xử lý
hồ sơ cứu hộ/tổn thất qua voice-to-form thay ghi tay.

- Tuần 1–2: Workshop từ điển nghiệp vụ với phòng bồi thường → mở rộng
  `insurance_motor` pack (mẫu biên bản chuẩn công ty, action call nối core
  claims qua webhook thật thay console mô phỏng; SSO nội bộ).
- Tuần 3–4: chạy song song (shadow mode) với quy trình giấy; đo KPI:
  - **time-to-output**: mục tiêu < 2 phút/hồ sơ (baseline 15 phút ghi tay)
  - **field accuracy sau duyệt**: ≥ 98% (máy điền + người sửa)
  - **tỉ lệ field máy điền đúng không cần sửa**: ≥ 85% (scorecard hiện tại ~90%
    trên audio clean, ~80% trên noisy)
  - **adoption**: ≥ 70% giám định viên dùng hằng ngày sau tuần 4
- Hạ tầng: Docker + 1 VM (2 vCPU đủ — ML layer CPU-only), secrets vault,
  VALSEA quota theo hợp đồng pilot, log/audit trail lưu 90 ngày.

## Giai đoạn 2 — Y tế + nâng chất lượng (tháng 2–3)

- Pilot phòng khám đa khoa: pack `healthcare_exam` nối HIS qua HL7/FHIR
  adapter (đơn thuốc điện tử, phiếu chỉ định CLS).
- Mở rộng chuyên khoa theo dữ liệu thật (thêm module specialties mới =
  thêm mục từ điển, không sửa engine).
- **Lexicon NER nâng cao**: nâng từ điển pack lên mô hình sense-entry
  (concept–sense–surface, cổng ngữ cảnh, trie leftmost-longest) và
  lexicon-enhanced NER (SoftLexicon/PhoBERT) khi tầng rule bão hòa.
- Số dài (biển số, mã hợp đồng): double-confirm bằng giọng ("đọc lại từng
  số") + validator regex — hiện validator đã bắt sai định dạng, thêm luồng
  hỏi lại tự động qua TTS.

## Giai đoạn 3 — Nền tảng hóa (tháng 4–6)

- **Pack Studio**: công cụ self-serve cho doanh nghiệp tự soạn từ điển
  nghiệp vụ (schema + action + trigger + lexicon), kèm bộ eval tự sinh
  audio test bằng TTS như pipeline hiện tại.
- Marketplace pack theo ngành (logistics, ngân hàng, CSKH…), mô hình
  dictionary-as-integration.
- On-prem option cho ngành nhạy cảm PII (y tế/ngân hàng): VALSEA private
  endpoint + ML local đã sẵn CPU-only.
- Đa kênh: tổng đài (SIP trunk → RTT relay đã có sẵn kiến trúc),
  mobile SDK ghi âm hiện trường.

## Rủi ro chính & giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| ASR nghe sai số dài (biển số, liều) | validator + attention (đã có) → double-confirm giọng nói (GĐ2); itn_rules từ điển |
| Batch API latency dao động (10s–120s ghi nhận) | luồng chính dùng RTT streaming; batch chỉ cho hồ sơ offline; warm-up + retry |
| Quota/credits API | cache TTS, replay mode cho training; hợp đồng quota pilot |
| PII / tuân thủ ngành | audit trail đầy đủ (điểm, người duyệt, evidence); on-prem GĐ3; không lưu audio mặc định |
| Người dùng không tin AI | Màn Duyệt & chấm điểm bắt buộc — "máy điền, người quyết"; evidence quote từng field |
