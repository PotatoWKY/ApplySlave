"""Relevance scoring for job listings against a user profile.

This is intentionally NOT LLM-based — it runs in microseconds per job using
keyword overlap and heuristic weighting. The LLM is too slow (~90s/call) to
score 50+ results interactively.

Scoring dimensions (0-100 total):
  - Title match (0-40): how well the job title matches the user's experience titles
  - Skills overlap (0-35): fraction of user skills mentioned in the job description
  - Location match (0-15): exact city/state match
  - Recency bonus (0-10): posted within last 7 days
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from applyslave.shared import JobListing, UserProfile


def score_job(job: JobListing, profile: UserProfile) -> int:
    """Return a relevance score 0-100 for a job relative to the user's profile."""
    total = 0.0
    total += _title_score(job, profile)
    total += _skills_score(job, profile)
    total += _location_score(job, profile)
    total += _recency_score(job)
    return min(100, max(0, round(total)))


def score_jobs(
    jobs: list[JobListing], profile: UserProfile
) -> list[tuple[JobListing, int]]:
    """Score all jobs and return (job, score) pairs sorted by score descending."""
    scored = [(job, score_job(job, profile)) for job in jobs]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def _title_score(job: JobListing, profile: UserProfile) -> float:
    """How well the job title matches the user's past titles (0-40)."""
    job_title_lower = job.title.lower()
    if not profile.experience:
        return 10.0

    best_match = 0.0
    for experience in profile.experience:
        exp_title_lower = experience.title.lower()
        exp_words = set(exp_title_lower.split())
        job_words = set(job_title_lower.split())

        if exp_words and job_words:
            overlap = len(exp_words & job_words)
            union = len(exp_words | job_words)
            jaccard = overlap / union if union > 0 else 0
            best_match = max(best_match, jaccard)

        if exp_title_lower in job_title_lower or job_title_lower in exp_title_lower:
            best_match = max(best_match, 0.9)

    return best_match * 40.0


def _skills_score(job: JobListing, profile: UserProfile) -> float:
    """Fraction of user skills mentioned in the job description/title (0-35)."""
    if not profile.skills:
        return 10.0

    searchable = (job.title + " " + (job.description_snippet or "")).lower()
    matched = sum(
        1 for skill in profile.skills if skill.lower() in searchable
    )
    fraction = matched / len(profile.skills)
    return fraction * 35.0


def _location_score(job: JobListing, profile: UserProfile) -> float:
    """Location match bonus (0-15)."""
    if not profile.location or not job.location:
        return 5.0

    profile_loc_lower = profile.location.lower()
    job_loc_lower = job.location.lower()

    profile_parts = {
        part.strip() for part in profile_loc_lower.replace(",", " ").split()
    }
    job_parts = {
        part.strip() for part in job_loc_lower.replace(",", " ").split()
    }

    if profile_parts & job_parts:
        return 15.0
    if job.remote:
        return 10.0
    return 0.0


def _recency_score(job: JobListing) -> float:
    """Bonus for recently posted jobs (0-10)."""
    if not job.posted_at:
        return 3.0

    now = datetime.now(tz=UTC)
    posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=UTC)
    age = now - posted

    if age < timedelta(days=1):
        return 10.0
    if age < timedelta(days=3):
        return 8.0
    if age < timedelta(days=7):
        return 5.0
    if age < timedelta(days=14):
        return 2.0
    return 0.0
