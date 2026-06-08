from __future__ import annotations

from pathlib import Path

import pytest

from hamster.profile_store import ProfileStore
from hamster.shared import Education, Experience, UserProfile


def _sample_profile() -> UserProfile:
    return UserProfile(
        first_name="San",
        last_name="Zhang",
        email="san@example.com",
        phone="+86-13800000000",
        location="Shanghai",
        education=[Education(school="XX Univ", major="CS", degree="BS")],
        experience=[Experience(company="XX Corp", title="Engineer")],
        skills=["Python", "TypeScript"],
    )


def test_save_and_load_round_trip(data_dir: Path) -> None:
    store = ProfileStore(data_dir)
    assert store.load_profile() is None

    saved = store.save_profile(_sample_profile())
    assert saved.id is not None
    assert saved.updated_at is not None

    loaded = store.load_profile()
    assert loaded is not None
    assert loaded.first_name == "San"
    assert loaded.skills == ["Python", "TypeScript"]
    assert len(loaded.education) == 1


def test_save_profile_updates_existing_row(data_dir: Path) -> None:
    store = ProfileStore(data_dir)
    first = store.save_profile(_sample_profile())
    second = store.save_profile(
        _sample_profile().model_copy(update={"email": "new@example.com"})
    )
    assert second.id == first.id
    loaded = store.load_profile()
    assert loaded is not None
    assert loaded.email == "new@example.com"


def test_resume_file_copy(data_dir: Path, tmp_path: Path) -> None:
    store = ProfileStore(data_dir)
    fake_pdf = tmp_path / "my_resume.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    stored_path = store.save_resume_file(fake_pdf)
    assert stored_path.exists()
    assert stored_path.parent == store.resumes_dir
    assert store.get_resume_path() == stored_path


def test_resume_file_rejects_non_pdf(data_dir: Path, tmp_path: Path) -> None:
    store = ProfileStore(data_dir)
    bad = tmp_path / "resume.docx"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        store.save_resume_file(bad)


def test_resume_file_missing_source(data_dir: Path, tmp_path: Path) -> None:
    store = ProfileStore(data_dir)
    with pytest.raises(FileNotFoundError):
        store.save_resume_file(tmp_path / "nope.pdf")
