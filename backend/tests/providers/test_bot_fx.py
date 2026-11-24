from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.providers.base import ProviderAccessDeniedError, ProviderResponseError
from app.providers.bot_fx import BASE_URL, BotFxProvider, parse_rates
from app.providers.http import ProviderHttp

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bot" / "daily_ref_rate.json"
TOKEN = "bot-test-token"


def fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def body(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {"result": {"data": {"data_detail": rows}}}


async def _noop_sleep(_: float) -> None:
    return None


@pytest.fixture
def provider() -> BotFxProvider:
    return BotFxProvider(ProviderHttp("bot", httpx.AsyncClient(), sleep=_noop_sleep), TOKEN)


def test_parse_recorded_response() -> None:
    rates = parse_rates(fixture())
    assert len(rates) == 22
    newest = max(rates, key=lambda r: r.rate_date)
    assert newest.rate_date == date(2026, 11, 24)
    assert newest.rate == Decimal("33.9440000")  # exact, from the string — no float
    assert {r.pair for r in rates} == {"USD/THB"}


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"result": {"data": {}}},
        {"result": {"data": {"data_detail": "nope"}}},
        body([{"period": "2026-11-24"}]),
        body([{"period": "24/11/2026", "rate": "33.9"}]),
        body([{"period": "2026-11-24", "rate": "abc"}]),
        body([{"period": "2026-11-24", "rate": "0"}]),
    ],
)
def test_parse_rejects_bad_bodies(bad: dict[str, Any]) -> None:
    with pytest.raises(ProviderResponseError):
        parse_rates(bad)


@respx.mock
async def test_request_shape_and_sorting(provider: BotFxProvider) -> None:
    route = respx.get(BASE_URL).respond(json=fixture())
    rates = await provider.get_usd_thb(date(2026, 10, 26), date(2026, 11, 24))

    request = route.calls.last.request
    assert request.headers["authorization"] == TOKEN  # raw token, no "Bearer"
    assert request.url.params["start_period"] == "2026-10-26"
    assert request.url.params["end_period"] == "2026-11-24"
    dates = [r.rate_date for r in rates]
    assert dates == sorted(dates)
    assert dates[0] == date(2026, 10, 26)


@respx.mock
async def test_filters_rows_outside_requested_range(provider: BotFxProvider) -> None:
    respx.get(BASE_URL).respond(json=fixture())
    rates = await provider.get_usd_thb(date(2026, 11, 20), date(2026, 11, 23))
    assert [r.rate_date for r in rates] == [date(2026, 11, 20), date(2026, 11, 23)]


@respx.mock
async def test_long_ranges_are_split(provider: BotFxProvider) -> None:
    route = respx.get(BASE_URL).respond(json=body([]))
    await provider.get_usd_thb(date(2026, 1, 1), date(2026, 7, 19))  # 200 days
    windows = [
        (c.request.url.params["start_period"], c.request.url.params["end_period"])
        for c in route.calls
    ]
    assert windows[:2] == [("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-03-03")]
    assert windows[-1] == ("2026-07-06", "2026-07-19")
    assert len(windows) == 7
    for start, end in windows:  # BOT rejects ranges longer than 31 days
        assert (date.fromisoformat(end) - date.fromisoformat(start)).days < 31


@respx.mock
async def test_empty_range_on_holidays(provider: BotFxProvider) -> None:
    respx.get(BASE_URL).respond(json=body([]))
    assert await provider.get_usd_thb(date(2026, 4, 13), date(2026, 4, 15)) == []


async def test_reversed_range_makes_no_call(provider: BotFxProvider) -> None:
    assert await provider.get_usd_thb(date(2026, 2, 1), date(2026, 1, 1)) == []


@respx.mock
async def test_bad_token(provider: BotFxProvider) -> None:
    respx.get(BASE_URL).respond(401, json={"message": "Unauthorized"})
    with pytest.raises(ProviderAccessDeniedError):
        await provider.get_usd_thb(date(2026, 11, 1), date(2026, 11, 2))
