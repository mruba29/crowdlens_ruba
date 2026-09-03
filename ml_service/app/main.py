"""CROWDLENS ML service — FastAPI on :8001.

Endpoints
  GET  /health            detector availability + backend name
  POST /analyze           multipart video upload -> SSE stream of per-frame results
  POST /analyze/path      { "path": "..." } for a video already on disk -> SSE stream

Privacy: this service performs person DETECTION and anonymous TRACKING only.
No face detection, no recognition, no identity. Track IDs are ephemeral ints.
"""
from __future__ import annotations
import json
import os
import tempfile
import time

from fastapi import FastAPI, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.pipeline import analyze_video, get_detector

app = FastAPI(title="CROWDLENS ML Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_START = time.time()


@app.get("/health")
def health():
    det = get_detector()
    status = "operational" if det.available and not det.degraded else (
        "degraded" if det.available else "offline"
    )
    return {
        "service": "crowdlens-ml",
        "status": status,
        "detector_backend": det.backend,
        "detector_available": det.available,
        "degraded": det.degraded,
        "capabilities": {
            "detection": det.available,
            "tracking": det.available,
            "optical_flow": True,
            "pose_estimation": False,
        },
        "uptime_sec": round(time.time() - _START, 1),
        "note": None if det.available else
        "No detector available. Install ultralytics or opencv HOG support to enable inference.",
    }


def _sse(gen):
    for item in gen:
        yield f"data: {json.dumps(item)}\n\n"


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), sample_every_n: int = 3,
                  max_frames: int = 600, zone_area_m2: float = 120.0):
    suffix = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read())
        tmp.close()
        gen = analyze_video(tmp.name, sample_every_n, max_frames, zone_area_m2)
        return StreamingResponse(_sse(gen), media_type="text/event-stream")
    finally:
        # temp file kept alive for the stream; OS temp dir is cleaned periodically.
        pass


@app.post("/analyze/path")
def analyze_path(payload: dict = Body(...)):
    path = payload.get("path")
    sample_every_n = int(payload.get("sample_every_n", 3))
    max_frames = int(payload.get("max_frames", 600))
    zone_area_m2 = float(payload.get("zone_area_m2", 120.0))
    if not path or not os.path.exists(path):
        return {"error": f"path not found: {path}"}
    gen = analyze_video(path, sample_every_n, max_frames, zone_area_m2)
    return StreamingResponse(_sse(gen), media_type="text/event-stream")
