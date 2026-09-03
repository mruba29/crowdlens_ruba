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

_DB_PATH = os.environ.get("CROWDLENS_DB",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "crowdlens.sqlite3"))
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
                acknowledged_at REAL
            )"""
        )


def add_alert(zone: str, level: str, score: float, reason: str, factors: dict) -> dict:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO alerts (created_at, zone, level, score, reason, factors, status) "
            "VALUES (?,?,?,?,?,?, 'ACTIVE')",
            (time.time(), zone, level, float(score), reason, json.dumps(factors)),
        )
        return get_alert(cur.lastrowid)


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
    }
