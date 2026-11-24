"""GET /api/quotes — today's prices strip and portfolio value for the current user."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, NowDep, RedisDep, SessionDep
from app.api.types import DecimalStr
from app.domain.errors import NoFxRateError
from app.domain.fx import FxChoice
from app.domain.market import BANGKOK, market_status
from app.domain.portfolio import Position
from app.domain.quotes import PriceSnapshot, build_quotes_view
from app.services.fx import fx_rate_on
from app.store.holdings import list_holdings
from app.store.quote_cache import load_quotes

router = APIRouter(prefix="/api/quotes", tags=["quotes"])

HUNDRED = Decimal(100)


class MarketOut(BaseModel):
    is_open: bool
    last_session_date: date  # US date of the session the prices belong to
    next_open_utc: datetime


class FxOut(BaseModel):
    usd_thb: DecimalStr
    rate_date: date
    is_fallback: bool


class HoldingQuoteOut(BaseModel):
    ticker: str
    shares: DecimalStr
    status: Literal["ok", "no_quote"]
    price: DecimalStr | None
    prev_close: DecimalStr | None
    change: DecimalStr | None
    change_pct: DecimalStr | None  # 1.5 means +1.5 %
    weight_pct: DecimalStr | None  # share of current portfolio value, in %
    value_usd: DecimalStr | None
    value_thb: DecimalStr | None
    as_of_utc: datetime | None


class PortfolioOut(BaseModel):
    value_usd: DecimalStr
    value_thb: DecimalStr
    change_pct: DecimalStr
    change_usd: DecimalStr
    change_thb: DecimalStr
    excluded: list[str]  # held tickers without a quote


class QuotesOut(BaseModel):
    market: MarketOut
    fx: FxOut | None
    portfolio: PortfolioOut | None
    holdings: list[HoldingQuoteOut]
    as_of_utc: datetime | None


@router.get("")
async def get_quotes(
    user: CurrentUser, session: SessionDep, redis: RedisDep, now: NowDep
) -> QuotesOut:
    holdings = await list_holdings(session, user.id)
    positions = [Position(h.ticker, h.shares) for h in holdings]
    cached = await load_quotes(redis, [p.ticker for p in positions if p.shares > 0])
    snapshots = {t: PriceSnapshot(q.price, q.prev_close, q.as_of_utc) for t, q in cached.items()}

    fx: FxChoice | None
    try:
        fx = await fx_rate_on(session, now.astimezone(BANGKOK).date())
    except NoFxRateError:
        fx = None

    view = build_quotes_view(positions, snapshots, fx.rate if fx else None)
    status = market_status(now)
    return QuotesOut(
        market=MarketOut(
            is_open=status.is_open,
            last_session_date=status.last_session_date,
            next_open_utc=status.next_open_utc,
        ),
        fx=FxOut(usd_thb=fx.rate, rate_date=fx.rate_date, is_fallback=fx.is_fallback)
        if fx
        else None,
        portfolio=PortfolioOut(
            value_usd=view.portfolio.value_usd,
            value_thb=view.portfolio.value_thb,
            change_pct=view.portfolio.change_pct,
            change_usd=view.portfolio.change_usd,
            change_thb=view.portfolio.change_thb,
            excluded=list(view.portfolio.excluded),
        )
        if view.portfolio
        else None,
        holdings=[
            HoldingQuoteOut(
                ticker=h.ticker,
                shares=h.shares,
                status=h.status,
                price=h.price,
                prev_close=h.prev_close,
                change=h.change,
                change_pct=h.change_pct,
                weight_pct=h.weight * HUNDRED if h.weight is not None else None,
                value_usd=h.value_usd,
                value_thb=h.value_thb,
                as_of_utc=h.as_of_utc,
            )
            for h in view.holdings
        ],
        as_of_utc=view.as_of_utc,
    )
