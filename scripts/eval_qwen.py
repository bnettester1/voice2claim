"""Eval ĐỐI CHỨNG Qwen 3.5 (chuẩn Anthropic) vs engine local — decision 0012.

So trên bộ gold A–J (field + action, tái dùng luật so khớp của scripts/eval.py)
cộng 4 case phủ định N1q–N4q dựng động từ trigger của pack (tinh thần US-101 —
nhánh main chưa merge negation guard nên local dự kiến dính false-positive;
đây chính là chỗ đo giá trị "LLM judge").

KHÔNG ghi đè docs/product/scorecard.md (bài học backlog #2) — kết quả in
console; muốn lưu thì --report <path.md>.

Chạy:  .venv/bin/python scripts/eval_qwen.py [--model qwen3.5-35b-a3b]
       [--cases A,B,N1q] [--skip-local] [--serial] [--report out.md]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import extraction, llm_qwen          # noqa: E402
from app.core.triggers import TriggerMatcher       # noqa: E402
from app.packs.loader import load_all              # noqa: E402

# tái dùng match_scalar/match_list từ eval.py (nguồn chân lý duy nhất)
_spec = importlib.util.spec_from_file_location("eval_gold", ROOT / "scripts" / "eval.py")
eval_gold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_gold)

TESTFILES = ["packs/testcases/kb_af.json", "packs/testcases/extended_gj.json"]


def load_cases() -> list[dict]:
    cases: list[dict] = []
    for f in TESTFILES:
        cases.extend(json.loads((ROOT / f).read_text())["cases"])
    return cases


def negation_cases(packs: dict) -> list[dict]:
    """4 case phủ định dựng động: trigger có thật nhưng bị 'khoan/đừng/chưa cần'."""
    out: list[dict] = []
    tpl = [
        "Khách: khoan đã em, đừng {t} vội nhé, để tôi hỏi người nhà đã.",
        "Khách: chưa cần {t} đâu em, tôi chỉ hỏi thủ tục trước thôi.",
    ]
    n = 0
    for pid in ("insurance_motor", "healthcare_exam"):
        pack = packs[pid]
        for a in pack.actions[:2]:
            if n >= 4:
                break
            trig = a.triggers[0]
            n += 1
            out.append({
                "id": f"N{n}q", "pack_id": pid,
                "title": f"Phủ định: {a.id}",
                "transcript": tpl[n % 2].format(t=trig),
                "gold_fields": {}, "gold_actions": [],
            })
    return out


def score_fields(case: dict, got: dict) -> tuple[int, int, list[str]]:
    hit, total, misses = 0, 0, []
    for name, gold in case["gold_fields"].items():
        val = (got.get(name) or {}).get("value")
        if isinstance(gold, list):
            h, t = eval_gold.match_list(gold, val)
            hit += h
            total += t
            if h < t:
                misses.append(f"{name} {h}/{t}")
        else:
            total += 1
            if eval_gold.match_scalar(gold, val):
                hit += 1
            else:
                misses.append(f"{name}: gold='{gold}' got='{val}'")
    return hit, total, misses


def score_actions(case: dict, fired: set[str]) -> tuple[bool, set[str]]:
    gold = set(case["gold_actions"])
    return gold <= fired, fired - gold


async def run_case(case: dict, packs: dict, args, sem: asyncio.Semaphore) -> dict:
    pack = packs[case["pack_id"]]
    row: dict = {"id": case["id"], "title": case.get("title", "")[:28]}

    async with sem:
        try:
            q = await llm_qwen.analyze(pack, case["transcript"], model=args.model)
            qh, qt, qmiss = score_fields(case, q["fields"])
            qfired = {a["id"] for a in q["actions"] if a["fire"]}
            qa_ok, qfp = score_actions(case, qfired)
            row.update(q_fields=f"{qh}/{qt}", q_action=qa_ok, q_fp=sorted(qfp),
                       q_ms=q["latency_ms"], q_miss=qmiss[:4],
                       q_reasons={a["id"]: a["reason"] for a in q["actions"] if a["fire"] or a["id"] in case["gold_actions"]})
        except Exception as e:  # noqa: BLE001 — eval phải chạy hết bảng
            row.update(q_fields="ERR", q_action=False, q_fp=[],
                       q_ms=-1, q_err=f"{type(e).__name__}: {e}"[:160])

    if not args.skip_local:
        t0 = time.perf_counter()
        lf = await extraction.extract(pack, case["transcript"])
        l_ms = int((time.perf_counter() - t0) * 1000)
        lh, lt, _ = score_fields(case, lf)
        armed = {ev.action.id for ev in TriggerMatcher(pack).scan_full(case["transcript"])}
        la_ok, lfp = score_actions(case, armed)
        row.update(l_fields=f"{lh}/{lt}", l_action=la_ok, l_fp=sorted(lfp), l_ms=l_ms)
    return row


def fmt_row(r: dict) -> str:
    def act(ok, fp):
        s = "✅" if ok and not fp else ("⚠️FP" if ok else "❌")
        return s + ("(" + ",".join(fp)[:30] + ")" if fp else "")
    q = f"{r.get('q_fields','-'):>7} {act(r.get('q_action'), r.get('q_fp', [])):<14} {r.get('q_ms',-1):>6}ms"
    l = (f"{r.get('l_fields','-'):>7} {act(r.get('l_action'), r.get('l_fp', [])):<14} {r.get('l_ms',-1):>5}ms"
         if "l_fields" in r else " (skip local)")
    return f"{r['id']:>4} | QWEN {q} | LOCAL {l}"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="")
    ap.add_argument("--cases", default="")
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument("--serial", action="store_true")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    if not llm_qwen.ready():
        print("Thiếu QWEN_API/QWEN_BASE — xem apikey.txt")
        return 2

    packs = load_all()
    cases = load_cases() + negation_cases(packs)
    if args.cases:
        want = {c.strip() for c in args.cases.split(",")}
        cases = [c for c in cases if c["id"] in want]

    model_label = args.model or "(default config)"
    print(f"Eval Qwen chuẩn Anthropic — model={model_label} — {len(cases)} case\n")
    sem = asyncio.Semaphore(1 if args.serial else 4)
    rows = await asyncio.gather(*(run_case(c, packs, args, sem) for c in cases))

    lines = [fmt_row(r) for r in rows]
    print("\n".join(lines))

    def agg(prefix: str, sel) -> str:
        done = [r for r in rows if r.get(f"{prefix}_fields") not in (None, "ERR")]
        if not done:
            return "n/a"
        fh = sum(int(r[f"{prefix}_fields"].split("/")[0]) for r in done)
        ft = sum(int(r[f"{prefix}_fields"].split("/")[1]) for r in done)
        aok = sum(1 for r in done if r[f"{prefix}_action"] and not r[f"{prefix}_fp"])
        ms = sorted(r[f"{prefix}_ms"] for r in done if r.get(f"{prefix}_ms", -1) >= 0)
        med = ms[len(ms) // 2] if ms else -1
        return (f"field {fh}/{ft} ({100*fh//max(ft,1)}%) · action sạch "
                f"{aok}/{len(done)} · latency median {med}ms")
    summary = [f"QWEN : {agg('q', None)}", ]
    if not args.skip_local:
        summary.append(f"LOCAL: {agg('l', None)}")
    errs = [f"  {r['id']}: {r['q_err']}" for r in rows if r.get("q_err")]
    print("\n== TỔNG ==\n" + "\n".join(summary))
    if errs:
        print("Lỗi Qwen:\n" + "\n".join(errs))
    neg = [r for r in rows if r["id"].endswith("q")]
    if neg:
        print("\n== PHỦ ĐỊNH (gold: không fire) ==")
        for r in neg:
            print(f"  {r['id']}: qwen {'✅ chặn' if not r.get('q_fp') else '❌ vẫn fire ' + str(r['q_fp'])}"
                  + (f" · local {'✅ chặn' if not r.get('l_fp') else '❌ vẫn arm ' + str(r['l_fp'])}"
                     if "l_fields" in r else ""))

    if args.report:
        md = ["# Eval Qwen đối chứng — " + model_label, "",
              "```", *lines, "", *summary, "```", ""]
        for r in rows:
            if r.get("q_miss"):
                md.append(f"- {r['id']} miss: {r['q_miss']}")
        Path(args.report).write_text("\n".join(md), encoding="utf-8")
        print(f"\nĐã ghi report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
