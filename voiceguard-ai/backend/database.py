import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATABASE_PATH = Path(__file__).parent / "voiceguard.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                filename TEXT NOT NULL,
                duration REAL NOT NULL,
                human_probability REAL NOT NULL,
                synthetic_probability REAL NOT NULL,
                confidence REAL NOT NULL,
                risk_score INTEGER NOT NULL,
                risk_level TEXT NOT NULL,
                indicators TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                detection_mode TEXT NOT NULL
            )
            """
        )


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


def list_analyses(limit: int = 25) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {
            **dict(row),
            "indicators": json.loads(row["indicators"]),
        }
        for row in rows
    ]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
