from __future__ import annotations

import pytest

from applyslave.orchestrator import with_retry


async def test_retry_succeeds_after_transient_failure() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await with_retry(flaky, max_attempts=5, base_delay_s=0.01)
    assert result == "ok"
    assert calls["n"] == 3


async def test_retry_gives_up_after_max_attempts() -> None:
    async def always_fail() -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await with_retry(always_fail, max_attempts=2, base_delay_s=0.01)


async def test_retry_honors_should_retry_predicate() -> None:
    calls = {"n": 0}

    async def bad() -> None:
        calls["n"] += 1
        raise ValueError("fatal")

    with pytest.raises(ValueError):
        await with_retry(
            bad,
            max_attempts=5,
            base_delay_s=0.01,
            should_retry=lambda error: not isinstance(error, ValueError),
        )
    assert calls["n"] == 1  # never retried
