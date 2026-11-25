"""GET /api/earnings/upcoming — the next earnings announcements of the user's holdings."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser, NowDep, SessionDep
from app.api.types import DecimalStr
from app.domain.market import NEW_YORK
from app.store.events import events_of_type
from app.store.holdings import list_holdings
from app.store.models import EventType

router = APIRouter(prefix="/api/earnings", tags=["earnings"])


class EarningsOut(BaseModel):
    ticker: str
    date: date  # US date
    hour: Literal["bmo", "amc", "dmh", "unknown"]
    time_utc: datetime | None  # the market open (bmo) / close (amc) it is announced around
    quarter: int | None
    fiscal_year: int | None
    eps_estimate: DecimalStr | None


@router.get("/upcoming")
async def upcoming(
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    days: Annotated[int, Query(ge=1, le=120)] = 90,
) -> list[EarningsOut]:
    today = now.astimezone(NEW_YORK).date()
    tickers = [h.ticker for h in await list_holdings(session, user.id) if h.shares > 0]
    events = await events_of_type(
        session, EventType.EARNINGS, tickers, today, today + timedelta(days=days)
    )
    return [
        EarningsOut(
            ticker=e.ticker or "",
            date=e.event_date,
            hour=e.payload.get("hour", "unknown"),
            time_utc=e.event_time_utc,
            quarter=e.payload.get("quarter"),
            fiscal_year=e.payload.get("fiscal_year"),
            eps_estimate=e.payload.get("eps_estimate"),
        )
        for e in events
        if e.ticker
    ]
