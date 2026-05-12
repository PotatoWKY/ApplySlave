"""Exponential-backoff retry for flaky operations.

Not every failure is worth retrying — network blips yes, permanent errors
(validation, 4xx) no. Callers classify errors as retryable via `should_retry`.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay_s: float = 1.0,
    max_delay_s: float = 10.0,
    should_retry: Callable[[Exception], bool] | None = None,
) -> T:
    """Run ``operation`` with exponential backoff + jitter.

    Stops early and re-raises if ``should_retry`` returns False.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as error:  # noqa: BLE001
            last_error = error
            if should_retry is not None and not should_retry(error):
                raise
            if attempt == max_attempts:
                break
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay = delay * random.uniform(0.8, 1.2)
            logger.warning(
                "Attempt %s/%s failed (%s); retrying in %.2fs",
                attempt,
                max_attempts,
                error,
                delay,
            )
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error
