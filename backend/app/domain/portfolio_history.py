"""Portfolio value/change for past trading days (feeds portfolio_daily).

Uses each day's stored close and change %. The previous close is implied from them
(close / (1 + change/100)), which stays correct across splits because change % is
split-adjusted.

Positions are what the user held at the end of each day (from the trade log). A day's change
is that day's move of those shares: money moved in or out by trading does not count as gain.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.fx import FxChoice
from app.domain.portfolio import HoldingDay, PortfolioChange, Position, portfolio_change

HUNDRED = Decimal(100)


@dataclass(frozen=True, slots=True)
class DayPrice:
    close: Decimal
    change_pct: Decimal | None


@dataclass(frozen=True, slots=True)
class PortfolioDay:
    trade_date: date
    change: PortfolioChange
    fx_rate_date: date


def implied_prev_close(price: DayPrice) -> Decimal | None:
    if price.change_pct is None or price.change_pct <= -HUNDRED:
        return None
    return price.close / (1 + price.change_pct / HUNDRED)


def portfolio_days(
    positions: Callable[[date], Sequence[Position]],
    prices: Mapping[str, Mapping[date, DayPrice]],
    fx: Mapping[date, FxChoice],
    dates: Iterable[date],
) -> list[PortfolioDay]:
    """One entry per date that has an FX rate and at least one priced holding.

    `positions(d)` = shares held at the end of day d.
    """
    out: list[PortfolioDay] = []
    for d in sorted(set(dates)):
        rate = fx.get(d)
        held = [p for p in positions(d) if p.shares > 0]
        if rate is None or not held:
            continue
        days: list[HoldingDay] = []
        for p in held:
            price = prices.get(p.ticker, {}).get(d)
            days.append(
                HoldingDay(
                    ticker=p.ticker,
                    shares=p.shares,
                    prev_close=implied_prev_close(price) if price else None,
                    close=price.close if price else None,
                )
            )
        change = portfolio_change(days, rate.rate)
        if change is not None:
            out.append(PortfolioDay(trade_date=d, change=change, fx_rate_date=rate.rate_date))
    return out
