# Overview — E11 Qwen 3.5 đối chứng (chuẩn Anthropic)

## Current Behavior

Decision 0010: không LLM ngoài toàn pilot — extraction = `extraction_local.py`,
action = `TriggerMatcher` (rule). Trên main CHƯA có negation guard (US-101 còn
ở worktree zen-burnell) → câu "khoan/đừng bấm nút…" vẫn arm nhầm. Vụ "LLM
judge cho action-fire" Long treo từ 18/07 chưa chốt.

## Target Behavior

Theo chỉ đạo Long 19/07: tích hợp **Qwen 3.5 open-weight** (workspace Alibaba
MaaS riêng của Long) qua **chuẩn Anthropic Messages API** làm lớp LLM **ĐỐI
CHỨNG thử nghiệm** cho 2 việc: phân tích transcript (extraction field) và nhận
action (fire/không, hiểu phủ định). Đo đối chứng với engine local trên bộ gold
A–J + 4 case phủ định. Đường demo chính KHÔNG đổi (0010 giữ nguyên cho
batch/live/call — xem decision 0012).

## Affected Users

Long (đánh giá hướng hybrid judge), giám khảo (nếu demo phần so sánh).

## Affected Product Docs

`AGENTS.md` (ràng buộc LLM có ngoại lệ 0012), decision 0012 (amend 0010),
story này. README/demo chưa đổi — chưa có bề mặt UI.

## Non-Goals

Không thay extraction_local trên đường demo; không gọi Qwen trong live/call
path (latency ~8s/call >> trần 500ms trigger); chưa bật judge tự động —
chờ Long chốt hybrid sau khi xem số liệu.
