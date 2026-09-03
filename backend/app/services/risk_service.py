"""Risk scoring + prediction + structural indicator, on top of the pure engines.

Keeps a small in-memory SRI history per session so predictions have context
even before rows are flushed to the database.
"""
from __future__ import annotations
from collections import defaultdict, deque

from app.core.sri import RiskComponents, calculate_sri, risk_level, contributing_factors
from app.core import prediction as pred_engine
from app.core.structural import estimate_structural_risk

_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=240))


def reset_session(session_id: str) -> None:
    _history.pop(session_id, None)


def score(components: dict) -> dict:
    rc = RiskComponents(
        density=components.get("density", 0.0),
        pressure=components.get("pressure", 0.0),
        velocity_variance=components.get("velocity_variance", 0.0),
        compressibility=components.get("compressibility", 0.0),
        reverse_flow=components.get("reverse_flow", 0.0),
        fallen_person=components.get("fallen_person", 0.0),
        age_vulnerability=components.get("age_vulnerability", 0.0),
    )
    sri = calculate_sri(rc)
    return {
        "sri": sri,
        "level": risk_level(sri),
        "components": rc.clamp().__dict__,
        "contributing_factors": contributing_factors(rc),
    }


def predict(session_id: str, t_offset_sec: float, sri: float, horizon_sec: int = 20) -> dict:
    hist = _history[session_id]
    hist.append((t_offset_sec, sri))
    fc = pred_engine.forecast(list(hist), horizon_sec=horizon_sec)
    return fc.as_dict()


def structural(people_count: int, avg_weight_kg: float, rated_capacity_kg: float,
               dynamic_load_factor: float = 1.2, vibration_freq_hz: float = 2.0,
               visual_deformation: float = 0.0, resonance_detected: bool = False) -> dict:
    return estimate_structural_risk(
        people_count, avg_weight_kg, rated_capacity_kg, dynamic_load_factor,
        vibration_freq_hz, visual_deformation, resonance_detected,
    )
