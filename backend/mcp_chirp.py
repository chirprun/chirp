"""
Chirp MCP surface: tools and resources mirror REST monitoring APIs.

Mounted at ``/mcp/`` (streamable HTTP; ``/mcp`` redirects here). Configure the LLM judge getter from
``backend.main`` after ``app.state.llm_judge`` is set.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from mcp.server.fastmcp import FastMCP

from backend.database import AsyncSessionLocal
from backend.engine.runner import run_scenario
from backend.models import AssertionResult, Run, Scenario
from backend.routers.runs import _run_to_dict
from backend.routers.scenarios import _last_run_map, _scenario_to_dict

_llm_judge_getter: Callable[[], Any] | None = None


def set_mcp_llm_judge_getter(getter: Callable[[], Any] | None) -> None:
    """Called from FastAPI startup so MCP tools use the same judge as HTTP routes."""
    global _llm_judge_getter
    _llm_judge_getter = getter


def _judge() -> Any:
    if _llm_judge_getter is None:
        return None
    return _llm_judge_getter()


def _json(data: Any) -> str:
    return json.dumps(data, default=str, indent=2)


def build_chirp_mcp() -> FastMCP:
    """Build FastMCP with streamable HTTP root path for mounting at ``/mcp/``."""
    mcp = FastMCP(
        "Chirp",
        instructions=(
            "Chirp synthetic monitoring for AI agents. "
            "Use chirp_list_scenarios / chirp_get_scenario to inspect definitions; "
            "chirp_check runs a full scheduled-style check (HTTP agent + assertions); "
            "chirp_get_run / chirp_list_runs read evidence."
        ),
        streamable_http_path="/",
        stateless_http=True,
    )

    @mcp.tool(name="chirp_list_scenarios", description="List all monitoring scenarios with last-run summary.")
    async def chirp_list_scenarios() -> str:
        async with AsyncSessionLocal() as db:
            scenarios = (
                await db.execute(
                    select(Scenario).options(selectinload(Scenario.assertions)).order_by(Scenario.created_at.desc())
                )
            ).scalars().all()
            run_map = await _last_run_map(db)
            rows = [_scenario_to_dict(s, run_map.get(s.id)) for s in scenarios]
        return _json(rows)

    @mcp.tool(name="chirp_get_scenario", description="Get one scenario by id, including assertions and alert policy.")
    async def chirp_get_scenario(scenario_id: str) -> str:
        async with AsyncSessionLocal() as db:
            scenario = (
                await db.execute(
                    select(Scenario)
                    .where(Scenario.id == scenario_id)
                    .options(selectinload(Scenario.assertions), selectinload(Scenario.alert_policy))
                )
            ).scalar_one_or_none()
            if not scenario:
                return _json({"error": "not_found", "scenario_id": scenario_id})
            last = (
                await db.execute(
                    select(Run).where(Run.scenario_id == scenario.id).order_by(Run.started_at.desc()).limit(1)
                )
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
        return _json(data)

    @mcp.tool(
        name="chirp_check",
        description="Run a full check for a scenario (same as POST /api/scenarios/{id}/trigger): agent HTTP call plus assertions.",
    )
    async def chirp_check(scenario_id: str) -> str:
        async with AsyncSessionLocal() as db:
            scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
            if not scenario:
                return _json({"error": "not_found", "scenario_id": scenario_id})
            run = await run_scenario(scenario_id, db, _judge())
            results = (await db.execute(select(AssertionResult).where(AssertionResult.run_id == run.id))).scalars().all()
        return _json(_run_to_dict(run, list(results)))

    @mcp.tool(name="chirp_get_run", description="Load a single run with assertion results by run id.")
    async def chirp_get_run(run_id: str) -> str:
        async with AsyncSessionLocal() as db:
            run = (await db.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
            if not run:
                return _json({"error": "not_found", "run_id": run_id})
            results = (await db.execute(select(AssertionResult).where(AssertionResult.run_id == run.id))).scalars().all()
        return _json(_run_to_dict(run, list(results)))

    @mcp.tool(name="chirp_list_runs", description="List recent runs for a scenario (newest first, capped).")
    async def chirp_list_runs(scenario_id: str, limit: int = 20) -> str:
        cap = max(1, min(limit, 50))
        async with AsyncSessionLocal() as db:
            scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
            if not scenario:
                return _json({"error": "not_found", "scenario_id": scenario_id})
            runs = (
                await db.execute(
                    select(Run).where(Run.scenario_id == scenario_id).order_by(Run.started_at.desc()).limit(cap)
                )
            ).scalars().all()
            run_ids = [r.id for r in runs]
            results = (
                (await db.execute(select(AssertionResult).where(AssertionResult.run_id.in_(run_ids)))).scalars().all()
                if run_ids
                else []
            )
            grouped: dict[str, list[AssertionResult]] = defaultdict(list)
            for res in results:
                grouped[res.run_id].append(res)
            rows = [_run_to_dict(r, grouped.get(r.id, [])) for r in runs]
        return _json(rows)

    @mcp.resource("chirp://scenarios", mime_type="application/json", description="All scenarios as JSON.")
    async def resource_scenarios() -> str:
        async with AsyncSessionLocal() as db:
            scenarios = (
                await db.execute(
                    select(Scenario).options(selectinload(Scenario.assertions)).order_by(Scenario.created_at.desc())
                )
            ).scalars().all()
            run_map = await _last_run_map(db)
            rows = [_scenario_to_dict(s, run_map.get(s.id)) for s in scenarios]
        return _json(rows)

    @mcp.resource("chirp://scenario/{scenario_id}", mime_type="application/json", description="One scenario by id.")
    async def resource_scenario(scenario_id: str) -> str:
        async with AsyncSessionLocal() as db:
            scenario = (
                await db.execute(
                    select(Scenario)
                    .where(Scenario.id == scenario_id)
                    .options(selectinload(Scenario.assertions), selectinload(Scenario.alert_policy))
                )
            ).scalar_one_or_none()
            if not scenario:
                return _json({"error": "not_found", "scenario_id": scenario_id})
            last = (
                await db.execute(
                    select(Run).where(Run.scenario_id == scenario.id).order_by(Run.started_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            data = _scenario_to_dict(scenario, last)
            if scenario.alert_policy:
                data["alert_policy"] = {
                    "consecutive_failures_threshold": scenario.alert_policy.consecutive_failures_threshold,
                    "llm_judge_confidence_threshold": scenario.alert_policy.llm_judge_confidence_threshold,
                }
        return _json(data)

    return mcp


chirp_mcp = build_chirp_mcp()
