"""Shared test fixtures (PDF resumes etc) for end-to-end / dry-run testing.

Lives at the repo root rather than inside any one package because both
profile-store tests and integration tests need access.
"""

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent
TEST_RESUME_PDF = FIXTURES_DIR / "pat_apply_resume.pdf"
