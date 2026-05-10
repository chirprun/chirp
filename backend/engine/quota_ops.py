"""Monthly quota counters per scenario."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import QuotaUsage, Run


def _month_key(dt: datetime) -> str:
    d = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def month_for_quota(dt: datetime | None = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return _month_key(d)


async def bump_quota_after_run(db: AsyncSession, scenario_id: str, run: Run, input_tokens: int, output_tokens: int) -> None:
    """Increment quota row after a completed PASS/FAIL run."""
    if run.status not in ("PASS", "FAIL"):
        return
    month = _month_key(run.started_at)
    q = await db.execute(
        select(QuotaUsage).where(QuotaUsage.scenario_id == scenario_id, QuotaUsage.month == month)
    )
    row = q.scalar_one_or_none()
    cost = float(run.total_cost_usd or 0.0)
    if row is None:
        row = QuotaUsage(
            scenario_id=scenario_id,
            month=month,
            runs_count=1,
            total_cost_usd=cost,
            total_input_tokens=max(0, input_tokens),
            total_output_tokens=max(0, output_tokens),
        )
        db.add(row)
    else:
        row.runs_count += 1
        row.total_cost_usd += cost
        row.total_input_tokens += max(0, input_tokens)
        row.total_output_tokens += max(0, output_tokens)
    await db.commit()
