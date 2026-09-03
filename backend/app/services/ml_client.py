"""Client for the external CROWDLENS ML service.

If the ML service is unreachable or reports itself unavailable, callers get a
clear signal (`MLUnavailable`) and the UI shows an explicit "ML Service Offline"
state. We never fabricate inference results.
"""
from __future__ import annotations
import json
from typing import Iterator

import httpx

from app.core.config import settings


class MLUnavailable(RuntimeError):
    pass


def health() -> dict:
    try:
        r = httpx.get(f"{settings.ML_SERVICE_URL}/health", timeout=settings.ML_SERVICE_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"service": "crowdlens-ml", "status": "offline", "detector_available": False,
                "reason": str(e)}


def status() -> str:
    """Return 'operational' | 'degraded' | 'offline'."""
    return health().get("status", "offline")


def analyze_path(video_path: str, sample_every_n: int = 3, max_frames: int = 600,
                 zone_area_m2: float = 120.0) -> Iterator[dict]:
    """Stream per-frame analysis dicts from the ML service (SSE -> dicts)."""
    payload = {
        "path": video_path,
        "sample_every_n": sample_every_n,
        "max_frames": max_frames,
        "zone_area_m2": zone_area_m2,
    }
    try:
        with httpx.stream("POST", f"{settings.ML_SERVICE_URL}/analyze/path",
                          json=payload, timeout=None) as r:
            if r.status_code != 200:
                raise MLUnavailable(f"ML service returned {r.status_code}")
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                try:
                    yield json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
    except httpx.HTTPError as e:
        raise MLUnavailable(str(e)) from e
