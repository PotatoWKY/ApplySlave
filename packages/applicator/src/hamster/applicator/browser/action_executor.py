"""Execute atomic page actions produced by the form-filler.

Each action is a tiny step the Python layer can reason about: fill a text
field, click a button, pick a select option, upload a file. The executor is
intentionally mechanical — all decision-making happens upstream.
"""

from __future__ import annotations

import logging
from pathlib import Path

from hamster.applicator.matching import (
    COMBOBOX_OPTION_SELECTOR,
    first_matching_index,
    normalize_option,
)
from hamster.shared import ActionFailure, ActionType, PageAction
from playwright.async_api import Page

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
                case ActionType.SELECT_COMBOBOX:
                    await self._select_combobox(page, action)
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

    async def run_plan(
        self, page: Page, actions: list[PageAction]
    ) -> list[ActionFailure]:
        """Execute every action, collecting per-action failures instead of
        aborting on the first one.

        A single field that won't fill (stale selector, an out-of-range value)
        must not throw away the other fields that filled fine — the engine
        still needs to screenshot and reach the dry-run / review gate. Each
        failure is captured as an ActionFailure and surfaced to the engine
        (which blocks live submit when any are present).

        Only ActionError is caught here. execute() already wraps every
        per-action exception in ActionError, so in practice that covers the
        action-level faults; anything raised outside execute() (a programming
        error in this loop itself) still propagates.
        """
        failures: list[ActionFailure] = []
        for action in actions:
            try:
                await self.execute(page, action)
            except ActionError as error:
                logger.error("Action failed (continuing): %s", error)
                failures.append(
                    ActionFailure(
                        selector=action.selector,
                        action_type=action.type,
                        error=str(error),
                    )
                )
        return failures

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

    async def _select_combobox(self, page: Page, action: PageAction) -> None:
        """Pick an option in a JS-driven combobox (any role=combobox widget).

        Open the control, then click the option whose text matches the value.
        Options render only while open and are located via the standards-first
        COMBOBOX_OPTION_SELECTOR ([role=option], react-select class as fallback),
        so this works on Greenhouse, Ashby, headless-ui, MUI, etc. Match is
        exact-trimmed first, then a case-insensitive contains fallback for
        labels that carry extra whitespace or punctuation.
        """
        if action.value is None:
            raise ActionError(f"combobox requires a value: {action.selector}")

        await page.click(action.selector, timeout=self._timeout_ms)
        await page.wait_for_selector(
            COMBOBOX_OPTION_SELECTOR, timeout=self._timeout_ms
        )

        # Resolve the option to click from the live menu text, using the same
        # exact-then-contains rule the mapper validated the value against (see
        # hamster.applicator.matching) so the two never disagree.
        option_locator = page.locator(COMBOBOX_OPTION_SELECTOR)
        option_texts = await option_locator.all_text_contents()
        match_index = first_matching_index(
            normalize_option(action.value), option_texts
        )
        if match_index is None:
            await page.keyboard.press("Escape")
            raise ActionError(
                f"no combobox option matching {action.value!r} for "
                f"{action.selector}"
            )
        await option_locator.nth(match_index).click(timeout=self._timeout_ms)

    async def _upload(self, page: Page, action: PageAction) -> None:
        if not action.value:
            raise ActionError(f"upload requires a file path: {action.selector}")
        file_path = Path(action.value)
        if not file_path.exists():
            raise ActionError(f"upload source does not exist: {file_path}")
        await page.set_input_files(
            action.selector, str(file_path), timeout=self._timeout_ms
        )
