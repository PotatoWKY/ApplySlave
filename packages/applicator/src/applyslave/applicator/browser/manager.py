"""Playwright browser lifecycle management with persistent context and stealth.

Uses Chromium with a persistent user-data-dir so login sessions survive across
runs. Injects a stealth init script to hide the usual automation fingerprints
(webdriver flag, missing plugins, missing chrome.runtime, etc).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from types import TracebackType
from typing import Self

from playwright.async_api import BrowserContext, Page, async_playwright

from applyslave.applicator.browser.stealth import STEALTH_INIT_SCRIPT

logger = logging.getLogger(__name__)


class BrowserManager:
    """Long-lived wrapper around a Playwright persistent browser context."""

    def __init__(
        self,
        *,
        user_data_dir: Path,
        headless: bool = False,
        slow_mo_ms: int = 0,
        channel: str = "chromium",
    ) -> None:
        self._user_data_dir = Path(user_data_dir)
        self._headless = headless
        self._slow_mo_ms = slow_mo_ms
        self._channel = channel
        self._playwright = None
        self._context: BrowserContext | None = None

    @property
    def context(self) -> BrowserContext | None:
        return self._context

    @property
    def has_session(self) -> bool:
        return self._user_data_dir.exists() and any(self._user_data_dir.iterdir())

    async def launch(self) -> None:
        """Start Playwright and open a persistent context."""
        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()

        launch_kwargs: dict = {
            "user_data_dir": str(self._user_data_dir),
            "headless": self._headless,
            "slow_mo": self._slow_mo_ms,
            "args": [
                "--disable-blink-features=AutomationControlled",
            ],
            "ignore_default_args": ["--enable-automation"],
        }
        # Only pin the channel when the caller explicitly asked for one that
        # needs the system browser (e.g. "chrome"). Default "chromium" uses
        # Playwright's bundled build and should not pass channel=.
        if self._channel != "chromium":
            launch_kwargs["channel"] = self._channel

        self._context = await self._playwright.chromium.launch_persistent_context(
            **launch_kwargs
        )
        await self._context.add_init_script(STEALTH_INIT_SCRIPT)
        logger.info("Browser launched (profile=%s)", self._user_data_dir)

    async def new_page(self) -> Page:
        if self._context is None:
            raise RuntimeError("BrowserManager.launch() must be called first")
        return await self._context.new_page()

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser closed")

    def clear_session(self) -> None:
        if self._user_data_dir.exists():
            shutil.rmtree(self._user_data_dir)
            logger.info("Cleared session at %s", self._user_data_dir)

    async def __aenter__(self) -> Self:
        await self.launch()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()
