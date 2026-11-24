"""Holdings repository. Every query is scoped to one user."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Boolean, delete, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.holdings_csv import HoldingRow
from app.domain.portfolio import Position
from app.store.models import Holding


class DuplicateTickerError(Exception):
    def __init__(self, ticker: str) -> None:
        super().__init__(f"holding {ticker} already exists")
        self.ticker = ticker


@dataclass(frozen=True, slots=True)
class UpsertResult:
    created: list[str]
    updated: list[str]


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


async def create_holding(
    session: AsyncSession, user_id: int, ticker: str, shares: Decimal, avg_cost_usd: Decimal
) -> Holding:
    stmt = (
        insert(Holding)
        .values(user_id=user_id, ticker=ticker, shares=shares, avg_cost_usd=avg_cost_usd)
        .on_conflict_do_nothing(index_elements=[Holding.user_id, Holding.ticker])
        .returning(Holding.id)
    )
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    if new_id is None:
        raise DuplicateTickerError(ticker)
    holding = await session.get(Holding, new_id)
    if holding is None:  # pragma: no cover — inserted in this same transaction
        raise RuntimeError(f"holding {new_id} vanished after insert")
    return holding


async def update_holding(
    session: AsyncSession, holding: Holding, shares: Decimal, avg_cost_usd: Decimal
) -> Holding:
    holding.shares = shares
    holding.avg_cost_usd = avg_cost_usd
    await session.flush()
    await session.refresh(holding)
    return holding


async def delete_holding(session: AsyncSession, user_id: int, holding_id: int) -> bool:
    result = await session.execute(
        delete(Holding)
        .where(Holding.id == holding_id, Holding.user_id == user_id)
        .returning(Holding.id)
    )
    return result.scalar_one_or_none() is not None


async def upsert_holdings(
    session: AsyncSession, user_id: int, rows: Sequence[HoldingRow]
) -> UpsertResult:
    """Insert new tickers, update shares/cost of existing ones. Holdings not in `rows` are kept."""
    if not rows:
        return UpsertResult(created=[], updated=[])
    base = insert(Holding).values(
        [
            {
                "user_id": user_id,
                "ticker": r.ticker,
                "shares": r.shares,
                "avg_cost_usd": r.avg_cost_usd,
            }
            for r in rows
        ]
    )
    stmt = base.on_conflict_do_update(
        index_elements=[Holding.user_id, Holding.ticker],
        set_={
            "shares": base.excluded.shares,
            "avg_cost_usd": base.excluded.avg_cost_usd,
            "updated_at": func.now(),
        },
    ).returning(Holding.ticker, literal_column("(xmax = 0)", Boolean).label("inserted"))
    result = await session.execute(stmt)
    created: list[str] = []
    updated: list[str] = []
    for ticker, inserted in result.all():
        (created if inserted else updated).append(ticker)
    return UpsertResult(created=sorted(created), updated=sorted(updated))


async def distinct_tickers(session: AsyncSession) -> list[str]:
    """All tickers held by anyone (shares > 0) — what the sync jobs fetch, once each."""
    result = await session.execute(
        select(Holding.ticker).where(Holding.shares > 0).distinct().order_by(Holding.ticker)
    )
    return list(result.scalars())


async def positions_by_user(session: AsyncSession) -> dict[int, list[Position]]:
    """Every user's held positions (shares > 0)."""
    result = await session.execute(
        select(Holding.user_id, Holding.ticker, Holding.shares)
        .where(Holding.shares > 0)
        .order_by(Holding.user_id, Holding.ticker)
    )
    out: dict[int, list[Position]] = {}
    for user_id, ticker, shares in result.all():
        out.setdefault(user_id, []).append(Position(ticker=ticker, shares=shares))
    return out
