"""FastAPI app — Speech-to-Meaning pilot (VALSEA Hackathon 2026)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.batch.routes import PACKS, router as batch_router
from app.core.actions import OUT_DIR, pregenerate_tts
from app.platform.routes import router as platform_router
from app.realtime.routes import router as realtime_router
from app.telephony.routes import router as telephony_router
from app.workflow.routes import nav_ctx, router as workflow_router

BASE = Path(__file__).resolve().parent


def _warm_ml() -> None:
    """Warm silero-VAD + NER local (thread nền — thiếu deps thì thôi)."""
    try:
        from app.core.ml import ner_local, vad
        vad.available()
        ner_local.available()
    except Exception:  # noqa: BLE001
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB sản phẩm E12: migrate + seed + bền hoá ticket (lỗi DB không chặn demo)
    try:
        from app.core.actions import ticket_store
        from app.db import bridge, database, seed
        database.migrate()
        seed.run(PACKS)
        bridge.install(ticket_store)
        from app.workflow.seeds import seed_defs
        seed_defs()
        from app.workflow.runner import runner
        recovered = await runner.recover()
        if recovered:
            print(f"[wf] recover {recovered} run dang chạy dở")
    except Exception as exc:  # noqa: BLE001
        print(f"[db] init lỗi ({type(exc).__name__}: {exc}) — chạy in-memory")
    # pre-generate TTS xác nhận + warm ML (nền, không chặn khởi động)
    task = asyncio.create_task(pregenerate_tts(PACKS))
    warm = asyncio.get_event_loop().run_in_executor(None, _warm_ml)  # noqa: F841
    yield
    task.cancel()


app = FastAPI(title="Voice2Claim — Speech-to-Meaning (VALSEA)", lifespan=lifespan)
app.include_router(batch_router)
app.include_router(realtime_router)
app.include_router(telephony_router)
app.include_router(platform_router)
app.include_router(workflow_router)
app.mount("/static", StaticFiles(directory=BASE / "web" / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "web" / "templates")


from app.web import asset_ver  # noqa: E402

templates.env.globals["asset_ver"] = asset_ver()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Voice2Claim — Tổng quan (shell sidebar E12)."""
    return templates.TemplateResponse(request, "dashboard.html",
                                      await nav_ctx())


@app.get("/pilot", response_class=HTMLResponse)
async def pilot(request: Request):
    """Demo Speech-to-Meaning cũ (batch/live/review/console) — nay là menu."""
    return templates.TemplateResponse(request, "pilot.html", await nav_ctx())


@app.get("/crm", response_class=HTMLResponse)
async def crm_page(request: Request):
    return templates.TemplateResponse(request, "crm.html", await nav_ctx())


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return templates.TemplateResponse(request, "tasks.html", await nav_ctx())


@app.get("/demo-video")
def demo_video(lang: str = "vi"):
    """Video hướng dẫn (popup) — ?lang=vi|en, bản 720p, fallback 1080p."""
    names = (("voice2claim_demo_en_720.mp4", "voice2claim_demo_en.mp4")
             if lang == "en"
             else ("voice2claim_demo_720.mp4", "voice2claim_demo.mp4"))
    for name in names:
        path = OUT_DIR / "demo" / name
        if path.exists():
            return FileResponse(path, media_type="video/mp4",
                                filename=f"voice2claim_demo_{lang}.mp4")
    return HTMLResponse("chưa có video demo", status_code=404)


@app.get("/uploads/{name}")
def get_upload(name: str):
    path = (OUT_DIR / "uploads" / name).resolve()
    if not str(path).startswith(str((OUT_DIR / "uploads").resolve())) \
            or not path.exists():
        return HTMLResponse("not found", status_code=404)
    return FileResponse(path)


@app.get("/call", response_class=HTMLResponse)
async def call_page(request: Request, pack: str = "insurance_callcenter"):
    from app.config import settings
    p = PACKS.get(pack)
    if p is None or (p.call_script is None and p.call_flows is None):
        p = PACKS.get("insurance_contract")
    if p.call_script is not None:
        names = [s.field for s in p.call_script.steps]
    else:
        names = ([s.field for s in p.call_flows.identify] + ["yeu_cau"]
                 + [s.field for i in p.call_flows.intents for s in i.steps])
    fields = [{"name": n, "label": p.field(n).label}
              for n in dict.fromkeys(names) if p.field(n) is not None]
    call_packs = [q for q in PACKS.values()
                  if q.call_script is not None or q.call_flows is not None]
    return templates.TemplateResponse(request, "call.html", {
        "pack": p,
        "fields": fields,
        "call_packs": call_packs,
        "twilio_ready": settings.twilio_ready,
        **(await nav_ctx()),
    })


@app.get("/rec/{sid}")
def get_recording(sid: str):
    from app.batch.routes import find_recording
    if not sid.isalnum():
        return HTMLResponse("bad id", status_code=400)
    found = find_recording(sid)
    if not found:
        return HTMLResponse("not found", status_code=404)
    path, mime = found
    return FileResponse(path, media_type=mime)


@app.get("/pdf/{name}")
def get_pdf(name: str):
    path = (OUT_DIR / name).resolve()
    if not str(path).startswith(str(OUT_DIR.resolve())) or not path.exists():
        return HTMLResponse("not found", status_code=404)
    return FileResponse(path, media_type="application/pdf")


@app.get("/health")
def health():
    from app.config import settings
    return {"ok": True, "keys": settings.status(), "packs": list(PACKS)}
