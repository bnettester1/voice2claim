# Domain Pack — Kho từ điển nghiệp vụ

Domain Pack là **sản phẩm dữ liệu** của pilot: một file JSON mô tả trọn nghiệp
vụ để engine (100% domain-agnostic) tự thích nghi. Doanh nghiệp tích hợp =
soạn pack, không sửa code.

## 1. Schema pack

```jsonc
{
  "id": "insurance_motor",
  "name": "Bảo hiểm — Giám định tai nạn xe",
  "icon": "🛡️",
  "form": {
    "title": "Phiếu ghi nhận tổn thất hiện trường",
    "sections": [
      { "title": "Thông tin khai báo", "fields": [
        { "name": "ten_khach_hang", "label": "Tên khách hàng", "type": "text",
          "required": true, "synonyms": ["người khai", "chủ xe"] },
        { "name": "bien_so_xe", "label": "Biển số xe", "type": "text",
          "pattern": "biển số VN", "itn": true }
        // ... type: text | number | date | enum | list | textarea
      ]}
    ]
  },
  "actions": [
    { "id": "REQUEST_MOTORBIKE_TOWING",
      "label": "Gửi yêu cầu cứu hộ xe máy",
      "triggers": ["bấm nút gửi yêu cầu cứu hộ xe máy",
                    "gửi yêu cầu cứu hộ xe máy",
                    "yêu cầu cứu hộ xe máy"],
      "confirm": "auto",            // auto = fire khi khớp final; click = chờ user
      "required_fields": ["vi_tri", "phuong_tien"],
      "tts_confirm": "Đã ghi nhận. Yêu cầu cứu hộ xe máy đang được gửi đi.",
      "template": "towing_request"  // template PDF/ticket
    }
  ],
  "specialties": {                   // module con — chỉ y tế dùng
    "tieu_hoa": { "hint_terms": [...], "fields_extra": [...] }
  },
  "hint_terms": ["Wave Alpha", "Toyota Vios", "59A-987.65", "yếm xe", ...],
  "itn_rules": [
    { "pattern": "năm chín a", "replace": "59A" }   // ví dụ — bổ sung khi eval lộ lỗi
  ],
  "few_shots": [ { "transcript": "...", "expected": { ... } } ],  // từ KB
  "extraction_instructions": "Giữ nguyên thuật ngữ tiếng Anh (EF, HP, LDL-C...)...",
  "scoring": {                       // FormScorer — xem architecture.md §5.6
    "submit_threshold": 85,          // ≥85 gửi thẳng; 60-84 gửi kèm xác nhận; <60 chặn
    "validators": [
      { "field": "bien_so_xe", "rule": "regex", "value": "^\\d{2}[A-Z]{1,2}-?\\d{3}\\.?\\d{2}$" },
      { "field": "lieu_thuoc", "rule": "unit",  "value": ["mg","g","ml","mmol/L","%"] }
    ]
  }
}
```

`packs/loader.py` build **`hint_text`** cho VALSEA RTT từ: field labels +
synonyms + enum values + toàn bộ trigger phrases + hint_terms (cap ~1000 ký tự).

## 2. Pack 1 — `insurance_motor` (Bảo hiểm tai nạn xe)

**Phạm vi v1 (từ KB A/B/C):** form hiện trường (tên, vị trí, phương tiện —
nhiều xe, biển số ITN, mô tả hư hỏng, thương tích/tình trạng người), actions
`REQUEST_MOTORBIKE_TOWING` · `CONFIRM_PERSONAL_INJURY` ·
`SUBMIT_MULTI_VEHICLE_COLLISION_REPORT`.

**Mở rộng (nghiệp vụ claims ops chung — phục vụ test case mới):**
- Trường bổ sung: `so_hop_dong/GCN bảo hiểm`, `thoi_diem_su_kien`,
  `nguyen_nhan` (enum: va chạm / ngập nước / trộm cắp bộ phận / cháy nổ /
  khác), `muc_do_uu_tien` (map từ sentiment/thương tích).
- Action bổ sung: `REQUEST_CAR_TOWING` (cứu hộ ô tô — "bấm nút gửi yêu cầu cứu
  hộ ô tô"), `SUBMIT_THEFT_PARTS_REPORT` (trộm gương/phụ tùng),
  `SCHEDULE_SURVEYOR_VISIT` (hẹn giám định viên tới hiện trường).
- hint_terms bổ sung: "thủy kích", "ngập nước", "chết máy", "kính chắn gió",
  "gương chiếu hậu", "camera hành trình", "bãi giữ xe", các hãng/mẫu xe phổ
  biến VN, format biển số 5 số mới.

## 3. Pack 2 — `healthcare_exam` (Y tế — khám ngoại trú)

Theo phạm vi đã chốt: **chỉ nghiệp vụ khám chung + 3 chuyên khoa xuất hiện
trong bộ test**, không ôm cả ngành y.

**Nghiệp vụ chung (core fields mọi ca khám):** tên BN, tuổi/năm sinh, lý do
khám, triệu chứng, sinh hiệu (nếu đọc), chẩn đoán, kết quả CLS, thuốc
(tên/hàm lượng/liều/liệu trình — phân biệt **thuốc mới vs thuốc duy trì**),
chỉ định CLS tiếp theo, lịch tái khám, dặn dò. Actions chung:
`ISSUE_ELECTRONIC_PRESCRIPTION` · `ISSUE_OUTPATIENT_TREATMENT_ORDER` ·
`PRINT_EXAMINATION_SLIP_AND_PRESCRIPTION` · `ORDER_LAB_TESTS` ·
`SCHEDULE_FOLLOW_UP`.

**Chuyên khoa (module `specialties`, chỉ 3):**

| Chuyên khoa | hint_terms lõi (giữ verbatim, không Việt hóa) | Nguồn |
| --- | --- | --- |
| `tieu_hoa` (Tiêu hóa) | HP, test hơi thở, nội soi dạ dày–tá tràng, ổ loét, viêm loét tá tràng, Esomeprazole, Clarithromycin, Amoxicillin, triple therapy, PPI | Kịch bản D |
| `chan_thuong_chinh_hinh` (Chấn thương chỉnh hình) | gãy kín, 1/3 giữa xương cẳng chân, dây chằng chéo trước, độ 2, bó bột đùi bàn chân, X-quang, MRI, Celecoxib, Alpha Choay | Kịch bản E |
| `tim_mach` (Tim mạch) | EF, siêu âm tim, LDL-C, mmol/L, lipid profile, men gan AST/ALT, Rosuvastatin, Aspirin, Amlodipine, tăng huyết áp, Holter | Kịch bản F |

Extraction instructions y tế: đơn vị liều giữ ITN (40mg, 1g, 3.8 mmol/L,
60%), phân biệt thuốc mới/cũ, không suy diễn chẩn đoán ngoài lời thoại.

## 4. Bộ test case mở rộng G–J (sinh audio bằng ElevenLabs)

Bổ sung 4 kịch bản mới ngoài 6 kịch bản KB — kiểm tra khả năng tổng quát hóa
của engine trên mục từ điển mở rộng (§2, §3). Mỗi test case gồm: script hội
thoại (giọng đọc ElevenLabs, ≥2 voice) + gold labels JSON + biến thể nhiễu.

| ID | Pack | Kịch bản | Gold NER chính | Action Call kỳ vọng | Hard-case yếu tố |
| --- | --- | --- | --- | --- | --- |
| G | insurance | Ô tô **ngập nước chết máy** hầm chung cư Q7, khách tên Hằng, Mazda CX-5 51H-368.24, nước tới nửa bánh, không nổ máy lại | tên, vị trí, xe+biển số, nguyên nhân=ngập nước, tình trạng "không khởi động được" | `REQUEST_CAR_TOWING` ("bấm nút gửi yêu cầu cứu hộ ô tô") | tiếng mưa + tiếng quạt hầm; từ "thủy kích" |
| H | insurance | **Trộm gỡ 2 gương + cạy cốp** xe Camry 30G-555.12 gửi bãi đêm, khách tên Phúc, có camera bãi xe | tên, vị trí bãi xe, xe+biển số, hạng mục mất (2 gương chiếu hậu, nẹp cốp), bằng chứng=camera | `SUBMIT_THEFT_PARTS_REPORT` + `SCHEDULE_SURVEYOR_VISIT` (2 action liên tiếp) | giọng miền Bắc nhanh; 2 trigger liền nhau |
| I | healthcare/tieu_hoa | BN Dũng 45t, đau thượng vị 2 tuần, ợ chua; **nội soi: viêm hang vị, test HP âm tính**; kê PPI Omeprazole 20mg sáng đói 4 tuần, hẹn tái khám | tên, triệu chứng, kết quả nội soi, HP âm tính (phân biệt với dương tính!), thuốc+liều+cách dùng, tái khám 4 tuần | `ISSUE_ELECTRONIC_PRESCRIPTION` | code-switch "HP âm tính" vs kịch bản D dương tính — bẫy trích xuất |
| J | healthcare/tim_mach | BN Loan 62t tăng huyết áp tái khám, HA nhà 150/95; **tăng liều Amlodipine 5mg→10mg**, thêm đo **Holter huyết áp 24h**, xét nghiệm điện giải đồ, tái khám 2 tuần | tên, chỉ số HA (ITN 150/95), thuốc chỉnh liều (cũ 5mg → mới 10mg), chỉ định Holter+điện giải đồ, tái khám 2 tuần | `ORDER_LAB_TESTS` + `SCHEDULE_FOLLOW_UP` | giọng BN lớn tuổi chậm; số liều thay đổi trên cùng 1 thuốc |
```

Quy trình sinh (script `scripts/gen_test_audio.py`, task P3a):
1. Soạn script hội thoại 2 vai (giám định viên/bác sĩ ↔ khách/BN) cho A–F
   (từ KB verbatim) và G–J (mới).
2. ElevenLabs TTS: mỗi vai một voice tiếng Việt khác nhau (nam/nữ, tốc độ
   khác nhau); xuất từng turn.
3. Ghép turn (pydub) + trộn nhiễu bằng torchaudio: còi cứu thương (A, B),
   trẻ khóc (B), mưa+quạt hầm (G), phòng khám ồn nhẹ (D–F, I, J); SNR kiểm
   soát 10–15dB.
4. Xuất mỗi kịch bản 3 biến thể: `clean.wav`, `noisy.wav`,
   `telephony.wav` (bandpass 300–3400Hz + downsample 8k→16k).
5. Gold labels: `packs/testcases/<id>.json` `{pack, transcript_ref,
   expected_fields, expected_actions}` — eval.py đọc trực tiếp.

## 5. Định nghĩa "đạt" khi eval

- Field-level: fuzzy match (rapidfuzz ratio ≥90 sau normalize) với gold; số/
  đơn vị/biển số phải **exact** sau ITN.
- Action: đúng id, đúng thời điểm (arm trong đoạn chứa trigger), không false
  positive ở 9 kịch bản còn lại.
- Scorecard xuất `docs/product/scorecard.md`: bảng field accuracy per
  scenario × {clean, noisy, telephony}.
