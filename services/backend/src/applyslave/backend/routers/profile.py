"""Profile CRUD + resume upload."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from applyslave.backend.dependencies import get_profile_store
from applyslave.profile_store import ProfileStore, parse_resume
from applyslave.shared import UserProfile

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=UserProfile | None)
async def read_profile(
    store: Annotated[ProfileStore, Depends(get_profile_store)],
) -> UserProfile | None:
    return store.load_profile()


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

    # Stream to a temp file before handing to ProfileStore so we don't keep
    # the whole resume in memory.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        stored_path = store.save_resume_file(tmp_path)
        parsed = parse_resume(stored_path)
        # Auto-merge detected fields into the existing profile if present
        current = store.load_profile()
        updates: dict = {"resume_path": str(stored_path)}
        if current is not None:
            if current.first_name in {"", None} and parsed.first_name:
                updates["first_name"] = parsed.first_name
            if current.last_name in {"", None} and parsed.last_name:
                updates["last_name"] = parsed.last_name
            if not current.email and parsed.email:
                updates["email"] = parsed.email
            if not current.phone and parsed.phone:
                updates["phone"] = parsed.phone
            if not current.linkedin_url and parsed.linkedin_url:
                updates["linkedin_url"] = parsed.linkedin_url
            if not current.github_url and parsed.github_url:
                updates["github_url"] = parsed.github_url
            store.save_profile(current.model_copy(update=updates))
        return {
            "path": str(stored_path),
            "parsed_fields": {
                "detected_first_name": parsed.first_name,
                "detected_last_name": parsed.last_name,
                "detected_email": parsed.email,
                "detected_phone": parsed.phone,
                "detected_linkedin_url": parsed.linkedin_url,
                "detected_github_url": parsed.github_url,
            },
        }
    finally:
        tmp_path.unlink(missing_ok=True)
