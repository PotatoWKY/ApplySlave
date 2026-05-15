"""LLM-powered seniority-level recommender.

Given a user's profile, decide which seniority levels they realistically
qualify for. Output is a structured list:
  - recommended: levels the user should target (default-checked in UI)
  - stretch:     levels worth considering with strong stories (optional)
  - off_target:  levels they're under- or over-qualified for

Cached in settings.json — only re-runs when the profile materially changes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from applyslave.shared import LLMClient, UserProfile

logger = logging.getLogger(__name__)


VALID_LEVELS = ["intern", "entry", "mid", "senior", "lead"]


LEVEL_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended": {
            "type": "array",
            "items": {"type": "string", "enum": VALID_LEVELS},
        },
        "stretch": {
            "type": "array",
            "items": {"type": "string", "enum": VALID_LEVELS},
        },
        "off_target": {
            "type": "array",
            "items": {"type": "string", "enum": VALID_LEVELS},
        },
        "reasoning": {"type": "string"},
    },
    "required": ["recommended", "stretch", "off_target", "reasoning"],
}


_PROMPT_TEMPLATE = """You are an experienced tech recruiter helping a candidate
decide which seniority levels to target when applying to jobs.

Given the candidate's profile below, classify each of these seniority levels:
  - intern: undergraduate / part-time student internships
  - entry:  new grad, 0-2 years experience, "Software Engineer I"
  - mid:    2-5 years experience, "Software Engineer II", "Senior" at small co
  - senior: 5-8 years experience, "Senior" / "Sr. Software Engineer"
  - lead:   8+ years, "Staff", "Principal", or team lead roles

Output ONLY a JSON object:
{{
  "recommended": [<levels they should target>],
  "stretch":     [<levels they could try but aren't a strong fit>],
  "off_target":  [<levels they're clearly under- or over-qualified for>],
  "reasoning":   "<one sentence explaining your call>"
}}

Each of the five levels must appear in exactly one of the three lists.

Heuristics:
- Count years from earliest start_date to most recent end_date (or today)
- Recent or current role title weighs more than total years
- A master's degree adds ~1 year of equivalent experience
- "Lead", "Staff", "Principal" titles → recommend senior + lead
- 0-2 years → recommend entry, stretch mid (not senior+)
- Pure intern history → recommend intern + entry only
- Be conservative: if unclear, prefer "stretch" over "recommended"

Candidate profile:
{profile_json}

JSON:"""


@dataclass
class LevelRecommendation:
    recommended: list[str]
    stretch: list[str]
    off_target: list[str]
    reasoning: str


@dataclass
class LevelRecommender:
    """Runs the LLM to classify which levels suit the user."""

    llm_client: LLMClient

    async def recommend(self, profile: UserProfile) -> LevelRecommendation:
        profile_payload = {
            "experience": [
                {
                    "company": exp.company,
                    "title": exp.title,
                    "start_date": exp.start_date,
                    "end_date": exp.end_date,
                }
                for exp in profile.experience
            ],
            "education": [
                {
                    "school": edu.school,
                    "degree": edu.degree,
                    "major": edu.major,
                    "end_date": edu.end_date,
                }
                for edu in profile.education
            ],
            "skills_count": len(profile.skills),
        }

        prompt = _PROMPT_TEMPLATE.format(
            profile_json=json.dumps(profile_payload, indent=2)
        )

        raw = await self.llm_client.chat_json(prompt, schema=LEVEL_SCHEMA)
        logger.debug("Level LLM raw response: %s", raw)

        return _payload_to_recommendation(raw)


def _payload_to_recommendation(payload: dict) -> LevelRecommendation:
    """Validate + coerce the LLM output into a recommendation."""
    recommended = _coerce_levels(payload.get("recommended", []))
    stretch = _coerce_levels(payload.get("stretch", []))
    off_target = _coerce_levels(payload.get("off_target", []))
    reasoning = str(payload.get("reasoning", "")).strip()

    # Defensive: ensure each level appears at most once across all lists.
    seen: set[str] = set()
    recommended = [
        level for level in recommended if not (level in seen or seen.add(level))
    ]
    stretch = [
        level for level in stretch if not (level in seen or seen.add(level))
    ]
    off_target = [
        level for level in off_target if not (level in seen or seen.add(level))
    ]

    # Defensive: cover any missing level by putting it in off_target.
    missing = [level for level in VALID_LEVELS if level not in seen]
    off_target.extend(missing)

    return LevelRecommendation(
        recommended=recommended,
        stretch=stretch,
        off_target=off_target,
        reasoning=reasoning,
    )


def _coerce_levels(raw: object) -> list[str]:
    """Filter to known level strings."""
    if not isinstance(raw, list):
        return []
    return [
        item.lower().strip()
        for item in raw
        if isinstance(item, str) and item.lower().strip() in VALID_LEVELS
    ]
