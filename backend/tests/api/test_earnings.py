from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_now
from app.store.events import EventIn, upsert_events
from app.store.models import EventType
from tests.api.conftest import LoginAs, buy

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def pin_clock(app: FastAPI) -> None:
    app.dependency_overrides[get_now] = lambda: NOW


def ev(ticker: str, d: date, hour: str, time_utc: datetime | None = None) -> EventIn:
    return EventIn(
        type=EventType.EARNINGS,
        ticker=ticker,
        event_date=d,
        event_time_utc=time_utc,
        source="finnhub",
        payload={"hour": hour, "quarter": 2, "fiscal_year": 2027, "eps_estimate": "4.9626"},
    )


async def test_upcoming_earnings_of_my_holdings(
    alice: AsyncClient, login_as: LoginAs, session: AsyncSession
) -> None:
    await buy(alice, "MSFT", "1")
    await buy(alice, "KO", "1")
    await upsert_events(
        session,
        [
            ev("MSFT", date(2027, 1, 26), "unknown"),
            ev("KO", date(2027, 2, 8), "amc", datetime(2027, 2, 8, 21, 0, tzinfo=UTC)),
            ev("NVDA", date(2027, 2, 23), "amc"),  # not held
            ev("KO", date(2026, 10, 21), "bmo"),  # past
            ev("KO", date(2027, 6, 1), "bmo"),  # beyond 90 days
        ],
    )
    body = (await alice.get("/api/earnings/upcoming")).json()
    assert [(e["ticker"], e["date"], e["hour"]) for e in body] == [
        ("MSFT", "2027-01-26", "unknown"),
        ("KO", "2027-02-08", "amc"),
    ]
    assert body[1]["time_utc"] == "2027-02-08T21:00:00Z"
    assert body[0]["eps_estimate"] == "4.9626"

    bob = await login_as("bob@example.com")
    assert (await bob.get("/api/earnings/upcoming")).json() == []


async def test_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/earnings/upcoming")).status_code == 401
