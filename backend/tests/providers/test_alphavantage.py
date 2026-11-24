from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.providers.alphavantage import BASE_URL, AlphaVantageDividendProvider, parse_dividends
from app.providers.base import ProviderRateLimitedError, ProviderResponseError
from app.providers.http import ProviderHttp

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "alphavantage"
KEY = "av-test-key"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def _noop_sleep(_: float) -> None:
    return None


def test_parse_recorded_stock() -> None:
    divs = parse_dividends("KO", load("dividends_KO.json"))
    assert len(divs) == 8
    assert [d.ex_date for d in divs] == sorted(d.ex_date for d in divs)  # oldest first
    latest = divs[-1]
    assert latest.ex_date == date(2026, 12, 1)
    assert latest.pay_date == date(2026, 12, 15)  # declared, not paid yet on 2026-11-24
    assert latest.declaration_date == date(2026, 10, 15)
    assert latest.amount == Decimal("0.53")


@pytest.mark.parametrize("name", ["dividends_VOO.json", "dividends_SCHD.json"])
def test_parse_recorded_etfs(name: str) -> None:
    divs = parse_dividends("ETF", load(name))
    assert len(divs) == 8
    assert all(d.pay_date is not None and d.pay_date >= d.ex_date for d in divs)


def test_amzn_placeholder_row_is_dropped() -> None:
    """AMZN pays no dividend; AV returns one row with amount "0.0"."""
    assert parse_dividends("AMZN", load("dividends_AMZN.json")) == []


def test_none_dates() -> None:
    body = {
        "data": [
            {
                "ex_dividend_date": "2026-12-01",
                "declaration_date": "None",
                "record_date": "None",
                "payment_date": "None",
                "amount": "0.25",
            }
        ]
    }
    (d,) = parse_dividends("X", body)
    assert (d.pay_date, d.record_date, d.declaration_date) == (None, None, None)


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (
            {"Information": "We have detected your API key ... 25 requests per day."},
            ProviderRateLimitedError,
        ),
        (
            {"Note": "Thank you for using Alpha Vantage! ... call frequency ..."},
            ProviderRateLimitedError,
        ),
        ({"Error Message": "Invalid API call."}, ProviderResponseError),
        ({"symbol": "X"}, ProviderResponseError),
        ({"data": [{"ex_dividend_date": "None", "amount": "1"}]}, ProviderResponseError),
        ({"data": [{"ex_dividend_date": "2026-01-01", "amount": "-1"}]}, ProviderResponseError),
        ([], ProviderResponseError),
    ],
)
def test_errors(body: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_dividends("X", body)


@respx.mock
async def test_request() -> None:
    route = respx.get(BASE_URL).respond(json=load("dividends_KO.json"))
    provider = AlphaVantageDividendProvider(
        ProviderHttp("alphavantage", httpx.AsyncClient(), sleep=_noop_sleep), KEY
    )
    divs = await provider.get_dividends("KO")
    params = route.calls.last.request.url.params
    assert (params["function"], params["symbol"], params["apikey"]) == ("DIVIDENDS", "KO", KEY)
    assert len(divs) == 8


@pytest.mark.parametrize(
    ("message", "retry_after"),
    [
        # recorded 2026-11-24 when calls were fired back to back
        (
            "Thank you for using Alpha Vantage! Please consider spreading out your free API "
            "requests more sparingly (1 request per second).",
            2.0,
        ),
        (
            "We have detected your API key as ... standard API rate limit is 25 requests per day.",
            None,
        ),
    ],
)
def test_burst_and_daily_limits_are_told_apart(message: str, retry_after: float | None) -> None:
    with pytest.raises(ProviderRateLimitedError) as info:
        parse_dividends("KO", {"Information": message})
    assert info.value.retry_after_s == retry_after
