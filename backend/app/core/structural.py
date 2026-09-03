"""
AI-based structural-risk INDICATOR. Not structural certification.
Never claim a structure is "safe" -- only report load/vibration indicators
that require human/engineering validation.
"""


def estimate_structural_risk(
    people_count: int,
    avg_weight_kg: float,
    rated_capacity_kg: float,
    dynamic_load_factor: float,
    vibration_freq_hz: float,
    visual_deformation: float = 0.0,
    resonance_detected: bool = False,
) -> dict:
    estimated_mass_kg = people_count * avg_weight_kg
    rated_capacity_kg = max(1.0, rated_capacity_kg)
    load_utilization = round(estimated_mass_kg / rated_capacity_kg, 3)

    overload_warning = load_utilization > 0.80 and dynamic_load_factor > 1.5
    immediate_alert = visual_deformation > 0.15 or resonance_detected or (
        load_utilization > 0.95 and dynamic_load_factor > 1.8
    )

    if immediate_alert:
        level = "IMMEDIATE_STRUCTURAL_ALERT"
    elif overload_warning:
        level = "STRUCTURAL_OVERLOAD_WARNING"
    elif load_utilization > 0.6:
        level = "ELEVATED"
    else:
        level = "NORMAL"

    return {
        "people_count": people_count,
        "estimated_mass_kg": round(estimated_mass_kg, 1),
        "rated_capacity_kg": rated_capacity_kg,
        "load_utilization": load_utilization,
        "dynamic_load_factor": dynamic_load_factor,
        "vibration_freq_hz": vibration_freq_hz,
        "resonance_detected": resonance_detected,
        "visual_deformation": visual_deformation,
        "structural_risk_level": level,
        "disclaimer": "AI-based structural-risk indicator. Not structural certification.",
    }
