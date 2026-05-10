from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.engine.slack_delivery import deliver_slack_alert_recorded
from backend.models import Base, Run, Scenario


@pytest.mark.asyncio
async def test_slack_delivered_after_retry(monkeypatch, tmp_path: Path):
    posts: list[int] = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            posts.append(1)
            req = httpx.Request("POST", url)
            if len(posts) < 2:
                return httpx.Response(503, request=req)
            return httpx.Response(200, request=req)

    monkeypatch.setattr("backend.engine.slack_delivery.httpx.AsyncClient", lambda *a, **k: _Client())

    async def _noop_backoff(_attempt: int) -> None:
        return None

    monkeypatch.setattr("backend.engine.slack_delivery._backoff", _noop_backoff)

    db_url = f"sqlite+aiosqlite:///{tmp_path}/slack.db"
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sid = str(uuid4())
    rid = str(uuid4())
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(
            Scenario(
                id=sid,
                name="s",
                description="",
                agent_endpoint="http://x/run",
                input_payload={},
                schedule_minutes=1,
                scenario_type="standard",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(Run(id=rid, scenario_id=sid, started_at=now, status="FAIL"))
        await session.commit()

    async with factory() as session:
        row = await deliver_slack_alert_recorded(
            session,
            run_id=rid,
            scenario_id=sid,
            webhook_url="https://hooks.slack.example/services/XXX",
            text="hello",
        )
        assert row.status == "delivered"
        assert row.http_status == 200
        assert len(posts) == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_slack_records_failed_on_400(monkeypatch, tmp_path: Path):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            req = httpx.Request("POST", url)
            return httpx.Response(400, text="no", request=req)

    monkeypatch.setattr("backend.engine.slack_delivery.httpx.AsyncClient", lambda *a, **k: _Client())

    async def _noop_backoff(_attempt: int) -> None:
        return None

    monkeypatch.setattr("backend.engine.slack_delivery._backoff", _noop_backoff)

    db_url = f"sqlite+aiosqlite:///{tmp_path}/slack2.db"
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sid = str(uuid4())
    rid = str(uuid4())
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(
            Scenario(
                id=sid,
                name="s",
                description="",
                agent_endpoint="http://x/run",
                input_payload={},
                schedule_minutes=1,
                scenario_type="standard",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(Run(id=rid, scenario_id=sid, started_at=now, status="FAIL"))
        await session.commit()

    async with factory() as session:
        row = await deliver_slack_alert_recorded(
            session,
            run_id=rid,
            scenario_id=sid,
            webhook_url="https://hooks.slack.example/services/XXX",
            text="hello",
        )
        assert row.status == "failed"
        assert row.http_status == 400

    await engine.dispose()
