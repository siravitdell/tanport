"""portfolio_daily repository (per user)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.portfolio_history import PortfolioDay
from app.store.models import PortfolioDaily


async def replace_days(
    session: AsyncSession, user_id: int, start: date, end: date, days: Sequence[PortfolioDay]
) -> int:
    """Rewrite the user's rows in [start, end]; dates no longer computable are removed."""
    await session.execute(
        delete(PortfolioDaily).where(
            PortfolioDaily.user_id == user_id,
            PortfolioDaily.trade_date >= start,
            PortfolioDaily.trade_date <= end,
        )
    )
    if not days:
        return 0
    stmt = insert(PortfolioDaily).values(
        [
            {
                "user_id": user_id,
                "trade_date": d.trade_date,
                "value_usd": d.change.value_usd,
                "value_thb": d.change.value_thb,
                "change_pct": d.change.change_pct,
                "change_thb": d.change.change_thb,
                "usd_thb": d.change.usd_thb,
                "fx_rate_date": d.fx_rate_date,
                "computed_at": func.now(),
            }
            for d in days
        ]
    )
    await session.execute(stmt)
    return len(days)


async def days_between(
    session: AsyncSession, user_id: int, start: date, end: date
) -> dict[date, PortfolioDaily]:
    result = await session.execute(
        select(PortfolioDaily).where(
            PortfolioDaily.user_id == user_id,
            PortfolioDaily.trade_date >= start,
            PortfolioDaily.trade_date <= end,
        )
    )
    return {row.trade_date: row for row in result.scalars()}
