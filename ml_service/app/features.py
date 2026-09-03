"""Crowd feature extraction from detections + tracks + optical flow.

Everything here is aggregate and anonymous: counts, densities, velocity
statistics, flow direction. No per-person attributes leave this module.

Outputs are raw physical-ish quantities; normalization to 0-100 risk
components happens in `normalize.py` so the raw values stay inspectable.
"""
from __future__ import annotations
import math
import numpy as np
import cv2


def _entropy(values: list[float], bins: int = 8) -> float:
    if len(values) < 2:
        return 0.0
    hist, _ = np.histogram(values, bins=bins, range=(-math.pi, math.pi))
    p = hist / max(1, hist.sum())
    p = p[p > 0]
    h = -(p * np.log(p)).sum()
    return float(h / math.log(bins))  # 0..1


class FeatureExtractor:
    def __init__(self, zone_area_m2: float = 100.0):
        self.zone_area_m2 = max(1.0, zone_area_m2)
        self._prev_gray: np.ndarray | None = None
        self._prev_track_centroids: dict[int, tuple] = {}
        self._reference_flow_dir: float | None = None

    def extract(self, frame: np.ndarray, detections: list[tuple], tracks: dict[int, dict],
                t_offset_sec: float) -> dict:
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        people = len(tracks)

        # ---- density (people per m^2), using a zone-area estimate ----
        density_ppm2 = people / self.zone_area_m2

        # ---- velocities from track displacement ----
        speeds, dirs = [], []
        for tid, t in tracks.items():
            vx, vy = t["velocity"]
            sp = math.hypot(vx, vy)
            speeds.append(sp)
            if sp > 0.5:
                dirs.append(math.atan2(vy, vx))
        mean_v = float(np.mean(speeds)) if speeds else 0.0
        var_v = float(np.var(speeds)) if speeds else 0.0
        direction_entropy = _entropy(dirs)

        # ---- reverse flow: fraction of movers opposing the dominant direction ----
        reverse_flow = 0.0
        if dirs:
            mean_dir = math.atan2(float(np.mean(np.sin(dirs))), float(np.mean(np.cos(dirs))))
            if self._reference_flow_dir is None and len(dirs) >= 3:
                self._reference_flow_dir = mean_dir
            ref = self._reference_flow_dir if self._reference_flow_dir is not None else mean_dir
            opposing = sum(1 for d in dirs if abs(math.atan2(math.sin(d - ref), math.cos(d - ref))) > math.pi / 2)
            reverse_flow = opposing / len(dirs)

        # ---- optical flow turbulence (dense Farneback magnitude variance) ----
        turbulence = 0.0
        flow_mag_mean = 0.0
        if self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            flow = cv2.calcOpticalFlowFarneback(self._prev_gray, gray, None,
                                                0.5, 2, 15, 3, 5, 1.2, 0)
            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            flow_mag_mean = float(mag.mean())
            turbulence = float(mag.var())
        self._prev_gray = gray

        # ---- interpersonal distance (nearest-neighbour mean over centroids) ----
        cents = np.array([t["centroid"] for t in tracks.values()], dtype=float)
        interpersonal_px = 0.0
        if len(cents) >= 2:
            d = np.linalg.norm(cents[:, None, :] - cents[None, :, :], axis=-1)
            np.fill_diagonal(d, np.inf)
            interpersonal_px = float(np.mean(np.min(d, axis=1)))
        # rough px->m using frame width ~ sqrt(zone_area)*scale
        px_per_m = w / math.sqrt(self.zone_area_m2) if self.zone_area_m2 else w
        interpersonal_m = interpersonal_px / px_per_m if px_per_m else 0.0

        # ---- compression index: inverse of interpersonal distance, capped ----
        compression = 0.0
        if interpersonal_m > 0:
            compression = min(1.0, 0.6 / interpersonal_m)
        elif people > 1:
            compression = 1.0

        # ---- pressure proxy: density * (compression + turbulence term) ----
        pressure_proxy = density_ppm2 * (0.5 + compression) + turbulence * 0.05

        # ---- edge pressure: centroid concentration near frame borders ----
        edge_pressure = 0.0
        if len(cents):
            margin_x, margin_y = w * 0.12, h * 0.12
            near = np.sum((cents[:, 0] < margin_x) | (cents[:, 0] > w - margin_x) |
                          (cents[:, 1] < margin_y) | (cents[:, 1] > h - margin_y))
            edge_pressure = float(near / len(cents))

        # ---- bottleneck flow rate: movers per second crossing frame mid-line ----
        bottleneck_flow = 0.0
        for tid, t in tracks.items():
            prev = self._prev_track_centroids.get(tid)
            if prev is not None and (prev[0] - w / 2) * (t["centroid"][0] - w / 2) < 0:
                bottleneck_flow += 1
        self._prev_track_centroids = {tid: t["centroid"] for tid, t in tracks.items()}

        # ---- queue disorder: spread of speeds when crowd is slow (queueing) ----
        queue_disorder = 0.0
        if mean_v < 2.0 and speeds:
            queue_disorder = min(1.0, float(np.std(speeds)) / 2.0)

        # ---- stop-wave propagation: alternating slow/fast bands (proxy) ----
        stop_wave = 0.0
        if len(speeds) >= 6:
            arr = np.array(speeds)
            slow_frac = float(np.mean(arr < 0.5))
            stop_wave = slow_frac * min(1.0, var_v)

        # ---- fallen person flag: very low box aspect ratio (wide & short) ----
        fallen = False
        for (x1, y1, x2, y2, c) in detections:
            bw, bh = (x2 - x1), (y2 - y1)
            if bh > 0 and (bw / bh) > 1.6 and c > 0.4:
                fallen = True
                break

        # ---- vulnerability index: placeholder aggregate (no age/gender inference) ----
        # Derived only from crowd geometry: high when dense + slow + compressed.
        vulnerability = min(1.0, 0.4 * min(1.0, density_ppm2 / 6.0) + 0.3 * compression +
                            0.3 * (1.0 if mean_v < 0.5 and people > 5 else 0.0))

        # ---- dynamics state classification ----
        state, conf = self._classify(density_ppm2, var_v, turbulence, reverse_flow, mean_v)

        return {
            "t_offset_sec": round(t_offset_sec, 2),
            "people_count": people,
            "density_ppm2": round(density_ppm2, 3),
            "mean_velocity": round(mean_v, 3),
            "velocity_variance": round(var_v, 3),
            "direction_entropy": round(direction_entropy, 3),
            "compression_index": round(compression, 3),
            "pressure_proxy": round(pressure_proxy, 3),
            "bottleneck_flow_rate": round(bottleneck_flow, 2),
            "queue_disorder": round(queue_disorder, 3),
            "fallen_person_flag": bool(fallen),
            "interpersonal_distance_m": round(interpersonal_m, 2),
            "reverse_flow_ratio": round(reverse_flow, 3),
            "edge_pressure": round(edge_pressure, 3),
            "vulnerability_index": round(vulnerability, 3),
            "stop_wave_propagation": round(stop_wave, 3),
            "optical_flow_magnitude": round(flow_mag_mean, 3),
            "turbulence": round(turbulence, 3),
            "dynamics_state": state,
            "dynamics_confidence": round(conf, 2),
        }

    @staticmethod
    def _classify(density, var_v, turbulence, reverse_flow, mean_v):
        score = 0.0
        score += min(1.0, density / 6.0) * 0.35
        score += min(1.0, var_v / 40.0) * 0.25
        score += min(1.0, turbulence / 20.0) * 0.2
        score += reverse_flow * 0.2
        if score < 0.25:
            return "PASSIVE", 0.9 - score
        if score < 0.5:
            return "ACTIVE", 0.85
        if score < 0.75:
            return "VOLATILE", 0.8
        return "PANIC", min(0.95, 0.6 + score / 3)
