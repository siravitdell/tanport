"""Latest quote per held ticker → Redis. Runs every 5 min; does nothing outside US market hours.

uv run python -m app.jobs.sync_quotes            # only inside the market window
uv run python -m app.jobs.sync_quotes --force    # any time
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis

from app.config import get_settings
from app.domain.market import in_quote_window
from app.jobs.lock import job_lock
from app.jobs.runtime import open_runtime
from app.logs import configure_logging
from app.providers.base import ProviderResponseError, ProviderUnavailableError, QuoteProvider
from app.store.db import SessionFactory
from app.store.holdings import distinct_tickers
from app.store.quote_cache import save_quote

JOB = "sync_quotes"
LOCK_TTL_S = 4 * 60  # shorter than the 5-min schedule

log = structlog.get_logger()


@dataclass
class QuoteSyncResult:
    saved: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: str | None = None


async def run(
    session_factory: SessionFactory,
    redis: Redis,
    provider: QuoteProvider,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> QuoteSyncResult:
    now = now or datetime.now(UTC)
    if not force and not in_quote_window(now):
        return QuoteSyncResult(skipped="market closed")

    async with job_lock(redis, JOB, LOCK_TTL_S) as acquired:
        if not acquired:
            log.info("job.skipped", job=JOB, reason="already running")
            return QuoteSyncResult(skipped="already running")

        async with session_factory() as session:
            tickers = await distinct_tickers(session)

        result = QuoteSyncResult()
        for ticker in tickers:
            # Per-ticker problems don't stop the others. Access-denied / rate-limited errors
            # affect every ticker, so they propagate and fail the run loudly.
            try:
                quote = await provider.get_quote(ticker)
            except (ProviderResponseError, ProviderUnavailableError) as exc:
                result.failed[ticker] = str(exc)
                log.warning("quote.failed", job=JOB, ticker=ticker, error=str(exc))
                continue
            await save_quote(redis, quote)
            result.saved.append(ticker)

        log.info("job.done", job=JOB, saved=len(result.saved), failed=len(result.failed))
        return result


async def _main(force: bool) -> None:
    configure_logging(get_settings().log_level)
    async with open_runtime() as rt:
        result = await run(rt.session_factory, rt.redis, rt.finnhub_quotes(), force=force)
        if result.skipped:
            log.info("job.skipped", job=JOB, reason=result.skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="run outside market hours too")
    asyncio.run(_main(parser.parse_args().force))
