# Execplan — E11 Qwen 3.5 đối chứng

1. ✅ Intake #6 (high-risk — hard gate external provider; amend 0010).
2. ✅ Probe workspace (scratchpad, không in key): list models (149, 94 qwen3*);
   tìm endpoint Anthropic-compatible → `/api/v2/apps/claude-code-proxy/v1/messages`
   OK với Bearer (x-api-key 401); OpenAI-compatible OK (đối chứng).
3. ✅ Nạp key: append `QWEN_API/QWEN_BASE/QWEN_MODEL` vào `apikey.txt`
   (gitignored, script không in giá trị).
4. ✅ `app/config.py`: alias + env + Settings.qwen_* + status()["qwen"].
5. ✅ `app/core/llm_qwen.py`: messages_create (chuẩn Anthropic) + analyze
   (prompt từ pack) + parse JSON robust.
6. ✅ `scripts/eval_qwen.py`: A–J + N1q–N4q, so local, report file riêng.
7. ✅ Smoke B+N1q → lộ lệch semantic ("nhớ bấm nút" bị coi là hướng dẫn) →
   tune LUẬT 1 trong prompt → B ✅ mà phủ định vẫn chặn.
8. ✅ Full run 397b (report eval-report-397b.md) + 35b (eval-report-35b.md).
9. ✅ Decision 0012 + AGENTS.md ngoại lệ + story/DB records + trace.
