from __future__ import annotations

from decimal import Decimal

from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.store.models import AppSettings, Holding
from tests.conftest import alembic_config

TABLES = {"holdings", "prices", "portfolio_daily", "events", "fx_rates", "settings"}


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


async def test_models_match_migrations(engine: AsyncEngine) -> None:
    """`alembic check` raises if autogenerate would produce any diff."""
    async with engine.connect() as conn:
        await conn.run_sync(lambda c: command.check(alembic_config(c)))


async def test_seed_settings_row(session: AsyncSession) -> None:
    row = (await session.execute(select(AppSettings))).scalar_one()
    assert row.withholding_rate == Decimal("0.15")
    assert row.big_move_threshold_pct == Decimal("3")
    assert row.dca_split == {"VOO": "70", "QQQM": "20", "SCHD": "10"}


async def test_seed_holdings(session: AsyncSession) -> None:
    tickers = set((await session.execute(select(Holding.ticker))).scalars())
    assert tickers >= {"VOO", "QQQM", "SCHD", "V", "MSFT", "KO", "GOOGL", "NVDA", "AMZN"}


async def test_money_columns_are_numeric(session: AsyncSession) -> None:
    result = await session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type IN ('real', 'double precision')"
        )
    )
    assert result.all() == []
