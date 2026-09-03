import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.sri import RiskComponents, calculate_sri, risk_level, contributing_factors


def test_sri_spec_example():
    c = RiskComponents(density=70, pressure=80, velocity_variance=60, compressibility=70,
                        reverse_flow=50, fallen_person=100, age_vulnerability=40)
    sri = calculate_sri(c)
    assert sri == 68.5
    assert risk_level(sri) == "ORANGE"


def test_risk_bands():
    assert risk_level(0) == "GREEN"
    assert risk_level(30) == "GREEN"
    assert risk_level(31) == "YELLOW"
    assert risk_level(55) == "YELLOW"
    assert risk_level(56) == "ORANGE"
    assert risk_level(75) == "ORANGE"
    assert risk_level(76) == "RED"
    assert risk_level(90) == "RED"
    assert risk_level(91) == "BLACK"
    assert risk_level(100) == "BLACK"


def test_zero_components_is_green():
    c = RiskComponents(0, 0, 0, 0, 0, 0, 0)
    assert calculate_sri(c) == 0.0
    assert risk_level(0.0) == "GREEN"


def test_clamping_out_of_range_inputs():
    c = RiskComponents(density=150, pressure=-20, velocity_variance=50,
                        compressibility=50, reverse_flow=50, fallen_person=50, age_vulnerability=50)
    sri = calculate_sri(c)
    assert 0 <= sri <= 100


def test_contributing_factors_sorted_desc():
    c = RiskComponents(density=90, pressure=10, velocity_variance=10, compressibility=10,
                        reverse_flow=10, fallen_person=10, age_vulnerability=10)
    factors = contributing_factors(c)
    assert factors[0]["factor"] == "density"
    assert factors[0]["band"] == "HIGH"


def test_weights_sum_to_one():
    from app.core.sri import WEIGHTS
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
