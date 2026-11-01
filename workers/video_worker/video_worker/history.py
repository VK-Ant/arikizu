"""SQLite history for video analyses.

Stores event metadata only. Never stores frame images. Uses the same DB
file as the Arikizu audit log by default so recent activity flows into the
operator dashboard without extra wiring.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .models import _find_project_root

DB_PATH = os.environ.get("ARIKIZU_VIDEO_DB", str(_find_project_root() / "arikizu.db"))


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.execute("""
        CREATE TABLE IF NOT EXISTS video_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            video_name TEXT,
            prompt TEXT,
            backend TEXT,
            total_frames INTEGER,
            analyzed_frames INTEGER,
            duration_s REAL,
            event_count INTEGER,
            payload_json TEXT
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS ix_video_analyses_created_at
        ON video_analyses(created_at DESC)
    """)
    return c


def record(video_name: str, prompt: str, backend: str,
           total_frames: int, analyzed_frames: int, duration_s: float,
           events: list[dict], subjects: list[dict], scene: dict | None = None,
           motion_analysis: dict | None = None) -> int:
    """Store one analysis. Returns the new row id."""
    payload = {
        "events": events,
        "subjects": subjects,
        "scene": scene or {},
        "motion_analysis": motion_analysis or {},
    }
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO video_analyses
               (created_at, video_name, prompt, backend, total_frames, analyzed_frames,
                duration_s, event_count, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), video_name, prompt, backend, total_frames,
             analyzed_frames, duration_s, len(events), json.dumps(payload)),
        )
        return int(cur.lastrowid)


def recent(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent analyses, newest first."""
    with _conn() as c:
        rows = c.execute(
            """SELECT id, created_at, video_name, prompt, backend, total_frames,
                      analyzed_frames, duration_s, event_count
               FROM video_analyses
               ORDER BY created_at DESC
               LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return [{
        "id": r[0], "created_at": r[1], "video_name": r[2], "prompt": r[3],
        "backend": r[4], "total_frames": r[5], "analyzed_frames": r[6],
        "duration_s": r[7], "event_count": r[8],
    } for r in rows]


def get(event_id: int) -> dict[str, Any] | None:
    """Full detail for one analysis including events + subjects."""
    with _conn() as c:
        row = c.execute(
            """SELECT id, created_at, video_name, prompt, backend, total_frames,
                      analyzed_frames, duration_s, event_count, payload_json
               FROM video_analyses WHERE id = ?""",
            (int(event_id),),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row[9]) if row[9] else {}
    return {
        "id": row[0], "created_at": row[1], "video_name": row[2], "prompt": row[3],
        "backend": row[4], "total_frames": row[5], "analyzed_frames": row[6],
        "duration_s": row[7], "event_count": row[8],
        **payload,
    }
