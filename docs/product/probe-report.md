# P0 Probe Report

Tổng: **8/9 OK**

| Probe | KQ | Latency | Ghi chú |
| --- | --- | --- | --- |
| ElevenLabs voices | OK | 5160ms | 21 voices |
| ElevenLabs TTS vi | OK | 9548ms | probe.wav 195KB |
| VALSEA transcribe | OK | 31008ms | text='Xin chào, tôi tên Tuấn. Xe tôi là Wave Alpha, biển số 59A-908.7365.' keys=detected_languages,raw_transcript,text |
| VALSEA RTT ws | OK | 1112ms | event=session.ready |
| VALSEA formatting service_log | OK | 1362ms | lang=EN? keys=customer_frustration_level,follow_up_actions,follow_up_required,generated_at,iss |
| VALSEA formatting meeting_minutes | OK | 1433ms | lang=VI keys=action_items,agenda_items,decisions,generated_at,key_discussions,notes,summary,t |
| VALSEA TTS | FAIL | 157ms | Client error '400 Bad Request' for url 'https://api.valsea.ai/v1/audio/speech'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400 |
| Groq LLM json | OK | 898ms | {
  "ten": "Tuấn"
} |
| Groq whisper baseline | OK | 2902ms |  Xin chào tôi Tên Tuan, Chết tôi là Wave Alpha, Biến xuân âm chín á chín trầm tâ |

> **Fix sau probe:** VALSEA TTS OK sau khi đổi `voice=valsea-female` + `response_format=wav` (8191ms, 125KB) — voices hợp lệ: valsea-neutral/male/female. Latency TTS ~8s → thiết kế: pre-generate các câu tts_confirm của pack lúc khởi động, cache file, phát tức thì.
> **Insight:** transcribe trả ITN sẵn nhưng sai số (59A-908.7365 vs gold 987.65) → hint_text/ITN rules là chỗ ghi điểm; formatting meeting_minutes=TIẾNG VIỆT, service_log=EN; whisper baseline nát tiếng Việt → side-by-side thắng rõ.
