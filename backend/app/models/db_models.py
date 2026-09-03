"""CROWDLENS database schema (PostgreSQL-compatible, SQLite-friendly).

Privacy invariant: NO table stores face images, biometrics, names, or any
personally identifying information. Tracking IDs are ephemeral integers scoped
to a single analysis session. All crowd data is zone-level and time-based.
"""
from __future__ import annotations
import datetime
import uuid

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Text, Index,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def gen_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------
# Event / camera / zone configuration
# --------------------------------------------------------------------------
class Event(Base):
    __tablename__ = "events"
    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    event_type = Column(String, default="Public Gathering")  # Temple Festival / Sports Stadium / Concert / EDM / Protest / Rally / Procession / Public Gathering
    location = Column(String, default="")
    status = Column(String, default="configured")  # configured / active / archived
    # thresholds & structural config
    critical_density_ppm2 = Column(Float, default=5.0)
    alert_thresholds = Column(JSON, default=lambda: {"YELLOW": 31, "ORANGE": 56, "RED": 76, "BLACK": 91})
    rated_structural_capacity_kg = Column(Float, default=50000.0)
    avg_crowd_weight_kg = Column(Float, default=70.0)
    prediction_horizon_sec = Column(Integer, default=20)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    cameras = relationship("Camera", back_populates="event", cascade="all, delete-orphan")
    zones = relationship("Zone", back_populates="event", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"
    id = Column(String, primary_key=True, default=gen_id)
    event_id = Column(String, ForeignKey("events.id"), nullable=True)
    code = Column(String, default="CAM-01")            # human label e.g. "CAM-04"
    name = Column(String, default="")                   # e.g. "North Exit"
    source_type = Column(String, default="upload")      # upload / rtsp / file
    source_uri = Column(String, default="")
    status = Column(String, default="offline")          # online / offline / analyzing / degraded
    resolution = Column(String, default="1920x1080")
    fps = Column(Integer, default=25)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    event = relationship("Event", back_populates="cameras")


class Zone(Base):
    __tablename__ = "zones"
    id = Column(String, primary_key=True, default=gen_id)
    event_id = Column(String, ForeignKey("events.id"), nullable=True)
    name = Column(String, nullable=False)               # "Zone A", "North Exit"
    role = Column(String, default="general")            # entrance / exit / bottleneck / restricted / general
    # polygon in normalized [0..1] image coords: [[x,y], ...]
    polygon = Column(JSON, default=list)
    width_m = Column(Float, default=5.0)
    height_m = Column(Float, default=5.0)
    capacity = Column(Integer, default=500)
    critical_density_ppm2 = Column(Float, default=5.0)
    created_at = Column(DateTime, default=now)

    event = relationship("Event", back_populates="zones")


# --------------------------------------------------------------------------
# Analysis sessions + time-series data
# --------------------------------------------------------------------------
class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"
    id = Column(String, primary_key=True, default=gen_id)
    event_id = Column(String, ForeignKey("events.id"), nullable=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=True)
    mode = Column(String, default="live_cv")            # live_cv / controlled_replay
    source = Column(String, default="real_cv")          # real_cv / controlled_replay
    video_filename = Column(String, nullable=True)
    video_path = Column(String, nullable=True)
    status = Column(String, default="created")          # created / processing / paused / completed / error / offline
    ml_backend = Column(String, nullable=True)          # "yolov8n+bytetrack" / "unavailable"
    error_message = Column(String, nullable=True)
    fps = Column(Float, nullable=True)
    frame_count = Column(Integer, nullable=True)
    frames_processed = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)


class CrowdMetric(Base):
    """One row per (session, zone, time offset). Zone-level aggregate only."""
    __tablename__ = "crowd_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("analysis_sessions.id"), nullable=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    zone_name = Column(String, nullable=True)
    t_offset_sec = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=now)

    people_count = Column(Integer, default=0)
    density_ppm2 = Column(Float, default=0.0)
    mean_velocity = Column(Float, default=0.0)
    velocity_variance = Column(Float, default=0.0)
    direction_entropy = Column(Float, default=0.0)
    compression_index = Column(Float, default=0.0)
    pressure_proxy = Column(Float, default=0.0)
    bottleneck_flow_rate = Column(Float, default=0.0)
    queue_disorder = Column(Float, default=0.0)
    fallen_person_flag = Column(Boolean, default=False)
    interpersonal_distance_m = Column(Float, default=1.5)
    reverse_flow_ratio = Column(Float, default=0.0)
    edge_pressure = Column(Float, default=0.0)
    vulnerability_index = Column(Float, default=0.0)
    stop_wave_propagation = Column(Float, default=0.0)

    dynamics_state = Column(String, default="PASSIVE")  # PASSIVE / ACTIVE / VOLATILE / PANIC
    dynamics_confidence = Column(Float, default=0.5)
    track_ids = Column(JSON, default=list)              # ephemeral ints, no identity
    detections = Column(JSON, default=list)             # [[x,y,x2,y2,conf], ...] normalized
    source = Column(String, default="real_cv")

    __table_args__ = (Index("ix_crowd_metrics_session_t", "session_id", "t_offset_sec"),)


class RiskScore(Base):
    __tablename__ = "risk_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("analysis_sessions.id"), nullable=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    zone_name = Column(String, nullable=True)
    t_offset_sec = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=now)
    sri = Column(Float, default=0.0)
    level = Column(String, default="GREEN")             # GREEN/YELLOW/ORANGE/RED/BLACK
    components = Column(JSON, default=dict)             # normalized 0-100 per feature
    contributing_factors = Column(JSON, default=list)   # ranked [{factor,value,weight,contribution,band}]
    source = Column(String, default="real_cv")

    __table_args__ = (Index("ix_risk_scores_session_t", "session_id", "t_offset_sec"),)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("analysis_sessions.id"), nullable=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    zone_name = Column(String, nullable=True)
    t_offset_sec = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=now)
    current_sri = Column(Float, default=0.0)
    forecast_sri = Column(Float, default=0.0)
    horizon_sec = Column(Integer, default=20)
    trend = Column(String, default="STABLE")            # INCREASING / DECREASING / STABLE
    time_to_critical_sec = Column(Integer, nullable=True)
    confidence = Column(Float, default=0.5)
    contributing_factors = Column(JSON, default=list)
    source = Column(String, default="real_cv")


class StructuralMetric(Base):
    __tablename__ = "structural_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("analysis_sessions.id"), nullable=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    zone_name = Column(String, nullable=True)
    t_offset_sec = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=now)
    people_count = Column(Integer, default=0)
    estimated_mass_kg = Column(Float, default=0.0)
    rated_capacity_kg = Column(Float, default=1.0)
    load_utilization = Column(Float, default=0.0)
    dynamic_load_factor = Column(Float, default=1.0)
    vibration_freq_hz = Column(Float, default=0.0)
    resonance_detected = Column(Boolean, default=False)
    visual_deformation = Column(Float, default=0.0)
    structural_risk_level = Column(String, default="NORMAL")
    disclaimer = Column(String, default="AI-based structural-risk indicator. Not structural certification.")


# --------------------------------------------------------------------------
# Alerts + incidents + audit
# --------------------------------------------------------------------------
class Alert(Base):
    __tablename__ = "alerts"
    id = Column(String, primary_key=True, default=gen_id)
    session_id = Column(String, ForeignKey("analysis_sessions.id"), nullable=True)
    event_id = Column(String, ForeignKey("events.id"), nullable=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    zone_name = Column(String, nullable=True)
    severity = Column(String, default="YELLOW")
    alert_type = Column(String, default="crowd_risk")
    sri = Column(Float, nullable=True)
    forecast_sri = Column(Float, nullable=True)
    time_to_critical_sec = Column(Integer, nullable=True)
    triggering_features = Column(JSON, default=list)    # human-readable signal strings
    feature_snapshot = Column(JSON, default=dict)       # component values at trigger
    prediction_snapshot = Column(JSON, default=dict)
    recommended_action = Column(String, default="")
    status = Column(String, default="ACTIVE")           # ACTIVE / ACKNOWLEDGED / ESCALATED / RESOLVED / FALSE_POSITIVE
    source = Column(String, default="real_cv")
    created_at = Column(DateTime, default=now)
    acknowledged_at = Column(DateTime, nullable=True)
    escalated_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(String, primary_key=True, default=gen_id)
    code = Column(String, unique=True)                  # "INC-00021"
    alert_id = Column(String, ForeignKey("alerts.id"), nullable=True)
    event_id = Column(String, ForeignKey("events.id"), nullable=True)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    zone_name = Column(String, nullable=True)
    camera_name = Column(String, nullable=True)
    severity = Column(String, default="YELLOW")
    operator = Column(String, default="Control Room Operator")
    risk_level = Column(String, default="YELLOW")
    sri = Column(Float, nullable=True)
    feature_snapshot = Column(JSON, default=dict)
    prediction_snapshot = Column(JSON, default=dict)
    action_taken = Column(String, nullable=True)
    resolution = Column(String, nullable=True)
    resolution_status = Column(String, default="IN_PROGRESS")  # IN_PROGRESS / RESOLVED / CLOSED
    timeline = Column(JSON, default=list)               # [{time,event,detail}]
    notes = Column(JSON, default=list)
    created_at = Column(DateTime, default=now)
    resolved_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=now)
    actor = Column(String, default="system")
    action = Column(String, nullable=False)             # e.g. "alert.acknowledge"
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    detail = Column(JSON, default=dict)


# --------------------------------------------------------------------------
# Model evaluation + system health
# --------------------------------------------------------------------------
class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    id = Column(String, primary_key=True, default=gen_id)
    label = Column(String, default="Untitled evaluation run")
    model_name = Column(String, default="")
    is_measured = Column(Boolean, default=False)        # False => these are TARGETS only
    metrics = Column(JSON, default=dict)                # {crowd_detection_map: 0.8, ...}
    targets = Column(JSON, default=dict)
    confusion_matrix = Column(JSON, nullable=True)
    per_event = Column(JSON, nullable=True)
    failure_cases = Column(JSON, nullable=True)
    latency_distribution = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)


class SystemHealthSample(Base):
    __tablename__ = "system_health"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=now)
    service = Column(String, nullable=False)            # frontend / backend / ml_service / database / websocket / camera_streams
    status = Column(String, default="operational")      # operational / degraded / offline
    latency_ms = Column(Float, nullable=True)
    fps = Column(Float, nullable=True)
    cpu_percent = Column(Float, nullable=True)
    memory_percent = Column(Float, nullable=True)
    active_streams = Column(Integer, nullable=True)
    detail = Column(JSON, default=dict)
