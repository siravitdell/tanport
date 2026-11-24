"""prices repository (daily closes, shared by all users)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.portfolio_history import DayPrice
from app.domain.prices import PriceRow
from app.store.models import Price


async def upsert_prices(session: AsyncSession, rows: Sequence[PriceRow], source: str) -> int:
    if not rows:
        return 0
    base = insert(Price).values(
        [
            {
                "ticker": r.ticker,
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "change_pct": r.change_pct,
                "source": source,
            }
            for r in rows
        ]
    )
    stmt = base.on_conflict_do_update(
        index_elements=[Price.ticker, Price.trade_date],
        set_={
            col: base.excluded[col]
            for col in ("open", "high", "low", "close", "change_pct", "source")
        },
    )
    await session.execute(stmt)
    return len(rows)


async def last_trade_date(session: AsyncSession, ticker: str) -> date | None:
    result = await session.execute(select(func.max(Price.trade_date)).where(Price.ticker == ticker))
    return result.scalar_one_or_none()


async def close_before(session: AsyncSession, ticker: str, before: date) -> Decimal | None:
    result = await session.execute(
        select(Price.close)
        .where(Price.ticker == ticker, Price.trade_date < before)
        .order_by(Price.trade_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def day_prices(
    session: AsyncSession, tickers: Iterable[str], start: date, end: date
) -> dict[str, dict[date, DayPrice]]:
    tickers = list(tickers)
    out: dict[str, dict[date, DayPrice]] = {t: {} for t in tickers}
    if not tickers:
        return out
    result = await session.execute(
        select(Price.ticker, Price.trade_date, Price.close, Price.change_pct).where(
            Price.ticker.in_(tickers), Price.trade_date >= start, Price.trade_date <= end
        )
    )
    for ticker, trade_date, close, change_pct in result.all():
        out[ticker][trade_date] = DayPrice(close=close, change_pct=change_pct)
    return out


async def recent_prices(session: AsyncSession, ticker: str, limit: int) -> Sequence[Price]:
    """Last `limit` trading days, oldest first."""
    result = await session.execute(
        select(Price).where(Price.ticker == ticker).order_by(Price.trade_date.desc()).limit(limit)
    )
    return list(reversed(result.scalars().all()))
