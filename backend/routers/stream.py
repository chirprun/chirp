from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.engine.runner import run_scenario
from backend.models import AssertionResult, Scenario
from backend.routers.runs import _run_to_dict

router = APIRouter(tags=["stream"])


@router.get("/api/scenarios/{scenario_id}/check-stream")
async def scenario_check_stream(
    scenario_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Server-Sent Events while a scenario check runs: ``thinking`` then ``response``.

    Event payload is JSON: ``{"phase": "thinking"|"response", ...}``.
    """
    scenario = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    llm_judge = getattr(request.app.state, "llm_judge", None)

    async def events() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'phase': 'thinking', 'message': 'Running scenario check…', 'scenario_id': scenario_id})}\n\n"
        run = await run_scenario(scenario_id, db, llm_judge)
        results = (await db.execute(select(AssertionResult).where(AssertionResult.run_id == run.id))).scalars().all()
        body = _run_to_dict(run, list(results))
        yield f"data: {json.dumps({'phase': 'response', 'run': body}, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
