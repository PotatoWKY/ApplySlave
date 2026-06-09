from __future__ import annotations

from hamster.applicator.form_filler import FormMapper
from hamster.applicator.llm import StaticLLMClient
from hamster.shared import (
    ActionType,
    ElementType,
    JobListing,
    JobSourceName,
    PageDOM,
    PageElement,
    UserProfile,
)


class _RecordingLLMClient:
    """Captures the prompt it's given, returns a fixed empty-ish plan."""

    def __init__(self) -> None:
        self.prompt: str | None = None

    async def chat_json(self, prompt: str, schema: dict | None = None) -> dict:
        self.prompt = prompt
        return {
            "actions": [],
            "unmapped_fields": [],
            "confidence": 0.5,
            "reasoning": "recorded",
        }


def _profile() -> UserProfile:
    return UserProfile(
        first_name="San",
        last_name="Zhang",
        email="san@example.com",
        phone="+86 13800000000",
        location="Shanghai",
        linkedin_url="https://linkedin.com/in/san",
        github_url="https://github.com/san",
        resume_path="/tmp/resume.pdf",
    )


def _dom() -> PageDOM:
    return PageDOM(
        url="https://x/apply",
        title="Apply",
        elements=[
            PageElement(
                id="el_0",
                element_type=ElementType.INPUT_TEXT,
                label="First Name",
                selector="#first",
                required=True,
            ),
            PageElement(
                id="el_1",
                element_type=ElementType.INPUT_TEXT,
                label="Last Name",
                selector="#last",
                required=True,
            ),
            PageElement(
                id="el_2",
                element_type=ElementType.INPUT_EMAIL,
                label="Email",
                selector="#email",
                required=True,
            ),
            PageElement(
                id="el_3",
                element_type=ElementType.INPUT_TEL,
                label="Phone number",
                selector="#phone",
            ),
            PageElement(
                id="el_4",
                element_type=ElementType.INPUT_FILE,
                label="Upload resume",
                selector="#resume",
            ),
            PageElement(
                id="el_5",
                element_type=ElementType.TEXTAREA,
                label="Why do you want to work here?",
                selector="#why",
            ),
            PageElement(
                id="el_6",
                element_type=ElementType.COMBOBOX,
                label="Are you open to relocation?",
                selector="#relocation",
                required=True,
                options=["Yes", "No"],
            ),
        ],
    )


async def test_deterministic_fills_known_fields() -> None:
    plan = await FormMapper().plan(_dom(), _profile())

    actions_by_selector = {action.selector: action for action in plan.actions}
    assert actions_by_selector["#first"].value == "San"
    assert actions_by_selector["#last"].value == "Zhang"
    assert actions_by_selector["#email"].value == "san@example.com"
    assert actions_by_selector["#phone"].value == "+86 13800000000"

    resume_action = actions_by_selector["#resume"]
    assert resume_action.type is ActionType.UPLOAD
    assert resume_action.value == "/tmp/resume.pdf"

    # Textarea for open-ended question stays unmapped
    assert "Why do you want to work here?" in plan.unmapped_fields


async def test_llm_fallback_fills_unmapped_fields() -> None:
    canned_llm_output = {
        "actions": [
            {
                "type": "fill",
                "selector": "#why",
                "value": "Great mission, strong team.",
            }
        ],
        "unmapped_fields": [],
        "confidence": 0.9,
        "reasoning": "mocked",
    }
    mapper = FormMapper(llm_client=StaticLLMClient(canned_llm_output))
    plan = await mapper.plan(_dom(), _profile())

    values = {action.selector: action.value for action in plan.actions}
    assert values["#why"] == "Great mission, strong team."
    # Deterministic + LLM should combine without duplicating existing selectors
    assert len(plan.actions) == len({a.selector for a in plan.actions})


async def test_merge_confidence_reflects_fill_ratio_not_min() -> None:
    """When the LLM covers every field the rules left, confidence should be
    high — not capped at the rule-base floor (the old min() bug).

    The DOM's only unmapped field is the #why textarea; the LLM fills it, so
    after merge nothing is unmapped and every fillable field has an action.
    """
    canned_llm_output = {
        "actions": [
            {"type": "fill", "selector": "#why", "value": "Great mission."},
            {
                "type": "select_combobox",
                "selector": "#relocation",
                "value": "Yes",
            },
        ],
        "unmapped_fields": [],
        "confidence": 0.95,
        "reasoning": "mocked",
    }
    mapper = FormMapper(llm_client=StaticLLMClient(canned_llm_output))
    plan = await mapper.plan(_dom(), _profile())

    assert not plan.unmapped_fields
    # Every fillable field is covered → confidence is 1.0, well above the old
    # min(0.6, 0.95) = 0.6 that the bug produced.
    assert plan.confidence == 1.0


async def test_combobox_action_type_corrected_from_element() -> None:
    """The LLM may emit the wrong action type for a combobox; the mapper must
    override it from the element's real type, not trust the model.

    Here the LLM (wrongly) emits a native 'select' for a combobox element.
    The merged plan must carry SELECT_COMBOBOX, since #relocation is a
    combobox — otherwise the executor would call select_option on a non-select
    and crash.
    """
    canned_llm_output = {
        "actions": [
            {"type": "select", "selector": "#relocation", "value": "Yes"},
        ],
        "unmapped_fields": [],
        "confidence": 0.9,
        "reasoning": "mocked",
    }
    mapper = FormMapper(llm_client=StaticLLMClient(canned_llm_output))
    plan = await mapper.plan(_dom(), _profile())

    relocation = next(a for a in plan.actions if a.selector == "#relocation")
    assert relocation.type is ActionType.SELECT_COMBOBOX
    assert relocation.value == "Yes"


async def test_merge_confidence_partial_when_fields_remain() -> None:
    """If the LLM leaves a field unmapped, confidence is the fill ratio,
    strictly between 0 and 1 — proving it's computed, not just min()."""
    canned_llm_output = {
        "actions": [],
        "unmapped_fields": ["Why do you want to work here?"],
        "confidence": 0.9,
        "reasoning": "mocked",
    }
    mapper = FormMapper(llm_client=StaticLLMClient(canned_llm_output))
    plan = await mapper.plan(_dom(), _profile())

    # One field still unmapped out of the fillable set → ratio < 1.0
    assert 0.0 < plan.confidence < 1.0


async def test_merge_drops_out_of_range_combobox_value() -> None:
    """An LLM-invented combobox value that isn't a real option is dropped.

    #relocation's options are ['Yes','No']; the LLM hallucinates 'I agree to
    the AI Policy'. That action must not reach the plan (it would crash the
    executor), and the field stays unmapped.
    """
    canned_llm_output = {
        "actions": [
            {
                "type": "select_combobox",
                "selector": "#relocation",
                "value": "I agree to the AI Policy",
            },
        ],
        "unmapped_fields": [],
        "confidence": 0.9,
        "reasoning": "mocked",
    }
    mapper = FormMapper(llm_client=StaticLLMClient(canned_llm_output))
    plan = await mapper.plan(_dom(), _profile())

    assert not any(a.selector == "#relocation" for a in plan.actions)
    assert "Are you open to relocation?" in plan.unmapped_fields


async def test_merge_passes_through_empty_option_combobox() -> None:
    """A combobox whose options failed to harvest is left to the (non-fatal)
    executor and excluded from the confidence denominator.

    With harvest_failed=True and empty options, the validation gate can't
    check the value, so it passes through rather than being silently dropped;
    and the field neither counts as covered nor penalizes confidence.
    """
    dom = PageDOM(
        url="https://x/apply",
        title="Apply",
        elements=[
            PageElement(
                id="el_0",
                element_type=ElementType.INPUT_EMAIL,
                label="Email",
                selector="#email",
                required=True,
            ),
            PageElement(
                id="el_1",
                element_type=ElementType.COMBOBOX,
                label="Unharvestable question",
                selector="#mystery",
                required=True,
                options=[],
                harvest_failed=True,
            ),
        ],
    )
    canned_llm_output = {
        "actions": [
            {
                "type": "select_combobox",
                "selector": "#mystery",
                "value": "Some guess",
            },
        ],
        "unmapped_fields": [],
        "confidence": 0.9,
        "reasoning": "mocked",
    }
    mapper = FormMapper(llm_client=StaticLLMClient(canned_llm_output))
    plan = await mapper.plan(dom, _profile())

    # Value passes through (not dropped) since options are unknown.
    assert any(a.selector == "#mystery" for a in plan.actions)
    # Email is the only field in the confidence denominator; it's covered, so
    # the harvest-failed combobox neither lowers confidence nor is unmapped.
    assert plan.confidence == 1.0
    assert "Unharvestable question" not in plan.unmapped_fields


async def test_free_text_filled_from_profile() -> None:
    """Optional free-text fields get filled from real profile material.

    The mapper itself doesn't synthesize text (the LLM does), but it must keep
    a valid LLM free-text action for an optional textarea and count it as
    covered. Uses a profile with real experience so the value is profile-drawn.
    """
    profile = UserProfile(
        first_name="San",
        last_name="Zhang",
        email="san@example.com",
        resume_path="/tmp/resume.pdf",
        skills=["Python", "FastAPI"],
    )
    dom = PageDOM(
        url="https://x/apply",
        title="Apply",
        elements=[
            PageElement(
                id="el_0",
                element_type=ElementType.INPUT_EMAIL,
                label="Email",
                selector="#email",
                required=True,
            ),
            PageElement(
                id="el_1",
                element_type=ElementType.TEXTAREA,
                label="Additional Information",
                selector="#additional",
            ),
        ],
    )
    canned_llm_output = {
        "actions": [
            {
                "type": "fill",
                "selector": "#additional",
                "value": "I work with Python and FastAPI.",
            },
        ],
        "unmapped_fields": [],
        "confidence": 0.9,
        "reasoning": "mocked",
    }
    mapper = FormMapper(llm_client=StaticLLMClient(canned_llm_output))
    plan = await mapper.plan(dom, profile)

    additional = next(a for a in plan.actions if a.selector == "#additional")
    assert "Python" in additional.value
    assert "Additional Information" not in plan.unmapped_fields


async def test_job_context_reaches_the_llm_prompt() -> None:
    """A JobListing passed to plan() must appear in the LLM prompt."""
    recorder = _RecordingLLMClient()
    dom = PageDOM(
        url="https://x/apply",
        title="Apply",
        elements=[
            PageElement(
                id="el_0",
                element_type=ElementType.TEXTAREA,
                label="Why do you want this role?",
                selector="#why",
            ),
        ],
    )
    job = JobListing(
        id="gh-anthropic-1",
        source=JobSourceName.GREENHOUSE,
        company="Anthropic",
        title="Software Engineer, Product",
        url="https://job-boards.greenhouse.io/anthropic/jobs/1",
        description_snippet="Build reliable systems.",
    )
    mapper = FormMapper(llm_client=recorder)
    await mapper.plan(dom, _profile(), job)

    assert recorder.prompt is not None
    assert "Anthropic" in recorder.prompt
    assert "Software Engineer, Product" in recorder.prompt
    assert "Build reliable systems." in recorder.prompt


async def test_no_job_keeps_prompt_role_free() -> None:
    """Backward compat: without a job, no role context leaks into the prompt."""
    recorder = _RecordingLLMClient()
    dom = PageDOM(
        url="https://x/apply",
        title="Apply",
        elements=[
            PageElement(
                id="el_0",
                element_type=ElementType.TEXTAREA,
                label="Why do you want this role?",
                selector="#why",
            ),
        ],
    )
    mapper = FormMapper(llm_client=recorder)
    await mapper.plan(dom, _profile())

    assert recorder.prompt is not None
    # The rules text mentions JOB CONTEXT; the actual block (Company: line)
    # must be absent when no job is passed.
    assert "Company: " not in recorder.prompt
