"""The ``Applicator`` protocol's default implementation.

Given a single URL and a user profile, drive a Playwright session through
page analysis, form mapping, and action execution until we reach a
terminal state (submitted, failed, or needs review).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from hamster.applicator.browser import ActionExecutor, BrowserManager, DOMExtractor
from hamster.applicator.form_filler import FormMapper, RuleBasedPageAnalyzer
from hamster.shared import (
    ApplicationStatus,
    ApplyResult,
    JobListing,
    PageAnalyzer,
    PageType,
    UserProfile,
)

logger = logging.getLogger(__name__)

_MAX_STEPS = 6  # enough for multi-page wizards; hard cap to avoid loops

# Below this mapping confidence we refuse to actually submit (unless wild
# mode is on) and stop for human review instead. Tune here — there is no
# settings plumbing for it on purpose; it's a safety floor, not a knob users
# should be flipping casually.
SUBMIT_CONFIDENCE_THRESHOLD = 0.8


class ApplicatorEngine:
    """Orchestrates one full apply attempt."""

    def __init__(
        self,
        *,
        browser: BrowserManager,
        dom_extractor: DOMExtractor | None = None,
        page_analyzer: PageAnalyzer | None = None,
        form_mapper: FormMapper | None = None,
        action_executor: ActionExecutor | None = None,
        dry_run: bool = True,
        wild_mode: bool = False,
        screenshot_dir: "Path | None" = None,
    ) -> None:
        self._browser = browser
        self._dom_extractor = dom_extractor or DOMExtractor()
        self._page_analyzer = page_analyzer or RuleBasedPageAnalyzer()
        self._form_mapper = form_mapper or FormMapper()
        self._action_executor = action_executor or ActionExecutor()
        self._dry_run = dry_run
        self._wild_mode = wild_mode
        self._screenshot_dir = screenshot_dir

    async def apply(
        self,
        url: str,
        profile: UserProfile,
        job: JobListing | None = None,
    ) -> ApplyResult:
        # job is request-scoped — passed per call, never stored on the engine,
        # because the worker reuses one engine across many applications.
        page = await self._browser.new_page()
        try:
            await page.goto(url)

            for step in range(_MAX_STEPS):
                dom = await self._dom_extractor.extract(page)
                analysis = await self._page_analyzer.analyze(dom)
                logger.info(
                    "Step %s: %s (confidence=%.2f)",
                    step,
                    analysis.page_type.value,
                    analysis.confidence,
                )

                if analysis.page_type is PageType.CONFIRMATION:
                    return ApplyResult(
                        success=True,
                        status=ApplicationStatus.SUBMITTED,
                        url=url,
                        confidence=analysis.confidence,
                    )
                if analysis.page_type is PageType.CAPTCHA:
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.NEEDS_REVIEW,
                        url=url,
                        intervention_reason="CAPTCHA",
                        confidence=analysis.confidence,
                    )
                if analysis.page_type is PageType.LOGIN:
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.NEEDS_REVIEW,
                        url=url,
                        intervention_reason="LOGIN_REQUIRED",
                        confidence=analysis.confidence,
                    )

                if analysis.page_type is not PageType.APPLICATION_FORM:
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.FAILED,
                        url=url,
                        error=f"Unsupported page type: {analysis.page_type.value}",
                    )

                plan = await self._form_mapper.plan(dom, profile, job)
                if plan.confidence < 0.3:
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.NEEDS_REVIEW,
                        url=url,
                        intervention_reason="LOW_CONFIDENCE",
                        confidence=plan.confidence,
                    )

                action_failures = await self._action_executor.run_plan(
                    page, plan.actions
                )
                execution_failures = [
                    failure.error for failure in action_failures
                ]
                if execution_failures:
                    logger.error(
                        "Filled %s with %d action failure(s): %s",
                        url,
                        len(execution_failures),
                        execution_failures,
                    )

                submit_selector = _find_submit_selector(dom)
                if submit_selector is None:
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.FAILED,
                        url=url,
                        error="No submit button found after filling",
                    )

                # Take a screenshot of the filled form before we click submit
                # (or stop here in dry-run mode).
                screenshot_path = await self._capture_screenshot(page, url)

                if self._dry_run:
                    logger.info(
                        "DRY-RUN: filled form for %s, stopping before submit. "
                        "Screenshot: %s",
                        url,
                        screenshot_path,
                    )
                    base_note = (
                        f"Dry-run complete. Form filled, submit not "
                        f"clicked. Screenshot: {screenshot_path}"
                        if screenshot_path
                        else "Dry-run complete. Form filled, submit not clicked."
                    )
                    # Surface fill failures so a human reconciles a blank field
                    # in the screenshot with a real failure vs. missing data.
                    if execution_failures:
                        base_note += (
                            f" ({len(execution_failures)} field(s) failed to "
                            "fill — see logs)"
                        )
                    return ApplyResult(
                        success=True,
                        status=ApplicationStatus.NEEDS_REVIEW,
                        url=url,
                        confidence=plan.confidence,
                        intervention_reason="DRY_RUN",
                        error=base_note,
                        execution_failures=execution_failures,
                    )

                # Live submission. A field that failed to fill blocks submit
                # even in wild mode: run_plan is now non-fatal, so without this
                # guard wild mode could submit a form with a blank required
                # field. This is the one execution-failure case that must stop
                # a live submit; it doesn't apply to dry-run (handled above).
                if execution_failures:
                    logger.warning(
                        "Not submitting %s: %d field(s) failed to fill. "
                        "Screenshot: %s",
                        url,
                        len(execution_failures),
                        screenshot_path,
                    )
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.NEEDS_REVIEW,
                        url=url,
                        confidence=plan.confidence,
                        intervention_reason="FILL_INCOMPLETE",
                        error=(
                            f"{len(execution_failures)} field(s) failed to "
                            "fill; not submitting. See logs."
                        ),
                        execution_failures=execution_failures,
                    )

                # Unless wild mode is on, refuse to click submit when the form
                # mapping confidence is below the safety floor — fill is done
                # and screenshotted, but a human should look before an
                # irreversible submit. Wild mode skips this: the user has opted
                # into "submit no matter what, zero touch".
                if (
                    not self._wild_mode
                    and plan.confidence < SUBMIT_CONFIDENCE_THRESHOLD
                ):
                    logger.info(
                        "Confidence %.2f below submit threshold %.2f for %s; "
                        "stopping for review. Screenshot: %s",
                        plan.confidence,
                        SUBMIT_CONFIDENCE_THRESHOLD,
                        url,
                        screenshot_path,
                    )
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.NEEDS_REVIEW,
                        url=url,
                        confidence=plan.confidence,
                        intervention_reason="BELOW_SUBMIT_THRESHOLD",
                        error=(
                            f"Mapping confidence {plan.confidence:.2f} below "
                            f"{SUBMIT_CONFIDENCE_THRESHOLD:.2f}; form filled but "
                            "not submitted. Enable wild mode to submit anyway."
                        ),
                    )

                from hamster.shared import ActionType, PageAction

                await self._action_executor.execute(
                    page,
                    PageAction(type=ActionType.CLICK, selector=submit_selector),
                )

                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=10_000
                    )
                except Exception:  # noqa: BLE001
                    # Some single-page-app forms never return to idle; that's OK.
                    pass

            return ApplyResult(
                success=False,
                status=ApplicationStatus.FAILED,
                url=url,
                error=f"Did not reach confirmation within {_MAX_STEPS} steps",
            )
        except Exception as error:  # noqa: BLE001
            logger.exception("apply() crashed")
            return ApplyResult(
                success=False,
                status=ApplicationStatus.FAILED,
                url=url,
                error=str(error),
            )
        finally:
            await page.close()
            logger.info(
                "Apply finished for %s at %s",
                url,
                datetime.now(UTC).isoformat(),
            )

    async def _capture_screenshot(self, page, url: str) -> str | None:
        """Save a screenshot of the filled form. Returns absolute path or None."""
        if self._screenshot_dir is None:
            return None
        try:
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
            from urllib.parse import urlparse

            domain = urlparse(url).netloc.replace(":", "_") or "unknown"
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            path = self._screenshot_dir / f"{timestamp}_{domain}.png"
            await page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to capture screenshot: %s", error)
            return None


def _find_submit_selector(dom) -> str | None:
    from hamster.shared import ElementType

    for element in dom.elements:
        if element.element_type is ElementType.BUTTON:
            label = (element.label or "").lower().strip()
            if any(
                keyword in label
                for keyword in ("submit", "apply", "send", "continue", "next")
            ):
                return element.selector
    return None
