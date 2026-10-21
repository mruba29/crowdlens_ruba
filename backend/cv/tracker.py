"""Ephemeral multi-object tracking.

Assigns short-lived integer IDs to detected persons, frame to frame, so
crowd-dynamics signals that need continuity (e.g. gate-crossing counts for
inflow/outflow) can be computed for real instead of guessed. IDs are
meaningless outside a single analysis session and are never linked to
identity — ported unchanged from ml_service/app/tracker.py, the standalone
prototype this project already verified, so the crossing-counting logic in
cv/flow.py is built on tested code rather than a new algorithm.

Uses a lightweight IoU + centroid tracker (BYTE-style two-stage association:
high-confidence matches first, then low-confidence recovery) — dependency-free,
consistent with the rest of backend/cv/.
"""
from __future__ import annotations
from dataclasses import dataclass, field


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a[:4]
    bx1, by1, bx2, by2 = b[:4]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


@dataclass
class Track:
    id: int
    box: tuple
    centroid: tuple
    age: int = 0
    misses: int = 0
    history: list = field(default_factory=list)   # recent centroids
    velocity: tuple = (0.0, 0.0)


class ByteStyleTracker:
    def __init__(self, iou_thresh: float = 0.3, max_misses: int = 15,
                 high_conf: float = 0.5, history_len: int = 30):
        self.iou_thresh = iou_thresh
        self.max_misses = max_misses
        self.high_conf = high_conf
        self.history_len = history_len
        self._next = 1
        self.tracks: dict[int, Track] = {}

    def _match(self, dets, track_ids):
        pairs, used_d = [], set()
        for tid in track_ids:
            t = self.tracks[tid]
            best, best_iou = None, self.iou_thresh
            for di, d in enumerate(dets):
                if di in used_d:
                    continue
                v = _iou(t.box, d)
                if v >= best_iou:
                    best, best_iou = di, v
            if best is not None:
                pairs.append((tid, best))
                used_d.add(best)
        return pairs, used_d

    def update(self, detections: list[tuple]) -> dict[int, dict]:
        dets = [tuple(d) for d in detections]
        high = [d for d in dets if d[4] >= self.high_conf]
        low = [d for d in dets if d[4] < self.high_conf]

        active = list(self.tracks.keys())
        # stage 1: high-confidence
        pairs, used_high = self._match(high, active)
        matched_tracks = {tid for tid, _ in pairs}

        # stage 2: recover remaining tracks with low-confidence dets
        remaining = [tid for tid in active if tid not in matched_tracks]
        low_pairs, used_low = self._match(low, remaining)

        def apply(tid, det):
            t = self.tracks[tid]
            cx, cy = (det[0] + det[2]) / 2, (det[1] + det[3]) / 2
            t.velocity = (cx - t.centroid[0], cy - t.centroid[1])
            t.box, t.centroid = det[:4], (cx, cy)
            t.age += 1
            t.misses = 0
            t.history.append((cx, cy))
            if len(t.history) > self.history_len:
                t.history.pop(0)

        for tid, di in pairs:
            apply(tid, high[di])
        for tid, di in low_pairs:
            apply(tid, low[di])

        matched_all = matched_tracks | {tid for tid, _ in low_pairs}
        for tid in active:
            if tid not in matched_all:
                self.tracks[tid].misses += 1
        for tid in [t for t, tr in self.tracks.items() if tr.misses > self.max_misses]:
            del self.tracks[tid]

        # new tracks from unmatched high-confidence detections
        for di, d in enumerate(high):
            if di in used_high:
                continue
            cx, cy = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
            self.tracks[self._next] = Track(id=self._next, box=d[:4], centroid=(cx, cy), history=[(cx, cy)])
            self._next += 1

        return {
            tid: {"centroid": t.centroid, "box": t.box, "velocity": t.velocity, "age": t.age}
            for tid, t in self.tracks.items()
        }
