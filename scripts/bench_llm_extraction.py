"""Benchmark LLM extraction time on increasingly complex resumes."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from applyslave.applicator.llm import LLMClient, ModelManager, ResumeExtractor


DATA_DIR = Path.home() / "Library" / "Application Support" / "ApplySlave"


SHORT_RESUME = """\
San Zhang
san@example.com | +86 138-0000-0000
Shanghai

EXPERIENCE
Software Engineer, Stripe (2022 - Present)
  Built things.

EDUCATION
BS CS, Tsinghua (2017-2021)

SKILLS
Python, TypeScript
"""


LONG_RESUME = """\
San Zhang
san.zhang@example.com | +86 138-0000-0000 | Shanghai, China
https://linkedin.com/in/sanzhang | https://github.com/sanzhang

SUMMARY
Senior software engineer with 6+ years of experience building distributed
systems, ML infrastructure, and developer tooling at scale. Led projects
serving 100M+ users at Stripe and Netflix. Passionate about open source,
developer experience, and high-leverage work.

EXPERIENCE

Senior Software Engineer, Stripe
March 2023 - Present, San Francisco (Remote)
  - Designed and implemented the fraud detection pipeline in Python +
    Kafka serving 200K transactions/second.
  - Led migration from monolithic Django app to gRPC microservices,
    reducing p99 latency by 60%.
  - Mentored 3 junior engineers and ran onboarding bootcamps for new hires.
  - Collaborated with product and design to ship customer-facing ATS
    integrations consumed by Fortune 500 companies.

Software Engineer, Netflix
August 2020 - February 2023, Los Gatos, CA
  - Built experimentation dashboards in React and TypeScript used by
    500+ PMs and designers.
  - Implemented real-time analytics backend using ClickHouse and Redis.
  - Shipped features used daily by 10M+ internal users.
  - Awarded "Innovation of the Year" for the video encoding optimization
    that saved $2M/year in CDN costs.

Software Engineering Intern, Google
Summer 2019, Mountain View, CA
  - Contributed to the Chrome DevTools team, specifically the Performance
    panel.
  - Shipped a feature to inspect JavaScript memory allocations that made
    it into Chrome 78.

Undergraduate Research Assistant, Tsinghua AI Lab
2018 - 2020, Beijing, China
  - Research on reinforcement learning applied to game playing agents.
  - Co-authored a paper accepted at NeurIPS 2020.

EDUCATION

Tsinghua University
BS, Computer Science, 2016 - 2020
  - GPA: 3.9/4.0, Dean's List all semesters
  - Relevant coursework: Operating Systems, Distributed Systems, ML,
    Compilers, Cryptography
  - President of the Computer Science student association

SKILLS

Languages: Python, TypeScript, Go, Rust, C++, SQL
Frameworks: React, FastAPI, Django, gRPC, Kafka, Kubernetes
Cloud: AWS (EC2, S3, Lambda, DynamoDB), GCP (BigQuery, Cloud Run)
ML: PyTorch, TensorFlow, scikit-learn, LangChain, llama.cpp
Tools: Git, Docker, Terraform, Bazel, Playwright

CERTIFICATIONS
  - AWS Certified Solutions Architect Professional
  - Certified Kubernetes Administrator (CKA)

LANGUAGES
  - English (Fluent)
  - Mandarin Chinese (Native)
  - Japanese (Conversational)
"""


async def bench(label: str, text: str) -> None:
    manager = ModelManager(data_dir=DATA_DIR)
    client = LLMClient(model_path=manager.model_path, verbose=False)
    extractor = ResumeExtractor(llm_client=client)

    print(f"\n=== {label} ({len(text)} chars) ===")
    start = time.monotonic()
    profile = await extractor.extract(resume_text=text)
    elapsed = time.monotonic() - start
    print(f"Total: {elapsed:.1f}s")
    print(f"  {len(profile.experience)} experience, "
          f"{len(profile.education)} education, "
          f"{len(profile.skills)} skills")


async def main() -> None:
    await bench("SHORT resume", SHORT_RESUME)
    await bench("LONG resume", LONG_RESUME)


if __name__ == "__main__":
    asyncio.run(main())
