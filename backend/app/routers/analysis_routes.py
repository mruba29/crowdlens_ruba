"""Video upload + analysis session lifecycle + metrics/risk/prediction queries."""
from __future__ import annotations
import os
import shutil
import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.config import settings
from app.models.db_models import (
    AnalysisSession, CrowdMetric, RiskScore, Prediction, StructuralMetric, Event,
)
from app.services import analysis_service, risk_service
from app import schemas

router = APIRouter(prefix="/api", tags=["analysis"])


def _d(o):
    d = dict(o.__dict__)
    d.pop("_sa_instance_state", None)
    return d


@router.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    safe = os.path.basename(file.filename or "video.mp4")
    dest = os.path.join(settings.UPLOAD_DIR, f"{datetime.datetime.utcnow().timestamp()}_{safe}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"video_id": os.path.basename(dest), "filename": safe, "stored_path": dest}


@router.post("/analysis/start", response_model=schemas.AnalysisSessionOut)
def start_analysis(payload: schemas.AnalysisStartIn, db: Session = Depends(get_db)):
    video_path = None
    video_filename = None
    if payload.mode == "live_cv":
        if not payload.video_id:
            raise HTTPException(400, "video_id required for live_cv analysis")
        video_path = os.path.join(settings.UPLOAD_DIR, os.path.basename(payload.video_id))
        if not os.path.exists(video_path):
            raise HTTPException(404, "uploaded video not found")
        video_filename = payload.video_id

    event_id = payload.event_id
    if not event_id:
        ev = db.query(Event).order_by(Event.created_at).first()
        event_id = ev.id if ev else None

    s = analysis_service.create_session(
        db, event_id=event_id, camera_id=payload.camera_id, mode=payload.mode,
        video_path=video_path, video_filename=video_filename,
    )
    analysis_service.start_session(s.id, speed=payload.speed)
    db.refresh(s)
    return s


@router.post("/analysis/{session_id}/pause", response_model=schemas.AnalysisSessionOut)
def pause_analysis(session_id: str, db: Session = Depends(get_db)):
    r = analysis_service.get_runner(session_id)
    if r:
        r.pause()
    s = db.get(AnalysisSession, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.post("/analysis/{session_id}/resume", response_model=schemas.AnalysisSessionOut)
def resume_analysis(session_id: str, speed: float = 1.0, db: Session = Depends(get_db)):
    analysis_service.start_session(session_id, speed=speed)
    s = db.get(AnalysisSession, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.post("/analysis/{session_id}/stop", response_model=schemas.AnalysisSessionOut)
def stop_analysis(session_id: str, db: Session = Depends(get_db)):
    r = analysis_service.get_runner(session_id)
    if r:
        r.stop()
    s = db.get(AnalysisSession, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    s.status = "completed"
    db.commit()
    return s


@router.get("/analysis", response_model=list[schemas.AnalysisSessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(AnalysisSession).order_by(desc(AnalysisSession.created_at)).all()


@router.get("/analysis/{session_id}", response_model=schemas.AnalysisSessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(AnalysisSession, session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.get("/analysis/{session_id}/metrics")
def session_metrics(session_id: str, limit: int = 500, db: Session = Depends(get_db)):
    rows = (db.query(CrowdMetric).filter(CrowdMetric.session_id == session_id)
            .order_by(CrowdMetric.id.desc()).limit(limit).all())
    return [_d(r) for r in reversed(rows)]


@router.get("/analysis/{session_id}/risk")
def session_risk(session_id: str, limit: int = 500, db: Session = Depends(get_db)):
    rows = (db.query(RiskScore).filter(RiskScore.session_id == session_id)
            .order_by(RiskScore.id.desc()).limit(limit).all())
    return [_d(r) for r in reversed(rows)]


@router.get("/analysis/{session_id}/prediction")
def session_prediction(session_id: str, limit: int = 500, db: Session = Depends(get_db)):
    rows = (db.query(Prediction).filter(Prediction.session_id == session_id)
            .order_by(Prediction.id.desc()).limit(limit).all())
    return [_d(r) for r in reversed(rows)]


# ---- zone-scoped latest ----
@router.get("/zones/{zone_id}/metrics")
def zone_metrics(zone_id: str, limit: int = 200, db: Session = Depends(get_db)):
    rows = (db.query(CrowdMetric).filter(CrowdMetric.zone_id == zone_id)
            .order_by(CrowdMetric.id.desc()).limit(limit).all())
    return [_d(r) for r in reversed(rows)]


@router.get("/zones/{zone_id}/risk")
def zone_risk(zone_id: str, limit: int = 200, db: Session = Depends(get_db)):
    rows = (db.query(RiskScore).filter(RiskScore.zone_id == zone_id)
            .order_by(RiskScore.id.desc()).limit(limit).all())
    return [_d(r) for r in reversed(rows)]


@router.get("/zones/{zone_id}/prediction")
def zone_prediction(zone_id: str, db: Session = Depends(get_db)):
    row = (db.query(Prediction).filter(Prediction.zone_id == zone_id)
           .order_by(Prediction.id.desc()).first())
    return _d(row) if row else {}


@router.get("/structural")
def structural_indicator(people_count: int = 500, event_id: str | None = None,
                         dynamic_load_factor: float = 1.4, vibration_freq_hz: float = 2.3,
                         visual_deformation: float = 0.0, resonance_detected: bool = False,
                         db: Session = Depends(get_db)):
    ev = db.get(Event, event_id) if event_id else db.query(Event).first()
    cap = ev.rated_structural_capacity_kg if ev else 50000.0
    weight = ev.avg_crowd_weight_kg if ev else 70.0
    return risk_service.structural(people_count, weight, cap, dynamic_load_factor,
                                   vibration_freq_hz, visual_deformation, resonance_detected)
