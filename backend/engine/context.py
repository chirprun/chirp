"""Request-of-work correlation for structured logs (run trace ID)."""

from __future__ import annotations

import uuid

import structlog


def bind_run_trace(run_id: str | None = None) -> str:
    """Bind ``run_trace_id`` for structlog context; returns the trace id."""
    tid = run_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(run_trace_id=tid)
    return tid


def unbind_run_trace() -> None:
    structlog.contextvars.unbind_contextvars("run_trace_id")
