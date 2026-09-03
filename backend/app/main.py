"""CROWDLENS backend — FastAPI :8000.

REST + WebSocket. All ML inference lives in the separate ml_service (:8001);
this process owns the database, risk/prediction/alert/incident logic, and
real-time fan-out.
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.realtime.hub import hub
from app.routers.config_routes import router as config_router
from app.routers.analysis_routes import router as analysis_router
from app.routers.ops_routes import router as ops_router
from app.seed import seed

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config_router)
app.include_router(analysis_router)
app.include_router(ops_router)


@app.on_event("startup")
async def _startup():
    hub.bind_loop(asyncio.get_running_loop())
    seed()


@app.get("/health")
def health():
    return {"status": "ok", "service": "crowdlens-backend", "version": settings.APP_VERSION}


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)
