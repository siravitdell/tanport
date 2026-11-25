from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_now
from app.domain.prices import PriceRow
from app.providers.base import FxRate, Quote
from app.store import fx as fx_store
from app.store.prices import upsert_prices
from app.store.quote_cache import save_quote
from tests.api.conftest import LoginAs, buy

CSV = {"content-type": "text/csv"}
NOW = datetime(2026, 11, 25, 5, 0, tzinfo=UTC)  # 12:00 in Bangkok


@pytest.fixture(autouse=True)
def fixed_now(app: FastAPI) -> None:
    app.dependency_overrides[get_now] = lambda: NOW


async def sell(c: AsyncClient, ticker: str, shares: str, price: str, day: str, **extra: Any) -> Any:
    return await c.post(
        "/api/trades",
        json={
            "side": "sell",
            "ticker": ticker,
            "trade_date": day,
            "shares": shares,
            "price_usd": price,
            "usd_thb": "33",
            **extra,
        },
    )


async def holdings(c: AsyncClient) -> dict[str, tuple[str, str]]:
    return {
        h["ticker"]: (h["shares"], h["avg_cost_usd"]) for h in (await c.get("/api/holdings")).json()
    }


async def test_a_buy_creates_the_holding(alice: AsyncClient) -> None:
    resp = await alice.post(
        "/api/trades",
        json={
            "side": "buy",
            "ticker": "voo",
            "trade_date": "2026-08-04",
            "shares": "1.5",
            "price_usd": "585.40",
            "fee_usd": "0.9",
            "usd_thb": "33.20",
        },
    )
    assert resp.status_code == 201, resp.text
    trade = resp.json()
    assert (trade["ticker"], trade["side"], trade["shares"]) == ("VOO", "buy", "1.5")
    assert trade["cash_usd"] == "-879"  # 1.5 × 585.40 + 0.9 fee, money out
    assert trade["cash_thb"] == "-29182.8"
    assert await holdings(alice) == {"VOO": ("1.5", "586")}  # fee is part of the cost


async def test_average_cost_partial_and_full_sale(alice: AsyncClient) -> None:
    await buy(alice, "NVDA", "5", "141.20", day="2026-08-04")
    await buy(alice, "NVDA", "2.93", "158.60", day="2026-09-08")
    resp = await sell(alice, "NVDA", "2", "153.87", "2026-11-09")
    assert resp.status_code == 201, resp.text
    assert resp.json()["cash_usd"] == "307.74"
    shares, avg = (await holdings(alice))["NVDA"]
    assert shares == "5.93"
    assert avg == "147.629004"  # (706 + 464.698) / 7.93, unchanged by the sale

    resp = await sell(alice, "NVDA", "5.93", "150", "2026-11-20")
    assert resp.status_code == 201
    assert await holdings(alice) == {}  # closed positions leave the holdings

    trades = (await alice.get("/api/trades")).json()
    assert [(t["trade_date"], t["side"]) for t in trades] == [
        ("2026-11-20", "sell"),
        ("2026-11-09", "sell"),
        ("2026-09-08", "buy"),
        ("2026-08-04", "buy"),
    ]


@pytest.mark.parametrize(
    ("shares", "day"),
    [
        ("3.00000001", "2026-11-01"),  # more than held
        ("1", "2026-01-01"),  # before it was bought (bought 2026-01-02)
    ],
)
async def test_overselling_is_refused(alice: AsyncClient, shares: str, day: str) -> None:
    await buy(alice, "KO", "3", "60")
    resp = await sell(alice, "KO", shares, "70", day)
    assert resp.status_code == 409
    assert "cannot sell" in resp.json()["detail"]
    assert len((await alice.get("/api/trades")).json()) == 1


async def test_delete_rebuilds_and_cannot_orphan_a_sale(alice: AsyncClient) -> None:
    bought = await buy(alice, "KO", "3", "60")
    sold = (await sell(alice, "KO", "1", "70", "2026-11-01")).json()

    resp = await alice.delete(f"/api/trades/{bought['id']}")
    assert resp.status_code == 409
    assert "later sale" in resp.json()["detail"]
    assert await holdings(alice) == {"KO": ("2", "60")}

    assert (await alice.delete(f"/api/trades/{sold['id']}")).status_code == 204
    assert await holdings(alice) == {"KO": ("3", "60")}
    assert (await alice.delete(f"/api/trades/{bought['id']}")).status_code == 204
    assert await holdings(alice) == {}


async def test_users_only_see_and_delete_their_own_trades(
    alice: AsyncClient, login_as: LoginAs
) -> None:
    bob = await login_as("bob@example.com")
    trade = await buy(alice, "VOO", "1", "500")
    assert (await bob.get("/api/trades")).json() == []
    assert (await bob.delete(f"/api/trades/{trade['id']}")).status_code == 404
    assert (await bob.get("/api/holdings")).json() == []
    assert await holdings(alice) == {"VOO": ("1", "500")}


async def test_rate_is_filled_from_the_bank_of_thailand(
    alice: AsyncClient, session: AsyncSession
) -> None:
    await fx_store.upsert_rates(
        session, [FxRate(date(2026, 11, 20), "USD/THB", Decimal("32.6"))], "bot"
    )
    body = {"side": "buy", "ticker": "KO", "shares": "1", "price_usd": "70"}

    # Sunday the 22nd: Friday's rate
    resp = await alice.post("/api/trades", json={**body, "trade_date": "2026-11-22"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["usd_thb"] == "32.6"

    resp = await alice.post("/api/trades", json={**body, "trade_date": "2026-11-01"})
    assert resp.status_code == 422
    assert "enter the rate" in resp.json()["detail"]

    fx = (await alice.get("/api/fx", params={"date": "2026-11-22"})).json()
    assert fx == {"usd_thb": "32.6", "rate_date": "2026-11-20", "is_fallback": True}
    assert (await alice.get("/api/fx", params={"date": "2026-11-01"})).status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        {"trade_date": "2026-11-26"},  # future (Bangkok today is the 25th)
        {"shares": "0"},
        {"price_usd": "-1"},
        {"usd_thb": "0"},
        {"ticker": "$$$"},
        {"side": "hold"},
        {"shares": "1.000000001"},  # more decimals than stored
    ],
)
async def test_invalid_trades(alice: AsyncClient, change: dict[str, str]) -> None:
    body = {
        "side": "buy",
        "ticker": "KO",
        "trade_date": "2026-11-01",
        "shares": "1",
        "price_usd": "70",
        "usd_thb": "33",
    }
    resp = await alice.post("/api/trades", json={**body, **change})
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/api/holdings"), ("PUT", "/api/holdings/1"), ("DELETE", "/api/holdings/1")],
)
async def test_holdings_are_read_only(alice: AsyncClient, method: str, path: str) -> None:
    assert (await alice.request(method, path, json={})).status_code == 405


# --- CSV import ---


async def test_import_trade_log_and_old_holdings_file(
    alice: AsyncClient, session: AsyncSession
) -> None:
    await fx_store.upsert_rates(
        session, [FxRate(date(2026, 11, 24), "USD/THB", Decimal("33.944"))], "bot"
    )
    log = (
        "date,side,ticker,shares,price_usd,fee_usd,usd_thb\n"
        "2026-08-04,buy,VOO,1.5,585.40,0,33.20\n"
        "2026-10-06,buy,VOO,1.46,603.10,,\n"  # empty rate: looked up, but none on/before then
    )
    resp = await alice.post("/api/trades/import", content=log, headers=CSV)
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"] == [
        {"line": 3, "column": "usd_thb", "message": "no rate known for 2026-10-06"}
    ]
    assert (await alice.get("/api/trades")).json() == []  # all or nothing

    resp = await alice.post(
        "/api/trades/import", content=log.replace(",,\n", ",,32.85\n"), headers=CSV
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 2

    # an old `ticker,shares,avg_cost_usd` file: buys today at today's rate
    resp = await alice.post(
        "/api/trades/import", content="ticker,shares,avg_cost_usd\nKO,15,61\n", headers=CSV
    )
    assert resp.status_code == 200, resp.text
    assert await holdings(alice) == {"VOO": ("2.96", "594.130405"), "KO": ("15", "61")}
    ko = next(t for t in (await alice.get("/api/trades")).json() if t["ticker"] == "KO")
    assert (ko["trade_date"], ko["usd_thb"]) == ("2026-11-25", "33.944")


async def test_import_rejects_bad_rows_and_oversells(alice: AsyncClient) -> None:
    resp = await alice.post(
        "/api/trades/import", content="ticker,shares,price_usd\nVOO,x,1\n", headers=CSV
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"][0]["column"] == "shares"

    oversell = "date,side,ticker,shares,price_usd,usd_thb\n2026-11-01,sell,VOO,1,500,33\n"
    resp = await alice.post("/api/trades/import", content=oversell, headers=CSV)
    assert resp.status_code == 409

    resp = await alice.post(
        "/api/trades/import", content="ticker", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 415
    assert (await alice.get("/api/trades")).json() == []


# --- portfolio ---


async def test_portfolio_values_positions_and_splits_pl(
    alice: AsyncClient, session: AsyncSession, redis: Redis
) -> None:
    await fx_store.upsert_rates(
        session, [FxRate(date(2026, 11, 24), "USD/THB", Decimal("33"))], "bot"
    )
    await buy(alice, "VOO", "10", "100", rate="35", day="2026-08-04")
    await buy(alice, "VOO", "10", "120", rate="34", day="2026-09-08")
    await buy(alice, "KO", "2", "50", rate="34", day="2026-09-08")
    await buy(alice, "NEW", "1", "10", rate="34", day="2026-09-08")
    resp = await sell(alice, "KO", "2", "55", "2026-11-09")  # +$10, at 33: 3630 − 3400
    assert resp.status_code == 201
    await save_quote(
        redis, Quote("VOO", Decimal(130), Decimal(128), Decimal(2), Decimal("1.5625"), NOW)
    )
    await upsert_prices(
        session,
        [PriceRow("NEW", date(2026, 11, 24), None, None, None, Decimal(12), None)],
        "tiingo",
    )

    body = (await alice.get("/api/portfolio")).json()
    assert body["fx"] == {"usd_thb": "33", "rate_date": "2026-11-24", "is_fallback": True}
    voo, new = body["positions"]
    assert (voo["ticker"], voo["price_source"], voo["value_thb"]) == ("VOO", "quote", "85800")
    assert (voo["unrealized_thb"], voo["price_pl_thb"], voo["fx_pl_thb"]) == (
        "10000",
        "13200",
        "-3200",
    )
    assert (new["ticker"], new["price_source"], new["value_usd"]) == ("NEW", "close", "12")
    t = body["totals"]
    assert t["trades"] == 5
    assert t["cost_thb"] == "76140"  # 75800 + 340
    assert t["realized_thb"] == "230"
    assert t["unpriced"] == []


async def test_portfolio_without_trades(alice: AsyncClient, session: AsyncSession) -> None:
    assert (await alice.get("/api/portfolio")).status_code == 503  # no FX rate at all yet
    await fx_store.upsert_rates(
        session, [FxRate(date(2026, 11, 24), "USD/THB", Decimal("33"))], "bot"
    )
    body = (await alice.get("/api/portfolio")).json()
    assert (body["positions"], body["totals"]) == ([], None)
