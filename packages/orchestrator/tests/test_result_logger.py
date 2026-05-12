from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from applyslave.orchestrator import ResultLogger
from applyslave.shared import ApplicationRecord, ApplicationStatus


def test_insert_and_list_applications(tmp_path: Path) -> None:
    store = ResultLogger(tmp_path)
    record = store.insert_application(
        ApplicationRecord(
            url="https://x/apply/1", company="X Co", title="SWE"
        )
    )
    assert record.id is not None
    assert record.created_at is not None

    listed = store.list_applications()
    assert len(listed) == 1
    assert listed[0].company == "X Co"


def test_duplicate_url_updates_existing(tmp_path: Path) -> None:
    store = ResultLogger(tmp_path)
    first = store.insert_application(
        ApplicationRecord(url="https://x/1", company="X", title="SWE")
    )
    second = store.insert_application(
        ApplicationRecord(
            url="https://x/1",
            company="X",
            title="SWE",
            status=ApplicationStatus.SUBMITTED,
        )
    )
    assert second.id == first.id
    by_url = store.get_by_url("https://x/1")
    assert by_url is not None
    assert by_url.status is ApplicationStatus.SUBMITTED


def test_update_status(tmp_path: Path) -> None:
    store = ResultLogger(tmp_path)
    record = store.insert_application(
        ApplicationRecord(url="https://x/2", company="X", title="SWE")
    )
    assert record.id is not None
    store.update_status(
        record.id,
        status=ApplicationStatus.FAILED,
        error="captcha",
    )
    updated = store.get_by_url("https://x/2")
    assert updated is not None
    assert updated.status is ApplicationStatus.FAILED
    assert updated.error == "captcha"


def test_discovery_task_round_trip(tmp_path: Path) -> None:
    store = ResultLogger(tmp_path)
    store.save_discovery_task(
        task_id="disc-1",
        keywords="engineer",
        location="remote",
        filters={"remote_only": True},
        status="running",
    )
    fetched = store.load_discovery_task("disc-1")
    assert fetched is not None
    assert fetched["keywords"] == "engineer"
    assert fetched["filters"] == {"remote_only": True}

    store.save_discovery_task(
        task_id="disc-1",
        keywords="engineer",
        location="remote",
        filters={"remote_only": True},
        status="completed",
        results=[{"id": "gh-1", "title": "SWE"}],
    )
    updated = store.load_discovery_task("disc-1")
    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["results"] == [{"id": "gh-1", "title": "SWE"}]


def test_filter_by_status(tmp_path: Path) -> None:
    store = ResultLogger(tmp_path)
    store.insert_application(
        ApplicationRecord(url="https://x/a", company="A", title="SWE")
    )
    b = store.insert_application(
        ApplicationRecord(url="https://x/b", company="B", title="PM")
    )
    assert b.id is not None
    store.update_status(
        b.id, status=ApplicationStatus.SUBMITTED, applied_at=datetime.now(UTC)
    )

    submitted = store.list_applications(status=ApplicationStatus.SUBMITTED)
    queued = store.list_applications(status=ApplicationStatus.QUEUED)
    assert [r.company for r in submitted] == ["B"]
    assert [r.company for r in queued] == ["A"]
