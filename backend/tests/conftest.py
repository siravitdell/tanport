"""Shared fixtures.

DB tests use the `tanport_test` database from docker-compose (`make test` starts it).
The schema is migrated to head once per session; each test runs inside a transaction
that is rolled back, so tests never see each other's data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import get_settings
from app.redis_client import make_redis
from app.store.db import make_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(connection: Connection) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False
    return cfg


def upgrade_head(connection: Connection) -> None:
    command.upgrade(alembic_config(connection), "head")


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine(get_settings().test_database_url)
    async with eng.begin() as conn:
        await conn.run_sync(upgrade_head)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        db = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield db
        finally:
            await db.close()
            await trans.rollback()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    """Dedicated Redis DB index (TEST_REDIS_URL, default /15), emptied around each test."""
    config = get_settings()
    if config.test_redis_url == config.redis_url:
        pytest.fail("TEST_REDIS_URL must differ from REDIS_URL: tests flush that database")
    client = make_redis(config.test_redis_url)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()
