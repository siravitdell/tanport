"""fx_rates repository."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import FxRate
from app.store.models import FxRate as FxRateRow


async def upsert_rates(session: AsyncSession, rates: Sequence[FxRate], source: str) -> int:
    if not rates:
        return 0
    stmt = insert(FxRateRow).values(
        [{"date": r.rate_date, "pair": r.pair, "rate": r.rate, "source": source} for r in rates]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[FxRateRow.date, FxRateRow.pair],
        set_={"rate": stmt.excluded.rate, "source": stmt.excluded.source},
    )
    await session.execute(stmt)
    return len(rates)


async def latest_on_or_before(
    session: AsyncSession, pair: str, on: date
) -> tuple[date, Decimal] | None:
    row = (
        await session.execute(
            select(FxRateRow.date, FxRateRow.rate)
            .where(FxRateRow.pair == pair, FxRateRow.date <= on)
            .order_by(FxRateRow.date.desc())
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row is not None else None


async def rates_between(
    session: AsyncSession, pair: str, start: date, end: date
) -> dict[date, Decimal]:
    result = await session.execute(
        select(FxRateRow.date, FxRateRow.rate).where(
            FxRateRow.pair == pair, FxRateRow.date >= start, FxRateRow.date <= end
        )
    )
    return {d: r for d, r in result.all()}


async def coverage(session: AsyncSession, pair: str) -> tuple[date, date] | None:
    """(earliest, latest) stored date for the pair, or None when empty."""
    row = (
        await session.execute(
            select(func.min(FxRateRow.date), func.max(FxRateRow.date)).where(FxRateRow.pair == pair)
        )
    ).one()
    return (row[0], row[1]) if row[0] is not None else None
