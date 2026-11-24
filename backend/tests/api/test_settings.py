from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.api.conftest import LoginAs

VALID = {
    "withholding_rate": "0.30",
    "big_move_threshold_pct": "2.5",
    "dca_split": {"voo": "60", "QQQM": "30", "SCHD": "10"},
}


async def test_new_user_gets_defaults(alice: AsyncClient) -> None:
    resp = await alice.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["withholding_rate"] == "0.15"
    assert body["big_move_threshold_pct"] == "3"
    assert body["dca_split"] == {"VOO": "70", "QQQM": "20", "SCHD": "10"}


async def test_put_settings(alice: AsyncClient) -> None:
    resp = await alice.put("/api/settings", json=VALID)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["withholding_rate"] == "0.3"
    assert body["big_move_threshold_pct"] == "2.5"
    assert body["dca_split"] == {"VOO": "60", "QQQM": "30", "SCHD": "10"}
    assert (await alice.get("/api/settings")).json()["dca_split"] == body["dca_split"]


@pytest.mark.parametrize(
    "changes",
    [
        {"withholding_rate": "1.5"},
        {"withholding_rate": "-0.1"},
        {"big_move_threshold_pct": "0"},
        {"dca_split": {"VOO": "70", "QQQM": "20"}},  # sums to 90
        {"dca_split": {}},
    ],
)
async def test_put_settings_validation(alice: AsyncClient, changes: dict[str, Any]) -> None:
    resp = await alice.put("/api/settings", json={**VALID, **changes})
    assert resp.status_code == 422


async def test_settings_are_per_user(alice: AsyncClient, login_as: LoginAs) -> None:
    await alice.put("/api/settings", json=VALID)
    bob = await login_as("bob@example.com")
    assert (await bob.get("/api/settings")).json()["withholding_rate"] == "0.15"
