from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import sync_earnings
from app.jobs.lock import JobLock
from app.providers.base import (
    Earnings,
    EarningsHour,
    ProviderRateLimitedError,
    ProviderResponseError,
)
from app.store.db import SessionFactory
from app.store.models import Event, Holding, User
from tests.fakes import FakeEarningsProvider

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)  # US date 2026-11-25


def earning(
    ticker: str, d: date, hour: EarningsHour = "amc", actual: str | None = None
) -> Earnings:
    eps = Decimal(actual) if actual else None
    return Earnings(ticker, d, hour, Decimal("1.5"), 4, 2026, eps_actual=eps)


@pytest.fixture
async def held(session: AsyncSession) -> None:
    user = User(email="e@example.com", password_hash="x")
    session.add(user)
    await session.flush()
    session.add_all(
        [
            Holding(user_id=user.id, ticker=t, shares=Decimal(1), avg_cost_usd=Decimal(1))
            for t in ("KO", "VOO", "NVDA")
        ]
    )
    await session.flush()


async def earnings_rows(session: AsyncSession) -> list[tuple[str | None, date, str | None]]:
    rows = (
        await session.execute(
            select(Event).where(Event.type == "earnings").order_by(Event.event_date)
        )
    ).scalars()
    return [(e.ticker, e.event_date, e.payload.get("hour")) for e in rows]


@pytest.mark.usefixtures("held")
async def test_saves_each_tickers_earnings_in_the_window(
    session_factory: SessionFactory, session: AsyncSession, redis: Redis
) -> None:
    provider = FakeEarningsProvider(
        earnings={
            "KO": [earning("KO", date(2027, 2, 8))],
            "NVDA": [
                earning("NVDA", date(2026, 11, 17), actual="2.68"),
                earning("NVDA", date(2027, 2, 23)),
            ],
            # VOO: an ETF, nothing
        }
    )
    result = await sync_earnings.run(session_factory, redis, provider, now=NOW)
    assert result.saved == {"KO": 1, "NVDA": 2, "VOO": 0}
    assert result.failed == {}
    # one call per ticker, 30 days back to 90 days ahead
    assert {c[0] for c in provider.calls} == {"KO", "NVDA", "VOO"}
    assert {(c[1], c[2]) for c in provider.calls} == {(date(2026, 10, 26), date(2027, 2, 23))}

    assert await earnings_rows(session) == [
        ("NVDA", date(2026, 11, 17), "amc"),
        ("KO", date(2027, 2, 8), "amc"),
        ("NVDA", date(2027, 2, 23), "amc"),
    ]
    reported = (
        await session.execute(select(Event).where(Event.event_date == date(2026, 11, 17)))
    ).scalar_one()
    assert reported.payload["eps_actual"] == "2.68"
    assert reported.event_time_utc == datetime(
        2026, 11, 17, 21, 0, tzinfo=UTC
    )  # after the 16:00 ET close


@pytest.mark.usefixtures("held")
async def test_a_moved_date_replaces_the_old_one(
    session_factory: SessionFactory, session: AsyncSession, redis: Redis
) -> None:
    provider = FakeEarningsProvider(earnings={"KO": [earning("KO", date(2027, 2, 8))]})
    await sync_earnings.run(session_factory, redis, provider, now=NOW)
    provider.earnings["KO"] = [earning("KO", date(2027, 2, 10), hour="bmo")]
    await sync_earnings.run(session_factory, redis, provider, now=NOW)
    assert await earnings_rows(session) == [("KO", date(2027, 2, 10), "bmo")]


class _Failing(FakeEarningsProvider):
    async def get_earnings(self, ticker: str, start: date, end: date) -> list[Earnings]:
        self.calls.append((ticker, start, end))
        if ticker == "KO":
            raise ProviderResponseError("finnhub", "bad body")
        if ticker == "NVDA":
            raise ProviderRateLimitedError("finnhub", "slow down", 30.0)
        return []


@pytest.mark.usefixtures("held")
async def test_errors_are_per_ticker_and_a_rate_limit_stops_the_run(
    session_factory: SessionFactory, redis: Redis
) -> None:
    provider = _Failing()
    result = await sync_earnings.run(session_factory, redis, provider, now=NOW)
    # alphabetical: KO fails and is skipped, NVDA hits the limit, VOO waits for the next run
    assert set(result.failed) == {"KO", "NVDA"}
    assert [c[0] for c in provider.calls] == ["KO", "NVDA"]


async def test_overlapping_run_is_skipped(session_factory: SessionFactory, redis: Redis) -> None:
    lock = JobLock(redis, sync_earnings.JOB, 60)
    assert await lock.acquire()
    try:
        result = await sync_earnings.run(session_factory, redis, FakeEarningsProvider(), now=NOW)
    finally:
        await lock.release()
    assert result.skipped == "already running"
