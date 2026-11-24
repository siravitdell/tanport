"""GET /api/income/monthly?year=YYYY — net THB dividends per month (received vs upcoming)."""

from __future__ import annotations

from contextlib import suppress
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser, NowDep, SessionDep
from app.api.types import DecimalStr
from app.domain.errors import NoFxRateError
from app.domain.fx import FxChoice
from app.domain.income import DividendPayment, HoldingCost, PaymentLine, build_income
from app.domain.market import BANGKOK
from app.services.fx import fx_rate_on
from app.store.events import dividend_pay_events
from app.store.holdings import list_holdings
from app.store.settings import get_user_settings

router = APIRouter(prefix="/api/income", tags=["income"])


class PaymentOut(BaseModel):
    ticker: str
    ex_date: date | None
    pay_date: date
    dps: DecimalStr
    shares: DecimalStr
    is_estimate: bool
    status: Literal["received", "upcoming"]
    gross_usd: DecimalStr | None
    tax_usd: DecimalStr | None
    net_usd: DecimalStr | None
    net_thb: DecimalStr | None
    usd_thb: DecimalStr | None
    fx_rate_date: date | None  # which day's rate was used
    fx_is_fallback: bool | None


class MonthOut(BaseModel):
    month: int
    received_thb: DecimalStr
    upcoming_thb: DecimalStr
    payments: list[PaymentOut]


class HoldingIncomeOut(BaseModel):
    ticker: str
    pays_dividend: bool
    pay_months: list[int]
    net_usd: DecimalStr
    net_thb: DecimalStr
    yield_on_cost_pct: DecimalStr | None


class TotalsOut(BaseModel):
    net_thb: DecimalStr
    gross_thb: DecimalStr
    tax_thb: DecimalStr
    received_thb: DecimalStr
    upcoming_thb: DecimalStr
    monthly_avg_thb: DecimalStr
    yield_on_cost_pct: DecimalStr | None


class IncomeOut(BaseModel):
    year: int
    withholding_rate: DecimalStr
    totals: TotalsOut
    months: list[MonthOut]
    holdings: list[HoldingIncomeOut]
    missing_fx: list[date]


def _payment(line: PaymentLine) -> PaymentOut:
    a, fx = line.amount, line.fx
    return PaymentOut(
        ticker=line.ticker,
        ex_date=line.ex_date,
        pay_date=line.pay_date,
        dps=line.dps,
        shares=line.shares,
        is_estimate=line.is_estimate,
        status=line.status,
        gross_usd=a.gross_usd if a else None,
        tax_usd=a.tax_usd if a else None,
        net_usd=a.net_usd if a else None,
        net_thb=a.net_thb if a else None,
        usd_thb=fx.rate if fx else None,
        fx_rate_date=fx.rate_date if fx else None,
        fx_is_fallback=fx.is_fallback if fx else None,
    )


@router.get("/monthly")
async def monthly_income(
    user: CurrentUser,
    session: SessionDep,
    now: NowDep,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> IncomeOut:
    today = now.astimezone(BANGKOK).date()
    year = year or today.year
    holdings = await list_holdings(session, user.id)
    costs = [HoldingCost(h.ticker, h.shares, h.avg_cost_usd) for h in holdings if h.shares > 0]
    settings = await get_user_settings(session, user.id)

    events = await dividend_pay_events(
        session, [c.ticker for c in costs], date(year, 1, 1), date(year, 12, 31)
    )
    payments = [
        DividendPayment(
            ticker=e.ticker or "",
            ex_date=date.fromisoformat(e.payload["ex_date"]) if e.payload.get("ex_date") else None,
            pay_date=e.event_date,
            dps=Decimal(e.payload["dps"]),
            is_estimate=e.is_estimate,
        )
        for e in events
    ]
    fx: dict[date, FxChoice] = {}
    for pay_date in {p.pay_date for p in payments}:
        # future pay dates resolve to the latest known rate; dates with no rate at all
        # are reported to the client in `missing_fx`
        with suppress(NoFxRateError):
            fx[pay_date] = await fx_rate_on(session, pay_date)

    income = build_income(
        year,
        today=today,
        holdings=costs,
        payments=payments,
        fx=fx,
        withholding_rate=settings.withholding_rate,
    )
    return IncomeOut(
        year=year,
        withholding_rate=settings.withholding_rate,
        totals=TotalsOut(
            net_thb=income.net_thb,
            gross_thb=income.gross_thb,
            tax_thb=income.tax_thb,
            received_thb=income.received_thb,
            upcoming_thb=income.upcoming_thb,
            monthly_avg_thb=income.monthly_avg_thb,
            yield_on_cost_pct=income.yield_on_cost_pct,
        ),
        months=[
            MonthOut(
                month=m.month,
                received_thb=m.received_thb,
                upcoming_thb=m.upcoming_thb,
                payments=[_payment(ln) for ln in m.lines],
            )
            for m in income.months
        ],
        holdings=[
            HoldingIncomeOut(
                ticker=h.ticker,
                pays_dividend=h.pays_dividend,
                pay_months=list(h.pay_months),
                net_usd=h.net_usd,
                net_thb=h.net_thb,
                yield_on_cost_pct=h.yield_on_cost_pct,
            )
            for h in income.holdings
        ],
        missing_fx=list(income.missing_fx),
    )
