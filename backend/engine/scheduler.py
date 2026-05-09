from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from backend.engine.runner import run_scenario
from backend.models import Scenario

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _build_job(scenario_id: str, db_factory, llm_judge):
    async def _job():
        async with db_factory() as db:
            await run_scenario(scenario_id, db, llm_judge)

    return _job


async def start_scheduler(db_factory, llm_judge):
    async with db_factory() as db:
        scenarios = (
            await db.execute(select(Scenario).where(Scenario.is_active.is_(True)))
        ).scalars().all()

    for scenario in scenarios:
        scheduler.add_job(
            _build_job(scenario.id, db_factory, llm_judge),
            trigger="interval",
            minutes=scenario.schedule_minutes,
            id=scenario.id,
            replace_existing=True,
        )
    if not scheduler.running:
        scheduler.start()
    logger.info("Scheduler started with scenarios", extra={"count": len(scenarios)})


async def reschedule_scenario(scenario, db_factory, llm_judge):
    try:
        scheduler.remove_job(scenario.id)
    except Exception:
        pass

    if scenario.is_active:
        scheduler.add_job(
            _build_job(scenario.id, db_factory, llm_judge),
            trigger="interval",
            minutes=scenario.schedule_minutes,
            id=scenario.id,
            replace_existing=True,
        )
    logger.info("Scenario rescheduled", extra={"scenario_id": scenario.id, "is_active": scenario.is_active})
