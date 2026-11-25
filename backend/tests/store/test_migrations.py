from __future__ import annotations

from decimal import Decimal

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
    "trades",
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


def _upgrade_0004_with_positions(
    connection: Connection, with_rates: bool
) -> list[tuple[object, ...]]:
    cfg = alembic_config(connection)
    command.downgrade(cfg, "0003")
    uid = connection.execute(
        text("INSERT INTO users (email, password_hash) VALUES ('m@example.com', 'x') RETURNING id")
    ).scalar_one()
    connection.execute(
        text(
            "INSERT INTO holdings (user_id, ticker, shares, avg_cost_usd, created_at) VALUES "
            "(:u, 'VOO', 2.5, 480.2, '2026-08-04 01:00+07'), "  # Bangkok date 2026-08-04
            "(:u, 'KO', 0, 0, now())"
        ),
        {"u": uid},
    )
    if with_rates:
        connection.execute(
            text(
                "INSERT INTO fx_rates (date, pair, rate, source) VALUES "
                "('2026-08-01', 'USD/THB', 33.1, 'bot'), ('2026-08-05', 'USD/THB', 33.4, 'bot')"
            )
        )
    command.upgrade(cfg, "head")
    trades = connection.execute(
        text("SELECT ticker, side, trade_date::text, shares, price_usd, usd_thb FROM trades")
    ).all()
    held = connection.execute(text("SELECT ticker FROM holdings")).all()
    return [tuple(r) for r in trades] + [("held", *[h[0] for h in held])]


async def test_0004_turns_positions_into_opening_buys(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            rows = await conn.run_sync(lambda c: _upgrade_0004_with_positions(c, True))
        finally:
            await trans.rollback()
    assert rows == [
        ("VOO", "buy", "2026-08-04", Decimal("2.5"), Decimal("480.2"), Decimal("33.1")),
        ("held", "VOO"),  # the empty KO row is gone
    ]


async def test_0004_needs_a_rate_for_existing_positions(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            with pytest.raises(RuntimeError, match="sync_fx"):
                await conn.run_sync(lambda c: _upgrade_0004_with_positions(c, False))
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
