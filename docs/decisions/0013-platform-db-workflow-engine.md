# 0013 Platform hoá: DB sản phẩm SQLite + Workflow Engine cấu hình trong DB + AI Điều hành

Date: 2026-07-19

## Status

Accepted (Long duyệt plan E12 ngày 19/07, `PLAN-E12-insurance-os.md`)

## Context

Pilot đến E11 chứng minh được chuỗi speech-to-meaning nhưng toàn bộ state là in-memory/file, CRM là REST ngoài + fixture, workflow là code ngầm trong `FlowAgent` + pack JSON — không thể demo câu chuyện "nền tảng tự động hoá workflow doanh nghiệp" (mở hợp đồng, claim end-to-end nhiều vai, tự cải tiến). Long chỉ đạo: chuẩn hoá lại database, dựng mini CRM/ERP cho công ty bảo hiểm, workflow gồm action lưu + config trong DB có visualization, autocall khi có action, 1 AI hiểu toàn bộ quy trình đứng sau điều khiển, kho tri thức + flywheel; frontend theo bộ skill emilkowalski.

## Decision

1. **DB sản phẩm**: SQLite stdlib (`data/app.db`, WAL, migration `PRAGMA user_version` + `app/db/schema/NNN-*.sql`) — zero dependency mới, tách hẳn `harness.db`. Schema chuẩn hoá CRM + ERP-lite + workflow platform + flywheel + KB + tickets; graph workflow là JSON nguyên khối trong `workflow_defs` (biên giới chuẩn hoá có chủ đích: phần cần aggregate — runs/steps/events/tasks/evaluations — đều là bảng riêng).
2. **Workflow engine** (`app/workflow/`): 14 node types, runner event-driven (WAIT thoát coroutine, resume bằng event + CAS idempotent, `recover()` khi boot), version hoá def (run pin version, bản cũ immutable). Tích hợp minimal-diff vào code cũ: `ticket_store.listeners`, adapter `to_crm_dict()`, 3 hook trong `engine.py`, `IntentSpec.workflow`.
3. **AI Điều hành v1 trung thực**: router keyword (`route_intent`) cho cả call + `/api/wf/dispatch`; mọi quyết định tự động ghi `status_history` actor `ai/system` → Decision Feed. **Amend phạm vi 0012**: Qwen 3.5 được dùng thêm cho 2 việc offline/async ngoài đường nói — (a) judge sau run (evaluations `qwen_judge`), (b) KB extraction admin (tài liệu → draft workflow) — vẫn TUYỆT ĐỐI không gọi trong batch/live/call path; thiếu key thì 2 tính năng tự ẩn.
4. **Autocall**: node `auto_call` dùng CallEngine outbound sẵn có, mode mặc định replay/browser (outbound Twilio trial tắc DTMF carrier VN — 0011), bật twilio khi account sẵn sàng.
5. **UI**: app shell sidebar trái (`/` = Dashboard), demo cũ thành menu (`/pilot`, `/call` wrap layout); frontend bắt buộc theo skill `emil-design-eng`, audit `improve-animations` trước khi chốt; visualization DAG tự viết (`wfviz.js`), không vendor mermaid.

## Alternatives Considered

1. SQLAlchemy/SQLModel + aiosqlite — bị loại: thêm dependency + failure mode, codebase dict-centric không cần ORM.
2. Nodes/edges tách bảng quan hệ — bị loại: chỉ được reassemble lại thành JSON, không có truy vấn nào cần join node.
3. Vendor mermaid.min.js (~2MB) cho visualization — bị loại: nặng, khó theme theo mockup, khó tô trạng thái run + click node.
4. LLM làm router trực tiếp trong cuộc gọi — bị loại theo 0010/0012 (latency ~8s, ràng buộc <500ms).
5. Giữ demo pages nguyên vị trí, platform là trang phụ — bị loại theo chỉ đạo Long: sidebar trái, demo thành menu.

## Consequences

Positive:
- State bền qua restart, demo nhiều vai (CSR/thẩm định/giám đốc/khách) trên cùng một nguồn dữ liệu; workflow sửa được bằng UI (version hoá) — đúng câu chuyện platform.
- Đường nói giữ nguyên hiệu năng và hành vi (hook fire-and-forget, adapter giữ shape dict cũ).
- Flywheel đo được thật (metrics per version), AI Điều hành giải thích được từng quyết định.

Tradeoffs:
- Runner tự viết → gánh rủi ro resume/idempotency (đối sách: CAS + per-run lock + recover + test headless 2 graph).
- SQLite 1-worker là trần scale (chấp nhận cho pilot; đằng nào in-memory store cũ cũng đã ép 1 worker).
- E-sign/rate token là demo-level (single-use, không auth) — không phải chữ ký điện tử pháp lý.
- Qwen mở rộng sang KB/judge làm tăng bề mặt phụ thuộc key ngoài (đối sách: degrade ẩn tính năng).

## Follow-Up

- S6: cập nhật `architecture.md`, `demo.md`, README; validation-report E12; trace.
- Khi Twilio account nâng cấp: bật `auto_call` mode twilio + cập nhật VoiceUrl runbook.
- Tương lai (ngoài E12): DB-sourced intents cho call path, drag-drop editor, template nghiệp vụ thuế/nhân sự/kế toán, multi-tenant.
