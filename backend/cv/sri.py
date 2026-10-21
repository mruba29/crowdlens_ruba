"""Phase 4 — Demographic Vulnerability + the Crowd Risk Engine (SRI).

Three real, honestly-scoped pieces:

1. Demographic estimate: CROWDLENS has no age/gender classifier anywhere in
   its CV pipeline (confirmed absent — see the project's own Phase 1 audit).
   So "children / adults / elderly" is never AI-detected per person. Instead
   it is the real, live headcount apportioned by an OPERATOR-CONFIGURED event
   composition (e.g. "this is a family festival, ~20% children") — real
   arithmetic on a real number, labeled as an estimate, never a per-person
   classification, never identity.

2. Vulnerability proxy: a documented heuristic blending that configured
   composition with real crowd conditions (density risk, compression). Zero
   contribution — reported as "not configured" — until the operator sets a
   composition, rather than silently assuming a neutral crowd.

3. SRI (Safety Risk Index): a transparent, ten-input weighted score, same
   0-100 / GREEN-BLACK banding CROWDLENS already uses elsewhere
   (cv/risk.py::risk_level). No single input can push the band on its own —
   see WEIGHTS below, all capped well under 0.5 and summing to 1.0. Ten
   real-time early-warning alert types are evaluated from the same inputs.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from cv.risk import risk_level  # reuse the exact same 5-band thresholds everywhere

# --------------------------------------------------------------------------
# demographic estimate + vulnerability proxy
# --------------------------------------------------------------------------
def demographic_estimate(people_count: int, children_pct: float | None,
                          adults_pct: float | None, elderly_pct: float | None) -> dict:
    """Apportions the REAL headcount by the operator's configured composition.
    Never AI-detected per person. Returns not_configured when the operator
    hasn't set a composition — never assumes one."""
    if children_pct is None or adults_pct is None or elderly_pct is None:
        return {"available": False, "reason": "not_configured"}
    total_pct = children_pct + adults_pct + elderly_pct
    if total_pct <= 0:
        return {"available": False, "reason": "not_configured"}
    # normalize in case the three don't sum to exactly 100
    c, a, e = (children_pct / total_pct, adults_pct / total_pct, elderly_pct / total_pct)
    return {
        "available": True,
        "estimated_children": round(people_count * c),
        "estimated_adults": round(people_count * a),
        "estimated_elderly": round(people_count * e),
        "basis": "Apportioned from the real live headcount using your configured event "
                 "composition — not detected per person by computer vision.",
    }


def vulnerability_proxy(children_pct: float | None, elderly_pct: float | None,
                         density_risk_0_100: float, compression_proxy_0_100: float,
                         child_weight: float = 0.6, elderly_weight: float = 0.8) -> dict:
    """0-100 heuristic estimate, documented and reweightable here. Requires a
    configured composition — reports not_configured rather than assuming a
    default (silently assuming "no vulnerable people" would understate risk)."""
    if children_pct is None or elderly_pct is None:
        return {"available": False, "reason": "not_configured", "score": None}
    composition_component = min(100.0, children_pct * child_weight + elderly_pct * elderly_weight)
    crowd_component = 0.5 * density_risk_0_100 + 0.5 * compression_proxy_0_100
    score = round(0.4 * composition_component + 0.6 * crowd_component, 1)
    return {
        "available": True, "score": min(100.0, max(0.0, score)),
        "composition_component": round(composition_component, 1),
        "crowd_condition_component": round(crowd_component, 1),
        "disclaimer": "Heuristic estimate — configured demographic composition weighted "
                       "against real crowd conditions. Not a clinical or physiological measurement.",
    }


# --------------------------------------------------------------------------
# fallen-person heuristic (ported, tested logic from ml_service/app/features.py)
# --------------------------------------------------------------------------
def fallen_person_flag(boxes: list) -> bool:
    """A standing person's box is taller than wide; a fallen/prone person's
    tends to be wider than tall. Same threshold as the project's existing
    verified prototype (ml_service) — a real, if approximate, geometric cue,
    not a pose/action classifier."""
    for (x1, y1, x2, y2, c) in boxes:
        bw, bh = (x2 - x1), (y2 - y1)
        if bh > 0 and (bw / bh) > 1.6 and c > 0.4:
            return True
    return False


# --------------------------------------------------------------------------
# SRI — transparent, multi-signal risk engine
# --------------------------------------------------------------------------
WEIGHTS = {
    "density": 0.18,
    "flow_imbalance": 0.10,
    "accumulation": 0.10,
    "velocity_variance": 0.10,
    "direction_conflict": 0.08,
    "reverse_flow": 0.12,
    "compression": 0.12,
    "edge_pressure": 0.08,
    "fallen_person": 0.07,
    "vulnerability": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

LABELS = {
    "density": "Density", "flow_imbalance": "Flow imbalance", "accumulation": "Accumulation",
    "velocity_variance": "Velocity variance", "direction_conflict": "Direction conflict",
    "reverse_flow": "Reverse flow", "compression": "Compression", "edge_pressure": "Edge pressure",
    "fallen_person": "Fallen person signal", "vulnerability": "Vulnerability",
}


@dataclass
class SRIComponents:
    density: float = 0.0
    flow_imbalance: float = 0.0
    accumulation: float = 0.0
    velocity_variance: float = 0.0
    direction_conflict: float = 0.0
    reverse_flow: float = 0.0
    compression: float = 0.0
    edge_pressure: float = 0.0
    fallen_person: float = 0.0
    vulnerability: float = 0.0
    # which components actually had real data this frame vs excluded (and
    # reweighted away) for lack of it — never silently treated as 0-risk data
    available: dict = field(default_factory=dict)

    def clamped(self) -> "SRIComponents":
        d = self.__dict__.copy()
        avail = d.pop("available")
        return SRIComponents(**{k: max(0.0, min(100.0, float(v))) for k, v in d.items()}, available=avail)


def compute_sri(c: SRIComponents) -> dict:
    """Weighted sum over only the components with real data this frame —
    missing inputs are excluded and the remaining weights renormalized, never
    treated as zero (which would understate risk) and never treated as 100
    (which would fabricate it)."""
    cc = c.clamped()
    active_weight = sum(WEIGHTS[k] for k, ok in cc.available.items() if ok) or 1e-9
    score = 0.0
    contributions = []
    for k, w in WEIGHTS.items():
        if not cc.available.get(k, True):
            continue
        norm_w = w / active_weight
        val = getattr(cc, k)
        contrib = norm_w * val
        score += contrib
        contributions.append({"factor": k, "label": LABELS[k], "value": round(val, 1),
                               "weight": round(norm_w, 3), "contribution": round(contrib, 1)})
    score = round(min(100.0, max(0.0, score)), 1)
    level, label = risk_level(score)
    contributions.sort(key=lambda r: r["contribution"], reverse=True)
    # explainability: only the notably-elevated components, arrow-style
    notable = [f"{r['label']} ↑" for r in contributions if r["value"] >= 40]
    return {"sri": score, "level": level, "label": label, "contributions": contributions,
            "notable_signals": notable}


# --------------------------------------------------------------------------
# ten early-warning alert types
# --------------------------------------------------------------------------
ALERT_ACTIONS = {
    "HIGH_INFLOW_LOW_OUTFLOW": "Restrict entry or open additional exits to rebalance flow.",
    "RAPID_ACCUMULATION": "Increase monitoring; prepare to pause inflow into this zone.",
    "CRITICAL_DENSITY": "Halt entry into this zone immediately.",
    "BOTTLENECK_CONGESTION": "Deploy staff to the bottleneck; consider alternate routing.",
    "FLOW_IMBALANCE": "Monitor closely — sustained imbalance may lead to accumulation.",
    "REVERSE_FLOW": "Investigate the cause of reverse movement — possible obstruction.",
    "COMPRESSION_INCREASE": "Reduce inflow; create space in the zone.",
    "EDGE_PRESSURE": "Check for crowd pressing against a barrier; reinforce if needed.",
    "SUDDEN_FLOW_DISTURBANCE": "Investigate the sudden change in crowd movement.",
    "FALLEN_PERSON_OBSTRUCTION": "Dispatch medical/rescue personnel to the zone immediately.",
}


def detect_early_warnings(*, density_ppm2: float | None, critical_ppm2: float,
                           flow_supported: bool, inflow_rate: float | None, outflow_rate: float | None,
                           flow_imbalance: float | None, accumulation_trend: str | None,
                           accumulation_rate: float | None, turbulence: float, prev_turbulence: float | None,
                           reverse_ratio: float | None, compression_proxy: float, prev_compression: float | None,
                           edge_pressure: float | None, is_bottleneck_zone: bool, bottleneck_flagged: bool,
                           fallen: bool, zone_name: str, sri_level: str) -> list[dict]:
    """Evaluates all 10 types against this frame's real signals. Returns the
    ones currently firing — analysis.py edge-triggers so only a *new* firing
    creates a stored alert, not one row per frame."""
    fired = []

    def add(alert_type: str, severity: str, trigger_signals: list[str]):
        fired.append({"alert_type": alert_type, "severity": severity, "zone": zone_name,
                      "trigger_signals": trigger_signals, "recommended_action": ALERT_ACTIONS[alert_type]})

    if flow_supported and inflow_rate is not None and outflow_rate is not None:
        if inflow_rate >= 5 and outflow_rate < inflow_rate * 0.4:
            add("HIGH_INFLOW_LOW_OUTFLOW", "ORANGE",
                [f"Inflow {inflow_rate}/min vs outflow {outflow_rate}/min"])
        elif flow_imbalance is not None and flow_imbalance > 2:
            add("FLOW_IMBALANCE", "YELLOW", [f"Flow imbalance +{flow_imbalance}/min"])

    if accumulation_trend == "increasing" and accumulation_rate is not None and accumulation_rate > 0.3:
        add("RAPID_ACCUMULATION", "ORANGE", [f"Density rising at {accumulation_rate}/m²/min"])

    if density_ppm2 is not None and critical_ppm2 > 0 and density_ppm2 >= critical_ppm2:
        add("CRITICAL_DENSITY", "RED", [f"Density {density_ppm2}/m² at or above critical {critical_ppm2}/m²"])

    if is_bottleneck_zone and bottleneck_flagged:
        add("BOTTLENECK_CONGESTION", "ORANGE", ["Bottleneck zone showing accumulation or positive flow imbalance"])

    if reverse_ratio is not None and reverse_ratio >= 0.30:
        add("REVERSE_FLOW", "ORANGE", [f"{round(reverse_ratio * 100)}% of tracked movement opposing dominant direction"])

    if compression_proxy >= 60 and (prev_compression is None or compression_proxy > prev_compression + 5):
        add("COMPRESSION_INCREASE", "ORANGE", [f"Compression proxy {compression_proxy} and rising"])

    if edge_pressure is not None and edge_pressure >= 0.35:
        add("EDGE_PRESSURE", "YELLOW", [f"{round(edge_pressure * 100)}% of detections near the frame boundary"])

    if turbulence >= 9.0 and (prev_turbulence is None or turbulence > prev_turbulence * 1.8):
        add("SUDDEN_FLOW_DISTURBANCE", "ORANGE", [f"Turbulence jumped to {round(turbulence, 1)}"])

    if fallen:
        add("FALLEN_PERSON_OBSTRUCTION", "RED", ["Detection with a fallen-person aspect ratio"])

    return fired
