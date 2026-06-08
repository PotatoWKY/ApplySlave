"""Playwright-based fixtures for browser tests.

Each browser test spins up a short-lived persistent context against a
temporary profile dir, then closes it. The fixture HTML is served via the
`file://` protocol so tests run offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from hamster.applicator.browser import BrowserManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def apply_form_url() -> str:
    return (FIXTURES_DIR / "apply_form.html").resolve().as_uri()


@pytest_asyncio.fixture
async def browser(tmp_path: Path) -> BrowserManager:
    manager = BrowserManager(
        user_data_dir=tmp_path / "chrome_profile",
        headless=True,
    )
    await manager.launch()
    try:
        yield manager
    finally:
        await manager.close()
