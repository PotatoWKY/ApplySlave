"""Backend test fixtures.

Each test gets a fresh temp data dir via APPLYSLAVE_DATA_DIR so SQLite state
doesn't leak across tests. We also clear the dependency caches between tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from applyslave.backend.dependencies import (
    get_profile_store,
    get_result_logger,
)
from applyslave.backend.main import create_app


@pytest_asyncio.fixture
async def backend_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    # Redirect all persistence into the per-test tmp dir
    os.environ["APPLYSLAVE_DATA_DIR"] = str(tmp_path)

    # Bust the lru_caches so the fixture dir is picked up
    get_profile_store.cache_clear()
    get_result_logger.cache_clear()

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        # Trigger lifespan startup by accessing the app state
        async with app.router.lifespan_context(app):
            yield client


@pytest.fixture
def sample_resume_pdf_path(tmp_path: Path) -> Path:
    """Write a minimal PDF with known fields for resume-upload tests."""
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas")
    path = tmp_path / "fixture_resume.pdf"
    canvas_obj = reportlab.Canvas(str(path))
    lines = [
        "San Zhang",
        "san.zhang@example.com  |  +86 138-0000-0000",
        "https://linkedin.com/in/sanzhang",
        "https://github.com/sanzhang",
    ]
    y = 800
    for line in lines:
        canvas_obj.drawString(50, y, line)
        y -= 20
    canvas_obj.save()
    return path
