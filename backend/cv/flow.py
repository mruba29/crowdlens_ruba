"""Gate inflow/outflow — counts real tracked people crossing the frame's
vertical midline, split by direction, using cv/tracker.py's frame-to-frame
centroid tracking. This is a real, computed signal (not a guess): a track's
centroid genuinely has to cross from one side to the other between two
frames to be counted.

What this can't honestly claim: which crossing direction corresponds to
"into the venue" for a specific real gate — that needs a calibrated
camera-to-map projection, which CROWDLENS does not have yet (see the Phase 1
report). So the operator declares which crossing direction ("left" or
"right") counts as inflow when attaching a video to an entrance/exit/
bottleneck zone; that assumption is carried in the API response, never hidden.
"""
from __future__ import annotations
from collections import deque


class FlowCounter:
    def __init__(self, window_sec: float = 60.0):
        self.window_sec = window_sec
        self._events: deque[tuple[float, str]] = deque()   # (t_offset_sec, "left"|"right")
        self._prev_cx: dict[int, float] = {}
        self.total_left = 0
        self.total_right = 0

    def update(self, t: float, tracks: dict[int, dict], frame_w: float) -> None:
        mid = frame_w / 2
        seen = set()
        for tid, tr in tracks.items():
            seen.add(tid)
            cx = tr["centroid"][0]
            prev = self._prev_cx.get(tid)
            if prev is not None and (prev - mid) * (cx - mid) < 0:
                direction = "right" if cx > prev else "left"
                self._events.append((t, direction))
                if direction == "right":
                    self.total_right += 1
                else:
                    self.total_left += 1
            self._prev_cx[tid] = cx
        # forget tracks that vanished (occluded / left frame / dropped) so a
        # stale centroid can't be compared against a much-later reappearance
        for tid in list(self._prev_cx):
            if tid not in seen:
                del self._prev_cx[tid]
        while self._events and t - self._events[0][0] > self.window_sec:
            self._events.popleft()

    def rates(self, inflow_direction: str) -> dict:
        outflow_direction = "left" if inflow_direction == "right" else "right"
        in_n = sum(1 for _, d in self._events if d == inflow_direction)
        out_n = sum(1 for _, d in self._events if d == outflow_direction)
        span_min = max(1e-6, self.window_sec / 60.0)
        return {
            "inflow_rate_per_min": round(in_n / span_min, 1),
            "outflow_rate_per_min": round(out_n / span_min, 1),
            "window_sec": self.window_sec,
            "sample_events": len(self._events),
            "total_in": self.total_right if inflow_direction == "right" else self.total_left,
            "total_out": self.total_left if inflow_direction == "right" else self.total_right,
        }
