"""Alerts, incidents, evaluations, system health, controlled-replay scenario."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core import scenario
from app.models.db_models import Alert, Incident, AuditLog, ModelEvaluation
from app.services import alert_service, incident_service, evaluation_service, health_service
from app import schemas

router = APIRouter(prefix="/api", tags=["operations"])


def _d(o):
    d = dict(o.__dict__)
    d.pop("_sa_instance_state", None)
    return d


# ---------------- Alerts ----------------
@router.get("/alerts")
def list_alerts(status: str | None = None, session_id: str | None = None,
                db: Session = Depends(get_db)):
    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status)
    if session_id:
        q = q.filter(Alert.session_id == session_id)
    return [_d(a) for a in q.order_by(desc(Alert.created_at)).all()]


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    return _d(a)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: str, operator: str = Body("Control Room Operator", embed=True),
                db: Session = Depends(get_db)):
    inc = incident_service.create_from_alert(db, alert_id, operator)
    if not inc:
        raise HTTPException(404, "alert not found")
    a = db.get(Alert, alert_id)
    return {"alert": _d(a), "incident": _d(inc)}


@router.post("/alerts/{alert_id}/escalate")
def escalate(alert_id: str, operator: str = Body("Control Room Operator", embed=True),
             db: Session = Depends(get_db)):
    a = alert_service.transition(db, alert_id, "ESCALATED", operator)
    if not a:
        raise HTTPException(404, "alert not found")
    return _d(a)


@router.post("/alerts/{alert_id}/resolve")
def resolve(alert_id: str, operator: str = Body("Control Room Operator", embed=True),
            db: Session = Depends(get_db)):
    a = alert_service.transition(db, alert_id, "RESOLVED", operator)
    if not a:
        raise HTTPException(404, "alert not found")
    return _d(a)


@router.post("/alerts/{alert_id}/false-positive")
def false_positive(alert_id: str, operator: str = Body("Control Room Operator", embed=True),
                   db: Session = Depends(get_db)):
    a = alert_service.transition(db, alert_id, "FALSE_POSITIVE", operator)
    if not a:
        raise HTTPException(404, "alert not found")
    return _d(a)


# ---------------- Incidents ----------------
@router.get("/incidents")
def list_incidents(status: str | None = None, severity: str | None = None,
                   zone: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Incident)
    if status:
        q = q.filter(Incident.resolution_status == status)
    if severity:
        q = q.filter(Incident.severity == severity)
    if zone:
        q = q.filter(Incident.zone_name == zone)
    return [_d(i) for i in q.order_by(desc(Incident.created_at)).all()]


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    i = db.get(Incident, incident_id)
    if not i:
        raise HTTPException(404, "incident not found")
    audit = (db.query(AuditLog).filter(AuditLog.entity_id == incident_id)
             .order_by(AuditLog.timestamp).all())
    return {**_d(i), "audit_trail": [_d(a) for a in audit]}


@router.post("/incidents")
def create_incident(payload: schemas.IncidentCreateIn, db: Session = Depends(get_db)):
    inc = incident_service.create_from_alert(db, payload.alert_id, payload.operator,
                                             payload.action_taken)
    if not inc:
        raise HTTPException(404, "alert not found")
    return _d(inc)


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: str, payload: schemas.IncidentUpdateIn,
                    db: Session = Depends(get_db)):
    inc = incident_service.update(db, incident_id, **payload.model_dump(exclude_none=True))
    if not inc:
        raise HTTPException(404, "incident not found")
    return _d(inc)


# ---------------- Evaluations ----------------
@router.get("/evaluations", response_model=list[schemas.EvaluationOut])
def list_evaluations(db: Session = Depends(get_db)):
    evaluation_service.ensure_baseline(db)
    return evaluation_service.list_all(db)


@router.post("/evaluations", response_model=schemas.EvaluationOut, status_code=201)
def upload_evaluation(payload: dict = Body(...), db: Session = Depends(get_db)):
    return evaluation_service.create(db, payload)


# ---------------- System health ----------------
@router.get("/system/health", response_model=schemas.SystemHealthOut)
def system_health(db: Session = Depends(get_db)):
    return health_service.snapshot(db)


# ---------------- Controlled Evaluation Replay ----------------
@router.get("/scenario/info")
def scenario_info():
    return {
        "name": scenario.SCENARIO_NAME,
        "zone": scenario.SCENARIO_ZONE,
        "total_duration_sec": scenario.TOTAL_DURATION_SEC,
        "timeline": scenario.timeline_markers(),
        "label": "Controlled Evaluation / Presentation Scenario",
        "disclaimer": "Deterministic replay. Not real-world live inference.",
    }


@router.get("/scenario/state")
def scenario_state(t: float = 0):
    return scenario.sample_at(t)
