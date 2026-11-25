"""GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD — per day: portfolio change + events."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, NowDep, SessionDep
from app.api.types import DecimalStr
from app.domain.calendar import (
    MAX_RANGE_DAYS,
    CalendarEvent,
    DayPortfolio,
    DayStatus,
    build_calendar,
    period_change,
)
from app.domain.market import NEW_YORK
from app.store.events import events_for
from app.store.holdings import list_holdings
from app.store.portfolio_daily import days_between
from app.store.settings import get_user_settings

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class DayPortfolioOut(BaseModel):
    value_thb: DecimalStr
    change_pct: DecimalStr | None
    change_thb: DecimalStr | None


class EventOut(BaseModel):
    id: int
    type: str
    ticker: str | None
    event_date: date
    event_time_utc: datetime | None
    is_estimate: bool
    payload: dict[str, Any]


class DayOut(BaseModel):
    date: date
    status: DayStatus
    portfolio: DayPortfolioOut | None
    events: list[EventOut]


class PeriodOut(BaseModel):
    change_pct: DecimalStr  # compounded over the range
    change_thb: DecimalStr
    trading_days: int


class CalendarOut(BaseModel):
    from_: date = Field(serialization_alias="from")
    to: date
    period: PeriodOut | None  # portfolio change over the whole range (e.g. "this month")
    days: list[DayOut]


@router.get("")
async def get_calendar(
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
) -> CalendarOut:
    if to < from_ or (to - from_).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"'to' must be on/after 'from' and the range at most {MAX_RANGE_DAYS} days",
        )
    holdings = await list_holdings(session, user.id)
    tickers = [h.ticker for h in holdings if h.shares > 0]
    settings = await get_user_settings(session, user.id)
    rows = await days_between(session, user.id, from_, to)
    events = await events_for(session, tickers, from_, to)

    days = build_calendar(
        from_,
        to,
        today=now.astimezone(NEW_YORK).date(),
        portfolio={
            d: DayPortfolio(value_thb=r.value_thb, change_pct=r.change_pct, change_thb=r.change_thb)
            for d, r in rows.items()
        },
        events=[
            CalendarEvent(
                id=e.id,
                type=e.type,
                ticker=e.ticker,
                event_date=e.event_date,
                event_time_utc=e.event_time_utc,
                is_estimate=e.is_estimate,
                payload=e.payload,
            )
            for e in events
        ],
        big_move_threshold=settings.big_move_threshold_pct,
    )
    period = period_change(d.portfolio for d in days if d.portfolio)
    return CalendarOut(
        from_=from_,
        to=to,
        period=PeriodOut(
            change_pct=period.change_pct,
            change_thb=period.change_thb,
            trading_days=period.trading_days,
        )
        if period
        else None,
        days=[
            DayOut(
                date=d.day,
                status=d.status,
                portfolio=DayPortfolioOut(
                    value_thb=d.portfolio.value_thb,
                    change_pct=d.portfolio.change_pct,
                    change_thb=d.portfolio.change_thb,
                )
                if d.portfolio
                else None,
                events=[
                    EventOut(
                        id=e.id,
                        type=e.type,
                        ticker=e.ticker,
                        event_date=e.event_date,
                        event_time_utc=e.event_time_utc,
                        is_estimate=e.is_estimate,
                        payload=dict(e.payload),
                    )
                    for e in d.events
                ],
            )
            for d in days
        ],
    )
