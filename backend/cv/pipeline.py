"""In-process video analysis pipeline.

decode (OpenCV) -> detect (YOLO/HOG) -> count -> density -> movement (optical flow)
-> risk score -> annotated frame (boxes drawn)

Yields one dict per sampled frame. The backend's analysis service consumes this
directly (no separate ML service process required).
"""
from __future__ import annotations
import base64
import math
from typing import Iterator

import numpy as np
import cv2

from cv.detector import get_detector
from cv.density import density_ppm2, density_risk
from cv.movement import MovementEstimator
from cv.risk import RiskFactors, RiskTracker, compute


def _interpersonal_distance_m(boxes, frame_w, zone_area_m2) -> float:
    if len(boxes) < 2:
        return 2.0
    cents = np.array([[(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] for b in boxes], dtype=float)
    d = np.linalg.norm(cents[:, None, :] - cents[None, :, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    nn_px = float(np.mean(np.min(d, axis=1)))
    px_per_m = frame_w / max(1.0, math.sqrt(zone_area_m2))
    return round(nn_px / px_per_m, 2) if px_per_m else 2.0


def _annotate(frame, boxes, count, density, score, level) -> str:
    img = frame.copy()
    colors = {"GREEN": (80, 200, 120), "YELLOW": (60, 200, 240), "ORANGE": (40, 140, 255),
              "RED": (60, 60, 240), "BLACK": (140, 40, 160)}
    col = colors.get(level, (200, 200, 200))
    for (x1, y1, x2, y2, c) in boxes:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), col, 2)
    bar_h = 34
    cv2.rectangle(img, (0, 0), (img.shape[1], bar_h), (20, 20, 24), -1)
    cv2.putText(img, f"People: {count}   Density: {density:.1f}/m2   SRI: {score:.0f} {level}",
                (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (235, 235, 235), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def analyze_video(path: str, *, zone_area_m2: float = 100.0, critical_ppm2: float = 5.0,
                  sample_every_n: int = 3, max_frames: int = 4000,
                  emit_frame_every: int = 1) -> Iterator[dict]:
    det = get_detector()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    mover = MovementEstimator()
    rtrack = RiskTracker()

    yield {"kind": "meta", "fps": fps, "frame_count": total, "detector_backend": det.backend,
           "detector_available": det.available}

    idx = emitted = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % sample_every_n == 0:
            t = idx / fps
            boxes = det.detect(frame)
            count = len(boxes)
            dppm2 = density_ppm2(count, zone_area_m2)
            mv = mover.update(frame)
            ipd = _interpersonal_distance_m(boxes, frame.shape[1], zone_area_m2)

            factors = RiskFactors(
                density=density_risk(dppm2, critical_ppm2),
                movement=mv["motion_risk"],
                density_increase=rtrack.density_increase_risk(t, dppm2),
                compression=rtrack.compression_risk(ipd, count),
            )
            r = compute(factors)

            out = {
                "kind": "frame",
                "frame_idx": idx,
                "t_offset_sec": round(t, 2),
                "people_count": count,
                "density_ppm2": dppm2,
                "mean_motion": mv["mean_motion"],
                "turbulence": mv["turbulence"],
                "flow_direction_deg": mv.get("flow_direction_deg"),
                "flow_direction_confidence": mv.get("flow_direction_confidence"),
                "interpersonal_distance_m": ipd,
                "score": r["score"],
                "level": r["level"],
                "label": r["label"],
                "factors": r["factors"],
                "contributions": r["contributions"],
                "boxes": [[round(b[0], 1), round(b[1], 1), round(b[2], 1), round(b[3], 1),
                           round(b[4], 3)] for b in boxes],
                "progress": round(idx / total, 3) if total else None,
            }
            if emitted % emit_frame_every == 0:
                out["annotated_frame"] = _annotate(frame, boxes, count, dppm2, r["score"], r["level"])
            yield out
            emitted += 1
            if emitted >= max_frames:
                break
        idx += 1

    cap.release()
    yield {"kind": "done", "frames_processed": emitted}
