# Validation Report — E12 Insurance OS

Ngày: 2026-07-19 · Branch `feature/e12-platform` (S0→S6, commit theo slice)

## Đối chiếu expectations (validation.md)

| # | Expectation | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | DB idempotent + bền | **PASS** | `init_db --reset` ×2 sạch; seed mỗi boot INSERT-if-missing; ticket TCK-0012 hydrate lại console sau reload server (chứng kiến trực tiếp khi uvicorn --reload); `scripts/test_db.py` 27/27 |
| 2 | Không hồi quy đường nói | **PASS** | `scripts/eval.py` 10/10 (86/86 field, trigger 0.5–1.4ms); `scripts/test_telephony.py` 49/49; replay E10 sau S1 và S4 vẫn đủ field, `status_reply` đọc y hệt (fixture seed trùng crm.py) |
| 3 | WF1 end-to-end | **PASS** | `scripts/test_workflow.py` case 1–3 (tự duyệt/reject/approve); E2E thật: intake UI → run #1 → mail Brevo `esign_request` (đính PDF) → `/sign/{token}` ký → policy `GCN-2026-363783` ACTIVE signed_at 19/07 02:28 → autocall + `esign_confirmed`; double-click token → no-op (CAS) |
| 4 | WF2 end-to-end | **PASS** | test case 4–5 (paid/rejected); E2E thật: replay call → run #2 tự khởi động (fire-and-forget sau fire_flow_action — không thêm độ trễ turn) → claim CL-XE-1907-002 → task thẩm định upload WAV thật → VALSEA bóc băng <5s (transcript thật) → `claim_report_RUN-2.pdf` → giám đốc duyệt UI → paid 5.000.000đ + 2 mail Brevo thật |
| 5 | Degrade sạch | **PASS** | Email stub test (không key → skipped, run vẫn done — case test); Qwen thiếu key → nút KB ẩn + judge im lặng (`ready()` gate); auto_call twilio thiếu điều kiện → tự về replay; DB lỗi → app chạy in-memory (lifespan try/except) |
| 6 | Flywheel | **PASS** | Run #3: khách ★5 qua `/rate/{token}` (single-use CAS); run #4: **Qwen judge thật ★4** kèm nhận xét (evaluations `qwen_judge`); auto-metrics mỗi run; bảng per-version trên trang workflow; editor lưu v mới (v1 immutable — wf_contract_open v1 archived, run #1 vẫn pin v1), activate chuyển con trỏ |
| 7 | UI chuẩn emil | **PASS** | Load skill emil-design-eng trước khi code; audit checklist (agent riêng) trên 12 file UI mới ra **8 finding** (thiếu `pointer:fine` 1 chỗ, thiếu reduced-motion cho card sign/rate, 5 nhóm phần tử bấm được thiếu `:active`/transition) — **đã sửa hết** (commit polish); 8/11 hạng mục còn lại sạch từ đầu (không `transition:all`, không scale(0), không ease-in, <300ms, stagger 45ms, origin đúng) |
| 8 | An toàn repo public | **PASS** | Scan secret trước commit (0 match/9.049 dòng P6 + các slice); `data/`, `out/` gitignore; token `secrets.token_urlsafe(16)` không PII |

## Con số chính

- Test tự động: test_db **27/27** · test_workflow **30/30** · test_telephony **49/49** · eval **10/10 (86/86 field)**.
- E2E thật đã chạy: 4 workflow run (2 từ web/dispatch, 1 từ cuộc gọi replay, 1 intake UI), 6+ email Brevo thật, 1 chữ ký điện tử, 1 autocall, 1 lần khách chấm ★, 1 Qwen judge, 1 KB extraction 16.7s → promote thành def draft `traffic_accident_assessment_call` (12 nodes, graph hợp lệ).
- AI Decision Feed: mọi bước đều có dòng actor `ai` (định tuyến, chấm rủi ro kèm lý do, giao việc, bóc băng, autocall, email, kết thúc run).

## Tồn đọng / giới hạn (đã chủ đích)

- E-sign/rate là demo-level (token 1 lần, không auth/không pháp lý).
- auto_call mode twilio chưa bật được với account trial (carrier VN nuốt DTMF — 0011); replay/browser dùng cho demo.
- KB extraction v1 chỉ file text; audio cần transcribe trước.
- Editor là JSON + preview (chưa drag-drop — ghi rõ trong 0013).
- 1 uvicorn worker (WAL + in-memory store).
