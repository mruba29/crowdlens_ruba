"""Person detection.

Primary path: Ultralytics YOLO (person class only).
Fallback path: OpenCV HOG+SVM pedestrian detector (always available).

If neither works the service reports itself DEGRADED and the caller is expected
to surface an explicit "ML Service Offline / degraded" state - never to fabricate
detections.
"""
from __future__ import annotations
import numpy as np

try:  # optional heavy dependency
    from ultralytics import YOLO  # type: ignore
    _HAS_YOLO = True
except Exception:  # pragma: no cover - depends on install
    _HAS_YOLO = False

import cv2

_PERSON_CLASS = 0  # COCO 'person'


class Detector:
    def __init__(self, model_name: str = "yolov8n.pt", conf: float = 0.35):
        self.conf = conf
        self.backend = "unavailable"
        self._yolo = None
        self._hog = None

        if _HAS_YOLO:
            try:
                self._yolo = YOLO(model_name)
                self.backend = f"yolo:{model_name}"
            except Exception:
                self._yolo = None

        if self._yolo is None:
            try:
                self._hog = cv2.HOGDescriptor()
                self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                self.backend = "hog+svm"
            except Exception:
                self._hog = None
                self.backend = "unavailable"

    @property
    def available(self) -> bool:
        return self.backend != "unavailable"

    @property
    def degraded(self) -> bool:
        # HOG works but is the lower-quality fallback.
        return self.backend == "hog+svm"

    def detect(self, frame: np.ndarray) -> list[tuple[float, float, float, float, float]]:
        """Return absolute-pixel (x1, y1, x2, y2, conf) person boxes."""
        if self._yolo is not None:
            res = self._yolo.predict(frame, classes=[_PERSON_CLASS], conf=self.conf, verbose=False)
            out: list[tuple] = []
            for r in res:
                for b in r.boxes:
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    out.append((x1, y1, x2, y2, float(b.conf[0])))
            return out

        if self._hog is not None:
            h, w = frame.shape[:2]
            tw = min(720, w)
            small = cv2.resize(frame, (tw, int(h * tw / w)))
            sx, sy = w / small.shape[1], h / small.shape[0]
            rects, weights = self._hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
            out = []
            for (x, y, bw, bh), wt in zip(rects, weights):
                out.append((x * sx, y * sy, (x + bw) * sx, (y + bh) * sy, float(wt)))
            return out

        return []
