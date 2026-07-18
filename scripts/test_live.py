"""E2E test live mode KHÔNG cần mic: stream assets/audio/<ID>.wav qua
/ws/live/<pack> như browser thật (frame 3200B/100ms, hơi nhanh hơn realtime),
in các event nhận được + số liệu chốt.

Dùng:  .venv/bin/python scripts/test_live.py [A] [--speed 3]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import websockets

FRAME = 3200  # 100ms PCM16 16k mono


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case", nargs="?", default="A")
    ap.add_argument("--speed", type=float, default=3.0, help="x realtime")
    ap.add_argument("--host", default="localhost:8321")
    ap.add_argument("--record", action="store_true",
                    help="ghi events → assets/replay/<ID>.json (replay mode UI)")
    args = ap.parse_args()

    case = args.case.upper()
    pack = "insurance_motor" if case in "ABCGH" else "healthcare_exam"
    wav_path = ROOT / "assets" / "audio" / f"{case}.wav"
    with wave.open(str(wav_path), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        pcm = w.readframes(w.getnframes())
    dur = len(pcm) / 2 / 16000
    print(f"▶ stream {wav_path.name} ({dur:.0f}s audio, tốc độ {args.speed}x) → /ws/live/{pack}")

    stats = {"partial": 0, "final": 0, "patch_fields": set(), "armed": {}, "fired": [],
             "results": [], "score": None, "saved_sid": None, "errors": [],
             "last_activity": time.monotonic()}
    recorded: list[dict] = []
    t0 = time.monotonic()

    async with websockets.connect(f"ws://{args.host}/ws/live/{pack}", max_size=2**22) as ws:

        async def sender():
            for i in range(0, len(pcm), FRAME):
                await ws.send(pcm[i:i + FRAME])
                await asyncio.sleep(0.1 / args.speed)
            # chờ VALSEA xử lý hết (không final/partial mới trong 8s, tối đa 120s)
            waited = 0.0
            while waited < 120:
                await asyncio.sleep(1)
                waited += 1
                if time.monotonic() - stats["last_activity"] > 8:
                    break
            await ws.send(json.dumps({"type": "mic.stop"}))
            await asyncio.sleep(5)  # chờ extraction cuối + action result
            await ws.send(json.dumps({"type": "session.end"}))

        async def receiver():
            try:
                async for raw in ws:
                    ev = json.loads(raw)
                    t = ev.get("type")
                    dt = time.monotonic() - t0
                    if args.record:
                        recorded.append({"dt": round(dt, 3), "ev": ev})
                    if t in ("transcript.partial", "transcript.final"):
                        stats["last_activity"] = time.monotonic()
                    if t == "session.ready":
                        print(f"[{dt:5.1f}s] READY hint={ev.get('hint_chars')} ký tự")
                    elif t == "transcript.partial":
                        stats["partial"] += 1
                        if stats["partial"] % 10 == 1:
                            print(f"[{dt:5.1f}s] partial#{stats['partial']}: {ev['text'][:60]}…")
                    elif t == "transcript.final":
                        stats["final"] += 1
                        print(f"[{dt:5.1f}s] FINAL#{stats['final']}: {ev['text'][:80]}")
                    elif t == "state.patch":
                        stats["patch_fields"].update(ev["fields"].keys())
                        print(f"[{dt:5.1f}s] PATCH rev{ev['rev']}: {list(ev['fields'])}")
                    elif t == "score.update":
                        stats["score"] = (ev["total"], ev["grade"])
                    elif t == "action.armed":
                        stats["armed"][ev["action"]] = ev["arm_latency_ms"]
                        print(f"[{dt:5.1f}s] ⚡ ARMED {ev['action']} score={ev['score']} latency={ev['arm_latency_ms']}ms")
                    elif t == "action.fired":
                        stats["fired"].append(ev["action"])
                        print(f"[{dt:5.1f}s] 🔥 FIRED {ev['action']}")
                    elif t == "action.result":
                        stats["results"].append(ev["ticket"]["id"])
                        print(f"[{dt:5.1f}s] ✅ RESULT {ev['ticket']['id']} pdf={ev['pdf_url']} tts={'yes' if ev.get('tts_b64') else 'no'}")
                    elif t == "session.saved":
                        stats["saved_sid"] = ev["sid"]
                        print(f"[{dt:5.1f}s] 💾 session.saved sid={ev['sid']}")
                    elif t in ("status", "error"):
                        stats["errors"].append(ev)
                        print(f"[{dt:5.1f}s] {t.upper()}: {ev}")
            except websockets.ConnectionClosed:
                pass

        await asyncio.gather(sender(), receiver())

    if args.record and recorded:
        rp_dir = ROOT / "assets" / "replay"
        rp_dir.mkdir(parents=True, exist_ok=True)
        rp = rp_dir / f"{case}.json"
        rp.write_text(json.dumps({"case": case, "pack": pack, "events": recorded},
                                 ensure_ascii=False), encoding="utf-8")
        print(f"💾 replay ghi → {rp} ({rp.stat().st_size//1024}KB, {len(recorded)} events)")

    print("\n== KẾT QUẢ LIVE ==")
    print(f"partials={stats['partial']} finals={stats['final']} "
          f"fields_patched={sorted(stats['patch_fields'])}")
    print(f"armed={stats['armed']} fired={stats['fired']} tickets={stats['results']}")
    print(f"score={stats['score']} saved_sid={stats['saved_sid']}")
    ok = (stats["partial"] > 0 and stats["final"] > 0 and stats["patch_fields"]
          and stats["armed"] and stats["saved_sid"])
    print("== PASS ==" if ok else "== FAIL ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
