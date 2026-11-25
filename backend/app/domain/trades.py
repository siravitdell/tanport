"""Positions from a trade log, average-cost method, in USD and in THB.

Replay in date order (same day: buys before sells, then entry order):
- buy:  shares += n; cost += n × price + fee (USD), and that × the trade's USD/THB (THB)
- sell: n ≤ shares held, else OversellError. The sold fraction of the cost leaves the position
        (average cost per share is unchanged); realized P/L = proceeds − fee − that cost.
        THB uses the sell's rate for the proceeds and the THB cost basis carried from the buys.

Unrealized P/L in THB splits into the stock's move and the currency's move:
  price part = (value USD − cost USD) × today's rate
  FX part    = cost USD × today's rate − cost THB
which add up to value THB − cost THB.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.domain.errors import DomainError
from app.domain.portfolio import Position

HUNDRED = Decimal(100)
ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class TradeFact:
    ticker: str
    side: str  # "buy" | "sell"
    trade_date: date
    shares: Decimal
    price_usd: Decimal
    fee_usd: Decimal
    usd_thb: Decimal
    id: int | None = None  # None = not saved yet (sorts after saved trades of the same day)

    @property
    def gross_usd(self) -> Decimal:
        return self.shares * self.price_usd

    @property
    def amount_usd(self) -> Decimal:
        """Cash out for a buy (price + fee), cash in for a sell (price − fee)."""
        return (
            self.gross_usd + self.fee_usd if self.side == "buy" else self.gross_usd - self.fee_usd
        )


class OversellError(DomainError):
    def __init__(self, trade: TradeFact, held: Decimal) -> None:
        super().__init__(
            f"cannot sell {trade.shares} {trade.ticker} on {trade.trade_date}: "
            f"only {held} held then"
        )
        self.trade = trade
        self.held = held


@dataclass(slots=True)
class Book:
    ticker: str
    shares: Decimal = ZERO
    cost_usd: Decimal = ZERO
    cost_thb: Decimal = ZERO
    realized_usd: Decimal = ZERO
    realized_thb: Decimal = ZERO
    trades: int = 0

    @property
    def avg_cost_usd(self) -> Decimal | None:
        return self.cost_usd / self.shares if self.shares > 0 else None

    @property
    def avg_cost_thb(self) -> Decimal | None:
        return self.cost_thb / self.shares if self.shares > 0 else None


def _order(t: TradeFact) -> tuple[date, int, float]:
    return (t.trade_date, 0 if t.side == "buy" else 1, t.id if t.id is not None else float("inf"))


def replay(trades: Iterable[TradeFact]) -> dict[str, Book]:
    """One Book per ticker ever traded (closed positions keep their realized P/L)."""
    books: dict[str, Book] = {}
    for t in sorted(trades, key=_order):
        book = books.setdefault(t.ticker, Book(t.ticker))
        book.trades += 1
        if t.side == "buy":
            book.shares += t.shares
            book.cost_usd += t.amount_usd
            book.cost_thb += t.amount_usd * t.usd_thb
            continue
        if t.side != "sell":
            raise ValueError(f"unknown side {t.side!r}")
        if t.shares > book.shares:
            raise OversellError(t, book.shares)
        if t.shares == book.shares:  # closing: the whole remaining cost, no division dust
            basis_usd, basis_thb = book.cost_usd, book.cost_thb
        else:  # multiply before dividing: 30 × 1 / 3 is exactly 10
            basis_usd = book.cost_usd * t.shares / book.shares
            basis_thb = book.cost_thb * t.shares / book.shares
        book.realized_usd += t.amount_usd - basis_usd
        book.realized_thb += t.amount_usd * t.usd_thb - basis_thb
        book.shares -= t.shares
        if book.shares == 0:  # no rounding dust left on a closed position
            book.cost_usd = ZERO
            book.cost_thb = ZERO
        else:
            book.cost_usd -= basis_usd
            book.cost_thb -= basis_thb
    return books


# --- shares held on a date ---


class ShareLedger:
    """Shares of each ticker held at the end of each day, from a trade log.

    A day's buys and sales all count by the end of that day. To receive a dividend the shares
    must be held before the ex-date, i.e. at the end of the previous day: `held_before`.
    """

    def __init__(self, trades: Iterable[TradeFact]) -> None:
        self._steps: dict[str, tuple[list[date], list[Decimal]]] = {}
        held: dict[str, Decimal] = {}
        for t in sorted(trades, key=_order):
            now = held.get(t.ticker, ZERO) + (t.shares if t.side == "buy" else -t.shares)
            if now < 0:
                raise OversellError(t, held.get(t.ticker, ZERO))
            held[t.ticker] = now
            days, shares = self._steps.setdefault(t.ticker, ([], []))
            if days and days[-1] == t.trade_date:
                shares[-1] = now  # end of that day
            else:
                days.append(t.trade_date)
                shares.append(now)

    @property
    def tickers(self) -> set[str]:
        """Every ticker ever traded."""
        return set(self._steps)

    def shares_on(self, ticker: str, day: date) -> Decimal:
        steps = self._steps.get(ticker)
        if steps is None:
            return ZERO
        days, shares = steps
        i = bisect_right(days, day)
        return shares[i - 1] if i else ZERO

    def held_before(self, ticker: str, day: date) -> Decimal:
        return self.shares_on(ticker, day - timedelta(days=1))

    def positions_on(self, day: date) -> list[Position]:
        return [Position(t, s) for t in sorted(self._steps) if (s := self.shares_on(t, day)) > 0]

    def held_between(self, ticker: str, start: date, end: date) -> bool:
        """Any shares at the end of some day in [start, end]."""
        if self.shares_on(ticker, start) > 0:
            return True
        days, shares = self._steps.get(ticker, ([], []))
        return any(start <= d <= end and s > 0 for d, s in zip(days, shares, strict=True))


# --- portfolio view ---


@dataclass(frozen=True, slots=True)
class PositionView:
    ticker: str
    shares: Decimal
    avg_cost_usd: Decimal
    avg_cost_thb: Decimal
    cost_usd: Decimal
    cost_thb: Decimal
    price_usd: Decimal | None  # None: no price known yet
    value_usd: Decimal | None
    value_thb: Decimal | None
    unrealized_thb: Decimal | None
    unrealized_pct: Decimal | None  # of the THB cost
    price_pl_thb: Decimal | None
    fx_pl_thb: Decimal | None
    weight_pct: Decimal | None  # of the priced portfolio value
    trades: int


@dataclass(frozen=True, slots=True)
class PortfolioTotals:
    value_usd: Decimal
    value_thb: Decimal
    cost_usd: Decimal  # every open position
    cost_thb: Decimal
    unrealized_thb: Decimal  # priced positions only
    unrealized_pct: Decimal | None
    price_pl_thb: Decimal
    fx_pl_thb: Decimal
    realized_thb: Decimal  # including closed positions
    realized_usd: Decimal
    trades: int
    unpriced: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioView:
    positions: list[PositionView] = field(default_factory=list)
    totals: PortfolioTotals | None = None


def portfolio_view(
    books: Mapping[str, Book], prices: Mapping[str, Decimal], usd_thb: Decimal
) -> PortfolioView:
    open_books = [b for b in books.values() if b.shares > 0]
    priced_value = sum(
        (b.shares * prices[b.ticker] for b in open_books if b.ticker in prices), ZERO
    )

    rows: list[PositionView] = []
    for b in open_books:
        price = prices.get(b.ticker)
        value_usd = b.shares * price if price is not None else None
        value_thb = value_usd * usd_thb if value_usd is not None else None
        unrealized = value_thb - b.cost_thb if value_thb is not None else None
        rows.append(
            PositionView(
                ticker=b.ticker,
                shares=b.shares,
                avg_cost_usd=b.cost_usd / b.shares,
                avg_cost_thb=b.cost_thb / b.shares,
                cost_usd=b.cost_usd,
                cost_thb=b.cost_thb,
                price_usd=price,
                value_usd=value_usd,
                value_thb=value_thb,
                unrealized_thb=unrealized,
                unrealized_pct=unrealized / b.cost_thb * HUNDRED
                if unrealized is not None and b.cost_thb > 0
                else None,
                price_pl_thb=(value_usd - b.cost_usd) * usd_thb if value_usd is not None else None,
                fx_pl_thb=b.cost_usd * usd_thb - b.cost_thb if value_usd is not None else None,
                weight_pct=value_usd / priced_value * HUNDRED
                if value_usd is not None and priced_value > 0
                else None,
                trades=b.trades,
            )
        )
    rows.sort(key=lambda r: (r.value_usd is None, -(r.value_usd or ZERO), r.ticker))

    if not books:
        return PortfolioView()
    priced = [r for r in rows if r.value_usd is not None]
    priced_cost_thb = sum((r.cost_thb for r in priced), ZERO)
    unrealized_total = sum((r.unrealized_thb or ZERO for r in priced), ZERO)
    totals = PortfolioTotals(
        value_usd=priced_value,
        value_thb=priced_value * usd_thb,
        cost_usd=sum((r.cost_usd for r in rows), ZERO),
        cost_thb=sum((r.cost_thb for r in rows), ZERO),
        unrealized_thb=unrealized_total,
        unrealized_pct=unrealized_total / priced_cost_thb * HUNDRED
        if priced_cost_thb > 0
        else None,
        price_pl_thb=sum((r.price_pl_thb or ZERO for r in priced), ZERO),
        fx_pl_thb=sum((r.fx_pl_thb or ZERO for r in priced), ZERO),
        realized_thb=sum((b.realized_thb for b in books.values()), ZERO),
        realized_usd=sum((b.realized_usd for b in books.values()), ZERO),
        trades=sum(b.trades for b in books.values()),
        unpriced=tuple(r.ticker for r in rows if r.value_usd is None),
    )
    return PortfolioView(positions=rows, totals=totals)
