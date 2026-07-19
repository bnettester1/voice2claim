"""CRM lookup cho tổng đài (E10) — notify REST server của Long.

GET /customers?query=<tên/mã claim> · GET /handlers?claim_type=<xe|y_te|nhan_tho>
Auth Bearer (MCP_AUTH_TOKEN từ ~/.notify.env — không bao giờ log). Đặt
User-Agent tử tế vì zone bật Browser Integrity Check (UA kiểu python bị 403).
Server lỗi/thiếu token → trả None, flow tiếp tục nhánh lookup_miss (degrade sạch).
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

_HEADERS = {"User-Agent": "valsea-pilot/1.0 (callcenter)"}

# trạng thái claim → câu ETA đọc cho khách
_ETA = {
    "investigating": "Dự kiến trong vòng 3 ngày làm việc sẽ có kết quả giám định ạ.",
    "pending_assignment": "Hồ sơ sẽ được phân công giám định viên trong hôm nay, "
                          "em sẽ nhắn tin cập nhật ngay khi có ạ.",
    "approved": "Hồ sơ đã được duyệt, khoản chi trả sẽ đến trong 5 ngày làm việc ạ.",
    "paid": "Hồ sơ đã chi trả xong ạ, anh chị kiểm tra tài khoản giúp em ạ.",
    "rejected": "Hồ sơ đang ở trạng thái từ chối — em sẽ chuyển bộ phận phúc tra "
                "liên hệ lại giải thích chi tiết ạ.",
}
_STATUS_VI = {
    "investigating": "đang giám định",
    "pending_assignment": "chờ phân công giám định viên",
    "approved": "đã duyệt chi trả",
    "paid": "đã chi trả",
    "rejected": "từ chối (chờ phúc tra)",
    "received": "đã tiếp nhận",
}


# Fallback LOCAL khi REST không sẵn (thiếu token/mạng) — bản rút gọn kho demo
# công khai của notify server (fake data), đủ cho 2 workflow demo.
_LOCAL_CUSTOMERS: list[dict] = [
    {"id": "KH-0001", "name": "Nguyễn Tiến Tuấn",
     "email": "nguyentientuan2052000@gmail.com", "phone": "+84911961540",
     "national_id": "079095001234", "policy": "bảo hiểm vật chất xe máy",
     "claim": {"id": "CL-XE-2607-001", "type": "motorbike_accident",
               "status": "investigating", "handler": "Lưu Hải Long"}},
    {"id": "KH-0002", "name": "Phạm Thị Mai", "email": "",
     "phone": "+84911961540", "national_id": "079088002345",
     "policy": "bảo hiểm vật chất ô tô",
     "claim": {"id": "CL-XE-2607-002", "type": "car_accident",
               "status": "pending_assignment", "handler": ""}},
    {"id": "KH-0004", "name": "Vũ Hoàng Nam", "email": "",
     "phone": "+84911961540", "national_id": "001092004567",
     "policy": "bảo hiểm sức khỏe",
     "claim": {"id": "CL-YT-2607-004", "type": "health",
               "status": "approved", "handler": "Trần Kim Phương"}},
]
_LOCAL_HANDLERS = {
    "xe": {"id": "NV-01", "name": "Lưu Hải Long", "email": "hailongluu@gmail.com"},
    "y_te": {"id": "NV-02", "name": "Trần Kim Phương", "email": "tkphuong132@gmail.com"},
    "nhan_tho": {"id": "NV-03", "name": "Lưu Hải Long", "email": "hailongluu@gmail.com"},
}


def ready() -> bool:
    return bool(settings.notify_token)


def _local_lookup(query: str) -> dict | None:
    from app.core.triggers import normalize_vi
    q = normalize_vi(query)
    if not q:
        return None
    best, best_score = None, 0
    for c in _LOCAL_CUSTOMERS:
        name = normalize_vi(c["name"])
        toks_q, toks_n = set(q.split()), set(name.split())
        score = len(toks_q & toks_n)
        if q in name or name in q:
            score += 2
        if score > best_score:
            best, best_score = c, score
    return dict(best) if best and best_score >= 1 else None


def verify_identity(cust: dict | None, cccd_tail: str) -> bool:
    """6–9 số cuối CCCD khách đọc khớp đuôi national_id trong hồ sơ."""
    if not cust or not cccd_tail:
        return False
    nid = str(cust.get("national_id") or "")
    tail = str(cccd_tail).strip()
    return bool(nid) and len(tail) >= 4 and nid.endswith(tail)


async def _get(path: str, params: dict, client: httpx.AsyncClient) -> Any | None:
    if not settings.notify_token:
        return None
    try:
        r = await client.get(
            f"{settings.notify_base}{path}", params=params,
            headers={**_HEADERS,
                     "Authorization": f"Bearer {settings.notify_token}"},
            timeout=8,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return data if data.get("ok", True) else None
    except Exception:  # noqa: BLE001
        return None


def _first(data: Any, *keys: str) -> dict | None:
    """Bóc phần tử đầu của list nằm dưới một trong các key (schema bao dung)."""
    if data is None:
        return None
    for k in keys:
        v = data.get(k) if isinstance(data, dict) else None
        if isinstance(v, list) and v:
            return v[0] if isinstance(v[0], dict) else None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


async def lookup_customer(query: str,
                          client: httpx.AsyncClient) -> dict | None:
    """→ hồ sơ khách khớp query: DB (E12) → REST notify → kho local."""
    try:
        from app.db.database import run_db
        from app.db.dal import crm as dal_crm
        hit = await run_db(dal_crm.search_customer_legacy, query)
        if hit:
            return hit
    except Exception:  # noqa: BLE001 — DB hỏng thì đi tiếp nhánh cũ
        pass
    data = await _get("/customers", {"query": query}, client)
    cust = _first(data, "customers", "results", "data")
    if cust:
        try:                     # hội tụ về DB để lần gọi sau tra tại chỗ
            from app.db.database import run_db
            from app.db.dal import crm as dal_crm
            await run_db(dal_crm.upsert_customer_legacy, dict(cust),
                         "notify_import")
        except Exception:  # noqa: BLE001
            pass
        return cust
    return _local_lookup(query)


async def lookup_handler(claim_type: str,
                         client: httpx.AsyncClient) -> dict | None:
    """→ nhân sự phụ trách nhóm claim: DB (E12) → REST notify → kho local."""
    try:
        from app.db.database import run_db
        from app.db.dal import erp as dal_erp
        hit = await run_db(dal_erp.handler_for_group, claim_type)
        if hit:
            return hit
    except Exception:  # noqa: BLE001
        pass
    data = await _get("/handlers", {"claim_type": claim_type}, client)
    h = _first(data, "handlers", "results", "data")
    return h if h else _LOCAL_HANDLERS.get(claim_type)


def profile_summary(cust: dict) -> str:
    """Hồ sơ → 1 câu tổng quan đọc cho khách (an toàn thiếu trường)."""
    name = cust.get("name") or cust.get("ten") or "anh chị"
    parts: list[str] = []
    pol = cust.get("policy") or cust.get("policies") or cust.get("policy_type")
    if isinstance(pol, list):
        pol = ", ".join(str(p.get("type", p) if isinstance(p, dict) else p)
                        for p in pol[:2])
    if pol:
        parts.append(f"đang có hợp đồng {pol}")
    claim = _claim_of(cust)
    if claim:
        parts.append(f"và hồ sơ {claim.get('id', '')} "
                     f"{_STATUS_VI.get(str(claim.get('status', '')), '')}".strip())
    joined = " ".join(parts) if parts else "có hồ sơ khách hàng trong hệ thống"
    return f"{name} hiện {joined}"


def _claim_of(cust: dict) -> dict | None:
    c = cust.get("claim") or cust.get("claims") or cust.get("claim_id")
    if isinstance(c, list):
        return c[0] if c and isinstance(c[0], dict) else None
    if isinstance(c, dict):
        return c
    if isinstance(c, str):
        return {"id": c, "status": cust.get("claim_status", "")}
    return None


def status_reply(tpl: str, cust: dict, handler: dict | None) -> str:
    """Điền reply_tpl của intent claim_status từ hồ sơ lookup."""
    claim = _claim_of(cust) or {}
    status_raw = str(claim.get("status", ""))
    hname = ""
    if handler:
        hname = handler.get("name") or handler.get("ten") or ""
    if not hname:
        hname = str(claim.get("handler") or cust.get("handler") or
                    "bộ phận giám định")
    return (tpl
            .replace("{ten}", str(cust.get("name") or cust.get("ten") or "anh chị"))
            .replace("{claim_id}", str(claim.get("id") or "của mình"))
            .replace("{status}", _STATUS_VI.get(status_raw, status_raw or "đang xử lý"))
            .replace("{handler}", hname)
            .replace("{eta}", _ETA.get(status_raw, "Em sẽ đôn đốc bộ phận xử lý cập nhật sớm nhất ạ.")))


def claim_type_of(cust: dict | None, fallback: str = "xe") -> str:
    claim = _claim_of(cust or {}) or {}
    cid = str(claim.get("id", ""))
    if "-YT-" in cid:
        return "y_te"
    if "-NT-" in cid:
        return "nhan_tho"
    if "-XE-" in cid:
        return "xe"
    return fallback
