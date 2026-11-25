from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_now
from app.domain.prices import PriceRow
from app.providers.base import FxRate
from app.store import fx as fx_store
from app.store.events import EventIn, upsert_events
from app.store.models import EventType, News
from app.store.prices import upsert_prices
from tests.api.conftest import LoginAs, buy

D = Decimal
D15 = date(2026, 12, 15)  # Tuesday
NOW = datetime(2026, 12, 16, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def pin_clock(app: FastAPI) -> None:
    app.dependency_overrides[get_now] = lambda: NOW


def price(ticker: str, close: str, pct: str) -> PriceRow:
    return PriceRow(ticker, D15, None, None, None, D(close), D(pct))


def article(ticker: str, at: datetime, n: int, importance: int | None = None) -> News:
    return News(
        ticker=ticker,
        published_at=at,
        headline=f"{ticker} story {n}",
        headline_key=f"{ticker.lower()} story {n}",
        url=f"https://finnhub.io/api/news?id={ticker}{n}",
        source="Yahoo",
        provider="finnhub",
        snippet="snippet",
        importance=importance,
    )


@pytest.fixture
async def market(session: AsyncSession) -> None:
    await upsert_prices(
        session, [price("VOO", "99", "-1"), price("NVDA", "94.6", "-5.4")], "tiingo"
    )
    await fx_store.upsert_rates(session, [FxRate(D15, "USD/THB", D("33"))], "bot")
    await upsert_events(
        session,
        [
            EventIn(
                type=EventType.PRICE_MOVE,
                ticker="NVDA",
                event_date=D15,
                source="tiingo",
                payload={"change_pct": "-5.4", "close": "94.6"},
            ),
            EventIn(
                type=EventType.PRICE_MOVE,
                ticker="VOO",
                event_date=D15,
                source="tiingo",
                payload={"change_pct": "-1", "close": "99"},
            ),  # < 3 %
            EventIn(
                type=EventType.PRICE_MOVE,
                ticker="KO",
                event_date=D15,
                source="tiingo",
                payload={"change_pct": "-6", "close": "60"},
            ),  # not held
        ],
    )
    noon_ny = datetime(2026, 12, 15, 17, 0, tzinfo=UTC)
    session.add_all(
        [
            *[article("NVDA", noon_ny + timedelta(minutes=i), i) for i in range(12)],
            article("NVDA", noon_ny - timedelta(hours=1), 99, importance=5),  # older but important
            article(
                "NVDA", datetime(2026, 12, 15, 4, 0, tzinfo=UTC), 100
            ),  # 14 Dec 23:00 in New York
            article(
                "NVDA", datetime(2026, 12, 16, 6, 0, tzinfo=UTC), 101
            ),  # 16 Dec 01:00 in New York
            article("KO", noon_ny, 1),  # not held
        ]
    )
    await session.flush()


@pytest.mark.usefixtures("market")
async def test_day_detail(alice: AsyncClient) -> None:
    await buy(alice, "VOO", "10", day="2026-12-01")
    await buy(alice, "NVDA", "5", day="2026-12-01")
    resp = await alice.get(f"/api/day/{D15}", params={"news_per_ticker": 5})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "ok"
    p = body["portfolio"]
    # prev: VOO 10 × 100 + NVDA 5 × 100 = 1500; now 990 + 473 = 1463
    assert (p["value_usd"], p["change_usd"], p["usd_thb"]) == ("1463", "-37", "33")
    assert p["change_thb"] == "-1221"

    assert [(h["ticker"], h["change_pct"]) for h in body["holdings"]] == [
        ("NVDA", "-5.4"),  # biggest move first
        ("VOO", "-1"),
    ]
    nvda = body["holdings"][0]
    assert (nvda["shares"], nvda["close"], nvda["change_thb"]) == ("5", "94.6", "-891")
    assert body["unpriced"] == []

    # the user's 3 % threshold drops VOO's move; KO is not held
    assert [(e["type"], e["ticker"]) for e in body["events"]] == [("price_move", "NVDA")]

    [news] = body["news"]
    assert (news["ticker"], news["total"]) == ("NVDA", 13)  # only 15 Dec in New York
    heads = [n["headline"] for n in news["items"]]
    assert heads[0] == "NVDA story 99"  # scored important first
    assert heads[1:] == ["NVDA story 11", "NVDA story 10", "NVDA story 9", "NVDA story 8"]


@pytest.mark.usefixtures("market")
async def test_positions_follow_the_trade_log(alice: AsyncClient) -> None:
    await buy(alice, "VOO", "10", day="2026-12-01")
    await buy(alice, "NVDA", "5", day="2026-12-16")  # bought the day after
    body = (await alice.get(f"/api/day/{D15}")).json()
    assert [h["ticker"] for h in body["holdings"]] == ["VOO"]
    assert body["events"] == []  # NVDA's move was before it was bought
    assert body["news"] == []


async def test_weekend_and_empty(alice: AsyncClient, login_as: LoginAs) -> None:
    body = (await alice.get("/api/day/2026-12-19")).json()  # Saturday, nothing held
    assert (body["status"], body["portfolio"], body["holdings"], body["news"]) == (
        "closed",
        None,
        [],
        [],
    )
    assert (await alice.get("/api/day/not-a-date")).status_code == 422
    assert (await alice.get("/api/day/1999-01-01")).status_code == 422


@pytest.mark.usefixtures("market")
async def test_held_but_not_priced_yet(alice: AsyncClient) -> None:
    await buy(alice, "SCHD", "3", day="2026-12-01")  # no close for SCHD
    body = (await alice.get(f"/api/day/{D15}")).json()
    assert body["portfolio"] is None
    assert body["unpriced"] == ["SCHD"]
    assert body["status"] == "no_data"


@pytest.mark.usefixtures("market")
async def test_closed_and_future_days_have_nothing_missing(alice: AsyncClient) -> None:
    await buy(alice, "VOO", "10", day="2026-12-01")
    for day in ("2026-12-19", "2026-12-25", "2026-12-30"):  # Saturday, Christmas, future
        body = (await alice.get(f"/api/day/{day}")).json()
        assert body["unpriced"] == [], day
        assert body["status"] in ("closed", "future")
