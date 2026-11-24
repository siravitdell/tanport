"""Holdings CRUD + CSV import. Thin: parsing/validation lives in app.domain, SQL in app.store."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import CurrentUser, SessionDep
from app.api.types import DecimalStr
from app.domain.holdings_csv import CsvImportError, normalize_ticker, parse_holdings_csv
from app.store import holdings as repo

router = APIRouter(prefix="/api/holdings", tags=["holdings"])

MAX_CSV_BYTES = 1_000_000
CSV_CONTENT_TYPES = ("text/csv", "text/plain", "application/csv", "application/vnd.ms-excel")

Shares = Annotated[DecimalStr, Field(ge=0, max_digits=20, decimal_places=8)]
CostUsd = Annotated[DecimalStr, Field(ge=0, max_digits=20, decimal_places=6)]


class HoldingIn(BaseModel):
    ticker: str
    shares: Shares
    avg_cost_usd: CostUsd

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return normalize_ticker(value)


class HoldingUpdate(BaseModel):
    shares: Shares
    avg_cost_usd: CostUsd


class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    shares: DecimalStr
    avg_cost_usd: DecimalStr
    created_at: datetime
    updated_at: datetime


class ImportResult(BaseModel):
    created: list[str]
    updated: list[str]
    holdings: list[HoldingOut]


def _not_found(holding_id: int) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"holding {holding_id} not found")


@router.get("")
async def list_holdings(user: CurrentUser, session: SessionDep) -> list[HoldingOut]:
    return [HoldingOut.model_validate(h) for h in await repo.list_holdings(session, user.id)]


@router.get("/{holding_id}")
async def get_holding(holding_id: int, user: CurrentUser, session: SessionDep) -> HoldingOut:
    holding = await repo.get_holding(session, user.id, holding_id)
    if holding is None:
        raise _not_found(holding_id)
    return HoldingOut.model_validate(holding)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_holding(body: HoldingIn, user: CurrentUser, session: SessionDep) -> HoldingOut:
    try:
        holding = await repo.create_holding(
            session, user.id, body.ticker, body.shares, body.avg_cost_usd
        )
    except repo.DuplicateTickerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return HoldingOut.model_validate(holding)


@router.put("/{holding_id}")
async def update_holding(
    holding_id: int, body: HoldingUpdate, user: CurrentUser, session: SessionDep
) -> HoldingOut:
    holding = await repo.get_holding(session, user.id, holding_id)
    if holding is None:
        raise _not_found(holding_id)
    holding = await repo.update_holding(session, holding, body.shares, body.avg_cost_usd)
    await session.commit()
    return HoldingOut.model_validate(holding)


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holding(holding_id: int, user: CurrentUser, session: SessionDep) -> Response:
    if not await repo.delete_holding(session, user.id, holding_id):
        raise _not_found(holding_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_IMPORT_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "text/csv": {
                "schema": {"type": "string"},
                "example": "ticker,shares,avg_cost_usd\nVOO,12.5,480.20\nKO,15,61.00\n",
            }
        },
    }
}


@router.post("/import", openapi_extra=_IMPORT_OPENAPI)
async def import_csv(request: Request, user: CurrentUser, session: SessionDep) -> ImportResult:
    """Upsert holdings from a CSV body (`Content-Type: text/csv`).

    Header `ticker,shares,avg_cost_usd`. Existing tickers are updated, new ones created,
    holdings not in the file are left alone. Any invalid row rejects the whole file (422).
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
        rows = parse_holdings_csv(text)
    except CsvImportError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": str(exc), "errors": [asdict(e) for e in exc.errors]},
        ) from exc

    result = await repo.upsert_holdings(session, user.id, rows)
    await session.commit()
    holdings = [HoldingOut.model_validate(h) for h in await repo.list_holdings(session, user.id)]
    return ImportResult(created=result.created, updated=result.updated, holdings=holdings)
