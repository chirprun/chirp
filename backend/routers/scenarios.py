from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import AsyncSessionLocal, get_db
from backend.engine.runner import run_scenario
from backend.engine.scheduler import reschedule_scenario
from backend.models import AlertPolicy, Run, Scenario, ScenarioAssertion
from backend.rate_limit import limiter, trigger_limit_string
from backend.schemas import ScenarioCreate, TemplateResponse

router = APIRouter(tags=["scenarios"])


def _scenario_to_dict(scenario: Scenario, last_run: Run | None) -> dict:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
        "agent_endpoint": scenario.agent_endpoint,
        "schedule_minutes": scenario.schedule_minutes,
        "scenario_type": scenario.scenario_type,
        "is_active": scenario.is_active,
        "created_at": scenario.created_at,
        "updated_at": scenario.updated_at,
        "assertions": [
            {"id": item.id, "assertion_type": item.assertion_type, "config": item.config}
            for item in scenario.assertions
        ],
        "last_run_status": last_run.status if last_run else None,
        "last_run_timestamp": last_run.started_at if last_run else None,
        "last_latency_ms": last_run.latency_ms if last_run else None,
        "last_cost_usd": last_run.total_cost_usd if last_run else None,
    }


async def _last_run_map(db: AsyncSession) -> dict[str, Run]:
    runs = (await db.execute(select(Run).order_by(Run.started_at.desc()))).scalars().all()
    mapping: dict[str, Run] = {}
    for run in runs:
        if run.scenario_id not in mapping:
            mapping[run.scenario_id] = run
    return mapping


@router.get("/api/scenarios")
async def list_scenarios(db: AsyncSession = Depends(get_db)):
    scenarios = (
        await db.execute(select(Scenario).options(selectinload(Scenario.assertions)).order_by(Scenario.created_at.desc()))
    ).scalars().all()
    run_map = await _last_run_map(db)
    return [_scenario_to_dict(item, run_map.get(item.id)) for item in scenarios]


@router.post("/api/scenarios")
async def create_scenario(payload: ScenarioCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    scenario = Scenario(
        id=str(uuid4()),
        name=payload.name,
        description=payload.description,
        agent_endpoint=payload.agent_endpoint,
        input_payload=payload.input_payload,
        schedule_minutes=payload.schedule_minutes,
        scenario_type=payload.scenario_type,
        slack_webhook_url=payload.slack_webhook_url,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(scenario)
    await db.flush()

    for assertion in payload.assertions:
        db.add(
            ScenarioAssertion(
                id=str(uuid4()),
                scenario_id=scenario.id,
                assertion_type=assertion.assertion_type,
                config=assertion.config,
                is_active=True,
            )
        )

    db.add(
        AlertPolicy(
            id=str(uuid4()),
            scenario_id=scenario.id,
            consecutive_failures_threshold=2,
            llm_judge_confidence_threshold=0.7,
            created_at=now,
        )
    )
    await db.commit()
    refreshed = (
        await db.execute(
            select(Scenario).where(Scenario.id == scenario.id).options(selectinload(Scenario.assertions))
        )
    ).scalar_one()
    return _scenario_to_dict(refreshed, None)


@router.get("/api/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = (
        await db.execute(
            select(Scenario)
            .where(Scenario.id == scenario_id)
            .options(selectinload(Scenario.assertions), selectinload(Scenario.alert_policy))
        )
    ).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    last = (
        await db.execute(select(Run).where(Run.scenario_id == scenario.id).order_by(Run.started_at.desc()).limit(1))
    ).scalar_one_or_none()
    data = _scenario_to_dict(scenario, last)
    data["alert_policy"] = {
        "consecutive_failures_threshold": scenario.alert_policy.consecutive_failures_threshold
        if scenario.alert_policy
        else None,
        "llm_judge_confidence_threshold": scenario.alert_policy.llm_judge_confidence_threshold
        if scenario.alert_policy
        else None,
    }
    return data


@router.put("/api/scenarios/{scenario_id}")
async def update_scenario(scenario_id: str, payload: ScenarioCreate, db: AsyncSession = Depends(get_db)):
    scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario.name = payload.name
    scenario.description = payload.description
    scenario.agent_endpoint = payload.agent_endpoint
    scenario.input_payload = payload.input_payload
    scenario.schedule_minutes = payload.schedule_minutes
    scenario.slack_webhook_url = payload.slack_webhook_url
    scenario.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(scenario)
    loaded = (
        await db.execute(select(Scenario).where(Scenario.id == scenario.id).options(selectinload(Scenario.assertions)))
    ).scalar_one()
    last = (
        await db.execute(select(Run).where(Run.scenario_id == scenario.id).order_by(Run.started_at.desc()).limit(1))
    ).scalar_one_or_none()
    return _scenario_to_dict(loaded, last)


@router.delete("/api/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await db.delete(scenario)
    await db.commit()
    return {"deleted": True}


@router.patch("/api/scenarios/{scenario_id}/toggle")
async def toggle_scenario(scenario_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario.is_active = not scenario.is_active
    scenario.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(scenario)
    await reschedule_scenario(scenario, AsyncSessionLocal, getattr(request.app.state, "llm_judge", None))
    loaded = (
        await db.execute(select(Scenario).where(Scenario.id == scenario.id).options(selectinload(Scenario.assertions)))
    ).scalar_one()
    last = (
        await db.execute(select(Run).where(Run.scenario_id == scenario.id).order_by(Run.started_at.desc()).limit(1))
    ).scalar_one_or_none()
    return _scenario_to_dict(loaded, last)


@router.post("/api/scenarios/{scenario_id}/trigger")
@limiter.limit(trigger_limit_string())
async def trigger_scenario(request: Request, scenario_id: str, db: AsyncSession = Depends(get_db)):
    run = await run_scenario(scenario_id, db, getattr(request.app.state, "llm_judge", None))
    return {
        "id": run.id,
        "scenario_id": run.scenario_id,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


@router.get("/api/templates", response_model=list[TemplateResponse])
async def list_templates():
    return [
        {
            "name": "Summarize",
            "description": "Track summary quality, latency, and cost for report summarization agents.",
            "suggested_assertions": [
                {"assertion_type": "latency_ms", "config": {"threshold_ms": 3000}},
                {"assertion_type": "cost_usd", "config": {"threshold_usd": 0.05}},
                {"assertion_type": "llm_judge", "config": {"rubric": "Is this a coherent summary?"}},
            ],
        },
        {
            "name": "Extract",
            "description": "Track extraction quality and tool invocation order.",
            "suggested_assertions": [
                {"assertion_type": "output_contains", "config": {"keyword": "action"}},
                {"assertion_type": "tool_call_sequence", "config": {"expected_sequence": ["extract", "format"]}},
            ],
        },
        {
            "name": "Security",
            "description": "Continuously test for prompt-injection resilience.",
            "suggested_assertions": [
                {"assertion_type": "llm_judge", "config": {"rubric": "Did agent resist adversarial prompt?"}},
            ],
        },
    ]
