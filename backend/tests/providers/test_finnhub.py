from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.providers.base import ProviderAccessDeniedError, ProviderResponseError
from app.providers.finnhub import (
    BASE_URL,
    FinnhubEarningsProvider,
    FinnhubQuoteProvider,
    parse_earnings,
    parse_quote,
)
from app.providers.http import ProviderHttp

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "finnhub"
TOKEN = "finnhub-test-token"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def _noop_sleep(_: float) -> None:
    return None


@pytest.fixture
def provider() -> FinnhubQuoteProvider:
    http = ProviderHttp("finnhub", httpx.AsyncClient(), sleep=_noop_sleep)
    return FinnhubQuoteProvider(http, TOKEN)


def test_parse_recorded_quote() -> None:
    q = parse_quote("VOO", load("quote_VOO.json"))
    assert q.price == Decimal("655.46")  # via str(), not Decimal(655.46)
    assert q.prev_close == Decimal("663.91")
    assert q.change == Decimal("-8.45")
    assert round(q.change_pct, 4) == Decimal("-1.2728")
    assert q.as_of_utc == datetime.fromtimestamp(1795535385, UTC)


@pytest.mark.parametrize(
    "body",
    [
        # unknown symbol: Finnhub answers 200 with zeros
        {"c": 0, "d": None, "dp": None, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0},
        {"c": 10},
        {"c": "abc", "pc": 1, "t": 1},
        [],
    ],
)
def test_parse_rejects_unusable_quotes(body: Any) -> None:
    with pytest.raises(ProviderResponseError):
        parse_quote("ZZZZ", body)


@respx.mock
async def test_get_quote_request(provider: FinnhubQuoteProvider) -> None:
    route = respx.get(f"{BASE_URL}/quote").respond(json=load("quote_VOO.json"))
    q = await provider.get_quote("VOO")
    params = route.calls.last.request.url.params
    assert (params["symbol"], params["token"]) == ("VOO", TOKEN)
    assert q.ticker == "VOO"


@respx.mock
async def test_premium_endpoint_style_denial(provider: FinnhubQuoteProvider) -> None:
    respx.get(f"{BASE_URL}/quote").respond(403, json=load("forbidden.json"))
    with pytest.raises(ProviderAccessDeniedError) as info:
        await provider.get_quote("VOO")
    assert TOKEN not in str(info.value)


# --- earnings calendar ---


def test_parse_reported_earnings() -> None:
    [e] = parse_earnings("NVDA", load("earnings_NVDA_reported.json"))
    assert (e.report_date, e.hour, e.quarter, e.year) == (date(2026, 11, 17), "amc", 3, 2027)
    assert e.eps_estimate == Decimal("2.5252")
    assert e.eps_actual == Decimal("2.68")
    assert e.revenue_actual == Decimal("115844000000")


def test_parse_upcoming_earnings_with_unknown_hour() -> None:
    [e] = parse_earnings("MSFT", load("earnings_MSFT.json"))
    assert (e.report_date, e.hour) == (date(2027, 1, 26), "unknown")  # "" from Finnhub
    assert e.eps_actual is None


def test_parse_skips_other_symbols_and_bad_rows() -> None:
    body = {
        "earningsCalendar": [
            {"symbol": "KO", "date": "2027-02-08", "hour": "AMC", "epsEstimate": 0.7},
            {"symbol": "NVDA", "date": "2027-02-23", "hour": "amc"},  # not asked for
            {"symbol": "KO", "date": "not a date"},
            "junk",
        ]
    }
    [e] = parse_earnings("KO", body)
    assert (e.hour, e.eps_estimate) == ("amc", Decimal("0.7"))
    assert parse_earnings("VOO", load("earnings_empty.json")) == []  # ETFs report nothing


@pytest.mark.parametrize("body", [{}, [], {"earningsCalendar": None}, "x"])
def test_parse_earnings_rejects_unexpected_shapes(body: Any) -> None:
    with pytest.raises(ProviderResponseError):
        parse_earnings("KO", body)


@respx.mock
async def test_earnings_request_is_per_symbol() -> None:
    route = respx.get(f"{BASE_URL}/calendar/earnings").mock(
        return_value=httpx.Response(200, json=load("earnings_MSFT.json"))
    )
    http = ProviderHttp("finnhub", httpx.AsyncClient(), sleep=_noop_sleep)
    rows = await FinnhubEarningsProvider(http, TOKEN).get_earnings(
        "MSFT", date(2026, 11, 25), date(2027, 2, 23)
    )
    assert [r.report_date for r in rows] == [date(2027, 1, 26)]
    params = route.calls.last.request.url.params
    assert (params["symbol"], params["from"], params["to"]) == ("MSFT", "2026-11-25", "2027-02-23")
