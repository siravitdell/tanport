"""Event persistence. Upserts are keyed on (type, ticker, event_date, source) so jobs can re-run."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
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
