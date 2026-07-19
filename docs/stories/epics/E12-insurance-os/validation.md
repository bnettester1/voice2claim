# Validation — E12 Insurance OS

## Expectations

1. **DB idempotent + bền**: `scripts/init_db.py --reset` chạy 2 lần liên tiếp không lỗi; xoá `data/app.db` → app boot tự migrate + seed; ticket sống qua restart (console hiện lại ≤50 ticket gần nhất, `_seq` không lùi).
2. **Không hồi quy đường nói**: `scripts/eval.py` 10/10 (86/86 field); replay call E10 đủ 7/7 field; trigger arm vẫn <500ms (arm_ms log); `status_reply` đọc nội dung y hệt trước E12 với fixture cũ.
3. **WF1 end-to-end**: intake web (có ảnh xe) → ai_assess rẽ đúng 2 nhánh theo ngưỡng → PDF hợp đồng → mail Brevo có link ký → `/sign/{token}` ký → policy `active` → autocall + mail confirm (+link ★). Double-click link ký không tạo run kép (CAS idempotent).
4. **WF2 end-to-end**: replay call → run tự khởi động sau `fire_flow_action` (fire-and-forget, không thêm độ trễ turn) → claim `investigating` → task thẩm định (upload WAV+ảnh) → VALSEA transcribe ra biên bản PDF có transcript → giám đốc duyệt cả 2 nhánh approve/reject → claim `paid`/`rejected` + email đúng template.
5. **Degrade sạch**: không Brevo key → email skip, run vẫn done; không Qwen key → judge + KB extract ẩn; không Twilio → auto_call mode replay/browser vẫn chạy.
6. **Flywheel**: ★ khách qua `/rate/{token}` (single-use), ★ staff khi hoàn tất task, auto-metrics mỗi run; `v_workflow_metrics` so sánh v1 vs v2 sau khi sửa def bằng editor (version mới, version cũ immutable).
7. **UI chuẩn emil**: audit `improve-animations` không còn finding mức cao; `prefers-reduced-motion` được tôn trọng; sidebar điều hướng đủ menu map trong plan; demo cũ (`/pilot`, `/call`) nguyên chức năng.
8. **An toàn repo public**: không secret trong diff (scan trước mỗi commit); `data/`, `out/uploads/` gitignore; token link không chứa PII.

## Proof

(Ghi ở validation-report.md khi hoàn tất S6.)
