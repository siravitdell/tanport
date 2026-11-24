"""Event persistence. Upserts are keyed on (type, ticker, event_date, source) so jobs can re-run."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import Event, EventType


class EventIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: EventType
    ticker: str | None
    event_date: date
    source: str
    event_time_utc: datetime | None = None
    payload: dict[str, Any] = {}
    is_estimate: bool = False


async def upsert_events(session: AsyncSession, events: Sequence[EventIn]) -> int:
    """Insert or update events; returns the number of rows written."""
    if not events:
        return 0
    rows = [e.model_dump(mode="python") for e in events]
    for row in rows:
        row["type"] = row["type"].value
    stmt = insert(Event).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_events_identity",
        set_={
            "event_time_utc": stmt.excluded.event_time_utc,
            "payload": stmt.excluded.payload,
            "is_estimate": stmt.excluded.is_estimate,
            "updated_at": func.now(),
        },
    )
    result = await session.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)


async def delete_events(
    session: AsyncSession,
    *,
    event_type: EventType,
    ticker: str,
    start: date,
    end: date,
    source: str,
) -> None:
    """Clear one ticker's events of a type in a date range before re-deriving them."""
    await session.execute(
        delete(Event).where(
            Event.type == event_type.value,
            Event.ticker == ticker,
            Event.event_date >= start,
            Event.event_date <= end,
            Event.source == source,
        )
    )


async def events_for(
    session: AsyncSession, tickers: Iterable[str], start: date, end: date
) -> Sequence[Event]:
    """Events for the given tickers plus market-wide ones (ticker NULL), by date."""
    tickers = list(tickers)
    result = await session.execute(
        select(Event)
        .where(
            Event.event_date >= start,
            Event.event_date <= end,
            or_(Event.ticker.in_(tickers), Event.ticker.is_(None)),
        )
        .order_by(Event.event_date, Event.type, Event.ticker)
    )
    return result.scalars().all()


DIVIDEND_TYPES = (EventType.EX_DIVIDEND.value, EventType.DIVIDEND_PAY.value)


async def replace_dividend_events(
    session: AsyncSession,
    ticker: str,
    sources: Sequence[str],
    window_start: date,
    events: Sequence[EventIn],
) -> int:
    """Re-derive a ticker's dividend events from `window_start` on (estimates get replaced)."""
    await session.execute(
        delete(Event).where(
            Event.type.in_(DIVIDEND_TYPES),
            Event.ticker == ticker,
            Event.source.in_(list(sources)),
            Event.event_date >= window_start,
        )
    )
    await upsert_events(session, events)
    return len(events)


async def dividend_pay_events(
    session: AsyncSession, tickers: Iterable[str], start: date, end: date
) -> Sequence[Event]:
    result = await session.execute(
        select(Event).where(
            Event.type == EventType.DIVIDEND_PAY.value,
            Event.ticker.in_(list(tickers)),
            Event.event_date >= start,
            Event.event_date <= end,
        )
    )
    return result.scalars().all()
