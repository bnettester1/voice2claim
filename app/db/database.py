"""SQLite sản phẩm E12 — data/app.db (tách hẳn harness.db của dev-tooling).

stdlib sqlite3, WAL, foreign_keys ON, busy_timeout 5s. Migration bằng
PRAGMA user_version + file app/db/schema/NNN-*.sql (mượn pattern harness).
DAL sync mở connection ngắn per-call; async gọi qua run_db (to_thread).
Invariant: 1 uvicorn worker (in-memory store cũ vốn đã ép điều này).
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def db_path() -> Path:
    return Path(os.environ.get("APP_DB_PATH") or REPO_ROOT / "data" / "app.db")


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """Connection ngắn: commit khi xong, rollback khi lỗi, luôn close."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate() -> int:
    """Áp schema/NNN-*.sql chưa chạy theo PRAGMA user_version. → version cuối."""
    conn = connect()
    try:
        cur = conn.execute("PRAGMA user_version").fetchone()[0]
        for path in sorted(SCHEMA_DIR.glob("[0-9]*.sql")):
            ver = int(path.name.split("-", 1)[0])
            if ver <= cur:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version={ver:d}")
            conn.commit()
            cur = ver
        return cur
    finally:
        conn.close()


async def run_db(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Chạy hàm DAL sync ngoài event loop (không bao giờ block vòng thoại)."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def next_code(conn: sqlite3.Connection, name: str, prefix: str, width: int = 4) -> str:
    """Sinh mã nghiệp vụ atomic từ bảng sequences: 'KH-0005', 'CL-XE-2607-003'…"""
    row = conn.execute(
        "INSERT INTO sequences(name, value) VALUES(?, 1) "
        "ON CONFLICT(name) DO UPDATE SET value = value + 1 RETURNING value",
        (name,),
    ).fetchone()
    return f"{prefix}{row[0]:0{width}d}"


def record_history(conn: sqlite3.Connection, entity_kind: str, entity_id: str,
                   to_status: str, from_status: str = "",
                   actor_kind: str = "system", actor_id: str = "",
                   note: str = "") -> None:
    """1 dòng status_history — nguồn của AI Decision Feed (actor_kind='ai')."""
    conn.execute(
        "INSERT INTO status_history(entity_kind, entity_id, from_status,"
        " to_status, actor_kind, actor_id, note) VALUES(?,?,?,?,?,?,?)",
        (entity_kind, entity_id, from_status, to_status, actor_kind,
         actor_id, note[:500]),
    )
