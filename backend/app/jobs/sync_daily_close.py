"""Daily closes → prices, price_move events, portfolio_daily for every user.

Scheduled after the US close (05:30 Bangkok). Safe to re-run: everything is upserted or
re-derived for the affected range.

    uv run python -m app.jobs.sync_daily_close
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import structlog
from redis.asyncio import Redis

from app.config import get_settings
from app.domain.market import NEW_YORK
from app.jobs.lock import job_lock
from app.jobs.runtime import open_runtime
from app.logs import configure_logging
from app.providers.base import PriceHistoryProvider, ProviderResponseError, ProviderUnavailableError
from app.services.daily_close import DailyCloseResult, DailyCloseService
from app.store.db import SessionFactory
from app.store.holdings import distinct_tickers
from app.store.settings import min_big_move_threshold

JOB = "sync_daily_close"
LOCK_TTL_S = 30 * 60

log = structlog.get_logger()


def us_today() -> date:
    return datetime.now(UTC).astimezone(NEW_YORK).date()


async def run(
    session_factory: SessionFactory,
    redis: Redis,
    provider: PriceHistoryProvider,
    *,
    end: date | None = None,
) -> DailyCloseResult | None:
    """Returns None if another run holds the lock."""
    end = end or us_today()
    async with job_lock(redis, JOB, LOCK_TTL_S) as acquired:
        if not acquired:
            log.info("job.skipped", job=JOB, reason="already running")
            return None

        result = DailyCloseResult()
        async with session_factory() as session:
            service = DailyCloseService(session, provider)
            threshold = await min_big_move_threshold(session, get_settings().big_move_threshold_pct)
            for ticker in await distinct_tickers(session):
                try:
                    start, rows = await service.sync_ticker(ticker, end)
                except (ProviderResponseError, ProviderUnavailableError) as exc:
                    # raised before anything is written for this ticker: nothing to undo
                    result.failed[ticker] = str(exc)
                    log.warning("daily_close.failed", job=JOB, ticker=ticker, error=str(exc))
                    continue
                result.moves += await service.record_moves(ticker, start, end, rows, threshold)
                result.saved[ticker] = len(rows)
                await session.commit()

            result.portfolio_days = await service.recompute_portfolios(end)
            await session.commit()

        log.info(
            "job.done",
            job=JOB,
            saved=sum(result.saved.values()),
            failed=len(result.failed),
            moves=result.moves,
            portfolio_days=result.portfolio_days,
        )
        return result


async def _main() -> None:
    configure_logging(get_settings().log_level)
    async with open_runtime() as rt:
        await run(rt.session_factory, rt.redis, rt.tiingo_prices())


if __name__ == "__main__":
    asyncio.run(_main())
