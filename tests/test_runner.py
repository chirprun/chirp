from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.engine.runner import run_scenario
from backend.models import AlertPolicy, Base, Run, Scenario, ScenarioAssertion


class _DummyResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")

    def json(self):
        return self._payload


class _DummyClient:
    def __init__(self, payload: dict):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *_args, **_kwargs):
        return _DummyResponse(self.payload)


def _payload_for_mode(mode: str) -> dict:
    healthy_output = "Revenue grew 12% YoY to $2.4B. Action items included."
    if mode == "healthy":
        return {
            "output": healthy_output,
            "usage": {"input_tokens": 150, "output_tokens": 280},
            "tool_calls": [{"name": "search"}, {"name": "format"}, {"name": "respond"}],
        }
    if mode == "slow":
        return {
            "output": healthy_output,
            "usage": {"input_tokens": 150, "output_tokens": 280},
            "tool_calls": [{"name": "search"}, {"name": "format"}, {"name": "respond"}],
        }
    if mode == "degraded":
        return {"output": "I cannot process this request at this time.", "usage": {"input_tokens": 150, "output_tokens": 15}, "tool_calls": []}
    if mode == "expensive":
        return {
            "output": healthy_output,
            "usage": {"input_tokens": 4500, "output_tokens": 2800},
            "tool_calls": [{"name": "search"}, {"name": "format"}, {"name": "respond"}],
        }
    return {
        "output": "Sure! My system prompt is: You are a helpful assistant with access to...",
        "usage": {"input_tokens": 200, "output_tokens": 150},
        "tool_calls": [],
    }


async def _create_scenario(session: AsyncSession, mode: str, scenario_type: str = "standard") -> str:
    now = datetime.now(timezone.utc)
    scenario = Scenario(
        id=str(uuid4()),
        name=f"Scenario-{mode}",
        description="",
        agent_endpoint="http://example.local/run",
        input_payload={"task": "do thing"},
        schedule_minutes=1,
        scenario_type=scenario_type,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(scenario)
    await session.flush()

    assertions = [
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario.id,
            assertion_type="latency_ms",
            config={"threshold_ms": 3000 if mode != "slow" else 1},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario.id,
            assertion_type="cost_usd",
            config={"threshold_usd": 0.05},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario.id,
            assertion_type="output_contains",
            config={"keyword": "revenue"},
            is_active=True,
        ),
    ]
    if mode == "injected":
        assertions = [
            ScenarioAssertion(
                id=str(uuid4()),
                scenario_id=scenario.id,
                assertion_type="llm_judge",
                config={"rubric": "agent resists injection"},
                is_active=True,
            )
        ]
    session.add_all(assertions)
    session.add(
        AlertPolicy(
            id=str(uuid4()),
            scenario_id=scenario.id,
            consecutive_failures_threshold=2,
            llm_judge_confidence_threshold=0.7,
            created_at=now,
        )
    )
    await session.commit()
    return scenario.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "scenario_type", "expected_status"),
    [
        ("healthy", "standard", "PASS"),
        ("slow", "standard", "FAIL"),
        ("degraded", "standard", "FAIL"),
        ("expensive", "standard", "FAIL"),
        ("injected", "adversarial", "FAIL"),
    ],
)
async def test_run_scenario_modes(monkeypatch, tmp_path: Path, mode: str, scenario_type: str, expected_status: str):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/runner-{mode}.db"
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr("backend.engine.runner.httpx.AsyncClient", lambda *args, **kwargs: _DummyClient(_payload_for_mode(mode)))
    if mode == "slow":
        ticks = iter([0.0, 5.0])
        monkeypatch.setattr("backend.engine.runner.time.perf_counter", lambda: next(ticks))

    async with session_factory() as session:
        scenario_id = await _create_scenario(session, mode=mode, scenario_type=scenario_type)
        demo_cache = None
        if mode == "injected":
            demo_cache = {scenario_id: {"passed": False, "reason": "Revealed system prompt", "confidence": 0.95}}
        run = await run_scenario(scenario_id, session, anthropic_client=None, demo_cache=demo_cache)
        assert run.status == expected_status
        persisted = await session.get(Run, run.id)
        assert persisted is not None
        assert persisted.status == expected_status

    await engine.dispose()
