# PROJECT DID — Speech-to-Meaning Pilot (VALSEA Hackathon 2026)

*Cập nhật: 2026-07-18 · Thống kê toàn bộ việc đã làm + việc đang dở dang.*

## Sản phẩm trong 30 giây

**"Từ Giọng Nói Đến Hành Động"** — biến hội thoại tiếng Việt thật (code-switch
Việt–Anh, giọng vùng miền, nhiễu nền, telephony) thành **Action Form đúng chuẩn
ngành + Action Call thực thi thật** (PDF, ticket, email, TTS xác nhận) — không
dừng ở transcript.

Kiến trúc lõi: **một engine ngang + kho từ điển nghiệp vụ cắm-rút (Domain
Pack)**. Doanh nghiệp tích hợp chỉ cần cung cấp 1 file JSON từ điển (schema
form, catalog action, thuật ngữ, luật chuẩn hóa) — engine tự thích nghi, không
sửa code. Pilot chạy 4 pack: bảo hiểm xe, y tế ngoại trú (+3 chuyên khoa),
hợp đồng bảo hiểm (outbound call), tổng đài CSKH bảo hiểm.

```
Giọng nói ─► VALSEA ASR (batch + realtime WSS, hint_text từ từ điển)
          ─► Semantic Engine local (rule + semantic_tags + PyTorch NER — không LLM ngoài, ~200ms)
          ─► Action Form điền dần (confidence từng field) ─► FormScorer + màn Duyệt (human gate)
          ─► Action Call: PDF chuẩn ngành + ticket hệ lõi + email + TTS xác nhận
```

Stack: FastAPI + Alpine.js (không build step) · PyTorch optional (VAD +
NER local, degrade sạch khi thiếu) · VALSEA là AI đám mây duy nhất.

---

## ✅ ĐÃ LÀM (theo milestone)

### P0–P1 — Nền móng + Semantic Engine
- Harness vận hành agent-ready (AGENTS.md, product docs, stories, decisions,
  harness-cli) theo repository-harness.
- Bộ tài liệu sản phẩm đầy đủ: `docs/product/` (overview = product contract,
  architecture có mermaid + spec API thật, domain-packs, demo script, mockup
  UI đã duyệt, pilot-roadmap).
- `app/config.py`: loader key an toàn (env > `apikey.txt` > `~/.notify.env`),
  chống lộ key qua repr/log; `scripts/probe.py` probe API chỉ báo OK/FAIL.
- Domain Pack v1: `packs/insurance_motor.json` + `packs/healthcare_exam.json`
  (schema Pydantic, hint_text builder, itn_rules, triggers, validators).
- Semantic engine + eval text-mode đạt 6/6 kịch bản gold (KB A–F).

### P2 — Batch path end-to-end + UI
- Upload/ghi âm → VALSEA `/v1/audio/transcriptions` → form động điền tự động
  + stopwatch time-to-output trên UI.
- **FormScorer** (`app/core/scoring.py`): completeness/confidence/agreement/
  validators, cap 79 khi khuyết field bắt buộc, re-score live khi sửa tay.
- **Action Executor** (`app/core/actions.py`): sinh PDF chuẩn ngành, ticket
  vào Core System Console (webhook log), TTS xác nhận.
- 4 màn UI theo mockup: 📁 Xử lý ghi âm · 📞 Live Call · ✅ Duyệt & Chấm điểm
  (gate gửi ≥85 / 60–84 xác nhận / <60 override có lý do) · 🗄️ Console.

### P4a — Live Call realtime (RTT)
- AudioWorklet mic → relay `wss /v1/realtime` VALSEA → partial/final →
  form điền dần real-time trên UI; trigger "bấm nút…" arm trên partial.
- Demo chips (audio mẫu A–J phát thẳng vào pipeline live) + bridge
  live → màn Duyệt.
- Số đo thật: session.ready **1.1–1.4s**, trigger arm **0.2–0.3ms**
  (đích <500ms), form bắt đầu điền từ ~giây thứ 9 của cuộc gọi.

### P3 + P4b — Bộ test mở rộng + PyTorch layer + Replay
- 4 test case mới G–J (ngập nước, trộm vặt, tiêu hóa, tăng huyết áp) + bộ
  audio test sinh bằng ElevenLabs (vi) × 3 biến thể **clean/noisy/telephony**
  (mix nhiễu + mô phỏng băng thông điện thoại 8kHz).
- PyTorch layer optional (`app/core/ml/`): silero-VAD + NER local đối chiếu
  (agreement score vào FormScorer); thiếu `requirements-ml.txt` thì degrade sạch.
- ITN rules trong pack (số đọc chữ → chữ số, biển số, liều thuốc…) sửa lỗi ASR.
- **Replay mode**: `scripts/test_live.py --record` ghi lại phiên RTT thật →
  chip replay trên UI, demo không cần mạng/credits.
- `scripts/eval.py` (text + audio mode) tự sinh `docs/product/scorecard.md`.

### P5 — Ship-ready
- Pilot & deployment roadmap (giai đoạn 0→3, KPI pilot, rủi ro/giảm thiểu).
- Runbook demo 4 màn (`docs/product/demo.md`), hardening mạng/retry
  (batch warm ~10–14s, cold 122s → warm-up), README đầy đủ.

### E8 — ☎️ Outbound Agent Call (AI gọi ra cho khách)
- Trang `/call`: tổng đài viên AI **gọi ra** hỏi thông tin còn thiếu của hợp
  đồng theo kịch bản trong pack, nghe khách trả lời (VALSEA RTT), điền form
  dần, đủ field thì gửi ticket + PDF + email.
- 3 mode bậc thang (demo không bao giờ chết): 🔁 **Replay** (đã verify
  end-to-end 4/4 field + ticket + PDF) · 🎧 **Browser** (mic/loa, đóng vai
  khách) · ☎️ **Twilio** (gọi số thật qua tunnel; webhook validate
  `X-Twilio-Signature`, mask số điện thoại trong log).
- Giọng agent = VALSEA TTS transcode μ-law; câu kịch bản pre-synthesize +
  cache (`assets/tts_cache/`); parser rule field-aware tiếng Việt
  (`app/telephony/parse_vi.py`: số đọc chữ, ngày sinh, CCCD, biển số, địa chỉ).
- Flow tổng đài CSKH (`insurance_callcenter`): nhận diện khách (CRM lookup
  qua notify REST, có fallback local data fake), tra cứu trạng thái claim, đọc
  ETA; email xác nhận qua mailer in-app (`app/core/mailer.py`).
- `scripts/test_telephony.py`: 21 test offline (codec μ-law/resample,
  TwiML/chữ ký, state machine agent 3 kịch bản).

### E9 — VALSEA-only (gỡ toàn bộ LLM ngoài) — decision 0010
- Groq bị gỡ hoàn toàn (từng làm treo demo vì rate-limit 429/744s).
- **Extraction chạy local** (`app/core/extraction_local.py` ~36KB): anchor
  synonyms từ pack + chiến lược domain + VALSEA semantic_tags + NER PyTorch
  verify. Không mạng, không rate-limit, ~200ms.
- Narrative PDF: VALSEA `/v1/formatting` trước, fallback template ghép field.
- Tài liệu cơ chế: `docs/product/co-che-normalization-va-tu-dien-ner.md`
  (110KB — normalization + từ điển NER), `docs/product/flow.html` (sơ đồ
  luồng), `docs/product/kich-ban-doc-thu.md` (kịch bản đọc thử demo).

### Kết quả đo được (đã kiểm chứng trên máy thật)
| Chỉ số | Kết quả |
| --- | --- |
| Eval gold 10 kịch bản (A–J) text-mode | **10/10 PASS · 86/86 field (100%)** |
| RTT session.ready | 1.1–1.4s |
| Trigger "bấm nút…" arm trên partial | 0.2–0.3ms (đích <500ms) |
| Batch transcribe (warm) | ~10–14s (cold 122s → có warm-up) |
| Extraction local | ~200ms, 0 call mạng |
| Test telephony offline | 21/21 PASS |
| E8 replay end-to-end | 4/4 field + ticket + PDF ✅ |

---

## 🔄 ĐANG LÀM / DỞ DANG

1. **Mode Twilio gọi số thật (E8)** — code xong + test offline pass, còn chờ:
   Twilio credentials (SID/token/số from) + tunnel public (`ngrok`/
   `cloudflared`). Runbook bật mode nằm trong README §Outbound Agent Call.
   Lưu ý trial Twilio: chỉ gọi số đã verify, không có số +84.
2. **US-101 — required_fields gate + chặn phủ định trigger** ("đừng bấm nút…"
   không được kích hoạt action) — đã làm xong ở worktree Claude riêng
   (`zen-burnell`), **chưa merge vào main** → chưa có trong bản export này.
3. **Deploy URL public** — chưa deploy (roadmap giai đoạn 1 có hướng dẫn
   Docker + VM; demo hiện chạy `localhost:8321`).
4. **Video demo + rehearsal** — quay lúc chạy thử theo runbook `demo.md`.
5. **Hướng nâng cấp đã bàn, chưa làm**: lexicon sense-entry
   (concept–sense–surface, trie leftmost-longest), lexicon-enhanced NER
   (SoftLexicon/PhoBERT), double-confirm số dài bằng giọng nói.

---

## 📁 Cấu trúc thư mục

```
app/
  main.py            # FastAPI: / (4 màn), /call, /health, /pdf, /rec
  config.py          # loader key an toàn (env > apikey.txt) — không log key
  batch/             # upload/transcribe batch + routes chính
  realtime/          # relay WSS VALSEA RTT (live call)
  telephony/         # E8: engine gọi ra, parse_vi, twilio, tts, crm, flows
  core/              # extraction_local, scoring, triggers, actions, mailer, ml/
  web/               # Alpine.js UI (index + call), không build step
packs/               # 4 Domain Pack JSON + testcases gold
scripts/             # probe, eval, gen_test_audio, test_live, test_telephony
docs/product/        # overview, architecture, domain-packs, demo, roadmap…
docs/decisions/      # ADR 0001–0010 (0008 stack, 0009 telephony, 0010 VALSEA-only)
docs/stories/        # backlog + epics E08/E09 (design/execplan/validation)
KB_tainanxe.txt, KB_khambenh.txt   # dữ liệu gold — KHÔNG sửa
assets/              # replay sessions, tts_cache, audio noise (tracked)
```

## 🔐 Key & bảo mật (quan trọng khi clone)

- Repo **không chứa bất kỳ API key nào**. Muốn chạy: copy
  `apikey.txt.example` → `apikey.txt` (đã gitignore) và điền key của bạn,
  hoặc export biến môi trường tương ứng.
- Key bắt buộc: `VALSEA_API_KEY`. Tuỳ chọn: ElevenLabs (sinh audio test +
  giọng dự phòng), Twilio (mode gọi số thật), Brevo (email xác nhận),
  notify token (CRM lookup — thiếu thì tự fallback data local).
- `apikey.txt` không bao giờ được commit/đọc vào chat/in log/gửi xuống
  browser; mọi call VALSEA đi qua backend. Dữ liệu khách trong
  `app/telephony/crm.py` là **demo giả** (email/SĐT dạng example).

## ▶️ Chạy nhanh

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements.txt --python .venv/bin/python
cp apikey.txt.example apikey.txt   # rồi điền key thật
.venv/bin/python -m uvicorn app.main:app --port 8321
# mở http://localhost:8321 (4 màn) · http://localhost:8321/call (outbound call)
```
