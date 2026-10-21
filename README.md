# CROWDLENS

**AI-powered crowd safety monitoring.**
Uploaded crowd video → detect people (YOLO) → count → crowd density → risk score → risk level → alert when risk is high.

> **Privacy by design:** no facial recognition, no names, no personal data. Only anonymous, zone-level crowd analytics. Any tracking IDs are temporary.

---

## What this is

A **dark control-room dashboard** (React) backed by a **FastAPI** service that runs
real computer vision (OpenCV + Ultralytics YOLO) on uploaded videos. Nothing on the
dashboard is faked — if no video has been analysed, the dashboard says so.

### Pages
| Page | What it does |
|---|---|
| **Dashboard** (home) | Control-room overview: total people / density / risk score / active alerts, a "Live Crowd Monitoring" grid of every uploaded video (camera card), a Crowd Risk Overview timeline, Active Alerts, and Top Risk Zones. Every number comes from the real analysis session or the video library — sections show *"No active analysis"* / *"No risk data available"* instead of faking data. |
| **Crowd Videos** | YouTube-style *browsing* (not branding) of every uploaded crowd video: search + category filters (Stadium / Temple Festival / Concert / Procession / Protest / Public Gathering), multi-file upload, responsive card grid with real thumbnail + duration + last-known risk. Click a card → video detail/analysis page. |
| **Live Analysis** | Upload a video → **Start Analysis** → YOLO runs frame by frame; shows the video with detection boxes drawn, live people count / density / risk, and per-zone counts. (The video detail page under Crowd Videos reuses this same analysis session — only one can run at a time.) |
| **Crowd Analytics** | Time-series charts: people count, density, movement (optical flow), risk score. |
| **Alerts** | Auto-generated when a zone hits **RED / BLACK**. Filter by severity, **Acknowledge** (persisted to SQLite → alert history). |
| **Settings** | Detection confidence, frame step, zone area, critical density, risk thresholds. Privacy Mode is always on. |

---

## Project structure

```
CROWDLENS/
├── backend/
│   ├── main.py            FastAPI app — all endpoints + WebSocket
│   ├── analysis.py        in-memory analysis session (background thread, zones, alerting)
│   ├── store.py           SQLite (stdlib sqlite3) — alert history + video library
│   ├── cv/
│   │   ├── detector.py    YOLO (ultralytics) with OpenCV HOG+SVM fallback
│   │   ├── density.py     people/m² + density risk
│   │   ├── movement.py    dense optical flow → movement + turbulence
│   │   ├── risk.py        0–100 crowd risk score + GREEN/YELLOW/ORANGE/RED/BLACK
│   │   └── pipeline.py    decode → detect → count → density → movement → risk → annotated frame
│   ├── uploads/           uploaded videos (gitignored)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── lib/           api.ts (typed client), types.ts
│   │   ├── store.tsx      app state: WebSocket + polling, metrics/alerts/health
│   │   ├── components/    Layout (sidebar + top bar), ui.tsx (gauge, cards, badges), charts.tsx (risk timeline)
│   │   ├── pages/         Dashboard, CrowdVideos, VideoDetail, LiveAnalysis, CrowdAnalytics, Alerts, Settings
│   │   └── App.tsx
│   └── package.json
├── data/vtest.avi         sample video (OpenCV pedestrian clip)
└── README.md
```

`backend/app/` and `ml_service/` are an earlier, larger architecture kept in the
repo but **not used** by this simple version. Run `backend/main.py`.

---

## Run it

**Prerequisites:** Python 3.11+, Node 20+. Two virtualenvs already exist
(`backend/venv`, plus `ml_service/venv` which this version doesn't need).

### Backend (terminal 1)
```powershell
cd C:\Users\ruba2\Downloads\CROWDLENS\CROWDLENS\backend
venv\Scripts\python -m uvicorn main:app --port 8000
```
First analysis downloads `yolov8n.pt` (~6 MB) automatically.

### Frontend (terminal 2)
```powershell
cd C:\Users\ruba2\Downloads\CROWDLENS\CROWDLENS\frontend
npm run dev
```
Open the URL it prints (http://localhost:5173 unless the port is taken).
If old Vite servers are holding ports, close them first:
`Get-Process node | Stop-Process -Force`

### Demo flow
1. **Live Analysis** → Choose video → **Upload** → **Start Analysis**
2. Detection boxes appear on the video; people count / density / risk update live
3. **Crowd Analytics** → charts fill in
4. If risk reaches RED/BLACK → **Alerts** shows a new alert → **Acknowledge**
5. Acknowledged alert stays in the history (survives restart)

Use a **busy** crowd clip (train station, stadium exit, festival) to push the risk
score into ORANGE/RED. The bundled `data/vtest.avi` only has ~10 people so it
stays GREEN — which is the correct, non-faked result.

---

## Dependencies

**Backend** (`backend/requirements.txt`): fastapi, uvicorn, python-multipart,
websockets, numpy, **opencv-python-headless 4.10**, **ultralytics** (YOLO; pulls
torch/torchvision). Do **not** install `opencv-python` (non-headless) — it
conflicts and its v5 wheel removes `cv2.HOGDescriptor`.

**Frontend** (`frontend/package.json`): react 19, react-router-dom 7, recharts 3,
tailwindcss 4, lucide-react, vite 8, typescript.

---

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health` | detector backend, privacy mode, status |
| POST | `/api/video/upload` | multipart `file` (+ optional `category`) → video record incl. `video_id`, real probed duration + thumbnail |
| GET | `/api/videos` | crowd video library (Crowd Videos page + dashboard camera cards) |
| GET | `/api/videos/categories` | the fixed category list used by the upload/filter UI |
| GET | `/api/videos/{id}` | one video's record |
| DELETE | `/api/videos/{id}` | remove an uploaded video (blocked while it's being analyzed) |
| GET | `/uploads/{id}` | static file — plays the uploaded video back (video detail page) |
| POST | `/api/analysis/start` | `{ video_id }` |
| POST | `/api/analysis/stop` | |
| GET | `/api/analysis/status` | |
| GET | `/api/metrics` | latest frame + history + zones |
| GET | `/api/zones` | per-zone people / density / risk |
| GET | `/api/alerts?level=` | alert history (`ALL/YELLOW/ORANGE/RED/BLACK`) |
| POST | `/api/alerts/{id}/acknowledge` | |
| GET / PUT | `/api/settings` | |
| WS | `/ws` | `metrics` / `status` / `alert` events |

---

## What actually works

- ✅ Real YOLO person detection on uploaded MP4/AVI/MOV/MKV/WEBM
- ✅ People count, density (people/m²), optical-flow movement + turbulence
- ✅ 0–100 risk score (density 40% · movement 25% · build-up 20% · compression 15%) with 5 bands
- ✅ Detection boxes drawn on frames, streamed to the UI (annotated JPEG)
- ✅ 4 vertical zones with per-zone counts / density / risk; high-risk zones highlighted
- ✅ Auto alerts on RED/BLACK, acknowledge → persisted SQLite history, severity filter
- ✅ Live updates via WebSocket (+ polling fallback)
- ✅ HOG+SVM fallback if `ultralytics` isn't installed; clear "detector unavailable" state
- ✅ Dashboard shows "No video selected" instead of fake numbers
- ✅ `pytest tests/ -q` — 14 passing (risk/alert/scenario engines of the legacy module)

## Limitations

- **Zones are vertical image bands**, not calibrated ground regions — a simple first-version approximation.
- **Density** depends on the configured *estimated zone area* (Settings) — it is an estimate, not metric ground truth (no camera calibration).
- **No live RTSP/CCTV** — uploaded files only.
- Analysis runs as fast as the CPU allows (roughly a few frames/sec with YOLOv8n on CPU); it is not real-time playback-locked.
- One analysis session at a time — the Dashboard's "Live Crowd Monitoring" and the Crowd Videos grid can hold many uploaded videos, but only one is *actually* being analyzed simultaneously. Every other card shows its real last-known numbers (or "Not analyzed" if it never ran) rather than a fake live feed.
- Alerts aren't tagged per-video yet, so the video detail page's Alerts panel shows the same global alert list as the Alerts page, not alerts scoped to that one file.
- The sidebar doesn't include "Predictive Risk" or "Incidents" — those would need real prediction/incident-tracking logic that doesn't exist yet, and the project's own rule is to never wire up a page that can't show real data.
- **Movement / compression** are frame-to-frame optical-flow proxies, not per-person trajectory tracking.
- Risk-threshold values in Settings are stored but the band cut-offs are fixed in this version.
