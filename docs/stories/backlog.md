# Story Backlog — VALSEA Speech-to-Meaning Pilot

Intake: **New spec** (Problem Brief VALSEA + quyết định user 2026-07-18).
Product docs: `docs/product/overview.md`, `architecture.md`, `domain-packs.md`,
`demo.md`. Task list vận hành chi tiết nằm trong Claude task list (13 task);
bảng này là ánh xạ epic → story cho harness.

## Epics

| Epic | Mô tả | Lane | Status |
| --- | --- | --- | --- |
| E1 Foundation | Harness + git + config loader + probe 3 API (không lộ key) | tiny | in_progress |
| E2 Dictionary | Domain Pack v1 từ KB (insurance_motor, healthcare_exam) + mở rộng từ điển (claims ops chung; y tế chung + tiêu hóa/chỉnh hình/tim mạch) | normal | planned |
| E3 Engine | Extraction Groq + FormStore + TriggerMatcher + eval text-mode 6/6; PyTorch layer (silero-VAD, NER hybrid) | normal | planned |
| E4 Batch UX | Upload/ghi âm → transcribe → form động + stopwatch; Action executor (PDF/ticket/TTS); hard-case panel | normal | planned |
| E5 Live Call | AudioWorklet → relay RTT → patch live + trigger <500ms + fallback ladder + replay | high-risk | planned |
| E6 Test Data | Audio ElevenLabs 6 kịch bản KB + 4 test case mới G–J (clean/noisy/telephony) + gold labels + scorecard | normal | planned |
| E7 Ship | Mockup UI (duyệt trước) → polish, README, roadmap pilot, deploy URL, rehearsal + video | normal | in_progress (mockup) |

## Story slices (tạo packet khi bắt tay làm)

- E2-S1 pack schema + loader Pydantic + hint_text builder.
- E2-S2 nội dung insurance_motor (A/B/C + mở rộng G/H).
- E2-S3 nội dung healthcare_exam (chung + 3 specialties, D/E/F + I/J).
- E3-S1 extraction + merge + eval 6/6 text.
- E3-S2 trigger matcher + đo arm-latency.
- E3-S3 ml/vad.py + ml/ner_local.py (degrade sạch khi thiếu deps).
- E3-S4 core/scoring.py — FormScorer (completeness/confidence/agreement/
  validators, cap 79 khi khuyết field bắt buộc, score.update).
- E4-S4 Màn 4 Duyệt & Chấm điểm: đọc lại form + evidence + nghe lại đoạn
  audio, sửa inline re-score live, gate GỬI (≥85 / 60–84 xác nhận / <60
  override có lý do) → mới chạy Action Executor + audit trail.
- E5-S1 worklet + echo relay (proof: partial hiện trên UI).
- E5-S2 extraction live + state.patch + action fire + TTS.
- E5-S3 fallback pseudo-streaming + replay mode.
- E4-S5 DocumentComposer: narrative từ VALSEA /v1/formatting (service_log /
  meeting_minutes / subtitles SRT) + fallback Groq VN; ticket đính
  service_log, priority = sentiment + frustration_level.
- E6-S1 script hội thoại G–J + gold labels.
- E6-S2 gen audio + mix nhiễu + telephony; eval audio-mode.

## Ràng buộc xuyên suốt

- `apikey.txt`: không đọc/in/log/commit (đã gitignore dòng 2).
- VALSEA ASR bắt buộc trong pipeline chính; whisper chỉ làm đối chứng.
- Mọi story UI phải bám mockup đã duyệt (`docs/product/mockup/`).
