"""In-memory analysis session: runs the CV pipeline in a background thread,
keeps the latest metrics + a rolling history, splits the frame into vertical
zones, and raises alerts when a zone goes RED/BLACK.
"""
from __future__ import annotations
import threading
import time
from collections import deque

from cv.pipeline import analyze_video
from cv.risk import risk_level
import store

# Simple fixed zones = vertical bands across the frame (left -> right).
ZONE_NAMES = ["Zone A", "Zone B", "Zone C", "Main Exit"]
ALERT_LEVELS = {"RED", "BLACK"}


class AnalysisState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.status = "idle"          # idle | processing | completed | stopped | error
        self.video_id: str | None = None
        self.video_path: str | None = None
        self.detector_backend: str | None = None
        self.started_at: float | None = None
        self.error: str | None = None
        self.fps: float | None = None
        self.frame_count: int | None = None
        self.frames_processed = 0
        self.latest: dict | None = None
        self.history: deque[dict] = deque(maxlen=600)
        self.zones: list[dict] = [dict(name=n, people=0, density=0.0, score=0.0, level="GREEN")
                                  for n in ZONE_NAMES]
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ---- snapshots for the API ----
    def status_dict(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "video_id": self.video_id,
                "detector_backend": self.detector_backend,
                "started_at": self.started_at,
                "fps": self.fps,
                "frame_count": self.frame_count,
                "frames_processed": self.frames_processed,
                "error": self.error,
                "has_data": self.latest is not None,
            }

    def metrics_dict(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "latest": self.latest,
                "history": list(self.history),
                "zones": self.zones,
            }


state = AnalysisState()


def _zone_of(cx_norm: float) -> int:
    return min(len(ZONE_NAMES) - 1, max(0, int(cx_norm * len(ZONE_NAMES))))


def _update_zones(boxes, frame_w, zone_area_m2, critical_ppm2) -> list[dict]:
    from cv.density import density_ppm2, density_risk
    from cv.risk import RiskFactors, compute
    counts = [0] * len(ZONE_NAMES)
    for (x1, y1, x2, y2, c) in boxes:
        cx = ((x1 + x2) / 2) / max(1.0, frame_w)
        counts[_zone_of(cx)] += 1
    zarea = max(1.0, zone_area_m2 / len(ZONE_NAMES))
    zones = []
    for name, n in zip(ZONE_NAMES, counts):
        d = density_ppm2(n, zarea)
        r = compute(RiskFactors(density=density_risk(d, critical_ppm2)))
        zones.append({"name": name, "people": n, "density": d,
                      "score": r["score"], "level": r["level"]})
    return zones


def start(video_id: str, video_path: str, *, settings: dict, publish) -> None:
    with state.lock:
        if state.status == "processing":
            return
        state.reset()
        state.status = "processing"
        state.video_id = video_id
        state.video_path = video_path
        state.started_at = time.time()
    state._stop.clear()
    t = threading.Thread(target=_run, args=(video_path, settings, publish), daemon=True)
    state._thread = t
    t.start()


def stop() -> None:
    state._stop.set()
    with state.lock:
        if state.status == "processing":
            state.status = "stopped"


def _run(video_path: str, settings: dict, publish) -> None:
    from cv.detector import get_detector
    zone_area = float(settings.get("zone_area_m2", 100.0))
    critical = float(settings.get("critical_density_ppm2", 5.0))
    conf = float(settings.get("detection_confidence", 0.35))
    sample_every = max(1, int(settings.get("analysis_sample_every_n", 3)))
    get_detector().set_confidence(conf)

    try:
        for msg in analyze_video(video_path, zone_area_m2=zone_area, critical_ppm2=critical,
                                 sample_every_n=sample_every):
            if state._stop.is_set():
                break
            if msg["kind"] == "meta":
                with state.lock:
                    state.fps = msg["fps"]
                    state.frame_count = msg["frame_count"]
                    state.detector_backend = msg["detector_backend"]
                    if not msg["detector_available"]:
                        state.status = "error"
                        state.error = "No detector available (install ultralytics or opencv HOG)."
                publish("status", state.status_dict())
                if state.status == "error":
                    return
            elif msg["kind"] == "frame":
                frame_w = 1.0
                # boxes are absolute px; approximate width from max x2
                if msg["boxes"]:
                    frame_w = max(b[2] for b in msg["boxes"]) or 1.0
                zones = _update_zones(msg["boxes"], frame_w * 1.05, zone_area, critical)
                with state.lock:
                    state.frames_processed += 1
                    state.latest = msg
                    state.history.append({k: msg[k] for k in (
                        "t_offset_sec", "people_count", "density_ppm2", "mean_motion",
                        "turbulence", "score", "level")})
                    state.zones = zones
                publish("metrics", {"latest": msg, "zones": zones})
                _maybe_alert(msg, zones, publish)
            elif msg["kind"] == "done":
                with state.lock:
                    if state.status == "processing":
                        state.status = "completed"
                    state.frames_processed = msg["frames_processed"]
                publish("status", state.status_dict())
    except Exception as e:  # noqa: BLE001
        with state.lock:
            state.status = "error"
            state.error = str(e)
        publish("status", state.status_dict())


def _maybe_alert(msg: dict, zones: list[dict], publish) -> None:
    # Alert on the highest-risk zone when it enters RED/BLACK and wasn't already.
    hot = max(zones, key=lambda z: z["score"]) if zones else None
    overall_level = msg["level"]
    if overall_level in ALERT_LEVELS:
        zone_name = hot["name"] if hot and hot["score"] >= msg["score"] * 0.6 else "Overall Crowd"
        last = store.last_active_level_for_zone(zone_name)
        if last == overall_level:
            return
        reason = _reason(msg)
        alert = store.add_alert(zone_name, overall_level, msg["score"], reason, msg["factors"])
        publish("alert", alert)


def _reason(msg: dict) -> str:
    parts = []
    f = msg["factors"]
    if f.get("density", 0) >= 55:
        parts.append("high crowd density")
    if f.get("movement", 0) >= 55:
        parts.append("increasing movement turbulence")
    if f.get("density_increase", 0) >= 45:
        parts.append("rapid crowd build-up")
    if f.get("compression", 0) >= 45:
        parts.append("crowd compression")
    return ("High risk from " + ", ".join(parts) + ".") if parts else \
        f"Crowd risk score reached {msg['score']:.0f}."
