"""ActionExecutor tests against the fixture apply form."""

from __future__ import annotations

from pathlib import Path

import pytest

from applyslave.applicator.browser import (
    ActionError,
    ActionExecutor,
    BrowserManager,
)
from applyslave.shared import ActionType, PageAction


async def test_fill_and_submit(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    resume_file = tmp_path / "resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4\n%EOF\n")

    actions = [
        PageAction(type=ActionType.FILL, selector="#first-name", value="San"),
        PageAction(type=ActionType.FILL, selector="#last-name", value="Zhang"),
        PageAction(type=ActionType.FILL, selector="#email", value="san@example.com"),
        PageAction(type=ActionType.SELECT, selector="#experience", value="3-5 years"),
        PageAction(
            type=ActionType.FILL,
            selector="#cover-letter",
            value="I am excited to apply.",
        ),
        PageAction(
            type=ActionType.UPLOAD,
            selector="#resume",
            value=str(resume_file),
        ),
        PageAction(type=ActionType.CHECK, selector="#sponsorship"),
    ]

    executor = ActionExecutor()
    await executor.run_plan(page, actions)

    # Verify DOM state reflects the actions
    assert await page.input_value("#first-name") == "San"
    assert await page.input_value("#email") == "san@example.com"
    assert await page.input_value("#experience") == "3-5"
    assert await page.input_value("#cover-letter") == "I am excited to apply."
    assert await page.is_checked("#sponsorship")


async def test_missing_upload_source_raises(
    browser: BrowserManager, apply_form_url: str, tmp_path: Path
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    missing_path = tmp_path / "nope.pdf"
    with pytest.raises(ActionError):
        await executor.execute(
            page,
            PageAction(
                type=ActionType.UPLOAD,
                selector="#resume",
                value=str(missing_path),
            ),
        )


async def test_select_missing_value_raises(
    browser: BrowserManager, apply_form_url: str
) -> None:
    page = await browser.new_page()
    await page.goto(apply_form_url)

    executor = ActionExecutor()
    with pytest.raises(ActionError):
        await executor.execute(
            page,
            PageAction(type=ActionType.SELECT, selector="#experience"),
        )
