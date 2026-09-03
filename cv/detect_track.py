"""
CROWDLENS real CV pipeline.

NOTE ON MODEL CHOICE:
The original spec calls for Ultralytics YOLO + ByteTrack. In this build
environment the torch/ultralytics install could not complete (sandbox disk
constraints), so this pipeline uses OpenCV's built-in HOG+SVM person detector
for REAL, non-simulated person detection, and a lightweight centroid tracker
for REAL, ephemeral (non-identity) tracking. The code is structured so a YOLO
detector can be dropped in behind the same `detect_people(frame)` interface
(see `detect_people_yolo_stub` below) without touching the rest of the
pipeline -- this is the production upgrade path, not a redesign.

Privacy: this pipeline never performs face detection, face recognition, or
identity extraction. Track IDs are integers assigned per-video and are
meaningless outside that video/session.
"""
from __future__ import annotations
import cv2
import numpy as np
from dataclasses import dataclass, field


@dataclass
class Track:
    track_id: int
    centroid: tuple
    age: int = 0
    misses: int = 0
    history: list = field(default_factory=list)


class CentroidTracker:
    """Minimal IoU/distance based tracker assigning ephemeral integer IDs."""

    def __init__(self, max_misses=8, max_distance=80):
        self.next_id = 1
        self.tracks: dict[int, Track] = {}
        self.max_misses = max_misses
        self.max_distance = max_distance

    def update(self, detections: list[tuple]) -> dict[int, tuple]:
        centroids = [((x + x2) / 2, (y + y2) / 2) for (x, y, x2, y2, conf) in detections]

        unmatched_dets = set(range(len(centroids)))
        matched_tracks = set()

        for tid, track in list(self.tracks.items()):
            best_idx, best_dist = None, self.max_distance
            for i in unmatched_dets:
                d = np.hypot(track.centroid[0] - centroids[i][0], track.centroid[1] - centroids[i][1])
                if d < best_dist:
                    best_dist, best_idx = d, i
            if best_idx is not None:
                track.centroid = centroids[best_idx]
                track.age += 1
                track.misses = 0
                track.history.append(centroids[best_idx])
                unmatched_dets.discard(best_idx)
                matched_tracks.add(tid)
            else:
                track.misses += 1

        for tid, track in list(self.tracks.items()):
            if track.misses > self.max_misses:
                del self.tracks[tid]

        for i in unmatched_dets:
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = Track(track_id=tid, centroid=centroids[i], history=[centroids[i]])

        return {tid: t.centroid for tid, t in self.tracks.items()}


_hog = cv2.HOGDescriptor()
_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


def detect_people(frame) -> list[tuple]:
    """Real (non-simulated) person detection via HOG+SVM. Returns (x,y,x2,y2,conf)."""
    small = cv2.resize(frame, (min(640, frame.shape[1]), int(frame.shape[0] * min(640, frame.shape[1]) / frame.shape[1])))
    scale_x = frame.shape[1] / small.shape[1]
    scale_y = frame.shape[0] / small.shape[0]
    rects, weights = _hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
    detections = []
    for (x, y, w, h), conf in zip(rects, weights):
        detections.append((x * scale_x, y * scale_y, (x + w) * scale_x, (y + h) * scale_y, float(conf)))
    return detections


def detect_people_yolo_stub(frame):
    """Drop-in upgrade path: replace body with Ultralytics YOLO person-class
    inference and return the same (x,y,x2,y2,conf) tuple list. Left as a stub
    because YOLO weights/torch could not be installed in this environment."""
    raise NotImplementedError("Install ultralytics + torch, then implement this to enable YOLO detection.")


def process_video(path: str, sample_every_n_frames: int = 5, max_frames: int = 200):
    """Process a video file end to end: detection + tracking + basic crowd
    features per sampled frame. Returns a list of per-frame feature dicts."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    tracker = CentroidTracker()
    results = []
    frame_idx = 0
    prev_centroids = {}

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % sample_every_n_frames == 0:
            detections = detect_people(frame)
            tracks = tracker.update(detections)

            velocities = []
            for tid, c in tracks.items():
                if tid in prev_centroids:
                    dx = c[0] - prev_centroids[tid][0]
                    dy = c[1] - prev_centroids[tid][1]
                    velocities.append(float(np.hypot(dx, dy)))
            prev_centroids = tracks

            people_count = len(tracks)
            avg_velocity = float(np.mean(velocities)) if velocities else 0.0
            velocity_variance = float(np.var(velocities)) if velocities else 0.0

            frame_area_px = frame.shape[0] * frame.shape[1]
            density_px = people_count / max(1, frame_area_px) * 1_000_000  # people per Mpx, proxy

            results.append({
                "frame_idx": frame_idx,
                "t_offset_sec": round(frame_idx / fps, 2),
                "people_count": people_count,
                "avg_velocity": round(avg_velocity, 3),
                "velocity_variance": round(velocity_variance, 3),
                "density_proxy_per_mpx": round(density_px, 3),
                "track_ids": list(tracks.keys()),
                "boxes": [(round(d[0]), round(d[1]), round(d[2]), round(d[3]), round(d[4], 2)) for d in detections],
            })
        frame_idx += 1
        if len(results) >= max_frames:
            break

    cap.release()
    return {
        "fps": fps,
        "frames_processed": len(results),
        "results": results,
    }
