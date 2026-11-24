from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.events import EventIn, upsert_events
from app.store.models import Event, EventType


async def _count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Event))).scalar_one())


async def test_upsert_is_idempotent_and_updates_payload(session: AsyncSession) -> None:
    first = EventIn(
        type=EventType.EX_DIVIDEND,
        ticker="KO",
        event_date=date(2026, 12, 1),
        source="alphavantage",
        payload={"dps": "0.51"},
        is_estimate=True,
    )
    await upsert_events(session, [first])
    await upsert_events(
        session, [first.model_copy(update={"payload": {"dps": "0.53"}, "is_estimate": False})]
    )

    assert await _count(session) == 1
    row = (await session.execute(select(Event))).scalar_one()
    assert row.payload == {"dps": "0.53"}
    assert row.is_estimate is False


async def test_macro_events_with_null_ticker_collide(session: AsyncSession) -> None:
    fomc = EventIn(
        type=EventType.MACRO, ticker=None, event_date=date(2026, 12, 10), source="manual"
    )
    await upsert_events(session, [fomc])
    await upsert_events(session, [fomc])
    assert await _count(session) == 1


async def test_same_day_different_source_are_separate(session: AsyncSession) -> None:
    base = EventIn(
        type=EventType.DIVIDEND_PAY, ticker="SCHD", event_date=date(2026, 12, 14), source="a"
    )
    await upsert_events(session, [base, base.model_copy(update={"source": "estimate"})])
    assert await _count(session) == 2


async def test_unknown_event_type_rejected_by_db(session: AsyncSession) -> None:
    session.add(Event(type="bogus", ticker="KO", event_date=date(2026, 1, 1), source="x"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_empty_upsert_is_noop(session: AsyncSession) -> None:
    assert await upsert_events(session, []) == 0
