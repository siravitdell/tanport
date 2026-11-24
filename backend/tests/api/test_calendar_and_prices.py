from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_now
from app.domain.portfolio import PortfolioChange
from app.domain.portfolio_history import PortfolioDay
from app.domain.prices import PriceRow
from app.store import portfolio_daily as portfolio_store
from app.store.events import EventIn, upsert_events
from app.store.models import EventType
from app.store.prices import upsert_prices

D = Decimal
NOW = datetime(2026, 12, 16, 15, 0, tzinfo=UTC)  # Wed 10:00 ET


@pytest.fixture(autouse=True)
def pin_clock(app: FastAPI) -> None:
    app.dependency_overrides[get_now] = lambda: NOW


async def _hold(client: AsyncClient, *tickers: str) -> int:
    for t in tickers:
        resp = await client.post(
            "/api/holdings", json={"ticker": t, "shares": "1", "avg_cost_usd": "1"}
        )
        assert resp.status_code == 201
    user_id: int = (await client.get("/api/auth/me")).json()["id"]
    return user_id


def _day(d: date, change_pct: str) -> PortfolioDay:
    change = PortfolioChange(
        value_usd=D("5000"),
        prev_value_usd=D("5000"),
        change_pct=D(change_pct),
        change_usd=D("-69"),
        change_thb=D("-2484"),
        value_thb=D("179268"),
        usd_thb=D("32.5"),
        holdings=(),
        excluded=(),
    )
    return PortfolioDay(trade_date=d, change=change, fx_rate_date=d)


async def test_prices_for_sparkline(alice: AsyncClient, session: AsyncSession) -> None:
    rows = [
        PriceRow(
            "VOO", date(2026, 12, d), None, None, None, D(600 + d), D("0.1") if d > 1 else None
        )
        for d in range(1, 17)
    ]
    await upsert_prices(session, rows, "tiingo")

    body = (await alice.get("/api/prices", params={"ticker": "voo", "days": 14})).json()
    assert body["ticker"] == "VOO"
    assert len(body["points"]) == 14
    assert body["points"][0]["trade_date"] == "2026-12-03"  # oldest first
    assert body["points"][-1] == {"trade_date": "2026-12-16", "close": "616", "change_pct": "0.1"}


@pytest.mark.parametrize("params", [{"ticker": "$$"}, {"ticker": "VOO", "days": 0}, {}])
async def test_prices_validation(alice: AsyncClient, params: dict[str, str | int]) -> None:
    assert (await alice.get("/api/prices", params=params)).status_code == 422


async def test_calendar(alice: AsyncClient, session: AsyncSession) -> None:
    user_id = await _hold(alice, "KO", "NVDA")
    await portfolio_store.replace_days(
        session,
        user_id,
        date(2026, 12, 1),
        date(2026, 12, 31),
        [_day(date(2026, 12, 15), "-1.38")],
    )
    await upsert_events(
        session,
        [
            EventIn(
                type=EventType.PRICE_MOVE,
                ticker="NVDA",
                event_date=date(2026, 12, 15),
                source="tiingo",
                payload={"change_pct": "-5.40", "close": "143.14"},
            ),
            EventIn(
                type=EventType.PRICE_MOVE,
                ticker="KO",
                event_date=date(2026, 12, 15),
                source="tiingo",
                payload={"change_pct": "2.10", "close": "70"},
            ),  # < 3 %
            EventIn(
                type=EventType.DIVIDEND_PAY,
                ticker="KO",
                event_date=date(2026, 12, 15),
                source="alphavantage",
                payload={"dps": "0.53"},
            ),
            EventIn(
                type=EventType.EX_DIVIDEND,
                ticker="VOO",
                event_date=date(2026, 12, 15),
                source="alphavantage",
            ),  # not held by alice
            EventIn(
                type=EventType.MACRO,
                ticker=None,
                event_date=date(2026, 12, 16),
                source="manual",
                payload={"name": "FOMC"},
            ),
        ],
    )

    resp = await alice.get("/api/calendar", params={"from": "2026-12-12", "to": "2026-12-19"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["from"], body["to"]) == ("2026-12-12", "2026-12-19")
    days = {d["date"]: d for d in body["days"]}
    assert [d["status"] for d in body["days"]] == [
        "closed",
        "closed",
        "no_data",
        "ok",
        "no_data",
        "future",
        "future",
        "closed",
    ]
    d15 = days["2026-12-15"]
    assert d15["portfolio"] == {"value_thb": "179268", "change_pct": "-1.38", "change_thb": "-2484"}
    assert [(e["type"], e["ticker"]) for e in d15["events"]] == [
        ("dividend_pay", "KO"),
        ("price_move", "NVDA"),
    ]
    assert d15["events"][1]["payload"]["change_pct"] == "-5.40"
    assert [e["payload"]["name"] for e in days["2026-12-16"]["events"]] == ["FOMC"]


async def test_calendar_respects_user_threshold(alice: AsyncClient, session: AsyncSession) -> None:
    await _hold(alice, "KO")
    await upsert_events(
        session,
        [
            EventIn(
                type=EventType.PRICE_MOVE,
                ticker="KO",
                event_date=date(2026, 12, 15),
                source="tiingo",
                payload={"change_pct": "2.10"},
            )
        ],
    )
    settings = {
        "withholding_rate": "0.15",
        "big_move_threshold_pct": "2",
        "dca_split": {"VOO": "100"},
    }
    assert (await alice.put("/api/settings", json=settings)).status_code == 200
    body = (
        await alice.get("/api/calendar", params={"from": "2026-12-15", "to": "2026-12-15"})
    ).json()
    assert [e["ticker"] for e in body["days"][0]["events"]] == ["KO"]


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-12-20", "to": "2026-12-01"},
        {"from": "2026-01-01", "to": "2026-03-31"},
        {"from": "2026-12-01"},
        {"from": "yesterday", "to": "2026-12-01"},
    ],
)
async def test_calendar_validation(alice: AsyncClient, params: dict[str, str]) -> None:
    assert (await alice.get("/api/calendar", params=params)).status_code == 422


async def test_calendar_requires_login(client: AsyncClient) -> None:
    resp = await client.get("/api/calendar", params={"from": "2026-12-01", "to": "2026-12-31"})
    assert resp.status_code == 401
