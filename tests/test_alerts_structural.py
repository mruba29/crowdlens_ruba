import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.alerts import should_alert, detected_signals, build_alert_payload
from app.core.structural import estimate_structural_risk
from app.core.scenario import sample_at, TOTAL_DURATION_SEC, SCENARIO_NAME


def test_should_alert_thresholds():
    assert should_alert("GREEN") is False
    assert should_alert("YELLOW") is False
    assert should_alert("ORANGE") is True
    assert should_alert("RED") is True
    assert should_alert("BLACK") is True


def test_detected_signals_flags_high_components():
    signals = detected_signals({"density": 80, "pressure": 20, "velocity_variance": 10,
                                 "compressibility": 10, "reverse_flow": 10, "fallen_person": 0})
    assert "Density increasing" in signals
    assert "Crowd pressure increasing" not in signals


def test_build_alert_payload_has_recommended_action():
    payload = build_alert_payload("Zone B", 82.0, "RED", {"density": 90}, 120, "controlled_replay")
    assert payload["severity"] == "RED"
    assert "deploy ground personnel" in payload["recommended_action"]
    assert payload["status"] == "OPEN"


def test_structural_overload_warning_rule():
    r = estimate_structural_risk(people_count=600, avg_weight_kg=70, rated_capacity_kg=40000,
                                  dynamic_load_factor=1.6, vibration_freq_hz=2.0)
    # mass = 42000 > 0.8*40000=32000, dynamic_factor>1.5 -> overload warning
    assert r["load_utilization"] > 0.8
    assert r["structural_risk_level"] == "STRUCTURAL_OVERLOAD_WARNING"
    assert "Not structural certification" in r["disclaimer"]


def test_structural_immediate_alert_on_deformation():
    r = estimate_structural_risk(people_count=100, avg_weight_kg=70, rated_capacity_kg=40000,
                                  dynamic_load_factor=1.0, vibration_freq_hz=1.0, visual_deformation=0.2)
    assert r["structural_risk_level"] == "IMMEDIATE_STRUCTURAL_ALERT"


def test_structural_never_claims_safe():
    r = estimate_structural_risk(people_count=10, avg_weight_kg=70, rated_capacity_kg=1000000,
                                  dynamic_load_factor=1.0, vibration_freq_hz=1.0)
    assert "safe" not in r["disclaimer"].lower()


def test_scenario_progression_reaches_critical_and_deescalates():
    start = sample_at(0)
    peak = sample_at(140)  # PREDICTED_CRITICAL keyframe
    end = sample_at(TOTAL_DURATION_SEC)
    assert start["level"] in ("GREEN", "YELLOW")
    assert peak["sri"] > start["sri"]
    assert peak["level"] in ("RED", "BLACK")
    assert end["sri"] < peak["sri"]
    assert start["source"] == "controlled_replay"


def test_scenario_labeled_as_controlled_replay():
    state = sample_at(50)
    assert state["scenario"] == SCENARIO_NAME
    assert state["source"] == "controlled_replay"
