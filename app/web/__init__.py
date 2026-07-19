"""Helper asset cho templates — cache-bust static (?v=) dùng chung mọi router."""
from __future__ import annotations

from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"


def asset_ver() -> str:
    """mtime lớn nhất của static lúc boot: đổi file + restart = URL mới →
    Cloudflare/browser cache miss ngay (bài học deploy 19/07)."""
    try:
        return str(int(max(p.stat().st_mtime for p in _STATIC.rglob("*.*"))))
    except ValueError:
        return "1"
