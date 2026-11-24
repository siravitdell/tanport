from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from app.domain.market import (
    easter_sunday,
    in_quote_window,
    is_market_open,
    is_trading_day,
    market_status,
    nyse_holidays,
    previous_trading_day,
    session,
    trading_days,
)


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
    ],
)
def test_easter(year: int, expected: date) -> None:
    assert easter_sunday(year) == expected


def test_nyse_holidays_2026() -> None:
    assert sorted(nyse_holidays(2026)) == [
        date(2026, 1, 1),
        date(2026, 1, 19),  # MLK
        date(2026, 2, 16),  # Washington's Birthday
        date(2026, 4, 3),  # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day observed (Jul 4 is a Saturday)
        date(2026, 9, 7),  # Labor Day
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),  # Christmas
    ]


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 12, 16), True),  # Wednesday
        (date(2026, 12, 19), False),  # Saturday
        (date(2026, 12, 20), False),  # Sunday
        (date(2026, 12, 25), False),  # Christmas
        (date(2021, 12, 31), True),  # Jan 1 2022 is Saturday → NOT observed on Friday
        (date(2022, 12, 26), False),  # Christmas on Sunday → observed Monday
        (date(2027, 12, 24), False),  # Christmas on Saturday → observed Friday
        (date(2021, 6, 18), True),  # Juneteenth only from 2022
        (date(2022, 6, 20), False),  # Juneteenth 2022 (Sunday) observed Monday
    ],
)
def test_is_trading_day(d: date, expected: bool) -> None:
    assert is_trading_day(d) is expected


@pytest.mark.parametrize(
    ("d", "open_bkk", "close_bkk", "close_bkk_date", "early"),
    [
        # US standard time: 21:30–04:00 Thai time
        (date(2026, 12, 16), time(21, 30), time(4, 0), date(2026, 12, 17), False),
        # US daylight time: 20:30–03:00 Thai time
        (date(2026, 7, 15), time(20, 30), time(3, 0), date(2026, 7, 16), False),
        # first trading day after DST starts (Mar 8 2026)
        (date(2026, 3, 9), time(20, 30), time(3, 0), date(2026, 3, 10), False),
        # last Friday before DST ends (Nov 1 2026) vs Monday after
        (date(2026, 10, 30), time(20, 30), time(3, 0), date(2026, 10, 31), False),
        (date(2026, 11, 2), time(21, 30), time(4, 0), date(2026, 11, 3), False),
        # early closes (13:00 ET)
        (date(2026, 11, 27), time(21, 30), time(1, 0), date(2026, 11, 28), True),
        (date(2026, 12, 24), time(21, 30), time(1, 0), date(2026, 12, 25), True),
        (date(2025, 7, 3), time(20, 30), time(0, 0), date(2025, 7, 4), True),
    ],
)
def test_session_in_bangkok(
    d: date, open_bkk: time, close_bkk: time, close_bkk_date: date, early: bool
) -> None:
    s = session(d)
    assert s is not None
    assert s.open_bangkok().time() == open_bkk
    assert s.open_bangkok().date() == d
    assert s.close_bangkok().time() == close_bkk
    assert s.close_bangkok().date() == close_bkk_date
    assert s.early_close is early


@pytest.mark.parametrize("d", [date(2026, 12, 19), date(2026, 7, 3)])
def test_no_session_when_closed(d: date) -> None:
    assert session(d) is None


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 12, 16, 14, 30, tzinfo=UTC), True),  # 09:30 ET open
        (datetime(2026, 12, 16, 14, 29, tzinfo=UTC), False),
        (datetime(2026, 12, 16, 20, 59, tzinfo=UTC), True),
        (datetime(2026, 12, 16, 21, 0, tzinfo=UTC), False),  # 16:00 ET close
        (datetime(2026, 12, 19, 16, 0, tzinfo=UTC), False),  # Saturday
        (datetime(2026, 11, 27, 18, 30, tzinfo=UTC), False),  # after 13:00 ET early close
    ],
)
def test_is_market_open(now: datetime, expected: bool) -> None:
    assert is_market_open(now) is expected


def test_is_market_open_requires_aware_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        is_market_open(datetime(2026, 12, 16, 15, 0))  # noqa: DTZ001


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 12, 17), date(2026, 12, 16)),
        (date(2026, 12, 21), date(2026, 12, 18)),  # Monday → Friday
        (date(2026, 12, 28), date(2026, 12, 24)),  # skip weekend + Christmas
    ],
)
def test_previous_trading_day(d: date, expected: date) -> None:
    assert previous_trading_day(d) == expected


def test_trading_days_range() -> None:
    assert trading_days(date(2026, 12, 24), date(2026, 12, 29)) == [
        date(2026, 12, 24),
        date(2026, 12, 28),
        date(2026, 12, 29),
    ]


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 12, 16, 14, 29, tzinfo=UTC), False),  # before open
        (datetime(2026, 12, 16, 15, 0, tzinfo=UTC), True),
        (datetime(2026, 12, 16, 21, 10, tzinfo=UTC), True),  # 16:10 ET, within 20-min grace
        (datetime(2026, 12, 16, 21, 20, tzinfo=UTC), False),
        (datetime(2026, 12, 19, 16, 0, tzinfo=UTC), False),  # Saturday
    ],
)
def test_in_quote_window(now: datetime, expected: bool) -> None:
    assert in_quote_window(now) is expected


@pytest.mark.parametrize(
    ("now", "is_open", "last", "next_open"),
    [
        # Wed 10:00 ET: open
        (
            datetime(2026, 12, 16, 15, 0, tzinfo=UTC),
            True,
            date(2026, 12, 16),
            datetime(2026, 12, 17, 14, 30, tzinfo=UTC),
        ),
        # Wed 08:00 ET: before the open → yesterday's prices
        (
            datetime(2026, 12, 16, 13, 0, tzinfo=UTC),
            False,
            date(2026, 12, 15),
            datetime(2026, 12, 16, 14, 30, tzinfo=UTC),
        ),
        # Saturday → Friday's session, opens Monday
        (
            datetime(2026, 12, 19, 12, 0, tzinfo=UTC),
            False,
            date(2026, 12, 18),
            datetime(2026, 12, 21, 14, 30, tzinfo=UTC),
        ),
        # Christmas Eve after the 13:00 early close → next open skips Christmas
        (
            datetime(2026, 12, 24, 19, 0, tzinfo=UTC),
            False,
            date(2026, 12, 24),
            datetime(2026, 12, 28, 14, 30, tzinfo=UTC),
        ),
        # summer (EDT): next open 13:30 UTC = 20:30 Bangkok
        (
            datetime(2026, 7, 15, 3, 0, tzinfo=UTC),
            False,
            date(2026, 7, 14),
            datetime(2026, 7, 15, 13, 30, tzinfo=UTC),
        ),
    ],
)
def test_market_status(now: datetime, is_open: bool, last: date, next_open: datetime) -> None:
    status = market_status(now)
    assert (status.is_open, status.last_session_date, status.next_open_utc) == (
        is_open,
        last,
        next_open,
    )
