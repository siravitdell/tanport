from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.providers.base import ProviderResponseError
from app.providers.http import ProviderHttp
from app.providers.tiingo import BASE_URL, TiingoPriceProvider, parse_bars

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tiingo"
TOKEN = "tiingo-test-token"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def _noop_sleep(_: float) -> None:
    return None


@pytest.fixture
def provider() -> TiingoPriceProvider:
    return TiingoPriceProvider(
        ProviderHttp("tiingo", httpx.AsyncClient(), sleep=_noop_sleep), TOKEN
    )


def test_parse_recorded_eod() -> None:
    bars = parse_bars("VOO", load("eod_VOO.json"))
    assert bars[0].trade_date == date(2026, 10, 26)
    assert bars[-1].trade_date == date(2026, 11, 23)
    assert bars[-1].close == Decimal("663.91")  # matches Finnhub's previous close that day
    assert bars[-1].high == Decimal("669.165")
    assert all(b.split_factor == 1 for b in bars)
    assert [b.trade_date for b in bars] == sorted(b.trade_date for b in bars)


def test_dividend_day_is_not_price_adjusted() -> None:
    rows = load("eod_KO_with_dividend.json")
    ex_row = next(r for r in rows if r["divCash"] > 0)
    bars = {b.trade_date: b for b in parse_bars("KO", rows)}
    ex_bar = bars[date.fromisoformat(ex_row["date"][:10])]
    assert ex_bar.close == Decimal(str(ex_row["close"]))  # raw close, not adjClose


@pytest.mark.parametrize(
    "body",
    [
        {"detail": "Error: Ticker 'ZZZZ' not found"},
        [{"date": "2026-11-23T00:00:00.000Z"}],
        [{"date": "nope", "close": 1}],
        [{"date": "2026-11-23T00:00:00.000Z", "close": 0}],
    ],
)
def test_parse_rejects_bad_bodies(body: Any) -> None:
    with pytest.raises(ProviderResponseError):
        parse_bars("ZZZZ", body)


@respx.mock
async def test_request_uses_auth_header_not_query(provider: TiingoPriceProvider) -> None:
    route = respx.get(f"{BASE_URL}/VOO/prices").respond(json=load("eod_VOO.json"))
    bars = await provider.get_daily_bars("VOO", date(2026, 11, 1), date(2026, 11, 23))
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Token {TOKEN}"
    assert "token" not in request.url.params
    assert request.url.params["startDate"] == "2026-11-01"
    assert request.url.params["endDate"] == "2026-11-23"
    assert bars[0].trade_date >= date(2026, 11, 1)


@respx.mock
async def test_unknown_ticker(provider: TiingoPriceProvider) -> None:
    respx.get(f"{BASE_URL}/ZZZZ/prices").respond(
        404, json={"detail": "Error: Ticker 'ZZZZ' not found"}
    )
    with pytest.raises(ProviderResponseError, match="not found"):
        await provider.get_daily_bars("ZZZZ", date(2026, 11, 1), date(2026, 11, 2))
