from __future__ import annotations

from hamster.applicator.form_filler import RuleBasedPageAnalyzer
from hamster.applicator.llm import StaticLLMClient
from hamster.shared import ElementType, PageDOM, PageElement, PageType


def _elem(**kw) -> PageElement:
    base = dict(id="el", element_type=ElementType.INPUT_TEXT, selector="#x")
    base.update(kw)
    return PageElement(**base)  # type: ignore[arg-type]


class _RaisingLLMClient:
    """LLM client that always errors, to exercise the degrade-to-UNKNOWN path."""

    async def chat_json(self, prompt: str, schema: dict | None = None) -> dict:
        del prompt, schema
        raise RuntimeError("model unavailable")


async def test_login_detected_from_url() -> None:
    dom = PageDOM(url="https://example.com/login", title="Login")
    analysis = await RuleBasedPageAnalyzer().analyze(dom)
    assert analysis.page_type is PageType.LOGIN


async def test_application_form_with_submit_button() -> None:
    dom = PageDOM(
        url="https://boards.greenhouse.io/stripe/jobs/1/apply",
        title="Apply",
        elements=[
            _elem(id="el_0", element_type=ElementType.INPUT_TEXT, selector="#a"),
            _elem(id="el_1", element_type=ElementType.INPUT_EMAIL, selector="#b"),
            _elem(id="el_2", element_type=ElementType.INPUT_FILE, selector="#c"),
            _elem(
                id="el_3",
                element_type=ElementType.BUTTON,
                selector="button[type=submit]",
                label="Submit Application",
            ),
        ],
    )
    analysis = await RuleBasedPageAnalyzer().analyze(dom)
    assert analysis.page_type is PageType.APPLICATION_FORM


async def test_confirmation_detected_from_title() -> None:
    dom = PageDOM(url="https://x/apply/done", title="Thank you for applying!")
    analysis = await RuleBasedPageAnalyzer().analyze(dom)
    assert analysis.page_type is PageType.CONFIRMATION


async def test_unknown_fallback() -> None:
    dom = PageDOM(url="https://x/something", title="Browse")
    analysis = await RuleBasedPageAnalyzer().analyze(dom)
    assert analysis.page_type is PageType.UNKNOWN


async def test_llm_fallback_classifies_when_rules_cannot() -> None:
    dom = PageDOM(url="https://x/something", title="Browse")
    llm = StaticLLMClient(
        {
            "page_type": "job_detail",
            "confidence": 0.82,
            "reasoning": "single posting with a description",
        }
    )
    analysis = await RuleBasedPageAnalyzer(llm_client=llm).analyze(dom)
    assert analysis.page_type is PageType.JOB_DETAIL
    assert analysis.confidence == 0.82


async def test_llm_failure_degrades_to_unknown() -> None:
    dom = PageDOM(url="https://x/something", title="Browse")
    analysis = await RuleBasedPageAnalyzer(
        llm_client=_RaisingLLMClient()
    ).analyze(dom)
    assert analysis.page_type is PageType.UNKNOWN


async def test_rules_win_without_calling_llm() -> None:
    """A rule-classifiable page must not pay the LLM cost."""
    llm = StaticLLMClient(
        {"page_type": "captcha", "confidence": 1.0, "reasoning": "wrong"}
    )
    dom = PageDOM(url="https://example.com/login", title="Login")
    analysis = await RuleBasedPageAnalyzer(llm_client=llm).analyze(dom)
    assert analysis.page_type is PageType.LOGIN
