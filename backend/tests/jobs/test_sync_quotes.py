from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import sync_quotes
from app.jobs.lock import JobLock
from app.providers.base import (
    ProviderAccessDeniedError,
    ProviderResponseError,
    Quote,
)
from app.store.db import SessionFactory
from app.store.models import Holding, User
from app.store.quote_cache import load_quotes
from tests.fakes import FakeQuoteProvider

OPEN = datetime(2026, 12, 16, 15, 0, tzinfo=UTC)  # Wed 10:00 ET
CLOSED = datetime(2026, 12, 19, 15, 0, tzinfo=UTC)  # Saturday


def quote(ticker: str, price: str) -> Quote:
    p = Decimal(price)
    return Quote(ticker, p, p, Decimal(0), Decimal(0), OPEN)


@pytest.fixture
async def holders(session: AsyncSession) -> None:
    """Two users; KO is held by both (fetched once), AMZN only with 0 shares (not fetched)."""
    a = User(email="a@example.com", password_hash="x")
    b = User(email="b@example.com", password_hash="x")
    session.add_all([a, b])
    await session.flush()
    session.add_all(
        [
            Holding(user_id=a.id, ticker="VOO", shares=Decimal(1), avg_cost_usd=Decimal(1)),
            Holding(user_id=a.id, ticker="KO", shares=Decimal(1), avg_cost_usd=Decimal(1)),
            Holding(user_id=b.id, ticker="KO", shares=Decimal(2), avg_cost_usd=Decimal(1)),
            Holding(user_id=b.id, ticker="AMZN", shares=Decimal(0), avg_cost_usd=Decimal(0)),
        ]
    )
    await session.flush()


@pytest.fixture
def provider() -> FakeQuoteProvider:
    return FakeQuoteProvider(quotes={"VOO": quote("VOO", "611.72"), "KO": quote("KO", "70.05")})


@pytest.mark.usefixtures("holders")
async def test_fetches_each_held_ticker_once(
    session_factory: SessionFactory, redis: Redis, provider: FakeQuoteProvider
) -> None:
    result = await sync_quotes.run(session_factory, redis, provider, now=OPEN)
    assert sorted(result.saved) == ["KO", "VOO"]
    assert sorted(c[0] for c in provider.calls) == ["KO", "VOO"]
    cached = await load_quotes(redis, ["VOO", "KO", "AMZN"])
    assert cached["VOO"].price == Decimal("611.72")
    assert "AMZN" not in cached


@pytest.mark.usefixtures("holders")
async def test_does_nothing_when_market_closed(
    session_factory: SessionFactory, redis: Redis, provider: FakeQuoteProvider
) -> None:
    result = await sync_quotes.run(session_factory, redis, provider, now=CLOSED)
    assert result.skipped == "market closed"
    assert provider.calls == []

    forced = await sync_quotes.run(session_factory, redis, provider, now=CLOSED, force=True)
    assert len(forced.saved) == 2


@pytest.mark.usefixtures("holders")
async def test_one_bad_ticker_does_not_stop_the_rest(
    session_factory: SessionFactory, redis: Redis
) -> None:
    class Flaky(FakeQuoteProvider):
        async def get_quote(self, ticker: str) -> Quote:
            if ticker == "KO":
                raise ProviderResponseError("finnhub", "no quote data for KO")
            return await super().get_quote(ticker)

    provider = Flaky(quotes={"VOO": quote("VOO", "611.72")})
    result = await sync_quotes.run(session_factory, redis, provider, now=OPEN)
    assert result.saved == ["VOO"]
    assert "no quote data" in result.failed["KO"]


@pytest.mark.usefixtures("holders")
async def test_access_denied_fails_the_run(
    session_factory: SessionFactory, redis: Redis, provider: FakeQuoteProvider
) -> None:
    provider.fail_with = ProviderAccessDeniedError("finnhub", "HTTP 401 on /api/v1/quote")
    with pytest.raises(ProviderAccessDeniedError):
        await sync_quotes.run(session_factory, redis, provider, now=OPEN)


@pytest.mark.usefixtures("holders")
async def test_overlapping_run_is_skipped(
    session_factory: SessionFactory, redis: Redis, provider: FakeQuoteProvider
) -> None:
    assert await JobLock(redis, sync_quotes.JOB, 60).acquire()
    result = await sync_quotes.run(session_factory, redis, provider, now=OPEN)
    assert result.skipped == "already running"
    assert provider.calls == []
