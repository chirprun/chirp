"""Bounded retries for LLM judge provider calls (rate limits / transient errors)."""

from __future__ import annotations

import asyncio
import random
from typing import Any

JUDGE_MAX_ATTEMPTS = 3
JUDGE_BACKOFF_BASE_S = 0.3


def _is_transient_judge_error(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.TimeoutError):
        return True
    mod = type(exc).__module__
    name = type(exc).__name__
    if mod.startswith("openai.") and name in (
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
    ):
        return True
    if mod.startswith("anthropic.") and name in (
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
    ):
        return True
    status = getattr(exc, "status_code", None)
    if status is not None and int(status) in {429, 502, 503, 504}:
        return True
    msg = str(exc).lower()
    if "429" in msg or "502" in msg or "503" in msg or "504" in msg or "rate limit" in msg:
        return True
    return False


async def judge_complete_with_retry(judge: Any, prompt: str, *, timeout_s: float = 12.0) -> str:
    """Call ``judge.complete(prompt)`` with wait_for + retries on transient failures."""
    last: BaseException | None = None
    for attempt in range(JUDGE_MAX_ATTEMPTS):
        try:
            return await asyncio.wait_for(judge.complete(prompt), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            last = exc
            if attempt >= JUDGE_MAX_ATTEMPTS - 1:
                raise
        except Exception as exc:
            last = exc
            if not _is_transient_judge_error(exc) or attempt >= JUDGE_MAX_ATTEMPTS - 1:
                raise
        delay = JUDGE_BACKOFF_BASE_S * (2**attempt) + random.uniform(0, 0.1)
        await asyncio.sleep(delay)
    assert last is not None
    raise last
