"""Turn a ticker's dividend history into calendar events (shared by all users).

Two events per payment — the ex-date and the pay date are different days:
  ex_dividend   on the ex-date  (you must hold shares *before* this day)
  dividend_pay  on the pay date (cash arrives)
Payload carries per-share facts only; each user's net THB is computed at read time.

Projected payments (not yet declared) come from app.domain.estimates and are marked
is_estimate with source "estimate".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.domain.estimates import DividendRecord, estimate_dividends
from app.providers.base import Dividend

ESTIMATE_SOURCE = "estimate"
DPS_PLACES = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class DividendEvent:
    type: str  # "ex_dividend" | "dividend_pay"
    ticker: str
    event_date: date
    is_estimate: bool
    source: str
    payload: dict[str, Any]


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def dividend_events(
    ticker: str,
    dividends: Sequence[Dividend],
    *,
    window_start: date,
    through: date,
    source: str,
) -> list[DividendEvent]:
    """Events dated in [window_start, through]: declared ones plus estimates after them."""
    events: list[DividendEvent] = []

    def add(ex: date, pay: date | None, dps: str, estimate: bool, extra: dict[str, Any]) -> None:
        src = ESTIMATE_SOURCE if estimate else source
        base = {"dps": dps, "ex_date": ex.isoformat(), "pay_date": _iso(pay), **extra}
        if window_start <= ex <= through:
            events.append(DividendEvent("ex_dividend", ticker, ex, estimate, src, base))
        if pay is not None and window_start <= pay <= through:
            events.append(DividendEvent("dividend_pay", ticker, pay, estimate, src, base))

    for d in dividends:
        add(
            d.ex_date,
            d.pay_date,
            str(d.amount),
            False,
            {"record_date": _iso(d.record_date), "declaration_date": _iso(d.declaration_date)},
        )

    history = [DividendRecord(d.ex_date, d.pay_date, d.amount) for d in dividends]
    for est in estimate_dividends(history, through=through):
        # a mean of 4 amounts: store at a sane precision (USD per share, 6 dp)
        dps = est.amount.quantize(DPS_PLACES, rounding=ROUND_HALF_UP)
        add(est.ex_date, est.pay_date, str(dps), True, {})

    events.sort(key=lambda e: (e.event_date, e.type))
    return events
