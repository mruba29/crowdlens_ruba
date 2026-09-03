"""Events, cameras, zones — configuration CRUD."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import Event, Camera, Zone
from app import schemas

router = APIRouter(prefix="/api", tags=["configuration"])


def _d(o):
    d = dict(o.__dict__)
    d.pop("_sa_instance_state", None)
    return d


# ---- events ----
@router.get("/events", response_model=list[schemas.EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.query(Event).order_by(Event.created_at.desc()).all()


@router.get("/events/{event_id}", response_model=schemas.EventOut)
def get_event(event_id: str, db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "event not found")
    return ev


@router.post("/events", response_model=schemas.EventOut, status_code=201)
def create_event(payload: schemas.EventIn, db: Session = Depends(get_db)):
    ev = Event(**payload.model_dump())
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@router.put("/events/{event_id}", response_model=schemas.EventOut)
def update_event(event_id: str, payload: schemas.EventIn, db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "event not found")
    for k, v in payload.model_dump().items():
        setattr(ev, k, v)
    db.commit()
    db.refresh(ev)
    return ev


# ---- zones ----
@router.get("/zones", response_model=list[schemas.ZoneOut])
def list_zones(event_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Zone)
    if event_id:
        q = q.filter(Zone.event_id == event_id)
    return q.all()


@router.post("/zones", response_model=schemas.ZoneOut, status_code=201)
def create_zone(payload: dict, db: Session = Depends(get_db)):
    z = Zone(**payload)
    db.add(z)
    db.commit()
    db.refresh(z)
    return z


@router.put("/zones/{zone_id}", response_model=schemas.ZoneOut)
def update_zone(zone_id: str, payload: dict, db: Session = Depends(get_db)):
    z = db.get(Zone, zone_id)
    if not z:
        raise HTTPException(404, "zone not found")
    for k, v in payload.items():
        setattr(z, k, v)
    db.commit()
    db.refresh(z)
    return z


@router.delete("/zones/{zone_id}", status_code=204)
def delete_zone(zone_id: str, db: Session = Depends(get_db)):
    z = db.get(Zone, zone_id)
    if z:
        db.delete(z)
        db.commit()


# ---- cameras ----
@router.get("/cameras", response_model=list[schemas.CameraOut])
def list_cameras(event_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Camera)
    if event_id:
        q = q.filter(Camera.event_id == event_id)
    return q.all()


@router.post("/cameras", response_model=schemas.CameraOut, status_code=201)
def create_camera(payload: dict, db: Session = Depends(get_db)):
    c = Camera(**payload)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/cameras/{camera_id}", response_model=schemas.CameraOut)
def update_camera(camera_id: str, payload: dict, db: Session = Depends(get_db)):
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "camera not found")
    for k, v in payload.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c
