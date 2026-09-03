"""Map raw crowd features onto normalized 0-100 risk components.

These are the seven inputs the backend SRI engine expects. Keeping this mapping
in the ML service means the CV pipeline owns 'how crowded / turbulent is this,
physically' while the backend owns 'how is that combined into a single score'.
"""
from __future__ import annotations


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def to_components(f: dict) -> dict:
    """f = FeatureExtractor.extract(...) output."""
    density = _clamp((f["density_ppm2"] / 6.0) * 100.0)          # 6 ppl/m^2 ~ critical
    pressure = _clamp((f["pressure_proxy"] / 8.0) * 100.0)
    velocity_variance = _clamp((f["velocity_variance"] / 40.0) * 100.0)
    compressibility = _clamp(f["compression_index"] * 100.0)
    reverse_flow = _clamp(f["reverse_flow_ratio"] * 100.0)
    fallen_person = 100.0 if f["fallen_person_flag"] else 0.0
    age_vulnerability = _clamp(f["vulnerability_index"] * 100.0)

    return {
        "density": round(density, 1),
        "pressure": round(pressure, 1),
        "velocity_variance": round(velocity_variance, 1),
        "compressibility": round(compressibility, 1),
        "reverse_flow": round(reverse_flow, 1),
        "fallen_person": round(fallen_person, 1),
        "age_vulnerability": round(age_vulnerability, 1),
    }
