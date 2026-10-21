"""Tiny persistence layer (sqlite3 stdlib) — alerts + acknowledgements only.

Everything else (live metrics, analysis status) is in-memory application state,
recomputed from the video each run. We persist alerts because the spec needs an
alert history that survives restarts.

Privacy: no names, no faces, no personal data — only anonymous crowd metrics.
"""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
import uuid

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_DB_PATH = os.environ.get(
    "CROWDLENS_DB",
    "/tmp/crowdlens.sqlite3" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "crowdlens.sqlite3")
)
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                zone TEXT NOT NULL,
                level TEXT NOT NULL,
                score REAL NOT NULL,
                reason TEXT NOT NULL,
                factors TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                acknowledged_at REAL,
                alert_type TEXT,
                recommended_action TEXT,
                video_id TEXT
            )"""
        )
        # Uploaded crowd-video library (the "Crowd Videos" browser + the
        # dashboard's "Live Crowd Monitoring" cards). Analysis itself is still
        # single-session/in-memory (see analysis.py) — this table just tracks
        # each uploaded file plus the *last known real* metrics for it, so the
        # UI can list many videos without ever inventing numbers.
        c.execute(
            """CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Uncategorized',
                uploaded_at REAL NOT NULL,
                size_bytes INTEGER,
                duration_sec REAL,
                thumbnail TEXT,
                status TEXT NOT NULL DEFAULT 'uploaded',
                last_people INTEGER,
                last_density REAL,
                last_score REAL,
                last_level TEXT,
                last_analyzed_at REAL
            )"""
        )
        # ---- Phase 1 foundation layer: events / cameras / zones / video_sources ----
        # An Event is the container multiple video sources belong to (temple
        # festival, stadium exit, etc). A video keeps working standalone (as
        # before) until it is attached to an event via video_sources — nothing
        # here changes the existing `videos` table or its API.
        c.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'Public Gathering',
                location TEXT DEFAULT '',
                start_time REAL,
                end_time REAL,
                crowd_context TEXT DEFAULT '',
                demo_children_pct REAL,
                demo_adults_pct REAL,
                demo_elderly_pct REAL,
                demo_gender_male_pct REAL,
                demo_gender_female_pct REAL,
                created_at REAL NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS zones (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'general',
                x REAL DEFAULT 0.1, y REAL DEFAULT 0.1, w REAL DEFAULT 0.2, h REAL DEFAULT 0.2,
                area_m2 REAL DEFAULT 100.0,
                capacity INTEGER DEFAULT 500,
                spatial_context TEXT NOT NULL DEFAULT 'open',
                created_at REAL NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS cameras (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'Uploaded Video',
                location_label TEXT DEFAULT '',
                x REAL DEFAULT 0.5, y REAL DEFAULT 0.5,
                orientation_deg REAL DEFAULT 0,
                zone_id TEXT,
                created_at REAL NOT NULL
            )"""
        )
        # 1:1 with videos.id — presence of a row here is what makes a video
        # "belong" to an event instead of being a standalone upload.
        c.execute(
            """CREATE TABLE IF NOT EXISTS video_sources (
                video_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                camera_id TEXT,
                zone_id TEXT,
                source_type TEXT NOT NULL DEFAULT 'Uploaded Video',
                capture_start_ts REAL,
                inflow_direction TEXT NOT NULL DEFAULT 'right',
                created_at REAL NOT NULL
            )"""
        )
        # ---- Phase 2: lightweight migration for DBs created before these columns existed ----
        for table, col, decl in (
            ("zones", "area_m2", "REAL DEFAULT 100.0"),
            ("zones", "capacity", "INTEGER DEFAULT 500"),
            ("zones", "spatial_context", "TEXT NOT NULL DEFAULT 'open'"),
            ("video_sources", "inflow_direction", "TEXT NOT NULL DEFAULT 'right'"),
            ("events", "demo_children_pct", "REAL"),
            ("events", "demo_adults_pct", "REAL"),
            ("events", "demo_elderly_pct", "REAL"),
            ("events", "demo_gender_male_pct", "REAL"),
            ("events", "demo_gender_female_pct", "REAL"),
            ("alerts", "alert_type", "TEXT"),
            ("alerts", "recommended_action", "TEXT"),
            ("alerts", "video_id", "TEXT"),
            ("videos", "metrics_summary", "TEXT"),
        ):
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass  # column already exists
        # ---- Incidents log table for critical safety incidents ----
        c.execute(
            """CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                alert_id INTEGER,
                video_id TEXT,
                zone TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                recommended_action TEXT,
                operator_notes TEXT,
                resolved_at REAL
            )"""
        )
        # ---- Phase 2: AI-vs-manual validation samples — only ever real, paired,
        # operator-entered numbers; never a fabricated accuracy figure. ----
        c.execute(
            """CREATE TABLE IF NOT EXISTS validation_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                video_id TEXT NOT NULL,
                zone_id TEXT,
                zone_name TEXT,
                ai_count INTEGER,
                manual_count INTEGER,
                count_error INTEGER,
                count_error_pct REAL,
                ai_density REAL,
                manual_density REAL,
                density_error REAL,
                density_error_pct REAL,
                ai_inflow_rate REAL,
                manual_inflow_rate REAL,
                inflow_error REAL,
                ai_outflow_rate REAL,
                manual_outflow_rate REAL,
                outflow_error REAL,
                note TEXT
            )"""
        )
        # ---- Phase 3: crowd-dynamics state-change history (for the Crowd
        # State Timeline + explainability) — one row per real state change,
        # not per frame. ----
        c.execute(
            """CREATE TABLE IF NOT EXISTS dynamics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                video_id TEXT NOT NULL,
                zone_id TEXT,
                zone_name TEXT,
                t_offset_sec REAL NOT NULL,
                dynamic_state TEXT NOT NULL,
                rollup_state TEXT NOT NULL,
                previous_state TEXT,
                contributing_signals TEXT NOT NULL
            )"""
        )


def add_alert(zone: str, level: str, score: float, reason: str, factors: dict, *,
              alert_type: str | None = None, recommended_action: str | None = None,
              video_id: str | None = None) -> dict:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO alerts (created_at, zone, level, score, reason, factors, status, "
            "alert_type, recommended_action, video_id) VALUES (?,?,?,?,?,?, 'ACTIVE', ?,?,?)",
            (time.time(), zone, level, float(score), reason, json.dumps(factors),
             alert_type, recommended_action, video_id),
        )
        alert_id = cur.lastrowid
        if level in ("RED", "BLACK"):
            title = f"{alert_type.replace('_', ' ').title() if alert_type else 'Critical Crowd Surge'} in {zone}"
            c.execute(
                "INSERT INTO incidents (created_at, alert_id, video_id, zone, severity, title, "
                "description, status, recommended_action) VALUES (?,?,?,?,?,?,?,'OPEN',?)",
                (time.time(), alert_id, video_id, zone, level, title, reason, recommended_action),
            )
    return get_alert(alert_id)


def create_incident(*, alert_id: int | None = None, video_id: str | None = None,
                    zone: str, severity: str, title: str, description: str,
                    recommended_action: str | None = None) -> dict:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO incidents (created_at, alert_id, video_id, zone, severity, title, "
            "description, status, recommended_action) VALUES (?,?,?,?,?,?,?,'OPEN',?)",
            (time.time(), alert_id, video_id, zone, severity, title, description, recommended_action),
        )
        last_id = cur.lastrowid
    return get_incident(last_id)


def get_incident(incident_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
        return _incident_row(row) if row else None


def list_incidents(status: str | None = None) -> list[dict]:
    q = "SELECT * FROM incidents"
    args: tuple = ()
    if status and status.upper() != "ALL":
        q += " WHERE status=?"
        args = (status.upper(),)
    q += " ORDER BY id DESC"
    with _conn() as c:
        return [_incident_row(r) for r in c.execute(q, args).fetchall()]


def update_incident(incident_id: int, status: str, operator_notes: str | None = None) -> dict | None:
    with _lock, _conn() as c:
        now = time.time() if status.upper() == "RESOLVED" else None
        if operator_notes is not None:
            c.execute("UPDATE incidents SET status=?, operator_notes=?, resolved_at=? WHERE id=?",
                      (status.upper(), operator_notes, now, incident_id))
        else:
            c.execute("UPDATE incidents SET status=?, resolved_at=? WHERE id=?",
                      (status.upper(), now, incident_id))
    return get_incident(incident_id)


def _incident_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "alert_id": r["alert_id"],
        "video_id": r["video_id"],
        "zone": r["zone"],
        "severity": r["severity"],
        "title": r["title"],
        "description": r["description"],
        "status": r["status"],
        "recommended_action": r["recommended_action"],
        "operator_notes": r["operator_notes"],
        "resolved_at": r["resolved_at"],
    }


def get_alert(alert_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        return _row(row) if row else None


def list_alerts(level_filter: str | None = None) -> list[dict]:
    q = "SELECT * FROM alerts"
    args: tuple = ()
    if level_filter and level_filter.upper() != "ALL":
        q += " WHERE level=?"
        args = (level_filter.upper(),)
    q += " ORDER BY id DESC"
    with _conn() as c:
        return [_row(r) for r in c.execute(q, args).fetchall()]


def acknowledge(alert_id: int) -> dict | None:
    with _lock, _conn() as c:
        c.execute("UPDATE alerts SET status='ACKNOWLEDGED', acknowledged_at=? WHERE id=?",
                  (time.time(), alert_id))
    return get_alert(alert_id)


def last_active_level_for_zone(zone: str) -> str | None:
    with _conn() as c:
        row = c.execute(
            "SELECT level FROM alerts WHERE zone=? ORDER BY id DESC LIMIT 1", (zone,)
        ).fetchone()
        return row["level"] if row else None


def _row(r: sqlite3.Row) -> dict:
    keys = r.keys()
    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "zone": r["zone"],
        "level": r["level"],
        "score": r["score"],
        "reason": r["reason"],
        "factors": json.loads(r["factors"]),
        "status": r["status"],
        "acknowledged_at": r["acknowledged_at"],
        "alert_type": r["alert_type"] if "alert_type" in keys else None,
        "recommended_action": r["recommended_action"] if "recommended_action" in keys else None,
        "video_id": r["video_id"] if "video_id" in keys else None,
    }


# ---------------------------------------------------------------- videos
def add_video(video_id: str, filename: str, category: str, size_bytes: int | None,
              duration_sec: float | None, thumbnail: str | None) -> dict:
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO videos (id, filename, category, uploaded_at, size_bytes, duration_sec, "
            "thumbnail, status) VALUES (?,?,?,?,?,?,?, 'uploaded')",
            (video_id, filename, category or "Uncategorized", time.time(), size_bytes,
             duration_sec, thumbnail),
        )
    return get_video(video_id)  # type: ignore[return-value]


def get_video(video_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        return _video_row(row) if row else None


def list_videos() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM videos ORDER BY uploaded_at DESC").fetchall()
        return [_video_row(r) for r in rows]


def update_video_metrics(video_id: str, *, status: str, people: int | None = None,
                          density: float | None = None, score: float | None = None,
                          level: str | None = None, metrics_summary: dict | str | None = None) -> None:
    with _lock, _conn() as c:
        summary_str = json.dumps(metrics_summary) if isinstance(metrics_summary, dict) else metrics_summary
        if people is None:
            if summary_str is not None:
                c.execute("UPDATE videos SET status=?, metrics_summary=? WHERE id=?", (status, summary_str, video_id))
            else:
                c.execute("UPDATE videos SET status=? WHERE id=?", (status, video_id))
        else:
            if summary_str is not None:
                c.execute(
                    "UPDATE videos SET status=?, last_people=?, last_density=?, last_score=?, "
                    "last_level=?, last_analyzed_at=?, metrics_summary=? WHERE id=?",
                    (status, people, density, score, level, time.time(), summary_str, video_id),
                )
            else:
                c.execute(
                    "UPDATE videos SET status=?, last_people=?, last_density=?, last_score=?, "
                    "last_level=?, last_analyzed_at=? WHERE id=?",
                    (status, people, density, score, level, time.time(), video_id),
                )


def update_video(video_id: str, *, filename: str | None = None, category: str | None = None) -> dict | None:
    """Rename and/or re-categorize an already-uploaded video (metadata only —
    the underlying file on disk is untouched)."""
    fields, args = [], []
    if filename is not None:
        fields.append("filename=?")
        args.append(filename)
    if category is not None:
        fields.append("category=?")
        args.append(category)
    if fields:
        args.append(video_id)
        with _lock, _conn() as c:
            c.execute(f"UPDATE videos SET {', '.join(fields)} WHERE id=?", args)
    return get_video(video_id)


def delete_video(video_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM videos WHERE id=?", (video_id,))


# ---------------------------------------------------------------- events (Phase 1)
def create_event(*, name: str, event_type: str, location: str, start_time: float | None,
                  end_time: float | None, crowd_context: str) -> dict:
    eid = uuid.uuid4().hex
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO events (id, name, event_type, location, start_time, end_time, "
            "crowd_context, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (eid, name, event_type or "Public Gathering", location or "", start_time, end_time,
             crowd_context or "", time.time()),
        )
    return get_event(eid)  # type: ignore[return-value]


def get_event(event_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return _event_row(row) if row else None


def list_events() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
        return [_event_row(r) for r in rows]


def update_event(event_id: str, **fields) -> dict | None:
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        with _lock, _conn() as c:
            c.execute(f"UPDATE events SET {cols} WHERE id=?", (*fields.values(), event_id))
    return get_event(event_id)


def delete_event(event_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM video_sources WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM cameras WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM zones WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM events WHERE id=?", (event_id,))


def _event_row(r: sqlite3.Row) -> dict:
    keys = r.keys()
    return {
        "id": r["id"], "name": r["name"], "event_type": r["event_type"], "location": r["location"],
        "start_time": r["start_time"], "end_time": r["end_time"], "crowd_context": r["crowd_context"],
        "demo_children_pct": r["demo_children_pct"] if "demo_children_pct" in keys else None,
        "demo_adults_pct": r["demo_adults_pct"] if "demo_adults_pct" in keys else None,
        "demo_elderly_pct": r["demo_elderly_pct"] if "demo_elderly_pct" in keys else None,
        "demo_gender_male_pct": r["demo_gender_male_pct"] if "demo_gender_male_pct" in keys else None,
        "demo_gender_female_pct": r["demo_gender_female_pct"] if "demo_gender_female_pct" in keys else None,
        "created_at": r["created_at"],
    }


# ---------------------------------------------------------------- zones (Phase 1 + 2)
def create_zone(event_id: str, name: str, role: str, x: float, y: float, w: float, h: float,
                 area_m2: float = 100.0, capacity: int = 500, spatial_context: str = "open") -> dict:
    zid = uuid.uuid4().hex
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO zones (id, event_id, name, role, x, y, w, h, area_m2, capacity, "
            "spatial_context, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (zid, event_id, name, role or "general", x, y, w, h,
             max(1.0, area_m2), max(1, capacity), spatial_context or "open", time.time()),
        )
    return get_zone(zid)  # type: ignore[return-value]


def get_zone(zone_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM zones WHERE id=?", (zone_id,)).fetchone()
        return _zone_row(row) if row else None


def list_zones(event_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM zones WHERE event_id=? ORDER BY created_at", (event_id,)).fetchall()
        return [_zone_row(r) for r in rows]


def update_zone(zone_id: str, **fields) -> dict | None:
    if not get_zone(zone_id):
        return None
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        with _lock, _conn() as c:
            c.execute(f"UPDATE zones SET {cols} WHERE id=?", (*fields.values(), zone_id))
    return get_zone(zone_id)


def delete_zone(zone_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE cameras SET zone_id=NULL WHERE zone_id=?", (zone_id,))
        c.execute("UPDATE video_sources SET zone_id=NULL WHERE zone_id=?", (zone_id,))
        c.execute("DELETE FROM zones WHERE id=?", (zone_id,))


def _zone_row(r: sqlite3.Row) -> dict:
    keys = r.keys()
    return {
        "id": r["id"], "event_id": r["event_id"], "name": r["name"], "role": r["role"],
        "x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"],
        "area_m2": r["area_m2"] if "area_m2" in keys else 100.0,
        "capacity": r["capacity"] if "capacity" in keys else 500,
        "spatial_context": r["spatial_context"] if "spatial_context" in keys else "open",
        "created_at": r["created_at"],
    }


# ---------------------------------------------------------------- cameras (Phase 1)
def create_camera(event_id: str, name: str, source_type: str, location_label: str,
                   x: float, y: float, orientation_deg: float, zone_id: str | None) -> dict:
    cid = uuid.uuid4().hex
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO cameras (id, event_id, name, source_type, location_label, x, y, "
            "orientation_deg, zone_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, event_id, name, source_type, location_label or "", x, y, orientation_deg,
             zone_id, time.time()),
        )
    return get_camera(cid)  # type: ignore[return-value]


def get_camera(camera_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone()
        return _camera_row(row) if row else None


def list_cameras(event_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM cameras WHERE event_id=? ORDER BY created_at", (event_id,)).fetchall()
        return [_camera_row(r) for r in rows]


def update_camera(camera_id: str, **fields) -> dict | None:
    if not get_camera(camera_id):
        return None
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        with _lock, _conn() as c:
            c.execute(f"UPDATE cameras SET {cols} WHERE id=?", (*fields.values(), camera_id))
    return get_camera(camera_id)


def delete_camera(camera_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE video_sources SET camera_id=NULL WHERE camera_id=?", (camera_id,))
        c.execute("DELETE FROM cameras WHERE id=?", (camera_id,))


def _camera_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "event_id": r["event_id"], "name": r["name"], "source_type": r["source_type"],
        "location_label": r["location_label"], "x": r["x"], "y": r["y"],
        "orientation_deg": r["orientation_deg"], "zone_id": r["zone_id"], "created_at": r["created_at"],
    }


# ---------------------------------------------------------------- video sources (Phase 1)
def attach_video(video_id: str, event_id: str, *, camera_id: str | None, zone_id: str | None,
                  source_type: str, capture_start_ts: float | None,
                  inflow_direction: str = "right") -> dict | None:
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO video_sources (video_id, event_id, camera_id, zone_id, source_type, "
            "capture_start_ts, inflow_direction, created_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(video_id) DO UPDATE SET event_id=excluded.event_id, "
            "camera_id=excluded.camera_id, zone_id=excluded.zone_id, "
            "source_type=excluded.source_type, capture_start_ts=excluded.capture_start_ts, "
            "inflow_direction=excluded.inflow_direction",
            (video_id, event_id, camera_id, zone_id, source_type or "Uploaded Video",
             capture_start_ts, inflow_direction or "right", time.time()),
        )
    return get_event_video(video_id)


def detach_video(video_id: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM video_sources WHERE video_id=?", (video_id,))


def get_video_source(video_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM video_sources WHERE video_id=?", (video_id,)).fetchone()
        return _source_row(row) if row else None


def list_event_videos(event_id: str) -> list[dict]:
    """Video sources attached to an event, joined with the underlying video's
    real data (filename, thumbnail, duration, last-known analysis) and its
    camera/zone names — everything the timeline and multi-camera views need."""
    with _conn() as c:
        rows = c.execute(
            """SELECT vs.*, v.filename, v.category, v.status, v.thumbnail, v.duration_sec,
                      v.size_bytes, v.uploaded_at, v.last_people, v.last_density, v.last_score,
                      v.last_level, v.last_analyzed_at,
                      cam.name AS camera_name, z.name AS zone_name
               FROM video_sources vs
               JOIN videos v ON v.id = vs.video_id
               LEFT JOIN cameras cam ON cam.id = vs.camera_id
               LEFT JOIN zones z ON z.id = vs.zone_id
               WHERE vs.event_id=?
               ORDER BY v.uploaded_at DESC""",
            (event_id,),
        ).fetchall()
        return [_event_video_row(r) for r in rows]


def get_event_video(video_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            """SELECT vs.*, v.filename, v.category, v.status, v.thumbnail, v.duration_sec,
                      v.size_bytes, v.uploaded_at, v.last_people, v.last_density, v.last_score,
                      v.last_level, v.last_analyzed_at,
                      cam.name AS camera_name, z.name AS zone_name
               FROM video_sources vs
               JOIN videos v ON v.id = vs.video_id
               LEFT JOIN cameras cam ON cam.id = vs.camera_id
               LEFT JOIN zones z ON z.id = vs.zone_id
               WHERE vs.video_id=?""",
            (video_id,),
        ).fetchone()
        return _event_video_row(row) if row else None


def _source_row(r: sqlite3.Row) -> dict:
    return {
        "video_id": r["video_id"], "event_id": r["event_id"], "camera_id": r["camera_id"],
        "zone_id": r["zone_id"], "source_type": r["source_type"],
        "capture_start_ts": r["capture_start_ts"], "inflow_direction": r["inflow_direction"],
        "created_at": r["created_at"],
    }


def _event_video_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["video_id"], "event_id": r["event_id"], "camera_id": r["camera_id"],
        "camera_name": r["camera_name"], "zone_id": r["zone_id"], "zone_name": r["zone_name"],
        "source_type": r["source_type"], "capture_start_ts": r["capture_start_ts"],
        "inflow_direction": r["inflow_direction"],
        "filename": r["filename"], "category": r["category"], "status": r["status"],
        "thumbnail": r["thumbnail"], "duration_sec": r["duration_sec"], "size_bytes": r["size_bytes"],
        "uploaded_at": r["uploaded_at"], "last_people": r["last_people"], "last_density": r["last_density"],
        "last_score": r["last_score"], "last_level": r["last_level"], "last_analyzed_at": r["last_analyzed_at"],
    }


# ---------------------------------------------------------------- timeline (Phase 1)
def event_timeline_at(event_id: str, t: float) -> list[dict]:
    """For a chosen global event timestamp `t` (unix seconds), work out where
    each attached source's playback should be. Never fakes a sync: a source
    with no operator-declared start time is always reported 'unavailable'."""
    out = []
    for v in list_event_videos(event_id):
        cst = v["capture_start_ts"]
        entry = {
            "video_id": v["id"], "filename": v["filename"], "camera_id": v["camera_id"],
            "camera_name": v["camera_name"], "zone_id": v["zone_id"], "zone_name": v["zone_name"],
            "source_type": v["source_type"], "capture_start_ts": cst,
        }
        if cst is None:
            entry.update(sync_status="unavailable", source_offset_sec=None, sync_offset_sec=None)
        else:
            offset = t - cst
            dur = v["duration_sec"]
            in_range = offset >= 0 and (dur is None or offset <= dur)
            entry.update(
                sync_status="synced" if in_range else "out_of_range",
                source_offset_sec=round(offset, 2) if in_range else None,
                sync_offset_sec=round(offset, 2),
            )
        out.append(entry)
    return out


def _video_row(r: sqlite3.Row) -> dict:
    keys = r.keys()
    summary = None
    if "metrics_summary" in keys and r["metrics_summary"]:
        try:
            summary = json.loads(r["metrics_summary"])
        except Exception:
            summary = None
    return {
        "id": r["id"],
        "filename": r["filename"],
        "category": r["category"],
        "uploaded_at": r["uploaded_at"],
        "size_bytes": r["size_bytes"],
        "duration_sec": r["duration_sec"],
        "thumbnail": r["thumbnail"],
        "status": r["status"],
        "last_people": r["last_people"],
        "last_density": r["last_density"],
        "last_score": r["last_score"],
        "last_level": r["last_level"],
        "last_analyzed_at": r["last_analyzed_at"],
        "metrics_summary": summary,
    }


# ---------------------------------------------------------------- validation (Phase 2)
def _err(ai: float | None, manual: float | None) -> tuple[float | None, float | None]:
    """(absolute error, percent error) — only ever computed from two real,
    operator-supplied numbers. None propagates if either side is missing;
    never a fabricated figure."""
    if ai is None or manual is None:
        return None, None
    err = ai - manual
    pct = round((err / manual) * 100.0, 1) if manual else None
    return round(err, 3), pct


def add_validation_sample(*, video_id: str, zone_id: str | None, zone_name: str | None,
                           ai_count: int | None, manual_count: int | None,
                           ai_density: float | None, manual_density: float | None,
                           ai_inflow_rate: float | None, manual_inflow_rate: float | None,
                           ai_outflow_rate: float | None, manual_outflow_rate: float | None,
                           note: str) -> dict:
    count_error, count_error_pct = _err(ai_count, manual_count)
    density_error, density_error_pct = _err(ai_density, manual_density)
    inflow_error, _ = _err(ai_inflow_rate, manual_inflow_rate)
    outflow_error, _ = _err(ai_outflow_rate, manual_outflow_rate)
    with _lock, _conn() as c:
        cur = c.execute(
            """INSERT INTO validation_samples
               (created_at, video_id, zone_id, zone_name, ai_count, manual_count, count_error,
                count_error_pct, ai_density, manual_density, density_error, density_error_pct,
                ai_inflow_rate, manual_inflow_rate, inflow_error, ai_outflow_rate,
                manual_outflow_rate, outflow_error, note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), video_id, zone_id, zone_name, ai_count, manual_count, count_error,
             count_error_pct, ai_density, manual_density, density_error, density_error_pct,
             ai_inflow_rate, manual_inflow_rate, inflow_error, ai_outflow_rate,
             manual_outflow_rate, outflow_error, note or ""),
        )
        rid = cur.lastrowid
    with _conn() as c:
        return _validation_row(c.execute("SELECT * FROM validation_samples WHERE id=?", (rid,)).fetchone())


def list_validation_samples(video_id: str | None = None) -> list[dict]:
    with _conn() as c:
        if video_id:
            rows = c.execute("SELECT * FROM validation_samples WHERE video_id=? ORDER BY id DESC", (video_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM validation_samples ORDER BY id DESC").fetchall()
        return [_validation_row(r) for r in rows]


def validation_summary(video_id: str | None = None) -> dict:
    samples = list_validation_samples(video_id)
    if not samples:
        return {"sample_count": 0, "mean_abs_count_error": None, "mean_abs_count_error_pct": None,
                "mean_abs_density_error": None, "mean_abs_density_error_pct": None,
                "mean_abs_inflow_error": None, "mean_abs_outflow_error": None}

    def mabs(key: str) -> float | None:
        vals = [abs(s[key]) for s in samples if s[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "sample_count": len(samples),
        "mean_abs_count_error": mabs("count_error"),
        "mean_abs_count_error_pct": mabs("count_error_pct"),
        "mean_abs_density_error": mabs("density_error"),
        "mean_abs_density_error_pct": mabs("density_error_pct"),
        "mean_abs_inflow_error": mabs("inflow_error"),
        "mean_abs_outflow_error": mabs("outflow_error"),
    }


def _validation_row(r: sqlite3.Row) -> dict:
    return {k: r[k] for k in r.keys()}


# ---------------------------------------------------------------- dynamics events (Phase 3)
def add_dynamics_event(*, video_id: str, zone_id: str | None, zone_name: str | None,
                        t_offset_sec: float, dynamic_state: str, rollup_state: str,
                        previous_state: str | None, contributing_signals: list[str]) -> dict:
    with _lock, _conn() as c:
        cur = c.execute(
            """INSERT INTO dynamics_events
               (created_at, video_id, zone_id, zone_name, t_offset_sec, dynamic_state,
                rollup_state, previous_state, contributing_signals)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (time.time(), video_id, zone_id, zone_name, t_offset_sec, dynamic_state,
             rollup_state, previous_state, json.dumps(contributing_signals)),
        )
        rid = cur.lastrowid
    with _conn() as c:
        return _dynamics_event_row(c.execute("SELECT * FROM dynamics_events WHERE id=?", (rid,)).fetchone())


def list_dynamics_events(video_id: str, limit: int = 200) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM dynamics_events WHERE video_id=? ORDER BY id DESC LIMIT ?",
            (video_id, limit),
        ).fetchall()
        return [_dynamics_event_row(r) for r in reversed(rows)]


def _dynamics_event_row(r: sqlite3.Row) -> dict:
    d = {k: r[k] for k in r.keys()}
    d["contributing_signals"] = json.loads(d["contributing_signals"])
    return d


# Ensure all database tables and migrations are initialized on module load
try:
    init()
except Exception:
    pass


