from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.conftest import alembic_config

TABLES = {
    "users",
    "user_sessions",
    "user_settings",
    "holdings",
    "prices",
    "portfolio_daily",
    "events",
    "fx_rates",
}


def _tables(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names()) - {"alembic_version"}


def _roundtrip(connection: Connection) -> tuple[set[str], set[str]]:
    cfg = alembic_config(connection)
    command.downgrade(cfg, "base")
    after_down = _tables(connection)
    command.upgrade(cfg, "head")
    return after_down, _tables(connection)


async def test_downgrade_then_upgrade_roundtrip(engine: AsyncEngine) -> None:
    # Postgres DDL is transactional: run inside a transaction and roll back.
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            after_down, after_up = await conn.run_sync(_roundtrip)
        finally:
            await trans.rollback()
    assert after_down == set()
    assert after_up == TABLES


def _upgrade_with_ownerless_position(connection: Connection) -> None:
    cfg = alembic_config(connection)
    command.downgrade(cfg, "0002")
    connection.execute(text("UPDATE holdings SET shares = 5 WHERE ticker = 'VOO'"))
    command.upgrade(cfg, "head")


async def test_0003_refuses_to_drop_real_positions(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            with pytest.raises(RuntimeError, match="no owner"):
                await conn.run_sync(_upgrade_with_ownerless_position)
        finally:
            await trans.rollback()


async def test_models_match_migrations(engine: AsyncEngine) -> None:
    """`alembic check` raises if autogenerate would produce any diff."""
    async with engine.connect() as conn:
        await conn.run_sync(lambda c: command.check(alembic_config(c)))


async def test_money_columns_are_numeric(session: AsyncSession) -> None:
    result = await session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type IN ('real', 'double precision')"
        )
    )
    assert result.all() == []
