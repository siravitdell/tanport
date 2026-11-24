"""Calendar month view: one entry per date with market status, portfolio change and events.

Dates are US trading dates (a US session's close lands early the next morning in Bangkok;
the calendar files it under the session's own date, like every quote screen).

Status — never shows 0 % for a day without data:
  "ok"       trading day with a portfolio_daily row
  "no_data"  trading day in the past/today without a row yet
  "future"   trading day after today
  "closed"   weekend or US market holiday
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from app.domain.market import is_trading_day

DayStatus = Literal["ok", "no_data", "future", "closed"]
MAX_RANGE_DAYS = 62


@dataclass(frozen=True, slots=True)
class DayPortfolio:
    value_thb: Decimal
    change_pct: Decimal | None
    change_thb: Decimal | None


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    id: int
    type: str
    ticker: str | None
    event_date: date
    event_time_utc: datetime | None
    is_estimate: bool
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CalendarDay:
    day: date
    status: DayStatus
    portfolio: DayPortfolio | None
    events: tuple[CalendarEvent, ...]


def _keep(event: CalendarEvent, threshold: Decimal) -> bool:
    """price_move events are stored at the lowest threshold of any user; apply this user's."""
    if event.type != "price_move":
        return True
    raw = event.payload.get("change_pct")
    try:
        return raw is not None and abs(Decimal(str(raw))) >= threshold
    except ArithmeticError:
        return False


def build_calendar(
    start: date,
    end: date,
    *,
    today: date,
    portfolio: Mapping[date, DayPortfolio],
    events: Sequence[CalendarEvent],
    big_move_threshold: Decimal,
) -> list[CalendarDay]:
    if end < start:
        raise ValueError("end must be on or after start")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"range longer than {MAX_RANGE_DAYS} days")

    by_day: dict[date, list[CalendarEvent]] = {}
    for e in events:
        if _keep(e, big_move_threshold):
            by_day.setdefault(e.event_date, []).append(e)

    days: list[CalendarDay] = []
    d = start
    while d <= end:
        status: DayStatus
        row = portfolio.get(d)
        if row is not None:
            status = "ok"
        elif not is_trading_day(d):
            status = "closed"
        elif d > today:
            status = "future"
        else:
            status = "no_data"
        days.append(
            CalendarDay(
                day=d,
                status=status,
                portfolio=row,
                events=tuple(by_day.get(d, [])),
            )
        )
        d += timedelta(days=1)
    return days
