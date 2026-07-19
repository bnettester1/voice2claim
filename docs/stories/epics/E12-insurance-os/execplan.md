# Execplan — E12 Insurance OS

7 slice, mỗi slice chạy demo được + commit riêng trên branch `feature/e12-platform`. Chi tiết từng slice trong `PLAN-E12-insurance-os.md`.

| Slice | Nội dung | Verify chính |
|---|---|---|
| S0 | Commit P6 lên main (401bf63) · branch `feature/e12-platform` · bootstrap harness · intake #7 + story E12 · epic folder · decision 0013 | harness-cli query matrix có E12 |
| S1 | `app/db/` (database.py, schema/001-init.sql, dal/*, bridge.py, seed.py) · `scripts/init_db.py` · hook main.py/crm.py/engine.py · gitignore `data/` | `init_db --reset` idempotent ×2 · unit `to_crm_dict` · replay call E2E ra đủ rows customers/claims/interactions/tickets · `scripts/eval.py` 10/10 |
| S2 | `layout.html` sidebar (emil-design-eng) · dashboard skeleton · CRM 3 tab + Khách hàng 360 · API `/api/wf/crm/*` · wrap `/pilot` + `/call` | browser preview từng trang · demo cũ nguyên vẹn qua menu |
| S3 | `app/workflow/` (defs/expr/nodes/runner/routes/seeds/wf_mailer) · `wfviz.js` · trang workflows + run · `/sign/{token}` · intake mở hợp đồng (ảnh xe + voice-prefill) | `scripts/test_workflow.py` WF1 2 nhánh headless · E2E intake→mail→ký→active→confirm |
| S4 | human_task + tasks inbox + upload · transcribe_media · `IntentSpec.workflow` + hook flow_agent · claim lifecycle | replay E10 → wf_claim tự chạy → task upload WAV → biên bản PDF → duyệt → paid + mail · nhánh reject · latency gọi không đổi |
| S5 | `auto_call` node gắn 2 graph · Decision Feed · `/api/wf/dispatch` · dashboard pulse | WF2 approve → autocall đúng câu render · interactions call_out · feed đúng thứ tự |
| S6 | rate + evaluations + metrics + editor versioning · KB upload/extract + Qwen judge (flagged) · audit improve-animations · docs (0013 final, README, architecture, demo) · trace | 5 mục Verification tổng trong plan |

## Trạng thái

- [x] S0 — 19/07: main 401bf63 (P6), branch tạo, intake #7, story E12, epic folder, decision 0013.
- [x] S1 — commit c0cc86d: DB 22 bảng + DAL + bridge + hook telephony; test_db 27/27; E2E replay ra đủ rows; eval 10/10.
- [x] S2 — commit aa7d5ec: shell sidebar + Dashboard + CRM 360; demo cũ thành menu (/pilot, /call); verify browser 4 trang.
- [x] S3 — commit 9970e55: engine (expr/defs/nodes/runner) + WF1 + wfviz + /sign + intake; test_workflow 20/20; E2E thật ký → GCN active + 2 mail Brevo.
- [x] S4 — commit 12fcc64: WF2 + tasks inbox + hook cuộc gọi→run + VALSEA bóc băng; 30/30; E2E replay → biên bản → duyệt → paid + 2 mail.
- [x] S5 — commit e720513: auto_call (NotifyAgent) + dispatch + seed auto-upgrade version; E2E: dispatch keyword → run #3 → autocall render đúng câu.
- [x] S6 — flywheel (★ khách/nhân sự/auto/qwen_judge + bảng metrics/version + editor lưu v mới) + KB (upload/Qwen extract/promote — draft `traffic_accident_assessment_call` 12 nodes từ KB_tainanxe) + audit motion + hồ sơ.
