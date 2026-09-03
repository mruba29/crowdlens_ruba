"""
CROWDLENS Safety Risk Index (SRI) engine.

SRI is a 0-100 composite risk score built from normalized (0-100) component
risks. This module is pure, deterministic math -- it is used identically by
both the real CV pipeline and the controlled evaluation replay, so the same
formula backs every SRI value shown in the UI.

Formula (weights sum to 1.0):
    SRI = 0.30*D + 0.20*P + 0.15*V + 0.15*C + 0.10*R + 0.05*F + 0.05*A
"""
from dataclasses import dataclass, asdict

WEIGHTS = {
    "density": 0.30,
    "pressure": 0.20,
    "velocity_variance": 0.15,
    "compressibility": 0.15,
    "reverse_flow": 0.10,
    "fallen_person": 0.05,
    "age_vulnerability": 0.05,
}


@dataclass
class RiskComponents:
    density: float
    pressure: float
    velocity_variance: float
    compressibility: float
    reverse_flow: float
    fallen_person: float
    age_vulnerability: float

    def clamp(self) -> "RiskComponents":
        d = asdict(self)
        for k, v in d.items():
            d[k] = max(0.0, min(100.0, float(v)))
        return RiskComponents(**d)


def calculate_sri(components: RiskComponents) -> float:
    c = components.clamp()
    total = (
        WEIGHTS["density"] * c.density
        + WEIGHTS["pressure"] * c.pressure
        + WEIGHTS["velocity_variance"] * c.velocity_variance
        + WEIGHTS["compressibility"] * c.compressibility
        + WEIGHTS["reverse_flow"] * c.reverse_flow
        + WEIGHTS["fallen_person"] * c.fallen_person
        + WEIGHTS["age_vulnerability"] * c.age_vulnerability
    )
    return round(total, 2)


def risk_level(sri: float) -> str:
    if sri <= 30:
        return "GREEN"
    if sri <= 55:
        return "YELLOW"
    if sri <= 75:
        return "ORANGE"
    if sri <= 90:
        return "RED"
    return "BLACK"


def contributing_factors(components: RiskComponents) -> list[dict]:
    """Rank each component's weighted contribution for the UI explainer panel."""
    c = components.clamp()
    rows = []
    for key, weight in WEIGHTS.items():
        raw = getattr(c, key)
        contribution = round(raw * weight, 2)
        if raw >= 70:
            band = "HIGH"
        elif raw >= 40:
            band = "MEDIUM"
        else:
            band = "LOW"
        rows.append(
            {
                "factor": key,
                "value": raw,
                "weight": weight,
                "contribution": contribution,
                "band": band,
            }
        )
    rows.sort(key=lambda r: r["contribution"], reverse=True)
    return rows
