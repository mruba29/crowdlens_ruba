"""Crowd Risk Score (SRI) — simple, explainable, 0-100.

factors (each normalized 0-100):
  density            how crowded the zone is vs its critical density
  movement           overall + turbulent motion (optical flow)
  density_increase   how fast the crowd is growing (rate of change)
  compression        people packed tighter than comfortable spacing

score = 0.40*density + 0.25*movement + 0.20*density_increase + 0.15*compression

Bands:  0-30 GREEN | 31-55 YELLOW | 56-75 ORANGE | 76-90 RED | 91-100 BLACK
"""
from __future__ import annotations
from dataclasses import dataclass

WEIGHTS = {
    "density": 0.40,
    "movement": 0.25,
    "density_increase": 0.20,
    "compression": 0.15,
}


@dataclass
class RiskFactors:
    density: float = 0.0
    movement: float = 0.0
    density_increase: float = 0.0
    compression: float = 0.0

    def clamped(self) -> "RiskFactors":
        return RiskFactors(**{k: max(0.0, min(100.0, float(v))) for k, v in self.__dict__.items()})


def risk_level(score: float) -> tuple[str, str]:
    if score <= 30:
        return "GREEN", "Normal"
    if score <= 55:
        return "YELLOW", "Warning"
    if score <= 75:
        return "ORANGE", "High Risk"
    if score <= 90:
        return "RED", "Critical"
    return "BLACK", "Emergency"


def compute(factors: RiskFactors) -> dict:
    f = factors.clamped()
    score = round(sum(WEIGHTS[k] * getattr(f, k) for k in WEIGHTS), 1)
    level, label = risk_level(score)
    contributions = sorted(
        ({"factor": k, "value": round(getattr(f, k), 1), "weight": WEIGHTS[k],
          "contribution": round(WEIGHTS[k] * getattr(f, k), 1)} for k in WEIGHTS),
        key=lambda r: r["contribution"], reverse=True,
    )
    return {"score": score, "level": level, "label": label, "factors": f.__dict__,
            "contributions": contributions}


class RiskTracker:
    """Keeps a short density history so density_increase can be measured."""

    def __init__(self, window: int = 10):
        self.window = window
        self._density_hist: list[tuple[float, float]] = []  # (t, density_ppm2)

    def density_increase_risk(self, t: float, density: float) -> float:
        self._density_hist.append((t, density))
        if len(self._density_hist) > self.window:
            self._density_hist.pop(0)
        if len(self._density_hist) < 3:
            return 0.0
        (t0, d0), (t1, d1) = self._density_hist[0], self._density_hist[-1]
        dt = max(1e-3, t1 - t0)
        rate = (d1 - d0) / dt  # people/m^2 per second
        # 0.3 ppl/m^2/s sustained growth -> 100
        return round(max(0.0, min(100.0, (rate / 0.3) * 100.0)), 1)

    @staticmethod
    def compression_risk(interpersonal_distance_m: float, people_count: int) -> float:
        if people_count < 2:
            return 0.0
        if interpersonal_distance_m <= 0:
            return 100.0
        # comfortable spacing ~1.2 m; 0.4 m or less -> 100
        return round(max(0.0, min(100.0, (1.2 - interpersonal_distance_m) / 0.8 * 100.0)), 1)
