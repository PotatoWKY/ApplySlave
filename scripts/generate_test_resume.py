"""Generate the fixture PDF resume used for dry-run / e2e testing.

The persona is intentionally fictional with safe contact info:
  * @example.com is reserved by IANA — mail is discarded
  * +1-555-01XX is a reserved test exchange — no real phone gets dialed
  * github.com/applyslave-test is an org we own / never receive submissions

Run: .venv/bin/python scripts/generate_test_resume.py
Output: tests/fixtures/pat_apply_resume.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "tests" / "fixtures" / "pat_apply_resume.pdf"


PROFILE = {
    "name": "Pat Apply",
    "headline": "Software Engineer · Test Persona",
    "email": "pat.apply@example.com",
    "phone": "+1-555-0100",
    "linkedin": "linkedin.com/in/applyslave-test",
    "github": "github.com/applyslave-test",
    "location": "Seattle, WA",
    "summary": (
        "Fictional candidate used by the ApplySlave test suite. Contact "
        "details point to RFC-reserved domains and phone exchanges so "
        "automated submissions can never reach a real person."
    ),
    "experience": [
        {
            "title": "Software Engineer",
            "company": "ApplySlave Test Co.",
            "dates": "2024-06 - Present",
            "bullets": [
                "Built fixture data for end-to-end test runs of the apply flow.",
                "Implemented form-fill regression tests across Greenhouse, "
                "Lever, Ashby, and Workable boards.",
                "Documented the dry-run protocol so future test runs do not "
                "submit anything to real hiring systems.",
            ],
        },
        {
            "title": "Software Engineer",
            "company": "Example Labs",
            "dates": "2022-08 - 2024-05",
            "bullets": [
                "Owned a Python + FastAPI service for processing resume PDFs.",
                "Designed a regression harness for headless-browser flows.",
                "Wrote tooling that reduced flaky-test rate from 12% to 3%.",
            ],
        },
        {
            "title": "Software Engineer Intern",
            "company": "Sandbox Inc.",
            "dates": "2021-06 - 2021-08",
            "bullets": [
                "Prototyped a CLI for replaying mock HTTP traffic.",
                "Added telemetry hooks for the company's internal CI farm.",
            ],
        },
    ],
    "education": [
        {
            "degree": "B.S. Computer Science",
            "school": "University of Washington",
            "dates": "2018-09 - 2022-06",
        },
    ],
    "skills": [
        "Python",
        "TypeScript",
        "React",
        "FastAPI",
        "Playwright",
        "SQLite",
        "Docker",
        "Git",
        "Pytest",
        "REST APIs",
    ],
}


def build() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="Pat Apply Resume",
        author="ApplySlave test fixture",
    )

    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "Name",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=4,
    )
    headline_style = ParagraphStyle(
        "Headline",
        parent=styles["Normal"],
        fontSize=11,
        textColor="#555555",
        spaceAfter=8,
    )
    contact_style = ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        textColor="#222222",
        spaceBefore=10,
        spaceAfter=4,
    )
    role_style = ParagraphStyle(
        "Role",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=2,
    )
    role_meta_style = ParagraphStyle(
        "RoleMeta",
        parent=styles["Normal"],
        fontSize=9,
        textColor="#666666",
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=styles["Normal"],
        fontSize=10,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=2,
    )
    body_style = styles["Normal"]

    story = []

    story.append(Paragraph(PROFILE["name"], name_style))
    story.append(Paragraph(PROFILE["headline"], headline_style))

    contact_line = (
        f"{PROFILE['email']} | {PROFILE['phone']} | {PROFILE['location']}<br/>"
        f"{PROFILE['linkedin']} | {PROFILE['github']}"
    )
    story.append(Paragraph(contact_line, contact_style))

    story.append(Paragraph("SUMMARY", section_style))
    story.append(Paragraph(PROFILE["summary"], body_style))

    story.append(Paragraph("EXPERIENCE", section_style))
    for exp in PROFILE["experience"]:
        story.append(
            Paragraph(f"<b>{exp['title']}</b> – {exp['company']}", role_style)
        )
        story.append(Paragraph(exp["dates"], role_meta_style))
        for bullet in exp["bullets"]:
            story.append(Paragraph(f"• {bullet}", bullet_style))
        story.append(Spacer(1, 4))

    story.append(Paragraph("EDUCATION", section_style))
    for edu in PROFILE["education"]:
        story.append(
            Paragraph(f"<b>{edu['degree']}</b> – {edu['school']}", role_style)
        )
        story.append(Paragraph(edu["dates"], role_meta_style))

    story.append(Paragraph("SKILLS", section_style))
    story.append(Paragraph(", ".join(PROFILE["skills"]), body_style))

    doc.build(story)
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    build()
