"""End-to-end engine test against the local fixture form."""

from __future__ import annotations

from pathlib import Path

from hamster.applicator import ApplicatorEngine
from hamster.applicator.browser import BrowserManager
from hamster.shared import (
    ActionType,
    ApplicationStatus,
    FillPlan,
    JobListing,
    JobSourceName,
    PageAction,
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
        wild_mode=True,  # fixture form has unmapped fields (conf 0.6); wild
        # mode bypasses the submit confidence gate so we reach the click.
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


async def test_engine_blocks_live_submit_below_confidence(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    """Live submit (dry_run=False) must stop for review when mapping
    confidence is below the safety threshold and wild mode is off.

    The fixture form has unmapped fields (experience/cover letter/sponsorship),
    so the rule-based mapper reports confidence 0.6 < 0.8 threshold.
    """
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n%EOF\n")

    profile = UserProfile(
        first_name="Low",
        last_name="Confidence",
        email="low@example.com",
        resume_path=str(resume),
    )

    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=_AlwaysFormAnalyzer(),
        dry_run=False,
        wild_mode=False,
    )
    result = await engine.apply(apply_form_url, profile)

    assert result.status is ApplicationStatus.NEEDS_REVIEW
    assert result.intervention_reason == "BELOW_SUBMIT_THRESHOLD"
    assert result.success is False


async def test_engine_wild_mode_submits_below_confidence(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    """Wild mode bypasses the confidence gate and submits regardless."""
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n%EOF\n")

    profile = UserProfile(
        first_name="Wild",
        last_name="Mode",
        email="wild@example.com",
        resume_path=str(resume),
    )

    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=_AlwaysConfirmedAnalyzer(),
        dry_run=False,
        wild_mode=True,
    )
    result = await engine.apply(apply_form_url, profile)

    # Same as the live-submit test: wild mode reaches the click and the
    # fixture confirms on the next step.
    assert result.status is ApplicationStatus.SUBMITTED
    assert result.success is True


class _DoomedComboboxMapper:
    """Returns a plan whose combobox action can't be executed (bad value),
    so we can verify one failed action doesn't sink the whole application."""

    async def plan(
        self,
        dom: PageDOM,
        profile: UserProfile,
        job: JobListing | None = None,
    ) -> FillPlan:
        return FillPlan(
            actions=[
                PageAction(
                    type=ActionType.FILL, selector="#first-name", value="San"
                ),
                # #relocation exists but 'Atlantis' is not an option -> the
                # executor will raise ActionError for this one action.
                PageAction(
                    type=ActionType.SELECT_COMBOBOX,
                    selector="#relocation",
                    value="Atlantis",
                ),
            ],
            unmapped_fields=[],
            confidence=0.95,
            reasoning="test stub",
        )


async def test_engine_dry_run_surfaces_action_failures(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    """A single failing action is surfaced in execution_failures and does NOT
    mark the whole application FAILED; confidence reflects the plan, not the
    execution outcome."""
    profile = UserProfile(
        first_name="San",
        last_name="Zhang",
        email="san@example.com",
    )

    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=_AlwaysFormAnalyzer(),
        form_mapper=_DoomedComboboxMapper(),
        dry_run=True,
        screenshot_dir=tmp_path / "shots",
    )
    result = await engine.apply(apply_form_url, profile)

    assert result.status is ApplicationStatus.NEEDS_REVIEW
    assert result.intervention_reason == "DRY_RUN"
    assert result.success is True
    # The one bad action is reported, not swallowed; the good fill still ran.
    assert len(result.execution_failures) == 1
    assert "#relocation" in result.execution_failures[0]
    # Confidence is the plan's (0.95), unaffected by the execution failure.
    assert result.confidence == 0.95


class _RecordingMapper:
    """Captures the job argument apply() forwards to plan()."""

    def __init__(self) -> None:
        self.received_job: JobListing | None = None
        self.called = False

    async def plan(
        self,
        dom: PageDOM,
        profile: UserProfile,
        job: JobListing | None = None,
    ) -> FillPlan:
        self.called = True
        self.received_job = job
        return FillPlan(
            actions=[], unmapped_fields=[], confidence=0.95, reasoning="stub"
        )


async def test_engine_forwards_job_to_mapper(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    """apply(url, profile, job) must hand the job to form_mapper.plan."""
    profile = UserProfile(first_name="Pat", last_name="Apply", email="p@example.com")
    job = JobListing(
        id="gh-x-1",
        source=JobSourceName.GREENHOUSE,
        company="Anthropic",
        title="Software Engineer",
        url="https://job-boards.greenhouse.io/anthropic/jobs/1",
    )
    mapper = _RecordingMapper()
    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=_AlwaysFormAnalyzer(),
        form_mapper=mapper,
        dry_run=True,
        screenshot_dir=tmp_path / "shots",
    )
    await engine.apply(apply_form_url, profile, job)
    assert mapper.called is True
    assert mapper.received_job is job


async def test_engine_defaults_job_to_none(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    """Backward compat: apply(url, profile) forwards job=None."""
    profile = UserProfile(first_name="Pat", last_name="Apply", email="p@example.com")
    mapper = _RecordingMapper()
    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=_AlwaysFormAnalyzer(),
        form_mapper=mapper,
        dry_run=True,
        screenshot_dir=tmp_path / "shots",
    )
    await engine.apply(apply_form_url, profile)
    assert mapper.called is True
    assert mapper.received_job is None
