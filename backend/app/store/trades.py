"""Trades repository (scoped to one user) and the holdings rebuild that follows every change."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.trades import Book, TradeFact, replay
from app.store.models import Holding, Trade, User

COST_QUANT = Decimal("0.000001")  # Numeric(20, 6)


def to_fact(t: Trade) -> TradeFact:
    return TradeFact(
        ticker=t.ticker,
        side=t.side,
        trade_date=t.trade_date,
        shares=t.shares,
        price_usd=t.price_usd,
        fee_usd=t.fee_usd,
        usd_thb=t.usd_thb,
        id=t.id,
    )


async def lock_user(session: AsyncSession, user_id: int) -> None:
    """Serialize trade writes of one user (validate-then-write must not interleave)."""
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def list_trades(session: AsyncSession, user_id: int) -> Sequence[Trade]:
    """Newest first."""
    result = await session.execute(
        select(Trade)
        .where(Trade.user_id == user_id)
        .order_by(Trade.trade_date.desc(), Trade.id.desc())
    )
    return result.scalars().all()


async def get_trade(session: AsyncSession, user_id: int, trade_id: int) -> Trade | None:
    result = await session.execute(
        select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def add_trades(
    session: AsyncSession, user_id: int, facts: Sequence[TradeFact]
) -> list[Trade]:
    rows = [
        Trade(
            user_id=user_id,
            ticker=f.ticker,
            side=f.side,
            trade_date=f.trade_date,
            shares=f.shares,
            price_usd=f.price_usd,
            fee_usd=f.fee_usd,
            usd_thb=f.usd_thb,
        )
        for f in facts
    ]
    session.add_all(rows)
    await session.flush()
    for r in rows:
        await session.refresh(r)
    return rows


async def delete_trade(session: AsyncSession, trade: Trade) -> None:
    await session.delete(trade)
    await session.flush()


async def books_for(session: AsyncSession, user_id: int) -> dict[str, Book]:
    return replay(to_fact(t) for t in await list_trades(session, user_id))


async def rebuild_holdings(session: AsyncSession, user_id: int) -> dict[str, Book]:
    """Make `holdings` match the trade log: open positions with their average cost, nothing else.

    Raises OversellError if the stored log is inconsistent (callers validate before writing).
    """
    books = await books_for(session, user_id)
    open_books = {t: b for t, b in books.items() if b.shares > 0}
    await session.execute(
        delete(Holding).where(Holding.user_id == user_id, Holding.ticker.not_in(open_books))
    )
    if open_books:
        stmt = insert(Holding).values(
            [
                {
                    "user_id": user_id,
                    "ticker": b.ticker,
                    "shares": b.shares,
                    "avg_cost_usd": (b.cost_usd / b.shares).quantize(COST_QUANT, ROUND_HALF_UP),
                }
                for b in open_books.values()
            ]
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Holding.user_id, Holding.ticker],
                set_={
                    "shares": stmt.excluded.shares,
                    "avg_cost_usd": stmt.excluded.avg_cost_usd,
                    "updated_at": func.now(),
                },
            )
        )
    return books
