"""Database layer for VoiceGuard AI.

Tables
------
- analyses          : completed voice analysis records
- speaker_voiceprints : per-speaker feature vectors for cross-session checks
- alert_log         : dispatched alert events
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATABASE_PATH = Path(__file__).parent / "voiceguard.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency under async FastAPI workers
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id                   TEXT PRIMARY KEY,
                created_at           TEXT NOT NULL,
                filename             TEXT NOT NULL,
                duration             REAL NOT NULL,
                human_probability    REAL NOT NULL,
                synthetic_probability REAL NOT NULL,
                confidence           REAL NOT NULL,
                risk_score           INTEGER NOT NULL,
                risk_level           TEXT NOT NULL,
                indicators           TEXT NOT NULL,
                recommended_action   TEXT NOT NULL,
                detection_mode       TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS speaker_voiceprints (
                id          TEXT PRIMARY KEY,
                speaker_id  TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                features    TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_voiceprints_speaker "
            "ON speaker_voiceprints(speaker_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_log (
                id            TEXT PRIMARY KEY,
                analysis_id   TEXT NOT NULL,
                level         TEXT NOT NULL,
                risk_score    INTEGER NOT NULL,
                channel       TEXT NOT NULL,
                indicators    TEXT NOT NULL,
                dispatched_at TEXT NOT NULL
            )
            """
        )


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------

def save_analysis(analysis: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO analyses (
                id, created_at, filename, duration, human_probability,
                synthetic_probability, confidence, risk_score, risk_level,
                indicators, recommended_action, detection_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis["id"],
                analysis["created_at"],
                analysis["filename"],
                analysis["duration"],
                analysis["human_probability"],
                analysis["synthetic_probability"],
                analysis["confidence"],
                analysis["risk_score"],
                analysis["risk_level"],
                json.dumps(analysis["indicators"]),
                analysis["recommended_action"],
                analysis["detection_mode"],
            ),
        )


def list_analyses(limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {**dict(row), "indicators": json.loads(row["indicators"])}
        for row in rows
    ]


def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if row is None:
        return None
    return {**dict(row), "indicators": json.loads(row["indicators"])}


def delete_analysis(analysis_id: str) -> bool:
    """Delete an analysis record.  Returns True when a row was deleted."""
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM analyses WHERE id = ?", (analysis_id,)
        )
    return cursor.rowcount > 0


def get_stats() -> dict[str, Any]:
    """Aggregate statistics over all stored analyses."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                ROUND(AVG(risk_score), 1) AS avg_risk,
                SUM(CASE WHEN risk_level = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_count,
                SUM(CASE WHEN risk_level = 'HIGH'     THEN 1 ELSE 0 END) AS high_count,
                SUM(CASE WHEN risk_level = 'MEDIUM'   THEN 1 ELSE 0 END) AS medium_count,
                SUM(CASE WHEN risk_level = 'LOW'      THEN 1 ELSE 0 END) AS low_count
            FROM analyses
            """
        ).fetchone()
    return {
        "total_analyses": row["total"] or 0,
        "average_risk_score": row["avg_risk"] or 0.0,
        "critical_count": row["critical_count"] or 0,
        "high_count": row["high_count"] or 0,
        "medium_count": row["medium_count"] or 0,
        "low_count": row["low_count"] or 0,
    }


# ---------------------------------------------------------------------------
# Speaker voiceprints
# ---------------------------------------------------------------------------

def save_voiceprint(speaker_id: str, features: dict[str, float]) -> str:
    from uuid import uuid4
    vp_id = str(uuid4())
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO speaker_voiceprints (id, speaker_id, created_at, features)
            VALUES (?, ?, ?, ?)
            """,
            (vp_id, speaker_id, utc_now(), json.dumps(features)),
        )
    return vp_id


def get_voiceprints_for_speaker(
    speaker_id: str, limit: int = 5
) -> list[dict[str, float]]:
    """Return the most recent *limit* feature vectors for *speaker_id*."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT features FROM speaker_voiceprints
            WHERE speaker_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (speaker_id, limit),
        ).fetchall()
    return [json.loads(row["features"]) for row in rows]


def count_voiceprints_for_speaker(speaker_id: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS cnt FROM speaker_voiceprints WHERE speaker_id = ?",
            (speaker_id,),
        ).fetchone()
    return row["cnt"] if row else 0


def delete_old_voiceprints(speaker_id: str, keep: int = 10) -> int:
    """Delete voiceprints beyond the *keep* most recent ones.  Returns deleted count."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM speaker_voiceprints
            WHERE speaker_id = ?
            AND id NOT IN (
                SELECT id FROM speaker_voiceprints
                WHERE speaker_id = ?
                ORDER BY created_at DESC LIMIT ?
            )
            """,
            (speaker_id, speaker_id, keep),
        )
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Alert log
# ---------------------------------------------------------------------------

def log_alert(alert: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO alert_log
            (id, analysis_id, level, risk_score, channel, indicators, dispatched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.get("id", ""),
                alert["analysis_id"],
                alert["level"],
                alert["risk_score"],
                alert.get("channel", "in-app"),
                json.dumps(alert.get("indicators", [])),
                alert.get("dispatched_at", utc_now()),
            ),
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
