from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.domain.calendar import (
    CalendarEvent,
    DayPortfolio,
    build_calendar,
    concerns_user,
    period_change,
)
from app.domain.trades import ShareLedger, TradeFact

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


@pytest.mark.parametrize(
    ("changes", "expected_pct", "expected_thb", "days"),
    [
        ([], None, None, 0),
        ([(None, None)], None, None, 0),  # first day of history: no change yet
        ([("1.5", "100")], "1.5", "100", 1),
        # compounded, not summed: 1.10 * 0.90 = 0.99 -> -1 %
        ([("10", "1000"), ("-10", "-1100")], "-1", "-100", 2),
        ([("0.59", "1"), ("-0.39", "2"), (None, None), ("0.03", "3")], "0.227758", "6", 3),
        # tiny daily moves keep their precision before the final quantize
        ([("0.0000004", "0"), ("0.0000004", "0")], "0.000001", "0", 2),
    ],
)
def test_period_change(
    changes: list[tuple[str | None, str | None]],
    expected_pct: str | None,
    expected_thb: str | None,
    days: int,
) -> None:
    def dec(value: str | None) -> Decimal | None:
        return D(value) if value is not None else None

    result = period_change([DayPortfolio(D(100), dec(p), dec(t)) for p, t in changes])
    if expected_pct is None:
        assert result is None
        return
    assert result is not None
    assert result.change_pct == dec(expected_pct)
    assert result.change_thb == dec(expected_thb)
    assert result.trading_days == days


def _ledger() -> ShareLedger:
    # KO: bought 1 Dec, sold all 10 Dec
    return ShareLedger(
        [
            TradeFact("KO", "buy", date(2026, 12, 1), D(5), D(70), D(0), D(33)),
            TradeFact("KO", "sell", date(2026, 12, 10), D(5), D(70), D(0), D(33)),
        ]
    )


@pytest.mark.parametrize(
    ("type_", "ticker", "day", "payload", "expected"),
    [
        ("macro", None, date(2026, 11, 1), {}, True),  # everyone's
        ("price_move", "KO", date(2026, 11, 30), {}, False),  # not bought yet
        ("price_move", "KO", date(2026, 12, 1), {}, True),  # bought that day
        ("price_move", "KO", date(2026, 12, 10), {}, False),  # sold that day
        ("ex_dividend", "KO", date(2026, 12, 1), {}, True),  # held on the day (no dividend)
        ("ex_dividend", "KO", date(2026, 12, 10), {}, True),  # held the day before: paid
        # paid after the sale, but earned before it: still shown
        ("dividend_pay", "KO", date(2026, 12, 15), {"ex_date": "2026-12-05"}, True),
        ("dividend_pay", "KO", date(2026, 12, 15), {"ex_date": "2026-11-20"}, False),
        (
            "dividend_pay",
            "KO",
            date(2026, 12, 20),
            {"ex_date": "2026-12-18"},
            False,
        ),  # future, not held
        ("price_move", "V", date(2026, 12, 5), {}, False),  # never held
    ],
)
def test_events_concern_positions_held_then(
    type_: str, ticker: str | None, day: date, payload: dict[str, Any], expected: bool
) -> None:
    event = CalendarEvent(1, type_, ticker, day, None, False, payload)
    assert concerns_user(event, _ledger(), today=TODAY) is expected
