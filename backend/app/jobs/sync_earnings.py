"""Earnings dates for every held ticker → `earnings` events (shared by all users).

One Finnhub call per ticker (the whole-market list is truncated). Each run re-derives a ticker's
events from 30 days back (to pick up the reported EPS) to 90 days ahead, so a moved date
replaces the old one instead of leaving it behind. ETFs simply have none.

    uv run python -m app.jobs.sync_earnings
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis

from app.config import get_settings
from app.domain.earnings import EARNINGS_SOURCE, earnings_event
from app.domain.market import NEW_YORK
from app.jobs.lock import job_lock
from app.jobs.runtime import open_runtime
from app.logs import configure_logging
from app.providers.base import (
    EarningsProvider,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.store.db import SessionFactory
from app.store.events import EventIn, delete_events, upsert_events
from app.store.holdings import distinct_tickers
from app.store.models import EventType

JOB = "sync_earnings"
LOCK_TTL_S = 15 * 60
LOOK_BACK = timedelta(days=30)
LOOK_AHEAD = timedelta(days=90)

log = structlog.get_logger()


@dataclass
class EarningsSyncResult:
    saved: dict[str, int] = field(default_factory=dict)  # ticker -> events written
    failed: dict[str, str] = field(default_factory=dict)
    skipped: str | None = None


async def run(
    session_factory: SessionFactory,
    redis: Redis,
    provider: EarningsProvider,
    *,
    now: datetime | None = None,
) -> EarningsSyncResult:
    today = (now or datetime.now(UTC)).astimezone(NEW_YORK).date()
    start, end = today - LOOK_BACK, today + LOOK_AHEAD

    async with job_lock(redis, JOB, LOCK_TTL_S) as acquired:
        if not acquired:
            log.info("job.skipped", job=JOB, reason="already running")
            return EarningsSyncResult(skipped="already running")

        result = EarningsSyncResult()
        async with session_factory() as session:
            for ticker in await distinct_tickers(session):
                try:
                    rows = await provider.get_earnings(ticker, start, end)
                except ProviderRateLimitedError as exc:
                    result.failed[ticker] = str(exc)
                    log.warning("earnings.rate_limited", job=JOB, ticker=ticker, error=str(exc))
                    break  # the rest waits for the next run
                except (ProviderResponseError, ProviderUnavailableError) as exc:
                    result.failed[ticker] = str(exc)
                    log.warning("earnings.failed", job=JOB, ticker=ticker, error=str(exc))
                    continue

                events = [
                    EventIn(
                        type=EventType.EARNINGS,
                        ticker=ev.ticker,
                        event_date=ev.event_date,
                        event_time_utc=ev.event_time_utc,
                        source=EARNINGS_SOURCE,
                        payload=ev.payload,
                    )
                    for ev in map(earnings_event, rows)
                    if start <= ev.event_date <= end
                ]
                await delete_events(
                    session,
                    event_type=EventType.EARNINGS,
                    ticker=ticker,
                    start=start,
                    end=end,
                    source=EARNINGS_SOURCE,
                )
                await upsert_events(session, events)
                await session.commit()
                result.saved[ticker] = len(events)

        log.info("job.done", job=JOB, saved=sum(result.saved.values()), failed=len(result.failed))
        return result


async def _main() -> None:
    configure_logging(get_settings().log_level)
    async with open_runtime() as rt:
        await run(rt.session_factory, rt.redis, rt.finnhub_earnings())


if __name__ == "__main__":
    asyncio.run(_main())
