# Design — E10 Autobot tổng đài

## Application Flow

```
FlowAgent (pack.call_flows):
greeting → IDENTIFY (ho_ten: parse_person_name; cccd_cuoi: parse_digits_tail 6–9)
→ "em đang kiểm tra, đợi giây lát" → CRM LOOKUP:
    crm.lookup_customer(tên) — notify REST GET /customers?query (Bearer
    MCP_AUTH_TOKEN, UA custom né Browser Integrity Check) → fallback kho
    local 3 khách demo; verify_identity = đuôi national_id khớp CCCD khách đọc
    → emit crm.profile (panel UI: khớp CCCD / nguồn / hợp đồng / hồ sơ / handler)
→ đọc profile_summary + menu → nghe câu TỰ DO
→ collect_free: ghi yeu_cau nguyên văn + extraction_local trên toàn hội thoại
   (guard: không đè field đã có confidence cao hơn)
→ route_intent (keyword substring + rapidfuzz partial ≥85, ngưỡng 60 — bộ lọc
   action KHÔNG LLM):
   · claim_status → crm.status_reply(reply_tpl): trạng thái + người phụ trách
     + ETA theo status map
   · new_claim   → empathy → hỏi CHỈ field còn trống trong steps (field đã
     bắt được từ lời kể thì bỏ qua — "AI tự quyết câu hỏi") → confirm summary
     (field + SĐT/email từ hồ sơ) → fire_flow_action:
       execute_action (ticket + PDF, priority CAO khi có thương tích)
       + send_ticket_emails (Brevo): khách + nhân sự xử lý (handler từ CRM
         theo claim_type; guard @example.com → default hộp thư Long)
→ ask_more (vòng tối đa 4 intent/cuộc; "thôi/cảm ơn" → closing) → hangup.
Recording: engine ghi WAV lời khách (PCM16 16k) → out/recordings/{sid}.wav,
đóng file TRƯỚC khi gửi mail để link /rec/{sid} nghe được; link trên UI + email.
```

## Interface Contract

- `POST /call/start` thêm: `pack` (insurance_contract | insurance_callcenter),
  `customer_email`, `handler_email`.
- Monitor WS thêm event: `crm.profile`, `intent`, `mail.status`, `recording`.
- `GET /call?pack=` render kịch bản tương ứng (fields build từ call_script
  hoặc call_flows).

## Hạ tầng gọi thật (đã provision 18/07)

- Twilio trial active, $15.50; số from **+14787588373** (mua qua API, ~$1.15/
  tháng từ credit); số đích verified duy nhất **+84911961540** (của Long).
- `TWILIO_SID`/`TWILIO_TOKEN` (Long cấp), `TWILIO_FROM`, `PUBLIC_BASE_URL`
  (cloudflared quick tunnel → localhost:8322) trong `~/.notify.env`.

## Inbound — đường gọi thật chính (18/07 tối, decision 0011)

- Route `GET/POST /telephony/inbound` (routes.py): validate
  `X-Twilio-Signature` (403) → chọn pack (`?pack=`, mặc định
  `insurance_callcenter`) → dựng `CallEngine(sid, pack, "twilio")`
  on-the-fly → prewarm TTS → trả TwiML `<Connect><Stream>` như outbound.
- VoiceUrl số +14787588373 trỏ `{PUBLIC_BASE_URL}/telephony/inbound`.
  Tunnel đổi URL → cập nhật CẢ VoiceUrl, không chỉ `~/.notify.env`.
- Lý do pivot: trial outbound bắt người nghe bấm phím trong lúc câu thông báo
  trial phát; carrier VN nuốt DTMF (4 cuộc fail cùng chữ ký) — inbound trial
  không cần keypress. Outbound giữ nguyên code làm đường phụ.

## Tối ưu trễ turn (đúc kết cuộc gọi thật với Long)

Phân rã trễ mỗi lượt = VAD 0.8s (giữ) + VALSEA final ~0.3–0.8s +
`ScriptedAgent.GRACE` (cắt 1.2 → **0.7s**) + TTS synth câu ĐỘNG 5–8s
(thủ phạm chính). Fix:

- `engine.say(text, filler=…)`: phát filler ĐÃ CACHE ngay lập tức
  (3 câu trong `tts.FILLERS`), synth câu chính chạy nền song song — áp vào
  lookup_found / status_reply / confirm của FlowAgent.
- `scripts/warm_tts.py` chạy nền poll 60s: VALSEA TTS hồi là prewarm câu tĩnh
  2 pack + filler + 6 câu ĐỘNG demo (lookup_found + status_reply × 3 khách
  kho local — database demo hữu hạn nên pre-synth được).
- `tts.synth` trả `(data, kind, vendor)` + retry VALSEA ×2; VALSEA TTS sập lâu
  (500 hàng loạt) → cờ `TTS_PREFER=elevenlabs` đồng nhất giọng cả cuộc;
  engine cảnh báo "câu dùng giọng dự phòng" lên panel Trạng thái.

## Alternatives Considered

1. LLM intent classifier — loại (0010 không LLM ngoài; Long đang cân nhắc
   riêng cho action-fire, chưa chốt — xem memory).
2. Twilio `<Gather>` IVR — loại như 0009.
3. MCP client trong app để lookup — loại: REST cùng server đơn giản hơn,
   agent-side đã có sẵn 2 cửa.
