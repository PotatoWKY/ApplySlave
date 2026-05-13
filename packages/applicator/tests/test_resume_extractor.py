"""Unit tests for ResumeExtractor using a mocked LLM client."""

from __future__ import annotations

import pytest

from applyslave.applicator.llm import ResumeExtractor, StaticLLMClient
from applyslave.shared import UserProfile


def _llm_response() -> dict:
    return {
        "first_name": "San",
        "last_name": "Zhang",
        "email": "san@example.com",
        "phone": "+86-138-0000-0000",
        "location": "Shanghai",
        "linkedin_url": "https://linkedin.com/in/sanzhang",
        "github_url": "https://github.com/sanzhang",
        "education": [
            {
                "school": "XX University",
                "degree": "BS",
                "major": "Computer Science",
                "start_date": "2018-09",
                "end_date": "2022-06",
            }
        ],
        "experience": [
            {
                "company": "XX Corp",
                "title": "Software Engineer",
                "description": "Built ATS integrations, Playwright pipelines.",
                "start_date": "2022-07",
                "end_date": None,
            },
            {
                "company": "YY LLC",
                "title": "Intern",
                "description": None,
                "start_date": "2021-06",
                "end_date": "2021-09",
            },
        ],
        "skills": ["Python", "TypeScript", "Playwright", "FastAPI"],
    }


async def test_extract_builds_structured_profile() -> None:
    extractor = ResumeExtractor(llm_client=StaticLLMClient(_llm_response()))
    profile = await extractor.extract(resume_text="...")

    assert profile.first_name == "San"
    assert profile.email == "san@example.com"
    assert len(profile.experience) == 2
    assert profile.experience[0].end_date is None  # ongoing
    assert profile.skills == ["Python", "TypeScript", "Playwright", "FastAPI"]


async def test_extract_backfills_from_regex_fallback() -> None:
    """When the LLM omits fields, fallback values fill them in."""
    partial = dict(_llm_response())
    partial["phone"] = None
    partial["linkedin_url"] = None
    extractor = ResumeExtractor(llm_client=StaticLLMClient(partial))

    fallback = UserProfile(
        first_name="",
        last_name="",
        email="fallback@example.com",
        phone="+86-999-9999-9999",
        linkedin_url="https://linkedin.com/in/fromregex",
    )

    profile = await extractor.extract(resume_text="...", fallback=fallback)
    # LLM-provided values win
    assert profile.email == "san@example.com"
    # Fallback kicks in for fields the LLM dropped
    assert profile.phone == "+86-999-9999-9999"
    assert profile.linkedin_url == "https://linkedin.com/in/fromregex"


async def test_extract_drops_incomplete_list_items() -> None:
    """Entries missing required sub-fields are filtered, not crashy."""
    junk = dict(_llm_response())
    junk["education"] = [
        {"school": "Good U", "degree": "BS"},
        {"degree": "MS"},  # missing school -> dropped
        {},  # dropped
    ]
    junk["experience"] = [
        {"company": "Has Both", "title": "SWE"},
        {"title": "Solo"},  # missing company -> dropped
    ]

    extractor = ResumeExtractor(llm_client=StaticLLMClient(junk))
    profile = await extractor.extract(resume_text="...")

    assert len(profile.education) == 1
    assert profile.education[0].school == "Good U"
    assert len(profile.experience) == 1
    assert profile.experience[0].company == "Has Both"


async def test_extract_tolerates_extra_fields() -> None:
    """Extra fields the LLM hallucinates are ignored, not a crash."""
    extra = dict(_llm_response())
    extra["hobbies"] = ["piano", "go"]
    extra["education"][0]["gpa"] = "3.9"

    extractor = ResumeExtractor(llm_client=StaticLLMClient(extra))
    profile = await extractor.extract(resume_text="...")

    assert profile.first_name == "San"
    assert len(profile.education) == 1


async def test_extract_fails_cleanly_on_empty_resume() -> None:
    """Very short input still produces a UserProfile (empty-ish)."""
    barren_response = {
        "first_name": "",
        "last_name": "",
        "email": "placeholder@example.com",
        "education": [],
        "experience": [],
        "skills": [],
    }
    extractor = ResumeExtractor(llm_client=StaticLLMClient(barren_response))
    profile = await extractor.extract(resume_text="")
    assert profile.email == "placeholder@example.com"
    assert profile.education == []
    assert profile.experience == []
