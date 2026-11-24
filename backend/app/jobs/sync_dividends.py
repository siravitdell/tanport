"""Declared + estimated dividends → ex_dividend / dividend_pay events (shared by all users).

Alpha Vantage's free key allows 25 calls a day, shared by every user, so:
- tickers synced in the last 20 h are skipped (unless --force);
- the least recently synced tickers go first;
- when the quota runs out, the remaining tickers are deferred to the next run
  (logged, not an error).

    uv run python -m app.jobs.sync_dividends [--force]
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import structlog
from redis.asyncio import Redis

from app.config import get_settings
from app.domain.dividends import ESTIMATE_SOURCE, dividend_events
from app.domain.market import BANGKOK
from app.jobs.lock import job_lock
from app.jobs.runtime import open_runtime
from app.logs import configure_logging
from app.providers.base import (
    Dividend,
    DividendProvider,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.store.db import SessionFactory
from app.store.events import EventIn, replace_dividend_events
from app.store.holdings import distinct_tickers
from app.store.models import EventType

JOB = "sync_dividends"
LOCK_TTL_S = 30 * 60
SOURCE = "alphavantage"
LAST_SYNC_KEY = "dividends:last_sync"  # sorted set: ticker -> unix time of last success
MIN_INTERVAL = timedelta(hours=20)
MAX_BURST_WAIT_S = 10.0

log = structlog.get_logger()


@dataclass
class DividendSyncResult:
    saved: dict[str, int] = field(default_factory=dict)  # ticker -> events written
    failed: dict[str, str] = field(default_factory=dict)
    deferred: list[str] = field(default_factory=list)  # quota ran out
    recent: list[str] = field(default_factory=list)  # synced < 20 h ago
    skipped: str | None = None


async def _get_with_burst_retry(provider: DividendProvider, ticker: str) -> Sequence[Dividend]:
    """A short-lived (per-second) throttle is waited out once; a daily quota is not."""
    try:
        return await provider.get_dividends(ticker)
    except ProviderRateLimitedError as exc:
        if exc.retry_after_s is None or exc.retry_after_s > MAX_BURST_WAIT_S:
            raise
        await asyncio.sleep(exc.retry_after_s)
        return await provider.get_dividends(ticker)


def window(today: date) -> tuple[date, date]:
    """Last year (for comparisons) through the end of next year (calendar look-ahead)."""
    return date(today.year - 1, 1, 1), date(today.year + 1, 12, 31)


async def run(
    session_factory: SessionFactory,
    redis: Redis,
    provider: DividendProvider,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> DividendSyncResult:
    now = now or datetime.now(UTC)
    start, through = window(now.astimezone(BANGKOK).date())

    async with job_lock(redis, JOB, LOCK_TTL_S) as acquired:
        if not acquired:
            log.info("job.skipped", job=JOB, reason="already running")
            return DividendSyncResult(skipped="already running")

        result = DividendSyncResult()
        async with session_factory() as session:
            tickers = await distinct_tickers(session)
            last = {t: await redis.zscore(LAST_SYNC_KEY, t) or 0.0 for t in tickers}
            ordered = sorted(tickers, key=lambda t: (last[t], t))
            fresh_after = (now - MIN_INTERVAL).timestamp()

            for i, ticker in enumerate(ordered):
                if not force and last[ticker] > fresh_after:
                    result.recent.append(ticker)
                    continue
                try:
                    dividends = await _get_with_burst_retry(provider, ticker)
                except ProviderRateLimitedError as exc:
                    for t in ordered[i:]:
                        due = force or last[t] <= fresh_after
                        (result.deferred if due else result.recent).append(t)
                    log.warning(
                        "dividends.quota_exhausted",
                        job=JOB,
                        deferred=result.deferred,
                        error=str(exc),
                    )
                    break
                except (ProviderResponseError, ProviderUnavailableError) as exc:
                    result.failed[ticker] = str(exc)
                    log.warning("dividends.failed", job=JOB, ticker=ticker, error=str(exc))
                    continue

                events = [
                    EventIn(
                        type=EventType(e.type),
                        ticker=e.ticker,
                        event_date=e.event_date,
                        source=e.source,
                        payload=e.payload,
                        is_estimate=e.is_estimate,
                    )
                    for e in dividend_events(
                        ticker, dividends, window_start=start, through=through, source=SOURCE
                    )
                ]
                result.saved[ticker] = await replace_dividend_events(
                    session, ticker, [SOURCE, ESTIMATE_SOURCE], start, events
                )
                await session.commit()
                await redis.zadd(LAST_SYNC_KEY, {ticker: now.timestamp()})

        log.info(
            "job.done",
            job=JOB,
            saved=len(result.saved),
            failed=len(result.failed),
            deferred=len(result.deferred),
            recent=len(result.recent),
        )
        return result


async def _main(force: bool) -> None:
    configure_logging(get_settings().log_level)
    async with open_runtime() as rt:
        await run(rt.session_factory, rt.redis, rt.alphavantage_dividends(), force=force)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the 20 h per-ticker interval")
    asyncio.run(_main(parser.parse_args().force))
