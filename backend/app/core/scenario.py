"""
Controlled Evaluation Replay: "Stadium Exit Surge".

This is a DETERMINISTIC, pre-authored scenario, not live model inference.
It exists so a hackathon demo has a reliable, repeatable risk progression to
show the full CROWDLENS pipeline (detection -> tracking -> features -> SRI ->
prediction -> alert -> operator response) end to end, even without a live
camera feed producing a genuine surge on demand.

Every value emitted by this module is labeled "source": "controlled_replay"
so the frontend can render the CONTROLLED EVALUATION REPLAY badge and never
confuse it with real_cv output.
"""
from app.core.sri import RiskComponents, calculate_sri, risk_level, contributing_factors

# Keyframes: (t_offset_sec, stage_label, people_count, components dict, avg_velocity,
#             direction_entropy, interpersonal_distance_m, dynamics_state, dynamics_conf)
KEYFRAMES = [
    (0,   "NORMAL",              120, dict(density=12, pressure=10, velocity_variance=15, compressibility=10, reverse_flow=5,  fallen_person=0, age_vulnerability=20), 1.2, 0.85, 1.4, "PASSIVE", 0.92),
    (20,  "DENSITY_RISING",      210, dict(density=38, pressure=25, velocity_variance=22, compressibility=20, reverse_flow=8,  fallen_person=0, age_vulnerability=25), 1.0, 0.78, 1.0, "ACTIVE",  0.88),
    (40,  "COMPRESSION",         320, dict(density=58, pressure=48, velocity_variance=35, compressibility=55, reverse_flow=15, fallen_person=0, age_vulnerability=28), 0.7, 0.66, 0.7, "ACTIVE",  0.83),
    (60,  "TURBULENCE",          410, dict(density=70, pressure=62, velocity_variance=64, compressibility=68, reverse_flow=30, fallen_person=0, age_vulnerability=30), 0.5, 0.48, 0.5, "VOLATILE",0.81),
    (80,  "REVERSE_FLOW",        460, dict(density=78, pressure=74, velocity_variance=71, compressibility=76, reverse_flow=62, fallen_person=0, age_vulnerability=32), 0.4, 0.35, 0.4, "VOLATILE",0.85),
    (100, "SRI_ORANGE",          510, dict(density=82, pressure=80, velocity_variance=75, compressibility=80, reverse_flow=68, fallen_person=0, age_vulnerability=34), 0.35,0.30, 0.35,"VOLATILE",0.87),
    (120, "SRI_RED",             560, dict(density=90, pressure=88, velocity_variance=82, compressibility=88, reverse_flow=78, fallen_person=1, age_vulnerability=36), 0.25,0.22, 0.28,"PANIC",   0.90),
    (140, "PREDICTED_CRITICAL",  590, dict(density=95, pressure=93, velocity_variance=87, compressibility=92, reverse_flow=85, fallen_person=1, age_vulnerability=38), 0.20,0.18, 0.24,"PANIC",   0.93),
    (160, "OPERATOR_RESPONSE",   540, dict(density=80, pressure=70, velocity_variance=60, compressibility=70, reverse_flow=55, fallen_person=0, age_vulnerability=34), 0.4, 0.40, 0.45,"ACTIVE",  0.80),
    (180, "RISK_DECREASE",       380, dict(density=45, pressure=35, velocity_variance=30, compressibility=32, reverse_flow=18, fallen_person=0, age_vulnerability=28), 0.9, 0.70, 0.9, "ACTIVE",  0.78),
    (200, "STABILIZED",          230, dict(density=20, pressure=15, velocity_variance=18, compressibility=15, reverse_flow=8,  fallen_person=0, age_vulnerability=22), 1.1, 0.82, 1.3, "PASSIVE", 0.90),
]

SCENARIO_NAME = "Stadium Exit Surge"
SCENARIO_ZONE = "Zone B - South Exit"
TOTAL_DURATION_SEC = KEYFRAMES[-1][0]


def _lerp(a, b, f):
    return a + (b - a) * f


def _interp_components(c1: dict, c2: dict, f: float) -> dict:
    return {k: _lerp(c1[k], c2[k], f) for k in c1}


def sample_at(t: float) -> dict:
    """Return interpolated scenario state at time t (seconds), deterministic."""
    t = max(0, min(TOTAL_DURATION_SEC, t))
    for i in range(len(KEYFRAMES) - 1):
        t0, stage0, pc0, comp0, v0, e0, d0, dyn0, conf0 = KEYFRAMES[i]
        t1, stage1, pc1, comp1, v1, e1, d1, dyn1, conf1 = KEYFRAMES[i + 1]
        if t0 <= t <= t1:
            f = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            people_count = round(_lerp(pc0, pc1, f))
            comps = _interp_components(comp0, comp1, f)
            velocity = round(_lerp(v0, v1, f), 2)
            entropy = round(_lerp(e0, e1, f), 2)
            distance = round(_lerp(d0, d1, f), 2)
            stage = stage0 if f < 0.5 else stage1
            dynamics_state = dyn0 if f < 0.5 else dyn1
            dynamics_conf = round(_lerp(conf0, conf1, f), 2)
            break
    else:
        t1, stage1, pc1, comp1, v1, e1, d1, dyn1, conf1 = KEYFRAMES[-1]
        people_count, comps, velocity, entropy, distance = pc1, comp1, v1, e1, d1
        stage, dynamics_state, dynamics_conf = stage1, dyn1, conf1

    rc = RiskComponents(**comps)
    sri = calculate_sri(rc)
    level = risk_level(sri)
    factors = contributing_factors(rc)

    # forecast: look 20s ahead along the deterministic timeline
    future_t = min(TOTAL_DURATION_SEC, t + 20)
    forecast_sri = sri
    if future_t != t:
        for i in range(len(KEYFRAMES) - 1):
            ft0, _, _, fc0, *_ = KEYFRAMES[i]
            ft1, _, _, fc1, *_ = KEYFRAMES[i + 1]
            if ft0 <= future_t <= ft1:
                ff = 0 if ft1 == ft0 else (future_t - ft0) / (ft1 - ft0)
                fcomps = _interp_components(fc0, fc1, ff)
                forecast_sri = calculate_sri(RiskComponents(**fcomps))
                break

    trend = "INCREASING" if forecast_sri > sri + 1 else ("DECREASING" if forecast_sri < sri - 1 else "STABLE")

    # time-to-critical: seconds until scenario timeline crosses SRI 91 (BLACK) from current t
    ttc = None
    for probe in range(int(t), TOTAL_DURATION_SEC + 1, 2):
        probe_state = None
        for i in range(len(KEYFRAMES) - 1):
            pt0, _, _, pc0, *_ = KEYFRAMES[i]
            pt1, _, _, pc1, *_ = KEYFRAMES[i + 1]
            if pt0 <= probe <= pt1:
                pf = 0 if pt1 == pt0 else (probe - pt0) / (pt1 - pt0)
                pcomps = _interp_components(pc0, pc1, pf)
                probe_state = calculate_sri(RiskComponents(**pcomps))
                break
        if probe_state is not None and probe_state >= 76:  # RED/BLACK boundary treated as critical
            ttc = probe - int(t)
            break

    return {
        "source": "controlled_replay",
        "scenario": SCENARIO_NAME,
        "zone": SCENARIO_ZONE,
        "t_offset_sec": round(t, 1),
        "stage": stage,
        "people_count": people_count,
        "components": {k: round(v, 1) for k, v in comps.items()},
        "avg_velocity": velocity,
        "direction_entropy": entropy,
        "interpersonal_distance_m": distance,
        "dynamics_state": dynamics_state,
        "dynamics_confidence": dynamics_conf,
        "sri": sri,
        "level": level,
        "contributing_factors": factors,
        "forecast_sri": forecast_sri,
        "trend": trend,
        "time_to_critical_sec": ttc,
        "prediction_confidence": round(min(0.95, 0.6 + (sri / 300)), 2),
    }


def timeline_markers():
    return [
        {"t": t, "stage": stage, "people_count": pc}
        for (t, stage, pc, *_rest) in KEYFRAMES
    ]
