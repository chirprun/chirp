from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./chirp.db")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def _migrate_sqlite_schema(sync_conn) -> None:
    """Lightweight additive migrations for existing SQLite files."""
    insp = inspect(sync_conn)
    tables = set(insp.get_table_names())
    if "runs" in tables:
        cols = {c["name"] for c in insp.get_columns("runs")}
        if "error_code" not in cols:
            sync_conn.execute(text("ALTER TABLE runs ADD COLUMN error_code VARCHAR(64)"))

    if "alert_deliveries" not in tables:
        sync_conn.execute(
            text(
                """
                CREATE TABLE alert_deliveries (
                    id VARCHAR(36) PRIMARY KEY,
                    run_id VARCHAR(36) NOT NULL REFERENCES runs(id),
                    scenario_id VARCHAR(36) NOT NULL REFERENCES scenarios(id),
                    channel VARCHAR(32) NOT NULL DEFAULT 'slack',
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    http_status INTEGER,
                    error_message TEXT,
                    text_snippet TEXT,
                    created_at TIMESTAMP NOT NULL,
                    delivered_at TIMESTAMP
                )
                """
            )
        )
        sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alert_deliveries_scenario ON alert_deliveries(scenario_id)"))

    if "quota_usage" not in tables:
        sync_conn.execute(
            text(
                """
                CREATE TABLE quota_usage (
                    id VARCHAR(36) PRIMARY KEY,
                    scenario_id VARCHAR(36) NOT NULL REFERENCES scenarios(id),
                    month VARCHAR(7) NOT NULL,
                    runs_count INTEGER NOT NULL DEFAULT 0,
                    total_cost_usd REAL NOT NULL DEFAULT 0,
                    total_input_tokens INTEGER NOT NULL DEFAULT 0,
                    total_output_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    UNIQUE(scenario_id, month)
                )
                """
            )
        )
        sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quota_usage_scenario ON quota_usage(scenario_id)"))


async def init_db() -> None:
    # Ensure models are imported before create_all to register table metadata.
    from backend.models import Base  # pylint: disable=import-outside-toplevel

    logger.info("Initializing database", extra={"database_url": DATABASE_URL})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite_schema)
    logger.info("Database initialization complete")
