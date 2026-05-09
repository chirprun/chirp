from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.engine.alert_policy import evaluate_alert_policy
from backend.engine.assertions import (
    AssertionOutcome,
    evaluate_contains,
    evaluate_cost,
    evaluate_latency,
    evaluate_llm_judge,
    evaluate_tool_sequence,
)
from backend.engine.probes import get_random_probe
from backend.models import AlertPolicy, AssertionResult, Run, Scenario

logger = logging.getLogger(__name__)

STALE_RUN_MAX_AGE = timedelta(minutes=45)
HTTP_MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.35
RETRYABLE_HTTP_STATUS = frozenset({429, 502, 503, 504})


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class AgentRequestFailed(Exception):
    def __init__(self, error_code: str, message: str) -> None:
        self.error_code = error_code
        super().__init__(message)


async def _backoff(attempt: int) -> None:
    delay = BACKOFF_BASE_S * (2**attempt) + random.uniform(0, 0.12)
    await asyncio.sleep(delay)


async def _post_agent_json(url: str, payload: dict) -> dict:
    """POST to agent with bounded retries on transient failures."""
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(HTTP_MAX_ATTEMPTS):
            try:
                response = await client.post(url, json=payload)
                if response.status_code in RETRYABLE_HTTP_STATUS and attempt < HTTP_MAX_ATTEMPTS - 1:
                    logger.warning(
                        "agent_http_retry",
                        extra={"url": url, "status": response.status_code, "attempt": attempt + 1},
                    )
                    await _backoff(attempt)
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in RETRYABLE_HTTP_STATUS and attempt < HTTP_MAX_ATTEMPTS - 1:
                        await _backoff(attempt)
                        continue
                    if exc.response.status_code >= 500:
                        raise AgentRequestFailed("agent_http_5xx", str(exc)) from exc
                    raise AgentRequestFailed("agent_http_4xx", str(exc)) from exc
                try:
                    return response.json()
                except ValueError as exc:
                    raise AgentRequestFailed("agent_invalid_json", f"Invalid JSON from agent: {exc}") from exc
            except httpx.TimeoutException as exc:
                if attempt < HTTP_MAX_ATTEMPTS - 1:
                    logger.warning("agent_timeout_retry", extra={"url": url, "attempt": attempt + 1})
                    await _backoff(attempt)
                    continue
                raise AgentRequestFailed("agent_timeout", str(exc)) from exc
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                if attempt < HTTP_MAX_ATTEMPTS - 1:
                    logger.warning("agent_connection_retry", extra={"url": url, "attempt": attempt + 1})
                    await _backoff(attempt)
                    continue
                raise AgentRequestFailed("agent_connection_error", str(exc)) from exc
    raise AgentRequestFailed("agent_error", "Exceeded HTTP retry attempts")


async def _send_slack_alert(webhook_url: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(webhook_url, json={"text": text})


def _extract_llm_payload(cached: dict, rubric: str, output_text: str) -> AssertionOutcome:
    return AssertionOutcome(
        assertion_type="llm_judge",
        passed=bool(cached.get("passed", False)),
        expected=f"rubric: {rubric}",
        actual=output_text,
        detail=str(cached.get("reason", "Demo cached result")),
        confidence=float(cached.get("confidence", 0.5)),
    )


async def _finalize_stale_and_overlap_runs(db: AsyncSession, scenario_id: str) -> Run | None:
    """
    Mark long-running RUNNING rows as ERROR, then return an active RUNNING run if one remains
    (caller should skip starting a new run).
    """
    now = datetime.now(timezone.utc)
    stale_before = now - STALE_RUN_MAX_AGE
    running_rows = (
        await db.execute(select(Run).where(Run.scenario_id == scenario_id, Run.status == "RUNNING"))
    ).scalars().all()
    for old in running_rows:
        if _utc(old.started_at) < stale_before:
            old.status = "ERROR"
            old.error_code = "stale_run_timeout"
            old.error_message = f"Run exceeded {int(STALE_RUN_MAX_AGE.total_seconds())}s without completion; marked stale."
            old.completed_at = now
            logger.warning(
                "stale_run_reclaimed",
                extra={"run_id": old.id, "scenario_id": scenario_id, "started_at": old.started_at.isoformat()},
            )
    if running_rows:
        await db.commit()

    active = (
        await db.execute(
            select(Run)
            .where(Run.scenario_id == scenario_id, Run.status == "RUNNING")
            .order_by(Run.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if active:
        logger.info("run_overlap_skip", extra={"scenario_id": scenario_id, "active_run_id": active.id})
    return active


async def run_scenario(
    scenario_id: str,
    db: AsyncSession,
    llm_judge,
    demo_cache: dict | None = None,
) -> Run:
    scenario_query = (
        select(Scenario)
        .where(Scenario.id == scenario_id)
        .options(selectinload(Scenario.assertions), selectinload(Scenario.alert_policy))
    )
    scenario = (await db.execute(scenario_query)).scalar_one_or_none()
    if scenario is None:
        raise ValueError(f"Scenario not found: {scenario_id}")

    active = await _finalize_stale_and_overlap_runs(db, scenario_id)
    if active is not None:
        return active

    run = Run(
        scenario_id=scenario.id,
        started_at=datetime.now(timezone.utc),
        status="RUNNING",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    payload = scenario.input_payload or {}
    probe = None
    if scenario.scenario_type == "adversarial":
        probe = get_random_probe()
        payload = {"task": probe["payload"]}

    started = time.perf_counter()
    try:
        parsed = await _post_agent_json(scenario.agent_endpoint, payload)
    except AgentRequestFailed as exc:
        run.status = "ERROR"
        run.error_code = exc.error_code
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        await db.commit()
        await db.refresh(run)
        return run

    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.raw_response = parsed

    output_text = str(parsed.get("output", ""))
    usage = parsed.get("usage", {}) or {}
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    tool_calls = parsed.get("tool_calls", []) or []
    tool_names = [call.get("name", "") for call in tool_calls if isinstance(call, dict)]

    prompt_cost = input_tokens * 0.000003
    response_cost = output_tokens * 0.000015
    tool_cost = float(parsed.get("tool_cost_usd", 0.0) or 0.0)
    total_cost = prompt_cost + tool_cost + response_cost
    run.prompt_cost_usd = prompt_cost
    run.tool_cost_usd = tool_cost
    run.response_cost_usd = response_cost
    run.total_cost_usd = total_cost

    assertion_outcomes: list[AssertionOutcome] = []
    for assertion in scenario.assertions:
        if not assertion.is_active:
            continue
        assertion_type = assertion.assertion_type
        config = assertion.config or {}
        if assertion_type == "latency_ms":
            assertion_outcomes.append(evaluate_latency(run.latency_ms or 0, int(config.get("threshold_ms", 3000))))
        elif assertion_type == "cost_usd":
            assertion_outcomes.append(evaluate_cost(input_tokens, output_tokens, float(config.get("threshold_usd", 0.05))))
        elif assertion_type == "output_contains":
            assertion_outcomes.append(evaluate_contains(output_text, str(config.get("keyword", ""))))
        elif assertion_type == "tool_call_sequence":
            assertion_outcomes.append(
                evaluate_tool_sequence(tool_names, list(config.get("expected_sequence", [])))
            )
        elif assertion_type == "llm_judge":
            rubric = str(config.get("rubric", ""))
            if probe:
                rubric = probe["pass_condition"]
            if demo_cache and scenario_id in demo_cache:
                outcome = _extract_llm_payload(demo_cache[scenario_id], rubric, output_text)
            else:
                outcome = await evaluate_llm_judge(output_text, rubric, llm_judge)
            assertion_outcomes.append(outcome)
        else:
            logger.warning("Unknown assertion type", extra={"assertion_type": assertion_type})

    for outcome in assertion_outcomes:
        db.add(
            AssertionResult(
                run_id=run.id,
                assertion_type=outcome.assertion_type,
                passed=outcome.passed,
                expected=outcome.expected,
                actual=outcome.actual,
                detail=outcome.detail,
                confidence=outcome.confidence,
            )
        )
    await db.commit()

    all_passed = all(item.passed for item in assertion_outcomes) if assertion_outcomes else True
    run.status = "PASS" if all_passed else "FAIL"
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)

    policy = scenario.alert_policy
    if policy:
        recent_runs = (
            await db.execute(
                select(Run).where(Run.scenario_id == scenario.id).order_by(Run.started_at.asc()).limit(20)
            )
        ).scalars().all()
        recent_results: list[list[AssertionResult]] = []
        for recent_run in recent_runs:
            results = (
                await db.execute(select(AssertionResult).where(AssertionResult.run_id == recent_run.id))
            ).scalars().all()
            recent_results.append(results)
        alert_decision = evaluate_alert_policy(recent_runs, policy, recent_results)
        if alert_decision.should_alert and scenario.slack_webhook_url:
            failed = [outcome.assertion_type for outcome in assertion_outcomes if not outcome.passed]
            text = (
                f"🚨 Chirp Alert: {scenario.name}\n"
                f"Status: FAIL ({alert_decision.reason})\n"
                f"Failed: {failed}\n"
                f"Latency: {run.latency_ms}ms | Cost: ${run.total_cost_usd:.4f}"
            )
            try:
                await _send_slack_alert(scenario.slack_webhook_url, text)
            except Exception as exc:  # pragma: no cover
                logger.warning("Slack alert failed", exc_info=exc)

    return run
