# 0008 — Pilot stack, scope và các lựa chọn kiến trúc

- Status: accepted
- Date: 2026-07-18
- Context: VALSEA Hackathon 48h (xem `docs/product/overview.md`)

## Quyết định

1. **Stack**: FastAPI (Python 3.11+) + Alpine.js/Jinja2, không build step.
   Lý do: websocket + Pydantic + PDF thuận Python; frontend nhẹ đủ cho form
   động; tối ưu tốc độ làm trong 48h. (Người dùng chốt 2026-07-18.)
2. **Kiến trúc Domain Pack**: từ điển nghiệp vụ JSON cắm-rút, engine
   domain-agnostic. Đây là mô hình kinh doanh (dictionary-as-integration) và
   là luận điểm AI-Native Architecture.
3. **PyTorch cho lớp ML local**: silero-VAD (end-of-speech), PhoBERT/
   VietMed-NER hybrid verifier + fallback extraction, torchaudio cho audio
   pipeline. Deps tách `requirements-ml.txt`, degrade sạch khi thiếu —
   không để model download chặn demo. (Yêu cầu user: dùng PyTorch cho phần
   engine ML.)
4. **Vai trò vendor**: VALSEA = toàn bộ speech (ASR batch/RTT/TTS agent) —
   ràng buộc đề + tối đa điểm API. ElevenLabs = CHỈ sinh audio test (tách
   vendor để test khách quan). Groq = LLM extraction + whisper baseline đối
   chứng (ngoài pipeline chính).
5. **Trigger <500ms**: fuzzy match (rapidfuzz) trên partial, không LLM trong
   đường arm; two-stage arm→fire.
6. **Bậc thang degrade 3 tầng**: RTT → pseudo-streaming (webm chunk → batch
   API) → replay JSON. Groq → model nhỏ → NER local → degraded. Demo không
   được phép chết trên sân khấu.
7. **Phạm vi từ điển y tế**: chỉ nghiệp vụ khám chung + 3 chuyên khoa có
   trong bộ test (tiêu hóa, chấn thương chỉnh hình, tim mạch) — không ôm cả
   ngành y trong 48h. (Người dùng chốt 2026-07-18.)
8. **Bộ khung harness** (hoangnb24/repository-harness) được cài làm lớp vận
   hành agent: product docs, backlog, decisions, TEST_MATRIX/CLI. Story
   ceremony giữ ở mức tối thiểu đủ dùng cho hackathon.

## Hệ quả

- Repo public: `apikey.txt` gitignored từ commit đầu; CI/tài liệu không bao
  giờ echo key.
- Mọi UI làm sau khi mockup được duyệt (tránh rework 2 lần trong 48h).
- Eval scorecard (10 test case × 3 biến thể audio) là bằng chứng chấm điểm,
  chạy lại được bằng 1 lệnh.
