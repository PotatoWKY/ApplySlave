"""Check how long each extraction takes when the LLMClient is reused."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from hamster.applicator.llm import LLMClient, ModelManager, ResumeExtractor


DATA_DIR = Path.home() / "Library" / "Application Support" / "Hamster"

SHORT = "San Zhang\nsan@x.com\nSoftware Engineer at Stripe\nBS CS Tsinghua 2020\nPython, TypeScript"
LONG = open(Path(__file__).parent / "_long_resume.txt").read() if (Path(__file__).parent / "_long_resume.txt").exists() else SHORT * 20


async def main() -> None:
    manager = ModelManager(data_dir=DATA_DIR)
    client = LLMClient(model_path=manager.model_path, verbose=False)
    extractor = ResumeExtractor(llm_client=client)

    for label, text in [
        ("first-short", SHORT),
        ("second-short", SHORT),
        ("third-short", SHORT),
        ("first-long", LONG),
        ("second-long", LONG),
    ]:
        start = time.monotonic()
        profile = await extractor.extract(resume_text=text)
        elapsed = time.monotonic() - start
        print(f"{label:15s}: {elapsed:5.1f}s  "
              f"({len(profile.experience)} exp, {len(profile.skills)} skills)")


if __name__ == "__main__":
    asyncio.run(main())
