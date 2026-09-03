"""Model evaluation. Ships with TARGETS only until a measured run is uploaded."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.db_models import ModelEvaluation

TARGETS = {
    "crowd_detection_map": {"target": 0.78, "comparator": ">="},
    "event_classification_accuracy": {"target": 0.85, "comparator": ">="},
    "dynamics_state_f1": {"target": 0.75, "comparator": ">="},
    "stampede_prediction_precision": {"target": 0.80, "comparator": ">="},
    "fallen_person_recall": {"target": 0.90, "comparator": ">="},
    "structural_load_error_pct": {"target": 15.0, "comparator": "<=|abs"},
    "alert_latency_sec": {"target": 2.0, "comparator": "<"},
}


def ensure_baseline(db: Session) -> None:
    if db.query(ModelEvaluation).count() == 0:
        db.add(ModelEvaluation(
            label="Target metrics (not yet measured)",
            model_name="crowdlens-baseline",
            is_measured=False,
            metrics={},
            targets=TARGETS,
            notes="These are engineering targets from the specification. No benchmark "
                  "run has been executed. Upload a measured evaluation to populate results.",
        ))
        db.commit()


def list_all(db: Session) -> list[ModelEvaluation]:
    return db.query(ModelEvaluation).order_by(ModelEvaluation.created_at.desc()).all()


def create(db: Session, payload: dict) -> ModelEvaluation:
    ev = ModelEvaluation(
        label=payload.get("label", "Uploaded evaluation run"),
        model_name=payload.get("model_name", ""),
        is_measured=True,
        metrics=payload.get("metrics", {}),
        targets=payload.get("targets", TARGETS),
        confusion_matrix=payload.get("confusion_matrix"),
        per_event=payload.get("per_event"),
        failure_cases=payload.get("failure_cases"),
        latency_distribution=payload.get("latency_distribution"),
        notes=payload.get("notes"),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev
