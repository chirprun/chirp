from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.engine.runner import run_scenario
from backend.models import AlertPolicy, Base, Run, Scenario, ScenarioAssertion


def _healthy_json() -> dict:
    return {
        "output": "Revenue grew 12% YoY to $2.4B.",
        "usage": {"input_tokens": 150, "output_tokens": 280},
        "tool_calls": [{"name": "search"}, {"name": "format"}],
    }


async def _minimal_scenario(session: AsyncSession) -> str:
    now = datetime.now(timezone.utc)
    sid = str(uuid4())
    session.add(
        Scenario(
            id=sid,
            name="overlap-test",
            description="",
            agent_endpoint="http://example.local/run",
            input_payload={"task": "x"},
            schedule_minutes=1,
            scenario_type="standard",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    session.add_all(
        [
            ScenarioAssertion(
                id=str(uuid4()),
                scenario_id=sid,
                assertion_type="latency_ms",
                config={"threshold_ms": 5000},
                is_active=True,
            ),
        ]
    )
    session.add(
        AlertPolicy(
            id=str(uuid4()),
            scenario_id=sid,
            consecutive_failures_threshold=2,
            llm_judge_confidence_threshold=0.7,
            created_at=now,
        )
    )
    await session.commit()
    return sid


@pytest.mark.asyncio
async def test_run_overlap_returns_active_run_without_http(tmp_path: Path, monkeypatch):
    posts: list[int] = []

    class _CountingDummy:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_a, **_k):
            posts.append(1)
            req = httpx.Request("POST", "http://example.local/run")
            return httpx.Response(200, json=_healthy_json(), request=req)

    monkeypatch.setattr("backend.engine.runner.httpx.AsyncClient", lambda *a, **k: _CountingDummy())

    db_url = f"sqlite+aiosqlite:///{tmp_path}/overlap.db"
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        sid = await _minimal_scenario(session)
        existing = Run(
            id=str(uuid4()),
            scenario_id=sid,
            started_at=datetime.now(timezone.utc),
            status="RUNNING",
        )
        session.add(existing)
        await session.commit()
        await session.refresh(existing)

        out = await run_scenario(sid, session, llm_judge=None)
        assert out.id == existing.id
        assert posts == []


@pytest.mark.asyncio
async def test_stale_running_run_is_reclaimed_then_new_run(tmp_path: Path, monkeypatch):
    class _Dummy:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_a, **_k):
            req = httpx.Request("POST", "http://example.local/run")
            return httpx.Response(200, json=_healthy_json(), request=req)

    monkeypatch.setattr("backend.engine.runner.httpx.AsyncClient", lambda *a, **k: _Dummy())

    db_url = f"sqlite+aiosqlite:///{tmp_path}/stale.db"
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        sid = await _minimal_scenario(session)
        old = Run(
            id=str(uuid4()),
            scenario_id=sid,
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            status="RUNNING",
        )
        session.add(old)
        await session.commit()

        out = await run_scenario(sid, session, llm_judge=None)
        assert out.id != old.id
        assert out.status == "PASS"
        await session.refresh(old)
        assert old.status == "ERROR"
        assert old.error_code == "stale_run_timeout"

    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_http_retries_on_503(tmp_path: Path, monkeypatch):
    attempts = {"n": 0}

    class _Flaky:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_a, **_k):
            attempts["n"] += 1
            req = httpx.Request("POST", "http://example.local/run")
            if attempts["n"] < 2:
                return httpx.Response(503, request=req)
            return httpx.Response(200, json=_healthy_json(), request=req)

    monkeypatch.setattr("backend.engine.runner.httpx.AsyncClient", lambda *a, **k: _Flaky())
    async def _noop(_attempt: int) -> None:
        return None

    monkeypatch.setattr("backend.engine.runner._backoff", _noop)

    db_url = f"sqlite+aiosqlite:///{tmp_path}/retry.db"
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        sid = await _minimal_scenario(session)
        out = await run_scenario(sid, session, llm_judge=None)
        assert out.status == "PASS"
        assert attempts["n"] == 2

    await engine.dispose()
