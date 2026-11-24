from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.estimates import add_months
from app.jobs import sync_dividends
from app.providers.base import Dividend, ProviderRateLimitedError, ProviderResponseError
from app.store.db import SessionFactory
from app.store.models import Event, Holding, User
from tests.fakes import FakeDividendProvider

NOW = datetime(2026, 11, 24, 0, 0, tzinfo=UTC)  # 07:00 Bangkok


def quarterly(ticker: str, last_ex: date, n: int = 4, dps: str = "0.53") -> list[Dividend]:
    exs = sorted(add_months(last_ex, -3 * i) for i in range(n))
    return [Dividend(ticker, ex, ex + timedelta(days=14), None, None, Decimal(dps)) for ex in exs]


@pytest.fixture
async def holders(session: AsyncSession) -> None:
    user = User(email="a@example.com", password_hash="x")
    session.add(user)
    await session.flush()
    session.add_all(
        [
            Holding(user_id=user.id, ticker=t, shares=Decimal(1), avg_cost_usd=Decimal(1))
            for t in ("AMZN", "KO", "VOO")
        ]
    )
    await session.flush()


@pytest.fixture
def provider() -> FakeDividendProvider:
    return FakeDividendProvider(
        dividends={
            "KO": quarterly("KO", date(2026, 12, 1)),
            "VOO": quarterly("VOO", date(2026, 9, 28), dps="1.85"),
        }
    )


async def _events(session: AsyncSession, ticker: str) -> list[Event]:
    return list(
        await session.scalars(
            select(Event).where(Event.ticker == ticker).order_by(Event.event_date, Event.type)
        )
    )


@pytest.mark.usefixtures("holders")
async def test_creates_declared_and_estimated_events(
    session_factory: SessionFactory,
    session: AsyncSession,
    redis: Redis,
    provider: FakeDividendProvider,
) -> None:
    result = await sync_dividends.run(session_factory, redis, provider, now=NOW)
    assert set(result.saved) == {"AMZN", "KO", "VOO"}
    assert result.saved["AMZN"] == 0  # non-payer: nothing, and no error
    ko = await _events(session, "KO")
    declared = [e for e in ko if not e.is_estimate]
    estimated = [e for e in ko if e.is_estimate]
    assert {e.type for e in declared} == {"ex_dividend", "dividend_pay"}
    assert all(e.source == "alphavantage" for e in declared)
    assert estimated
    assert all(e.source == "estimate" for e in estimated)
    assert min(e.event_date for e in estimated if e.type == "ex_dividend") > date(2026, 12, 1)
    assert max(e.event_date for e in ko) <= date(2027, 12, 31)


@pytest.mark.usefixtures("holders")
async def test_recently_synced_tickers_are_skipped(
    session_factory: SessionFactory, redis: Redis, provider: FakeDividendProvider
) -> None:
    await sync_dividends.run(session_factory, redis, provider, now=NOW)
    provider.calls.clear()

    later = await sync_dividends.run(session_factory, redis, provider, now=NOW + timedelta(hours=2))
    assert sorted(later.recent) == ["AMZN", "KO", "VOO"]
    assert provider.calls == []  # Alpha Vantage quota untouched

    forced = await sync_dividends.run(
        session_factory, redis, provider, now=NOW + timedelta(hours=2), force=True
    )
    assert len(forced.saved) == 3

    next_day = await sync_dividends.run(
        session_factory, redis, provider, now=NOW + timedelta(hours=26)
    )
    assert len(next_day.saved) == 3


@pytest.mark.usefixtures("holders")
async def test_declaration_replaces_the_estimate(
    session_factory: SessionFactory,
    session: AsyncSession,
    redis: Redis,
    provider: FakeDividendProvider,
) -> None:
    await sync_dividends.run(session_factory, redis, provider, now=NOW)
    voo_estimates = [e for e in await _events(session, "VOO") if e.is_estimate]
    next_est = min(e.event_date for e in voo_estimates if e.type == "ex_dividend")

    # Vanguard declares the December payment
    declared = Dividend("VOO", date(2026, 12, 21), date(2026, 12, 23), None, None, Decimal("2.01"))
    provider.dividends["VOO"].append(declared)
    await sync_dividends.run(session_factory, redis, provider, now=NOW, force=True)

    voo = await _events(session, "VOO")
    assert ("ex_dividend", date(2026, 12, 21), False) in [
        (e.type, e.event_date, e.is_estimate) for e in voo
    ]
    assert next_est not in [e.event_date for e in voo if e.is_estimate]
    assert min(e.event_date for e in voo if e.is_estimate) > date(2026, 12, 23)
    # no duplicates after re-running
    keys = [(e.type, e.event_date, e.source) for e in voo]
    assert len(keys) == len(set(keys))


@pytest.mark.usefixtures("holders")
async def test_quota_exhaustion_defers_the_rest_least_recent_first(
    session_factory: SessionFactory, redis: Redis, provider: FakeDividendProvider
) -> None:
    class Quota(FakeDividendProvider):
        remaining = 1

        async def get_dividends(self, ticker: str) -> list[Dividend]:
            if self.remaining == 0:
                raise ProviderRateLimitedError("alphavantage", "25 requests per day")
            self.remaining -= 1
            return list(await super().get_dividends(ticker))

    limited = Quota(dividends=provider.dividends)
    first = await sync_dividends.run(session_factory, redis, limited, now=NOW)
    assert list(first.saved) == ["AMZN"]  # alphabetical when nothing synced yet
    assert first.deferred == ["KO", "VOO"]
    assert first.failed == {}

    limited.remaining = 1
    second = await sync_dividends.run(session_factory, redis, limited, now=NOW + timedelta(hours=1))
    assert list(second.saved) == ["KO"]  # never-synced tickers go before the fresh one
    assert second.deferred == ["VOO"]
    assert second.recent == ["AMZN"]


@pytest.mark.usefixtures("holders")
async def test_one_failure_does_not_stop_the_rest(
    session_factory: SessionFactory, redis: Redis, provider: FakeDividendProvider
) -> None:
    class Broken(FakeDividendProvider):
        async def get_dividends(self, ticker: str) -> list[Dividend]:
            if ticker == "KO":
                raise ProviderResponseError("alphavantage", "dividends for KO: bad row")
            return list(await super().get_dividends(ticker))

    result = await sync_dividends.run(
        session_factory, redis, Broken(dividends=provider.dividends), now=NOW
    )
    assert "bad row" in result.failed["KO"]
    assert set(result.saved) == {"AMZN", "VOO"}


@pytest.mark.usefixtures("holders")
async def test_per_second_throttle_is_waited_out(
    session_factory: SessionFactory, redis: Redis, provider: FakeDividendProvider
) -> None:
    class Bursty(FakeDividendProvider):
        throttled = False

        async def get_dividends(self, ticker: str) -> list[Dividend]:
            if ticker == "KO" and not self.throttled:
                self.throttled = True
                raise ProviderRateLimitedError("alphavantage", "1 request per second", 0.01)
            return list(await super().get_dividends(ticker))

    result = await sync_dividends.run(
        session_factory, redis, Bursty(dividends=provider.dividends), now=NOW
    )
    assert set(result.saved) == {"AMZN", "KO", "VOO"}
    assert result.deferred == []
