#!/usr/bin/env python3
"""Dựng video demo Voice2Claim: ảnh cảnh + caption text + thuyết minh VALSEA TTS.

  .venv/bin/python scripts/make_demo_video.py out/demo/scenes.json        # bản Việt
  .venv/bin/python scripts/make_demo_video.py out/demo/scenes_en.json en  # bản Anh

scenes.json = [{"id","kind":"card|shot","img"?,"title","sub","voice","min":giây?}, …]
- kind=card  → title card tím (cắt cảnh giữa các phần)
- kind=shot  → screenshot + thanh caption dưới màn
Audio thuyết minh: VALSEA /v1/audio/speech (cache theo id — xoá wav để đọc lại).
Ghép: mỗi cảnh 1 segment mp4 (fade in/out) → concat → out/demo/voice2claim_demo.mp4
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "out" / "demo"
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
W, H = 1920, 1080
FPS = 30
PURPLE = "0x6252D8"
BG = "0xF1F2F9"


def sh(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {' '.join(args[:6])}…\n{r.stderr[-600:]}")


def dur_of(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


SUFFIX = ""          # "" = bản Việt · "en" = bản Anh (set trong main)


def _audio_dir() -> Path:
    return DEMO / (f"audio_{SUFFIX}" if SUFFIX else "audio")


async def tts_all(scenes: list[dict]) -> None:
    from app.core import valsea
    import httpx
    _audio_dir().mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=90) as client:
        for s in scenes:
            out = _audio_dir() / f"{s['id']}.wav"
            if out.exists() and out.stat().st_size > 1000:
                continue
            text = s.get("voice", "").strip()
            if not text:
                continue
            print(f"  TTS {s['id']}: {text[:50]}…")
            audio = await valsea.tts(text, client=client)
            out.write_bytes(audio)
            await asyncio.sleep(0.4)


def _txt(sid: str, suffix: str, content: str) -> Path:
    d = DEMO / "txt"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}_{suffix}.txt"
    p.write_text(content, encoding="utf-8")
    return p


def render_segment(s: dict, idx: int) -> Path:
    sid = s["id"]
    seg = DEMO / (f"seg_{SUFFIX}" if SUFFIX else "seg") / f"{idx:02d}_{sid}.mp4"
    seg.parent.mkdir(parents=True, exist_ok=True)
    wav = _audio_dir() / f"{sid}.wav"
    has_audio = wav.exists() and wav.stat().st_size > 1000
    dur = max((dur_of(wav) + 1.0) if has_audio else 0, float(s.get("min", 5)))
    fade_out = max(0.0, dur - 0.35)
    tfile = _txt(sid, "t", s.get("title", ""))
    sfile = _txt(sid, "s", s.get("sub", ""))

    if s.get("kind") == "card":
        vf = (
            f"drawtext=fontfile={FONT}:textfile={tfile}:fontsize=64:"
            f"fontcolor=white:x=(w-text_w)/2:y=(h/2)-90,"
            f"drawtext=fontfile={FONT}:textfile={sfile}:fontsize=34:"
            f"fontcolor=0xE6E1FF:x=(w-text_w)/2:y=(h/2)+10,"
            f"drawtext=fontfile={FONT}:text='Voice2Claim':fontsize=26:"
            f"fontcolor=0xCFC6FF:x=(w-text_w)/2:y=h-90,"
            f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out:.2f}:d=0.35"
        )
        vin = ["-f", "lavfi", "-i", f"color=c={PURPLE}:s={W}x{H}:r={FPS}"]
    else:
        img = str(ROOT / s["img"])
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG},"
            f"drawbox=y=ih-170:w=iw:h=170:color=white@0.94:t=fill,"
            f"drawbox=y=ih-170:w=iw:h=5:color={PURPLE}@0.95:t=fill,"
            f"drawtext=fontfile={FONT}:textfile={tfile}:fontsize=40:"
            f"fontcolor=0x23284D:x=60:y=h-140,"
            f"drawtext=fontfile={FONT}:textfile={sfile}:fontsize=26:"
            f"fontcolor=0x6B7294:x=60:y=h-78,"
            f"fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out:.2f}:d=0.35"
        )
        vin = ["-loop", "1", "-framerate", str(FPS), "-i", img]

    ain = ["-i", str(wav)] if has_audio else \
          ["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono"]
    sh(["ffmpeg", "-y", *vin, *ain,
        "-t", f"{dur:.2f}", "-vf", vf,
        "-af", "apad", "-shortest",
        "-c:v", "h264_videotoolbox", "-b:v", "5000k",  # ffmpeg conda không có libx264
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-ar", "24000",
        str(seg)])
    print(f"  seg {seg.name}  {dur:.1f}s")
    return seg


def main() -> int:
    global SUFFIX
    scenes_path = Path(sys.argv[1] if len(sys.argv) > 1
                       else DEMO / "scenes.json")
    SUFFIX = sys.argv[2] if len(sys.argv) > 2 else ""
    scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    print(f"[video] {len(scenes)} cảnh ({SUFFIX or 'vi'}) — TTS VALSEA…")
    asyncio.run(tts_all(scenes))

    print("[video] render segments…")
    segs = [render_segment(s, i) for i, s in enumerate(scenes)]

    lst = DEMO / f"concat{('_' + SUFFIX) if SUFFIX else ''}.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in segs),
                   encoding="utf-8")
    final = DEMO / (f"voice2claim_demo_{SUFFIX}.mp4" if SUFFIX
                    else "voice2claim_demo.mp4")
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c", "copy", str(final)])
    total = dur_of(final)
    print(f"[video] XONG → {final}  ({total/60:.1f} phút, "
          f"{final.stat().st_size//1_000_000}MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
