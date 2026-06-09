"""Tests for build_form_mapping_prompt job-context injection + budget."""

from __future__ import annotations

from hamster.applicator.llm import DefaultPromptBuilder
from hamster.shared import (
    Education,
    ElementType,
    Experience,
    JobListing,
    JobSourceName,
    PageDOM,
    PageElement,
    UserProfile,
)


def _dom(element_count: int = 1) -> PageDOM:
    elements = [
        PageElement(
            id=f"el_{index}",
            element_type=ElementType.INPUT_TEXT,
            label=f"Field {index}",
            selector=f"#f{index}",
        )
        for index in range(element_count)
    ]
    return PageDOM(url="https://x/apply", title="Apply", elements=elements)


def _combobox_heavy_dom(element_count: int) -> PageDOM:
    """Realistic worst case: many comboboxes with long labels + option lists,
    the kind of EEO/eligibility form this feature targets."""
    elements = [
        PageElement(
            id=f"el_{index}",
            element_type=ElementType.COMBOBOX,
            label=(
                f"Question {index}: are you authorized to work and willing to "
                "comply with all applicable role requirements as described?"
            ),
            selector=f"#q{index}",
            options=[f"Option {choice}" for choice in range(20)],
        )
        for index in range(element_count)
    ]
    return PageDOM(url="https://x/apply", title="Apply", elements=elements)


def _profile() -> UserProfile:
    return UserProfile(
        first_name="Pat",
        last_name="Apply",
        email="pat@example.com",
        skills=["Python", "FastAPI"],
    )


def _job() -> JobListing:
    return JobListing(
        id="gh-anthropic-1",
        source=JobSourceName.GREENHOUSE,
        company="Anthropic",
        title="Software Engineer, Product",
        url="https://job-boards.greenhouse.io/anthropic/jobs/1",
        description_snippet="Build reliable systems used by millions.",
    )


def test_no_job_omits_context_block() -> None:
    prompt = DefaultPromptBuilder().build_form_mapping_prompt(_dom(), _profile())
    # The phrase "JOB CONTEXT" appears in the rules text; the *block* (the
    # actual Company/Title lines) must be absent without a job.
    assert "Company: " not in prompt
    assert "Anthropic" not in prompt


def test_job_injects_context_block() -> None:
    prompt = DefaultPromptBuilder().build_form_mapping_prompt(
        _dom(), _profile(), _job()
    )
    assert "Company: Anthropic" in prompt
    assert "Title: Software Engineer, Product" in prompt
    assert "Build reliable systems used by millions." in prompt


def test_job_without_description_omits_description_line() -> None:
    job = _job().model_copy(update={"description_snippet": None})
    prompt = DefaultPromptBuilder().build_form_mapping_prompt(
        _dom(), _profile(), job
    )
    assert "Anthropic" in prompt
    assert "Software Engineer, Product" in prompt
    assert "Description:" not in prompt


def test_never_fabricate_rules_preserved_with_job() -> None:
    prompt = DefaultPromptBuilder().build_form_mapping_prompt(
        _dom(), _profile(), _job()
    )
    # The key guardrail substrings must survive the job-context change.
    assert "NEVER FABRICATE" in prompt
    assert "unmapped_fields" in prompt
    assert "transferable-skills" in prompt


def test_quantitative_threshold_guardrail_present() -> None:
    """The prompt must instruct against affirming unmet numeric thresholds
    (e.g. '5+ years') — the live-run fabrication this guardrail addresses."""
    prompt = DefaultPromptBuilder().build_form_mapping_prompt(
        _dom(), _profile(), _job()
    )
    assert "QUANTITATIVE threshold" in prompt
    assert "never affirm" in prompt


def test_prompt_stays_within_token_budget_worst_case() -> None:
    """A 60-field form + full profile + a max-length description must leave
    headroom under the 16384-token context (rough ~3.5 chars/token)."""
    profile = UserProfile(
        first_name="Pat",
        last_name="Apply",
        email="pat@example.com",
        phone="+1-555-0100",
        location="Seattle, WA",
        linkedin_url="https://linkedin.com/in/x",
        github_url="https://github.com/x",
        education=[
            Education(school="UW", degree="B.S. CS", major="CS"),
        ],
        experience=[
            Experience(
                company=f"Co {index}",
                title="Software Engineer",
                description="Built and tested services across the stack. " * 5,
            )
            for index in range(4)
        ],
        skills=[f"skill-{index}" for index in range(20)],
    )
    job = _job().model_copy(update={"description_snippet": "x " * 1000})
    # 100 combobox elements (above the 60 cap) with long labels + 20 options
    # each — the realistic worst case, not 80 bare text inputs.
    prompt = DefaultPromptBuilder().build_form_mapping_prompt(
        _combobox_heavy_dom(element_count=100), profile, job
    )
    estimated_tokens = len(prompt) / 3.5
    assert estimated_tokens < 12000, f"prompt too large: ~{estimated_tokens:.0f} tokens"
