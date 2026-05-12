"""SQLite storage for the user profile.

Single-user app: exactly zero or one profile row. Lists (education / experience
/ skills) are JSON-encoded inside the profile row for simplicity. If we ever
need to query into those (we won't — this is personal profile data), we can
normalize later.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from applyslave.shared import Education, Experience, UserProfile

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    location TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    education_json TEXT NOT NULL DEFAULT '[]',
    experience_json TEXT NOT NULL DEFAULT '[]',
    skills_json TEXT NOT NULL DEFAULT '[]',
    resume_path TEXT,
    updated_at TEXT NOT NULL
);
"""


class ProfileStore:
    """Filesystem-backed storage under a single data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.resumes_dir = self.data_dir / "resumes"
        self.resumes_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "profile.db"
        self._ensure_schema()

    # --- Schema ---------------------------------------------------------

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Profile CRUD ---------------------------------------------------

    def save_profile(self, profile: UserProfile) -> UserProfile:
        """Insert a new profile or update the existing row.

        Single-user app: we enforce at most one row by reusing id=1.
        """
        now = datetime.now(UTC)
        payload = (
            profile.first_name,
            profile.last_name,
            profile.email,
            profile.phone,
            profile.location,
            profile.linkedin_url,
            profile.github_url,
            json.dumps([edu.model_dump() for edu in profile.education]),
            json.dumps([exp.model_dump() for exp in profile.experience]),
            json.dumps(profile.skills),
            profile.resume_path,
            now.isoformat(),
        )
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM user_profile LIMIT 1").fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO user_profile (
                        first_name, last_name, email, phone, location,
                        linkedin_url, github_url,
                        education_json, experience_json, skills_json,
                        resume_path, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                profile_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                profile_id = int(existing[0])
                conn.execute(
                    """
                    UPDATE user_profile SET
                        first_name = ?, last_name = ?, email = ?,
                        phone = ?, location = ?,
                        linkedin_url = ?, github_url = ?,
                        education_json = ?, experience_json = ?, skills_json = ?,
                        resume_path = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*payload, profile_id),
                )

        return profile.model_copy(update={"id": profile_id, "updated_at": now})

    def load_profile(self) -> UserProfile | None:
        """Return the single stored profile, or None."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM user_profile LIMIT 1").fetchone()
        if row is None:
            return None
        return UserProfile(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row["email"],
            phone=row["phone"],
            location=row["location"],
            linkedin_url=row["linkedin_url"],
            github_url=row["github_url"],
            education=[Education(**edu) for edu in json.loads(row["education_json"])],
            experience=[Experience(**exp) for exp in json.loads(row["experience_json"])],
            skills=list(json.loads(row["skills_json"])),
            resume_path=row["resume_path"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # --- Resume files ---------------------------------------------------

    def save_resume_file(self, source: Path, name: str = "main_resume") -> Path:
        """Copy a PDF into the managed resumes dir. Returns the stored path."""
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"Resume source not found: {source}")
        if source.suffix.lower() != ".pdf":
            raise ValueError(f"Resume must be a PDF: {source}")
        target = self.resumes_dir / f"{name}.pdf"
        shutil.copy2(source, target)
        return target

    def get_resume_path(self, name: str = "main_resume") -> Path | None:
        candidate = self.resumes_dir / f"{name}.pdf"
        return candidate if candidate.exists() else None
