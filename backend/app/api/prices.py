"""GET /api/prices?ticker=VOO&days=14 — recent daily closes (sparklines)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.api.types import DecimalStr
from app.domain.holdings_csv import normalize_ticker
from app.store.prices import recent_prices

router = APIRouter(prefix="/api/prices", tags=["prices"])


class PricePoint(BaseModel):
    trade_date: date
    close: DecimalStr
    change_pct: DecimalStr | None


class PricesOut(BaseModel):
    ticker: str
    points: list[PricePoint]  # oldest first


@router.get("")
async def get_prices(
    _user: CurrentUser,
    session: SessionDep,
    ticker: Annotated[str, Query(min_length=1, max_length=16)],
    days: Annotated[int, Query(ge=1, le=365)] = 14,
) -> PricesOut:
    try:
        symbol = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    rows = await recent_prices(session, symbol, days)
    return PricesOut(
        ticker=symbol,
        points=[
            PricePoint(trade_date=r.trade_date, close=r.close, change_pct=r.change_pct)
            for r in rows
        ],
    )
