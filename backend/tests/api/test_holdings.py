from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.api.conftest import LoginAs

CSV = {"content-type": "text/csv"}


async def _create(c: AsyncClient, ticker: str, shares: Any, cost: Any) -> dict[str, Any]:
    resp = await c.post(
        "/api/holdings", json={"ticker": ticker, "shares": shares, "avg_cost_usd": cost}
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_new_user_has_no_holdings(alice: AsyncClient) -> None:
    resp = await alice.get("/api/holdings")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_returns_money_as_strings(alice: AsyncClient) -> None:
    body = await _create(alice, "voo", "12.50", "480.2")
    assert body["ticker"] == "VOO"
    assert body["shares"] == "12.5"
    assert body["avg_cost_usd"] == "480.2"


async def test_json_numbers_are_accepted_without_float_noise(alice: AsyncClient) -> None:
    body = await _create(alice, "KO", 0.1, 61.07)
    assert body["shares"] == "0.1"
    assert body["avg_cost_usd"] == "61.07"


@pytest.mark.parametrize(
    "payload",
    [
        {"ticker": "$$$", "shares": "1", "avg_cost_usd": "1"},
        {"ticker": "VOO", "shares": "-1", "avg_cost_usd": "1"},
        {"ticker": "VOO", "shares": "1", "avg_cost_usd": "abc"},
        {"ticker": "VOO", "shares": "1.123456789", "avg_cost_usd": "1"},  # > 8 decimals
        {"ticker": "VOO", "shares": "1"},
    ],
)
async def test_create_validation(alice: AsyncClient, payload: dict[str, Any]) -> None:
    assert (await alice.post("/api/holdings", json=payload)).status_code == 422


async def test_duplicate_ticker_conflict(alice: AsyncClient) -> None:
    await _create(alice, "VOO", "1", "1")
    resp = await alice.post(
        "/api/holdings", json={"ticker": "voo", "shares": "2", "avg_cost_usd": "2"}
    )
    assert resp.status_code == 409


async def test_get_update_delete(alice: AsyncClient) -> None:
    created = await _create(alice, "SCHD", "10", "26.1")
    url = f"/api/holdings/{created['id']}"

    assert (await alice.get(url)).json()["ticker"] == "SCHD"

    updated = await alice.put(url, json={"shares": "12.25", "avg_cost_usd": "26.4"})
    assert updated.status_code == 200
    assert (updated.json()["shares"], updated.json()["avg_cost_usd"]) == ("12.25", "26.4")

    assert (await alice.delete(url)).status_code == 204
    assert (await alice.get(url)).status_code == 404
    assert (await alice.delete(url)).status_code == 404


async def test_users_cannot_see_or_touch_each_others_holdings(
    alice: AsyncClient, login_as: LoginAs
) -> None:
    bob = await login_as("bob@example.com")
    alices = await _create(alice, "NVDA", "3", "120")
    url = f"/api/holdings/{alices['id']}"

    assert (await bob.get("/api/holdings")).json() == []
    assert (await bob.get(url)).status_code == 404
    assert (await bob.put(url, json={"shares": "0", "avg_cost_usd": "0"})).status_code == 404
    assert (await bob.delete(url)).status_code == 404
    # Bob can hold the same ticker independently
    await _create(bob, "NVDA", "1", "100")
    assert (await alice.get(url)).json()["shares"] == "3"


async def test_import_creates_and_updates(alice: AsyncClient) -> None:
    await _create(alice, "VOO", "1", "400")
    await _create(alice, "AMZN", "4", "178.3")  # not in the file → kept

    csv_text = "ticker,shares,avg_cost_usd\nVOO,12.5,480.20\nko,15,61\n"
    resp = await alice.post("/api/holdings/import", content=csv_text, headers=CSV)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == ["KO"]
    assert body["updated"] == ["VOO"]
    by_ticker = {h["ticker"]: h for h in body["holdings"]}
    assert set(by_ticker) == {"AMZN", "KO", "VOO"}
    assert by_ticker["VOO"]["shares"] == "12.5"
    assert by_ticker["VOO"]["avg_cost_usd"] == "480.2"


async def test_import_is_all_or_nothing(alice: AsyncClient) -> None:
    await _create(alice, "VOO", "1", "400")
    csv_text = "ticker,shares,avg_cost_usd\nVOO,99,1\nKO,abc,61\n"
    resp = await alice.post("/api/holdings/import", content=csv_text, headers=CSV)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["errors"] == [{"line": 3, "column": "shares", "message": "not a number: 'abc'"}]
    holdings = (await alice.get("/api/holdings")).json()
    assert [(h["ticker"], h["shares"]) for h in holdings] == [("VOO", "1")]


async def test_import_rejects_wrong_content_type(alice: AsyncClient) -> None:
    resp = await alice.post("/api/holdings/import", json={"ticker": "VOO"})
    assert resp.status_code == 415


async def test_import_rejects_non_utf8(alice: AsyncClient) -> None:
    body = "ticker,shares,avg_cost_usd\nVOO,1,1\n".encode("utf-16")
    resp = await alice.post("/api/holdings/import", content=body, headers=CSV)
    assert resp.status_code == 422
