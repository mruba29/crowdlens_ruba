"""Crowd Dynamics module — signals and a rule-based state classifier built on
top of the real per-frame CV output (detections, optical flow, tracking).

Every function here either returns a real number computed from real detections
/ tracks / motion history, or None with the caller expected to report "not
available" — never a guessed value. Nothing here claims a physical
measurement: "Compression Proxy" and "Edge Pressure Proxy" are named that way
deliberately (see PHASE3_REPORT.md), and classify_dynamic_state() never
outputs anything resembling "stampede" — it feeds signals into the existing
risk engine, it does not replace it.
"""
from __future__ import annotations
import math
from collections import deque

DYNAMIC_STATES = ("STATIONARY", "FLOW", "DISTURBED", "VOLATILE", "REVERSE_FLOW", "STOP_WAVE")
ROLLUP_STATES = ("NORMAL", "FLOW", "DISTURBED", "HIGH_RISK")

# ---- thresholds (documented, not hidden — tune here, referenced in the report) ----
_MOTION_FLOOR = 0.15           # px/frame below this = not really moving
_TURBULENCE_DISTURBED = 4.0    # optical-flow magnitude variance
_TURBULENCE_VOLATILE = 9.0
_REVERSE_RATIO_STATE = 0.30    # >=30% of moving tracks opposing dominant direction
_COMPRESSION_VOLATILE = 60.0   # 0-100 compression proxy
_ENTROPY_MULTIDIRECTIONAL = 0.55  # 0-1 normalized direction entropy
_EDGE_PRESSURE_ELEVATED = 0.35    # fraction of detections near a frame edge
_STOPWAVE_DROP_RATIO = 0.6     # relative drop in motion to call a possible stop-wave
_STOPWAVE_SUSTAIN_SEC = 2.5    # prior motion must have been sustained at least this long


# --------------------------------------------------------------------------
# per-object signals (need the frame-to-frame tracker; None without it)
# --------------------------------------------------------------------------
def direction_entropy(tracks: dict[int, dict], n_bins: int = 8) -> float | None:
    """Shannon entropy (normalized 0-1) of moving tracks' headings. Low =
    everyone moving the same way (unidirectional); high = scattered
    (multidirectional). None when there's no meaningful sample of movers."""
    headings = []
    for t in tracks.values():
        vx, vy = t["velocity"]
        speed = math.hypot(vx, vy)
        if speed >= _MOTION_FLOOR:
            headings.append(math.degrees(math.atan2(vy, vx)) % 360)
    if len(headings) < 3:
        return None
    counts = [0] * n_bins
    for h in headings:
        counts[int(h / (360 / n_bins)) % n_bins] += 1
    total = len(headings)
    ent = -sum((c / total) * math.log2(c / total) for c in counts if c > 0)
    max_ent = math.log2(n_bins)
    return round(ent / max_ent, 3) if max_ent > 0 else 0.0


def reverse_flow_ratio(tracks: dict[int, dict], dominant_deg: float | None) -> float | None:
    """Fraction of moving tracks heading > 135 degrees away from the crowd's
    dominant direction. None when there's no dominant direction to compare
    against, or nobody is moving enough to judge."""
    if dominant_deg is None:
        return None
    moving = []
    for t in tracks.values():
        vx, vy = t["velocity"]
        speed = math.hypot(vx, vy)
        if speed >= _MOTION_FLOOR:
            moving.append(math.degrees(math.atan2(vy, vx)) % 360)
    if len(moving) < 3:
        return None
    reverse = 0
    for h in moving:
        diff = abs((h - dominant_deg + 180) % 360 - 180)
        if diff > 135:
            reverse += 1
    return round(reverse / len(moving), 3)


# --------------------------------------------------------------------------
# whole-frame signals (available for any active analysis, tracker or not)
# --------------------------------------------------------------------------
def edge_pressure_proxy(boxes: list, frame_w: float, frame_h: float, margin_frac: float = 0.12) -> float | None:
    """Fraction of detections whose centroid sits within `margin_frac` of any
    frame edge — a proxy for accumulation against whatever the camera framed
    at its boundary (a real wall/barricade only if the operator framed the
    shot that way; CROWDLENS has no calibrated boundary geometry to confirm
    that, so this is named — and must stay labeled — a proxy)."""
    if not boxes or frame_w <= 0 or frame_h <= 0:
        return None
    mx, my = frame_w * margin_frac, frame_h * margin_frac
    near = 0
    for (x1, y1, x2, y2, _c) in boxes:
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if cx < mx or cx > frame_w - mx or cy < my or cy > frame_h - my:
            near += 1
    return round(near / len(boxes), 3)


class StopWaveDetector:
    """Temporal-only: watches whole-frame mean motion for a sustained flow
    followed by a sharp, sudden drop. This is NOT spatial shockwave
    propagation tracking (CROWDLENS has no per-position velocity field over
    time) — it is a real, computed signal on the actual motion time series,
    honestly scoped as a *possible* stop-wave, never a confirmed one."""

    def __init__(self, window_sec: float = 6.0):
        self.window_sec = window_sec
        self._hist: deque[tuple[float, float]] = deque()

    def update(self, t: float, mean_motion: float) -> dict:
        self._hist.append((t, mean_motion))
        while self._hist and t - self._hist[0][0] > self.window_sec:
            self._hist.popleft()
        if len(self._hist) < 4:
            return {"possible_stop_wave": False, "reason": "insufficient_history"}

        # sustained motion = most of the window before "now" was flowing
        prior = [m for (ts, m) in self._hist if ts < t - 0.5]
        if len(prior) < 3:
            return {"possible_stop_wave": False, "reason": "insufficient_history"}
        sustained_sec = (self._hist[-2][0] - self._hist[0][0]) if len(self._hist) > 1 else 0.0
        prior_avg = sum(prior) / len(prior)
        current = mean_motion
        if prior_avg < _MOTION_FLOOR or sustained_sec < _STOPWAVE_SUSTAIN_SEC:
            return {"possible_stop_wave": False, "reason": "no_sustained_flow_to_compare"}

        drop_ratio = max(0.0, (prior_avg - current) / prior_avg)
        flagged = drop_ratio >= _STOPWAVE_DROP_RATIO
        return {
            "possible_stop_wave": flagged,
            "reason": None if flagged else "no_sharp_drop",
            "prior_avg_motion": round(prior_avg, 3),
            "current_motion": round(current, 3),
            "drop_ratio": round(drop_ratio, 3),
        }


# --------------------------------------------------------------------------
# classifier
# --------------------------------------------------------------------------
def classify_dynamic_state(*, mean_motion: float, turbulence: float,
                            compression_proxy: float, reverse_ratio: float | None,
                            accumulation_trend: str | None, flow_imbalance: float | None,
                            stop_wave: dict, people_count: int) -> tuple[str, list[str]]:
    """Deterministic priority cascade over real signals — checked most
    specific/urgent first. Returns (state, human-readable contributing
    reasons), the same explainability pattern analysis.py already uses for
    alerts. Never returns anything implying a confirmed incident."""
    reasons: list[str] = []

    if people_count == 0:
        return "STATIONARY", ["No people currently detected in this zone."]

    if stop_wave.get("possible_stop_wave"):
        reasons.append(f"Sharp motion drop after sustained flow ({round(stop_wave['drop_ratio'] * 100)}% decrease) — possible stop-wave.")
        if compression_proxy >= _COMPRESSION_VOLATILE:
            reasons.append("Compression proxy elevated at the same time.")
        return "STOP_WAVE", reasons

    if reverse_ratio is not None and reverse_ratio >= _REVERSE_RATIO_STATE:
        reasons.append(f"{round(reverse_ratio * 100)}% of tracked movement is opposing the dominant direction.")
        if compression_proxy >= _COMPRESSION_VOLATILE:
            reasons.append("Compression proxy elevated.")
        return "REVERSE_FLOW", reasons

    volatile_signals = 0
    if turbulence >= _TURBULENCE_VOLATILE:
        reasons.append("Movement turbulence sharply elevated.")
        volatile_signals += 1
    if compression_proxy >= _COMPRESSION_VOLATILE:
        reasons.append("Compression proxy elevated (interpersonal spacing reduced).")
        volatile_signals += 1
    if accumulation_trend == "increasing":
        reasons.append("Density accumulating (build-up trend).")
        volatile_signals += 1
    if flow_imbalance is not None and flow_imbalance > 0:
        reasons.append("Inflow exceeds outflow (flow imbalance positive).")
        volatile_signals += 1
    if volatile_signals >= 2:
        return "VOLATILE", reasons

    if turbulence >= _TURBULENCE_DISTURBED or volatile_signals == 1:
        if not reasons:
            reasons.append("Movement turbulence above normal.")
        return "DISTURBED", reasons

    if mean_motion < _MOTION_FLOOR:
        return "STATIONARY", ["Crowd present but not moving (motion below noise floor)."]

    return "FLOW", ["Coherent, steady movement — no elevated turbulence, compression, or imbalance."]


def draw_overlay(annotated_frame_b64: str, *, dominant_deg: float | None,
                  dominant_conf: float | None, reverse_ratio: float | None,
                  compression_proxy: float, edge_pressure: float | None,
                  dynamic_state: str) -> str:
    """Adds a Crowd Dynamics overlay (direction arrow, reverse-flow badge,
    compression/edge-pressure readout, state label) on top of the detection-box
    frame cv/pipeline.py already produced. Kept as a separate re-encode step
    so the base annotation pipeline (Phase 1/2, already tested) is untouched."""
    import base64
    import numpy as np
    import cv2

    try:
        header, b64data = annotated_frame_b64.split(",", 1)
        buf = np.frombuffer(base64.b64decode(b64data), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return annotated_frame_b64
    except Exception:  # noqa: BLE001
        return annotated_frame_b64

    h, w = img.shape[:2]
    state_colors = {
        "STATIONARY": (170, 170, 170), "FLOW": (120, 200, 80), "DISTURBED": (60, 200, 240),
        "VOLATILE": (60, 60, 240), "REVERSE_FLOW": (40, 140, 255), "STOP_WAVE": (140, 40, 160),
    }
    col = state_colors.get(dynamic_state, (200, 200, 200))

    # dominant-direction arrow from frame center, length scaled by confidence
    if dominant_deg is not None and dominant_conf:
        cx, cy = w // 2, h // 2
        length = int(min(w, h) * 0.18 * min(1.0, max(0.25, dominant_conf)))
        rad = np.deg2rad(dominant_deg)
        ex, ey = int(cx + length * np.cos(rad)), int(cy + length * np.sin(rad))
        cv2.arrowedLine(img, (cx, cy), (ex, ey), col, 3, tipLength=0.3)

    # bottom status bar: dynamic state + reverse-flow / compression / edge readouts
    bar_h = 26
    cv2.rectangle(img, (0, h - bar_h), (w, h), (20, 20, 24), -1)
    parts = [f"DYNAMICS: {dynamic_state.replace('_', ' ')}"]
    if reverse_ratio:
        parts.append(f"reverse-flow {round(reverse_ratio * 100)}%")
    parts.append(f"compression {round(compression_proxy)}")
    if edge_pressure is not None:
        parts.append(f"edge-pressure {round(edge_pressure * 100)}%")
    cv2.putText(img, "  |  ".join(parts), (10, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)

    ok, out = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        return annotated_frame_b64
    return "data:image/jpeg;base64," + base64.b64encode(out.tobytes()).decode("ascii")


def rollup_state(dynamic_state: str, risk_level: str) -> str:
    """Coarser NORMAL -> FLOW -> DISTURBED -> HIGH_RISK narrative, combining
    the dynamics classifier with the existing (unrelated, already-tested)
    risk band — deterministic mapping, documented here rather than hidden in
    the caller."""
    if dynamic_state in ("VOLATILE", "STOP_WAVE") or risk_level in ("RED", "BLACK"):
        return "HIGH_RISK"
    if dynamic_state in ("DISTURBED", "REVERSE_FLOW") or risk_level == "ORANGE":
        return "DISTURBED"
    if dynamic_state == "FLOW":
        return "FLOW"
    return "NORMAL"
