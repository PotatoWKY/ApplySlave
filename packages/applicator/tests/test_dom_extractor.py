"""DOMExtractor tests using a local HTML fixture."""

from __future__ import annotations

from hamster.applicator.browser import BrowserManager, DOMExtractor
from hamster.shared import ElementType


async def test_extract_finds_all_form_fields(
    browser: BrowserManager, apply_form_url: str
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    extractor = DOMExtractor()
    dom = await extractor.extract(page)

    assert dom.title == "Test Application Form"

    by_label = {el.label: el for el in dom.elements if el.label}

    first_name = by_label["First Name"]
    assert first_name.element_type is ElementType.INPUT_TEXT
    assert first_name.required is True

    email = by_label["Email"]
    assert email.element_type is ElementType.INPUT_EMAIL

    phone = by_label["Phone"]
    assert phone.element_type is ElementType.INPUT_TEL

    experience = by_label["Years of experience"]
    assert experience.element_type is ElementType.SELECT
    assert set(experience.options) >= {"0-1 years", "1-3 years", "3-5 years"}

    cover = by_label["Cover letter"]
    assert cover.element_type is ElementType.TEXTAREA

    resume = by_label["Upload resume"]
    assert resume.element_type is ElementType.INPUT_FILE

    # The checkbox label wraps the input so the label text includes both
    # the input and the visible description.
    sponsorship = next(
        el for el in dom.elements if el.element_type is ElementType.INPUT_CHECKBOX
    )
    assert "sponsorship" in (sponsorship.label or "").lower()

    submit = next(
        el for el in dom.elements if el.element_type is ElementType.BUTTON
    )
    assert "submit" in (submit.label or "").lower()
