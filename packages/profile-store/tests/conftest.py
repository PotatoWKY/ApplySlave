"""Fixtures that build a tiny PDF on disk for resume-parser tests.

We generate PDFs via reportlab only when tests actually need a real PDF; this
keeps the package's runtime dependency footprint to pdfplumber alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "ApplySlave"


@pytest.fixture
def sample_resume_pdf(tmp_path: Path) -> Path:
    """Generate a minimal PDF resume on disk for the test session."""
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas")
    canvas = reportlab.Canvas

    path = tmp_path / "sample_resume.pdf"
    canvas_obj = canvas(str(path))
    y = 800
    for line in [
        "San Zhang",
        "san.zhang@example.com  |  +86 138-0000-0000",
        "https://linkedin.com/in/sanzhang",
        "https://github.com/sanzhang",
        "",
        "Experience",
        "Software Engineer, XX Corp (2022 - Present)",
        "  Built stuff, shipped stuff.",
        "",
        "Education",
        "XX University, BS Computer Science (2018 - 2022)",
    ]:
        canvas_obj.drawString(50, y, line)
        y -= 20
    canvas_obj.save()
    return path
