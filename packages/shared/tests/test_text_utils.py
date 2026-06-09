"""Tests for clean_job_description (ATS description -> capped plain text)."""

from __future__ import annotations

from hamster.shared.text_utils import clean_job_description


def test_none_and_empty_return_none() -> None:
    assert clean_job_description(None) is None
    assert clean_job_description("") is None
    assert clean_job_description("   \n\t  ") is None


def test_unescapes_entities_and_strips_tags() -> None:
    raw = "&lt;div&gt;&lt;h2&gt;About&lt;/h2&gt;&lt;p&gt;Build services&lt;/p&gt;&lt;/div&gt;"
    assert clean_job_description(raw) == "About Build services"


def test_handles_nested_and_unclosed_tags() -> None:
    raw = "&lt;div&gt;&lt;b&gt;Bold&lt;/b&gt; and &lt;i&gt;broken"
    assert clean_job_description(raw) == "Bold and broken"


def test_drops_script_and_style_bodies() -> None:
    raw = "&lt;script&gt;steal()&lt;/script&gt;Real text"
    cleaned = clean_job_description(raw)
    assert cleaned == "Real text"
    assert "steal" not in cleaned


def test_collapses_whitespace() -> None:
    raw = "Line one\n\n\n   Line   two\t\tend"
    assert clean_job_description(raw) == "Line one Line two end"


def test_truncates_at_word_boundary_with_ellipsis() -> None:
    raw = "word " * 100  # 500 chars
    cleaned = clean_job_description(raw, max_chars=20)
    assert len(cleaned) <= 22  # 20 + " …"
    assert cleaned.endswith("…")
    # No partial word before the ellipsis.
    assert "wor…" not in cleaned


def test_single_long_token_is_hard_cut() -> None:
    raw = "x" * 100
    cleaned = clean_job_description(raw, max_chars=10)
    # Must make progress (not empty, not the whole string).
    assert cleaned is not None
    assert len(cleaned) <= 12


def test_realistic_blob_caps_to_max() -> None:
    # ~10KB of escaped HTML like Greenhouse returns.
    body = "&lt;p&gt;We are hiring engineers to build reliable systems.&lt;/p&gt;"
    raw = body * 200
    cleaned = clean_job_description(raw, max_chars=2000)
    assert cleaned is not None
    assert len(cleaned) <= 2002
    assert "<" not in cleaned and "&lt;" not in cleaned
