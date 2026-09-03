"""End-to-end per-video pipeline: decode -> detect -> track -> features -> components.

Yields one result dict per sampled frame so the caller can stream progress
(Server-Sent Events) back to the backend / UI.
"""
from __future__ import annotations
from typing import Iterator
import cv2

from app.detector import Detector
from app.tracker import ByteStyleTracker
from app.features import FeatureExtractor
from app.normalize import to_components

_detector: Detector | None = None


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector()
    return _detector


def analyze_video(path: str, sample_every_n: int = 3, max_frames: int = 600,
                  zone_area_m2: float = 120.0) -> Iterator[dict]:
    det = get_detector()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    tracker = ByteStyleTracker()
    extractor = FeatureExtractor(zone_area_m2=zone_area_m2)

    yield {"kind": "meta", "fps": fps, "frame_count": total, "detector_backend": det.backend,
           "degraded": det.degraded, "available": det.available}

    idx, emitted = 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % sample_every_n == 0:
            t = idx / fps
            dets = det.detect(frame)
            tracks = tracker.update(dets)
            feats = extractor.extract(frame, dets, tracks, t)
            comps = to_components(feats)
            h, w = frame.shape[:2]
            norm_boxes = [[round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4), round(c, 3)]
                          for (x1, y1, x2, y2, c) in dets]
            yield {
                "kind": "frame",
                "frame_idx": idx,
                "features": feats,
                "components": comps,
                "track_ids": sorted(tracks.keys()),
                "detections": norm_boxes,
                "progress": round(emitted / max(1, (total / sample_every_n)), 3) if total else None,
            }
            emitted += 1
            if emitted >= max_frames:
                break
        idx += 1

    cap.release()
    yield {"kind": "done", "frames_processed": emitted}
