"""GET /api/day/{date} — everything about one US trading date for the current user.

The portfolio and every holding's move are computed from the shares held at the end of that
day and that day's closes (the same rule as the calendar's portfolio_daily). Events follow the
calendar's rules; news is what was published on that New York calendar date, per ticker.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, NowDep, SessionDep
from app.api.types import DecimalStr
from app.domain.calendar import (
    CalendarEvent,
    DayPortfolio,
    DayStatus,
    build_calendar,
    concerns_user,
)
from app.domain.errors import NoFxRateError
from app.domain.market import NEW_YORK
from app.domain.portfolio import HoldingDay, portfolio_change
from app.domain.portfolio_history import implied_prev_close
from app.services.fx import fx_rate_on
from app.store import news as news_store
from app.store.events import events_for
from app.store.prices import day_prices
from app.store.settings import get_user_settings
from app.store.trades import ledger_for

router = APIRouter(prefix="/api/day", tags=["day"])

HUNDRED = 100


class DayPortfolioOut(BaseModel):
    value_usd: DecimalStr
    value_thb: DecimalStr
    change_pct: DecimalStr
    change_usd: DecimalStr
    change_thb: DecimalStr
    usd_thb: DecimalStr
    fx_rate_date: date


class HoldingMoveOut(BaseModel):
    ticker: str
    shares: DecimalStr
    close: DecimalStr
    change_pct: DecimalStr
    change_usd: DecimalStr
    change_thb: DecimalStr
    weight_pct: DecimalStr  # share of the portfolio at the previous close


class EventOut(BaseModel):
    id: int
    type: str
    ticker: str | None
    event_date: date
    event_time_utc: datetime | None
    is_estimate: bool
    payload: dict[str, Any]


class NewsItemOut(BaseModel):
    id: int
    published_at: datetime
    headline: str
    source: str
    url: str
    snippet: str | None
    summary: str | None  # Thai, once scored (Phase 4)
    importance: int | None  # 1-5, once scored (Phase 4)


class TickerNewsOut(BaseModel):
    ticker: str
    total: int  # all of that day's items; `items` is the top of them
    items: list[NewsItemOut]


class DayOut(BaseModel):
    date: date
    status: DayStatus
    portfolio: DayPortfolioOut | None
    holdings: list[HoldingMoveOut]  # by |change %|, largest first
    unpriced: list[str]  # held that day, no close (yet)
    events: list[EventOut]
    news: list[TickerNewsOut]  # holdings' order first, then the rest


@router.get("/{day}")
async def get_day(
    day: Annotated[date, Path()],
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    news_per_ticker: Annotated[int, Query(ge=0, le=50)] = 10,
) -> DayOut:
    if day.year < 2000 or day.year > 2100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "date out of range")
    today = now.astimezone(NEW_YORK).date()
    ledger = await ledger_for(session, user.id)
    positions = ledger.positions_on(day)
    tickers = sorted(ledger.tickers)

    # --- portfolio and holdings ---
    prices = await day_prices(session, [p.ticker for p in positions], day, day)
    change = None
    fx = None
    if positions:
        try:
            fx = await fx_rate_on(session, day)
        except NoFxRateError:
            fx = None
    if fx is not None:
        holding_days = []
        for p in positions:
            price = prices.get(p.ticker, {}).get(day)
            holding_days.append(
                HoldingDay(
                    ticker=p.ticker,
                    shares=p.shares,
                    prev_close=implied_prev_close(price) if price else None,
                    close=price.close if price else None,
                )
            )
        change = portfolio_change(holding_days, fx.rate)

    # --- events (the calendar's rules) ---
    settings = await get_user_settings(session, user.id)
    raw_events = [
        CalendarEvent(
            id=e.id,
            type=e.type,
            ticker=e.ticker,
            event_date=e.event_date,
            event_time_utc=e.event_time_utc,
            is_estimate=e.is_estimate,
            payload=e.payload,
        )
        for e in await events_for(session, tickers, day, day)
    ]
    [cal] = build_calendar(
        day,
        day,
        today=today,
        portfolio={day: DayPortfolio(change.value_thb, change.change_pct, change.change_thb)}
        if change
        else {},
        events=[e for e in raw_events if concerns_user(e, ledger, today)],
        big_move_threshold=settings.big_move_threshold_pct,
    )

    # --- news of that New York day, for what was held then ---
    held_tickers = [p.ticker for p in positions] or (
        [p.ticker for p in ledger.positions_on(today)] if day > today else []
    )
    start = datetime.combine(day, time.min, NEW_YORK)
    items, totals = await news_store.news_between(
        session, held_tickers, start, start + timedelta(days=1), news_per_ticker
    )
    holdings: list[HoldingMoveOut] = []
    if change is not None:
        shares = {p.ticker: p.shares for p in positions}
        holdings = [
            HoldingMoveOut(
                ticker=h.ticker,
                shares=shares[h.ticker],
                close=prices[h.ticker][day].close,
                change_pct=h.change_pct,
                change_usd=h.change_usd,
                change_thb=h.change_usd * change.usd_thb,
                weight_pct=h.weight * HUNDRED,
            )
            for h in change.holdings
        ]
    moved = [h.ticker for h in holdings]
    order = moved + [t for t in held_tickers if t not in moved]

    return DayOut(
        date=day,
        status=cal.status,
        portfolio=DayPortfolioOut(
            value_usd=change.value_usd,
            value_thb=change.value_thb,
            change_pct=change.change_pct,
            change_usd=change.change_usd,
            change_thb=change.change_thb,
            usd_thb=change.usd_thb,
            fx_rate_date=fx.rate_date,
        )
        if change and fx
        else None,
        holdings=holdings,
        # only a trading day that has happened can be missing a close
        unpriced=[]
        if cal.status in ("closed", "future")
        else list(change.excluded)
        if change
        else [p.ticker for p in positions],
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
            for e in cal.events
        ],
        news=[
            TickerNewsOut(
                ticker=t,
                total=totals.get(t, 0),
                items=[
                    NewsItemOut(
                        id=n.id,
                        published_at=n.published_at,
                        headline=n.headline,
                        source=n.source,
                        url=n.url,
                        snippet=n.snippet,
                        summary=n.summary,
                        importance=n.importance,
                    )
                    for n in items.get(t, [])
                ],
            )
            for t in order
            if totals.get(t)
        ],
    )
