"""Tests for shared option-matching used by the mapper and executor."""

from __future__ import annotations

from hamster.applicator.matching import (
    first_matching_index,
    normalize_option,
    value_matches_option,
)


def test_exact_match_wins() -> None:
    assert first_matching_index("no", ["Yes", "No"]) == 1
    assert first_matching_index("yes", ["Yes", "No"]) == 0


def test_whole_word_fallback_matches_extra_wording() -> None:
    # An option that carries extra text after the answer still matches.
    assert first_matching_index("yes", ["Yes, I agree", "No"]) == 0


def test_substring_does_not_falsely_match_short_value() -> None:
    """'No' must NOT match an option merely containing the letters 'no'.

    Regression for the containment bug: 'No' is a substring of 'know' and
    'None', which previously selected the semantically-opposite option.
    """
    assert (
        first_matching_index(
            "no", ["Yes, I know the role is onsite", "I cannot relocate"]
        )
        is None
    )
    assert first_matching_index("no", ["None of the above"]) is None
    assert first_matching_index("no", ["I do not wish to answer"]) is None


def test_value_matches_option_wrapper() -> None:
    assert value_matches_option("No", ["Yes", "No"]) is True
    assert value_matches_option("I agree to the AI Policy", ["Yes", "No"]) is False
    assert value_matches_option(None, ["Yes", "No"]) is False


def test_normalize_is_case_and_space_insensitive() -> None:
    assert normalize_option("  Yes  ") == "yes"
