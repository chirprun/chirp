from __future__ import annotations

from prometheus_client import REGISTRY, generate_latest

from backend.observability.metrics import observe_run_completion


def _pass_total(blob: bytes) -> float:
    for line in blob.splitlines():
        if (
            line.startswith(b"chirp_runs_total")
            and b'status="PASS"' in line
            and not line.startswith(b"#")
        ):
            return float(line.split()[-1])
    return 0.0


def test_observe_run_completion_increments_pass_counter():
    before = _pass_total(generate_latest(REGISTRY))
    observe_run_completion("PASS")
    after = _pass_total(generate_latest(REGISTRY))
    assert after == before + 1.0
