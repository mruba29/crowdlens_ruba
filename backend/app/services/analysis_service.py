"""Analysis orchestration.

Two modes, one output contract (crowd_update events on /ws/live + rows in
crowd_metrics / risk_scores / predictions):

  live_cv           -> stream frames from the ML service, score each frame
  controlled_replay -> play the deterministic Stadium Exit Surge timeline
                       (clearly labelled, never presented as live inference)
"""
from __future__ import annotations
import asyncio
import datetime
import threading

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core import scenario
from app.models.db_models import (
    AnalysisSession, CrowdMetric, RiskScore, Prediction, Event, Camera, Zone,
)
from app.realtime.hub import hub
from app.services import ml_client, risk_service, alert_service

_runners: dict[str, "AnalysisRunner"] = {}


def get_runner(session_id: str) -> "AnalysisRunner | None":
    return _runners.get(session_id)


def create_session(db: Session, *, event_id, camera_id, mode, video_path=None,
                   video_filename=None) -> AnalysisSession:
    s = AnalysisSession(
        event_id=event_id, camera_id=camera_id, mode=mode,
        source="controlled_replay" if mode == "controlled_replay" else "real_cv",
        video_path=video_path, video_filename=video_filename, status="created",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class AnalysisRunner:
    def __init__(self, session_id: str, speed: float = 1.0):
        self.session_id = session_id
        self.speed = speed
        self.status = "created"
        self.t = 0.0
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_level: str | None = None

    # ---- lifecycle ----
    def start(self):
        if self._thread and self._thread.is_alive():
            self._pause.clear()
            return
        self._stop.clear()
        self._pause.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        self._pause.set()
        self.status = "paused"
        self._push_stage("PAUSED")

    def resume(self):
        self._pause.clear()

    def stop(self):
        self._stop.set()

    # ---- helpers ----
    def _push_stage(self, stage: str, extra: dict | None = None):
        hub.publish("processing_stage", {"session_id": self.session_id, "stage": stage,
                                         **(extra or {})})

    def _cfg(self, db):
        s = db.get(AnalysisSession, self.session_id)
        event = db.get(Event, s.event_id) if s and s.event_id else None
        zone = None
        if s and s.camera_id:
            cam = db.get(Camera, s.camera_id)
            if cam and cam.zone_id:
                zone = db.get(Zone, cam.zone_id)
        if zone is None and event and event.zones:
            zone = event.zones[0]
        return s, event, zone

    def _persist_and_broadcast(self, db, s, event, zone, *, t_offset, people_count,
                               features: dict, components: dict, source: str,
                               track_ids=None, detections=None):
        scored = risk_service.score(components)
        horizon = (event.prediction_horizon_sec if event else 20)
        forecast = risk_service.predict(self.session_id, t_offset, scored["sri"], horizon)
        zone_name = zone.name if zone else (features.get("zone_name") or "Zone A")
        zone_id = zone.id if zone else None

        db.add(CrowdMetric(
            session_id=self.session_id, zone_id=zone_id, zone_name=zone_name,
            t_offset_sec=t_offset, people_count=people_count,
            density_ppm2=features.get("density_ppm2", 0.0),
            mean_velocity=features.get("mean_velocity", 0.0),
            velocity_variance=features.get("velocity_variance", 0.0),
            direction_entropy=features.get("direction_entropy", 0.0),
            compression_index=features.get("compression_index", 0.0),
            pressure_proxy=features.get("pressure_proxy", 0.0),
            bottleneck_flow_rate=features.get("bottleneck_flow_rate", 0.0),
            queue_disorder=features.get("queue_disorder", 0.0),
            fallen_person_flag=bool(features.get("fallen_person_flag", False)),
            interpersonal_distance_m=features.get("interpersonal_distance_m", 1.5),
            reverse_flow_ratio=features.get("reverse_flow_ratio", 0.0),
            edge_pressure=features.get("edge_pressure", 0.0),
            vulnerability_index=features.get("vulnerability_index", 0.0),
            stop_wave_propagation=features.get("stop_wave_propagation", 0.0),
            dynamics_state=features.get("dynamics_state", "PASSIVE"),
            dynamics_confidence=features.get("dynamics_confidence", 0.5),
            track_ids=track_ids or [], detections=detections or [], source=source,
        ))
        db.add(RiskScore(
            session_id=self.session_id, zone_id=zone_id, zone_name=zone_name,
            t_offset_sec=t_offset, sri=scored["sri"], level=scored["level"],
            components=scored["components"], contributing_factors=scored["contributing_factors"],
            source=source,
        ))
        db.add(Prediction(
            session_id=self.session_id, zone_id=zone_id, zone_name=zone_name,
            t_offset_sec=t_offset, current_sri=forecast["current_sri"],
            forecast_sri=forecast["forecast_sri"], horizon_sec=forecast["horizon_sec"],
            trend=forecast["trend"], time_to_critical_sec=forecast["time_to_critical_sec"],
            confidence=forecast["confidence"],
            contributing_factors=scored["contributing_factors"], source=source,
        ))
        db.commit()

        alert_service.maybe_raise(
            db, session_id=self.session_id, event_id=s.event_id if s else None,
            zone_id=zone_id, zone_name=zone_name, sri=scored["sri"], level=scored["level"],
            components=scored["components"], forecast=forecast, source=source,
            last_level=self._last_level,
        )
        self._last_level = scored["level"]

        hub.publish("crowd_update", {
            "session_id": self.session_id, "source": source, "t_offset_sec": round(t_offset, 2),
            "zone_name": zone_name, "people_count": people_count,
            "features": features, "components": scored["components"],
            "sri": scored["sri"], "level": scored["level"],
            "contributing_factors": scored["contributing_factors"],
            "forecast_sri": forecast["forecast_sri"], "trend": forecast["trend"],
            "time_to_critical_sec": forecast["time_to_critical_sec"],
            "prediction_confidence": forecast["confidence"],
            "track_ids": track_ids or [], "detections": detections or [],
        })

    # ---- run loop ----
    def _run(self):
        db = SessionLocal()
        try:
            s, event, zone = self._cfg(db)
            if not s:
                return
            self.status = "processing"
            s.status = "processing"
            s.started_at = datetime.datetime.utcnow()
            db.commit()
            if s.mode == "controlled_replay":
                self._run_replay(db, s, event, zone)
            else:
                self._run_live(db, s, event, zone)
        except ml_client.MLUnavailable as e:
            self._fail(db, "ML service unavailable — analysis stopped. " + str(e), offline=True)
        except Exception as e:  # noqa: BLE001
            self._fail(db, str(e))
        finally:
            db.close()
            _runners.pop(self.session_id, None)

    def _fail(self, db, message: str, offline: bool = False):
        self.status = "offline" if offline else "error"
        s = db.get(AnalysisSession, self.session_id)
        if s:
            s.status = self.status
            s.error_message = message
            db.commit()
        self._push_stage("ML_OFFLINE" if offline else "ERROR", {"message": message})

    def _run_live(self, db, s, event, zone):
        self._push_stage("DETECTING_PEOPLE")
        zone_area = (zone.width_m * zone.height_m) if zone else 120.0
        h = ml_client.health()
        if not h.get("detector_available"):
            raise ml_client.MLUnavailable(h.get("reason") or h.get("note") or "detector unavailable")
        s.ml_backend = h.get("detector_backend")
        db.commit()
        self._push_stage("TRACKING_CROWD")
        n = 0
        for msg in ml_client.analyze_path(s.video_path, sample_every_n=3, max_frames=600,
                                          zone_area_m2=zone_area):
            if self._stop.is_set():
                break
            while self._pause.is_set() and not self._stop.is_set():
                self._pause.wait(0.2)
            kind = msg.get("kind")
            if kind == "meta":
                s.fps = msg.get("fps")
                s.frame_count = msg.get("frame_count")
                db.commit()
            elif kind == "frame":
                f = msg["features"]
                self._persist_and_broadcast(
                    db, s, event, zone, t_offset=f["t_offset_sec"],
                    people_count=f["people_count"], features=f, components=msg["components"],
                    source="real_cv", track_ids=msg.get("track_ids"),
                    detections=msg.get("detections"),
                )
                n += 1
                s.frames_processed = n
                if n % 10 == 0:
                    db.commit()
                self._push_stage("CALCULATING_RISK", {"frames_processed": n})
            elif kind == "done":
                break
        s.status = "completed"
        s.ended_at = datetime.datetime.utcnow()
        s.frames_processed = n
        db.commit()
        self.status = "completed"
        self._push_stage("COMPLETED", {"frames_processed": n})

    def _run_replay(self, db, s, event, zone):
        tick = 0.5
        total = scenario.TOTAL_DURATION_SEC
        self._push_stage("REPLAY_RUNNING")
        while self.t <= total and not self._stop.is_set():
            while self._pause.is_set() and not self._stop.is_set():
                self._pause.wait(0.2)
            st = scenario.sample_at(self.t)
            comps = st["components"]
            features = {
                "t_offset_sec": st["t_offset_sec"],
                "density_ppm2": comps["density"] / 20.0,
                "mean_velocity": st["avg_velocity"],
                "velocity_variance": comps["velocity_variance"],
                "direction_entropy": st.get("direction_entropy", 0.0),
                "compression_index": comps["compressibility"] / 100.0,
                "pressure_proxy": comps["pressure"] / 12.0,
                "reverse_flow_ratio": comps["reverse_flow"] / 100.0,
                "interpersonal_distance_m": st.get("interpersonal_distance_m", 1.0),
                "fallen_person_flag": comps["fallen_person"] >= 0.5,
                "vulnerability_index": comps["age_vulnerability"] / 100.0,
                "edge_pressure": 0.0, "bottleneck_flow_rate": 0.0, "queue_disorder": 0.0,
                "stop_wave_propagation": 0.0,
                "dynamics_state": st["dynamics_state"],
                "dynamics_confidence": st["dynamics_confidence"],
                "stage": st["stage"], "zone_name": st["zone"],
            }
            # replay carries authored component values directly
            components = {k: float(v) for k, v in comps.items()}
            self._persist_and_broadcast(
                db, s, event, zone, t_offset=self.t, people_count=st["people_count"],
                features=features, components=components, source="controlled_replay",
            )
            self._stop.wait(tick / max(0.1, self.speed))
            self.t += tick
        s.status = "completed" if self.t > total else "paused"
        s.ended_at = datetime.datetime.utcnow()
        db.commit()
        self.status = s.status
        self._push_stage("COMPLETED" if self.t > total else "PAUSED")


def start_session(session_id: str, speed: float = 1.0) -> AnalysisRunner:
    runner = _runners.get(session_id)
    if runner is None:
        runner = AnalysisRunner(session_id, speed=speed)
        _runners[session_id] = runner
    else:
        runner.speed = speed
    risk_service.reset_session(session_id)
    runner.start()
    return runner
