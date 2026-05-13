from __future__ import annotations

import httpx


async def test_empty_profile_returns_null(
    backend_client: httpx.AsyncClient,
) -> None:
    response = await backend_client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() is None


async def test_save_then_load_profile(
    backend_client: httpx.AsyncClient,
) -> None:
    payload = {
        "first_name": "San",
        "last_name": "Zhang",
        "email": "san@example.com",
        "phone": "+86 13800000000",
        "location": "Shanghai",
        "linkedin_url": None,
        "github_url": None,
        "education": [],
        "experience": [],
        "skills": ["Python", "TypeScript"],
        "resume_path": None,
    }
    save_response = await backend_client.post("/api/profile", json=payload)
    assert save_response.status_code == 200
    saved = save_response.json()
    assert saved["id"] is not None

    fetch_response = await backend_client.get("/api/profile")
    assert fetch_response.status_code == 200
    fetched = fetch_response.json()
    assert fetched["first_name"] == "San"
    assert fetched["skills"] == ["Python", "TypeScript"]


async def test_upload_resume_autofills_profile(
    backend_client: httpx.AsyncClient, sample_resume_pdf_path
) -> None:
    # Save an empty profile first so the auto-merge path runs
    await backend_client.post(
        "/api/profile",
        json={
            "first_name": "",
            "last_name": "",
            "email": "placeholder@example.com",
            "phone": None,
            "location": None,
            "linkedin_url": None,
            "github_url": None,
            "education": [],
            "experience": [],
            "skills": [],
            "resume_path": None,
        },
    )

    with open(sample_resume_pdf_path, "rb") as fh:
        response = await backend_client.post(
            "/api/profile/resume",
            files={"file": ("resume.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["path"].endswith(".pdf")
    # Model isn't installed in CI, so the regex-only path runs
    assert body["llm_used"] is False
    parsed = body["parsed_fields"]
    assert parsed["detected_email"] == "san.zhang@example.com"

    # The profile should now be populated from the regex parse results
    profile = (await backend_client.get("/api/profile")).json()
    assert profile["first_name"] == "San"
