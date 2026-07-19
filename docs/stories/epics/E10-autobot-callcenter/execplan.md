# Exec Plan — E10 Autobot tổng đài đa-workflow

## Goal

Yêu cầu Long 18/07 tối: bot gọi khách, hỏi vấn đề, **từng câu trả lời ghi lại
và qua bộ lọc ra action**, hỏi bộ câu hỏi theo workflow nghiệp vụ, có tương
tác, ưu tiên VALSEA realtime, lookup thông tin khách qua server sau khi
validate, tự gửi email cho nhân sự xử lý + người nhận. 2 case mẫu: tra cứu
tiến độ hồ sơ + tiếp nhận claim mới.

## Scope

In scope: schema `call_flows` (identify/intents/steps/templates trong pack);
pack `insurance_callcenter`; `FlowAgent` + intent router keyword (không LLM —
đúng 0010); CRM client notify REST + fallback kho local + xác thực đuôi CCCD;
ghi âm WAV lời khách (`/rec/{sid}`); action cuối = ticket + PDF + email Brevo
(mailer sẵn có); UI /call chọn kịch bản + panel hồ sơ/intent/mail/ghi âm;
provision hạ tầng Twilio (mua số from bằng trial credit) + cloudflared tunnel.

Out of scope: barge-in; nhiều cuộc song song; NLU thống kê (router = keyword
fuzzy — nâng cấp sau nếu Long duyệt đưa LLM judge trở lại).

## Risk Classification

External systems (Twilio mua số + webhook, Brevo email, notify REST), Public
contracts (payload /call/start mở rộng), Existing behavior (engine/agent E8),
Multi-domain → hard gate external → **high-risk** (intake #4).

## Work Phases

1. Provision: số Twilio +14787588373 (trial credit $15.5), tunnel trycloudflare,
   creds từ ~/.notify.env (Long cấp SID/TOKEN).
2. Schema + pack + CRM + FlowAgent + recording + mail + UI.
3. Proof: unit 49 test + E2E replay 2 lần (lần 1 lộ bug ho_ten bị extraction
   nền đè — đã vá; lần 2 sạch 01:20).
4. Gọi thật +84911961540 — **BLOCKED: apikey.txt bị xoá khi làm export public
   → mất key VALSEA/ElevenLabs, cuộc gọi thật sẽ không có giọng nói. Chờ Long
   khôi phục key rồi bấm gọi (mọi hạ tầng khác đã sẵn).**

## Stop Conditions

- Không gọi số chưa verified (trial); số đích duy nhất: +84911961540.
- Email mặc định về hộp thư của Long (hailongluu@gmail.com / long@luuhailong.com);
  email khách demo @example.com không bao giờ được gửi.
