from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import sync_daily_close
from app.jobs.lock import JobLock
from app.providers.base import DailyBar, FxRate, ProviderResponseError
from app.store import fx as fx_store
from app.store.db import SessionFactory
from app.store.models import Event, Holding, PortfolioDaily, Price, Trade, User, UserSettings
from tests.fakes import FakePriceHistoryProvider

D = Decimal
D14, D15, D16 = date(2026, 12, 14), date(2026, 12, 15), date(2026, 12, 16)
END = D16


def bar(ticker: str, d: date, close: str) -> DailyBar:
    return DailyBar(ticker, d, None, None, None, D(close))


def bars() -> dict[str, list[DailyBar]]:
    return {
        "VOO": [bar("VOO", D14, "100"), bar("VOO", D15, "102.5"), bar("VOO", D16, "99.425")],
        "KO": [bar("KO", D14, "70"), bar("KO", D15, "70"), bar("KO", D16, "72.1")],
    }


@pytest.fixture
async def users(session: AsyncSession) -> tuple[int, int]:
    """A holds VOO 10 + KO 20 (default 3 % threshold); B holds KO 5 and uses 2 %."""
    a = User(email="a@example.com", password_hash="x")
    b = User(email="b@example.com", password_hash="x")
    session.add_all([a, b])
    await session.flush()
    session.add_all(
        [
            UserSettings(user_id=a.id),
            UserSettings(user_id=b.id, big_move_threshold_pct=D(2)),
            Holding(user_id=a.id, ticker="VOO", shares=D(10), avg_cost_usd=D(1)),
            Holding(user_id=a.id, ticker="KO", shares=D(20), avg_cost_usd=D(1)),
            Holding(user_id=b.id, ticker="KO", shares=D(5), avg_cost_usd=D(1)),
            # positions over time come from the trades (holdings = what is held now)
            *[
                Trade(
                    user_id=uid,
                    ticker=t,
                    side="buy",
                    trade_date=date(2026, 1, 2),
                    shares=D(n),
                    price_usd=D(1),
                    usd_thb=D(33),
                )
                for uid, t, n in [(a.id, "VOO", 10), (a.id, "KO", 20), (b.id, "KO", 5)]
            ],
        ]
    )
    await fx_store.upsert_rates(
        session,
        [FxRate(D14, "USD/THB", D("32.5")), FxRate(D16, "USD/THB", D("33"))],
        "bot",
    )
    await session.flush()
    return a.id, b.id


@pytest.fixture
def provider() -> FakePriceHistoryProvider:
    return FakePriceHistoryProvider(bars=bars())


async def test_first_run_backfills_and_derives_everything(
    session_factory: SessionFactory,
    session: AsyncSession,
    redis: Redis,
    provider: FakePriceHistoryProvider,
    users: tuple[int, int],
) -> None:
    user_a, user_b = users
    result = await sync_daily_close.run(session_factory, redis, provider, end=END)
    assert result is not None
    assert result.saved == {"KO": 3, "VOO": 3}
    assert result.failed == {}

    # new tickers: backfill window
    assert {c[1] for c in provider.calls} == {END - timedelta(days=100)}

    prices = {
        (p.ticker, p.trade_date): p.change_pct for p in (await session.scalars(select(Price)))
    }
    assert prices[("VOO", D14)] is None
    assert prices[("VOO", D15)] == D("2.5")
    assert prices[("VOO", D16)] == D("-3")
    assert prices[("KO", D16)] == D("3")

    # events at the lowest threshold of any user (B's 2 %): VOO +2.5, VOO −3, KO +3
    moves = sorted(
        (e.ticker, e.event_date, Decimal(e.payload["change_pct"]))
        for e in await session.scalars(select(Event).where(Event.type == "price_move"))
    )
    assert moves == [("KO", D16, D(3)), ("VOO", D15, D("2.5")), ("VOO", D16, D(-3))]

    rows = {(r.user_id, r.trade_date): r for r in await session.scalars(select(PortfolioDaily))}
    assert set(rows) == {(user_a, D15), (user_a, D16), (user_b, D15), (user_b, D16)}
    a16 = rows[(user_a, D16)]
    assert a16.value_usd == D("2436.25")
    assert a16.usd_thb == D("33")
    assert rows[(user_a, D15)].fx_rate_date == D14  # no rate on the 15th → previous day
    assert rows[(user_b, D16)].change_pct == D("3")


async def test_rerun_is_idempotent_and_applies_corrections(
    session_factory: SessionFactory,
    session: AsyncSession,
    redis: Redis,
    provider: FakePriceHistoryProvider,
    users: tuple[int, int],
) -> None:
    await sync_daily_close.run(session_factory, redis, provider, end=END)
    provider.calls.clear()
    # the provider revises VOO's last close: no longer a big move
    provider.bars["VOO"][-1] = bar("VOO", D16, "102")

    await sync_daily_close.run(session_factory, redis, provider, end=END)
    # known tickers: only the last week is re-fetched
    assert {c[1] for c in provider.calls} == {D16 - timedelta(days=7)}

    voo_moves = (
        await session.scalars(
            select(Event.event_date).where(Event.type == "price_move", Event.ticker == "VOO")
        )
    ).all()
    assert voo_moves == [D15]
    assert len((await session.scalars(select(Price))).all()) == 6
    assert len((await session.scalars(select(PortfolioDaily))).all()) == 4


async def test_a_failing_ticker_does_not_stop_the_others(
    session_factory: SessionFactory,
    session: AsyncSession,
    redis: Redis,
    users: tuple[int, int],
) -> None:
    class Flaky(FakePriceHistoryProvider):
        async def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
            if ticker == "KO":
                raise ProviderResponseError("tiingo", "HTTP 404 on /tiingo/daily/KO/prices")
            return list(await super().get_daily_bars(ticker, start, end))

    result = await sync_daily_close.run(session_factory, redis, Flaky(bars=bars()), end=END)
    assert result is not None
    assert result.saved == {"VOO": 3}
    assert "404" in result.failed["KO"]
    # portfolio still computed, with KO excluded (no data) rather than counted as 0 %
    row = await session.scalar(
        select(PortfolioDaily).where(
            PortfolioDaily.user_id == users[0], PortfolioDaily.trade_date == D16
        )
    )
    assert row is not None
    assert row.change_pct == D("-3")


@pytest.mark.usefixtures("users")
async def test_overlapping_run_is_skipped(
    session_factory: SessionFactory, redis: Redis, provider: FakePriceHistoryProvider
) -> None:
    assert await JobLock(redis, sync_daily_close.JOB, 60).acquire()
    assert await sync_daily_close.run(session_factory, redis, provider, end=END) is None
    assert provider.calls == []
