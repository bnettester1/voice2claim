# Voice2Claim — Speech-to-Meaning · VALSEA Hackathon 2026

> **"Từ Giọng Nói Đến Hành Động"** — biến hội thoại tiếng Việt thật (code-switch
> Việt–Anh, giọng vùng miền, nhiễu nền) thành **Action Form đúng chuẩn ngành +
> Action Call thực thi thật**, không dừng ở transcript.

## Ý tưởng trong 30 giây

Một **engine ngang** + **kho từ điển nghiệp vụ cắm-rút (Domain Pack)**.
Doanh nghiệp tích hợp chỉ cần cung cấp một file từ điển nghiệp vụ (schema form,
catalog action call, thuật ngữ ngành, luật chuẩn hóa) — engine tự thích nghi:

```
Giọng nói ─► VALSEA ASR (batch + realtime, hint_text từ từ điển)
          ─► Semantic Engine local (rule + semantic_tags VALSEA + PyTorch NER
              — không LLM ngoài, ~200ms, không rate-limit)
          ─► Action Form điền dần (confidence từng field)
          ─► Action Call: PDF chuẩn ngành + ticket hệ lõi + TTS xác nhận
```

Pilot chạy 2 vertical: 🛡️ **Bảo hiểm** (giám định tai nạn xe) và 🩺 **Y tế**
(khám ngoại trú: nghiệp vụ chung + tiêu hóa, chấn thương chỉnh hình, tim mạch)
— đổi bằng một nút switcher, cùng một engine.

## 🎙️ Voice2Claim — nền tảng vận hành (E12)

Từ pilot giọng nói, hệ đã nâng thành **mini CRM/ERP + workflow platform** cho
công ty bảo hiểm — mở `http://localhost:8321/` là vào shell sidebar:

- **Tổng quan** — KPI vận hành + **AI Decision Feed** (mọi quyết định của AI
  Điều hành: định tuyến, chấm rủi ro kèm lý do, giao việc, autocall, email).
- **CRM** — khách hàng 360 (hợp đồng, claim, tương tác, timeline) trên SQLite
  `data/app.db` (tự migrate + seed khi khởi động; reset: `python scripts/init_db.py --reset`).
- **Công việc** — hộp việc theo vai (CSR / thẩm định viên / giám đốc — đổi vai
  góc dưới sidebar); hoàn tất việc là workflow tự chạy tiếp.
- **Flows** — workflow lưu & version hoá trong DB, sơ đồ trực quan, editor JSON
  + bảng chất lượng theo version (flywheel: ★ khách qua email, ★ nhân sự,
  auto-metrics, Qwen judge async):
  - 📄 **Mở hợp đồng**: intake (voice-prefill + ảnh xe) → AI thẩm định rule-based
    → hợp đồng PDF → **ký điện tử qua email** → kích hoạt → **autocall** + mail.
  - 🚗 **Claim tai nạn**: cuộc gọi E10 tự điền form → mở claim → thẩm định viên
    đi hiện trường (upload ghi âm/ảnh) → **VALSEA bóc băng → biên bản PDF** →
    giám đốc duyệt → chi trả/từ chối + autocall + mail.
- **Kho tri thức** — upload tài liệu nghiệp vụ → Qwen bóc tách thành workflow
  nháp → promote vào Flows (offline/async, decision 0012/0013 — không chạy
  trên đường gọi).
- AI ngoài cuộc gọi: `POST /api/wf/dispatch {"text": "xe tôi bị đâm…"}` — cùng
  keyword router của tổng đài, trả về workflow được chọn + lý do khớp.

Hồ sơ: [PLAN-E12-insurance-os.md](PLAN-E12-insurance-os.md) ·
[decision 0013](docs/decisions/0013-platform-db-workflow-engine.md) ·
[epic E12](docs/stories/epics/E12-insurance-os/).

## Tài liệu

| Tài liệu | Nội dung |
| --- | --- |
| [docs/product/overview.md](docs/product/overview.md) | Product contract, tiêu chí chấm, deliverables |
| [docs/product/architecture.md](docs/product/architecture.md) | Kiến trúc đầy đủ (mermaid), spec VALSEA API, thiết kế realtime, PyTorch layer, bậc thang degrade |
| [docs/product/domain-packs.md](docs/product/domain-packs.md) | Schema từ điển nghiệp vụ, phạm vi 2 pack, bộ test case A–J |
| [docs/product/demo.md](docs/product/demo.md) | Kịch bản demo 4 màn + đặc tả UI |
| [docs/product/mockup/](docs/product/mockup/) | Mockup giao diện (mở bằng browser) |
| [docs/stories/backlog.md](docs/stories/backlog.md) | Epic/story backlog |
| [docs/decisions/0008-pilot-stack-and-scope.md](docs/decisions/0008-pilot-stack-and-scope.md) | Các quyết định kiến trúc đã chốt |

Repo dùng [repository-harness](https://github.com/hoangnb24/repository-harness)
làm lớp vận hành agent-ready (AGENTS.md, product docs, stories, decisions,
harness-cli). Xem `AGENTS.md` để bắt đầu.

## Chạy

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements.txt --python .venv/bin/python   # core
uv pip install -r requirements-ml.txt --python .venv/bin/python # PyTorch layer (VAD + NER) — tùy chọn
# đặt apikey.txt ở repo root (KHÔNG commit — đã gitignore)
.venv/bin/python -m uvicorn app.main:app --port 8321
# mở http://localhost:8321
```

**4 chế độ trên UI:** 📁 Xử lý ghi âm (upload/ghi âm/chip audio mẫu A–J) ·
📞 Live Call (mic streaming RTT, form điền real-time) · ✅ Duyệt & Chấm điểm
(FormScorer + gate gửi) · 🗄️ Core System Console (ticket + webhook log).
**Replay chips** trong tab Live phát lại bản ghi thật không cần mạng/credits.

## ☎️ Agent Call — E8 gọi ra bổ sung hợp đồng · E10 tổng đài gọi vào

Trang **`/call`**: tổng đài viên AI **gọi ra**, hỏi các thông tin còn thiếu
của hợp đồng bảo hiểm theo kịch bản trong pack `insurance_contract`, nghe
khách trả lời (VALSEA RTT + correction + ITN), điền form dần, đủ thì gửi
ticket + PDF. **Đường cuộc gọi toàn VALSEA, không LLM ngoài**: giọng agent là
VALSEA TTS (transcode μ-law cho Twilio; ElevenLabs chỉ là dự phòng), còn câu
trả lời được hiểu bằng parser rule field-aware (`app/telephony/parse_vi.py`
— số đọc chữ → chữ số, ngày sinh, CCCD, biển số, địa chỉ; 0ms, không
rate-limit). Câu kịch bản được pre-synthesize + cache.

3 mode (bậc thang degrade — demo không bao giờ chết):

| Mode | Cần gì | Dùng khi |
| --- | --- | --- |
| 🔁 **Replay** | không cần telephony (key VALSEA để có giọng nói) | demo an toàn — đã verify end-to-end: 4/4 field + ticket + PDF |
| 🎧 **Browser** | mic/loa trình duyệt + key VALSEA | bạn đóng vai khách nói thật, không cần telephony |
| ☎️ **Twilio** | 4 biến dưới + tunnel public | gọi số điện thoại thật |

Runbook bật mode Twilio:

```bash
# 1. Tunnel public về server local (chọn 1):
ngrok http 8321                      # hoặc: cloudflared tunnel --url http://localhost:8321
# 2. Thêm vào apikey.txt (hoặc export env) — KHÔNG commit:
#    TWILIO_ACCOUNT_SID=ACxxxx  TWILIO_AUTH_TOKEN=xxxx
#    TWILIO_FROM_NUMBER=+1xxxx  PUBLIC_BASE_URL=https://<tunnel-domain>
# 3. Restart server, mở /call → nút "Gọi số thật" sáng, nhập số E.164 (+84…)
```

Lưu ý Twilio trial: chỉ gọi được số đã verify trong console, có câu thông báo
trial ở đầu cuộc gọi; Twilio không bán số +84 — gọi đi VN tính cước quốc tế.
Webhook được validate `X-Twilio-Signature`; số điện thoại mask trong log.
Test offline: `.venv/bin/python scripts/test_telephony.py` (49 test: codec
μ-law/resample, TwiML/chữ ký, agent state machine, parser field-aware,
intent router + CRM lookup của E10).

**Chiều gọi thật khuyến nghị: INBOUND (E10, decision 0011).** Trial outbound
bắt người nghe bấm phím trong lúc câu thông báo trial phát — nhà mạng VN
thường nuốt DTMF nên chiều gọi ra dễ tắc. Khách **gọi vào** số Twilio thì
không cần keypress: trỏ VoiceUrl của số về
`{PUBLIC_BASE_URL}/telephony/inbound` — bot tổng đài (pack
`insurance_callcenter`) xác thực → tra hồ sơ → nhận yêu cầu → ticket + email
+ ghi âm. Tunnel đổi URL thì phải cập nhật **cả VoiceUrl** (không chỉ env).
Trước demo: chạy `scripts/warm_tts.py` để prewarm giọng (câu tĩnh + filler +
câu động của kho demo).

## Kiểm chứng & công cụ

| Lệnh | Việc |
| --- | --- |
| `.venv/bin/python scripts/probe.py` | Probe 3 API (không in key) → docs/product/probe-report.md |
| `.venv/bin/python scripts/eval.py` | Eval text-mode 10 kịch bản vs gold KB |
| `.venv/bin/python scripts/eval.py --audio --variants clean,noisy,telephony` | Eval audio qua VALSEA ASR → docs/product/scorecard.md |
| `.venv/bin/python scripts/gen_test_audio.py --variants` | Sinh bộ audio test (ElevenLabs flash_v2_5 vi + nhiễu + telephony) |
| `.venv/bin/python scripts/test_live.py A --record` | E2E live qua RTT + ghi bản replay |

Số đo đã kiểm chứng trên máy thật: RTT session.ready **1.1–1.4s**, trigger arm
trên partial **0.2–0.3ms** (đích <500ms), form điền dần từ giây thứ ~9 của cuộc
gọi, batch VALSEA warm ~10–14s (cold 122s → runbook warm-up). Chi tiết:
[scorecard](docs/product/scorecard.md) · [probe report](docs/product/probe-report.md)
· [runbook demo](docs/product/demo.md).

## Bảo mật

`apikey.txt` (VALSEA / ElevenLabs) **không bao giờ** được commit, đọc
vào chat, in ra log hay gửi xuống browser. Mọi call VALSEA đi qua backend.
Pilot không dùng LLM ngoài (Groq đã gỡ — decision 0010).
