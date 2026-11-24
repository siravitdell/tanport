"""Dividend income for one user and one year (the income page and the calendar's card).

Per payment: net THB = shares × dps × (1 − withholding) × USD/THB on the pay date
(fallback: latest earlier rate — for future pay dates that is today's rate).

"received" = declared and paid on/before today; everything else is "upcoming"
(declared but not paid yet, or estimated).

Limitation: uses current holdings for the whole year (no trade history yet), i.e. it
assumes today's shares were held before each ex-date.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
) -> IncomeYear:
    held = {h.ticker: h for h in holdings if h.shares > 0}
    lines: list[PaymentLine] = []
    for p in sorted(payments, key=lambda p: (p.pay_date, p.ticker)):
        h = held.get(p.ticker)
        if h is None or p.pay_date.year != year:
            continue
        rate = fx.get(p.pay_date)
        amount = (
            dividend_amount(h.shares, p.dps, withholding_rate, rate.rate)
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
                shares=h.shares,
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
    for ticker, h in held.items():
        mine = [ln for ln in lines if ln.ticker == ticker]
        net_usd = sum((ln.amount.net_usd for ln in mine if ln.amount), ZERO)
        cost = h.shares * h.avg_cost_usd
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
    total_net_usd = sum((ln.amount.net_usd for ln in priced if ln.amount), ZERO)
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
