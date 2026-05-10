from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


async def _noop_start_scheduler(*_a, **_k) -> None:
    return None


def _reload_chirp_app(tmp_path, monkeypatch, **extra_env: str) -> object:
    """Rebuild backend modules so env (DB URL, rate limits, metrics) and routers pick up test config."""
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/chirp_test.sqlite")
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    monkeypatch.delenv("CHIRP_DISABLE_RATE_LIMIT", raising=False)
    for k, v in extra_env.items():
        monkeypatch.setenv(k, v)

    import backend.database as db_mod
    import backend.engine.scheduler as sched_mod
    import backend.main as main_mod
    import backend.mcp_chirp as mcp_mod
    import backend.rate_limit as rl_mod
    import backend.routers.runs as runs_mod
    import backend.routers.scenarios as scenarios_mod

    if sched_mod.scheduler.running:
        try:
            sched_mod.scheduler.shutdown(wait=False)
        except Exception:
            pass
    monkeypatch.setattr(sched_mod, "start_scheduler", _noop_start_scheduler)

    importlib.reload(db_mod)
    importlib.reload(rl_mod)
    importlib.reload(scenarios_mod)
    importlib.reload(runs_mod)
    importlib.reload(mcp_mod)
    importlib.reload(main_mod)
    return main_mod


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    return _reload_chirp_app(tmp_path, monkeypatch)


def test_health_and_quota_and_deliveries(demo_app, monkeypatch):
    import backend.routers.scenarios as scenarios_mod

    async def _fake_run(*_a, **_k):
        class _R:
            id = "run-fake-1"

        return _R()

    monkeypatch.setattr(scenarios_mod, "run_scenario", _fake_run)

    with TestClient(demo_app.app) as client:
        assert client.get("/api/health").status_code == 200
        rows = client.get("/api/scenarios").json()
        assert len(rows) >= 1
        sid = rows[0]["id"]
        q = client.get(f"/api/scenarios/{sid}/quota").json()
        assert q["scenario_id"] == sid
        assert "runs_count" in q
        d = client.get(f"/api/scenarios/{sid}/alert-deliveries").json()
        assert isinstance(d, list)


def test_metrics_disabled_returns_404(demo_app):
    with TestClient(demo_app.app) as client:
        assert client.get("/metrics").status_code == 404


def test_metrics_enabled_returns_prometheus(tmp_path, monkeypatch):
    main_mod = _reload_chirp_app(tmp_path, monkeypatch, METRICS_ENABLED="true")
    with TestClient(main_mod.app) as client:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert b"chirp_runs_total" in r.content


def test_trigger_rate_limit_returns_429(tmp_path, monkeypatch):
    main_mod = _reload_chirp_app(tmp_path, monkeypatch, CHIRP_TRIGGER_RATE_LIMIT="2/minute")
    import backend.routers.scenarios as scenarios_mod

    async def _fake_run(sid, _db, _llm_judge):
        now = datetime.now(timezone.utc)

        class _R:
            id = "run-fake-rl"
            scenario_id = sid
            status = "PASS"
            started_at = now
            completed_at = now

        return _R()

    monkeypatch.setattr(scenarios_mod, "run_scenario", _fake_run)

    with TestClient(main_mod.app) as client:
        rows = client.get("/api/scenarios").json()
        sid = rows[0]["id"]
        assert client.post(f"/api/scenarios/{sid}/trigger").status_code == 200
        assert client.post(f"/api/scenarios/{sid}/trigger").status_code == 200
        r3 = client.post(f"/api/scenarios/{sid}/trigger")
        assert r3.status_code == 429
