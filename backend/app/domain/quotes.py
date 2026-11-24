"""Today's prices view for one user: per-holding price/change/weight + portfolio totals.

Weights shown in the strip are by *current* market value ("สัดส่วนตามพอร์ตจริง").
The portfolio day change uses previous-close weights (app.domain.portfolio).
Holdings without a quote are listed with status "no_quote" and left out of totals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.domain.money import pct_change
from app.domain.portfolio import HoldingDay, PortfolioChange, portfolio_change, weights


@dataclass(frozen=True, slots=True)
class Position:
    ticker: str
    shares: Decimal


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    price: Decimal
    prev_close: Decimal
    as_of_utc: datetime


@dataclass(frozen=True, slots=True)
class HoldingQuote:
    ticker: str
    shares: Decimal
    status: Literal["ok", "no_quote"]
    price: Decimal | None
    prev_close: Decimal | None
    change: Decimal | None
    change_pct: Decimal | None
    value_usd: Decimal | None
    value_thb: Decimal | None
    weight: Decimal | None  # 0..1
    as_of_utc: datetime | None


@dataclass(frozen=True, slots=True)
class QuotesView:
    holdings: tuple[HoldingQuote, ...]  # by weight desc, then quote-less ones by ticker
    portfolio: PortfolioChange | None  # None when nothing is priced or no FX rate
    as_of_utc: datetime | None  # newest quote time


def _no_quote(p: Position) -> HoldingQuote:
    return HoldingQuote(
        ticker=p.ticker,
        shares=p.shares,
        status="no_quote",
        price=None,
        prev_close=None,
        change=None,
        change_pct=None,
        value_usd=None,
        value_thb=None,
        weight=None,
        as_of_utc=None,
    )


def build_quotes_view(
    positions: Sequence[Position],
    snapshots: Mapping[str, PriceSnapshot],
    usd_thb: Decimal | None,
) -> QuotesView:
    held = [p for p in positions if p.shares > 0]
    values = {p.ticker: p.shares * snapshots[p.ticker].price for p in held if p.ticker in snapshots}
    current_weights = weights(values)

    rows: list[HoldingQuote] = []
    for p in held:
        snap = snapshots.get(p.ticker)
        if snap is None:
            rows.append(_no_quote(p))
            continue
        value = values[p.ticker]
        rows.append(
            HoldingQuote(
                ticker=p.ticker,
                shares=p.shares,
                status="ok",
                price=snap.price,
                prev_close=snap.prev_close,
                change=snap.price - snap.prev_close,
                change_pct=pct_change(snap.price, snap.prev_close) if snap.prev_close > 0 else None,
                value_usd=value,
                value_thb=value * usd_thb if usd_thb is not None else None,
                weight=current_weights[p.ticker],
                as_of_utc=snap.as_of_utc,
            )
        )
    rows.sort(key=lambda r: (r.status != "ok", -(r.weight or 0), r.ticker))

    portfolio = None
    if usd_thb is not None:
        portfolio = portfolio_change(
            [
                HoldingDay(
                    ticker=p.ticker,
                    shares=p.shares,
                    prev_close=snapshots[p.ticker].prev_close if p.ticker in snapshots else None,
                    close=snapshots[p.ticker].price if p.ticker in snapshots else None,
                )
                for p in held
            ],
            usd_thb,
        )
    times = [s.as_of_utc for t, s in snapshots.items() if t in values]
    return QuotesView(holdings=tuple(rows), portfolio=portfolio, as_of_utc=max(times, default=None))
