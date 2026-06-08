"""Live smoke test: load the local LLM and extract a resume.

Usage: uv run python scripts/smoke_llm_extraction.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from hamster.applicator.llm import LLMClient, ModelManager, ResumeExtractor
from hamster.profile_store import extract_text, parse_resume


DATA_DIR = Path.home() / "Library" / "Application Support" / "Hamster"


def _build_sample_pdf(path: Path) -> Path:
    """Generate a realistic-looking sample resume PDF on disk."""
    from reportlab.pdfgen import canvas

    canvas_obj = canvas.Canvas(str(path))
    y = 800
    lines = [
        "San Zhang",
        "san.zhang@example.com | +86 138-0000-0000",
        "Shanghai, China",
        "https://linkedin.com/in/sanzhang | https://github.com/sanzhang",
        "",
        "EXPERIENCE",
        "Senior Software Engineer, Stripe",
        "  2022 - Present",
        "  Shipped ATS integrations consumed by 200k users.",
        "  Led design for fraud detection pipeline in Python + Kafka.",
        "",
        "Software Engineer Intern, Netflix",
        "  Summer 2021",
        "  Built experimentation dashboards using React and TypeScript.",
        "",
        "EDUCATION",
        "BS Computer Science, Tsinghua University",
        "  2017 - 2021",
        "  GPA 3.8",
        "",
        "SKILLS",
        "Python, TypeScript, React, Kafka, AWS, PostgreSQL, Docker",
    ]
    for line in lines:
        canvas_obj.drawString(50, y, line)
        y -= 18
    canvas_obj.save()
    return path


async def main() -> None:
    manager = ModelManager(data_dir=DATA_DIR)
    if not manager.is_installed():
        print(f"Model not installed at {manager.model_path}")
        sys.exit(1)
    print(f"Loading model from {manager.model_path} ({manager.model_name})")

    tmp_pdf = DATA_DIR / "smoke_resume.pdf"
    tmp_pdf.parent.mkdir(parents=True, exist_ok=True)
    _build_sample_pdf(tmp_pdf)

    resume_text = extract_text(tmp_pdf)
    regex_parsed = parse_resume(tmp_pdf)
    print(f"Regex found: {regex_parsed.email}, "
          f"{regex_parsed.first_name} {regex_parsed.last_name}")

    llm_client = LLMClient(model_path=manager.model_path, verbose=False)
    extractor = ResumeExtractor(llm_client=llm_client)

    print("\nExtracting with LLM (first call will load the model ~5-10s)...")
    start = time.monotonic()
    profile = await extractor.extract(resume_text=resume_text)
    elapsed = time.monotonic() - start
    print(f"Done in {elapsed:.1f}s.\n")

    print(f"Name:     {profile.first_name} {profile.last_name}")
    print(f"Email:    {profile.email}")
    print(f"Phone:    {profile.phone}")
    print(f"Location: {profile.location}")
    print(f"LinkedIn: {profile.linkedin_url}")
    print(f"GitHub:   {profile.github_url}")
    print()
    print(f"Experience ({len(profile.experience)} entries):")
    for exp in profile.experience:
        print(f"  - {exp.title} @ {exp.company}  "
              f"[{exp.start_date or '?'} → {exp.end_date or 'present'}]")
        if exp.description:
            print(f"      {exp.description[:120]}")
    print()
    print(f"Education ({len(profile.education)} entries):")
    for edu in profile.education:
        print(f"  - {edu.degree or '?'} {edu.major or ''} @ {edu.school}  "
              f"[{edu.start_date or '?'} → {edu.end_date or '?'}]")
    print()
    print(f"Skills ({len(profile.skills)}):")
    print(f"  {', '.join(profile.skills)}")


if __name__ == "__main__":
    asyncio.run(main())
