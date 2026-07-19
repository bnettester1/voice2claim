"""API nền tảng: dashboard + CRM. Mọi handler đều mỏng — logic nằm trong DAL."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.database import run_db
from app.db.dal import crm as dal_crm
from app.db.dal import stats as dal_stats

router = APIRouter()


@router.get("/api/wf/dashboard")
async def wf_dashboard():
    try:
        return await run_db(dal_stats.dashboard)
    except Exception as exc:  # noqa: BLE001 — DB lỗi thì UI hiện trạng thái rỗng
        return JSONResponse({"counts": {"db_ok": False},
                             "feed": [], "error": str(exc)[:120]},
                            status_code=200)


@router.get("/api/wf/crm/customers")
async def wf_customers():
    return {"customers": await run_db(dal_crm.list_customers)}


@router.get("/api/wf/crm/customers/{customer_id}")
async def wf_customer_360(customer_id: str):
    detail = await run_db(dal_crm.customer_360, customer_id)
    if detail is None:
        return JSONResponse({"error": "không có khách này"}, status_code=404)
    return {"detail": detail}


@router.patch("/api/wf/crm/customers/{customer_id}")
async def wf_customer_update(customer_id: str, payload: dict):
    ok = await run_db(dal_crm.update_customer, customer_id,
                      str(payload.get("name") or ""),
                      payload.get("email"), payload.get("phone"),
                      payload.get("national_id"))
    if not ok:
        return JSONResponse({"error": "không có gì để sửa hoặc sai mã khách"},
                            status_code=400)
    return {"ok": True}


@router.get("/api/wf/crm/employees")
async def wf_employees():
    from app.db.dal import erp as dal_erp
    return {"employees": await run_db(dal_erp.list_employees)}


@router.patch("/api/wf/crm/employees/{employee_id}")
async def wf_employee_update(employee_id: str, payload: dict):
    from app.db.dal import erp as dal_erp
    ok = await run_db(dal_erp.update_employee, employee_id,
                      str(payload.get("name") or ""),
                      payload.get("email"), payload.get("phone"))
    if not ok:
        return JSONResponse({"error": "không có gì để sửa hoặc sai mã NV"},
                            status_code=400)
    return {"ok": True}


@router.get("/api/wf/crm/policies")
async def wf_policies():
    return {"policies": await run_db(dal_crm.list_policies)}


@router.get("/api/wf/crm/claims")
async def wf_claims():
    return {"claims": await run_db(dal_crm.list_claims)}
