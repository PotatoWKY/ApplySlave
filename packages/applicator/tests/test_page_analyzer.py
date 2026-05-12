from __future__ import annotations

from applyslave.applicator.form_filler import RuleBasedPageAnalyzer
from applyslave.shared import ElementType, PageDOM, PageElement, PageType


def _elem(**kw) -> PageElement:
    base = dict(id="el", element_type=ElementType.INPUT_TEXT, selector="#x")
    base.update(kw)
    return PageElement(**base)  # type: ignore[arg-type]


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
