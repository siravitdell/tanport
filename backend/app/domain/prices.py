"""Daily change % from consecutive closes, adjusted for splits.

On a split day (factor f, e.g. 10 for 10:1) the previous close is divided by f, so a
split never shows up as a -90 % "move". Dividends are *not* adjusted: the ex-date drop
is part of the day's real price change, as on any quote screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.money import pct_change
from app.providers.base import DailyBar


@dataclass(frozen=True, slots=True)
class PriceRow:
    ticker: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    change_pct: Decimal | None  # None when there is no previous close to compare with


def with_changes(bars: Sequence[DailyBar], prev_close: Decimal | None) -> list[PriceRow]:
    """`prev_close` is the stored close just before the first bar (None if unknown)."""
    rows: list[PriceRow] = []
    prev = prev_close
    for bar in sorted(bars, key=lambda b: b.trade_date):
        change = None
        if prev is not None and prev > 0:
            change = pct_change(bar.close, prev / bar.split_factor)
        rows.append(
            PriceRow(
                ticker=bar.ticker,
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                change_pct=change,
            )
        )
        prev = bar.close
    return rows
