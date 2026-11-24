"""Projected (not yet declared) dividends, estimated from the last 4 payments.

- amount   = mean dividend per share of the last 4 payments
- cadence  = median gap between their ex-dates, snapped to monthly/quarterly/semi/annual
- ex-date  = last ex-date + cadence, moved to the next US trading day if needed
- pay date = projected ex-date + median ex->pay lag
Projection starts after the latest known (paid or declared) ex-date.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from statistics import median

from app.domain.market import is_trading_day

LOOKBACK = 4

# (months between payments, typical gap in days)
_CADENCES: tuple[tuple[int, int], ...] = ((1, 30), (3, 91), (6, 182), (12, 365))


@dataclass(frozen=True, slots=True)
class DividendRecord:
    ex_date: date
    pay_date: date | None
    amount: Decimal  # USD per share


@dataclass(frozen=True, slots=True)
class EstimatedDividend:
    ex_date: date
    pay_date: date
    amount: Decimal
    is_estimate: bool = True


def add_months(d: date, months: int) -> date:
    """Same day-of-month `months` later, clamped to month end (Jan 31 + 1 -> Feb 28)."""
    year, month0 = divmod(d.year * 12 + d.month - 1 + months, 12)
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _next_trading_day_on_or_after(d: date) -> date:
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def _cadence_months(ex_dates: Sequence[date]) -> int | None:
    gaps = [(b - a).days for a, b in pairwise(ex_dates)]
    if not gaps:
        return None
    gap = median(gaps)
    months, typical = min(_CADENCES, key=lambda c: abs(c[1] - gap))
    # Reject irregular histories (e.g. one-off specials) rather than guessing.
    if abs(typical - gap) > typical * 0.35:
        return None
    return months


def estimate_dividends(
    history: Sequence[DividendRecord], *, through: date
) -> list[EstimatedDividend]:
    """Estimated payments with ex-date after the latest known one and on/before `through`.

    Returns [] for non-payers (e.g. AMZN) or when history is too short/irregular.
    """
    if len(history) < 2:
        return []
    recent = sorted(history, key=lambda r: r.ex_date)[-LOOKBACK:]
    months = _cadence_months([r.ex_date for r in recent])
    if months is None:
        return []

    amount = sum((r.amount for r in recent), Decimal(0)) / len(recent)
    lags = [(r.pay_date - r.ex_date).days for r in recent if r.pay_date is not None]
    lag = timedelta(days=round(median(lags)) if lags else 0)

    out: list[EstimatedDividend] = []
    last_ex = recent[-1].ex_date
    step = 1
    while True:
        ex = _next_trading_day_on_or_after(add_months(last_ex, months * step))
        if ex > through:
            break
        out.append(EstimatedDividend(ex_date=ex, pay_date=ex + lag, amount=amount))
        step += 1
    return out
