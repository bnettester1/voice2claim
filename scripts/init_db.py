#!/usr/bin/env python3
"""Khởi tạo / reset DB sản phẩm E12 (data/app.db).

  python scripts/init_db.py                 # migrate + seed (mặc định)
  python scripts/init_db.py --reset         # xoá DB rồi migrate + seed
  python scripts/init_db.py --import-notify # kéo kho khách fake từ notify REST

KHÔNG chạy --reset khi server đang chạy (in-memory store sẽ lệch DB).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="xoá DB rồi tạo lại")
    ap.add_argument("--no-seed", action="store_true", help="chỉ migrate")
    ap.add_argument("--import-notify", action="store_true",
                    help="import khách từ notify REST (cần MCP_AUTH_TOKEN)")
    args = ap.parse_args()

    from app.db import database, seed

    path = database.db_path()
    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        print(f"[init_db] đã xoá {path.name}*")

    ver = database.migrate()
    print(f"[init_db] schema version = {ver} ({path})")

    if not args.no_seed:
        from app.packs.loader import load_all
        seed.run(load_all())
        with database.db() as conn:
            counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("customers", "employees", "policies", "claims",
                                "action_catalog", "kb_documents", "tickets")}
        print("[init_db] seed OK:", ", ".join(f"{k}={v}" for k, v in counts.items()))

    if args.import_notify:
        n = _import_notify()
        print(f"[init_db] notify import: {n} khách")
    return 0


def _import_notify() -> int:
    import httpx

    from app.config import settings
    from app.db.dal import crm as dal_crm

    if not settings.notify_token:
        print("[init_db] bỏ qua import-notify (không có MCP_AUTH_TOKEN)")
        return 0
    total = 0
    with httpx.Client(timeout=10) as client:
        try:
            r = client.get(
                f"{settings.notify_base}/customers", params={"query": ""},
                headers={"User-Agent": "valsea-pilot/1.0 (init-db)",
                         "Authorization": f"Bearer {settings.notify_token}"})
            if r.status_code != 200:
                print(f"[init_db] notify HTTP {r.status_code} — bỏ qua")
                return 0
            data = r.json()
            rows = (data.get("customers") or data.get("results")
                    or data.get("data") or (data if isinstance(data, list) else []))
            for cust in rows:
                if isinstance(cust, dict) and \
                        dal_crm.upsert_customer_legacy(cust, "notify_import"):
                    total += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[init_db] notify lỗi ({type(exc).__name__}) — bỏ qua")
    return total


if __name__ == "__main__":
    raise SystemExit(main())
