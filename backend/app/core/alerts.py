"""Alert decision-support rules. These NEVER trigger automatic physical actions
-- they only generate decision-support alerts for a human operator."""

RECOMMENDED_ACTIONS = {
    "YELLOW": "Increase monitoring frequency and brief ground personnel.",
    "ORANGE": "Restrict incoming flow and pre-position ground personnel near the zone.",
    "RED": "Restrict incoming flow and deploy ground personnel to the zone immediately.",
    "BLACK": "Activate emergency response / evacuation protocol per venue plan.",
}

SIGNAL_THRESHOLDS = {
    "density": 55,
    "pressure": 55,
    "velocity_variance": 55,
    "compressibility": 55,
    "reverse_flow": 40,
}

HUMAN_LABEL = {
    "density": "Density increasing",
    "pressure": "Crowd pressure increasing",
    "velocity_variance": "Velocity variance high",
    "compressibility": "Compression increasing",
    "reverse_flow": "Reverse flow detected",
    "fallen_person": "Possible fallen person detected",
}


def detected_signals(components: dict) -> list[str]:
    signals = []
    for key, threshold in SIGNAL_THRESHOLDS.items():
        if components.get(key, 0) >= threshold:
            signals.append(HUMAN_LABEL[key])
    if components.get("fallen_person", 0) >= 0.5:
        signals.append(HUMAN_LABEL["fallen_person"])
    return signals


def should_alert(level: str) -> bool:
    return level in ("ORANGE", "RED", "BLACK")


def build_alert_payload(zone: str, sri: float, level: str, components: dict, ttc, source: str) -> dict:
    return {
        "zone_name": zone,
        "severity": level,
        "alert_type": "crowd_risk",
        "sri": sri,
        "time_to_critical_sec": ttc,
        "signals": detected_signals(components),
        "recommended_action": RECOMMENDED_ACTIONS.get(level, "Continue monitoring."),
        "status": "OPEN",
        "source": source,
    }
