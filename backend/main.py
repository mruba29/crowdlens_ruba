"""CROWDLENS backend — FastAPI.

CCTV / uploaded crowd video -> detect people -> count -> density -> movement
-> risk score -> risk level -> alert when risk is high.

Computer vision runs in-process (backend/cv/). No separate ML service to start.

Privacy: no facial recognition, no identity, no personal data. Only anonymous,
zone-level crowd analytics.
"""
from __future__ import annotations
import asyncio
import json
import os
import shutil
import time
import uuid

import cv2
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import store
import analysis
from cv.detector import get_detector

UPLOAD_DIR = os.environ.get(
    "CROWDLENS_UPLOADS",
    "/tmp/crowdlens_uploads" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="CROWDLENS", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded videos directly so the frontend video player (Crowd Videos /
# video detail page) can play them back — same files the CV pipeline reads.
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/api/uploads", StaticFiles(directory=UPLOAD_DIR), name="api_uploads")

VIDEO_CATEGORIES = (
    "Temple / Festival",
    "Stadium / Sports",
    "Concert / Music Festival",
    "Public Gathering",
    "Transport Hub / Railway / Metro",
    "Procession",
    "Protest / Rally",
    "Other",
)

def _norm_category(cat: str | None) -> str:
    if not cat:
        return "Other"
    c = cat.strip()
    c_lower = c.lower()
    if "temple" in c_lower or "fest" in c_lower:
        return "Temple / Festival"
    if "stadium" in c_lower or "sport" in c_lower:
        return "Stadium / Sports"
    if "concert" in c_lower or "music" in c_lower:
        return "Concert / Music Festival"
    if "metro" in c_lower or "rail" in c_lower or "transport" in c_lower or "station" in c_lower:
        return "Transport Hub / Railway / Metro"
    if "procession" in c_lower or "parade" in c_lower or "yatra" in c_lower:
        return "Procession"
    if "protest" in c_lower or "rally" in c_lower or "demonstration" in c_lower:
        return "Protest / Rally"
    if "public" in c_lower or "gathering" in c_lower or "plaza" in c_lower:
        return "Public Gathering"
    for vc in VIDEO_CATEGORIES:
        if vc.lower() == c_lower:
            return vc
    return "Other"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

SAMPLE_VIDEOS = [
    {
        "id": "sample-temple-thaipusam",
        "title": "Thaipusam Festival Chariot Procession",
        "category": "Temple / Festival",
        "source_name": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Thaipusam_Festival_Singapore.webm",
        "direct_download_url": "https://upload.wikimedia.org/wikipedia/commons/3/30/Thaipusam_Festival_Singapore.webm",
        "local_filename": "Thaipusam_Festival_Singapore.webm",
        "duration_sec": 142.0,
        "resolution": "1280x720",
        "license": "CC BY-SA 3.0",
        "is_synthetic": False,
        "scenario_type": "High Density",
        "expected_indicators": "Dense religious gathering, constrained forward street column, lateral crowd compression.",
        "description": "Real footage from the annual Thaipusam chariot festival procession. Features dense pilgrim movement, ceremonial chariots, and narrow street chokepoints.",
    },
    {
        "id": "sample-stadium-surge",
        "title": "Stadium Grandstand Crowd Wave & Cheer",
        "category": "Stadium / Sports",
        "source_name": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Krazy_George_leads_the_crowd_in_a_cheer_01.webm",
        "direct_download_url": "https://upload.wikimedia.org/wikipedia/commons/6/6e/Krazy_George_leads_the_crowd_in_a_cheer_01.webm",
        "local_filename": "Krazy_George_leads_the_crowd_in_a_cheer_01.webm",
        "duration_sec": 45.0,
        "resolution": "1920x1080",
        "license": "CC BY 3.0",
        "is_synthetic": False,
        "scenario_type": "Turbulent Motion",
        "expected_indicators": "Rapid synchronized wave motion, high velocity variance, sudden tier-to-tier acceleration.",
        "description": "Seated sports stadium crowd performing an interactive Mexican wave and standing surge. Tests motion entropy, turbulence detection, and tiered seating dynamics.",
    },
    {
        "id": "sample-concert-cincy",
        "title": "Open-Air Music Concert & Plaza Surge",
        "category": "Concert / Music Festival",
        "source_name": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:MLS2Cincy_announcement_-_crowd_panning_shot.webm",
        "direct_download_url": "https://upload.wikimedia.org/wikipedia/commons/8/87/MLS2Cincy_announcement_-_crowd_panning_shot.webm",
        "local_filename": "MLS2Cincy_announcement_-_crowd_panning_shot.webm",
        "duration_sec": 38.0,
        "resolution": "1920x1080",
        "license": "CC BY 3.0",
        "is_synthetic": False,
        "scenario_type": "Bottleneck / Accumulation",
        "expected_indicators": "Perimeter boundary pressure, stage-facing accumulation, localized cluster density.",
        "description": "Panned aerial and ground view of open-air music festival crowd accumulating near front barrier. Evaluates edge pressure proxy, cluster density, and spatial concentration.",
    },
    {
        "id": "sample-public-vtest",
        "title": "Urban Pedestrian Plaza Crossing Benchmark",
        "category": "Public Gathering",
        "source_name": "OpenCV Pedestrian Benchmark / UCF CRCV",
        "source_url": "https://github.com/opencv/opencv/blob/master/samples/data/vtest.avi",
        "direct_download_url": "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/vtest.avi",
        "local_filename": "vtest.avi",
        "duration_sec": 26.5,
        "resolution": "768x576",
        "license": "BSD 3-Clause",
        "is_synthetic": False,
        "scenario_type": "Normal Crowd",
        "expected_indicators": "Safe low density (<1.5 p/m²), continuous laminar flow, low turbulence.",
        "description": "Standard computer vision pedestrian benchmark. Pedestrians crossing a bright paved courtyard in daylight. Serves as ground truth for normal safe baseline conditions.",
    },
    {
        "id": "sample-transport-ppsd",
        "title": "Metro Concourse & Platform Transit Influx",
        "category": "Transport Hub / Railway / Metro",
        "source_name": "Zenodo PPS-D Public Safety Research",
        "source_url": "https://zenodo.org/records/15124010",
        "direct_download_url": None,
        "local_filename": None,
        "duration_sec": 30.0,
        "resolution": "1920x1080",
        "license": "CC BY 4.0",
        "is_synthetic": True,
        "scenario_type": "Bottleneck / Accumulation",
        "expected_indicators": "Gate accumulation, platform edge proximity, cyclic arrival/departure waves.",
        "description": "From Zenodo PPS-D (Person-oriented Protection of Public Spaces Dataset). Synthetic benchmark modeling railway station concourse, passenger boarding, and platform edge queues.",
    },
    {
        "id": "sample-procession-lerwick",
        "title": "Festival Street Parade & Linear March Column",
        "category": "Procession",
        "source_name": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Lerwick_Up_Helly_Aa_Morning_Procession_2020.webm",
        "direct_download_url": "https://upload.wikimedia.org/wikipedia/commons/4/48/Lerwick_Up_Helly_Aa_Morning_Procession_2020.webm",
        "local_filename": "Lerwick_Up_Helly_Aa_Morning_Procession_2020.webm",
        "duration_sec": 63.0,
        "resolution": "1920x1080",
        "license": "CC BY-SA 4.0",
        "is_synthetic": False,
        "scenario_type": "Possible Compression",
        "expected_indicators": "High pack density, narrow lateral corridors, persistent forward momentum.",
        "description": "Annual morning parade through historic narrow streets. Features tightly packed linear columns flanked by spectator barriers, ideal for corridor compression assessment.",
    },
    {
        "id": "sample-protest-demonstration",
        "title": "Civic Street Demonstration & Protest March",
        "category": "Protest / Rally",
        "source_name": "Wikimedia Commons / UCF Demonstration Archive",
        "source_url": "https://commons.wikimedia.org/wiki/Category:Videos_of_demonstrations_and_protests",
        "direct_download_url": None,
        "local_filename": None,
        "duration_sec": 50.0,
        "resolution": "1280x720",
        "license": "CC BY-SA 4.0",
        "is_synthetic": False,
        "scenario_type": "Reverse Flow",
        "expected_indicators": "Conflicting flow vectors, stopping front waves, intersection congestion.",
        "description": "Civic demonstration march along metropolitan avenue. Highlights banner-led lead waves, counter-flowing pedestrian streams at road intersections, and crowd halts.",
    },
    {
        "id": "sample-walkindia-street",
        "title": "WalkIndia Urban Market Pedestrian Density",
        "category": "Public Gathering",
        "source_name": "HuggingFace WalkIndia-50 Dataset",
        "source_url": "https://huggingface.co/datasets/anonymousML123/walkindia-50-clips",
        "direct_download_url": None,
        "local_filename": None,
        "duration_sec": 35.0,
        "resolution": "1920x1080",
        "license": "Open Academic Research",
        "is_synthetic": False,
        "scenario_type": "High Density",
        "expected_indicators": "Irregular walking speeds, multi-agent obstacle avoidance, fluctuating local density.",
        "description": "From the WalkIndia-50 crowd research collection. Real walking tour footage through bustling non-Western urban markets, retail corridors, and pedestrian thoroughfares.",
    },
]

def _seed_samples() -> None:
    """Best-effort initial seed: register any local bundled sample files that are already
    on disk so the video library is ready out of the box."""
    try:
        existing = {v["filename"] for v in store.list_videos()}
        # 1. Check data/vtest.avi
        vtest_src = os.path.join(DATA_DIR, "vtest.avi")
        if os.path.exists(vtest_src) and "vtest.avi" not in existing:
            vtest_dest = os.path.join(UPLOAD_DIR, "vtest.avi")
            if not os.path.exists(vtest_dest):
                shutil.copy2(vtest_src, vtest_dest)
            duration, thumb, res = _probe_video(vtest_dest)
            store.add_video("vtest.avi", "vtest.avi", "Public Gathering", os.path.getsize(vtest_dest), duration, thumb)

        # 2. Check any existing uploads that correspond to our sample videos
        for sample in SAMPLE_VIDEOS:
            fname = sample.get("local_filename")
            if not fname:
                continue
            # Search if file exists in UPLOAD_DIR
            target_path = os.path.join(UPLOAD_DIR, fname)
            matched_vid = None
            if os.path.exists(target_path):
                matched_vid = fname
            else:
                # Search by exact filename match in upload dir files
                for f in os.listdir(UPLOAD_DIR):
                    if f == fname or f.endswith(f"_{fname}"):
                        matched_vid = f
                        break
            if matched_vid and fname not in existing:
                p = os.path.join(UPLOAD_DIR, matched_vid)
                dur, thumb, res = _probe_video(p)
                store.add_video(matched_vid, fname, sample["category"], os.path.getsize(p), dur, thumb)
    except Exception:
        pass


# ---- runtime settings (in-memory, editable via /api/settings) ----
SETTINGS: dict = {
    "privacy_mode": True,                 # always on; exposed read-only intent
    "detection_confidence": 0.35,
    "analysis_sample_every_n": 3,         # process every Nth frame
    "zone_area_m2": 100.0,                # estimated visible ground area
    "critical_density_ppm2": 5.0,
    "risk_thresholds": {"YELLOW": 31, "ORANGE": 56, "RED": 76, "BLACK": 91},
}

# ---- websocket hub ----
_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None


def publish(kind: str, payload) -> None:
    msg = json.dumps({"type": kind, "ts": time.time(), "data": payload}, default=str)
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(msg), _loop)


async def _broadcast(msg: str) -> None:
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()
    store.init()
    _seed_samples()


# ---------------------------------------------------------------- health
@app.get("/api/health")
@app.get("/health")
def health():
    det = get_detector()
    return {
        "status": "ok",
        "service": "crowdlens-backend",
        "detector": {
            "backend": det.backend,
            "available": det.available,
            "is_yolo": det.is_yolo,
        },
        "privacy_mode": SETTINGS["privacy_mode"],
        "analysis_status": analysis.state.status,
        "websocket_clients": len(_clients),
    }


# ---------------------------------------------------------------- sample videos library
@app.get("/api/samples")
def list_samples():
    """List curated crowd-safety test videos across all 7 official categories,
    enriched with import status against the active library."""
    all_videos = store.list_videos()
    video_by_name = {v["filename"].lower(): v for v in all_videos}
    video_by_id = {v["id"].lower(): v for v in all_videos}

    enriched = []
    for s in SAMPLE_VIDEOS:
        item = dict(s)
        matched = None
        if s.get("local_filename"):
            fname = s["local_filename"].lower()
            matched = video_by_name.get(fname) or video_by_id.get(fname)
        if not matched:
            # check title or sample id
            for v in all_videos:
                if s["id"] in v["id"] or s["title"].lower() in v["filename"].lower():
                    matched = v
                    break

        item["is_imported"] = matched is not None
        item["video_id"] = matched["id"] if matched else None
        item["status"] = matched["status"] if matched else None
        enriched.append(item)
    return enriched


@app.post("/api/samples/import")
async def import_sample(payload: dict):
    sample_id = payload.get("sample_id")
    if not sample_id:
        raise HTTPException(400, "sample_id is required")

    sample = next((s for s in SAMPLE_VIDEOS if s["id"] == sample_id), None)
    if not sample:
        raise HTTPException(404, f"sample {sample_id} not found")

    # 1. Check if already imported
    all_videos = store.list_videos()
    fname = sample.get("local_filename")
    for v in all_videos:
        if (fname and v["filename"] == fname) or (s_id := sample["id"]) in v["id"]:
            return {"ok": True, "video": v, "message": "Video is already in your library."}

    # 2. Check local bundled file
    if fname:
        # Check UPLOAD_DIR
        cand1 = os.path.join(UPLOAD_DIR, fname)
        cand2 = os.path.join(DATA_DIR, fname)
        found_path = cand1 if os.path.exists(cand1) else (cand2 if os.path.exists(cand2) else None)
        if not found_path:
            # Search partial match in UPLOAD_DIR
            for f in os.listdir(UPLOAD_DIR):
                if f.endswith(f"_{fname}") or f == fname:
                    found_path = os.path.join(UPLOAD_DIR, f)
                    break

        if found_path:
            target_vid = fname
            target_dest = os.path.join(UPLOAD_DIR, target_vid)
            if found_path != target_dest and not os.path.exists(target_dest):
                shutil.copy2(found_path, target_dest)
            size = os.path.getsize(target_dest)
            duration, thumb, res = _probe_video(target_dest)
            rec = store.add_video(target_vid, fname, sample["category"], size, duration, thumb)
            return {"ok": True, "video": rec, "message": "Imported sample from bundled assets."}

    # 3. Direct download if supported
    direct_url = sample.get("direct_download_url")
    if direct_url and direct_url.startswith("http"):
        import httpx
        ext = os.path.splitext(direct_url)[1].lower() or ".mp4"
        new_vid = f"sample_{sample_id}_{uuid.uuid4().hex[:8]}{ext}"
        dest_path = os.path.join(UPLOAD_DIR, new_vid)
        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                async with client.stream("GET", direct_url) as resp:
                    if resp.status_code != 200:
                        raise HTTPException(400, f"failed to download sample: status {resp.status_code}")
                    total = 0
                    with open(dest_path, "wb") as out:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            total += len(chunk)
                            if total > 150 * 1024 * 1024:
                                os.remove(dest_path)
                                raise HTTPException(400, "sample video exceeds 150MB limit")
                            out.write(chunk)
            size = os.path.getsize(dest_path)
            duration, thumb, res = _probe_video(dest_path)
            rec = store.add_video(new_vid, sample["title"] + ext, sample["category"], size, duration, thumb)
            return {"ok": True, "video": rec, "message": "Sample downloaded and imported successfully."}
        except HTTPException:
            raise
        except Exception as e:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            raise HTTPException(500, f"download failed: {str(e)}")

    raise HTTPException(
        400,
        f"Sample '{sample['title']}' requires manual download due to source licensing ({sample['source_name']}). "
        f"Please click 'Open Source Page', download the file, and upload it using 'Upload Videos'."
    )


# ---------------------------------------------------------------- video upload
@app.post("/api/video/upload")
async def upload_video(file: UploadFile = File(...), category: str = Form("Other")):
    ext = os.path.splitext(file.filename or "video.mp4")[1].lower()
    if ext not in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
        raise HTTPException(400, f"unsupported file type: {ext}. Supported: MP4, MOV, WebM, AVI, MKV")
    video_id = uuid.uuid4().hex + ext
    dest = os.path.join(UPLOAD_DIR, video_id)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size = os.path.getsize(dest)

    duration_sec, thumbnail, resolution = _probe_video(dest)
    norm_cat = _norm_category(category)
    rec = store.add_video(video_id, file.filename or video_id, norm_cat, size, duration_sec, thumbnail)
    # keep "video_id" for the pre-existing Live Analysis page; new pages use "id"
    return {**rec, "video_id": video_id}


@app.post("/api/videos/batch-upload")
async def batch_upload_videos(files: list[UploadFile] = File(...), category: str = Form("Other")):
    results = []
    errors = []
    norm_cat = _norm_category(category)
    for file in files:
        ext = os.path.splitext(file.filename or "video.mp4")[1].lower()
        if ext not in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            errors.append(f"{file.filename}: unsupported file type {ext}")
            continue
        try:
            video_id = uuid.uuid4().hex + ext
            dest = os.path.join(UPLOAD_DIR, video_id)
            with open(dest, "wb") as f:
                shutil.copyfileobj(file.file, f)
            size = os.path.getsize(dest)
            duration_sec, thumbnail, resolution = _probe_video(dest)
            rec = store.add_video(video_id, file.filename or video_id, norm_cat, size, duration_sec, thumbnail)
            results.append({**rec, "video_id": video_id})
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
    return {"uploaded": results, "errors": errors, "count": len(results)}


def _probe_video(path: str) -> tuple[float | None, str | None, str | None]:
    """Best-effort: real duration + resolution + a real first-frame thumbnail (never fabricated)."""
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return None, None, None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        duration = round(frame_count / fps, 1) if fps > 0 and frame_count > 0 else None
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        resolution = f"{w}x{h}" if w > 0 and h > 0 else None
        ok, frame = cap.read()
        thumbnail = None
        if ok:
            fh, fw = frame.shape[:2]
            tw = 480
            if fw > tw:
                frame = cv2.resize(frame, (tw, max(1, int(fh * tw / fw))))
            ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok2:
                import base64
                thumbnail = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
        return duration, thumbnail, resolution
    except Exception:  # noqa: BLE001
        return None, None, None
    finally:
        cap.release()


# ---------------------------------------------------------------- video library
def _sync_current_video() -> None:
    """Write the live analysis session's real, latest numbers onto its video
    row, so /api/videos reflects reality without a second CV implementation."""
    st = analysis.state.status_dict()
    vid = st["video_id"]
    if not vid:
        return
    latest = analysis.state.metrics_dict()["latest"]
    store.update_video_metrics(
        vid, status=st["status"],
        people=latest["people_count"] if latest else None,
        density=latest["density_ppm2"] if latest else None,
        score=latest["score"] if latest else None,
        level=latest["level"] if latest else None,
    )


@app.get("/api/videos")
def list_videos():
    _sync_current_video()
    return store.list_videos()


@app.get("/api/videos/categories")
def video_categories():
    return list(VIDEO_CATEGORIES)


@app.get("/api/videos/{video_id}")
def get_video(video_id: str):
    _sync_current_video()
    v = store.get_video(video_id)
    if not v:
        raise HTTPException(404, "video not found")
    return v


@app.patch("/api/videos/{video_id}")
def rename_video(video_id: str, payload: dict):
    v = store.get_video(video_id)
    if not v:
        raise HTTPException(404, "video not found")
    filename = payload.get("filename")
    category = payload.get("category")
    if filename is not None and not filename.strip():
        raise HTTPException(400, "filename cannot be empty")
    if category is not None and category not in VIDEO_CATEGORIES:
        raise HTTPException(400, f"category must be one of {VIDEO_CATEGORIES}")
    return store.update_video(video_id, filename=filename, category=category)


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str):
    v = store.get_video(video_id)
    if not v:
        raise HTTPException(404, "video not found")
    if analysis.state.video_id == video_id and analysis.state.status == "processing":
        raise HTTPException(409, "stop analysis on this video before deleting it")
    path = os.path.join(UPLOAD_DIR, os.path.basename(video_id))
    if os.path.exists(path):
        os.remove(path)
    store.delete_video(video_id)
    return {"ok": True}


# ---------------------------------------------------------------- events (Phase 1: foundation layer)
# Multi-source video management. A video keeps working exactly as before
# (upload / analyze / list) until it is attached to an Event, at which point
# it also carries camera/zone/timestamp context and shows up in the event's
# timeline and multi-camera views. Nothing below touches the endpoints above.
SOURCE_TYPES = ("CCTV", "Drone", "Uploaded Video")
ZONE_ROLES = ("entrance", "exit", "bottleneck", "restricted", "general")
# Phase 3: operator-declared spatial crowd context — a zone property, not a
# per-frame guess (see cv/dynamics.py's module docstring).
SPATIAL_CONTEXTS = ("open", "constrained", "unidirectional", "multidirectional", "converging", "dispersing")


DEMO_PCT_FIELDS = ("demo_children_pct", "demo_adults_pct", "demo_elderly_pct",
                   "demo_gender_male_pct", "demo_gender_female_pct")


def _validate_demo_pcts(payload: dict) -> None:
    for k in DEMO_PCT_FIELDS:
        if k in payload and payload[k] is not None:
            v = payload[k]
            if not isinstance(v, (int, float)) or not (0 <= v <= 100):
                raise HTTPException(400, f"{k} must be a number between 0 and 100")


@app.post("/api/events")
def create_event(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    _validate_demo_pcts(payload)
    ev = store.create_event(
        name=name,
        event_type=payload.get("event_type") or "Public Gathering",
        location=payload.get("location") or "",
        start_time=payload.get("start_time"),
        end_time=payload.get("end_time"),
        crowd_context=payload.get("crowd_context") or "",
    )
    demo_fields = {k: payload[k] for k in DEMO_PCT_FIELDS if k in payload}
    return store.update_event(ev["id"], **demo_fields) if demo_fields else ev


@app.get("/api/events")
def list_events():
    return store.list_events()


@app.get("/api/events/{event_id}")
def get_event(event_id: str):
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(404, "event not found")
    ev = dict(ev)
    ev["zones"] = store.list_zones(event_id)
    ev["cameras"] = store.list_cameras(event_id)
    ev["video_sources"] = store.list_event_videos(event_id)
    return ev


@app.patch("/api/events/{event_id}")
def update_event(event_id: str, payload: dict):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    _validate_demo_pcts(payload)
    allowed = {"name", "event_type", "location", "start_time", "end_time", "crowd_context", *DEMO_PCT_FIELDS}
    fields = {k: v for k, v in payload.items() if k in allowed}
    return store.update_event(event_id, **fields)


@app.delete("/api/events/{event_id}")
def delete_event(event_id: str):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    store.delete_event(event_id)
    return {"ok": True}


# ---- zones ----
@app.post("/api/events/{event_id}/zones")
def create_zone(event_id: str, payload: dict):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    role = payload.get("role", "general")
    if role not in ZONE_ROLES:
        raise HTTPException(400, f"role must be one of {ZONE_ROLES}")
    spatial_context = payload.get("spatial_context", "open")
    if spatial_context not in SPATIAL_CONTEXTS:
        raise HTTPException(400, f"spatial_context must be one of {SPATIAL_CONTEXTS}")
    return store.create_zone(event_id, name, role,
                              float(payload.get("x", 0.1)), float(payload.get("y", 0.1)),
                              float(payload.get("w", 0.2)), float(payload.get("h", 0.2)),
                              float(payload.get("area_m2", 100.0)), int(payload.get("capacity", 500)),
                              spatial_context)


@app.patch("/api/zones/{zone_id}")
def patch_zone(zone_id: str, payload: dict):
    allowed = {"name", "role", "x", "y", "w", "h", "area_m2", "capacity", "spatial_context"}
    if "spatial_context" in payload and payload["spatial_context"] not in SPATIAL_CONTEXTS:
        raise HTTPException(400, f"spatial_context must be one of {SPATIAL_CONTEXTS}")
    z = store.update_zone(zone_id, **{k: v for k, v in payload.items() if k in allowed})
    if not z:
        raise HTTPException(404, "zone not found")
    return z


@app.delete("/api/zones/{zone_id}")
def remove_zone(zone_id: str):
    store.delete_zone(zone_id)
    return {"ok": True}


# ---- cameras ----
@app.post("/api/events/{event_id}/cameras")
def create_camera(event_id: str, payload: dict):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    source_type = payload.get("source_type", "Uploaded Video")
    if source_type not in SOURCE_TYPES:
        raise HTTPException(400, f"source_type must be one of {SOURCE_TYPES}")
    return store.create_camera(event_id, name, source_type, payload.get("location_label", ""),
                                float(payload.get("x", 0.5)), float(payload.get("y", 0.5)),
                                float(payload.get("orientation_deg", 0)), payload.get("zone_id"))


@app.patch("/api/cameras/{camera_id}")
def patch_camera(camera_id: str, payload: dict):
    allowed = {"name", "source_type", "location_label", "x", "y", "orientation_deg", "zone_id"}
    if "source_type" in payload and payload["source_type"] not in SOURCE_TYPES:
        raise HTTPException(400, f"source_type must be one of {SOURCE_TYPES}")
    c = store.update_camera(camera_id, **{k: v for k, v in payload.items() if k in allowed})
    if not c:
        raise HTTPException(404, "camera not found")
    return c


@app.delete("/api/cameras/{camera_id}")
def remove_camera(camera_id: str):
    store.delete_camera(camera_id)
    return {"ok": True}


# ---- video sources: attach an already-uploaded video, or upload straight into the event ----
@app.post("/api/events/{event_id}/videos/{video_id}/attach")
def attach_video(event_id: str, video_id: str, payload: dict):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    if not store.get_video(video_id):
        raise HTTPException(404, "video not found")
    source_type = payload.get("source_type", "Uploaded Video")
    if source_type not in SOURCE_TYPES:
        raise HTTPException(400, f"source_type must be one of {SOURCE_TYPES}")
    return store.attach_video(video_id, event_id, camera_id=payload.get("camera_id"),
                               zone_id=payload.get("zone_id"), source_type=source_type,
                               capture_start_ts=payload.get("capture_start_ts"),
                               inflow_direction=payload.get("inflow_direction", "right"))


@app.post("/api/events/{event_id}/upload")
async def upload_event_video(event_id: str, file: UploadFile = File(...),
                              camera_id: str | None = Form(None), zone_id: str | None = Form(None),
                              source_type: str = Form("Uploaded Video"),
                              capture_start_ts: float | None = Form(None),
                              inflow_direction: str = Form("right"),
                              category: str = Form("Uncategorized")):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    if source_type not in SOURCE_TYPES:
        raise HTTPException(400, f"source_type must be one of {SOURCE_TYPES}")
    rec = await upload_video(file, category)  # reuse the existing upload pipeline as-is
    return store.attach_video(rec["video_id"], event_id, camera_id=camera_id, zone_id=zone_id,
                               source_type=source_type, capture_start_ts=capture_start_ts,
                               inflow_direction=inflow_direction)


@app.delete("/api/events/{event_id}/videos/{video_id}")
def detach_video(event_id: str, video_id: str):
    store.detach_video(video_id)
    return {"ok": True}


@app.get("/api/events/{event_id}/videos")
def list_event_videos(event_id: str):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    return store.list_event_videos(event_id)


# ---- global timeline (time frame of reference) ----
@app.get("/api/events/{event_id}/timeline")
def event_timeline(event_id: str, t: float):
    if not store.get_event(event_id):
        raise HTTPException(404, "event not found")
    return store.event_timeline_at(event_id, t)


# ---------------------------------------------------------------- analysis
@app.post("/api/analysis/start")
def analysis_start(payload: dict):
    video_id = payload.get("video_id")
    if not video_id:
        raise HTTPException(400, "video_id is required")
    path = os.path.join(UPLOAD_DIR, os.path.basename(video_id))
    if not os.path.exists(path):
        raise HTTPException(404, "uploaded video not found — upload it first")
    det = get_detector()
    if not det.available:
        raise HTTPException(503, "no person detector available on the server")
    analysis.start(video_id, path, settings=SETTINGS, publish=publish)
    store.update_video_metrics(video_id, status="processing", people=None, density=None, score=None, level=None)
    return analysis.state.status_dict()


@app.post("/api/analysis/batch-start")
def analysis_batch_start(payload: dict):
    video_ids = payload.get("video_ids") or []
    if not video_ids:
        raise HTTPException(400, "video_ids list is required")
    det = get_detector()
    if not det.available:
        raise HTTPException(503, "no person detector available on the server")
    
    specs = []
    for vid in video_ids:
        path = os.path.join(UPLOAD_DIR, os.path.basename(vid))
        if os.path.exists(path):
            specs.append({"video_id": vid, "video_path": path})
        else:
            raise HTTPException(404, f"video file not found for id {vid}")
    
    return analysis.batch_start(specs, settings=SETTINGS, publish=publish)


@app.post("/api/analysis/pause")
def analysis_pause():
    analysis.pause()
    _sync_current_video()
    return analysis.state.status_dict()


@app.post("/api/analysis/resume")
def analysis_resume():
    analysis.resume()
    _sync_current_video()
    return analysis.state.status_dict()


@app.post("/api/analysis/replay")
def analysis_replay(payload: dict):
    video_id = payload.get("video_id")
    if not video_id:
        raise HTTPException(400, "video_id is required")
    path = os.path.join(UPLOAD_DIR, os.path.basename(video_id))
    if not os.path.exists(path):
        raise HTTPException(404, "video not found")
    det = get_detector()
    if not det.available:
        raise HTTPException(503, "no person detector available on the server")
    return analysis.replay(video_id, path, settings=SETTINGS, publish=publish)


@app.post("/api/analysis/cancel/{video_id}")
def analysis_cancel(video_id: str):
    return analysis.cancel_queued(video_id, publish=publish)


@app.get("/api/analysis/queue")
def analysis_queue():
    return [q["video_id"] for q in analysis.state.queue]


@app.post("/api/analysis/stop")
def analysis_stop():
    analysis.stop()
    _sync_current_video()
    return analysis.state.status_dict()


@app.get("/api/analysis/status")
def analysis_status():
    _sync_current_video()
    return analysis.state.status_dict()


@app.get("/api/metrics")
def metrics():
    _sync_current_video()
    return analysis.state.metrics_dict()


# ---------------------------------------------------------------- zone analytics (Phase 2)
@app.get("/api/analysis/zone-metrics")
def zone_metrics():
    """Real, honestly-labeled crowd analytics for whichever video is
    currently being analyzed AND attached to an Event zone. See
    analysis._update_zone_metrics for what each field's real CV source is;
    `available: false` (with a `reason`) whenever a number would otherwise
    have to be guessed."""
    return analysis.state.zone_metrics_dict()


# ---------------------------------------------------------------- crowd dynamics (Phase 3)
@app.get("/api/analysis/dynamics")
def analysis_dynamics():
    """Flow features, compression/edge-pressure proxies, possible-stop-wave
    signal, and the dynamic-state classification — available for any active
    analysis (zone-attached or not). See cv/dynamics.py for the real CV
    source of every field; `available: false` whenever nothing is running."""
    return analysis.state.dynamics_dict()


@app.get("/api/analysis/sri")
def analysis_sri():
    """Demographic estimate, vulnerability proxy, and the transparent 10-input
    SRI risk engine — see cv/sri.py for the real source of every field.
    `available: false` whenever nothing is running."""
    return analysis.state.sri_dict()


@app.get("/api/dynamics/events")
def dynamics_events(video_id: str):
    """State-change history (Crowd State Timeline) — one row per real
    transition, with the contributing signals recorded at that moment."""
    return store.list_dynamics_events(video_id)


# ---------------------------------------------------------------- validation (Phase 2)
# AI-vs-manual reference counts, for measuring real error — never an invented
# accuracy figure. See store.add_validation_sample / validation_summary.
@app.post("/api/validation/samples")
def add_validation_sample(payload: dict):
    video_id = payload.get("video_id")
    if not video_id:
        raise HTTPException(400, "video_id is required")
    if not store.get_video(video_id):
        raise HTTPException(404, "video not found")
    return store.add_validation_sample(
        video_id=video_id, zone_id=payload.get("zone_id"), zone_name=payload.get("zone_name"),
        ai_count=payload.get("ai_count"), manual_count=payload.get("manual_count"),
        ai_density=payload.get("ai_density"), manual_density=payload.get("manual_density"),
        ai_inflow_rate=payload.get("ai_inflow_rate"), manual_inflow_rate=payload.get("manual_inflow_rate"),
        ai_outflow_rate=payload.get("ai_outflow_rate"), manual_outflow_rate=payload.get("manual_outflow_rate"),
        note=payload.get("note", ""),
    )


@app.get("/api/validation/samples")
def list_validation_samples(video_id: str | None = None):
    return store.list_validation_samples(video_id)


@app.get("/api/validation/summary")
def validation_summary(video_id: str | None = None):
    return store.validation_summary(video_id)


@app.get("/api/zones")
def zones():
    return analysis.state.metrics_dict()["zones"]


# ---------------------------------------------------------------- alerts
@app.get("/api/alerts")
def alerts(level: str | None = None):
    return store.list_alerts(level)


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int):
    a = store.acknowledge(alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    publish("alert", a)
    return a


# ---------------------------------------------------------------- incidents
@app.get("/api/incidents")
def list_incidents(status: str | None = None):
    return store.list_incidents(status)


@app.post("/api/incidents")
def create_incident(payload: dict):
    zone = payload.get("zone")
    title = payload.get("title")
    if not zone or not title:
        raise HTTPException(400, "zone and title are required")
    inc = store.create_incident(
        alert_id=payload.get("alert_id"),
        video_id=payload.get("video_id"),
        zone=zone,
        severity=payload.get("severity", "RED"),
        title=title,
        description=payload.get("description", ""),
        recommended_action=payload.get("recommended_action"),
    )
    publish("incident", inc)
    return inc


@app.patch("/api/incidents/{incident_id}")
def update_incident(incident_id: int, payload: dict):
    status = payload.get("status")
    if not status:
        raise HTTPException(400, "status is required")
    inc = store.update_incident(incident_id, status=status, operator_notes=payload.get("operator_notes"))
    if not inc:
        raise HTTPException(404, "incident not found")
    publish("incident", inc)
    return inc


# ---------------------------------------------------------------- predictive risk forecast
@app.get("/api/predictive/forecast")
def predictive_forecast():
    _sync_current_video()
    st = analysis.state.status_dict()
    is_active = st["status"] in ("processing", "paused")
    latest = analysis.state.latest if is_active else None
    dyn = analysis.state.dynamics if is_active else None
    zm = analysis.state.zone_metrics if is_active else None

    current_people = latest["people_count"] if latest else 0
    current_density = latest["density_ppm2"] if latest else 0.0
    current_score = latest["score"] if latest else 0.0
    current_level = latest["level"] if latest else "GREEN"
    accum_rate = zm.get("accumulation_rate_ppm2_per_min") if zm and zm.get("available") else None
    if accum_rate is None:
        hist = list(analysis.state.history)
        if len(hist) >= 6:
            dt = max(1.0, hist[-1]["t_offset_sec"] - hist[0]["t_offset_sec"]) / 60.0
            accum_rate = round((hist[-1]["density_ppm2"] - hist[0]["density_ppm2"]) / dt, 3)
        else:
            accum_rate = 0.0

    critical_threshold = float(SETTINGS.get("critical_density_ppm2", 5.0))
    time_to_critical_min = None
    if accum_rate > 0.02 and current_density < critical_threshold:
        time_to_critical_min = round((critical_threshold - current_density) / accum_rate, 1)

    projections = []
    for m in (0, 3, 5, 10, 15, 20, 30):
        projected_d = max(0.0, round(current_density + (accum_rate * m), 2))
        projected_people = max(0, int(current_people + (accum_rate * m * float(SETTINGS.get("zone_area_m2", 100.0)))))
        risk_proj = min(100.0, max(0.0, round(current_score + (accum_rate * m * 10.0), 1)))
        lvl = "GREEN" if risk_proj < 31 else "YELLOW" if risk_proj < 56 else "ORANGE" if risk_proj < 76 else "RED" if risk_proj < 91 else "BLACK"
        projections.append({
            "minutes_ahead": m,
            "projected_density_ppm2": projected_d,
            "projected_people": projected_people,
            "projected_risk_score": risk_proj,
            "projected_level": lvl,
            "critical_exceeded": projected_d >= critical_threshold,
        })

    scenarios = [
        {
            "name": "Observed Dynamic Baseline",
            "type": "observed",
            "description": "Calculated directly from real-time optical flow & accumulation rates.",
            "inflow_change_pct": 0,
            "projected_peak_density": max(p["projected_density_ppm2"] for p in projections),
            "time_to_critical_min": time_to_critical_min,
            "status": "active" if is_active else "idle",
        },
        {
            "name": "Surge Inflow Simulation (+25%)",
            "type": "modelled",
            "description": "Modelled scenario simulating sudden crowd ingress surge at main entrance.",
            "inflow_change_pct": 25,
            "projected_peak_density": round(max(p["projected_density_ppm2"] for p in projections) * 1.25, 2),
            "time_to_critical_min": round(time_to_critical_min * 0.75, 1) if time_to_critical_min else 7.5,
            "status": "modelled",
        },
        {
            "name": "Egress Bottleneck Restriction (-40%)",
            "type": "modelled",
            "description": "Modelled scenario where exit gates are partially constricted.",
            "inflow_change_pct": 0,
            "outflow_change_pct": -40,
            "projected_peak_density": round(max(p["projected_density_ppm2"] for p in projections) * 1.45, 2),
            "time_to_critical_min": round(time_to_critical_min * 0.55, 1) if time_to_critical_min else 4.8,
            "status": "modelled",
        },
    ]

    return {
        "is_active": is_active,
        "video_id": st["video_id"],
        "current_density": current_density,
        "current_people": current_people,
        "current_level": current_level,
        "critical_threshold": critical_threshold,
        "accumulation_rate_ppm2_per_min": accum_rate,
        "time_to_critical_min": time_to_critical_min,
        "projections": projections,
        "scenarios": scenarios,
        "disclaimer": "Dynamic trend is derived from real optical flow; scenarios are modelled simulations for decision support.",
    }


# ---------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings():
    return SETTINGS


@app.put("/api/settings")
def update_settings(payload: dict):
    allowed = {"detection_confidence", "analysis_sample_every_n", "zone_area_m2",
               "critical_density_ppm2", "risk_thresholds"}
    for k, v in payload.items():
        if k in allowed:
            SETTINGS[k] = v
    SETTINGS["privacy_mode"] = True  # non-negotiable
    get_detector().set_confidence(float(SETTINGS["detection_confidence"]))
    return SETTINGS


# ---------------------------------------------------------------- websocket
@app.websocket("/ws")
@app.websocket("/api/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "connected", "data": None}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clients.discard(websocket)
    except Exception:
        _clients.discard(websocket)

if __name__ == '__main__':
    import uvicorn
    host = os.environ.get('BACKEND_HOST', '0.0.0.0')
    port = int(os.environ.get('BACKEND_PORT', '8000'))
    uvicorn.run('main:app', host=host, port=port, reload=True)

