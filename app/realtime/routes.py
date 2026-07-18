from fastapi import APIRouter, WebSocket

from app.batch.routes import PACKS
from app.realtime.session import LiveSession

router = APIRouter()


@router.websocket("/ws/live/{pack_id}")
async def live_ws(ws: WebSocket, pack_id: str):
    pack = PACKS.get(pack_id)
    if not pack:
        await ws.close(code=4404)
        return
    await LiveSession(ws, pack).run()
