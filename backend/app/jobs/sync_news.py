"""Company news for every held ticker → `news` (shared by all users). Every 30 minutes.

Per ticker: yesterday and today (UTC dates; the first time 3 days back), de-duplicated against
what was stored for that ticker in the same period (same URL, or the same story under another
outlet's URL). No LLM here: summaries and importance are a separate step.
News older than 180 days is deleted.

    uv run python -m app.jobs.sync_news
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis

from app.config import get_settings
from app.domain.news import dedupe
from app.jobs.lock import job_lock
from app.jobs.runtime import open_runtime
from app.logs import configure_logging
from app.providers.base import (
    NewsProvider,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.store import news as news_store
from app.store.db import SessionFactory
from app.store.holdings import distinct_tickers

JOB = "sync_news"
PROVIDER = "finnhub"
LOCK_TTL_S = 10 * 60
FIRST_RUN_DAYS = 3
RETENTION = timedelta(days=180)

log = structlog.get_logger()


@dataclass
class NewsSyncResult:
    fetched: dict[str, int] = field(default_factory=dict)
    inserted: dict[str, int] = field(default_factory=dict)  # new, after de-duplication
    failed: dict[str, str] = field(default_factory=dict)
    pruned: int = 0
    skipped: str | None = None


async def run(
    session_factory: SessionFactory,
    redis: Redis,
    provider: NewsProvider,
    *,
    now: datetime | None = None,
) -> NewsSyncResult:
    now = now or datetime.now(UTC)
    today = now.astimezone(UTC).date()

    async with job_lock(redis, JOB, LOCK_TTL_S) as acquired:
        if not acquired:
            log.info("job.skipped", job=JOB, reason="already running")
            return NewsSyncResult(skipped="already running")

        result = NewsSyncResult()
        async with session_factory() as session:
            for ticker in await distinct_tickers(session):
                first_time = await news_store.latest_published(session, ticker) is None
                start = today - timedelta(days=FIRST_RUN_DAYS if first_time else 1)
                try:
                    items = await provider.get_news(ticker, start, today)
                except ProviderRateLimitedError as exc:
                    result.failed[ticker] = str(exc)
                    log.warning("news.rate_limited", job=JOB, ticker=ticker, error=str(exc))
                    break
                except (ProviderResponseError, ProviderUnavailableError) as exc:
                    result.failed[ticker] = str(exc)
                    log.warning("news.failed", job=JOB, ticker=ticker, error=str(exc))
                    continue

                since = datetime.combine(start - timedelta(days=1), datetime.min.time(), UTC)
                keys, urls = await news_store.known_since(session, ticker, since)
                fresh = dedupe(sorted(items, key=lambda n: n.published_at), keys, urls)
                result.fetched[ticker] = len(items)
                result.inserted[ticker] = await news_store.insert_news(session, fresh, PROVIDER)
                await session.commit()

            result.pruned = await news_store.prune_news(session, now - RETENTION)
            await session.commit()

        log.info(
            "job.done",
            job=JOB,
            fetched=sum(result.fetched.values()),
            inserted=sum(result.inserted.values()),
            failed=len(result.failed),
            pruned=result.pruned,
        )
        return result


async def _main() -> None:
    configure_logging(get_settings().log_level)
    async with open_runtime() as rt:
        await run(rt.session_factory, rt.redis, rt.finnhub_news())


if __name__ == "__main__":
    asyncio.run(_main())
