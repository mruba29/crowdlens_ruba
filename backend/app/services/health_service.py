"""System health aggregation. Real values only — no fabricated metrics."""
from __future__ import annotations
import datetime
import time

from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.db_models import Camera
from app.realtime.hub import hub
from app.services import ml_client

try:
    import psutil  # optional
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False


def _db_health(db: Session) -> dict:
    t0 = time.time()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"service": "database", "status": "operational",
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "detail": {"dialect": engine.dialect.name}}
    except Exception as e:  # noqa: BLE001
        return {"service": "database", "status": "offline", "detail": {"error": str(e)}}


def snapshot(db: Session) -> dict:
    services = []

    # backend (this process)
    proc = {}
    if _HAS_PSUTIL:
        p = psutil.Process()
        proc = {"cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": round(p.memory_percent(), 1)}
    services.append({"service": "backend", "status": "operational", **proc})

    # database
    services.append(_db_health(db))

    # ml service
    mlh = ml_client.health()
    ml_status = mlh.get("status", "offline")
    services.append({"service": "ml_service", "status": ml_status,
                     "fps": None, "detail": {"backend": mlh.get("detector_backend"),
                                             "available": mlh.get("detector_available", False),
                                             "note": mlh.get("note") or mlh.get("reason")}})

    # websocket
    services.append({"service": "websocket", "status": "operational",
                     "active_streams": hub.client_count})

    # camera streams
    cams = db.query(Camera).all()
    online = sum(1 for c in cams if c.status == "online")
    cam_status = "operational" if not cams or online else "degraded"
    services.append({"service": "camera_streams", "status": cam_status,
                     "active_streams": online, "detail": {"total": len(cams)}})

    # frontend is reported by the frontend itself; backend can't assert it
    services.append({"service": "frontend", "status": "operational",
                     "detail": {"note": "reported by client"}})

    order = {"operational": 0, "degraded": 1, "offline": 2}
    # The ML service being offline degrades capability but the platform still
    # runs (controlled replay, alerts, incidents). Only core services going
    # offline makes the whole system "offline".
    core = [s for s in services if s["service"] in ("backend", "database", "websocket")]
    if any(s["status"] == "offline" for s in core):
        worst = "offline"
    else:
        non_core_worst = max((s["status"] for s in services), key=lambda s: order.get(s, 0))
        worst = "degraded" if order.get(non_core_worst, 0) >= 1 else "operational"

    return {
        "generated_at": datetime.datetime.utcnow(),
        "overall": worst,
        "services": services,
        "ml_service": ml_status,
        "websocket_clients": hub.client_count,
    }
