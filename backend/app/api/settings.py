"""Per-user settings: withholding rate, big-move threshold, DCA split."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser, SessionDep
from app.api.types import DecimalStr, decimal_to_str
from app.domain.dca import validate_dca_split
from app.store.models import UserSettings
from app.store.settings import get_user_settings, update_user_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsOut(BaseModel):
    withholding_rate: DecimalStr
    big_move_threshold_pct: DecimalStr
    dca_split: dict[str, DecimalStr]
    updated_at: datetime


class SettingsIn(BaseModel):
    # 0.15 with W-8BEN (US–Thailand treaty), 0.30 without
    withholding_rate: Annotated[DecimalStr, Field(ge=0, le=1)]
    big_move_threshold_pct: Annotated[DecimalStr, Field(gt=0, le=100)]
    dca_split: dict[str, DecimalStr]

    @field_validator("dca_split")
    @classmethod
    def _split(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        return validate_dca_split(value)


def _out(row: UserSettings) -> SettingsOut:
    return SettingsOut(
        withholding_rate=row.withholding_rate,
        big_move_threshold_pct=row.big_move_threshold_pct,
        dca_split={t: Decimal(p) for t, p in row.dca_split.items()},
        updated_at=row.updated_at,
    )


@router.get("")
async def get_settings(user: CurrentUser, session: SessionDep) -> SettingsOut:
    row = await get_user_settings(session, user.id)
    await session.commit()  # persists a recreated default row, if one was needed
    return _out(row)


@router.put("")
async def put_settings(body: SettingsIn, user: CurrentUser, session: SessionDep) -> SettingsOut:
    row = await update_user_settings(
        session,
        user.id,
        withholding_rate=body.withholding_rate,
        big_move_threshold_pct=body.big_move_threshold_pct,
        dca_split={t: decimal_to_str(p) for t, p in body.dca_split.items()},
    )
    await session.commit()
    return _out(row)
