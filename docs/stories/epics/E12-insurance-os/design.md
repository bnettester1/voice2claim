# Design — E12 Insurance OS

Chi tiết đầy đủ trong `PLAN-E12-insurance-os.md` (bản duyệt 19/07). Tóm tắt quyết định thiết kế:

## Database (Phần 1 plan)

- stdlib `sqlite3` (không dep mới), WAL, `foreign_keys=ON`, `busy_timeout=5000`, migration `PRAGMA user_version` + `app/db/schema/NNN-*.sql` (mượn pattern harness). DB `data/app.db` (gitignore), env `APP_DB_PATH`.
- DAL sync mở connection ngắn per-call, async qua `run_db()` = `asyncio.to_thread`. 1 uvicorn worker (invariant sẵn có).
- ID nghiệp vụ TEXT giữ format cũ (`KH-…`, `NV-…`, `CL-XE-ddmm-seq`, `TCK-####`, `GCN-…`); bảng máy INTEGER PK; `sequences` sinh mã atomic; `name_norm` = `normalize_vi`.
- Biên giới chuẩn hoá: graph workflow là JSON nguyên khối (engine-owned); mọi thứ cần aggregate (runs/step_runs/events/tasks/evaluations) tách bảng riêng.
- Tích hợp minimal-diff: tickets qua `ticket_store.listeners` (không sửa `execute_action`); CRM DB-first → REST notify → fixture, adapter `to_crm_dict()` giữ nguyên shape dict cũ; 3 hook ~8 dòng trong `engine.py` (`crm_lookup`/`fire_flow_action`/`hangup_done`); packs giữ phần giọng nói/form, DB giữ phần thực thi/điều phối.

## Workflow engine (Phần 2)

- Graph `{nodes:[{id,type,label,config}], edges:[{from,to,when?,label?,else?}]}`; điều kiện `expr.py` an toàn (dotted path + op, không eval).
- Runner: per-run `asyncio.Lock`, step_runs ghi từng node, WAIT thoát coroutine (event-driven resume), CAS `UPDATE … WHERE status IN (waiting_*)` idempotent, `recover()` lúc boot, side-effect node check step done trước khi replay.
- `auto_call` node: CallEngine outbound script động render từ context; mode replay/browser mặc định (Twilio trial tắc DTMF carrier VN), twilio khi sẵn sàng.
- Khởi động run từ cuộc gọi: `IntentSpec.workflow` + hook sau `fire_flow_action`, fire-and-forget — zero độ trễ thêm.

## AI Điều hành (Phần 3)

- Router = `route_intent` keyword (call) + `/api/wf/dispatch` (ngoài call, cùng hàm, trả matched keywords + score).
- Mọi quyết định tự động ghi `status_history` actor_kind `ai`/`system` → Decision Feed.
- Qwen 3.5: CHỈ async judge sau run + KB extraction admin (mở rộng phạm vi 0012 → ghi ở decision 0013). Thiếu key → ẩn.

## UI (Phần 4)

- Shell `layout.html` sidebar trái + role switcher (localStorage, không auth); `/` = Dashboard; demo cũ wrap: index → `/pilot` (hash tab), `/call` giữ route.
- Frontend theo skill `emil-design-eng` (ease-out custom bezier, <300ms, transform/opacity only, reduced-motion, stagger…); audit `improve-animations` ở S6.
- Visualization `wfviz.js` tự viết (~260 LOC): Kahn toposort → cột longest-path, barycenter, card HTML + SVG bezier edges + pill điều kiện; run mode tô màu node theo status, poll 3s.
- Editor v1: JSON textarea + validate + preview + save v{n+1} immutable; mini-form cho field editable.

## Flywheel + KB (Phần 5, 6)

- evaluations theo rater_kind (customer ★ qua `/rate/{token}`, staff khi hoàn tất task, auto-metrics lúc end, qwen_judge async); `v_workflow_metrics` so sánh per version.
- KB upload sha1-dedupe `data/kb/`; Qwen extract → `kb_extractions` draft → promote thành `workflow_defs` bản draft.

## Rủi ro chính

Resume/idempotency runner (CAS + lock + recover + test headless); token single-use không PII; không await DB trong vòng thoại; WAL + to_thread + 1 worker; hydrate TCK seq từ MAX(DB); repo public — không log secret, `data/` gitignore.
