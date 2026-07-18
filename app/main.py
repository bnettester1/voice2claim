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
from app.realtime.routes import router as realtime_router
from app.telephony.routes import router as telephony_router

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
    # pre-generate TTS xác nhận + warm ML (nền, không chặn khởi động)
    task = asyncio.create_task(pregenerate_tts(PACKS))
    warm = asyncio.get_event_loop().run_in_executor(None, _warm_ml)  # noqa: F841
    yield
    task.cancel()


app = FastAPI(title="Speech-to-Meaning Pilot", lifespan=lifespan)
app.include_router(batch_router)
app.include_router(realtime_router)
app.include_router(telephony_router)
app.mount("/static", StaticFiles(directory=BASE / "web" / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "web" / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/call", response_class=HTMLResponse)
def call_page(request: Request, pack: str = "insurance_callcenter"):
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
