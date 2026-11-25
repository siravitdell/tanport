"""Dividend income for one user and one year (the income page and the calendar's card).

Per payment: net THB = shares × dps × (1 − withholding) × USD/THB on the pay date
(fallback: latest earlier rate — for future pay dates that is today's rate).

"received" = declared and paid on/before today; everything else is "upcoming"
(declared but not paid yet, or estimated).

Shares per payment: those held at the end of the day before the ex-date (from the trade log,
`held_before`). A payment whose ex-date is still ahead counts the shares held now. Positions
sold during the year keep the dividends they earned while held. Yield on cost uses the current
positions only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from app.domain.fx import FxChoice
from app.domain.tax import DividendAmount, dividend_amount

HUNDRED = Decimal(100)
ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class HoldingCost:
    ticker: str
    shares: Decimal
    avg_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class DividendPayment:
    ticker: str
    ex_date: date | None
    pay_date: date
    dps: Decimal
    is_estimate: bool


@dataclass(frozen=True, slots=True)
class PaymentLine:
    ticker: str
    ex_date: date | None
    pay_date: date
    dps: Decimal
    shares: Decimal
    is_estimate: bool
    status: Literal["received", "upcoming"]
    fx: FxChoice | None
    amount: DividendAmount | None  # None when no FX rate is available


@dataclass(frozen=True, slots=True)
class MonthIncome:
    month: int  # 1..12
    received_thb: Decimal
    upcoming_thb: Decimal
    lines: tuple[PaymentLine, ...]


@dataclass(frozen=True, slots=True)
class HoldingIncome:
    ticker: str
    pays_dividend: bool  # any payment in the year
    pay_months: tuple[int, ...]
    net_usd: Decimal
    net_thb: Decimal
    yield_on_cost_pct: Decimal | None  # net USD ÷ cost USD; None when cost unknown


@dataclass(frozen=True, slots=True)
class IncomeYear:
    year: int
    months: tuple[MonthIncome, ...]  # always 12
    holdings: tuple[HoldingIncome, ...]  # by net THB desc, non-payers last
    gross_thb: Decimal
    tax_thb: Decimal
    net_thb: Decimal
    received_thb: Decimal
    upcoming_thb: Decimal
    monthly_avg_thb: Decimal
    yield_on_cost_pct: Decimal | None
    missing_fx: tuple[date, ...]  # pay dates that couldn't be converted


def build_income(
    year: int,
    *,
    today: date,
    holdings: Sequence[HoldingCost],
    payments: Sequence[DividendPayment],
    fx: Mapping[date, FxChoice],
    withholding_rate: Decimal,
    held_before: Callable[[str, date], Decimal] | None = None,
) -> IncomeYear:
    """`holdings` = current positions (cost for yield on cost). `held_before(ticker, d)` = shares
    held at the end of the day before d; None = assume the current shares were always held."""
    held = {h.ticker: h for h in holdings if h.shares > 0}

    def entitled(p: DividendPayment) -> Decimal:
        current = held[p.ticker].shares if p.ticker in held else ZERO
        ex = p.ex_date or p.pay_date
        if held_before is None or ex > today:
            return current  # not ex yet: whoever holds it now gets it
        return held_before(p.ticker, ex)

    lines: list[PaymentLine] = []
    for p in sorted(payments, key=lambda p: (p.pay_date, p.ticker)):
        if p.pay_date.year != year:
            continue
        shares = entitled(p)
        if shares <= 0:
            continue
        rate = fx.get(p.pay_date)
        amount = (
            dividend_amount(shares, p.dps, withholding_rate, rate.rate)
            if rate is not None
            else None
        )
        received = not p.is_estimate and p.pay_date <= today
        lines.append(
            PaymentLine(
                ticker=p.ticker,
                ex_date=p.ex_date,
                pay_date=p.pay_date,
                dps=p.dps,
                shares=shares,
                is_estimate=p.is_estimate,
                status="received" if received else "upcoming",
                fx=rate,
                amount=amount,
            )
        )

    def net(ls: Sequence[PaymentLine], status: str | None = None) -> Decimal:
        return sum(
            (
                ln.amount.net_thb
                for ln in ls
                if ln.amount and (status is None or ln.status == status)
            ),
            ZERO,
        )

    months = tuple(
        MonthIncome(
            month=m,
            received_thb=net([ln for ln in lines if ln.pay_date.month == m], "received"),
            upcoming_thb=net([ln for ln in lines if ln.pay_date.month == m], "upcoming"),
            lines=tuple(ln for ln in lines if ln.pay_date.month == m),
        )
        for m in range(1, 13)
    )

    per_holding: list[HoldingIncome] = []
    # held now, plus anything sold that paid while it was held
    for ticker in sorted(held.keys() | {ln.ticker for ln in lines}):
        h = held.get(ticker)
        mine = [ln for ln in lines if ln.ticker == ticker]
        net_usd = sum((ln.amount.net_usd for ln in mine if ln.amount), ZERO)
        cost = h.shares * h.avg_cost_usd if h else ZERO
        per_holding.append(
            HoldingIncome(
                ticker=ticker,
                pays_dividend=bool(mine),
                pay_months=tuple(sorted({ln.pay_date.month for ln in mine})),
                net_usd=net_usd,
                net_thb=net(mine),
                yield_on_cost_pct=net_usd / cost * HUNDRED if cost > 0 and mine else None,
            )
        )
    per_holding.sort(key=lambda x: (not x.pays_dividend, -x.net_thb, x.ticker))

    priced = [ln for ln in lines if ln.amount]
    # yield on what is held now: dividends of positions since sold are not on that cost
    total_net_usd = sum(
        (ln.amount.net_usd for ln in priced if ln.amount and ln.ticker in held), ZERO
    )
    total_cost = sum((h.shares * h.avg_cost_usd for h in held.values()), ZERO)
    net_thb = net(lines)
    return IncomeYear(
        year=year,
        months=months,
        holdings=tuple(per_holding),
        gross_thb=sum((ln.amount.gross_thb for ln in priced if ln.amount), ZERO),
        tax_thb=sum((ln.amount.tax_thb for ln in priced if ln.amount), ZERO),
        net_thb=net_thb,
        received_thb=net(lines, "received"),
        upcoming_thb=net(lines, "upcoming"),
        monthly_avg_thb=net_thb / 12,
        yield_on_cost_pct=total_net_usd / total_cost * HUNDRED if total_cost > 0 else None,
        missing_fx=tuple(sorted({ln.pay_date for ln in lines if ln.amount is None})),
    )
