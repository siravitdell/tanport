"""Per-user settings repository (row created at registration)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import UserSettings


async def get_user_settings(session: AsyncSession, user_id: int) -> UserSettings:
    row = await session.get(UserSettings, user_id)
    if row is None:
        # Every user gets a row in create_user(); recreate defaults if it was ever lost.
        row = UserSettings(user_id=user_id)
        session.add(row)
        await session.flush()
        await session.refresh(row)
    return row


async def update_user_settings(
    session: AsyncSession,
    user_id: int,
    *,
    withholding_rate: Decimal,
    big_move_threshold_pct: Decimal,
    dca_split: dict[str, str],
) -> UserSettings:
    row = await get_user_settings(session, user_id)
    row.withholding_rate = withholding_rate
    row.big_move_threshold_pct = big_move_threshold_pct
    row.dca_split = dca_split
    await session.flush()
    await session.refresh(row)
    return row
