from __future__ import annotations

from pathlib import Path

from hamster.profile_store import parse_resume


def test_parse_resume_extracts_common_fields(sample_resume_pdf: Path) -> None:
    parsed = parse_resume(sample_resume_pdf)
    assert parsed.email == "san.zhang@example.com"
    assert parsed.first_name == "San"
    assert parsed.last_name == "Zhang"
    assert parsed.linkedin_url is not None
    assert "linkedin.com/in/sanzhang" in parsed.linkedin_url
    assert parsed.github_url is not None
    assert "github.com/sanzhang" in parsed.github_url
    assert parsed.phone is not None
    assert "138" in parsed.phone
