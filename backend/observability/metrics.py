"""Prometheus metrics (import side effects: registers collectors on first import)."""

from __future__ import annotations

from prometheus_client import Counter

RUNS_TOTAL = Counter(
    "chirp_runs_total",
    "Completed synthetic runs by terminal status",
    labelnames=("status",),
)


def observe_run_completion(status: str) -> None:
    RUNS_TOTAL.labels(status=status.upper()).inc()
