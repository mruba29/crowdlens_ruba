"""Crowd density.

density (people/m^2) = people_count / zone_area_m2

The zone area is a configured estimate for the camera's visible ground area.
Also returns a 0-100 'density risk' used by the risk score, where the configured
critical density maps to 100.
"""
from __future__ import annotations


def density_ppm2(people_count: int, zone_area_m2: float) -> float:
    area = max(1.0, zone_area_m2)
    return round(people_count / area, 3)


def density_risk(density: float, critical_ppm2: float = 5.0) -> float:
    """0-100. `critical_ppm2` people/m^2 -> 100."""
    critical = max(0.5, critical_ppm2)
    return round(max(0.0, min(100.0, (density / critical) * 100.0)), 1)
