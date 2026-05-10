"""Slack webhook delivery with bounded HTTP retries and DB audit rows."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AlertDelivery

logger = logging.getLogger(__name__)

SLACK_MAX_ATTEMPTS = 3
SLACK_BACKOFF_BASE_S = 0.35
RETRYABLE = frozenset({429, 502, 503, 504})


async def _backoff(attempt: int) -> None:
    await asyncio.sleep(SLACK_BACKOFF_BASE_S * (2**attempt) + random.uniform(0, 0.1))


async def deliver_slack_alert_recorded(
    db: AsyncSession,
    *,
    run_id: str,
    scenario_id: str,
    webhook_url: str,
    text: str,
) -> AlertDelivery:
    now = datetime.now(timezone.utc)
    row = AlertDelivery(
        run_id=run_id,
        scenario_id=scenario_id,
        channel="slack",
        status="pending",
        text_snippet=text[:2000],
        created_at=now,
    )
    db.add(row)
    await db.flush()

    last_err: str | None = None
    http_status: int | None = None
    for attempt in range(SLACK_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(webhook_url, json={"text": text})
            http_status = resp.status_code
            if resp.status_code < 400:
                row.status = "delivered"
                row.http_status = resp.status_code
                row.delivered_at = datetime.now(timezone.utc)
                last_err = None
                break
            last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
            if resp.status_code not in RETRYABLE or attempt >= SLACK_MAX_ATTEMPTS - 1:
                row.status = "failed"
                row.http_status = resp.status_code
                row.error_message = last_err
                break
            logger.warning(
                "slack_webhook_retry",
                extra={"attempt": attempt + 1, "status": resp.status_code, "run_id": run_id},
            )
            await _backoff(attempt)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_err = str(exc)
            if attempt >= SLACK_MAX_ATTEMPTS - 1:
                row.status = "failed"
                row.error_message = last_err
                break
            logger.warning("slack_webhook_transport_retry", extra={"attempt": attempt + 1, "run_id": run_id})
            await _backoff(attempt)

    if last_err and row.status == "pending":
        row.status = "failed"
        row.error_message = last_err
        row.http_status = http_status
    await db.commit()
    await db.refresh(row)
    return row
