"""The ``Applicator`` protocol's default implementation.

Given a single URL and a user profile, drive a Playwright session through
page analysis, form mapping, and action execution until we reach a
terminal state (submitted, failed, or needs review).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from applyslave.applicator.browser import ActionExecutor, BrowserManager, DOMExtractor
from applyslave.applicator.form_filler import FormMapper, RuleBasedPageAnalyzer
from applyslave.shared import (
    ApplicationStatus,
    ApplyResult,
    PageAnalyzer,
    PageType,
    UserProfile,
)

logger = logging.getLogger(__name__)

_MAX_STEPS = 6  # enough for multi-page wizards; hard cap to avoid loops


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
    ) -> None:
        self._browser = browser
        self._dom_extractor = dom_extractor or DOMExtractor()
        self._page_analyzer = page_analyzer or RuleBasedPageAnalyzer()
        self._form_mapper = form_mapper or FormMapper()
        self._action_executor = action_executor or ActionExecutor()

    async def apply(self, url: str, profile: UserProfile) -> ApplyResult:
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

                plan = await self._form_mapper.plan(dom, profile)
                if plan.confidence < 0.3:
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.NEEDS_REVIEW,
                        url=url,
                        intervention_reason="LOW_CONFIDENCE",
                        confidence=plan.confidence,
                    )

                await self._action_executor.run_plan(page, plan.actions)

                submit_selector = _find_submit_selector(dom)
                if submit_selector is None:
                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.FAILED,
                        url=url,
                        error="No submit button found after filling",
                    )

                from applyslave.shared import ActionType, PageAction

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


def _find_submit_selector(dom) -> str | None:
    from applyslave.shared import ElementType

    for element in dom.elements:
        if element.element_type is ElementType.BUTTON:
            label = (element.label or "").lower().strip()
            if any(
                keyword in label
                for keyword in ("submit", "apply", "send", "continue", "next")
            ):
                return element.selector
    return None
