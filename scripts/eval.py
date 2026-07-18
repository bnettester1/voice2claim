"""Eval engine vs gold labels (KB A–F + testcase mở rộng).

Text-mode:  .venv/bin/python scripts/eval.py
Audio-mode: .venv/bin/python scripts/eval.py --audio   (cần assets/audio/*.wav — task P3a)

Chấm:
- Field text/textarea: token_set_ratio(normalize) ≥ 75.
- Field list: TỪNG mục gold phải khớp 1 mục extracted (≥75); biển số so exact alnum.
- Field enum: bằng nhau sau normalize.
- Action: gold action phải được arm khi scan_full; action khác KHÔNG được arm (false positive).
Ghi docs/product/scorecard.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from rapidfuzz import fuzz

from app.core.extraction import extract
from app.core.form_state import FormStore
from app.core.triggers import TriggerMatcher, normalize_vi
from app.packs.loader import load_all

CASE_FILES = [ROOT / "packs" / "testcases" / "kb_af.json",
              ROOT / "packs" / "testcases" / "extended_gj.json"]
AUDIO_DIR = ROOT / "assets" / "audio"
SCORECARD = ROOT / "docs" / "product" / "scorecard.md"

PLATE_RE = re.compile(r"\d{2}[-\s]?[A-Za-z]{1,2}\d?[-\s]?\d{3}[.\s]?\d{2}")
_UNIT_COLLAPSE = re.compile(r"(\d)\s+(mg|mcg|g|ml|mmol|mmhg|%)", re.IGNORECASE)


def _norm(s: str) -> str:
    """normalize_vi + gộp '5 mg'→'5mg' để so công bằng đơn vị liều."""
    return normalize_vi(_UNIT_COLLAPSE.sub(r"\1\2", str(s)))


def norm_plate(s: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", s.upper())


def has_plate(s: str) -> bool:
    return bool(PLATE_RE.search(s or ""))


def match_scalar(gold: str, got) -> bool:
    if got is None:
        return False
    got_s = str(got)
    if has_plate(str(gold)):
        gp = PLATE_RE.search(str(gold)).group()
        return norm_plate(gp) in norm_plate(got_s)
    return fuzz.token_set_ratio(_norm(gold), _norm(got_s)) >= 75


def match_list(gold_items: list, got) -> tuple[int, int]:
    if not isinstance(got, list):
        got = [got] if got not in (None, "") else []
    got_s = [str(x) for x in got]
    hit = 0
    for g in gold_items:
        ok = False
        for x in got_s:
            if has_plate(str(g)):
                gp = PLATE_RE.search(str(g)).group()
                base = normalize_vi(re.sub(re.escape(gp), " ", str(g)))
                plate_ok = norm_plate(gp) in norm_plate(x)
                text_ok = (not base.strip()) or fuzz.token_set_ratio(base, _norm(x)) >= 60
                ok = plate_ok and text_ok
            else:
                ok = fuzz.token_set_ratio(_norm(g), _norm(x)) >= 75
            if ok:
                break
        hit += int(ok)
    return hit, len(gold_items)


async def run_case(case: dict, packs, client, audio_variant: str = "") -> dict:
    """audio_variant: '' = text-mode; 'clean'|'noisy'|'telephony' = ASR trước."""
    from app.core import valsea

    pack = packs[case["pack_id"]]
    transcript, asr_ms = case["transcript"], 0
    if audio_variant:
        suffix = "" if audio_variant == "clean" else f"_{audio_variant}"
        wav = AUDIO_DIR / f"{case['id']}{suffix}.wav"
        if not wav.exists():
            return {"id": case["id"], "variant": audio_variant, "skipped": True}
        t0 = time.monotonic()
        verbose = await valsea.transcribe(wav.read_bytes(), wav.name, client=client)
        asr_ms = int((time.monotonic() - t0) * 1000)
        from app.core.normalize import apply_itn
        transcript = apply_itn(pack, verbose.get("text") or "")
    case = {**case, "transcript_used": transcript}
    t0 = time.monotonic()
    extraction = await extract(pack, transcript, client=client)
    extract_ms = int((time.monotonic() - t0) * 1000)

    store = FormStore(pack)
    store.merge(extraction)
    values = store.snapshot()

    field_hits, field_total, misses = 0, 0, []
    for name, gold in case["gold_fields"].items():
        got = values.get(name)
        if isinstance(gold, list):
            h, t = match_list(gold, got)
            field_hits += h
            field_total += t
            if h < t:
                misses.append(f"{name}: {h}/{t} (got={got})")
        else:
            field_total += 1
            if match_scalar(gold, got):
                field_hits += 1
            else:
                misses.append(f"{name}: gold='{gold}' got='{got}'")

    matcher = TriggerMatcher(pack)
    t0 = time.perf_counter()
    events = matcher.scan_full(transcript)
    trig_ms = (time.perf_counter() - t0) * 1000
    armed = {e.action.id for e in events if e.kind == "armed"}
    gold_actions = set(case["gold_actions"])
    action_ok = gold_actions <= armed
    false_pos = armed - gold_actions

    return {
        "id": case["id"], "title": case["title"], "pack": pack.id,
        "variant": audio_variant or "text",
        "field_hits": field_hits, "field_total": field_total,
        "misses": misses, "action_ok": action_ok,
        "false_pos": sorted(false_pos), "armed": sorted(armed),
        "asr_ms": asr_ms, "extract_ms": extract_ms, "trig_ms": round(trig_ms, 2),
        "passed": field_hits == field_total and action_ok and not false_pos,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", action="store_true", help="chạy qua VALSEA ASR từ assets/audio")
    ap.add_argument("--variants", default="clean",
                    help="audio-mode: clean,noisy,telephony (bỏ qua nếu thiếu file)")
    ap.add_argument("--only", default="", help="chỉ chạy các case id, vd A,B")
    args = ap.parse_args()

    packs = load_all()
    cases = []
    for f in CASE_FILES:
        if f.exists():
            cases += json.loads(f.read_text(encoding="utf-8"))["cases"]
    if args.only:
        keep = {x.strip().upper() for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in keep]

    variants = [v.strip() for v in args.variants.split(",") if v.strip()] if args.audio else [""]

    async with httpx.AsyncClient(timeout=180) as client:
        results = []
        for c in cases:  # tuần tự — tránh 429 rate-limit
            for v in variants:
                try:
                    r = await run_case(c, packs, client, audio_variant=v)
                except Exception as e:  # noqa: BLE001 — mạng đứt giữa chừng vẫn ghi scorecard
                    print(f"[CRASH] {c['id']}/{v or 'text'}: {str(e)[:120]}")
                    results.append({"id": c["id"], "title": c["title"],
                                    "pack": c["pack_id"], "variant": v or "text",
                                    "field_hits": 0,
                                    "field_total": len(c["gold_fields"]),
                                    "misses": [f"CRASH: {str(e)[:80]}"],
                                    "action_ok": False, "false_pos": [], "armed": [],
                                    "asr_ms": 0, "extract_ms": 0, "trig_ms": 0,
                                    "passed": False})
                    continue
                if r.get("skipped"):
                    continue
                results.append(r)
                print(f"[{ 'PASS' if r['passed'] else 'FAIL' }] {r['id']}/{r['variant']}: "
                      f"fields {r['field_hits']}/{r['field_total']}, "
                      f"action={'ok' if r['action_ok'] else 'MISS'}, fp={r['false_pos']}, "
                      f"asr={r['asr_ms']}ms extract={r['extract_ms']}ms trigger={r['trig_ms']}ms")
                for m in r["misses"]:
                    print(f"       miss → {m}")

    mode = "audio-mode (VALSEA ASR)" if args.audio else "text-mode"
    lines = [f"# Scorecard — eval {mode}", "",
             "| Case | Variant | Pack | Fields | Action | FalsePos | ASR | Extract | KQ |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    n_pass = 0
    for r in results:
        n_pass += int(r["passed"])
        lines.append(
            f"| {r['id']} {r['title'][:26]} | {r['variant']} | {r['pack']} "
            f"| {r['field_hits']}/{r['field_total']} "
            f"| {'✅' if r['action_ok'] else '❌'} | {','.join(r['false_pos']) or '—'} "
            f"| {r['asr_ms']}ms | {r['extract_ms']}ms | {'✅ PASS' if r['passed'] else '❌ FAIL'} |")
    total_fields = sum(r["field_total"] for r in results)
    hit_fields = sum(r["field_hits"] for r in results)
    lines += ["", f"**Tổng: {n_pass}/{len(results)} case PASS · field-level "
                  f"{hit_fields}/{total_fields} ({100*hit_fields/max(1,total_fields):.0f}%)**"]
    SCORECARD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n== {n_pass}/{len(results)} PASS · fields {hit_fields}/{total_fields} ==  → {SCORECARD}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
