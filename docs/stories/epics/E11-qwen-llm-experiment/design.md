# Design — E11 Qwen 3.5 đối chứng

## Kiến trúc

```
apikey.txt (QWEN_API / QWEN_BASE / QWEN_MODEL — gitignored, KHÔNG log)
    └─ app/config.py (alias qwen/qwen_base/qwen_model; status() chỉ báo bool)
        └─ app/core/llm_qwen.py
            ├─ messages_create(): POST {QWEN_BASE}/v1/messages
            │    CHUẨN ANTHROPIC: body {model, max_tokens, system, messages},
            │    response Message object (content blocks, stop_reason, usage).
            │    Khác gốc: auth `Authorization: Bearer` (x-api-key → 401,
            │    probe 19/07); vẫn gửi anthropic-version. Retry ×2 nhẹ.
            ├─ analyze(pack, transcript): prompt dựng từ pack
            │    (all_fields + actions + 3 LUẬT semantic) → JSON
            │    {fields{name:{value,confidence,evidence}}, actions[{id,fire,reason}]}
            │    — fields cùng shape extraction.extract() để so trực tiếp.
            └─ _parse_json(): bóc fence + cắt object cân bằng ngoặc.
scripts/eval_qwen.py — bảng so QWEN vs LOCAL từng case + tổng + mục phủ định.
```

## Luật semantic trong prompt (khớp spec TriggerMatcher + US-101)

1. Ai đó NÓI RA cụm kích hoạt (kể cả dạng nhắc "nhớ bấm nút X") → fire=true —
   cụm kích hoạt là LỆNH điều khiển hệ thống, không phải mô tả.
   (Vòng tune 1: thiếu luật này Qwen từ chối case B — "chỉ là lời hướng dẫn".)
2. Ngoại lệ duy nhất: phủ định/trì hoãn tường minh ngay trước cụm
   (đừng/khoan/thôi/chưa cần/không cần/để sau/hỏi…đã) → fire=false.
3. Chỉ kể sự việc, không ai nói cụm kích hoạt → fire=false.

## Eval

- Tái dùng `match_scalar`/`match_list` của `scripts/eval.py` (importlib) —
  một nguồn chân lý so khớp duy nhất.
- 4 case phủ định N1q–N4q dựng ĐỘNG từ `pack.actions[:2].triggers[0]` của 2
  pack (không hardcode id; main chưa merge `negative_triggers.json` của
  US-101 nên không dùng được file đó).
- KHÔNG đụng `docs/product/scorecard.md` (bài học backlog #2) — report ghi
  file riêng trong story folder qua `--report`.

## Chọn model

`qwen3.5-397b-a17b` (open-weight flagship MoE) làm default — action sạch
14/14. Bản `qwen3.5-35b-a3b` đo thử: không nhanh hơn đáng kể (median 6.8s vs
8.1s trên workspace này) mà dính 1 FP → không đáng đổi. Đổi model qua
`QWEN_MODEL` hoặc `--model`, không sửa code.

## Alternatives Considered

1. OpenAI-compatible endpoint (`/compatible-mode/v1`) — hoạt động, nhưng Long
   yêu cầu chuẩn Anthropic; proxy `/api/v2/apps/claude-code-proxy` đáp ứng.
2. Mở lại Groq — loại: 0010 + tiền sử 429 làm treo demo (0009).
3. `qwen3.5-plus/flash` (đóng) — loại: Long yêu cầu bản opensource/open-weight.
