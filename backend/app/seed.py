"""Idempotent demo seed: the 'Stadium Exit Surge' event + cameras + zones."""
from __future__ import annotations

from app.core.database import SessionLocal
from app.models.db_models import Event, Camera, Zone
from app.services.evaluation_service import ensure_baseline


def seed() -> None:
    db = SessionLocal()
    try:
        ensure_baseline(db)
        if db.query(Event).count() > 0:
            return

        event = Event(
            name="Stadium Exit Surge",
            event_type="Sports Stadium",
            location="City Stadium — South Stand",
            status="active",
            critical_density_ppm2=5.0,
            rated_structural_capacity_kg=50000.0,
            avg_crowd_weight_kg=70.0,
            prediction_horizon_sec=20,
        )
        db.add(event)
        db.flush()

        zones = [
            Zone(event_id=event.id, name="Zone A — Concourse", role="general",
                 width_m=20, height_m=12, capacity=3000, critical_density_ppm2=4.5,
                 polygon=[[0.02, 0.05], [0.42, 0.05], [0.42, 0.55], [0.02, 0.55]]),
            Zone(event_id=event.id, name="Zone B — North Exit", role="bottleneck",
                 width_m=6, height_m=8, capacity=500, critical_density_ppm2=5.0,
                 polygon=[[0.45, 0.1], [0.7, 0.1], [0.7, 0.62], [0.45, 0.62]]),
            Zone(event_id=event.id, name="Zone C — Ramp", role="exit",
                 width_m=8, height_m=10, capacity=800, critical_density_ppm2=5.0,
                 polygon=[[0.73, 0.08], [0.98, 0.08], [0.98, 0.7], [0.73, 0.7]]),
        ]
        db.add_all(zones)
        db.flush()

        db.add_all([
            Camera(event_id=event.id, code="CAM-01", name="Concourse Overview",
                   status="online", zone_id=zones[0].id, resolution="1920x1080", fps=25),
            Camera(event_id=event.id, code="CAM-04", name="North Exit",
                   status="online", zone_id=zones[1].id, resolution="1920x1080", fps=25),
            Camera(event_id=event.id, code="CAM-05", name="Ramp Camera",
                   status="online", zone_id=zones[2].id, resolution="1280x720", fps=20),
            Camera(event_id=event.id, code="CAM-06", name="South Gate",
                   status="offline", resolution="1920x1080", fps=25),
        ])
        db.commit()
    finally:
        db.close()
