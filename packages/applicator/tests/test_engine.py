"""End-to-end engine test against the local fixture form."""

from __future__ import annotations

from pathlib import Path

from applyslave.applicator import ApplicatorEngine
from applyslave.applicator.browser import BrowserManager
from applyslave.shared import (
    ApplicationStatus,
    PageAnalysis,
    PageDOM,
    PageType,
    UserProfile,
)


class _AlwaysConfirmedAnalyzer:
    """Simulates a confirmation page on the second extraction call."""

    def __init__(self) -> None:
        self.call = 0

    def analyze_sync(self, dom: PageDOM) -> PageAnalysis | None:
        return None

    async def analyze(self, dom: PageDOM) -> PageAnalysis:
        self.call += 1
        if self.call == 1:
            return PageAnalysis(
                page_type=PageType.APPLICATION_FORM, confidence=0.9, reasoning="stub"
            )
        return PageAnalysis(
            page_type=PageType.CONFIRMATION, confidence=0.9, reasoning="stub"
        )


async def test_engine_runs_on_fixture_form(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n%EOF\n")

    profile = UserProfile(
        first_name="San",
        last_name="Zhang",
        email="san@example.com",
        phone="+86 13800000000",
        location="Shanghai",
        resume_path=str(resume),
    )

    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=_AlwaysConfirmedAnalyzer(),
        dry_run=False,  # this test verifies the live submit path
    )
    result = await engine.apply(apply_form_url, profile)

    # Fixture form's Submit button redirects (self-POST with hash),
    # so we check that we exited cleanly at the confirmation step.
    assert result.status is ApplicationStatus.SUBMITTED
    assert result.success is True


class _AlwaysFormAnalyzer:
    """Always returns APPLICATION_FORM so the engine reaches the submit step."""

    async def analyze(self, dom: PageDOM) -> PageAnalysis:
        return PageAnalysis(
            page_type=PageType.APPLICATION_FORM, confidence=0.9, reasoning="stub"
        )


async def test_engine_dry_run_stops_before_submit(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n%EOF\n")

    profile = UserProfile(
        first_name="Pat",
        last_name="Apply",
        email="pat.apply@example.com",
        phone="+1-555-0100",
        location="Seattle, WA",
        resume_path=str(resume),
    )

    screenshot_dir = tmp_path / "shots"
    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=_AlwaysFormAnalyzer(),
        dry_run=True,
        screenshot_dir=screenshot_dir,
    )
    result = await engine.apply(apply_form_url, profile)

    # Dry run never confirms but reports needs_review with DRY_RUN reason
    assert result.status is ApplicationStatus.NEEDS_REVIEW
    assert result.intervention_reason == "DRY_RUN"
    assert result.success is True

    # Screenshot should be on disk
    shots = list(screenshot_dir.glob("*.png"))
    assert len(shots) == 1
    assert shots[0].stat().st_size > 0
