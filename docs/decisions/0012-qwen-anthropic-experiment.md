# 0012 Qwen 3.5 open-weight qua chuẩn Anthropic — lớp LLM đối chứng (amend 0010)

Date: 2026-07-19

## Status

Accepted

## Context

Decision 0010 (18/07, Long chốt) cấm LLM ngoài toàn pilot. Nhưng vụ "đưa LLM
vào để ra quyết định action" Long vẫn treo từ 18/07 chiều. 19/07 Long chỉ đạo
mới: cung cấp key workspace Alibaba MaaS riêng, yêu cầu tích hợp **Qwen 3.5
opensource theo chuẩn Anthropic** và **test cho phần phân tích và nhận
action**. Cần khung pháp lý nội bộ rõ để 0010 không bị hiểu là đã vứt.

## Decision

- **Amend 0010, không thay**: đường demo chính (batch / live / call) GIỮ
  nguyên extraction_local + TriggerMatcher — không call LLM nào trên đường
  nóng. Qwen 3.5 được phép như **lớp ĐỐI CHỨNG / THỬ NGHIỆM** ngoài đường
  demo (`app/core/llm_qwen.py`, `scripts/eval_qwen.py`), và là ứng viên tầng
  judge nếu Long chốt hybrid.
- **Chuẩn giao tiếp: Anthropic Messages API** (`/v1/messages`, content
  blocks, stop_reason) qua endpoint `{workspace}/api/v2/apps/claude-code-proxy`
  — auth `Authorization: Bearer` (x-api-key bị 401, đã probe). Code không
  phụ thuộc SDK — httpx thuần, giữ đúng shape Messages để sau này trỏ về
  Anthropic thật chỉ cần đổi base+key.
- **Model mặc định `qwen3.5-397b-a17b`** (open-weight flagship): action sạch
  14/14 + chặn phủ định 4/4 trong eval. Đổi qua `QWEN_MODEL`/`--model`.
- Key/base/model nằm trong `apikey.txt` (gitignored) qua `app/config.py` —
  cùng rule VALSEA: không in/log/commit.

## Alternatives Considered

1. OpenAI-compatible mode — hoạt động nhưng trái yêu cầu "chuẩn anthropic".
2. Mở lại Groq — trái 0010 + tiền sử 429 treo demo giữa cuộc gọi.
3. Model đóng (qwen3.5-plus/flash/max) — trái yêu cầu "opensource".
4. Giữ 0010 tuyệt đối (từ chối) — trái chỉ đạo mới 19/07 của chính Long.

## Consequences

Positive:

- Có số liệu thật cho quyết định hybrid judge: Qwen action 14/14 + phủ định
  4/4 (local main 10/14, thua cả 4 câu phủ định); field 90% vs local 100%
  (local tune theo bộ); latency ~8s → judge chỉ khả thi ASYNC sau ARM.
- Interface chuẩn Anthropic → sau này swap sang Claude API chỉ đổi config.

Tradeoffs:

- Thêm 1 phụ thuộc ngoài (chỉ trong eval/experiment, không trên đường demo).
- Latency ~7–8s/call — không dùng được cho trigger <500ms.
- Extractor local vẫn là điểm mù ngoài phân phối; so sánh này chưa đo bộ
  ngoài gold.

## Follow-Up

- Long chốt hybrid? → story mới: TriggerMatcher ARM (nhanh) + Qwen judge
  async FIRE/HOLD/REJECT có audit reason; cần merge US-101 trước để local có
  negation guard làm baseline công bằng.
- Bộ test ngoài phân phối (case mới không nằm trong tune set) trước khi quyết.
