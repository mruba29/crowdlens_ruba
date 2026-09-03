"""Typed request/response models for the CROWDLENS API."""
from __future__ import annotations
import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["GREEN", "YELLOW", "ORANGE", "RED", "BLACK"]
ServiceStatus = Literal["operational", "degraded", "offline"]


# ---------------- Events / cameras / zones ----------------
class ZoneIn(BaseModel):
    name: str
    role: str = "general"
    polygon: list[list[float]] = Field(default_factory=list)
    width_m: float = 5.0
    height_m: float = 5.0
    capacity: int = 500
    critical_density_ppm2: float = 5.0


class ZoneOut(ZoneIn):
    id: str
    event_id: Optional[str] = None
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class CameraIn(BaseModel):
    code: str = "CAM-01"
    name: str = ""
    source_type: str = "upload"
    source_uri: str = ""
    resolution: str = "1920x1080"
    fps: int = 25
    zone_id: Optional[str] = None


class CameraOut(CameraIn):
    id: str
    event_id: Optional[str] = None
    status: str = "offline"
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class EventIn(BaseModel):
    name: str
    event_type: str = "Public Gathering"
    location: str = ""
    critical_density_ppm2: float = 5.0
    alert_thresholds: dict[str, float] = Field(
        default_factory=lambda: {"YELLOW": 31, "ORANGE": 56, "RED": 76, "BLACK": 91}
    )
    rated_structural_capacity_kg: float = 50000.0
    avg_crowd_weight_kg: float = 70.0
    prediction_horizon_sec: int = 20


class EventOut(EventIn):
    id: str
    status: str = "configured"
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    cameras: list[CameraOut] = Field(default_factory=list)
    zones: list[ZoneOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ---------------- Analysis ----------------
class AnalysisStartIn(BaseModel):
    event_id: Optional[str] = None
    camera_id: Optional[str] = None
    mode: Literal["live_cv", "controlled_replay"] = "live_cv"
    video_id: Optional[str] = None          # a previously uploaded video
    speed: float = 1.0                       # controlled_replay playback speed


class AnalysisSessionOut(BaseModel):
    id: str
    event_id: Optional[str] = None
    camera_id: Optional[str] = None
    mode: str
    source: str
    status: str
    ml_backend: Optional[str] = None
    error_message: Optional[str] = None
    video_filename: Optional[str] = None
    fps: Optional[float] = None
    frame_count: Optional[int] = None
    frames_processed: int = 0
    started_at: Optional[datetime.datetime] = None
    ended_at: Optional[datetime.datetime] = None
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


# ---------------- Metrics / risk / prediction ----------------
class CrowdMetricOut(BaseModel):
    session_id: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    t_offset_sec: float = 0.0
    people_count: int = 0
    density_ppm2: float = 0.0
    mean_velocity: float = 0.0
    velocity_variance: float = 0.0
    direction_entropy: float = 0.0
    compression_index: float = 0.0
    pressure_proxy: float = 0.0
    bottleneck_flow_rate: float = 0.0
    queue_disorder: float = 0.0
    fallen_person_flag: bool = False
    interpersonal_distance_m: float = 1.5
    reverse_flow_ratio: float = 0.0
    edge_pressure: float = 0.0
    vulnerability_index: float = 0.0
    stop_wave_propagation: float = 0.0
    dynamics_state: str = "PASSIVE"
    dynamics_confidence: float = 0.5
    track_ids: list[int] = Field(default_factory=list)
    detections: list[list[float]] = Field(default_factory=list)
    source: str = "real_cv"

    class Config:
        from_attributes = True


class RiskScoreOut(BaseModel):
    session_id: Optional[str] = None
    zone_name: Optional[str] = None
    t_offset_sec: float = 0.0
    sri: float = 0.0
    level: RiskLevel = "GREEN"
    components: dict[str, float] = Field(default_factory=dict)
    contributing_factors: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "real_cv"

    class Config:
        from_attributes = True


class PredictionOut(BaseModel):
    session_id: Optional[str] = None
    zone_name: Optional[str] = None
    t_offset_sec: float = 0.0
    current_sri: float = 0.0
    forecast_sri: float = 0.0
    horizon_sec: int = 20
    trend: Literal["INCREASING", "DECREASING", "STABLE"] = "STABLE"
    time_to_critical_sec: Optional[int] = None
    confidence: float = 0.5
    contributing_factors: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "real_cv"

    class Config:
        from_attributes = True


class StructuralMetricOut(BaseModel):
    zone_name: Optional[str] = None
    people_count: int = 0
    estimated_mass_kg: float = 0.0
    rated_capacity_kg: float = 1.0
    load_utilization: float = 0.0
    dynamic_load_factor: float = 1.0
    vibration_freq_hz: float = 0.0
    resonance_detected: bool = False
    visual_deformation: float = 0.0
    structural_risk_level: str = "NORMAL"
    disclaimer: str = "AI-based structural-risk indicator. Not structural certification."

    class Config:
        from_attributes = True


# ---------------- Alerts / incidents ----------------
class AlertOut(BaseModel):
    id: str
    session_id: Optional[str] = None
    zone_name: Optional[str] = None
    severity: RiskLevel
    alert_type: str = "crowd_risk"
    sri: Optional[float] = None
    forecast_sri: Optional[float] = None
    time_to_critical_sec: Optional[int] = None
    triggering_features: list[str] = Field(default_factory=list)
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    prediction_snapshot: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str = ""
    status: str = "ACTIVE"
    source: str = "real_cv"
    created_at: Optional[datetime.datetime] = None
    acknowledged_at: Optional[datetime.datetime] = None
    escalated_at: Optional[datetime.datetime] = None
    resolved_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: str
    code: str
    alert_id: Optional[str] = None
    zone_name: Optional[str] = None
    camera_name: Optional[str] = None
    severity: RiskLevel
    operator: str
    risk_level: str
    sri: Optional[float] = None
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    prediction_snapshot: dict[str, Any] = Field(default_factory=dict)
    action_taken: Optional[str] = None
    resolution: Optional[str] = None
    resolution_status: str = "IN_PROGRESS"
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime.datetime] = None
    resolved_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class IncidentCreateIn(BaseModel):
    alert_id: str
    operator: str = "Control Room Operator"
    action_taken: Optional[str] = None


class IncidentUpdateIn(BaseModel):
    action_taken: Optional[str] = None
    resolution: Optional[str] = None
    resolution_status: Optional[Literal["IN_PROGRESS", "RESOLVED", "CLOSED"]] = None
    note: Optional[str] = None


# ---------------- Evaluation / health ----------------
class EvaluationOut(BaseModel):
    id: str
    label: str
    model_name: str = ""
    is_measured: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)
    targets: dict[str, Any] = Field(default_factory=dict)
    confusion_matrix: Optional[Any] = None
    per_event: Optional[Any] = None
    failure_cases: Optional[Any] = None
    latency_distribution: Optional[Any] = None
    notes: Optional[str] = None
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class ServiceHealth(BaseModel):
    service: str
    status: ServiceStatus
    latency_ms: Optional[float] = None
    fps: Optional[float] = None
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    active_streams: Optional[int] = None
    detail: dict[str, Any] = Field(default_factory=dict)


class SystemHealthOut(BaseModel):
    generated_at: datetime.datetime
    overall: ServiceStatus
    services: list[ServiceHealth]
    ml_service: ServiceStatus
    websocket_clients: int = 0
    api_response_ms: Optional[float] = None
