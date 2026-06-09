"""Headful dry-run of the apply pipeline against a real Greenhouse posting.

Pulls a live job URL from the Greenhouse public API (so we never hard-code a
URL that might 404), then drives ApplicatorEngine in dry-run mode with a
visible browser: it opens the posting, classifies the page, maps the profile
onto the form, fills what it can, screenshots the filled form, and stops
before clicking submit.

No model is required — without the LLM the FormMapper falls back to its
deterministic field matching (name / email / phone / etc). dry_run=True means
nothing is ever submitted.

Run: .venv/bin/python scripts/dryrun_greenhouse.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from hamster.applicator import ApplicatorEngine
from hamster.applicator.browser import BrowserManager
from hamster.applicator.form_filler import FormMapper, RuleBasedPageAnalyzer
from hamster.applicator.llm import LLMClient, ModelManager
from hamster.backend.dependencies import get_data_dir, get_profile_store
from hamster.job_discovery.sources.greenhouse import GreenhouseSource
from hamster.shared import Education, Experience, JobListing, SearchQuery, UserProfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dryrun")

REPO_ROOT = Path(__file__).resolve().parent.parent
RESUME_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "pat_apply_resume.pdf"
SCREENSHOT_DIR = REPO_ROOT / "data" / "dryrun_screenshots"

# A few large, long-lived Greenhouse boards. We try them in order until one
# returns at least one job, so the demo doesn't depend on any single company
# currently having an open req.
CANDIDATE_COMPANIES = ["anthropic", "stripe", "databricks", "figma", "ramp"]


# The synthetic profile is a software engineer, so bias the demo toward a role
# it can HONESTLY speak to. Applying a SWE persona to a Chief-of-Staff posting
# would only show fields left blank — picking an eng role shows the LLM
# tailoring real skills to the actual role.
_ENG_TITLE_HINTS = ("engineer", "developer", "software", "swe", "backend",
                    "frontend", "full stack", "full-stack", "infrastructure")


def _looks_engineering(title: str) -> bool:
    lowered = title.lower()
    return any(hint in lowered for hint in _ENG_TITLE_HINTS)


async def _find_live_job() -> tuple[str, JobListing] | None:
    """Return (apply_url, JobListing) for a live Greenhouse posting.

    Prefers an engineering role the synthetic SWE profile genuinely fits;
    falls back to the first available job if no eng role is open.
    """
    first_job: JobListing | None = None
    for company in CANDIDATE_COMPANIES:
        source = GreenhouseSource(companies=[company])
        try:
            jobs = await source.list_jobs(SearchQuery())
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to fetch %s: %s", company, error)
            await source.aclose()
            continue
        await source.aclose()
        for job in jobs:
            if first_job is None:
                first_job = job
            if _looks_engineering(job.title):
                return str(job.apply_url or job.url), job
    if first_job is not None:
        return str(first_job.apply_url or first_job.url), first_job
    return None


async def main() -> int:
    # Prefer the real saved profile (the whole point is to see the real data
    # land on the form). Fall back to a synthetic one if none is saved.
    profile = get_profile_store().load_profile()
    if profile is not None:
        logger.info(
            "Using saved profile: %s %s <%s>",
            profile.first_name,
            profile.last_name,
            profile.email,
        )
    else:
        if not RESUME_FIXTURE.exists():
            logger.error("No saved profile and resume fixture missing")
            return 1
        logger.info("No saved profile; using synthetic Pat Apply")
        # Keep these fields in sync with PROFILE in generate_test_resume.py so
        # the persona is consistent across the resume PDF and this demo. The
        # experience/skills are what let the LLM write role-tailored free-text.
        profile = UserProfile(
            first_name="Pat",
            last_name="Apply",
            email="pat.apply@example.com",
            phone="+1-555-0100",
            location="Seattle, WA",
            linkedin_url="https://linkedin.com/in/hamster-test",
            github_url="https://github.com/hamster-test",
            resume_path=str(RESUME_FIXTURE),
            education=[
                Education(
                    school="University of Washington",
                    degree="B.S. Computer Science",
                    major="Computer Science",
                    start_date="2018-09",
                    end_date="2022-06",
                )
            ],
            experience=[
                Experience(
                    company="Hamster Test Co.",
                    title="Software Engineer",
                    description=(
                        "Built fixture data and form-fill regression tests "
                        "across Greenhouse, Lever, Ashby, and Workable boards."
                    ),
                    start_date="2024-06",
                ),
                Experience(
                    company="Example Labs",
                    title="Software Engineer",
                    description=(
                        "Owned a Python + FastAPI service for processing "
                        "resume PDFs; built a headless-browser regression "
                        "harness that cut flaky-test rate from 12% to 3%."
                    ),
                    start_date="2022-08",
                    end_date="2024-05",
                ),
            ],
            skills=[
                "Python",
                "TypeScript",
                "React",
                "FastAPI",
                "Playwright",
                "SQLite",
                "Docker",
                "Pytest",
            ],
        )

    logger.info("Finding a live Greenhouse posting…")
    found = await _find_live_job()
    if found is None:
        logger.error("No live Greenhouse job found across %s", CANDIDATE_COMPANIES)
        return 1
    url, job = found
    logger.info("Target: %s @ %s", job.title, job.company)
    logger.info("URL: %s", url)
    if job.description_snippet:
        logger.info(
            "Job description present (%d chars) — LLM will tailor answers",
            len(job.description_snippet),
        )

    # Wire in the local LLM if the model is present, so open-ended / custom
    # fields and dropdowns (the ones rule-based mapping can't touch) get
    # filled too. One shared client feeds both the page analyzer and the form
    # mapper — the same path the production worker uses.
    manager = ModelManager(data_dir=get_data_dir())
    if manager.is_installed():
        logger.info("LLM model present; wiring it into analyzer + FormMapper")
        llm_client = LLMClient(model_path=manager.model_path)
    else:
        logger.info("No LLM model; rule-based analysis + form mapping only")
        llm_client = None
    page_analyzer = RuleBasedPageAnalyzer(llm_client=llm_client)
    form_mapper = FormMapper(llm_client=llm_client)

    # Headful + slow_mo so the fill is visible to a human watching.
    browser = BrowserManager(
        user_data_dir=REPO_ROOT / "data" / "dryrun_browser_profile",
        headless=False,
        slow_mo_ms=600,
    )
    await browser.launch()

    engine = ApplicatorEngine(
        browser=browser,
        page_analyzer=page_analyzer,
        form_mapper=form_mapper,
        dry_run=True,  # SAFETY: never clicks submit
        wild_mode=False,
        screenshot_dir=SCREENSHOT_DIR,
    )

    try:
        result = await engine.apply(url, profile, job)
    finally:
        # Let the watcher see the final state for a moment before teardown.
        await asyncio.sleep(3)
        await browser.close()

    logger.info("=== DRY-RUN RESULT ===")
    logger.info("status: %s", result.status.value)
    logger.info("success: %s", result.success)
    logger.info("confidence: %.2f", result.confidence)
    logger.info("intervention_reason: %s", result.intervention_reason)
    logger.info("error/notes: %s", result.error)

    shots = sorted(SCREENSHOT_DIR.glob("*.png")) if SCREENSHOT_DIR.exists() else []
    if shots:
        logger.info("screenshot: %s", shots[-1])
    else:
        logger.info("no screenshot captured")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
