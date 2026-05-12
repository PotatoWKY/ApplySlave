from __future__ import annotations

from pathlib import Path

from applyslave.orchestrator import (
    ApplicationOrchestrator,
    JobTask,
    ResultLogger,
)
from applyslave.shared import ApplicationStatus, ApplyResult, UserProfile


class _StubApplicator:
    """Deterministic applicator: first URL succeeds, second fails."""

    async def apply(self, url: str, profile: UserProfile) -> ApplyResult:
        del profile
        if "good" in url:
            return ApplyResult(
                success=True, status=ApplicationStatus.SUBMITTED, url=url
            )
        return ApplyResult(
            success=False,
            status=ApplicationStatus.FAILED,
            url=url,
            error="simulated",
        )


def _profile() -> UserProfile:
    return UserProfile(first_name="San", last_name="Zhang", email="san@example.com")


async def test_orchestrator_runs_batch_and_persists(tmp_path: Path) -> None:
    logger_store = ResultLogger(tmp_path)
    events: list[tuple[str, dict]] = []

    async def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    orchestrator = ApplicationOrchestrator(
        applicator=_StubApplicator(),
        logger_store=logger_store,
        on_event=on_event,
    )

    tasks = [
        JobTask(url="https://good/1", company="GoodCo", title="SWE"),
        JobTask(url="https://bad/1", company="BadCo", title="PM"),
    ]
    results = await orchestrator.run_batch(_profile(), tasks)

    statuses = [result.status for result in results]
    assert ApplicationStatus.SUBMITTED in statuses
    assert ApplicationStatus.FAILED in statuses

    # Verify persistence
    stored = logger_store.list_applications()
    assert {record.url for record in stored} == {
        "https://good/1",
        "https://bad/1",
    }
    good_record = next(r for r in stored if "good" in r.url)
    assert good_record.status is ApplicationStatus.SUBMITTED
    assert good_record.applied_at is not None

    # Verify events fired in a sensible order
    event_types = [evt_type for evt_type, _ in events]
    assert event_types.count("application_started") == 2
    assert "application_completed" in event_types
    assert "application_failed" in event_types
