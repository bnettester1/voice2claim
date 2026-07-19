"""Canh VALSEA TTS hồi phục → prewarm toàn bộ câu kịch bản + câu ĐỘNG demo.

Chạy nền: .venv/bin/python scripts/warm_tts.py
Poll 60s/lần; khi VALSEA TTS sống lại thì synth-cache (giọng valsea-female):
- mọi câu tĩnh của 2 pack gọi + 3 câu filler
- 6 câu ĐỘNG của kho demo (lookup_found + status_reply cho 3 khách local)
→ demo gọi thật đồng nhất 100%% giọng VALSEA kể cả câu đọc hồ sơ.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.core import valsea
from app.packs.loader import load_all
from app.telephony import crm, tts


def _texts() -> list[str]:
    out: list[str] = list(tts.FILLERS)
    packs = load_all()
    for pack in packs.values():
        if pack.call_script is not None:
            sc = pack.call_script
            out += [sc.greeting, sc.closing, sc.closing_partial]
            for s in sc.steps:
                out += [s.ask, s.reask]
        if pack.call_flows is not None:
            fl = pack.call_flows
            out += [fl.greeting, fl.lookup_wait, fl.lookup_miss, fl.menu_prompt,
                    fl.unknown_intent, fl.ask_more, fl.closing]
            for s in fl.identify:
                out += [s.ask, s.reask]
            for it in fl.intents:
                out.append(it.empathy)
                for s in it.steps:
                    out += [s.ask, s.reask]
            # câu ĐỘNG khả dĩ của kho demo local (đếm được → cache trước)
            for cust in crm._LOCAL_CUSTOMERS:
                handler = crm._LOCAL_HANDLERS.get(crm.claim_type_of(cust))
                out.append(fl.lookup_found_tpl.replace(
                    "{summary}", crm.profile_summary(cust)))
                for it in fl.intents:
                    if it.reply_tpl:
                        out.append(crm.status_reply(it.reply_tpl, cust, handler))
    return [t for t in dict.fromkeys(out) if t]


async def main() -> None:
    texts = _texts()
    print(f"[warm_tts] {len(texts)} câu cần cache — chờ VALSEA TTS hồi phục…")
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            try:
                await valsea.tts("Kiểm tra.", client=client)
                print("[warm_tts] VALSEA TTS ĐÃ SỐNG — bắt đầu prewarm")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[warm_tts] chưa sống ({str(exc)[:60]}) — thử lại sau 60s")
                await asyncio.sleep(60)
        done = 0
        for t in texts:
            t0 = time.time()
            try:
                _, _, vendor = await tts.synth(t, "twilio", client)
                done += 1
                print(f"[warm_tts] {done}/{len(texts)} {vendor} {time.time()-t0:.1f}s  {t[:46]}")
            except Exception as exc:  # noqa: BLE001
                print(f"[warm_tts] LỖI {str(exc)[:60]}  {t[:46]}")
            await asyncio.sleep(0.3)
    print(f"[warm_tts] XONG — {done}/{len(texts)} câu giọng VALSEA trong cache")


if __name__ == "__main__":
    asyncio.run(main())
