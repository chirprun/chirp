"""API rate limits (SlowAPI). Disabled when ``CHIRP_DISABLE_RATE_LIMIT`` is truthy (e.g. tests)."""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_enabled() -> bool:
    return os.getenv("CHIRP_DISABLE_RATE_LIMIT", "").lower() not in ("1", "true", "yes")


def trigger_limit_string() -> str:
    return os.getenv("CHIRP_TRIGGER_RATE_LIMIT", "120/minute")


limiter = Limiter(key_func=get_remote_address, enabled=_rate_limit_enabled())
