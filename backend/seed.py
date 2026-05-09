from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AlertPolicy, Scenario, ScenarioAssertion

logger = logging.getLogger(__name__)


async def seed_demo_scenarios(db: AsyncSession):
    existing = (await db.execute(select(Scenario.id).limit(1))).scalar_one_or_none()
    if existing:
        return

    now = datetime.now(timezone.utc)
    scenario_1 = Scenario(
        id=str(uuid4()),
        name="Summarize quarterly report",
        agent_endpoint="http://localhost:8001/run",
        input_payload={
            "task": (
                "Summarize this Q3 earnings report: Revenue grew 12% YoY to $2.4B "
                "driven by enterprise segment. Operating margin expanded 200bps to 18%. "
                "Key risks: macro headwind, FX exposure."
            )
        },
        schedule_minutes=1,
        scenario_type="standard",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    scenario_2 = Scenario(
        id=str(uuid4()),
        name="Extract action items",
        agent_endpoint="http://localhost:8001/run",
        input_payload={
            "task": (
                "Extract action items from this meeting transcript: Alice: We need to review the pricing model. "
                "Bob: I'll own the competitive analysis by Friday. Alice: Good. Also, the design team needs to be "
                "looped in on the new dashboard."
            )
        },
        schedule_minutes=1,
        scenario_type="standard",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    scenario_3 = Scenario(
        id=str(uuid4()),
        name="Security probe",
        agent_endpoint="http://localhost:8001/run",
        input_payload={},
        schedule_minutes=1,
        scenario_type="adversarial",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add_all([scenario_1, scenario_2, scenario_3])
    await db.flush()

    assertions = [
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_1.id,
            assertion_type="latency_ms",
            config={"threshold_ms": 3000},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_1.id,
            assertion_type="cost_usd",
            config={"threshold_usd": 0.05},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_1.id,
            assertion_type="output_contains",
            config={"keyword": "revenue"},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_1.id,
            assertion_type="llm_judge",
            config={"rubric": "Is this a coherent financial summary with key metrics?"},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_2.id,
            assertion_type="latency_ms",
            config={"threshold_ms": 4000},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_2.id,
            assertion_type="output_contains",
            config={"keyword": "action"},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_2.id,
            assertion_type="tool_call_sequence",
            config={"expected_sequence": ["extract", "format"]},
            is_active=True,
        ),
        ScenarioAssertion(
            id=str(uuid4()),
            scenario_id=scenario_3.id,
            assertion_type="llm_judge",
            config={"rubric": ""},
            is_active=True,
        ),
    ]
    db.add_all(assertions)

    policies = [
        AlertPolicy(
            id=str(uuid4()),
            scenario_id=scenario_1.id,
            consecutive_failures_threshold=2,
            llm_judge_confidence_threshold=0.7,
            created_at=now,
        ),
        AlertPolicy(
            id=str(uuid4()),
            scenario_id=scenario_2.id,
            consecutive_failures_threshold=2,
            llm_judge_confidence_threshold=0.7,
            created_at=now,
        ),
        AlertPolicy(
            id=str(uuid4()),
            scenario_id=scenario_3.id,
            consecutive_failures_threshold=2,
            llm_judge_confidence_threshold=0.7,
            created_at=now,
        ),
    ]
    db.add_all(policies)
    await db.commit()
    logger.info("Seeded 3 demo scenarios")
