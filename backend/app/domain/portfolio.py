"""Portfolio daily change.

change % = Σ (weight_i × change %_i), weights by market value at the previous close.
Holdings without both a previous close and a close for the day are left out of the
calculation and reported in `excluded` (never treated as 0 %).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from app.domain.money import pct_change


@dataclass(frozen=True, slots=True)
class HoldingDay:
    ticker: str
    shares: Decimal
    prev_close: Decimal | None
    close: Decimal | None


@dataclass(frozen=True, slots=True)
class HoldingChange:
    ticker: str
    weight: Decimal  # 0..1, by previous-close market value
    change_pct: Decimal
    value_usd: Decimal
    change_usd: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioChange:
    value_usd: Decimal
    prev_value_usd: Decimal
    change_pct: Decimal
    change_usd: Decimal
    change_thb: Decimal
    value_thb: Decimal
    usd_thb: Decimal
    holdings: tuple[HoldingChange, ...]  # sorted by |change %| desc
    excluded: tuple[str, ...]  # tickers with missing prices


def portfolio_change(days: Iterable[HoldingDay], usd_thb: Decimal) -> PortfolioChange | None:
    """Return None when nothing is priceable (e.g. empty portfolio, all shares 0)."""
    # (ticker, shares, prev_close, close) with both prices present
    priced: list[tuple[str, Decimal, Decimal, Decimal]] = []
    excluded: list[str] = []
    for day in days:
        if day.shares == 0:
            continue
        if day.prev_close is None or day.close is None or day.prev_close <= 0:
            excluded.append(day.ticker)
            continue
        priced.append((day.ticker, day.shares, day.prev_close, day.close))

    prev_total = sum((shares * prev for _, shares, prev, _ in priced), Decimal(0))
    if prev_total == 0:
        return None

    changes: list[HoldingChange] = []
    for ticker, shares, prev_close, close in priced:
        prev_value = shares * prev_close
        value = shares * close
        changes.append(
            HoldingChange(
                ticker=ticker,
                weight=prev_value / prev_total,
                change_pct=pct_change(close, prev_close),
                value_usd=value,
                change_usd=value - prev_value,
            )
        )

    value_total = sum((c.value_usd for c in changes), Decimal(0))
    change_pct = sum((c.weight * c.change_pct for c in changes), Decimal(0))
    change_usd = value_total - prev_total
    changes.sort(key=lambda c: (-abs(c.change_pct), c.ticker))
    return PortfolioChange(
        value_usd=value_total,
        prev_value_usd=prev_total,
        change_pct=change_pct,
        change_usd=change_usd,
        change_thb=change_usd * usd_thb,
        value_thb=value_total * usd_thb,
        usd_thb=usd_thb,
        holdings=tuple(changes),
        excluded=tuple(excluded),
    )


def weights(values: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """Current weights (0..1) from market values; all zero when the total is zero."""
    total = sum(values.values(), Decimal(0))
    if total == 0:
        return {t: Decimal(0) for t in values}
    return {t: v / total for t, v in values.items()}
