# Product Contract — VALSEA Speech-to-Meaning Pilot

> Hackathon 48h: *"Speech-to-Meaning, Not Speech-to-Text: Turning Vietnamese
> Voice into Workflow-Ready Action"* (VALSEA — Vietnam AI Innovation Challenge,
> track Innovation). Spec gốc: `Problem_Brief_VALSEA.docx.md` (root repo).

## 1. Bài toán

Từ một lớp tiếng nói tiếng Việt thật (hội thoại lộn xộn, code-switch Việt–Anh,
giọng vùng miền, nhiễu nền) → sinh ra **đầu ra sẵn sàng cho quy trình làm việc**:

- **Action Form**: biểu mẫu nghiệp vụ đúng chuẩn ngành được điền tự động.
- **Action Call**: lệnh nghiệp vụ có tên (vd `REQUEST_MOTORBIKE_TOWING`) được
  kích hoạt bằng câu nói ("bấm nút…"), thực thi thật (PDF, ticket, TTS).

Không dừng ở transcript. Không phải chatbot.

## 2. Mô hình sản phẩm (pitch)

**Một engine ngang + kho từ điển nghiệp vụ cắm-rút (Domain Pack).**
Doanh nghiệp tích hợp = cung cấp 1 file từ điển nghiệp vụ (schema form, catalog
action, thuật ngữ, luật chuẩn hóa) → engine tự thích nghi, không sửa code.
Đây là điểm khác biệt kiến trúc, khớp định vị hạ tầng ngang của VALSEA.

Vertical pilot: **Bảo hiểm (giám định tai nạn xe)** và **Y tế (khám bệnh —
nghiệp vụ chung + 3 chuyên khoa: tiêu hóa, chấn thương chỉnh hình, tim mạch)**.

## 3. Người dùng & luồng chính

| Người dùng | Luồng | Đầu ra |
| --- | --- | --- |
| Giám định viên bảo hiểm | Gọi điện/ghi âm hiện trường → form tai nạn tự điền → nói "bấm nút Gửi yêu cầu cứu hộ" | Biên bản PDF + ticket cứu hộ + TTS xác nhận |
| Bác sĩ / thư ký y khoa | Ghi âm buổi khám → bệnh án/đơn thuốc tự điền → "nhấn nút Kê đơn thuốc điện tử" | Đơn thuốc điện tử PDF + ticket HIS |
| Người vận hành demo | Đổi Domain Pack trên UI | Cùng engine, nghiệp vụ khác |

Ba chế độ chạy: **Batch** (upload/ghi âm xong xử lý) · **Live** (streaming mic,
form điền dần real-time, agent đáp giọng nói) · **Replay** (kịch bản thu sẵn —
cứu nguy demo).

## 4. Tiêu chí thành công (map với rubric chấm)

| Rubric | Trọng số | Cách pilot ăn điểm |
| --- | --- | --- |
| Best Use of VALSEA API | 15% | ASR batch + RTT streaming + `hint_text` nhận từ điển nghiệp vụ + TTS agent + semantic_tags/sentiment |
| Workflow-Readiness | 15% | Form + PDF + ticket + action call chạy thật, cắm được webhook |
| AI-Native Architecture | 20% | Domain Pack cắm-rút; hybrid LLM (Groq) + PyTorch NER local; degrade ladder 3 tầng |
| Problem Relevance | 20% | 2 vertical thật, form đúng chuẩn ngành, đo time-to-output |
| Technical Execution | 15% | Eval scorecard 10 test case; arm-latency <500ms có số đo |
| Deployment/Feasibility/Startup | 45% còn lại | URL public, roadmap pilot, mô hình dictionary-as-a-service |

**Ba outcome đo được trên sân khấu (theo brief):**
1. Time-to-output: từ giờ (ghi chép tay) → <1 phút, có stopwatch trên UI.
2. ≥1 hard case (code-switch/nhiễu/telephony) đúng, so side-by-side với ASR
   generic (Groq whisper-large-v3 làm đối chứng — ngoài pipeline chính).
3. Structured output chạy thật: form + PDF + ticket, không mockup.

## 5. Ràng buộc cứng

- **VALSEA ASR là bắt buộc** cho speech-to-text (`/v1/audio/transcriptions`,
  `wss /v1/realtime`). Không thay bằng ASR khác trong pipeline chính.
- Tiếng Việt bắt buộc, giữ đúng dấu; **không "Việt hóa" thuật ngữ tiếng Anh**
  chèn trong câu (EF, HP, LDL-C, MRI, tên thuốc).
- Intent latency <500ms cho trigger phrase "bấm nút…" (spec KB).
- `apikey.txt` không bao giờ được commit/đọc/in/log (repo sẽ public).
- Anti-pattern bị trừ điểm: wrapper chatbot, demo mockup, chỉ chạy data sạch.

## 6. Deliverables 48h

- [x] Prototype demo được — chạy local `localhost:8321` (4 chế độ: batch /
  live RTT / duyệt-chấm điểm / console; replay offline). URL public: deploy
  theo hướng dẫn roadmap khi có tài khoản hosting; video quay lúc rehearsal.
- [x] GitHub repo (source + harness docs; push public khi team sẵn sàng —
  `apikey.txt` đã gitignore từ commit đầu).
- [x] Kiến trúc explainable — `docs/product/architecture.md` (mermaid + spec
  API thật + thiết kế risk + số đo).
- [x] Pilot/deployment roadmap — `docs/product/pilot-roadmap.md`.
- [x] Bộ test: 10 kịch bản (A–F từ KB + G–J mở rộng) × clean/noisy/telephony,
  audio ElevenLabs (flash_v2_5 vi), gold labels, `scripts/eval.py` →
  `docs/product/scorecard.md`; E2E live `scripts/test_live.py`.

## 7. Nguồn dữ liệu chuẩn (gold)

- `KB_tainanxe.txt`: kịch bản A (va chạm xe máy–ô tô), B (ô tô + người bị
  thương), C (va chạm liên hoàn 3 xe) + NER form + Action Call kỳ vọng.
- `KB_khambenh.txt`: kịch bản D (tiêu hóa — loét tá tràng HP+), E (chấn thương
  chỉnh hình — gãy xương), F (tim mạch — siêu âm tim, EF 60%) + NER + Action.
- Test case mở rộng G–J: định nghĩa tại `docs/product/domain-packs.md` §4.
