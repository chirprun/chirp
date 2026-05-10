from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.engine.quota_ops import bump_quota_after_run, month_for_quota
from backend.models import Base, QuotaUsage, Run, Scenario


@pytest.mark.asyncio
async def test_bump_quota_after_run_creates_and_increments(tmp_path: Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/quota.db"
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sid = str(uuid4())
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(
            Scenario(
                id=sid,
                name="q",
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
        await session.commit()

    run_id = str(uuid4())
    async with factory() as session:
        run = Run(
            id=run_id,
            scenario_id=sid,
            started_at=now,
            status="PASS",
            total_cost_usd=0.01,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        await bump_quota_after_run(session, sid, run, 10, 20)
        await session.refresh(run)

    async with factory() as session:
        row = (await session.execute(select(QuotaUsage).where(QuotaUsage.scenario_id == sid))).scalar_one()
        assert row.month == month_for_quota(now)
        assert row.runs_count == 1
        assert row.total_cost_usd == pytest.approx(0.01)
        assert row.total_input_tokens == 10
        assert row.total_output_tokens == 20

    async with factory() as session:
        run2 = Run(
            id=str(uuid4()),
            scenario_id=sid,
            started_at=now,
            status="PASS",
            total_cost_usd=0.02,
        )
        session.add(run2)
        await session.commit()
        await session.refresh(run2)
        await bump_quota_after_run(session, sid, run2, 1, 2)

    async with factory() as session:
        row = (await session.execute(select(QuotaUsage).where(QuotaUsage.scenario_id == sid))).scalar_one()
        assert row.runs_count == 2
        assert row.total_cost_usd == pytest.approx(0.03)
        assert row.total_input_tokens == 11
        assert row.total_output_tokens == 22

    await engine.dispose()


@pytest.mark.asyncio
async def test_bump_quota_skips_non_terminal_status(tmp_path: Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/quota2.db"
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sid = str(uuid4())
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(
            Scenario(
                id=sid,
                name="q",
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
        run = Run(id=str(uuid4()), scenario_id=sid, started_at=now, status="RUNNING", total_cost_usd=0.0)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        await bump_quota_after_run(session, sid, run, 1, 1)

    async with factory() as session:
        rows = (await session.execute(select(QuotaUsage).where(QuotaUsage.scenario_id == sid))).scalars().all()
        assert rows == []

    await engine.dispose()
