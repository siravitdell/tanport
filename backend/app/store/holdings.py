"""Holdings repository (reads). Every per-user query is scoped to one user.

Holdings are derived from the trade log: only app.store.trades.rebuild_holdings writes them.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import Holding


async def list_holdings(session: AsyncSession, user_id: int) -> Sequence[Holding]:
    result = await session.execute(
        select(Holding)
        .where(Holding.user_id == user_id)
        .order_by(Holding.ticker)
        # refresh rows already in the identity map (e.g. after a Core upsert)
        .execution_options(populate_existing=True)
    )
    return result.scalars().all()


async def get_holding(session: AsyncSession, user_id: int, holding_id: int) -> Holding | None:
    result = await session.execute(
        select(Holding).where(Holding.id == holding_id, Holding.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def distinct_tickers(session: AsyncSession) -> list[str]:
    """All tickers held by anyone (shares > 0) — what the sync jobs fetch, once each."""
    result = await session.execute(
        select(Holding.ticker).where(Holding.shares > 0).distinct().order_by(Holding.ticker)
    )
    return list(result.scalars())
