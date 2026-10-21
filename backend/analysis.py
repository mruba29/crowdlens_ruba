"""In-memory analysis session: runs the CV pipeline in a background thread,
keeps the latest metrics + a rolling history, splits the frame into vertical
zones, and raises alerts when a zone goes RED/BLACK.

Phase 2 adds real zone-aware crowd analytics (density/occupancy/accumulation/
inflow-outflow/bottleneck) for whichever video is attached to an Event zone —
see zone_metrics_dict(). A video with no zone attachment behaves exactly as
before; this is additive, not a redesign.
"""
from __future__ import annotations
import threading
import time
from collections import deque

from cv.pipeline import analyze_video
from cv.risk import risk_level
from cv.tracker import ByteStyleTracker
from cv.flow import FlowCounter
from cv.dynamics import (
    direction_entropy, reverse_flow_ratio, edge_pressure_proxy, StopWaveDetector,
    classify_dynamic_state, rollup_state, draw_overlay,
)
from cv.sri import (
    demographic_estimate, vulnerability_proxy, fallen_person_flag,
    SRIComponents, compute_sri, detect_early_warnings,
)
import store

# Simple fixed zones = vertical bands across the frame (left -> right).
ZONE_NAMES = ["Zone A", "Zone B", "Zone C", "Main Exit"]
ALERT_LEVELS = {"RED", "BLACK"}

# Zone roles for which inflow/outflow gate-crossing counting is meaningful at
# all — a "general" or "restricted" zone has no gate to count crossings on.
FLOW_ROLES = {"entrance", "exit", "bottleneck"}
# minimum elapsed analysis time before a flow rate is reported, rather than
# an early, noisy instantaneous number
FLOW_WARMUP_SEC = 5.0
# how many recent density samples to compare against earlier ones for the
# accumulation trend call (same recent-vs-earlier-average method the
# frontend's riskTrend() already uses, so the two never disagree in spirit)
_TREND_WINDOW = 10


class AnalysisState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self._pause = threading.Event()
        self.queue: list[dict] = []
        self._publish = None
        self.reset()

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set()

    def queue_add(self, video_specs: list) -> None:
        with self.lock:
            for item in video_specs:
                if isinstance(item, str):
                    self.queue.append({"video_id": item})
                else:
                    self.queue.append(item)

    def cancel_queued(self, video_id: str) -> bool:
        with self.lock:
            initial = len(self.queue)
            self.queue = [q for q in self.queue if (q.get("video_id") if isinstance(q, dict) else q) != video_id]
            return len(self.queue) < initial

    def pause(self) -> None:
        self._pause.set()
        with self.lock:
            if self.status == "processing":
                self.status = "paused"

    def resume(self) -> None:
        self._pause.clear()
        with self.lock:
            if self.status == "paused":
                self.status = "processing"


    def reset(self) -> None:
        self.status = "idle"          # idle | processing | paused | completed | stopped | error
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
        self._pause.clear()

        # ---- Phase 2: real Event-zone context for the video being analyzed,
        # resolved once in start(). None whenever the video isn't attached to
        # an event zone — every zone-analytics field then reports "not
        # available" instead of guessing. ----
        self.event_id: str | None = None
        self.zone_id: str | None = None
        self.zone_name: str | None = None
        self.zone_role: str | None = None
        self.zone_area_m2: float | None = None
        self.zone_capacity: int | None = None
        self.inflow_direction: str = "right"
        self._tracker: ByteStyleTracker | None = None
        self._flow: FlowCounter | None = None
        self._density_hist: deque[tuple[float, float]] = deque(maxlen=_TREND_WINDOW)
        self.zone_metrics: dict | None = None

        # ---- Phase 3: crowd-dynamics module. The tracker above is now
        # created for every analysis (not just flow-role zones) since
        # direction entropy / reverse-flow need it regardless of zone role;
        # FlowCounter stays zone+role-gated exactly as in Phase 2. ----
        self.spatial_context: str | None = None   # from the attached zone, operator-declared
        self._stopwave: StopWaveDetector | None = None
        self._dynamic_state_prev: str | None = None
        # debounce: require the same raw per-frame classification to repeat
        # a few times before it's reported/logged as a real state, so single-
        # frame noise doesn't spam the timeline with flicker
        self._pending_state: str | None = None
        self._pending_count = 0
        self.dynamics: dict | None = None

        # ---- Phase 4: demographic vulnerability + the SRI risk engine ----
        self.demo_children_pct: float | None = None
        self.demo_adults_pct: float | None = None
        self.demo_elderly_pct: float | None = None
        self._prev_turbulence: float | None = None
        self._prev_compression: float | None = None
        self._active_alert_types: set[str] = set()
        self.sri: dict | None = None

    def zone_metrics_dict(self) -> dict:
        with self.lock:
            return self.zone_metrics or {"available": False, "reason": "no_active_analysis"}

    def dynamics_dict(self) -> dict:
        with self.lock:
            return self.dynamics or {"available": False, "reason": "no_active_analysis"}

    def sri_dict(self) -> dict:
        with self.lock:
            return self.sri or {"available": False, "reason": "no_active_analysis"}

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
                "is_paused": self._pause.is_set(),
                "queue_length": len(self.queue),
                "queue": [q["video_id"] for q in self.queue],
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


def _update_zone_metrics(msg: dict, frame_w: float, tracks: dict) -> dict:
    """Real, honestly-labeled zone analytics for whichever video is attached
    to an Event zone. Every field either comes from an actual computation on
    this frame's real detections, or reports why it can't yet — never a
    fabricated number. See cv/flow.py and the Phase 2 report for what each
    signal's real CV source is."""
    if not state.zone_id:
        return {"available": False, "reason": "not_zone_attached"}

    from cv.density import density_ppm2

    people = msg["people_count"]
    area = state.zone_area_m2 or 100.0
    density = density_ppm2(people, area)

    capacity = state.zone_capacity or 0
    occupancy_pct = round((people / capacity) * 100.0, 1) if capacity > 0 else None

    # accumulation: recent-vs-earlier average density over a short rolling
    # window, same method the frontend's riskTrend() already uses.
    state._density_hist.append((msg["t_offset_sec"], density))
    trend = "not_available"
    accumulation_rate = None
    if len(state._density_hist) >= 4:
        vals = [d for _, d in state._density_hist]
        half = max(2, len(vals) // 2)
        earlier_avg = sum(vals[:half]) / half
        recent_avg = sum(vals[-half:]) / half
        delta = recent_avg - earlier_avg
        t0, d0 = state._density_hist[0]
        t1, d1 = state._density_hist[-1]
        dt_min = max(1e-6, (t1 - t0) / 60.0)
        accumulation_rate = round((d1 - d0) / dt_min, 3)
        trend = "increasing" if delta > 0.15 else "decreasing" if delta < -0.15 else "stable"

    # inflow/outflow: only meaningful on a gate-role zone, and only once a
    # real tracker has had a moment to build up crossing events.
    flow = {"supported": False, "reason": "zone_role_not_flow_relevant",
            "inflow_direction": state.inflow_direction, "inflow_rate_per_min": None,
            "outflow_rate_per_min": None, "flow_imbalance_per_min": None, "accumulation_risk": False}
    if state.zone_role in FLOW_ROLES and state._flow is not None:
        state._flow.update(msg["t_offset_sec"], tracks, frame_w)
        elapsed = time.time() - (state.started_at or time.time())
        if elapsed < FLOW_WARMUP_SEC:
            flow = {"supported": True, "reason": "requires_calibration",
                    "inflow_direction": state.inflow_direction, "inflow_rate_per_min": None,
                    "outflow_rate_per_min": None, "flow_imbalance_per_min": None, "accumulation_risk": False}
        else:
            r = state._flow.rates(state.inflow_direction)
            imbalance = round(r["inflow_rate_per_min"] - r["outflow_rate_per_min"], 1)
            flow = {"supported": True, "reason": None, "inflow_direction": state.inflow_direction,
                    "inflow_rate_per_min": r["inflow_rate_per_min"],
                    "outflow_rate_per_min": r["outflow_rate_per_min"],
                    "flow_imbalance_per_min": imbalance, "accumulation_risk": imbalance > 0,
                    "total_in": r["total_in"], "total_out": r["total_out"]}

    bottleneck_flagged = state.zone_role == "bottleneck" and (
        trend == "increasing" or flow.get("accumulation_risk") is True)

    dom_deg = msg.get("flow_direction_deg")
    return {
        "available": True, "reason": None,
        "video_id": state.video_id, "event_id": state.event_id,
        "zone_id": state.zone_id, "zone_name": state.zone_name, "zone_role": state.zone_role,
        "people_count": people,
        "zone_area_m2": area, "density_ppm2": density, "density_status": "ok",
        "capacity": capacity or None, "occupancy_pct": occupancy_pct,
        "occupancy_status": "ok" if capacity > 0 else "not_available",
        "accumulation_rate_ppm2_per_min": accumulation_rate, "accumulation_trend": trend,
        "flow": flow,
        "bottleneck": {"is_bottleneck_zone": state.zone_role == "bottleneck", "flagged": bottleneck_flagged},
        "dominant_direction_deg": dom_deg,
        "dominant_direction_confidence": msg.get("flow_direction_confidence"),
        "dominant_direction_status": "ok" if dom_deg is not None else "not_available",
    }


def _update_dynamics(msg: dict, frame_w: float, frame_h: float, tracks: dict, zmetrics: dict) -> dict:
    """Crowd Dynamics module (Phase 3): flow features, compression/edge
    proxies, a possible-stop-wave signal, and the rule-based dynamic-state
    classifier — all from real per-frame signals already computed this frame
    (see cv/dynamics.py). Available for any active analysis, zone-attached or
    not; spatial_context specifically comes from the zone (operator-declared),
    never inferred frame-by-frame."""
    people = msg["people_count"]
    mean_motion = msg["mean_motion"]
    turbulence = msg["turbulence"]
    dom_deg = msg.get("flow_direction_deg")
    dom_conf = msg.get("flow_direction_confidence")

    entropy = direction_entropy(tracks) if tracks else None
    rev_ratio = reverse_flow_ratio(tracks, dom_deg) if tracks else None
    edge_p = edge_pressure_proxy(msg["boxes"], frame_w, frame_h)
    compression_proxy = msg["factors"].get("compression", 0.0)  # 0-100, real (cv/risk.py)

    sw = state._stopwave.update(msg["t_offset_sec"], mean_motion) if state._stopwave else {"possible_stop_wave": False}

    accum_trend = zmetrics.get("accumulation_trend") if zmetrics.get("available") else None
    accum_rate = zmetrics.get("accumulation_rate_ppm2_per_min") if zmetrics.get("available") else None
    flow_imbalance = None
    if zmetrics.get("available"):
        f = zmetrics.get("flow") or {}
        if f.get("reason") is None:
            flow_imbalance = f.get("flow_imbalance_per_min")

    raw_state, reasons = classify_dynamic_state(
        mean_motion=mean_motion, turbulence=turbulence, compression_proxy=compression_proxy,
        reverse_ratio=rev_ratio, accumulation_trend=accum_trend, flow_imbalance=flow_imbalance,
        stop_wave=sw, people_count=people,
    )

    # debounce: only adopt the new raw classification once it has repeated
    # for a few consecutive frames, so a single anomalous frame doesn't read
    # as a state change on the timeline.
    if raw_state == state._pending_state:
        state._pending_count += 1
    else:
        state._pending_state = raw_state
        state._pending_count = 1
    dyn_state = raw_state if state._pending_count >= 3 or state._dynamic_state_prev is None \
        else state._dynamic_state_prev

    roll = rollup_state(dyn_state, msg["level"])

    if dyn_state != state._dynamic_state_prev and state.video_id:
        try:
            store.add_dynamics_event(
                video_id=state.video_id, zone_id=state.zone_id, zone_name=state.zone_name,
                t_offset_sec=msg["t_offset_sec"], dynamic_state=dyn_state, rollup_state=roll,
                previous_state=state._dynamic_state_prev, contributing_signals=reasons,
            )
        except Exception:  # noqa: BLE001 — never let history logging break analysis
            pass
        state._dynamic_state_prev = dyn_state

    return {
        "available": True,
        "mean_velocity": mean_motion, "velocity_variance": turbulence,
        "dominant_direction_deg": dom_deg, "dominant_direction_confidence": dom_conf,
        "direction_entropy": entropy,
        "direction_entropy_status": "ok" if entropy is not None else "not_available",
        "reverse_flow_ratio": rev_ratio,
        "reverse_flow_status": "ok" if rev_ratio is not None else "not_available",
        "flow_imbalance_per_min": flow_imbalance,
        "accumulation_rate_ppm2_per_min": accum_rate, "accumulation_trend": accum_trend or "not_available",
        "compression_proxy": round(compression_proxy, 1),
        "interpersonal_distance_m": msg.get("interpersonal_distance_m"),
        "compression_disclaimer": "Proxy from interpersonal spacing — not a physical pressure measurement.",
        "edge_pressure_proxy": edge_p,
        "edge_pressure_status": "ok" if edge_p is not None else "not_available",
        "edge_pressure_elevated": bool(edge_p is not None and edge_p >= 0.35),
        "edge_pressure_disclaimer": "Proxy for detections concentrated near the camera's frame boundary — not a calibrated physical barrier.",
        "stop_wave": sw,
        "dynamic_state": dyn_state, "contributing_signals": reasons,
        "rollup_state": roll,
        "spatial_context": state.spatial_context,
        "spatial_context_status": "ok" if state.spatial_context else "not_zone_attached",
    }


def _update_sri(msg: dict, critical_ppm2: float, zmetrics: dict, dynamics: dict) -> dict:
    """Phase 4: demographic estimate, vulnerability proxy, the 10-input SRI
    engine, and the 10 early-warning alert types — all from this frame's real
    signals (already computed above) plus the operator-configured event
    demographic composition, if any. Fires alerts into the same `alerts`
    table the base risk score already uses (edge-triggered: a stored alert
    row is only created the moment a signal starts firing, not every frame
    it stays elevated)."""
    people = msg["people_count"]
    f = msg["factors"]  # 0-100 density/movement/compression from cv/risk.py, real

    demo = demographic_estimate(people, state.demo_children_pct, state.demo_adults_pct, state.demo_elderly_pct)
    vuln = vulnerability_proxy(state.demo_children_pct, state.demo_elderly_pct,
                                f.get("density", 0.0), f.get("compression", 0.0))

    fallen = fallen_person_flag(msg["boxes"])

    zone_avail = zmetrics.get("available", False)
    flow = zmetrics.get("flow") if zone_avail else None
    flow_ok = bool(flow and flow.get("reason") is None)

    entropy = dynamics.get("direction_entropy")
    reverse = dynamics.get("reverse_flow_ratio")
    edge = dynamics.get("edge_pressure_proxy")

    comp = SRIComponents(
        density=f.get("density", 0.0),
        flow_imbalance=min(100.0, max(0.0, (flow["flow_imbalance_per_min"] or 0) * 10)) if flow_ok else 0.0,
        accumulation=f.get("density_increase", 0.0),
        velocity_variance=min(100.0, (msg["turbulence"] / 15.0) * 100.0),
        direction_conflict=(entropy * 100.0) if entropy is not None else 0.0,
        reverse_flow=(reverse * 100.0) if reverse is not None else 0.0,
        compression=f.get("compression", 0.0),
        edge_pressure=(edge * 100.0) if edge is not None else 0.0,
        fallen_person=100.0 if fallen else 0.0,
        vulnerability=vuln.get("score") or 0.0,
        available={
            "density": True, "flow_imbalance": flow_ok, "accumulation": True,
            "velocity_variance": True, "direction_conflict": entropy is not None,
            "reverse_flow": reverse is not None, "compression": True,
            "edge_pressure": edge is not None, "fallen_person": True,
            "vulnerability": vuln.get("available", False),
        },
    )
    sri = compute_sri(comp)

    zone_name = zmetrics.get("zone_name") if zone_avail else "Overall Crowd"
    warnings = detect_early_warnings(
        density_ppm2=zmetrics.get("density_ppm2") if zone_avail else None, critical_ppm2=critical_ppm2,
        flow_supported=bool(flow and flow.get("supported")),
        inflow_rate=flow.get("inflow_rate_per_min") if flow_ok else None,
        outflow_rate=flow.get("outflow_rate_per_min") if flow_ok else None,
        flow_imbalance=flow.get("flow_imbalance_per_min") if flow_ok else None,
        accumulation_trend=zmetrics.get("accumulation_trend") if zone_avail else None,
        accumulation_rate=zmetrics.get("accumulation_rate_ppm2_per_min") if zone_avail else None,
        turbulence=msg["turbulence"], prev_turbulence=state._prev_turbulence,
        reverse_ratio=reverse, compression_proxy=f.get("compression", 0.0),
        prev_compression=state._prev_compression,
        edge_pressure=edge,
        is_bottleneck_zone=bool(zone_avail and zmetrics.get("bottleneck", {}).get("is_bottleneck_zone")),
        bottleneck_flagged=bool(zone_avail and zmetrics.get("bottleneck", {}).get("flagged")),
        fallen=fallen, zone_name=zone_name or "Overall Crowd", sri_level=sri["level"],
    )
    state._prev_turbulence = msg["turbulence"]
    state._prev_compression = f.get("compression", 0.0)

    now_firing = {w["alert_type"] for w in warnings}
    for w in warnings:
        if w["alert_type"] not in state._active_alert_types:
            try:
                store.add_alert(w["zone"], w["severity"], sri["sri"],
                                 f"{w['alert_type'].replace('_', ' ').title()}: {'; '.join(w['trigger_signals'])}",
                                 {c["factor"]: c["value"] for c in sri["contributions"]},
                                 alert_type=w["alert_type"], recommended_action=w["recommended_action"],
                                 video_id=state.video_id)
            except Exception:  # noqa: BLE001
                pass
    state._active_alert_types = now_firing

    return {
        "available": True, "sri": sri["sri"], "level": sri["level"], "label": sri["label"],
        "contributions": sri["contributions"], "notable_signals": sri["notable_signals"],
        "demographic_estimate": demo, "vulnerability": vuln,
        "active_alert_types": sorted(now_firing),
        "disclaimer": "Early signals feeding a multi-input engine — never a single-signal "
                       "stampede detection.",
    }


def start(video_id: str, video_path: str, *, settings: dict, publish) -> None:
    # resolve real Event-zone context (Phase 1 data) for this video, if any —
    # done outside the lock since it hits the DB.
    vsrc = store.get_video_source(video_id)
    zone = store.get_zone(vsrc["zone_id"]) if vsrc and vsrc.get("zone_id") else None
    event = store.get_event(vsrc["event_id"]) if vsrc and vsrc.get("event_id") else None

    with state.lock:
        if state.status == "processing":
            return
        state.reset()
        state.status = "processing"
        state.video_id = video_id
        state.video_path = video_path
        state.started_at = time.time()
        state._publish = publish
        # Phase 3: tracker + stop-wave detector run for every analysis, zone
        # or not — dynamics is a general capability, unlike occupancy/inflow
        # which genuinely need a configured zone.
        state._tracker = ByteStyleTracker()
        state._stopwave = StopWaveDetector()
        if vsrc:
            state.event_id = vsrc["event_id"]
            state.inflow_direction = vsrc.get("inflow_direction") or "right"
        if event:
            state.demo_children_pct = event.get("demo_children_pct")
            state.demo_adults_pct = event.get("demo_adults_pct")
            state.demo_elderly_pct = event.get("demo_elderly_pct")
        if zone:
            state.zone_id = zone["id"]
            state.zone_name = zone["name"]
            state.zone_role = zone["role"]
            state.zone_area_m2 = zone["area_m2"]
            state.zone_capacity = zone["capacity"]
            state.spatial_context = zone.get("spatial_context") or "open"
            if zone["role"] in FLOW_ROLES:
                state._flow = FlowCounter()
    state._stop.clear()
    state._pause.clear()
    t = threading.Thread(target=_run, args=(video_path, settings, publish), daemon=True)
    state._thread = t
    t.start()


def stop() -> None:
    state._stop.set()
    state._pause.clear()
    with state.lock:
        if state.status in ("processing", "paused"):
            state.status = "stopped"
    if state._publish:
        state._publish("status", state.status_dict())


def pause() -> None:
    state._pause.set()
    with state.lock:
        if state.status == "processing":
            state.status = "paused"
    if state._publish:
        state._publish("status", state.status_dict())


def resume() -> None:
    state._pause.clear()
    with state.lock:
        if state.status == "paused":
            state.status = "processing"
    if state._publish:
        state._publish("status", state.status_dict())


def replay(video_id: str, video_path: str, *, settings: dict, publish) -> dict:
    stop()
    time.sleep(0.15)
    start(video_id, video_path, settings=settings, publish=publish)
    store.update_video_metrics(video_id, status="processing", people=None, density=None, score=None, level=None)
    return state.status_dict()


def batch_start(video_specs: list[dict], *, settings: dict, publish) -> dict:
    """Start analysis on the first video and queue the remaining videos."""
    with state.lock:
        for spec in video_specs:
            store.update_video_metrics(spec["video_id"], status="queued", people=None, density=None, score=None, level=None)
        
        is_idle = state.status in ("idle", "completed", "stopped", "error")
        if is_idle and video_specs:
            first = video_specs[0]
            state.queue = list(video_specs[1:])
            # release lock before calling start
        else:
            state.queue.extend(video_specs)
            first = None

    if first:
        start(first["video_id"], first["video_path"], settings=settings, publish=publish)
        store.update_video_metrics(first["video_id"], status="processing", people=None, density=None, score=None, level=None)

    publish("status", state.status_dict())
    return state.status_dict()


def cancel_queued(video_id: str, publish) -> dict:
    with state.lock:
        state.queue = [q for q in state.queue if q["video_id"] != video_id]
        is_active = (state.video_id == video_id and state.status in ("processing", "paused"))
    if is_active:
        stop()
    store.update_video_metrics(video_id, status="uploaded", people=None, density=None, score=None, level=None)
    publish("status", state.status_dict())
    return state.status_dict()


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
            while state._pause.is_set() and not state._stop.is_set():
                time.sleep(0.1)
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
                frame_w, frame_h = 1.0, 1.0
                # boxes are absolute px; approximate frame size from the boxes
                # themselves (cv/pipeline.py doesn't pass raw dimensions through)
                if msg["boxes"]:
                    frame_w = max(b[2] for b in msg["boxes"]) or 1.0
                    frame_h = max(b[3] for b in msg["boxes"]) or 1.0
                zones = _update_zones(msg["boxes"], frame_w * 1.05, zone_area, critical)
                tracks = state._tracker.update(msg["boxes"]) if state._tracker else {}
                zmetrics = _update_zone_metrics(msg, frame_w, tracks)
                dynamics = _update_dynamics(msg, frame_w * 1.05, frame_h * 1.05, tracks, zmetrics)
                if msg.get("annotated_frame"):
                    msg["annotated_frame"] = draw_overlay(
                        msg["annotated_frame"], dominant_deg=dynamics["dominant_direction_deg"],
                        dominant_conf=dynamics["dominant_direction_confidence"],
                        reverse_ratio=dynamics["reverse_flow_ratio"],
                        compression_proxy=dynamics["compression_proxy"],
                        edge_pressure=dynamics["edge_pressure_proxy"],
                        dynamic_state=dynamics["dynamic_state"],
                    )
                sri = _update_sri(msg, critical, zmetrics, dynamics)
                with state.lock:
                    state.frames_processed += 1
                    state.latest = msg
                    state.history.append({k: msg[k] for k in (
                        "t_offset_sec", "people_count", "density_ppm2", "mean_motion",
                        "turbulence", "score", "level")} | (
                        {"zone_metrics": zmetrics} if zmetrics.get("available") else {}) | (
                        {"dynamics": dynamics} if dynamics.get("available") else {}) | (
                        {"sri": sri} if sri.get("available") else {}))
                    state.zones = zones
                    state.zone_metrics = zmetrics
                    state.dynamics = dynamics
                    state.sri = sri
                publish("metrics", {"latest": msg, "zones": zones, "zone_metrics": zmetrics,
                                    "dynamics": dynamics, "sri": sri})
                _maybe_alert(msg, zones, publish)
            elif msg["kind"] == "done":
                with state.lock:
                    if state.status in ("processing", "paused"):
                        state.status = "completed"
                    state.frames_processed = msg["frames_processed"]
                    latest_snap = state.latest
                    zones_snap = state.zones
                    dyn_snap = state.dynamics
                    sri_snap = state.sri
                    hist_snap = list(state.history)
                    vid = state.video_id

                if vid and latest_snap:
                    summary = {
                        "history": hist_snap[-180:],
                        "zones": zones_snap,
                        "dynamics": dyn_snap,
                        "sri": sri_snap,
                        "frames_processed": msg.get("frames_processed", 0),
                    }
                    store.update_video_metrics(
                        vid,
                        status="completed",
                        people=latest_snap.get("people_count"),
                        density=latest_snap.get("density_ppm2"),
                        score=latest_snap.get("score"),
                        level=latest_snap.get("level"),
                        metrics_summary=summary,
                    )
                publish("status", state.status_dict())

                # Check queue for next video
                next_item = None
                with state.lock:
                    if state.queue:
                        next_item = state.queue.pop(0)
                if next_item:
                    time.sleep(0.3)
                    start(next_item["video_id"], next_item["video_path"], settings=settings, publish=publish)
                return
    except Exception as e:  # noqa: BLE001
        with state.lock:
            state.status = "error"
            state.error = str(e)
            vid = state.video_id
        if vid:
            store.update_video_metrics(vid, status="failed", people=None, density=None, score=None, level=None)
        publish("status", state.status_dict())
        next_item = None
        with state.lock:
            if state.queue:
                next_item = state.queue.pop(0)
        if next_item:
            time.sleep(0.5)
            start(next_item["video_id"], next_item["video_path"], settings=settings, publish=publish)


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
