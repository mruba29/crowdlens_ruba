# CROWDLENS — Full Rebuild to Spec

Tracking doc for the rebuild. Checked items are done and verified.

## Architecture

```
ml_service/     FastAPI :8001  — YOLO person detection + ByteTrack + OpenCV + optical flow + feature extraction
backend/        FastAPI :8000  — REST + WebSocket + DB + risk/alert/incident/evaluation business logic (NO ML here)
frontend/       Vite :5173     — React + TS + Tailwind (DARK command-center) + Recharts + zustand
```

- **DB**: SQLAlchemy 2.0, `DATABASE_URL` env. Default `sqlite:///./crowdlens.db` for zero-config dev; PostgreSQL-compatible (`postgresql+psycopg://...`). JSON columns, string UUID PKs.
- **ML availability**: `ml_service` degrades gracefully if `ultralytics` is not installed. Backend surfaces `ml_service: online | degraded | offline`. Frontend shows an explicit **"ML Service Offline"** state — never fake inference.
- **Controlled Evaluation Replay**: deterministic, clearly labelled, needs no ML — the reliable demo path.
- **Shared state**: zustand stores so video analysis → metrics → SRI → prediction → alerts → incidents → dashboard all update together.

## Phases

### Phase 1 — Backend foundation  ✅
- [x] `opencv-python-headless` 5 → 4.10 fix (HOGDescriptor); 14/14 tests pass
- [x] `backend/app/core/config.py` — settings / env, DATABASE_URL
- [x] `backend/app/core/database.py` — Postgres-compatible engine
- [x] `backend/app/models/db_models.py` — full 13-table spec schema (verified: creates cleanly)
- [x] `backend/app/schemas/__init__.py` — typed pydantic responses
- [ ] seed data → Event "Stadium Exit Surge"  (moved to Phase 3)

### Phase 2 — ML service  ✅ (verified: /health + SSE /analyze on vtest.avi)
- [x] `ml_service/app/detector.py` — YOLO (ultralytics) → HOG+SVM fallback → graceful degrade
- [x] `ml_service/app/tracker.py` — BYTE-style two-stage association, ephemeral IDs
- [x] `ml_service/app/features.py` — all 15 spec crowd features + optical flow + dynamics classifier
- [x] `ml_service/app/normalize.py` — raw features → 7 SRI components
- [x] `ml_service/app/pipeline.py` + `main.py` — `/health`, `/analyze`, `/analyze/path` (SSE)
- [x] `ml_service/requirements.txt` (aligned to backend venv versions; py3.14 wheels)
- current runtime state: **degraded** (HOG fallback) until `pip install ultralytics`

### Phase 3 — Backend services + API  ✅ (verified: backend boots, replay E2E, 14/14 tests)
- [x] `realtime/hub.py` — unified `/ws/live` channel + thread-safe publish
- [x] `core/prediction.py` — linear-trend forecast + time-to-critical + confidence
- [x] `services/ml_client.py` — httpx client to ML service, SSE parsing, offline signal
- [x] `services/risk_service.py` — SRI + prediction + structural on the pure engines
- [x] `services/alert_service.py` — raise on band-entry + lifecycle + audit
- [x] `services/analysis_service.py` — live_cv (ml_client SSE) + controlled_replay, persist + publish (401 rows in E2E test)
- [x] `services/incident_service.py`, `evaluation_service.py`, `health_service.py`
- [x] `seed.py` — Stadium Exit Surge event + 3 zones + 4 cameras + evaluation baseline
- [x] routers: `config_routes` (events/cameras/zones), `analysis_routes` (upload/start/pause/stop/metrics/risk/prediction/structural), `ops_routes` (alerts/incidents/evaluations/system-health/scenario)
- [x] `main.py` rewritten; old `routers/api.py` + `services/scenario_runner.py` removed
- [x] keep SRI / scenario / alert-rule / structural engines — 14/14 tests still pass

### Phase 4 — Frontend shell
- [ ] dark theme tokens, `index.css`
- [ ] API service layer (typed, per resource) + `ws.ts`
- [ ] zustand stores
- [ ] Sidebar (13 items), TopBar (event, cameras, ML status, WS status, latency, clock)
- [ ] state components: EmptyState, ErrorState, LoadingState, OfflineState

### Phase 5 — Reusable components
- [ ] CrowdVideoPlayer, DetectionOverlay, TrackingOverlay, ZoneOverlay
- [ ] RiskGauge, DensityHeatmap, SRIChart, PredictionChart
- [ ] MetricCard, RiskBadge, AlertCard, AlertTimeline, IncidentTimeline
- [ ] StructuralGauge, SystemStatus, CameraCard, EventSelector, ZoneSelector
- [ ] PrivacyBadge, EvaluationMetric

### Phase 6 — Pages (13)
- [ ] Overview, Live Analysis, Crowd Analytics, Predictive Risk, Structural Safety
- [ ] Alerts, Incidents, Historical Replay, Event Configuration
- [ ] Model Evaluation, Privacy & Ethics, System Health, Settings

### Phase 7 — Integration + demo flow
- [ ] wire the 21-step presentation flow end to end
- [ ] docker-compose (3 services + postgres)
- [ ] README + run scripts
