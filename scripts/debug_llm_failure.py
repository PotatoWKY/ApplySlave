"""Reproduce the LLM extraction failure on the real uploaded resume.

This shows the full traceback that the HTTP handler swallows.
"""

from __future__ import annotations

import asyncio
import traceback
from pathlib import Path

from hamster.applicator.llm import LLMClient, ModelManager, ResumeExtractor
from hamster.profile_store import extract_text


DATA_DIR = Path.home() / "Library" / "Application Support" / "Hamster"
RESUME_PATH = DATA_DIR / "resumes" / "main_resume.pdf"


async def main() -> None:
    if not RESUME_PATH.exists():
        print(f"No resume at {RESUME_PATH}")
        return

    resume_text = extract_text(RESUME_PATH)
    print(f"Resume length: {len(resume_text)} chars")
    print(f"First 400 chars:\n{resume_text[:400]}")
    print("=" * 60)

    manager = ModelManager(data_dir=DATA_DIR)
    client = LLMClient(model_path=manager.model_path, verbose=False)
    extractor = ResumeExtractor(llm_client=client)

    try:
        profile = await extractor.extract(resume_text=resume_text)
        print("SUCCESS")
        print(f"  {profile.first_name} {profile.last_name}  <{profile.email}>")
        print(f"  {len(profile.experience)} experience")
        print(f"  {len(profile.education)} education")
        print(f"  {len(profile.skills)} skills")
    except Exception as error:
        print(f"FAILED: {type(error).__name__}: {error}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
