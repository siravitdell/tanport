from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_now
from app.providers.base import FxRate, Quote
from app.store import fx as fx_store
from app.store.quote_cache import save_quote
from tests.api.conftest import LoginAs, buy

NOW_OPEN = datetime(2026, 12, 16, 15, 0, tzinfo=UTC)  # Wed 10:00 ET = 22:00 Bangkok
SATURDAY = datetime(2026, 12, 19, 5, 0, tzinfo=UTC)

type SetNow = Callable[[datetime], None]


def quote(ticker: str, price: str, prev: str) -> Quote:
    p, pc = Decimal(price), Decimal(prev)
    return Quote(ticker, p, pc, p - pc, (p - pc) / pc * 100, NOW_OPEN)


@pytest.fixture
def at(app: FastAPI) -> SetNow:
    def _set(now: datetime) -> None:
        app.dependency_overrides[get_now] = lambda: now

    _set(NOW_OPEN)
    return _set


@pytest.fixture
async def market_data(session: AsyncSession, redis: Redis) -> None:
    await save_quote(redis, quote("VOO", "606", "600"))
    await save_quote(redis, quote("KO", "69.3", "70"))
    await fx_store.upsert_rates(
        session, [FxRate(date(2026, 12, 15), "USD/THB", Decimal("32.50"))], "bot"
    )


async def _holdings(client: AsyncClient, rows: list[tuple[str, str]]) -> None:
    for ticker, shares in rows:
        await buy(client, ticker, shares)


@pytest.mark.usefixtures("market_data", "at")
async def test_quotes_for_current_user(alice: AsyncClient) -> None:
    await _holdings(alice, [("VOO", "10"), ("KO", "20"), ("NVDA", "5")])
    body = (await alice.get("/api/quotes")).json()

    assert body["market"] == {
        "is_open": True,
        "last_session_date": "2026-12-16",
        "next_open_utc": "2026-12-17T14:30:00Z",
    }
    assert body["fx"] == {"usd_thb": "32.5", "rate_date": "2026-12-15", "is_fallback": True}

    tickers = [(h["ticker"], h["status"]) for h in body["holdings"]]
    assert tickers == [("VOO", "ok"), ("KO", "ok"), ("NVDA", "no_quote")]
    voo = body["holdings"][0]
    assert voo["price"] == "606"
    assert voo["change_pct"] == "1"
    assert voo["value_thb"] == "196950"
    assert Decimal(voo["weight_pct"]).quantize(Decimal("0.1")) == Decimal("81.4")

    portfolio = body["portfolio"]
    assert portfolio["value_usd"] == "7446"
    assert portfolio["change_usd"] == "46"
    assert portfolio["change_thb"] == "1495"
    assert portfolio["excluded"] == ["NVDA"]
    assert Decimal(portfolio["change_pct"]).quantize(Decimal("0.0001")) == Decimal("0.6216")


@pytest.mark.usefixtures("market_data")
async def test_weekend_shows_last_session_as_closed(alice: AsyncClient, at: SetNow) -> None:
    at(SATURDAY)
    await _holdings(alice, [("VOO", "1")])
    body = (await alice.get("/api/quotes")).json()
    assert body["market"]["is_open"] is False
    assert body["market"]["last_session_date"] == "2026-12-18"
    assert body["holdings"][0]["price"] == "606"  # last known price, not 0


@pytest.mark.usefixtures("at")
async def test_no_market_data_yet(alice: AsyncClient) -> None:
    await _holdings(alice, [("VOO", "1")])
    body = (await alice.get("/api/quotes")).json()
    assert body["fx"] is None
    assert body["portfolio"] is None
    assert body["holdings"][0]["status"] == "no_quote"
    assert body["holdings"][0]["change_pct"] is None  # never a fake 0 %


@pytest.mark.usefixtures("market_data", "at")
async def test_only_own_holdings(alice: AsyncClient, login_as: LoginAs) -> None:
    await _holdings(alice, [("VOO", "10")])
    bob = await login_as("bob@example.com")
    await _holdings(bob, [("KO", "1")])
    body = (await bob.get("/api/quotes")).json()
    assert [h["ticker"] for h in body["holdings"]] == ["KO"]
    assert body["portfolio"]["value_usd"] == "69.3"
