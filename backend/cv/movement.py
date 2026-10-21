"""Crowd movement via dense optical flow (Farneback).

Returns:
  mean_motion              average flow magnitude (px/frame) - overall movement
  turbulence                variance of flow magnitude - chaotic / conflicting movement
  motion_risk                0-100 combining the two
  flow_direction_deg          dominant movement direction (0=right, 90=down, image
                              coords), or None when there isn't enough motion to
                              call a direction — never a guessed angle.
  flow_direction_confidence   0-1, how concentrated that direction is (circular
                              mean resultant length) - low means the crowd is
                              moving in many directions at once, not one dominant way.
"""
from __future__ import annotations
import numpy as np
import cv2

# below this per-pixel flow magnitude, motion is treated as noise, not movement
_NOISE_FLOOR = 0.3


class MovementEstimator:
    def __init__(self) -> None:
        self._prev_gray: np.ndarray | None = None

    def update(self, frame: np.ndarray) -> dict:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is None or self._prev_gray.shape != gray.shape:
            self._prev_gray = gray
            return {"mean_motion": 0.0, "turbulence": 0.0, "motion_risk": 0.0,
                    "flow_direction_deg": None, "flow_direction_confidence": 0.0}

        flow = cv2.calcOpticalFlowFarneback(self._prev_gray, gray, None,
                                            0.5, 2, 15, 3, 5, 1.2, 0)
        self._prev_gray = gray
        fx, fy = flow[..., 0], flow[..., 1]
        mag, ang = cv2.cartToPolar(fx, fy)
        mean_motion = float(mag.mean())
        turbulence = float(mag.var())

        motion_component = min(100.0, (mean_motion / 3.0) * 100.0)
        turb_component = min(100.0, (turbulence / 15.0) * 100.0)
        motion_risk = round(0.5 * motion_component + 0.5 * turb_component, 1)

        # dominant direction: circular mean of the angle at pixels that are
        # actually moving, weighted by their magnitude. The resultant vector
        # length (0-1) tells us how concentrated that direction really is —
        # a low value means "no dominant direction", reported honestly as
        # such rather than an over-precise angle from near-random motion.
        moving = mag > _NOISE_FLOOR
        direction_deg = None
        direction_conf = 0.0
        if np.count_nonzero(moving) > 25:  # need a meaningful sample of moving pixels
            wsum_x = float(np.sum(np.cos(ang[moving]) * mag[moving]))
            wsum_y = float(np.sum(np.sin(ang[moving]) * mag[moving]))
            wsum = float(np.sum(mag[moving]))
            resultant = (wsum_x ** 2 + wsum_y ** 2) ** 0.5
            direction_conf = round(min(1.0, resultant / wsum), 3) if wsum > 0 else 0.0
            if direction_conf >= 0.15:  # too dispersed below this -> no call
                direction_deg = round(np.degrees(np.arctan2(wsum_y, wsum_x)) % 360, 1)

        return {
            "mean_motion": round(mean_motion, 3),
            "turbulence": round(turbulence, 3),
            "motion_risk": motion_risk,
            "flow_direction_deg": direction_deg,
            "flow_direction_confidence": direction_conf,
        }
