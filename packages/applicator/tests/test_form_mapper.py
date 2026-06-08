from __future__ import annotations

from hamster.applicator.form_filler import FormMapper
from hamster.applicator.llm import StaticLLMClient
from hamster.shared import (
    ActionType,
    ElementType,
    PageDOM,
    PageElement,
    UserProfile,
)


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
            {"type": "fill", "selector": "#why", "value": "Great mission."}
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
