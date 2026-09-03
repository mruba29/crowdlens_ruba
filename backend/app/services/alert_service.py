"""Alert generation + lifecycle. Decision-support only — never auto-acts."""
from __future__ import annotations
import datetime

from sqlalchemy.orm import Session

from app.core.alerts import should_alert, detected_signals, RECOMMENDED_ACTIONS
from app.models.db_models import Alert, AuditLog
from app.realtime.hub import hub


def maybe_raise(db: Session, *, session_id: str | None, event_id: str | None,
                zone_id: str | None, zone_name: str, sri: float, level: str,
                components: dict, forecast: dict, source: str,
                last_level: str | None) -> Alert | None:
    """Raise a new alert when the risk band first enters ORANGE/RED/BLACK."""
    if not should_alert(level) or level == last_level:
        return None
    alert = Alert(
        session_id=session_id, event_id=event_id, zone_id=zone_id, zone_name=zone_name,
        severity=level, alert_type="crowd_risk", sri=sri,
        forecast_sri=forecast.get("forecast_sri"),
        time_to_critical_sec=forecast.get("time_to_critical_sec"),
        triggering_features=detected_signals(components),
        feature_snapshot=components,
        prediction_snapshot=forecast,
        recommended_action=RECOMMENDED_ACTIONS.get(level, "Continue monitoring."),
        status="ACTIVE", source=source,
    )
    db.add(alert)
    db.add(AuditLog(actor="system", action="alert.raise", entity_type="alert",
                    entity_id=None, detail={"zone": zone_name, "severity": level, "sri": sri}))
    db.commit()
    db.refresh(alert)
    hub.publish("alert", {"action": "new", "alert": _dict(alert)})
    return alert


def transition(db: Session, alert_id: str, new_status: str, actor: str) -> Alert | None:
    alert = db.get(Alert, alert_id)
    if not alert:
        return None
    now = datetime.datetime.utcnow()
    alert.status = new_status
    if new_status == "ACKNOWLEDGED":
        alert.acknowledged_at = now
    elif new_status == "ESCALATED":
        alert.escalated_at = now
    elif new_status in ("RESOLVED", "FALSE_POSITIVE"):
        alert.resolved_at = now
    db.add(AuditLog(actor=actor, action=f"alert.{new_status.lower()}",
                    entity_type="alert", entity_id=alert_id, detail={}))
    db.commit()
    db.refresh(alert)
    hub.publish("alert", {"action": "update", "alert": _dict(alert)})
    return alert


def _dict(a: Alert) -> dict:
    d = dict(a.__dict__)
    d.pop("_sa_instance_state", None)
    return d
