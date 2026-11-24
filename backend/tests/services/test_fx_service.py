from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NoFxRateError
from app.providers.base import FxRate, ProviderUnavailableError
from app.services.fx import FxService
from app.store import fx as fx_store
from tests.fakes import FakeFXProvider

TODAY = date(2026, 12, 16)


def rate(d: date, value: str) -> FxRate:
    return FxRate(rate_date=d, pair="USD/THB", rate=Decimal(value))


@pytest.fixture
def provider() -> FakeFXProvider:
    # Thai business days only: no rate on Sat 12 / Sun 13 Dec
    return FakeFXProvider(
        rates=[
            rate(date(2026, 1, 5), "34.10"),
            rate(date(2026, 12, 10), "32.40"),
            rate(date(2026, 12, 11), "32.50"),
            rate(date(2026, 12, 14), "32.65"),
            rate(date(2026, 12, 15), "32.70"),
        ]
    )


@pytest.fixture
def service(session: AsyncSession, redis: Redis, provider: FakeFXProvider) -> FxService:
    return FxService(session, redis, provider, today=lambda: TODAY)


async def test_refresh_fetches_two_weeks_then_caches_for_24h(
    service: FxService, provider: FakeFXProvider, redis: Redis
) -> None:
    assert await service.refresh() == 4
    assert provider.calls == [(TODAY - timedelta(days=14), TODAY)]

    assert await service.refresh() == 0  # within 24 h: BOT is not called again
    assert len(provider.calls) == 1
    assert 0 < await redis.ttl("fx:USD/THB:refreshed") <= 24 * 3600

    await service.refresh(force=True)
    assert len(provider.calls) == 2


async def test_failed_fetch_does_not_set_cache(
    service: FxService, provider: FakeFXProvider
) -> None:
    provider.fail_with = ProviderUnavailableError("bot", "down")
    with pytest.raises(ProviderUnavailableError):
        await service.refresh()
    provider.fail_with = None
    assert await service.refresh() == 4  # retried, not suppressed by a cache marker


@pytest.mark.parametrize(
    ("on", "expected_rate", "expected_date", "fallback"),
    [
        (date(2026, 12, 15), "32.70", date(2026, 12, 15), False),  # pay date has a rate
        (date(2026, 12, 13), "32.50", date(2026, 12, 11), True),  # Sunday → Friday's rate
        (date(2026, 12, 31), "32.70", date(2026, 12, 15), True),  # future pay date → latest
    ],
)
async def test_rate_on(
    service: FxService, on: date, expected_rate: str, expected_date: date, fallback: bool
) -> None:
    await service.refresh()
    choice = await service.rate_on(on)
    assert choice.rate == Decimal(expected_rate)
    assert choice.rate_date == expected_date
    assert choice.is_fallback is fallback


async def test_latest_uses_bangkok_today(service: FxService) -> None:
    await service.refresh()
    choice = await service.latest()
    assert (choice.rate_date, choice.rate) == (date(2026, 12, 15), Decimal("32.70"))


async def test_no_rate_raises(service: FxService) -> None:
    with pytest.raises(NoFxRateError):
        await service.rate_on(date(2026, 12, 15))


async def test_backfill_only_fetches_missing_edges(
    service: FxService, provider: FakeFXProvider, session: AsyncSession
) -> None:
    await service.refresh()  # stores 10–15 Dec
    provider.calls.clear()

    assert await service.backfill(date(2026, 1, 1)) == 1  # the 5 Jan rate
    # before the earliest stored day, and after the latest (15th) up to today (16th)
    assert provider.calls == [
        (date(2026, 1, 1), date(2026, 12, 9)),
        (date(2026, 12, 16), TODAY),
    ]
    assert await fx_store.coverage(session, "USD/THB") == (date(2026, 1, 5), date(2026, 12, 15))

    provider.calls.clear()
    # latest stored is the 15th, today is the 16th → only that edge is fetched
    await service.backfill(date(2026, 6, 1))
    assert provider.calls == [(date(2026, 12, 16), TODAY)]


async def test_upsert_overwrites_revised_rates(session: AsyncSession) -> None:
    await fx_store.upsert_rates(session, [rate(date(2026, 12, 15), "32.70")], "bot")
    await fx_store.upsert_rates(session, [rate(date(2026, 12, 15), "32.71")], "bot")
    rates = await fx_store.rates_between(session, "USD/THB", date(2026, 12, 1), date(2026, 12, 31))
    assert rates == {date(2026, 12, 15): Decimal("32.710000")}
