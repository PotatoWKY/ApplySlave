"""Seniority-level recommender — pure Python rules.

We tried using the LLM for this and it kept getting basic arithmetic and
rule application wrong. The task is small enough that hand-written rules
beat a 4B-class LLM on accuracy, and they run in microseconds instead of
~90 seconds.

The classifier is exposed under the same `LevelRecommender` name so the
rest of the system doesn't care.

Rules:
  1. Compute effective years = sum of full-time roles + degree bonus.
     Master's adds +1, PhD adds +3, internships don't count.
  2. Map years to a primary level:
       0-2 -> entry, 2-5 -> mid, 5-8 -> senior, 8+ -> lead
     No full-time roles -> intern.
  3. Title overrides:
       "Staff", "Principal", "Director", "Lead Engineer" -> bump UP one
       "Intern" only history -> primary = intern
  4. Recommended = primary + level immediately below
     Stretch     = level immediately above primary
     Off-target  = the rest
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from hamster.shared import LLMClient, UserProfile

logger = logging.getLogger(__name__)


VALID_LEVELS = ["intern", "entry", "mid", "senior", "lead"]
_LEVEL_ORDER = {level: index for index, level in enumerate(VALID_LEVELS)}


@dataclass
class LevelRecommendation:
    recommended: list[str]
    stretch: list[str]
    off_target: list[str]
    reasoning: str


@dataclass
class LevelRecommender:
    """Rules-based level classifier.

    Takes an `LLMClient` arg for API symmetry with the rest of the system,
    but doesn't use it. Kept as part of the constructor so swapping in a
    real LLM-based implementation later is a single-file change.
    """

    llm_client: LLMClient | None = None

    async def recommend(self, profile: UserProfile) -> LevelRecommendation:
        return _classify(profile)


def _classify(profile: UserProfile) -> LevelRecommendation:
    effective_years = _compute_effective_years(profile)
    role_count = _count_full_time_roles(profile)
    recent_title = _most_recent_title(profile) or ""
    bumped_reason: str | None = None

    if role_count == 0:
        primary = "intern"
        years_note = "no full-time experience"
    else:
        primary = _years_to_level(effective_years)
        years_note = f"{effective_years:.1f} effective years"

        # Title overrides — only bump up for senior-track titles.
        if _has_lead_title(recent_title):
            new_primary = _bump_up(primary)
            if new_primary != primary:
                bumped_reason = (
                    f"title '{recent_title}' implies higher seniority"
                )
                primary = new_primary

    recommended = [primary]
    below = _bump_down(primary)
    if below != primary:
        recommended = [below, primary]

    stretch_level = _bump_up(primary)
    stretch = [stretch_level] if stretch_level != primary else []

    off_target = [
        level
        for level in VALID_LEVELS
        if level not in recommended and level not in stretch
    ]

    reasoning_parts = [f"primary = {primary} ({years_note})"]
    if bumped_reason:
        reasoning_parts.append(f"bumped up: {bumped_reason}")
    reasoning = "; ".join(reasoning_parts)

    return LevelRecommendation(
        recommended=recommended,
        stretch=stretch,
        off_target=off_target,
        reasoning=reasoning,
    )


def _years_to_level(years: float) -> str:
    if years < 2:
        return "entry"
    if years < 5:
        return "mid"
    if years < 8:
        return "senior"
    return "lead"


def _bump_up(level: str) -> str:
    index = _LEVEL_ORDER[level]
    return VALID_LEVELS[min(index + 1, len(VALID_LEVELS) - 1)]


def _bump_down(level: str) -> str:
    index = _LEVEL_ORDER[level]
    return VALID_LEVELS[max(index - 1, 0)]


def _has_lead_title(title: str) -> bool:
    title_lower = title.lower()
    return any(
        keyword in title_lower
        for keyword in (
            "staff ",
            "staff,",
            "principal",
            "director",
            "lead engineer",
            "head of",
            "vp ",
            "vice president",
        )
    )


def _compute_effective_years(profile: UserProfile) -> float:
    """Sum of (end - start) for full-time, non-internship roles.

    Education does NOT add to effective years. Most employers count
    work experience and degree separately — a JD asking for "3 years
    experience" means 3 years of work, not 2 years + a master's.
    Education affects level via the new-grad rule below, not by year math.
    """
    total_months = 0
    for exp in profile.experience:
        if _looks_like_internship(exp.title):
            continue
        start = _parse_yyyy_mm(exp.start_date)
        end = _parse_yyyy_mm(exp.end_date) or date.today()
        if start and end > start:
            months = (end.year - start.year) * 12 + (end.month - start.month)
            total_months += max(0, months)

    return total_months / 12


def _count_full_time_roles(profile: UserProfile) -> int:
    return sum(
        1
        for exp in profile.experience
        if not _looks_like_internship(exp.title)
    )


def _most_recent_title(profile: UserProfile) -> str | None:
    if not profile.experience:
        return None
    sorted_exp = sorted(
        profile.experience,
        key=lambda exp: exp.start_date or "",
        reverse=True,
    )
    return sorted_exp[0].title if sorted_exp else None


def _looks_like_internship(title: str) -> bool:
    title_lower = title.lower()
    return "intern" in title_lower or "co-op" in title_lower or "coop" in title_lower


def _parse_yyyy_mm(value: str | None) -> date | None:
    if not value:
        return None
    parts = value.strip().split("-")
    try:
        if len(parts) >= 2:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 1:
            return date(int(parts[0]), 1, 1)
    except (ValueError, IndexError):
        return None
    return None
