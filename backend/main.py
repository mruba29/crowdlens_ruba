"""CROWDLENS backend — FastAPI.

CCTV / uploaded crowd video -> detect people -> count -> density -> movement
-> risk score -> risk level -> alert when risk is high.

Computer vision runs in-process (backend/cv/). No separate ML service to start.

Privacy: no facial recognition, no identity, no personal data. Only anonymous,
zone-level crowd analytics.
"""
from __future__ import annotations
import asyncio
import json
import os
import shutil
import time
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import store
import analysis
from cv.detector import get_detector

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="CROWDLENS", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- runtime settings (in-memory, editable via /api/settings) ----
SETTINGS: dict = {
    "privacy_mode": True,                 # always on; exposed read-only intent
    "detection_confidence": 0.35,
    "analysis_sample_every_n": 3,         # process every Nth frame
    "zone_area_m2": 100.0,                # estimated visible ground area
    "critical_density_ppm2": 5.0,
    "risk_thresholds": {"YELLOW": 31, "ORANGE": 56, "RED": 76, "BLACK": 91},
}

# ---- websocket hub ----
_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None


def publish(kind: str, payload) -> None:
    msg = json.dumps({"type": kind, "ts": time.time(), "data": payload}, default=str)
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(msg), _loop)


async def _broadcast(msg: str) -> None:
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()
    store.init()


# ---------------------------------------------------------------- health
@app.get("/api/health")
@app.get("/health")
def health():
    det = get_detector()
    return {
        "status": "ok",
        "service": "crowdlens-backend",
        "detector": {
            "backend": det.backend,
            "available": det.available,
            "is_yolo": det.is_yolo,
        },
        "privacy_mode": SETTINGS["privacy_mode"],
        "analysis_status": analysis.state.status,
        "websocket_clients": len(_clients),
    }


# ---------------------------------------------------------------- video upload
@app.post("/api/video/upload")
async def upload_video(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "video.mp4")[1].lower()
    if ext not in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
        raise HTTPException(400, f"unsupported file type: {ext}")
    video_id = uuid.uuid4().hex + ext
    dest = os.path.join(UPLOAD_DIR, video_id)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size = os.path.getsize(dest)
    return {"video_id": video_id, "filename": file.filename, "size_bytes": size}


# ---------------------------------------------------------------- analysis
@app.post("/api/analysis/start")
def analysis_start(payload: dict):
    video_id = payload.get("video_id")
    if not video_id:
        raise HTTPException(400, "video_id is required")
    path = os.path.join(UPLOAD_DIR, os.path.basename(video_id))
    if not os.path.exists(path):
        raise HTTPException(404, "uploaded video not found — upload it first")
    det = get_detector()
    if not det.available:
        raise HTTPException(503, "no person detector available on the server")
    analysis.start(video_id, path, settings=SETTINGS, publish=publish)
    return analysis.state.status_dict()


@app.post("/api/analysis/stop")
def analysis_stop():
    analysis.stop()
    return analysis.state.status_dict()


@app.get("/api/analysis/status")
def analysis_status():
    return analysis.state.status_dict()


@app.get("/api/metrics")
def metrics():
    return analysis.state.metrics_dict()


@app.get("/api/zones")
def zones():
    return analysis.state.metrics_dict()["zones"]


# ---------------------------------------------------------------- alerts
@app.get("/api/alerts")
def alerts(level: str | None = None):
    return store.list_alerts(level)


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int):
    a = store.acknowledge(alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    publish("alert", a)
    return a


# ---------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings():
    return SETTINGS


@app.put("/api/settings")
def update_settings(payload: dict):
    allowed = {"detection_confidence", "analysis_sample_every_n", "zone_area_m2",
               "critical_density_ppm2", "risk_thresholds"}
    for k, v in payload.items():
        if k in allowed:
            SETTINGS[k] = v
    SETTINGS["privacy_mode"] = True  # non-negotiable
    get_detector().set_confidence(float(SETTINGS["detection_confidence"]))
    return SETTINGS


# ---------------------------------------------------------------- websocket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "connected", "data": None}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clients.discard(websocket)
    except Exception:
        _clients.discard(websocket)
