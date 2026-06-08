"""Profile CRUD + resume upload."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from hamster.applicator.llm import (
    LLMClient,
    LevelRecommender,
    ModelManager,
    ResumeExtractor,
)
from hamster.backend.dependencies import (
    get_data_dir,
    get_profile_store,
)
from hamster.profile_store import (
    ParsedResume,
    ProfileStore,
    extract_text,
    parse_resume,
)
from hamster.shared import UserProfile

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
    from hamster.applicator.llm import LLMClient as LocalLLMClient

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
    """Classify which seniority levels the user qualifies for.

    Uses pure-Python rules (no LLM). Tried with the LLM first but the 4B-class
    model couldn't reliably do the date arithmetic + rule application. This
    runs in microseconds and matches the user's intuition more consistently.
    """
    profile = store.load_profile()
    if not profile:
        return {
            "recommended": ["entry", "mid"],
            "stretch": ["senior"],
            "off_target": ["intern", "lead"],
            "reasoning": "No profile on file; defaulting to entry/mid.",
            "from_cache": False,
            "llm_used": False,
        }

    recommender = LevelRecommender()
    result = await recommender.recommend(profile)
    return {
        "recommended": result.recommended,
        "stretch": result.stretch,
        "off_target": result.off_target,
        "reasoning": result.reasoning,
        "from_cache": False,
        "llm_used": False,
    }


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
