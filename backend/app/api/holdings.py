"""Holdings (read-only). They are derived from the trade log: write through /api/trades."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser, SessionDep
from app.api.types import DecimalStr
from app.store import holdings as repo

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    shares: DecimalStr
    avg_cost_usd: DecimalStr
    created_at: datetime
    updated_at: datetime


@router.get("")
async def list_holdings(user: CurrentUser, session: SessionDep) -> list[HoldingOut]:
    return [HoldingOut.model_validate(h) for h in await repo.list_holdings(session, user.id)]


@router.get("/{holding_id}")
async def get_holding(holding_id: int, user: CurrentUser, session: SessionDep) -> HoldingOut:
    holding = await repo.get_holding(session, user.id, holding_id)
    if holding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"holding {holding_id} not found")
    return HoldingOut.model_validate(holding)
