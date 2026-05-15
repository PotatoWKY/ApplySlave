"""Profile CRUD + resume upload."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from applyslave.applicator.llm import (
    LLMClient,
    LevelRecommender,
    ModelManager,
    ResumeExtractor,
    VALID_LEVELS,
)
from applyslave.backend.dependencies import (
    get_data_dir,
    get_profile_store,
    load_settings,
    save_settings,
)
from applyslave.profile_store import (
    ParsedResume,
    ProfileStore,
    extract_text,
    parse_resume,
)
from applyslave.shared import UserProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profile", tags=["profile"])


async def _get_llm_client_or_none() -> LLMClient | None:
    """Return a loaded LLM client if the model is installed, else None.

    Cached module-global so the model stays loaded across requests. The
    first upload still pays ~30s for Metal shader compilation; subsequent
    uploads in the same backend session return in ~90s (inference time).

    If the model was deleted (cache set to None by the delete endpoint),
    we re-check disk before trying to recreate the client.
    """
    global _CACHED_LLM_CLIENT  # noqa: PLW0603

    if _CACHED_LLM_CLIENT is not None:
        # Verify the model file still exists (could have been deleted
        # between requests). If gone, drop the stale cache.
        manager = ModelManager(data_dir=get_data_dir())
        if not manager.is_installed():
            _CACHED_LLM_CLIENT = None
            return None
        return _CACHED_LLM_CLIENT

    manager = ModelManager(data_dir=get_data_dir())
    if not manager.is_installed():
        return None

    # Lazy import so we only pay the llama-cpp import cost when really used
    from applyslave.applicator.llm import LLMClient as LocalLLMClient

    _CACHED_LLM_CLIENT = LocalLLMClient(model_path=manager.model_path)
    return _CACHED_LLM_CLIENT


_CACHED_LLM_CLIENT: LLMClient | None = None


@router.get("", response_model=UserProfile | None)
async def read_profile(
    store: Annotated[ProfileStore, Depends(get_profile_store)],
) -> UserProfile | None:
    return store.load_profile()


@router.get("/suggested-searches")
async def suggested_searches(
    store: Annotated[ProfileStore, Depends(get_profile_store)],
) -> dict:
    """Generate search keyword suggestions based on the user's profile.

    Uses simple heuristics (not LLM) to extract job titles from experience
    and common role variants. Fast enough to call on page load.
    """
    profile = store.load_profile()
    if not profile or not profile.experience:
        return {"suggestions": ["software engineer", "developer", "analyst"]}

    suggestions: list[str] = []
    seen: set[str] = set()

    for experience in profile.experience:
        title = experience.title.strip()
        if title and title.lower() not in seen:
            suggestions.append(title)
            seen.add(title.lower())

    # Add common variants based on the most recent title
    if suggestions:
        recent = suggestions[0].lower()
        variants = _generate_variants(recent)
        for variant in variants:
            if variant.lower() not in seen:
                suggestions.append(variant)
                seen.add(variant.lower())

    return {"suggestions": suggestions[:8]}


def _generate_variants(title: str) -> list[str]:
    """Generate common search variants from a job title."""
    variants: list[str] = []
    title_lower = title.lower()

    # Level variants
    for prefix in ("senior ", "sr. ", "sr ", "junior ", "jr. ", "jr ", "lead ", "staff ", "principal "):
        if title_lower.startswith(prefix):
            base = title[len(prefix):]
            variants.append(base)
            break
    else:
        variants.append(f"Senior {title}")

    # Domain variants
    if "full stack" in title_lower or "fullstack" in title_lower:
        variants.extend(["Backend Developer", "Frontend Developer"])
    elif "backend" in title_lower:
        variants.append("Full Stack Developer")
    elif "frontend" in title_lower or "front-end" in title_lower:
        variants.append("Full Stack Developer")
    elif "software" in title_lower and "engineer" in title_lower:
        variants.extend(["Backend Engineer", "Full Stack Engineer"])

    return variants


@router.get("/recommended-levels")
async def recommended_levels(
    store: Annotated[ProfileStore, Depends(get_profile_store)],
) -> dict:
    """Use the local LLM to classify which seniority levels the user qualifies for.

    Cached in settings.json keyed by a profile fingerprint, so we only re-run
    the LLM (~90s on M3) when the profile actually changes.
    """
    profile = store.load_profile()
    if not profile or not profile.experience:
        return {
            "recommended": ["entry", "mid"],
            "stretch": ["senior"],
            "off_target": ["intern", "lead"],
            "reasoning": "No experience on file; defaulting to entry/mid.",
            "from_cache": False,
            "llm_used": False,
        }

    fingerprint = _profile_fingerprint(profile)
    cached = _load_cached_levels(fingerprint)
    if cached is not None:
        return {**cached, "from_cache": True, "llm_used": True}

    llm_client = await _get_llm_client_or_none()
    if llm_client is None:
        return _heuristic_levels(profile, "Model not installed; using heuristic.")

    try:
        recommender = LevelRecommender(llm_client=llm_client)
        result = await recommender.recommend(profile)
        payload = {
            "recommended": result.recommended,
            "stretch": result.stretch,
            "off_target": result.off_target,
            "reasoning": result.reasoning,
        }
        _save_cached_levels(fingerprint, payload)
        return {**payload, "from_cache": False, "llm_used": True}
    except Exception as error:  # noqa: BLE001
        logger.exception("Level recommendation failed; using heuristic")
        return _heuristic_levels(profile, f"LLM failed: {error}")


def _profile_fingerprint(profile: UserProfile) -> str:
    """A short hash of the parts of the profile that affect level recommendation."""
    import hashlib

    payload = {
        "experience": [
            (exp.title, exp.start_date, exp.end_date) for exp in profile.experience
        ],
        "education": [
            (edu.degree, edu.end_date) for edu in profile.education
        ],
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


def _load_cached_levels(fingerprint: str) -> dict | None:
    settings = load_settings()
    cache = settings.get("level_recommendation_cache") or {}
    if not isinstance(cache, dict):
        return None
    if cache.get("fingerprint") == fingerprint:
        result = cache.get("result")
        if isinstance(result, dict):
            return result
    return None


def _save_cached_levels(fingerprint: str, payload: dict) -> None:
    settings = load_settings()
    settings["level_recommendation_cache"] = {
        "fingerprint": fingerprint,
        "result": payload,
    }
    save_settings(settings)


def _heuristic_levels(profile: UserProfile, reason: str) -> dict:
    """Fallback when the LLM can't run. Counts years of experience."""
    total_years = _estimate_years(profile)

    if total_years < 1:
        recommended = ["intern", "entry"]
        stretch = ["mid"]
    elif total_years < 3:
        recommended = ["entry", "mid"]
        stretch = ["senior"]
    elif total_years < 6:
        recommended = ["mid", "senior"]
        stretch = ["lead"]
    else:
        recommended = ["senior", "lead"]
        stretch = ["mid"]

    off_target = [level for level in VALID_LEVELS if level not in recommended and level not in stretch]
    return {
        "recommended": recommended,
        "stretch": stretch,
        "off_target": off_target,
        "reasoning": f"{reason} (~{total_years:.1f} years experience)",
        "from_cache": False,
        "llm_used": False,
    }


def _estimate_years(profile: UserProfile) -> float:
    """Crude experience-years estimate from start_date/end_date strings."""
    from datetime import date

    total_months = 0
    for exp in profile.experience:
        start = _parse_yyyy_mm(exp.start_date)
        end = _parse_yyyy_mm(exp.end_date) or date.today()
        if start and end > start:
            months = (end.year - start.year) * 12 + (end.month - start.month)
            total_months += max(0, months)
    return total_months / 12


def _parse_yyyy_mm(value: str | None):
    from datetime import date

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


@router.post("", response_model=UserProfile)
async def save_profile(
    profile: UserProfile,
    store: Annotated[ProfileStore, Depends(get_profile_store)],
) -> UserProfile:
    return store.save_profile(profile)


@router.post("/resume", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile,
    store: Annotated[ProfileStore, Depends(get_profile_store)],
) -> dict:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Only PDF resumes are supported")

    suffix = Path(file.filename or "resume.pdf").suffix or ".pdf"
    if suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="File extension must be .pdf")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        stored_path = store.save_resume_file(tmp_path)
        regex_parsed = parse_resume(stored_path)

        # Try the LLM path; fall back to regex-only if the model isn't
        # installed yet (first-run flow before model download).
        llm_client = await _get_llm_client_or_none()
        llm_used = False
        llm_error: str | None = None
        if llm_client is not None:
            try:
                resume_text = extract_text(stored_path)
                logger.info(
                    "Running LLM extraction on resume (%d chars)",
                    len(resume_text),
                )
                regex_profile = _regex_to_profile(regex_parsed, stored_path)
                extractor = ResumeExtractor(llm_client=llm_client)
                extracted = await extractor.extract(
                    resume_text=resume_text,
                    fallback=regex_profile,
                )
                extracted = extracted.model_copy(
                    update={"resume_path": str(stored_path)}
                )
                store.save_profile(extracted)
                llm_used = True
                logger.info("LLM extraction succeeded")
                return {
                    "path": str(stored_path),
                    "llm_used": True,
                    "profile": extracted.model_dump(mode="json"),
                    "parsed_fields": _regex_report(regex_parsed),
                }
            except Exception as error:  # noqa: BLE001
                logger.exception("LLM extraction failed, falling back to regex")
                llm_error = f"{type(error).__name__}: {error}"

        # LLM unavailable or crashed → regex-only path
        _merge_regex_into_store(store, regex_parsed, str(stored_path))
        current = store.load_profile()
        return {
            "path": str(stored_path),
            "llm_used": llm_used,
            "llm_error": llm_error,
            "profile": current.model_dump(mode="json") if current else None,
            "parsed_fields": _regex_report(regex_parsed),
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def _regex_report(parsed: ParsedResume) -> dict:
    return {
        "detected_first_name": parsed.first_name,
        "detected_last_name": parsed.last_name,
        "detected_email": parsed.email,
        "detected_phone": parsed.phone,
        "detected_linkedin_url": parsed.linkedin_url,
        "detected_github_url": parsed.github_url,
    }


def _regex_to_profile(parsed: ParsedResume, resume_path: Path) -> UserProfile:
    """Build a minimal UserProfile from the regex parse for LLM fallback."""
    return UserProfile(
        first_name=parsed.first_name or "",
        last_name=parsed.last_name or "",
        email=parsed.email or "",
        phone=parsed.phone,
        linkedin_url=parsed.linkedin_url,
        github_url=parsed.github_url,
        resume_path=str(resume_path),
    )


def _merge_regex_into_store(
    store: ProfileStore, parsed: ParsedResume, resume_path: str
) -> None:
    """Regex-only path: write a fresh profile from whatever regex extracted.

    We treat a new resume upload as ground truth and overwrite the existing
    profile. If the user had manually edited fields, the UI should warn
    them before calling this endpoint (TODO).
    """
    profile = UserProfile(
        first_name=parsed.first_name or "",
        last_name=parsed.last_name or "",
        email=parsed.email or "",
        phone=parsed.phone,
        linkedin_url=parsed.linkedin_url,
        github_url=parsed.github_url,
        resume_path=resume_path,
    )
    store.save_profile(profile)
