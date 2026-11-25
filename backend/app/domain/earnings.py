"""Earnings announcements → calendar events.

The provider gives a US date and "bmo" (before market open) / "amc" (after market close) /
"dmh" (during market hours) / unknown. The event's `event_time_utc` is the moment that word
refers to: the session's open for bmo, its close for amc (13:00 ET on early-close days), so the
UI can say e.g. "ก่อนตลาดเปิด 21:30" or "หลังตลาดปิด 04:00 (เช้าวันถัดไป)" in Bangkok time,
correct across US daylight-saving changes. dmh/unknown → no time.

`event_date` stays the US date, like every other market event in the calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.domain.market import session
from app.providers.base import Earnings

EARNINGS_SOURCE = "finnhub"


@dataclass(frozen=True, slots=True)
class EarningsEvent:
    ticker: str
    event_date: date
    event_time_utc: datetime | None
    payload: dict[str, Any]


def _s(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def announcement_time_utc(report_date: date, hour: str) -> datetime | None:
    s = session(report_date)
    if s is None:  # not a trading day: no session to be before/after
        return None
    if hour == "bmo":
        return s.open_utc
    if hour == "amc":
        return s.close_utc
    return None


def earnings_event(e: Earnings) -> EarningsEvent:
    return EarningsEvent(
        ticker=e.ticker,
        event_date=e.report_date,
        event_time_utc=announcement_time_utc(e.report_date, e.hour),
        payload={
            "hour": e.hour,
            "quarter": e.quarter,
            "fiscal_year": e.year,
            "eps_estimate": _s(e.eps_estimate),
            "eps_actual": _s(e.eps_actual),
            "revenue_estimate": _s(e.revenue_estimate),
            "revenue_actual": _s(e.revenue_actual),
            "reported": e.eps_actual is not None,
        },
    )
