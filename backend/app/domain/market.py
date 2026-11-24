"""US equity market calendar (NYSE rules) and hours, derived from America/New_York.

Covers regular holidays and the standard 13:00 ET early closes. Unscheduled closures
(e.g. national days of mourning) cannot be predicted; for past dates the presence of
price data is the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
BANGKOK = ZoneInfo("Asia/Bangkok")

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + month // 12, month % 12 + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def easter_sunday(year: int) -> date:
    """Gregorian Easter (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> date | None:
    """Saturday -> Friday before, Sunday -> Monday after."""
    if d.weekday() == SAT:
        return d - timedelta(days=1)
    if d.weekday() == SUN:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=64)
def nyse_holidays(year: int) -> frozenset[date]:
    days: set[date | None] = set()
    new_year = date(year, 1, 1)
    # NYSE does not observe New Year's Day on the preceding Friday when Jan 1 is a Saturday.
    if new_year.weekday() != SAT:
        days.add(_observed(new_year))
    days.add(_nth_weekday(year, 1, MON, 3))  # Martin Luther King Jr. Day
    days.add(_nth_weekday(year, 2, MON, 3))  # Washington's Birthday
    days.add(easter_sunday(year) - timedelta(days=2))  # Good Friday
    days.add(_last_weekday(year, 5, MON))  # Memorial Day
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))  # Juneteenth
    days.add(_observed(date(year, 7, 4)))  # Independence Day
    days.add(_nth_weekday(year, 9, MON, 1))  # Labor Day
    days.add(_nth_weekday(year, 11, THU, 4))  # Thanksgiving
    days.add(_observed(date(year, 12, 25)))  # Christmas
    return frozenset(d for d in days if d is not None and d.year == year)


def is_trading_day(d: date) -> bool:
    return d.weekday() < SAT and d not in nyse_holidays(d.year)


def _is_early_close(d: date) -> bool:
    if not is_trading_day(d):
        return False
    day_after_thanksgiving = _nth_weekday(d.year, 11, THU, 4) + timedelta(days=1)
    return d in {date(d.year, 7, 3), day_after_thanksgiving, date(d.year, 12, 24)}


@dataclass(frozen=True, slots=True)
class Session:
    trade_date: date  # New York calendar date
    open_utc: datetime
    close_utc: datetime
    early_close: bool

    def open_bangkok(self) -> datetime:
        return self.open_utc.astimezone(BANGKOK)

    def close_bangkok(self) -> datetime:
        return self.close_utc.astimezone(BANGKOK)


def session(d: date) -> Session | None:
    """Regular session for New York date `d`, or None when the market is closed."""
    if not is_trading_day(d):
        return None
    early = _is_early_close(d)
    open_ny = datetime.combine(d, REGULAR_OPEN, tzinfo=NEW_YORK)
    close_ny = datetime.combine(d, EARLY_CLOSE if early else REGULAR_CLOSE, tzinfo=NEW_YORK)
    return Session(
        trade_date=d,
        open_utc=open_ny.astimezone(UTC),
        close_utc=close_ny.astimezone(UTC),
        early_close=early,
    )


def is_market_open(now_utc: datetime) -> bool:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    s = session(now_utc.astimezone(NEW_YORK).date())
    return s is not None and s.open_utc <= now_utc < s.close_utc


def previous_trading_day(d: date) -> date:
    prev = d - timedelta(days=1)
    while not is_trading_day(prev):
        prev -= timedelta(days=1)
    return prev


def trading_days(start: date, end: date) -> list[date]:
    """Trading days in [start, end]."""
    out: list[date] = []
    d = start
    while d <= end:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out
