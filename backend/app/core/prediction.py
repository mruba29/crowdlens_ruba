"""Temporal risk prediction — probabilistic decision-support, not a guarantee.

Given a short history of (t, SRI) samples, fit a local linear trend, project it
`horizon` seconds ahead, and estimate seconds-to-critical (SRI >= 76). Confidence
falls with trend volatility and rises with history length.

This is intentionally a simple, explainable model. The frontend must present the
output as probabilistic ("estimated", "forecast"), never as certainty.
"""
from __future__ import annotations
from dataclasses import dataclass

CRITICAL_SRI = 76.0


@dataclass
class Forecast:
    current_sri: float
    forecast_sri: float
    horizon_sec: int
    trend: str                 # INCREASING / DECREASING / STABLE
    time_to_critical_sec: int | None
    confidence: float          # 0..1

    def as_dict(self) -> dict:
        return {
            "current_sri": round(self.current_sri, 1),
            "forecast_sri": round(self.forecast_sri, 1),
            "horizon_sec": self.horizon_sec,
            "trend": self.trend,
            "time_to_critical_sec": self.time_to_critical_sec,
            "confidence": round(self.confidence, 2),
        }


def _linfit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        return 0.0, (ys[-1] if ys else 0.0)
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    return slope, intercept


def forecast(history: list[tuple[float, float]], horizon_sec: int = 20,
             window: int = 12) -> Forecast:
    """history: list of (t_offset_sec, sri), oldest first."""
    if not history:
        return Forecast(0.0, 0.0, horizon_sec, "STABLE", None, 0.3)

    recent = history[-window:]
    xs = [t for t, _ in recent]
    ys = [s for _, s in recent]
    cur_t, cur_sri = recent[-1]

    slope, intercept = _linfit(xs, ys)
    projected = intercept + slope * (cur_t + horizon_sec)
    projected = max(0.0, min(100.0, projected))

    if slope > 0.15:
        trend = "INCREASING"
    elif slope < -0.15:
        trend = "DECREASING"
    else:
        trend = "STABLE"

    ttc: int | None = None
    if slope > 0.05 and cur_sri < CRITICAL_SRI:
        secs = (CRITICAL_SRI - cur_sri) / slope
        if 0 < secs <= 3600:
            ttc = int(round(secs))
    elif cur_sri >= CRITICAL_SRI:
        ttc = 0

    # confidence: more history + lower residual variance => higher
    if len(recent) >= 3:
        preds = [intercept + slope * x for x in xs]
        resid = sum((y - p) ** 2 for y, p in zip(ys, preds)) / len(ys)
        fit_conf = max(0.0, 1.0 - resid / 400.0)
    else:
        fit_conf = 0.4
    length_conf = min(1.0, len(recent) / window)
    confidence = max(0.3, min(0.95, 0.35 + 0.4 * fit_conf + 0.25 * length_conf))

    return Forecast(cur_sri, projected, horizon_sec, trend, ttc, confidence)
