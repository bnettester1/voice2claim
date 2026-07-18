# Design — E8 Outbound Agent Call

## Domain Model

- `Pack insurance_contract`: form 2 section — "Hợp đồng (hồ sơ gốc)" (prefill,
  read-only trên UI) và "Thông tin cần bổ sung" (field thiếu, required).
- `CallScriptSpec` (mới trong `packs/loader.py`): `greeting`, `closing`,
  `steps[{field, ask, reask, confirm_tpl}]`, `no_answer_reask_secs`. Kịch bản
  nằm TRONG pack — đúng triết lý domain pack.
- `CallSession`: id hex ngẫu nhiên (đóng vai token WS), pack, FormStore,
  transcript agent+khách, trạng thái máy `dialing→greeting→ask(field)→
  listen→confirm→…→closing→done`.

## Application Flow

```
UI POST /call/start {mode, phone?, customer}
  → tạo CallSession + warm TTS cache (câu kịch bản static)
  → mode twilio : Twilio REST Calls.json (Url=/telephony/twiml?sid=…)
       Twilio → GET/POST twiml → <Connect><Stream url=wss…/ws/twilio/{sid}>
       Twilio WS media (μ-law 8k b64) → decode → PCM16 16k → CallEngine
       CallEngine.speak() → ElevenLabs ulaw_8000 → media frames + mark → Twilio
  → mode browser: trang mở WS /ws/call/browser/{sid} gửi PCM16 16k binary
       (tái dùng pcm_worklet.js); agent audio trả JSON {tts.audio mp3 b64}
  → mode replay : ReplayTransport bơm transcript.final canned theo nhịp
CallEngine (chung cho 3 mode):
  audio PCM16 → VALSEA wss /v1/realtime (hint_text pack) + silero-VAD commit
  transcript.final → extract() (Groq, fallback regex validator pack)
  → FormStore.merge → monitor emit; agent máy trạng thái quyết định câu nói kế
  đủ required → execute_action(ticket) → closing → hangup (REST) → done
UI WS /ws/callmon/{sid}: nhận call.state / transcript hai chiều / state.patch /
  score.update / ticket — trang chỉ việc render.
```

## Interface Contract

- `POST /call/start` → `{sid, mode}`; 400 khi mode twilio mà thiếu creds.
- `GET|POST /telephony/twiml?sid=` → TwiML XML; validate `X-Twilio-Signature`
  khi có auth token (lenient scheme http/https cho tunnel).
- `POST /telephony/status?sid=` → 204; cập nhật call.state.
- `WS /ws/twilio/{sid}`: Twilio Media Streams protocol (connected/start/media/
  mark/stop; gửi lại media/mark/clear).
- `WS /ws/call/browser/{sid}`: binary PCM16 16k + JSON `mic.stop`; nhận
  `tts.audio`, `call.state`.
- `WS /ws/callmon/{sid}`: chỉ đọc, JSON events như trên.

## Data Model

In-memory `CALLS: dict[sid, CallSession]` (như SESSIONS batch). Không DB.
Ticket đi vào `ticket_store` hiện có. TTS cache: `assets/tts_cache/` (đã có).

## UI / Platform Impact

Trang mới `/call` (Jinja + Alpine, không build step) — cố ý tối giản: 1 cột
hợp đồng, 1 cột hội thoại + trạng thái; banner mode + nút Gọi. Tái dùng
`app.css` + `pcm_worklet.js`.

## Observability

- Log có cấu trúc mỗi call: sid, mode, arm TTS ms, RTT connect ms, số lượt
  hỏi/re-ask, tổng thời gian; KHÔNG log key/số điện thoại đầy đủ (mask 4 số
  cuối).
- `ticket_store.log` cho hành động ticket như batch/live.

## Alternatives Considered

1. Twilio `<Say>`/`<Gather>` (TwiML IVR có sẵn) — loại: không dùng được VALSEA
   ASR tiếng Việt, mất luận điểm pilot.
2. ElevenLabs Conversational AI (agent trọn gói) — loại: ASR/logic nằm ngoài
   stack VALSEA + không kiểm soát kịch bản form-filling.
3. SDK `twilio` Python — loại: chỉ cần 2 REST call + TwiML string; httpx đủ,
   đỡ dep mới.
