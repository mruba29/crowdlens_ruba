"""Crowd movement via dense optical flow (Farneback).

Returns:
  mean_motion       average flow magnitude (px/frame) - overall movement
  turbulence        variance of flow magnitude - chaotic / conflicting movement
  motion_risk       0-100 combining the two
"""
from __future__ import annotations
import numpy as np
import cv2


class MovementEstimator:
    def __init__(self) -> None:
        self._prev_gray: np.ndarray | None = None

    def update(self, frame: np.ndarray) -> dict:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is None or self._prev_gray.shape != gray.shape:
            self._prev_gray = gray
            return {"mean_motion": 0.0, "turbulence": 0.0, "motion_risk": 0.0}

        flow = cv2.calcOpticalFlowFarneback(self._prev_gray, gray, None,
                                            0.5, 2, 15, 3, 5, 1.2, 0)
        self._prev_gray = gray
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mean_motion = float(mag.mean())
        turbulence = float(mag.var())

        motion_component = min(100.0, (mean_motion / 3.0) * 100.0)
        turb_component = min(100.0, (turbulence / 15.0) * 100.0)
        motion_risk = round(0.5 * motion_component + 0.5 * turb_component, 1)

        return {
            "mean_motion": round(mean_motion, 3),
            "turbulence": round(turbulence, 3),
            "motion_risk": motion_risk,
        }
