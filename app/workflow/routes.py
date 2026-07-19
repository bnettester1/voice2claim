"""Routes workflow — trang (/workflows, /runs, /sign, /rate) + API /api/wf/*."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.core.actions import OUT_DIR
from app.db.database import run_db
from app.db.dal import erp as dal_erp
from app.db.dal import flywheel as dal_fw
from app.db.dal import workflow as dal_wf
from app.workflow.defs import NODE_TYPES, validate_graph
from app.workflow.runner import complete_task_and_resume, runner

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent
                            / "web" / "templates")
from app.web import asset_ver  # noqa: E402
templates.env.globals["asset_ver"] = asset_ver()

UPLOAD_DIR = OUT_DIR / "uploads"
_UPLOAD_OK = {".wav", ".m4a", ".mp3", ".ogg", ".webm",
              ".jpg", ".jpeg", ".png", ".pdf"}
_UPLOAD_MAX = 10_000_000


async def nav_ctx() -> dict:
    try:
        return {"nav_flows": await run_db(dal_wf.active_flows),
                "nav_tasks": True, "nav_kb": True}
    except Exception:  # noqa: BLE001
        return {"nav_flows": [], "nav_tasks": True, "nav_kb": True}


# ================= trang =================
@router.get("/workflows", response_class=HTMLResponse)
async def workflows_page(request: Request):
    return templates.TemplateResponse(request, "workflows.html",
                                      await nav_ctx())


@router.get("/workflows/{key}", response_class=HTMLResponse)
async def workflow_detail_page(request: Request, key: str):
    return templates.TemplateResponse(
        request, "workflows.html", {**(await nav_ctx()), "wf_key": key})


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_page(request: Request, run_id: int):
    return templates.TemplateResponse(
        request, "run.html", {**(await nav_ctx()), "run_id": run_id})


@router.get("/sign/{token}", response_class=HTMLResponse)
async def sign_page(request: Request, token: str):
    ev = await run_db(dal_wf.get_token, token)
    ctx: dict = {"token": token, "state": "invalid", "summary": None}
    if ev and ev.get("run_id"):
        run = await run_db(dal_wf.get_run, int(ev["run_id"]), False)
        if run:
            c = run["context"]
            fields = c.get("fields") or {}
            ctx["summary"] = {
                "name": (c.get("customer") or {}).get("name")
                        or fields.get("ho_ten", ""),
                "product": fields.get("san_pham", "Bảo hiểm vật chất ô tô"),
                "policy_no": c.get("policy_no", ""),
                "xe": fields.get("xe_khach", ""),
                "bien_so": fields.get("bien_so_xe", ""),
                "pdf_url": (c.get("contract_doc") or {}).get("url", ""),
            }
            ctx["state"] = "signed" if ev["status"] == "consumed" else "ready"
    return templates.TemplateResponse(request, "sign.html", ctx)


@router.post("/api/wf/sign/{token}")
async def sign_submit(token: str, payload: dict):
    signed_name = str(payload.get("signed_name") or "").strip()
    if not signed_name:
        return JSONResponse({"error": "cần gõ họ tên để ký"}, status_code=400)
    run_id = await runner.resume_token(token, {
        "signed_name": signed_name,
        "signed_at": time.strftime("%d/%m/%Y %H:%M")})
    if run_id is None:
        return JSONResponse({"error": "link đã dùng hoặc không hợp lệ"},
                            status_code=409)
    return {"ok": True, "run_id": run_id}


@router.get("/rate/{token}", response_class=HTMLResponse)
async def rate_page(request: Request, token: str, stars: int | None = None):
    ev = await run_db(dal_wf.get_token, token)
    state = "invalid"
    if ev:
        state = "done" if ev["status"] == "consumed" else "ready"
    return templates.TemplateResponse(
        request, "rate.html",
        {"token": token, "state": state, "stars": stars or 0})


@router.post("/api/wf/rate/{token}")
async def rate_submit(token: str, payload: dict):
    stars = int(payload.get("stars") or 0)
    if not 1 <= stars <= 5:
        return JSONResponse({"error": "chấm 1-5 sao"}, status_code=400)
    ev = await run_db(dal_wf.consume_token, token,
                      {"stars": stars, "comment": payload.get("comment", "")})
    if ev is None or not ev.get("run_id"):
        return JSONResponse({"error": "link đã dùng hoặc không hợp lệ"},
                            status_code=409)
    await run_db(dal_fw.upsert_evaluation, int(ev["run_id"]), "customer",
                 stars, str(payload.get("comment") or ""))
    return {"ok": True}


# ================= API defs =================
@router.get("/api/wf/defs")
async def api_defs():
    return {"defs": await run_db(dal_wf.list_defs)}


@router.get("/api/wf/defs/{key}")
async def api_def_detail(key: str, version: int | None = None):
    d = await run_db(dal_wf.get_def_by_key, key, version)
    if d is None:
        return JSONResponse({"error": "không có workflow này"}, status_code=404)
    return {"def": d, "versions": await run_db(dal_wf.list_versions, key),
            "node_types": {k: v["icon"] for k, v in NODE_TYPES.items()},
            "metrics": await run_db(dal_fw.metrics_by_key, key)}


@router.post("/api/wf/defs/validate")
async def api_validate(payload: dict):
    errors = validate_graph(payload.get("graph") or {})
    return {"ok": not errors, "errors": errors}


@router.post("/api/wf/defs/{key}/versions")
async def api_add_version(key: str, payload: dict):
    graph = payload.get("graph") or {}
    errors = validate_graph(graph)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
    cur = await run_db(dal_wf.get_def_by_key, key)
    if cur is None:
        return JSONResponse({"error": "không có workflow này"}, status_code=404)
    ver = await run_db(dal_wf.next_version, key)
    await run_db(dal_wf.insert_def, key, cur["name"], graph, cur["trigger"],
                 cur["description"], ver, "draft", "manual",
                 str(payload.get("note") or ""))
    return {"ok": True, "version": ver}


@router.post("/api/wf/defs/{key}/activate")
async def api_activate(key: str, payload: dict):
    ok = await run_db(dal_wf.activate, key, int(payload.get("version") or 0))
    return {"ok": ok}


# ================= API runs =================
@router.get("/api/wf/runs")
async def api_runs(def_key: str = "", status: str = "", limit: int = 50):
    return {"runs": await run_db(dal_wf.list_runs, def_key, status, limit)}


@router.get("/api/wf/runs/{run_id}")
async def api_run_detail(run_id: int):
    run = await run_db(dal_wf.get_run, run_id)
    if run is None:
        return JSONResponse({"error": "không có run này"}, status_code=404)
    status_map: dict[str, str] = {}
    for s in run["steps"]:
        status_map[s["node_id"]] = {
            "completed": "done", "running": "current", "waiting": "waiting",
            "failed": "failed", "interrupted": "failed", "skipped": "skipped",
        }.get(s["status"], "")
    if run["status"] == "running":
        status_map.setdefault(run["current_node"], "current")
    if run["status"].startswith("waiting"):
        status_map[run["current_node"]] = "waiting"
    run["evaluations"] = await run_db(dal_fw.run_evaluations, run_id)
    return {"run": run, "status_map": status_map}


@router.post("/api/wf/runs")
async def api_start_run(payload: dict):
    def_key = str(payload.get("def_key") or "")
    try:
        run_id = await runner.start(def_key, payload.get("context") or {},
                                    str(payload.get("channel") or "web"))
    except LookupError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return {"ok": True, "run_id": run_id}


@router.post("/api/wf/runs/{run_id}/retry")
async def api_retry(run_id: int):
    return {"ok": await runner.retry(run_id)}


@router.post("/api/wf/dispatch")
async def api_dispatch(payload: dict):
    """AI Điều hành ngoài cuộc gọi: chọn workflow theo form_type/keywords —
    dùng CÙNG router keyword của tổng đài (route_intent), giải thích được."""
    from types import SimpleNamespace

    from app.telephony.flow_agent import route_intent

    text = str(payload.get("text") or "")
    form_type = str(payload.get("form_type") or "")
    defs = await run_db(dal_wf.active_defs_full)
    chosen, matched_by = None, ""
    if form_type:
        chosen = next((d for d in defs
                       if d["trigger"].get("form_type") == form_type), None)
        matched_by = f"form_type={form_type}" if chosen else ""
    if chosen is None and text:
        fake_intents = [SimpleNamespace(
            id=d["key"], keywords=d["trigger"].get("keywords") or [])
            for d in defs]
        hit = route_intent(fake_intents, text)
        if hit is not None:
            chosen = next(d for d in defs if d["key"] == hit.id)
            matched_by = "keywords: " + ", ".join(
                k for k in chosen["trigger"].get("keywords", [])
                if k.lower() in text.lower()) or "fuzzy"
    if chosen is None:
        return JSONResponse({"ok": False,
                             "error": "không khớp workflow nào",
                             "candidates": [d["key"] for d in defs]},
                            status_code=404)
    run_id = await runner.start(chosen["key"], payload.get("context") or {},
                                str(payload.get("channel") or "api"))
    from app.db.database import db as _db, record_history
    def _note():
        with _db() as conn:
            record_history(conn, "run", str(run_id), "dispatched", "", "ai", "",
                           f"Dispatch: “{(text or form_type)[:60]}” →"
                           f" {chosen['name']} ({matched_by})")
    await run_db(_note)
    return {"ok": True, "def_key": chosen["key"], "run_id": run_id,
            "matched": matched_by}


# ================= API tasks =================
@router.get("/api/wf/tasks")
async def api_tasks(role: str = "", status: str = "open,in_progress"):
    return {"tasks": await run_db(dal_erp.task_inbox, role, "", status)}


@router.get("/api/wf/tasks/{task_id}")
async def api_task_detail(task_id: int):
    t = await run_db(dal_erp.get_task, task_id)
    if t is None:
        return JSONResponse({"error": "không có task này"}, status_code=404)
    return {"task": t}


@router.post("/api/wf/tasks/{task_id}/complete")
async def api_task_complete(task_id: int, payload: dict):
    task = await complete_task_and_resume(
        task_id, str(payload.get("outcome") or "completed"),
        str(payload.get("note") or ""), payload.get("result") or {},
        str(payload.get("actor_id") or ""))
    if task is None:
        return JSONResponse({"error": "không có task này"}, status_code=404)
    stars = int(payload.get("stars") or 0)     # flywheel: ★ nhân sự (tuỳ chọn)
    if 1 <= stars <= 5 and task.get("run_id"):
        rater = {"assessor_visit": "handler", "director_approval": "director",
                 "complete_form": "agent"}.get(task["task_type"], "agent")
        await run_db(dal_fw.upsert_evaluation, int(task["run_id"]), rater,
                     stars, str(payload.get("note") or ""),
                     str(payload.get("actor_id") or ""))
    return {"ok": True, "task_status": task["status"], "run_id": task.get("run_id")}


# ================= kho tri thức =================
KB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "kb"
_KB_KIND = {".txt": "text", ".md": "text", ".pdf": "pdf",
            ".wav": "audio", ".m4a": "audio", ".mp3": "audio",
            ".jpg": "image", ".jpeg": "image", ".png": "image"}


@router.get("/kb", response_class=HTMLResponse)
async def kb_page(request: Request):
    return templates.TemplateResponse(request, "kb.html", await nav_ctx())


@router.get("/api/wf/kb")
async def api_kb_list():
    from app.config import settings
    from app.db.dal import kb as dal_kb
    data = await run_db(dal_kb.list_documents)
    data["qwen_ready"] = bool(settings.qwen_key and settings.qwen_base)
    return data


@router.post("/api/wf/kb/upload")
async def api_kb_upload(file: UploadFile = File(...)):
    import hashlib
    from app.db.dal import kb as dal_kb
    ext = Path(file.filename or "x").suffix.lower()
    kind = _KB_KIND.get(ext)
    if kind is None:
        return JSONResponse({"error": f"đuôi {ext} chưa hỗ trợ"},
                            status_code=400)
    data = await file.read()
    if len(data) > _UPLOAD_MAX:
        return JSONResponse({"error": "file quá 10MB"}, status_code=400)
    sha1 = hashlib.sha1(data).hexdigest()
    KB_DIR.mkdir(parents=True, exist_ok=True)
    path = KB_DIR / f"{sha1}{ext}"
    path.write_bytes(data)
    doc_id = await run_db(dal_kb.register_document,
                          Path(file.filename).name, file.content_type or "",
                          kind, f"data/kb/{path.name}", len(data), sha1)
    return {"ok": True, "doc_id": doc_id}


@router.post("/api/wf/kb/{doc_id}/extract")
async def api_kb_extract(doc_id: int):
    """Qwen bóc tách nghiệp vụ → draft workflow (admin/offline — 0012/0013)."""
    from app.workflow.kb_extract import extract_document
    return await extract_document(doc_id)


@router.post("/api/wf/kb/extractions/{ext_id}/promote")
async def api_kb_promote(ext_id: int, payload: dict | None = None):
    from app.db.dal import kb as dal_kb
    ext = await run_db(dal_kb.get_extraction, ext_id)
    if ext is None:
        return JSONResponse({"error": "không có bản bóc tách"}, status_code=404)
    data = ext["extracted"]
    graph = data.get("graph") or {}
    errors = validate_graph(graph)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
    key = str(data.get("key") or f"wf_kb_{ext_id}")
    if await run_db(dal_wf.get_def_by_key, key):
        key = f"{key}_{ext_id}"
    def_id = await run_db(
        dal_wf.insert_def, key, str(data.get("name") or key), graph,
        {"channel": "api", "icon": "🧪",
         "keywords": data.get("keywords") or []},
        str(data.get("summary") or ""), 1, "draft", "kb_extraction",
        f"promote từ KB #{ext['doc_id']}", ext_id)
    await run_db(dal_kb.mark_promoted, ext_id, def_id)
    return {"ok": True, "key": key}


# ================= uploads =================
@router.post("/api/wf/uploads")
async def api_upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "x").suffix.lower()
    if ext not in _UPLOAD_OK:
        return JSONResponse({"error": f"đuôi {ext} không cho phép"},
                            status_code=400)
    data = await file.read()
    if len(data) > _UPLOAD_MAX:
        return JSONResponse({"error": "file quá 10MB"}, status_code=400)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = f"{int(time.time())}_{Path(file.filename).name}".replace(" ", "_")
    path = UPLOAD_DIR / safe
    path.write_bytes(data)
    return {"ok": True, "name": safe, "path": f"out/uploads/{safe}",
            "url": f"/uploads/{safe}", "size": len(data)}
