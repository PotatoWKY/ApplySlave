"""In-process job queue with bounded concurrency.

Wraps an ``asyncio.Queue`` plus a simple worker pool so the orchestrator
can submit jobs to be applied without overwhelming the remote sites.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from applyslave.shared import ApplyResult

logger = logging.getLogger(__name__)


@dataclass
class JobTask:
    """A single URL to be applied to, with the metadata needed to log it."""

    url: str
    company: str
    title: str
    index: int = 0


@dataclass
class JobQueue:
    """Pass jobs through a bounded pool of workers."""

    concurrency: int = 1
    _queue: asyncio.Queue[JobTask | None] = field(
        default_factory=lambda: asyncio.Queue()
    )

    async def submit(self, task: JobTask) -> None:
        await self._queue.put(task)

    async def drain(
        self,
        worker: Callable[[JobTask], Awaitable[ApplyResult]],
    ) -> list[ApplyResult]:
        """Process everything currently in the queue and return results in order."""
        pending = []
        while not self._queue.empty():
            pending.append(self._queue.get_nowait())

        semaphore = asyncio.Semaphore(self.concurrency)

        async def _run(task: JobTask) -> ApplyResult:
            async with semaphore:
                logger.info("Starting apply: %s @ %s", task.title, task.company)
                try:
                    return await worker(task)
                except Exception as error:  # noqa: BLE001
                    logger.exception("Worker crashed on %s", task.url)
                    from applyslave.shared import ApplicationStatus

                    return ApplyResult(
                        success=False,
                        status=ApplicationStatus.FAILED,
                        url=task.url,
                        company=task.company,
                        title=task.title,
                        error=str(error),
                    )

        results = await asyncio.gather(*(_run(task) for task in pending))
        return list(results)
