from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_now
from app.providers.base import FxRate
from app.store import fx as fx_store
from app.store.events import EventIn, upsert_events
from app.store.models import EventType
from tests.api.conftest import LoginAs

NOW = datetime(2026, 11, 24, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def pin_clock(app: FastAPI) -> None:
    app.dependency_overrides[get_now] = lambda: NOW


def pay(ticker: str, pay_date: date, dps: str, *, estimate: bool = False) -> EventIn:
    return EventIn(
        type=EventType.DIVIDEND_PAY,
        ticker=ticker,
        event_date=pay_date,
        source="estimate" if estimate else "alphavantage",
        is_estimate=estimate,
        payload={
            "dps": dps,
            "ex_date": pay_date.replace(day=1).isoformat(),
            "pay_date": pay_date.isoformat(),
        },
    )


@pytest.fixture
async def market(session: AsyncSession) -> None:
    await upsert_events(
        session,
        [
            pay("KO", date(2026, 4, 1), "0.53"),
            pay("KO", date(2026, 12, 15), "0.53"),
            pay("VOO", date(2026, 12, 31), "1.85", estimate=True),
        ],
    )
    await fx_store.upsert_rates(
        session,
        [
            FxRate(date(2026, 4, 1), "USD/THB", Decimal("34")),
            FxRate(date(2026, 11, 24), "USD/THB", Decimal("33.944")),
        ],
        "bot",
    )


async def _import(client: AsyncClient, csv_text: str) -> None:
    resp = await client.post(
        "/api/holdings/import", content=csv_text, headers={"content-type": "text/csv"}
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.usefixtures("market")
async def test_monthly_income(alice: AsyncClient) -> None:
    await _import(alice, "ticker,shares,avg_cost_usd\nKO,15,61\nVOO,2,480\nAMZN,3,178\n")
    resp = await alice.get("/api/income/monthly")  # defaults to the current year
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["year"] == 2026
    assert body["withholding_rate"] == "0.15"
    totals = body["totals"]
    assert totals["net_thb"] == "565.88546"
    assert totals["received_thb"] == "229.755"
    assert totals["upcoming_thb"] == "336.13046"
    assert Decimal(totals["gross_thb"]) - Decimal(totals["tax_thb"]) == Decimal(totals["net_thb"])

    april = body["months"][3]
    assert april["received_thb"] == "229.755"
    (payment,) = april["payments"]
    assert payment == {
        "ticker": "KO",
        "ex_date": "2026-04-01",
        "pay_date": "2026-04-01",
        "dps": "0.53",
        "shares": "15",
        "is_estimate": False,
        "status": "received",
        "gross_usd": "7.95",
        "tax_usd": "1.1925",
        "net_usd": "6.7575",
        "net_thb": "229.755",
        "usd_thb": "34",
        "fx_rate_date": "2026-04-01",
        "fx_is_fallback": False,
    }
    december = body["months"][11]
    assert [(p["ticker"], p["status"], p["fx_rate_date"]) for p in december["payments"]] == [
        ("KO", "upcoming", "2026-11-24"),  # future pay date → latest known rate
        ("VOO", "upcoming", "2026-11-24"),
    ]
    holdings = {h["ticker"]: h for h in body["holdings"]}
    assert holdings["KO"]["pay_months"] == [4, 12]
    assert holdings["AMZN"] == {
        "ticker": "AMZN",
        "pays_dividend": False,
        "pay_months": [],
        "net_usd": "0",
        "net_thb": "0",
        "yield_on_cost_pct": None,
    }
    assert body["missing_fx"] == []


@pytest.mark.usefixtures("market")
async def test_withholding_follows_user_setting(alice: AsyncClient) -> None:
    await _import(alice, "ticker,shares,avg_cost_usd\nKO,15,61\n")
    settings = {
        "withholding_rate": "0.30",
        "big_move_threshold_pct": "3",
        "dca_split": {"VOO": "100"},
    }
    assert (await alice.put("/api/settings", json=settings)).status_code == 200
    april = (await alice.get("/api/income/monthly", params={"year": 2026})).json()["months"][3]
    assert april["payments"][0]["net_usd"] == "5.565"  # 7.95 × 0.70


@pytest.mark.usefixtures("market")
async def test_income_is_per_user(alice: AsyncClient, login_as: LoginAs) -> None:
    await _import(alice, "ticker,shares,avg_cost_usd\nKO,15,61\n")
    bob = await login_as("bob@example.com")
    await _import(bob, "ticker,shares,avg_cost_usd\nKO,1,61\n")
    body = (await bob.get("/api/income/monthly", params={"year": 2026})).json()
    assert body["months"][3]["payments"][0]["shares"] == "1"


async def test_other_year_and_no_fx(alice: AsyncClient, session: AsyncSession) -> None:
    await _import(alice, "ticker,shares,avg_cost_usd\nKO,15,61\n")
    await upsert_events(session, [pay("KO", date(2025, 4, 1), "0.51")])
    body = (await alice.get("/api/income/monthly", params={"year": 2025})).json()
    assert body["year"] == 2025
    assert body["missing_fx"] == ["2025-04-01"]  # no FX stored at all in this test
    assert body["months"][3]["payments"][0]["net_thb"] is None
    assert body["totals"]["net_thb"] == "0"


@pytest.mark.parametrize("year", ["1999", "abc"])
async def test_year_validation(alice: AsyncClient, year: str) -> None:
    assert (await alice.get("/api/income/monthly", params={"year": year})).status_code == 422
