"""Person detection.

Primary:  Ultralytics YOLO (person class only) — used automatically if installed.
Fallback: OpenCV HOG + SVM pedestrian detector (always available with opencv).

If neither is usable, `Detector.available` is False and the API reports the
detector as unavailable — we never fabricate detections.

Privacy: detection only. No face detection, no recognition, no identity.
"""
from __future__ import annotations
import numpy as np
import cv2

try:
    from ultralytics import YOLO  # type: ignore
    _HAS_YOLO = True
except Exception:
    _HAS_YOLO = False

_PERSON_CLASS = 0  # COCO 'person'


class Detector:
    def __init__(self, conf: float = 0.35, model_name: str = "yolov8n.pt"):
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
                self.backend = "unavailable"

    @property
    def available(self) -> bool:
        return self.backend != "unavailable"

    @property
    def is_yolo(self) -> bool:
        return self.backend.startswith("yolo")

    def set_confidence(self, conf: float) -> None:
        self.conf = max(0.05, min(0.95, float(conf)))

    def detect(self, frame: np.ndarray) -> list[tuple[float, float, float, float, float]]:
        """Return (x1, y1, x2, y2, confidence) person boxes in absolute pixels."""
        if self._yolo is not None:
            res = self._yolo.predict(frame, classes=[_PERSON_CLASS], conf=self.conf, verbose=False)
            out: list[tuple] = []
            for r in res:
                for b in r.boxes:
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    out.append((float(x1), float(y1), float(x2), float(y2), float(b.conf[0])))
            return out

        if self._hog is not None:
            h, w = frame.shape[:2]
            tw = min(720, w)
            small = cv2.resize(frame, (tw, max(1, int(h * tw / w))))
            sx, sy = w / small.shape[1], h / small.shape[0]
            rects, weights = self._hog.detectMultiScale(small, winStride=(8, 8),
                                                        padding=(8, 8), scale=1.05)
            out = []
            for (x, y, bw, bh), wt in zip(rects, weights):
                if wt < self.conf * 2:  # HOG weights aren't 0-1; loose gate
                    continue
                out.append((x * sx, y * sy, (x + bw) * sx, (y + bh) * sy, float(min(1.0, wt / 3))))
            return out

        return []


_detector: Detector | None = None


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector()
    return _detector
