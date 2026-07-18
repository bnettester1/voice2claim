"""FlowAgent (E10) — tổng đài đa-workflow theo pack.call_flows.

Vòng đời: greeting → IDENTIFY (tên + số cuối CCCD) → LOOKUP hồ sơ (notify REST
/ kho local, xác thực đuôi CCCD) → đọc tổng quan hồ sơ → nghe yêu cầu tự do →
INTENT ROUTER (keyword fuzzy, không LLM) → workflow tương ứng:
  - claim_status: trả lời từ hồ sơ (trạng thái/người phụ trách/ETA)
  - new_claim  : hỏi các field CÒN TRỐNG (extraction đã điền được gì thì bỏ
    qua — "AI tự quyết câu hỏi") → xác nhận → ticket + PDF + email nhân sự/khách
→ hỏi thêm → closing. Mọi lượt nói đều vào transcript + WAV recording.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from app.core.triggers import normalize_vi
from app.packs.loader import IntentSpec
from app.telephony.agent import CallEnded, ScriptedAgent

_NO_MORE = ("khong", "thoi", "het roi", "cam on", "khong can", "du roi",
            "vay thoi", "bye", "tam biet")


def route_intent(intents: list[IntentSpec], heard: str) -> IntentSpec | None:
    """Chọn workflow theo keyword — substring trước, fuzzy partial sau."""
    n = normalize_vi(heard)
    if not n:
        return None
    best, best_score = None, 0.0
    for it in intents:
        score = 0.0
        for kw in it.keywords:
            k = normalize_vi(kw)
            if not k:
                continue
            if k in n:
                score += 100 + len(k)          # khớp nguyên cụm — mạnh nhất
            else:
                r = fuzz.partial_ratio(k, n)
                if r >= 85:
                    score += r / 2
        if score > best_score:
            best, best_score = it, score
    return best if best_score >= 60 else None


class FlowAgent(ScriptedAgent):
    def _is_no_more(self, heard: str) -> bool:
        n = f" {normalize_vi(heard)} "
        return any(f" {kw}" in n for kw in _NO_MORE)

    async def _handle_intent(self, intent: IntentSpec, fl) -> None:
        e = self.e
        e.emit({"type": "intent", "id": intent.id, "label": intent.label})

        if intent.reply_tpl:                      # tra cứu từ hồ sơ
            from app.telephony import crm
            if e.cust:
                await e.say(crm.status_reply(intent.reply_tpl, e.cust, e.handler))
            else:
                await e.say("Dạ em chưa tìm thấy hồ sơ để tra cứu ngay, em sẽ "
                            "chuyển bộ phận nghiệp vụ kiểm tra và gọi lại "
                            "cho mình trong hôm nay ạ.")

        if intent.empathy:
            await e.say(intent.empathy)

        for idx, step in enumerate(intent.steps):
            fs = e.store.fields.get(step.field)
            if fs is not None and fs.value not in (None, "", []):
                e.emit_step(idx, step.field, "filled")   # đã bắt được từ lời kể
                continue
            await self._do_step(idx, step, fl.reask_after_secs)

        if intent.confirm_tpl:
            await e.say(intent.confirm_tpl.replace("{summary}",
                                                   e.fields_summary()))
            heard = await self._listen(6)
            if heard is not None and self._is_no_more(heard) is False:
                await e.collect_free(heard)       # khách bổ sung phút chót
        if intent.action:
            await e.fire_flow_action(intent)

    async def run(self) -> None:
        fl = self.e.pack.call_flows
        served = False
        try:
            await self.e.say(fl.greeting)
            for idx, step in enumerate(fl.identify):
                await self._do_step(idx, step, fl.reask_after_secs)
            if fl.lookup_wait:
                await self.e.say(fl.lookup_wait)
            found = await self.e.crm_lookup()
            if found:
                from app.telephony import crm
                await self.e.say(fl.lookup_found_tpl.replace(
                    "{summary}", crm.profile_summary(self.e.cust)))
            else:
                await self.e.say(fl.lookup_miss or fl.menu_prompt)

            pending: str | None = None
            for _turn in range(4):                # tối đa 4 lượt yêu cầu/cuộc
                heard = pending or await self._listen(fl.reask_after_secs + 4)
                pending = None
                if heard is None:
                    if served:
                        break
                    await self.e.say(fl.menu_prompt or fl.unknown_intent)
                    heard = await self._listen(fl.reask_after_secs + 4)
                    if heard is None:
                        break
                await self.e.collect_free(heard)  # ghi yeu_cau + extract field
                intent = route_intent(fl.intents, heard)
                if intent is None:
                    if served or self._is_no_more(heard):
                        break                      # "thôi cảm ơn em" → chốt máy
                    await self.e.say(fl.unknown_intent)
                    continue
                await self._handle_intent(intent, fl)
                served = True
                if fl.ask_more:
                    await self.e.say(fl.ask_more)
                    more = await self._listen(7)
                    if more is None or self._is_no_more(more):
                        break
                    pending = more
            await self.e.say(fl.closing)
            await self.e.hangup_done("hoàn tất cuộc gọi" if served
                                     else "khách không có yêu cầu")
        except CallEnded:
            await self.e.hangup_done("khách cúp máy", hungup=True)
        except Exception as exc:  # noqa: BLE001
            self.e.emit({"type": "error", "code": "flow_agent",
                         "message": str(exc)[:150]})
            await self.e.hangup_done("lỗi flow")
