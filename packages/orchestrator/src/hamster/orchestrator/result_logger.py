"""SQLite-backed persistence for discovery tasks and application records.

Uses the same database file as profile-store by convention; callers pass in a
shared data directory. Schema is append-only for application history so users
can see everything they've ever submitted.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from hamster.shared import ApplicationRecord, ApplicationStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    applied_at TEXT,
    created_at TEXT NOT NULL,
    job_listing_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);

CREATE TABLE IF NOT EXISTS discovery_tasks (
    id TEXT PRIMARY KEY,
    keywords TEXT NOT NULL,
    location TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    status TEXT NOT NULL,
    results_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class ResultLogger:
    """Persist application attempts and discovery tasks."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "profile.db"
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # Migration: older DBs may not have the job_listing_json column
            cursor = conn.execute("PRAGMA table_info(applications)")
            columns = {row["name"] for row in cursor.fetchall()}
            if "job_listing_json" not in columns:
                conn.execute(
                    "ALTER TABLE applications ADD COLUMN job_listing_json TEXT"
                )

    # --- Applications ----------------------------------------------------

    def insert_application(self, record: ApplicationRecord) -> ApplicationRecord:
        now = datetime.now(UTC)
        applied_at = record.applied_at.isoformat() if record.applied_at else None
        job_json = (
            record.job.model_dump_json() if record.job is not None else None
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO applications (
                    url, company, title, status, error, applied_at, created_at,
                    job_listing_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    status = excluded.status,
                    error = excluded.error,
                    applied_at = excluded.applied_at,
                    job_listing_json = COALESCE(
                        excluded.job_listing_json, job_listing_json
                    )
                RETURNING id
                """,
                (
                    record.url,
                    record.company,
                    record.title,
                    record.status.value,
                    record.error,
                    applied_at,
                    now.isoformat(),
                    job_json,
                ),
            )
            inserted_id = int(cursor.fetchone()[0])
        return record.model_copy(update={"id": inserted_id, "created_at": now})

    def update_status(
        self,
        application_id: int,
        *,
        status: ApplicationStatus,
        error: str | None = None,
        applied_at: datetime | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE applications
                SET status = ?, error = ?, applied_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    error,
                    applied_at.isoformat() if applied_at else None,
                    application_id,
                ),
            )

    def list_applications(
        self,
        *,
        status: ApplicationStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApplicationRecord]:
        query = "SELECT * FROM applications"
        params: tuple = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params = params + (limit, offset)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_by_url(self, url: str) -> ApplicationRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM applications WHERE url = ?", (url,)
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    # --- Discovery tasks -------------------------------------------------

    def save_discovery_task(
        self,
        *,
        task_id: str,
        keywords: str,
        location: str,
        filters: dict,
        status: str,
        results: list[dict] | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO discovery_tasks (
                    id, keywords, location, filters_json, status,
                    results_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    results_json = excluded.results_json,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    keywords,
                    location,
                    json.dumps(filters),
                    status,
                    json.dumps(results) if results is not None else None,
                    now,
                    now,
                ),
            )

    def load_discovery_task(self, task_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM discovery_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "keywords": row["keywords"],
            "location": row["location"],
            "filters": json.loads(row["filters_json"]),
            "status": row["status"],
            "results": json.loads(row["results_json"]) if row["results_json"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def _row_to_record(row: sqlite3.Row) -> ApplicationRecord:
    from hamster.shared import JobListing

    applied_at_str = row["applied_at"]
    created_at_str = row["created_at"]

    job: JobListing | None = None
    # Older rows may not have this column; sqlite3.Row indexes by name only
    # if the column exists, so guard with `keys()`.
    if "job_listing_json" in row.keys() and row["job_listing_json"]:
        try:
            job = JobListing.model_validate_json(row["job_listing_json"])
        except Exception:  # noqa: BLE001
            job = None

    return ApplicationRecord(
        id=row["id"],
        url=row["url"],
        company=row["company"],
        title=row["title"],
        status=ApplicationStatus(row["status"]),
        error=row["error"],
        applied_at=datetime.fromisoformat(applied_at_str) if applied_at_str else None,
        created_at=datetime.fromisoformat(created_at_str) if created_at_str else None,
        job=job,
    )
