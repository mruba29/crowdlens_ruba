"""Alert -> Incident workflow + incident management."""
from __future__ import annotations
import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.db_models import Alert, Incident, AuditLog, Camera
from app.realtime.hub import hub


def _next_code(db: Session) -> str:
    n = db.query(func.count(Incident.id)).scalar() or 0
    return f"INC-{n + 1:05d}"


def create_from_alert(db: Session, alert_id: str, operator: str,
                      action_taken: str | None = None) -> Incident | None:
    alert = db.get(Alert, alert_id)
    if not alert:
        return None
    now = datetime.datetime.utcnow()
    cam_name = None
    inc = Incident(
        code=_next_code(db), alert_id=alert.id, event_id=alert.event_id,
        zone_id=alert.zone_id, zone_name=alert.zone_name, camera_name=cam_name,
        severity=alert.severity, operator=operator, risk_level=alert.severity, sri=alert.sri,
        feature_snapshot=alert.feature_snapshot or {},
        prediction_snapshot=alert.prediction_snapshot or {},
        action_taken=action_taken or alert.recommended_action,
        resolution_status="IN_PROGRESS",
        timeline=[
            {"time": (alert.created_at or now).isoformat(), "event": f"{alert.severity} alert raised",
             "detail": ", ".join(alert.triggering_features or [])},
            {"time": now.isoformat(), "event": "Operator acknowledged", "detail": operator},
        ],
        notes=[],
    )
    db.add(inc)
    if alert.status == "ACTIVE":
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_at = now
    db.add(AuditLog(actor=operator, action="incident.create", entity_type="incident",
                    entity_id=inc.id, detail={"alert_id": alert.id, "code": inc.code}))
    db.commit()
    db.refresh(inc)
    hub.publish("incident", {"action": "new", "incident": _dict(inc)})
    hub.publish("alert", {"action": "update", "alert": _adict(alert)})
    return inc


def update(db: Session, incident_id: str, *, action_taken=None, resolution=None,
           resolution_status=None, note=None, operator="Control Room Operator") -> Incident | None:
    inc = db.get(Incident, incident_id)
    if not inc:
        return None
    now = datetime.datetime.utcnow()
    tl = list(inc.timeline or [])
    if action_taken:
        inc.action_taken = action_taken
        tl.append({"time": now.isoformat(), "event": "Action recorded", "detail": action_taken})
    if resolution:
        inc.resolution = resolution
    if note:
        inc.notes = list(inc.notes or []) + [{"time": now.isoformat(), "text": note, "by": operator}]
    if resolution_status:
        inc.resolution_status = resolution_status
        tl.append({"time": now.isoformat(), "event": f"Status → {resolution_status}", "detail": operator})
        if resolution_status in ("RESOLVED", "CLOSED"):
            inc.resolved_at = now
    inc.timeline = tl
    db.add(AuditLog(actor=operator, action="incident.update", entity_type="incident",
                    entity_id=inc.id, detail={"resolution_status": resolution_status}))
    db.commit()
    db.refresh(inc)
    hub.publish("incident", {"action": "update", "incident": _dict(inc)})
    return inc


def _dict(o) -> dict:
    d = dict(o.__dict__)
    d.pop("_sa_instance_state", None)
    return d


_adict = _dict
