from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.engine.quota_ops import month_for_quota
from backend.models import AlertDelivery, AssertionResult, QuotaUsage, Run, Scenario

router = APIRouter(tags=["runs"])


def _run_to_dict(run: Run, assertion_results: list[AssertionResult]) -> dict:
    return {
        "id": run.id,
        "scenario_id": run.scenario_id,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "status": run.status,
        "latency_ms": run.latency_ms,
        "prompt_cost_usd": run.prompt_cost_usd,
        "tool_cost_usd": run.tool_cost_usd,
        "response_cost_usd": run.response_cost_usd,
        "total_cost_usd": run.total_cost_usd,
        "error_message": run.error_message,
        "error_code": run.error_code,
        "assertion_results": [
            {
                "id": result.id,
                "assertion_type": result.assertion_type,
                "passed": result.passed,
                "expected": result.expected,
                "actual": result.actual,
                "detail": result.detail,
                "confidence": result.confidence,
            }
            for result in assertion_results
        ],
    }


@router.get("/api/scenarios/{scenario_id}/runs")
async def list_runs(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    runs = (
        await db.execute(
            select(Run).where(Run.scenario_id == scenario_id).order_by(Run.started_at.desc()).limit(50)
        )
    ).scalars().all()
    run_ids = [run.id for run in runs]
    results = (
        await db.execute(select(AssertionResult).where(AssertionResult.run_id.in_(run_ids)))
    ).scalars().all() if run_ids else []
    grouped: dict[str, list[AssertionResult]] = defaultdict(list)
    for result in results:
        grouped[result.run_id].append(result)
    return [_run_to_dict(run, grouped.get(run.id, [])) for run in runs]


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = (await db.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    results = (await db.execute(select(AssertionResult).where(AssertionResult.run_id == run.id))).scalars().all()
    return _run_to_dict(run, results)


@router.get("/api/scenarios/{scenario_id}/quality-trend")
async def quality_trend(scenario_id: str, db: AsyncSession = Depends(get_db)):
    runs = (
        await db.execute(
            select(Run).where(Run.scenario_id == scenario_id).order_by(Run.started_at.desc()).limit(100)
        )
    ).scalars().all()
    run_ids = [run.id for run in runs]
    results = (
        await db.execute(select(AssertionResult).where(AssertionResult.run_id.in_(run_ids)))
    ).scalars().all() if run_ids else []
    grouped: dict[str, list[AssertionResult]] = defaultdict(list)
    for result in results:
        grouped[result.run_id].append(result)

    points = []
    for run in reversed(runs):
        assertions = grouped.get(run.id, [])
        total = len(assertions)
        passed = len([item for item in assertions if item.passed])
        quality = (passed / total) * 100 if total else (100.0 if run.status == "PASS" else 0.0)
        points.append({"hour": run.started_at.replace(minute=0, second=0, microsecond=0).isoformat(), "quality_score": quality})
    return points


@router.get("/api/scenarios/{scenario_id}/cost-trend")
async def cost_trend(scenario_id: str, db: AsyncSession = Depends(get_db)):
    runs = (
        await db.execute(
            select(Run).where(Run.scenario_id == scenario_id).order_by(Run.started_at.desc()).limit(100)
        )
    ).scalars().all()
    return [
        {
            "run_id": run.id,
            "prompt_cost": run.prompt_cost_usd or 0.0,
            "tool_cost": run.tool_cost_usd or 0.0,
            "response_cost": run.response_cost_usd or 0.0,
        }
        for run in reversed(runs)
    ]


@router.get("/api/scenarios/{scenario_id}/quota")
async def get_scenario_quota(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    month = month_for_quota()
    row = (
        await db.execute(select(QuotaUsage).where(QuotaUsage.scenario_id == scenario_id, QuotaUsage.month == month))
    ).scalar_one_or_none()
    if not row:
        return {
            "scenario_id": scenario_id,
            "month": month,
            "runs_count": 0,
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
    return {
        "scenario_id": scenario_id,
        "month": row.month,
        "runs_count": row.runs_count,
        "total_cost_usd": row.total_cost_usd,
        "total_input_tokens": row.total_input_tokens,
        "total_output_tokens": row.total_output_tokens,
        "updated_at": row.updated_at,
    }


@router.get("/api/scenarios/{scenario_id}/alert-deliveries")
async def list_alert_deliveries(scenario_id: str, db: AsyncSession = Depends(get_db), limit: int = 50):
    scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    cap = max(1, min(limit, 100))
    rows = (
        await db.execute(
            select(AlertDelivery)
            .where(AlertDelivery.scenario_id == scenario_id)
            .order_by(AlertDelivery.created_at.desc())
            .limit(cap)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "channel": r.channel,
            "status": r.status,
            "http_status": r.http_status,
            "error_message": r.error_message,
            "created_at": r.created_at,
            "delivered_at": r.delivered_at,
        }
        for r in rows
    ]
