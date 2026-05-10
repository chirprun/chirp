from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.engine import judge_retry
from backend.engine.judge_retry import judge_complete_with_retry


@pytest.mark.parametrize(
    ("exc", "transient"),
    [
        (asyncio.TimeoutError(), True),
        (RuntimeError("429 rate limit"), True),
        (RuntimeError("503 unavailable"), True),
        (RuntimeError("bad request 400"), False),
    ],
)
def test_is_transient_judge_error(exc, transient):
    assert judge_retry._is_transient_judge_error(exc) is transient


def test_is_transient_status_code_attr():
    class Err(Exception):
        status_code = 401

    assert judge_retry._is_transient_judge_error(Err("x")) is False

    class Rate(Exception):
        status_code = 429

    assert judge_retry._is_transient_judge_error(Rate("x")) is True


@pytest.mark.asyncio
async def test_judge_complete_with_retry_succeeds_after_transient(monkeypatch):
    monkeypatch.setattr("backend.engine.judge_retry.asyncio.sleep", AsyncMock())

    class _Judge:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, prompt: str) -> str:
            self.calls += 1
            if self.calls < 2:

                class _503(Exception):
                    status_code = 503

                raise _503("retry me")
            return '{"pass": true, "reason": "ok"}'

    judge = _Judge()
    out = await judge_complete_with_retry(judge, "p", timeout_s=2.0)
    assert "pass" in out
    assert judge.calls == 2


@pytest.mark.asyncio
async def test_judge_complete_with_retry_non_transient_raises(monkeypatch):
    monkeypatch.setattr("backend.engine.judge_retry.asyncio.sleep", AsyncMock())

    class _Judge:
        async def complete(self, prompt: str) -> str:
            raise ValueError("not transient")

    with pytest.raises(ValueError, match="not transient"):
        await judge_complete_with_retry(_Judge(), "p", timeout_s=2.0)
