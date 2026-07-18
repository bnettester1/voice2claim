# Agent Instructions

## Local Project Notes — VALSEA Speech-to-Meaning Pilot

- **TUYỆT ĐỐI KHÔNG** đọc, in, log hay commit `apikey.txt` (đã gitignore).
  Code chỉ load nó lúc runtime qua `app/config.py`; probe chỉ báo OK/FAIL.
- Đọc trước: `docs/product/overview.md` (contract) →
  `docs/product/architecture.md` (thiết kế đã chốt) →
  `docs/product/domain-packs.md` (từ điển nghiệp vụ + test case G–J) →
  `docs/product/demo.md` (UI/kịch bản demo).
- Ràng buộc cứng: VALSEA ASR bắt buộc cho speech-to-text pipeline chính
  (batch `/v1/audio/transcriptions`, live `wss /v1/realtime`). **KHÔNG dùng
  Groq/LLM ngoài** (Long chốt 18/07, decision 0010) — extraction chạy local
  (`app/core/extraction_local.py` + `app/telephony/parse_vi.py`), tận dụng
  semantic_tags/formatting/TTS của VALSEA. Trigger "bấm nút…" phải arm <500ms.
- Stack: FastAPI + Alpine.js (không build step). PyTorch cho lớp ML local
  (`app/core/ml/`), deps tách `requirements-ml.txt`, thiếu thì degrade sạch.
- Dữ liệu gold: `KB_tainanxe.txt`, `KB_khambenh.txt` — không sửa 2 file này.
- UI phải bám mockup đã duyệt tại `docs/product/mockup/`.
- Quyết định kiến trúc: `docs/decisions/0008-pilot-stack-and-scope.md`.

<!-- HARNESS:BEGIN -->
## Harness

Choose the request class before any Harness operation.

- When the requested outcome is only an answer, explanation, review, diagnosis,
  plan, or status report: inspect only the material needed to respond. Keep the
  task read-only. Do not bootstrap, initialize or migrate a database, record
  intake, or record a trace.
- When the user explicitly asks to change, build, fix, or write repository
  artifacts: first run `scripts/bootstrap-harness.sh`
  on macOS/Linux or `.\scripts\bootstrap-harness.ps1` on Windows. Then use
  `docs/FEATURE_INTAKE.md` to classify and record the request, query
  `scripts/bin/harness-cli query matrix --active --summary` on macOS/Linux or
  `.\scripts\bin\harness-cli.exe query matrix --active --summary` on Windows,
  and retrieve only the lane- and task-specific context described in
  `docs/CONTEXT_RULES.md`.
<!-- HARNESS:END -->
