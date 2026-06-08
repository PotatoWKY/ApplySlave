"""Execute atomic page actions produced by the form-filler.

Each action is a tiny step the Python layer can reason about: fill a text
field, click a button, pick a select option, upload a file. The executor is
intentionally mechanical — all decision-making happens upstream.
"""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import Page

from hamster.shared import ActionType, PageAction

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 5_000


class ActionError(Exception):
    """Raised when executing a single action fails after retries."""


class ActionExecutor:
    """Execute a single PageAction against a Page."""

    def __init__(self, *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        self._timeout_ms = timeout_ms

    async def execute(self, page: Page, action: PageAction) -> None:
        logger.debug("Executing %s on %s", action.type.value, action.selector)
        try:
            match action.type:
                case ActionType.FILL:
                    await self._fill(page, action)
                case ActionType.CLICK:
                    await self._click(page, action)
                case ActionType.SELECT:
                    await self._select(page, action)
                case ActionType.CHECK:
                    await page.check(action.selector, timeout=self._timeout_ms)
                case ActionType.UNCHECK:
                    await page.uncheck(action.selector, timeout=self._timeout_ms)
                case ActionType.UPLOAD:
                    await self._upload(page, action)
        except Exception as error:  # noqa: BLE001
            raise ActionError(
                f"{action.type.value} failed on {action.selector}: {error}"
            ) from error

    async def run_plan(self, page: Page, actions: list[PageAction]) -> None:
        for action in actions:
            await self.execute(page, action)

    # --- private helpers ------------------------------------------------

    async def _fill(self, page: Page, action: PageAction) -> None:
        value = action.value or ""
        locator = page.locator(action.selector).first
        await locator.click(timeout=self._timeout_ms)
        await locator.fill("")
        await locator.fill(value, timeout=self._timeout_ms)

    async def _click(self, page: Page, action: PageAction) -> None:
        await page.click(action.selector, timeout=self._timeout_ms)

    async def _select(self, page: Page, action: PageAction) -> None:
        if action.value is None:
            raise ActionError(f"select requires a value: {action.selector}")
        try:
            await page.select_option(
                action.selector,
                label=action.value,
                timeout=self._timeout_ms,
            )
        except Exception:
            # Some dropdowns only match by value, not label
            await page.select_option(
                action.selector,
                value=action.value,
                timeout=self._timeout_ms,
            )

    async def _upload(self, page: Page, action: PageAction) -> None:
        if not action.value:
            raise ActionError(f"upload requires a file path: {action.selector}")
        file_path = Path(action.value)
        if not file_path.exists():
            raise ActionError(f"upload source does not exist: {file_path}")
        await page.set_input_files(
            action.selector, str(file_path), timeout=self._timeout_ms
        )
