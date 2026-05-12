"""Round-trip and validation tests for shared models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from applyslave.shared import (
    ApplicationRecord,
    ApplicationStatus,
    Education,
    Experience,
    JobListing,
    JobSourceName,
    PageDOM,
    PageElement,
    ElementType,
    SearchQuery,
    UserProfile,
)


def test_user_profile_minimum_required_fields() -> None:
    profile = UserProfile(first_name="San", last_name="Zhang", email="san@example.com")
    assert profile.first_name == "San"
    assert profile.education == []
    assert profile.skills == []


def test_user_profile_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        UserProfile(
            first_name="San",
            last_name="Zhang",
            email="san@example.com",
            bogus_field="oops",  # type: ignore[call-arg]
        )


def test_user_profile_round_trip_json() -> None:
    original = UserProfile(
        first_name="San",
        last_name="Zhang",
        email="san@example.com",
        education=[Education(school="XX Univ", degree="BS", major="CS")],
        experience=[Experience(company="XX Corp", title="Engineer")],
        skills=["Python", "TypeScript"],
    )
    dumped = original.model_dump_json()
    restored = UserProfile.model_validate_json(dumped)
    assert restored == original


def test_job_listing_source_is_enum() -> None:
    listing = JobListing(
        id="gh-1",
        source=JobSourceName.GREENHOUSE,
        company="Stripe",
        title="SWE",
        url="https://boards.greenhouse.io/stripe/jobs/1",
    )
    assert listing.source is JobSourceName.GREENHOUSE


def test_search_query_defaults_are_independent() -> None:
    one = SearchQuery(keywords="engineer")
    two = SearchQuery(keywords="pm")
    one.exclude_companies.append("Oracle")
    assert two.exclude_companies == []


def test_application_record_status_enum() -> None:
    record = ApplicationRecord(
        url="https://example.com/apply",
        company="Example",
        title="SWE",
    )
    assert record.status is ApplicationStatus.QUEUED


def test_page_dom_element_type_is_enum() -> None:
    dom = PageDOM(
        url="https://example.com",
        title="Apply",
        elements=[
            PageElement(
                id="el_1",
                element_type=ElementType.INPUT_EMAIL,
                selector="#email",
            )
        ],
    )
    assert dom.elements[0].element_type is ElementType.INPUT_EMAIL
