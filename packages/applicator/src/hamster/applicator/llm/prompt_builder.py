"""Prompt templates for page understanding and form-field mapping.

Keeping these as ordinary Python strings makes them easy to test; the LLM
client itself is a pluggable dependency so prompts can be iterated on without
touching inference code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from hamster.shared import PageDOM, UserProfile


@dataclass
class DefaultPromptBuilder:
    """Builds prompts for `PageAnalyzer` and `FormMapper` LLM calls."""

    def build_page_analysis_prompt(self, dom: PageDOM) -> str:
        payload = {
            "url": dom.url,
            "title": dom.title,
            "elements": [
                {
                    "label": el.label,
                    "type": el.element_type.value,
                    "required": el.required,
                }
                for el in dom.elements[:40]  # cap so prompt stays bounded
            ],
        }
        return (
            "You are analyzing a web page for a job-application bot.\n"
            "Decide the page's category and output only JSON matching:\n"
            '{"page_type": "...", "confidence": 0.0, "reasoning": "..."}\n\n'
            "Allowed values for page_type: login, job_list, job_detail, "
            "application_form, confirmation, captcha, unknown.\n\n"
            f"Page data:\n{json.dumps(payload, ensure_ascii=False)}\n"
        )

    def build_form_mapping_prompt(
        self, dom: PageDOM, profile: UserProfile
    ) -> str:
        elements = [
            {
                "id": el.id,
                "type": el.element_type.value,
                "label": el.label,
                "placeholder": el.placeholder,
                "required": el.required,
                "options": el.options,
                "selector": el.selector,
            }
            for el in dom.elements
        ]
        profile_payload = {
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "education": [edu.model_dump() for edu in profile.education],
            "experience": [exp.model_dump() for exp in profile.experience],
            "skills": profile.skills,
            "resume_path": profile.resume_path,
        }
        return (
            "You are mapping a user's profile onto a web application form.\n"
            "Return only JSON matching:\n"
            '{"actions":[{"type":"fill|click|select|select_combobox|check|'
            'uncheck|upload","selector":"...","value":"..."}],'
            '"unmapped_fields":["..."],'
            '"confidence":0.0,'
            '"reasoning":"..."}\n\n'
            "Rules:\n"
            "- Use exactly the selectors given.\n"
            "- For 'select' (native) and 'combobox' elements, value MUST "
            "exactly match one of the provided options.\n"
            "- Use type='select_combobox' for elements whose type is "
            "'combobox'; use type='select' for type 'select'.\n"
            "- For a combobox/select whose options list is empty or missing, "
            "do NOT invent a value outside the option set — add it to "
            "unmapped_fields instead.\n"
            "- Answer every required combobox question (visa sponsorship, "
            "relocation, in-person, etc.) using the profile; only leave one "
            "unmapped if the profile genuinely lacks the information.\n"
            "- Fill optional free-text fields (e.g. 'Additional Information', "
            "cover-letter-style textareas) by synthesizing ONLY from "
            "profile.experience[].description and profile.skills — they add "
            "value, so don't leave them blank when the profile has material.\n"
            "- NEVER FABRICATE. Do not state degrees, employers, dates, "
            "certifications, work authorization, or security clearances that "
            "are not present in the profile. If a field asks about work "
            "authorization / visa / sponsorship / clearance / a degree and the "
            "profile lacks that information, add it to unmapped_fields rather "
            "than guessing.\n"
            "  Example DO: field 'Additional Information' -> "
            "'I have built Python/FastAPI services and browser automation; "
            "skills include Python, TypeScript, React.' (drawn from profile)\n"
            "  Example DON'T: field 'Highest degree' with no education in "
            "profile -> do NOT answer 'B.S.'; add to unmapped_fields.\n"
            "- Use type='upload' with value=profile.resume_path for resume "
            "file inputs.\n"
            "- Add fields you couldn't map to 'unmapped_fields'.\n\n"
            f"Form elements:\n{json.dumps(elements, ensure_ascii=False)}\n\n"
            f"User profile:\n{json.dumps(profile_payload, ensure_ascii=False)}\n"
        )
