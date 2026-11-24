from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.domain.calendar import CalendarEvent, DayPortfolio, build_calendar

D = Decimal
TODAY = date(2026, 12, 16)  # Wednesday


def event(day: date, type_: str, ticker: str | None, **payload: Any) -> CalendarEvent:
    return CalendarEvent(1, type_, ticker, day, None, False, payload)


def test_day_statuses() -> None:
    rows = {date(2026, 12, 15): DayPortfolio(D("179268"), D("-1.38"), D("-2484"))}
    days = build_calendar(
        date(2026, 12, 12),
        date(2026, 12, 25),
        today=TODAY,
        portfolio=rows,
        events=[],
        big_move_threshold=D(3),
    )
    status = {d.day.day: d.status for d in days}
    assert status[12] == "closed"  # Saturday
    assert status[14] == "no_data"  # trading day, nothing computed
    assert status[15] == "ok"
    assert status[16] == "no_data"  # today: close not in yet
    assert status[17] == "future"
    assert status[25] == "closed"  # Christmas
    assert days[3].portfolio == rows[date(2026, 12, 15)]
    assert all(d.portfolio is None for d in days if d.status != "ok")


def test_events_grouped_by_day_and_big_moves_filtered_per_user() -> None:
    d = date(2026, 12, 16)
    events = [
        event(d, "price_move", "NVDA", change_pct="-5.40"),
        event(d, "price_move", "KO", change_pct="2.5"),  # stored for a 2 % user
        event(d, "dividend_pay", "KO", net_thb="42"),
        event(d - timedelta(days=1), "macro", None, name="CPI"),
    ]
    days = build_calendar(
        d - timedelta(days=1), d, today=TODAY, portfolio={}, events=events, big_move_threshold=D(3)
    )
    assert [e.type for e in days[0].events] == ["macro"]
    assert [(e.type, e.ticker) for e in days[1].events] == [
        ("price_move", "NVDA"),
        ("dividend_pay", "KO"),
    ]

    lower = build_calendar(d, d, today=TODAY, portfolio={}, events=events, big_move_threshold=D(2))
    assert len(lower[0].events) == 3


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 12, 2), date(2026, 12, 1)), (date(2026, 1, 1), date(2026, 3, 5))],
)
def test_invalid_ranges(start: date, end: date) -> None:
    with pytest.raises(ValueError, match=r"range|end"):
        build_calendar(start, end, today=TODAY, portfolio={}, events=[], big_move_threshold=D(3))
