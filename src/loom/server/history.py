"""Durable run history for the web dashboard.

The dashboard keeps live runs in memory, which is fine while the server is up
but means the "past builds" list empties on every restart. This module stores a
small summary row per run in SQLite (alongside the existing ~/.loom state) so
history survives restarts.

Only finished-run summaries are persisted - live progress stays in memory and
streams over the websocket.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DIR = Path.home() / ".loom"
DEFAULT_HISTORY_DB = DEFAULT_HISTORY_DIR / "runs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    thread_id         TEXT,
    description       TEXT NOT NULL,
    status            TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    completed_at      TEXT,
    duration_seconds  REAL,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    total_cost_usd    REAL NOT NULL DEFAULT 0.0,
    tests_verified    INTEGER NOT NULL DEFAULT 0,
    error             TEXT,
    extra             TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at DESC);
"""


@dataclass
class RunRecord:
    """One persisted build run."""

    run_id: str
    thread_id: str | None
    description: str
    status: str
    started_at: str
    completed_at: str | None = None
    duration_seconds: float | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tests_verified: bool = False
    error: str | None = None
    extra: dict[str, object] | None = None


class RunHistory:
    """SQLite-backed store of build run summaries."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_HISTORY_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, record: RunRecord) -> None:
        """Insert or update a run summary.

        History is a convenience, never the source of truth for a live run, so
        a write failure is logged and swallowed rather than failing the build.
        """
        try:
            payload = asdict(record)
            payload["tests_verified"] = int(record.tests_verified)
            payload["extra"] = json.dumps(record.extra) if record.extra else None
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO runs (
                        run_id, thread_id, description, status, started_at,
                        completed_at, duration_seconds, total_tokens,
                        total_cost_usd, tests_verified, error, extra
                    ) VALUES (
                        :run_id, :thread_id, :description, :status, :started_at,
                        :completed_at, :duration_seconds, :total_tokens,
                        :total_cost_usd, :tests_verified, :error, :extra
                    )
                    ON CONFLICT(run_id) DO UPDATE SET
                        status           = excluded.status,
                        completed_at     = excluded.completed_at,
                        duration_seconds = excluded.duration_seconds,
                        total_tokens     = excluded.total_tokens,
                        total_cost_usd   = excluded.total_cost_usd,
                        tests_verified   = excluded.tests_verified,
                        error            = excluded.error,
                        extra            = excluded.extra
                    """,
                    payload,
                )
        except sqlite3.Error as e:
            logger.warning(f"Could not persist run {record.run_id}: {e}")

    def list(self, limit: int = 100) -> list[RunRecord]:
        """Return the most recent runs, newest first."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
        except sqlite3.Error as e:
            logger.warning(f"Could not read run history: {e}")
            return []
        return [self._to_record(r) for r in rows]

    def get(self, run_id: str) -> RunRecord | None:
        """Return one run by id, or None."""
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        except sqlite3.Error as e:
            logger.warning(f"Could not read run {run_id}: {e}")
            return None
        return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            thread_id=row["thread_id"],
            description=row["description"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_seconds=row["duration_seconds"],
            total_tokens=row["total_tokens"],
            total_cost_usd=row["total_cost_usd"],
            tests_verified=bool(row["tests_verified"]),
            error=row["error"],
            extra=json.loads(row["extra"]) if row["extra"] else None,
        )


_history: RunHistory | None = None


def get_history() -> RunHistory:
    """Get the process-wide run history store."""
    global _history
    if _history is None:
        _history = RunHistory()
    return _history
