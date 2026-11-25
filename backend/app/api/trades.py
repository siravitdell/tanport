"""Trade log: list, record a buy/sell, delete, CSV import. Every change rebuilds the holdings.

A sale may never exceed the shares held on its date, also after a delete or an import: such a
request is refused with 409 and nothing is written.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import CurrentUser, NowDep, SessionDep
from app.api.holdings import HoldingOut
from app.api.types import DecimalStr
from app.domain.errors import NoFxRateError
from app.domain.market import BANGKOK
from app.domain.trades import OversellError, TradeFact, replay
from app.domain.trades_csv import CsvImportError, RowError, normalize_ticker, parse_trades_csv
from app.services.fx import fx_rate_on
from app.store import holdings as holdings_repo
from app.store import trades as repo
from app.store.models import Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])

MAX_CSV_BYTES = 1_000_000
CSV_CONTENT_TYPES = ("text/csv", "text/plain", "application/csv", "application/vnd.ms-excel")

Shares = Annotated[DecimalStr, Field(gt=0, max_digits=20, decimal_places=8)]
Usd = Annotated[DecimalStr, Field(ge=0, max_digits=20, decimal_places=6)]
FxRate = Annotated[DecimalStr, Field(gt=0, max_digits=12, decimal_places=6)]


class TradeIn(BaseModel):
    side: Literal["buy", "sell"]
    ticker: str
    trade_date: date
    shares: Shares
    price_usd: Usd
    fee_usd: Usd = Decimal(0)
    usd_thb: FxRate | None = None  # None: the Bank of Thailand rate of trade_date

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return normalize_ticker(value)


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    side: str
    ticker: str
    trade_date: date
    shares: DecimalStr
    price_usd: DecimalStr
    fee_usd: DecimalStr
    usd_thb: DecimalStr
    cash_usd: DecimalStr  # money in (+, sell) or out (−, buy), fee included
    cash_thb: DecimalStr
    created_at: datetime


class ImportResult(BaseModel):
    imported: int
    holdings: list[HoldingOut]


def _out(t: Trade) -> TradeOut:
    amount = repo.to_fact(t).amount_usd
    cash = amount if t.side == "sell" else -amount
    return TradeOut(
        id=t.id,
        side=t.side,
        ticker=t.ticker,
        trade_date=t.trade_date,
        shares=t.shares,
        price_usd=t.price_usd,
        fee_usd=t.fee_usd,
        usd_thb=t.usd_thb,
        cash_usd=cash,
        cash_thb=cash * t.usd_thb,
        created_at=t.created_at,
    )


def _conflict(exc: OversellError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


async def _rate_for(session: SessionDep, day: date) -> Decimal:
    try:
        return (await fx_rate_on(session, day)).rate
    except NoFxRateError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"no USD/THB rate known for {day}: enter the rate (usd_thb)",
        ) from exc


@router.get("")
async def list_trades(user: CurrentUser, session: SessionDep) -> list[TradeOut]:
    """Newest first."""
    return [_out(t) for t in await repo.list_trades(session, user.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_trade(
    body: TradeIn, user: CurrentUser, session: SessionDep, now: NowDep
) -> TradeOut:
    if body.trade_date > now.astimezone(BANGKOK).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "trade_date is in the future")
    rate = body.usd_thb if body.usd_thb is not None else await _rate_for(session, body.trade_date)
    fact = TradeFact(
        body.ticker, body.side, body.trade_date, body.shares, body.price_usd, body.fee_usd, rate
    )

    await repo.lock_user(session, user.id)
    existing = [repo.to_fact(t) for t in await repo.list_trades(session, user.id)]
    try:
        replay([*existing, fact])
    except OversellError as exc:
        raise _conflict(exc) from exc
    [trade] = await repo.add_trades(session, user.id, [fact])
    await repo.rebuild_holdings(session, user.id)
    await session.commit()
    return _out(trade)


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trade(trade_id: int, user: CurrentUser, session: SessionDep) -> Response:
    await repo.lock_user(session, user.id)
    trade = await repo.get_trade(session, user.id, trade_id)
    if trade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"trade {trade_id} not found")
    remaining = [
        repo.to_fact(t) for t in await repo.list_trades(session, user.id) if t.id != trade_id
    ]
    try:
        replay(remaining)
    except OversellError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"deleting this trade would leave a later sale uncovered: {exc}",
        ) from exc
    await repo.delete_trade(session, trade)
    await repo.rebuild_holdings(session, user.id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_IMPORT_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "text/csv": {
                "schema": {"type": "string"},
                "example": "date,side,ticker,shares,price_usd,fee_usd,usd_thb\n"
                "2026-08-04,buy,VOO,1.5,585.40,0,33.20\n2026-11-09,sell,NVDA,2,153.87,0,\n",
            }
        },
    }
}


def _csv_error(errors: list[RowError], message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        {"message": message, "errors": [asdict(e) for e in errors]},
    )


@router.post("/import", openapi_extra=_IMPORT_OPENAPI)
async def import_csv(
    request: Request, user: CurrentUser, session: SessionDep, now: NowDep
) -> ImportResult:
    """Add trades from a CSV body (`Content-Type: text/csv`); see app.domain.trades_csv.

    Any invalid row rejects the whole file (422); a sale beyond what is held rejects it (409).
    """
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in CSV_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "send the file body as Content-Type: text/csv"
        )
    body = await request.body()
    if len(body) > MAX_CSV_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"CSV larger than {MAX_CSV_BYTES} bytes"
        )
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "CSV must be UTF-8 encoded"
        ) from exc

    try:
        rows = parse_trades_csv(text, now.astimezone(BANGKOK).date())
    except CsvImportError as exc:
        raise _csv_error(exc.errors, str(exc)) from exc

    rates: dict[date, Decimal] = {}
    missing: list[RowError] = []
    facts: list[TradeFact] = []
    for r in rows:
        rate = r.usd_thb
        if rate is None:
            if r.trade_date not in rates:
                try:
                    rates[r.trade_date] = (await fx_rate_on(session, r.trade_date)).rate
                except NoFxRateError:
                    missing.append(RowError(r.line, "usd_thb", f"no rate known for {r.trade_date}"))
                    continue
            rate = rates[r.trade_date]
        facts.append(
            TradeFact(r.ticker, r.side, r.trade_date, r.shares, r.price_usd, r.fee_usd, rate)
        )
    if missing:
        raise _csv_error(missing, f"{len(missing)} problem(s) in CSV")

    await repo.lock_user(session, user.id)
    existing = [repo.to_fact(t) for t in await repo.list_trades(session, user.id)]
    try:
        replay([*existing, *facts])
    except OversellError as exc:
        raise _conflict(exc) from exc
    await repo.add_trades(session, user.id, facts)
    await repo.rebuild_holdings(session, user.id)
    await session.commit()
    holdings = await holdings_repo.list_holdings(session, user.id)
    return ImportResult(
        imported=len(facts), holdings=[HoldingOut.model_validate(h) for h in holdings]
    )
