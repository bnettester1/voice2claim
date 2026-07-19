# Overview — E12 Insurance OS

## Current Behavior

- Không có database sản phẩm: state nằm ở dict in-memory (`ticket_store`, `SESSIONS`, `CALLS`), file `out/*.pdf` + `out/recordings/`, CRM là REST notify ngoài + fixture hardcode trong `app/telephony/crm.py`.
- "Workflow" là code ngầm: `FlowAgent` + `pack.call_flows.intents` (2 intent), không cấu hình được ngoài pack JSON, không có trạng thái bền, không rẽ nhánh ngoài cuộc gọi, không có human task / chờ sự kiện.
- UI là 2 trang demo rời (`/` tabs batch/live/review/console, `/call`), không có màn hình vận hành cho đội nghiệp vụ.

## Target Behavior

- SQLite `data/app.db` chuẩn hoá toàn bộ: CRM (customers/policies/insured_assets/claims/interactions/documents), ERP-lite (employees/tasks), workflow platform (workflow_defs versioned + graph JSON, action_catalog, workflow_runs, step_runs, events), flywheel (evaluations + v_workflow_metrics), KB (kb_documents/kb_extractions), tickets bền qua restart.
- Workflow engine: graph JSON config trong DB, 14 node types (collect_form, crm_lookup, ai_assess, branch, gen_pdf, send_email, wait_event, human_task, transcribe_media, auto_call, fire_action, update_record, start, end), runner event-driven wait/resume, crash-safe.
- 2 flow demo end-to-end: `wf_contract_open` (intake → AI thẩm định → hợp đồng PDF → e-sign qua mail → kích hoạt → autocall + confirm) và `wf_claim` (nối E10: cuộc gọi → claim → thẩm định hiện trường + bóc băng VALSEA → biên bản → giám đốc duyệt → chi trả/từ chối).
- Web app vận hành: sidebar trái, Dashboard (pulse + AI Decision Feed), CRM 360, Hộp công việc theo vai, trang workflow có visualization DAG + editor version hoá, KB, demo cũ thành menu (`/pilot`, `/call`).
- AI Điều hành minh bạch: route keyword (call + dispatch), mọi quyết định hệ thống ghi `status_history` actor `ai/system`; Qwen chỉ async (judge + KB extraction), degrade sạch khi thiếu key.
- Flywheel: đánh giá ★ theo vai + auto-metrics mỗi run, so sánh theo version của workflow def.

## Affected Users

- Tổng đài viên / CSR (nhận cuộc gọi, hoàn thiện phiếu).
- Thẩm định viên (task hiện trường, upload ghi âm/ảnh).
- Giám đốc (duyệt chi trả).
- Khách hàng (link ký điện tử, email, autocall, đánh giá ★).
- Admin nền tảng (sửa workflow, xem metrics, KB).

## Affected Product Docs

- `PLAN-E12-insurance-os.md` (plan đã duyệt 19/07)
- `docs/product/architecture.md`, `docs/product/demo.md`, `README.md` (cập nhật ở S6)
- `docs/decisions/0013-platform-db-workflow-engine.md`

## Non-Goals

- Auth/phân quyền thật (role switcher demo-level, không đăng nhập).
- Thanh toán thật (payout = status + email).
- Drag-drop workflow builder (editor v1 = JSON + preview + mini-form).
- LLM trên đường batch/live/call (giữ 0010/0012).
- Multi-tenant / template nghiệp vụ thuế-nhân sự-kế toán (làm sau, ngoài E12).
