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
    if "runs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("runs")}
    if "error_code" not in cols:
        sync_conn.execute(text("ALTER TABLE runs ADD COLUMN error_code VARCHAR(64)"))


async def init_db() -> None:
    # Ensure models are imported before create_all to register table metadata.
    from backend.models import Base  # pylint: disable=import-outside-toplevel

    logger.info("Initializing database", extra={"database_url": DATABASE_URL})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite_schema)
    logger.info("Database initialization complete")
