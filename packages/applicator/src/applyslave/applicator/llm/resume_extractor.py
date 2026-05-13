"""LLM-powered resume parser.

Given the raw text of a resume PDF, build a ``UserProfile`` with the full
structured history (experience, education, skills, location, etc).

The heavy lifting happens in the LLM — all we do here is:
1. Clip / chunk the text so we respect the model's context window.
2. Build a strict JSON-schema prompt.
3. Validate the response against our Pydantic models.
4. Merge with the fast regex-only parse so we prefer LLM output where it
   exists but fall back to regex for anything the model missed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from applyslave.shared import (
    Education,
    Experience,
    LLMClient,
    UserProfile,
)

logger = logging.getLogger(__name__)


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": ["string", "null"]},
        "location": {"type": ["string", "null"]},
        "linkedin_url": {"type": ["string", "null"]},
        "github_url": {"type": ["string", "null"]},
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "school": {"type": "string"},
                    "degree": {"type": ["string", "null"]},
                    "major": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "end_date": {"type": ["string", "null"]},
                },
                "required": ["school"],
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "end_date": {"type": ["string", "null"]},
                },
                "required": ["company", "title"],
            },
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "first_name",
        "last_name",
        "email",
        "education",
        "experience",
        "skills",
    ],
}


_PROMPT_TEMPLATE = """You are a resume parser. Extract the candidate's
structured profile from the raw resume text below and output only a JSON
object matching this schema:

{{
  "first_name": string,
  "last_name": string,
  "email": string,
  "phone": string | null,
  "location": string | null,
  "linkedin_url": string | null,
  "github_url": string | null,
  "education": [
    {{"school": string, "degree": string|null, "major": string|null,
      "start_date": "YYYY-MM"|"YYYY"|null, "end_date": "YYYY-MM"|"YYYY"|null}}
  ],
  "experience": [
    {{"company": string, "title": string, "description": string|null,
      "start_date": "YYYY-MM"|"YYYY"|null, "end_date": "YYYY-MM"|"YYYY"|null}}
  ],
  "skills": [string]
}}

Rules:
- Output ONLY the JSON object. No prose, no code fences.
- Use null (not empty string) for missing optional fields.
- Preserve dates as the resume writes them if unambiguous (prefer YYYY-MM).
- For ongoing roles, set end_date to null.
- Split skills into individual items, not one long comma-joined string.
- Copy URLs exactly as they appear; if only a bare domain+path is given,
  prepend https:// yourself.
- Use the resume's language for title/description text; don't translate.

Resume text:
\"\"\"
{resume_text}
\"\"\"

JSON:"""


# A Qwen3-4B context window is 32k tokens. We never need more than ~8k tokens
# (~24k chars) of resume; cap so we don't blow past the window and so
# inference stays fast.
_MAX_RESUME_CHARS = 24_000


@dataclass
class ResumeExtractor:
    """Runs an LLM to produce a full ``UserProfile`` from a resume."""

    llm_client: LLMClient

    async def extract(
        self,
        *,
        resume_text: str,
        fallback: UserProfile | None = None,
    ) -> UserProfile:
        """Return a ``UserProfile`` built from the resume.

        If ``fallback`` is given (usually the regex-only parse), fields the
        LLM left empty are backfilled from it.
        """
        trimmed = resume_text.strip()
        if len(trimmed) > _MAX_RESUME_CHARS:
            logger.info(
                "Trimming resume from %d to %d chars for LLM",
                len(trimmed),
                _MAX_RESUME_CHARS,
            )
            trimmed = trimmed[:_MAX_RESUME_CHARS]

        prompt = _PROMPT_TEMPLATE.format(resume_text=trimmed)

        raw = await self.llm_client.chat_json(prompt, schema=EXTRACTION_SCHEMA)
        logger.debug("LLM raw response: %s", raw)

        profile = _payload_to_profile(raw)
        if fallback is not None:
            profile = _merge_fallback(profile, fallback)
        return profile


def _payload_to_profile(payload: dict) -> UserProfile:
    """Convert the LLM dict into a validated UserProfile.

    We are deliberately permissive here: the model occasionally omits a
    required list. We coerce those to empty lists and let Pydantic handle
    the rest.
    """
    payload = dict(payload)  # shallow copy

    for list_field in ("education", "experience", "skills"):
        payload.setdefault(list_field, [])
    for optional_field in (
        "phone",
        "location",
        "linkedin_url",
        "github_url",
    ):
        payload.setdefault(optional_field, None)

    education_raw = payload.get("education") or []
    experience_raw = payload.get("experience") or []

    # Filter out entries missing required subfields rather than crashing
    education = [
        Education(**_strip_unknowns(edu, Education.model_fields.keys()))
        for edu in education_raw
        if isinstance(edu, dict) and edu.get("school")
    ]
    experience = [
        Experience(**_strip_unknowns(exp, Experience.model_fields.keys()))
        for exp in experience_raw
        if isinstance(exp, dict) and exp.get("company") and exp.get("title")
    ]
    skills_raw = payload.get("skills") or []
    skills = [
        str(skill).strip()
        for skill in skills_raw
        if isinstance(skill, (str, int, float)) and str(skill).strip()
    ]

    return UserProfile(
        first_name=str(payload.get("first_name") or "").strip(),
        last_name=str(payload.get("last_name") or "").strip(),
        email=str(payload.get("email") or "").strip(),
        phone=_nullable_str(payload.get("phone")),
        location=_nullable_str(payload.get("location")),
        linkedin_url=_nullable_str(payload.get("linkedin_url")),
        github_url=_nullable_str(payload.get("github_url")),
        education=education,
        experience=experience,
        skills=skills,
    )


def _strip_unknowns(raw: dict, allowed: object) -> dict:
    allowed_set = set(allowed)
    return {key: value for key, value in raw.items() if key in allowed_set}


def _nullable_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _merge_fallback(primary: UserProfile, fallback: UserProfile) -> UserProfile:
    """Fill empty fields on ``primary`` from ``fallback``."""
    updates: dict = {}
    if not primary.first_name and fallback.first_name:
        updates["first_name"] = fallback.first_name
    if not primary.last_name and fallback.last_name:
        updates["last_name"] = fallback.last_name
    if not primary.email and fallback.email:
        updates["email"] = fallback.email
    if not primary.phone and fallback.phone:
        updates["phone"] = fallback.phone
    if not primary.location and fallback.location:
        updates["location"] = fallback.location
    if not primary.linkedin_url and fallback.linkedin_url:
        updates["linkedin_url"] = fallback.linkedin_url
    if not primary.github_url and fallback.github_url:
        updates["github_url"] = fallback.github_url
    return primary.model_copy(update=updates) if updates else primary


# Debug helper for ad-hoc testing
def schema_as_json() -> str:
    return json.dumps(EXTRACTION_SCHEMA, indent=2)
