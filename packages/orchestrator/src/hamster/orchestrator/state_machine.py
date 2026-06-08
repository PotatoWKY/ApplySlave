"""High-level coordinator: take URLs, run them through an Applicator, log results."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

from hamster.orchestrator.job_queue import JobQueue, JobTask
from hamster.orchestrator.result_logger import ResultLogger
from hamster.shared import (
    ApplicationRecord,
    ApplicationStatus,
    Applicator,
    ApplyResult,
    UserProfile,
)

logger = logging.getLogger(__name__)


EventCallback = Callable[[str, dict], Awaitable[None]]


class ApplicationOrchestrator:
    """Coordinates discovery → queue → apply → persist.

    Event callback receives ``(event_type, payload)`` pairs so the FastAPI
    layer can forward them out over WebSocket.
    """

    def __init__(
        self,
        *,
        applicator: Applicator,
        logger_store: ResultLogger,
        on_event: EventCallback | None = None,
        concurrency: int = 1,
    ) -> None:
        self._applicator = applicator
        self._logger_store = logger_store
        self._on_event = on_event
        self._concurrency = concurrency

    async def run_batch(
        self,
        profile: UserProfile,
        tasks: list[JobTask],
    ) -> list[ApplyResult]:
        """Apply to every task, persist each outcome, and emit progress events."""
        queue = JobQueue(concurrency=self._concurrency)
        for task in tasks:
            # Pre-insert so the UI can see all queued jobs immediately
            self._logger_store.insert_application(
                ApplicationRecord(
                    url=task.url,
                    company=task.company,
                    title=task.title,
                    status=ApplicationStatus.QUEUED,
                )
            )
            await queue.submit(task)

        async def worker(task: JobTask) -> ApplyResult:
            await self._emit(
                "application_started",
                {"url": task.url, "company": task.company, "title": task.title},
            )
            self._mark_in_progress(task)

            result = await self._applicator.apply(task.url, profile)

            record = self._logger_store.get_by_url(task.url)
            if record is not None and record.id is not None:
                self._logger_store.update_status(
                    record.id,
                    status=result.status,
                    error=result.error,
                    applied_at=datetime.now(UTC)
                    if result.status is ApplicationStatus.SUBMITTED
                    else None,
                )

            await self._emit(
                "application_completed"
                if result.success
                else "application_failed",
                {
                    "url": task.url,
                    "company": task.company,
                    "title": task.title,
                    "status": result.status.value,
                    "error": result.error,
                },
            )
            return result

        return await queue.drain(worker)

    # --- helpers --------------------------------------------------------

    def _mark_in_progress(self, task: JobTask) -> None:
        record = self._logger_store.get_by_url(task.url)
        if record is not None and record.id is not None:
            self._logger_store.update_status(
                record.id, status=ApplicationStatus.IN_PROGRESS
            )

    async def _emit(self, event_type: str, payload: dict) -> None:
        if self._on_event is None:
            return
        try:
            await self._on_event(event_type, payload)
        except Exception as error:  # noqa: BLE001
            logger.warning("Event emit failed: %s", error)


async def as_completed_results(
    coroutines: list[Awaitable[ApplyResult]],
) -> AsyncIterator[ApplyResult]:
    """Yield ApplyResults as each coroutine finishes."""
    for coro in asyncio.as_completed(coroutines):
        yield await coro
