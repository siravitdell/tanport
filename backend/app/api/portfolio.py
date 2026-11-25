"""GET /api/portfolio — positions from the trade log valued at the latest price and today's rate.
GET /api/fx?date= — the USD/THB rate that applies to a date (pre-fills the trade form).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, NowDep, RedisDep, SessionDep
from app.api.types import DecimalStr
from app.domain.errors import NoFxRateError
from app.domain.market import BANGKOK
from app.domain.trades import portfolio_view
from app.services.fx import fx_rate_on
from app.store import trades as trades_repo
from app.store.prices import recent_prices
from app.store.quote_cache import load_quotes

router = APIRouter(tags=["portfolio"])


class FxOut(BaseModel):
    usd_thb: DecimalStr
    rate_date: date
    is_fallback: bool  # True: no rate for that date (weekend/holiday/not published yet)


class PositionOut(BaseModel):
    ticker: str
    shares: DecimalStr
    avg_cost_usd: DecimalStr
    avg_cost_thb: DecimalStr
    cost_usd: DecimalStr
    cost_thb: DecimalStr
    price_usd: DecimalStr | None
    price_source: str | None  # "quote" (live) | "close" (last daily close)
    value_usd: DecimalStr | None
    value_thb: DecimalStr | None
    unrealized_thb: DecimalStr | None
    unrealized_pct: DecimalStr | None
    price_pl_thb: DecimalStr | None
    fx_pl_thb: DecimalStr | None
    weight_pct: DecimalStr | None
    trades: int


class TotalsOut(BaseModel):
    value_usd: DecimalStr
    value_thb: DecimalStr
    cost_usd: DecimalStr
    cost_thb: DecimalStr
    unrealized_thb: DecimalStr
    unrealized_pct: DecimalStr | None
    price_pl_thb: DecimalStr
    fx_pl_thb: DecimalStr
    realized_thb: DecimalStr
    realized_usd: DecimalStr
    trades: int
    unpriced: list[str]


class PortfolioOut(BaseModel):
    fx: FxOut
    positions: list[PositionOut]
    totals: TotalsOut | None  # None: no trades yet


@router.get("/api/fx")
async def get_fx(
    session: SessionDep,
    _user: CurrentUser,
    now: NowDep,
    on: Annotated[date | None, Query(alias="date")] = None,
) -> FxOut:
    day = on or now.astimezone(BANGKOK).date()
    try:
        fx = await fx_rate_on(session, day)
    except NoFxRateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no USD/THB rate known for {day}") from exc
    return FxOut(usd_thb=fx.rate, rate_date=fx.rate_date, is_fallback=fx.is_fallback)


@router.get("/api/portfolio")
async def get_portfolio(
    user: CurrentUser, session: SessionDep, redis: RedisDep, now: NowDep
) -> PortfolioOut:
    try:
        fx = await fx_rate_on(session, now.astimezone(BANGKOK).date())
    except NoFxRateError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "no USD/THB rate yet: run sync_fx"
        ) from exc

    books = await trades_repo.books_for(session, user.id)
    open_tickers = [t for t, b in books.items() if b.shares > 0]
    prices: dict[str, Decimal] = {}
    source: dict[str, str] = {}
    for ticker, quote in (await load_quotes(redis, open_tickers)).items():
        prices[ticker], source[ticker] = quote.price, "quote"
    for ticker in open_tickers:
        if ticker not in prices and (last := await recent_prices(session, ticker, 1)):
            prices[ticker], source[ticker] = last[-1].close, "close"

    view = portfolio_view(books, prices, fx.rate)
    t = view.totals
    return PortfolioOut(
        fx=FxOut(usd_thb=fx.rate, rate_date=fx.rate_date, is_fallback=fx.is_fallback),
        positions=[
            PositionOut(
                ticker=p.ticker,
                shares=p.shares,
                avg_cost_usd=p.avg_cost_usd,
                avg_cost_thb=p.avg_cost_thb,
                cost_usd=p.cost_usd,
                cost_thb=p.cost_thb,
                price_usd=p.price_usd,
                price_source=source.get(p.ticker),
                value_usd=p.value_usd,
                value_thb=p.value_thb,
                unrealized_thb=p.unrealized_thb,
                unrealized_pct=p.unrealized_pct,
                price_pl_thb=p.price_pl_thb,
                fx_pl_thb=p.fx_pl_thb,
                weight_pct=p.weight_pct,
                trades=p.trades,
            )
            for p in view.positions
        ],
        totals=TotalsOut(
            value_usd=t.value_usd,
            value_thb=t.value_thb,
            cost_usd=t.cost_usd,
            cost_thb=t.cost_thb,
            unrealized_thb=t.unrealized_thb,
            unrealized_pct=t.unrealized_pct,
            price_pl_thb=t.price_pl_thb,
            fx_pl_thb=t.fx_pl_thb,
            realized_thb=t.realized_thb,
            realized_usd=t.realized_usd,
            trades=t.trades,
            unpriced=list(t.unpriced),
        )
        if t
        else None,
    )
