"""Scheduled jobs. Run exactly one worker process:  python -m app.worker

Times are Asia/Bangkok. Every job takes its own Redis lock, so an overlapping run is
skipped rather than doubled, and every job is safe to re-run.

| job                      | when                 | why                                         |
|--------------------------|----------------------|---------------------------------------------|
| sync_quotes              | every 5 min          | the job itself only works in US market hours |
| sync_daily_close         | 05:30                | after the US close                          |
| sync_daily_close_catchup | 08:30                | Tiingo can publish late in US winter        |
| sync_dividends           | 06:00                | Alpha Vantage, quota-aware                  |
| sync_earnings            | 06:00                | Finnhub, one call per ticker                |
| sync_fx                  | 18:30 + at startup   | BOT publishes the day's rate in the evening |
| cleanup_sessions         | 04:00                | drop expired login sessions                 |
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from redis.asyncio import Redis

from app.config import get_settings
from app.jobs import sync_daily_close, sync_dividends, sync_earnings, sync_fx, sync_quotes
from app.jobs.runtime import Runtime, open_runtime
from app.logs import configure_logging
from app.store.users import delete_expired_sessions

log = structlog.get_logger()

LAST_SUCCESS_KEY = "jobs:last_success"  # hash: job id -> ISO time
LAST_ERROR_KEY = "jobs:last_error"  # hash: job id -> "ISO time | error"

JobFn = Callable[[Runtime], Awaitable[Any]]


@dataclass(frozen=True)
class JobSpec:
    id: str
    trigger: BaseTrigger
    run: JobFn
    misfire_grace_s: int


async def _quotes(rt: Runtime) -> Any:
    return await sync_quotes.run(rt.session_factory, rt.redis, rt.finnhub_quotes())


async def _daily_close(rt: Runtime) -> Any:
    return await sync_daily_close.run(rt.session_factory, rt.redis, rt.tiingo_prices())


async def _dividends(rt: Runtime) -> Any:
    return await sync_dividends.run(rt.session_factory, rt.redis, rt.alphavantage_dividends())


async def _earnings(rt: Runtime) -> Any:
    return await sync_earnings.run(rt.session_factory, rt.redis, rt.finnhub_earnings())


async def _fx_scheduled(rt: Runtime) -> Any:
    # The schedule *is* the once-a-day rule, so bypass the 24 h marker: a marker set a few
    # seconds later yesterday must not make today's run skip.
    return await sync_fx.run(rt.session_factory, rt.redis, rt.bot_fx(), force=True)


async def _fx_startup(rt: Runtime) -> Any:
    return await sync_fx.run(rt.session_factory, rt.redis, rt.bot_fx())


async def _cleanup_sessions(rt: Runtime) -> int:
    async with rt.session_factory() as session:
        removed = await delete_expired_sessions(session)
        await session.commit()
    return removed


def job_specs(tz: str, now: datetime | None = None) -> list[JobSpec]:
    def cron(**fields: Any) -> CronTrigger:
        return CronTrigger(timezone=tz, **fields)

    return [
        JobSpec("sync_quotes", cron(minute="*/5"), _quotes, misfire_grace_s=120),
        JobSpec("sync_daily_close", cron(hour=5, minute=30), _daily_close, 3600),
        JobSpec("sync_daily_close_catchup", cron(hour=8, minute=30), _daily_close, 3600),
        JobSpec("sync_dividends", cron(hour=6, minute=0), _dividends, 3600),
        JobSpec("sync_earnings", cron(hour=6, minute=0), _earnings, 3600),
        JobSpec("sync_fx", cron(hour=18, minute=30), _fx_scheduled, 3600),
        JobSpec(
            "sync_fx_startup", DateTrigger(run_date=now or datetime.now(UTC)), _fx_startup, 3600
        ),
        JobSpec("cleanup_sessions", cron(hour=4, minute=0), _cleanup_sessions, 3600),
    ]


async def run_job(job_id: str, fn: Callable[[], Awaitable[Any]], redis: Redis) -> None:
    """Run one job; log and record the outcome. Never lets an error kill the scheduler."""
    started = datetime.now(UTC)
    structlog.contextvars.bind_contextvars(job=job_id)
    try:
        result = await fn()
    except Exception as exc:  # logged with traceback and recorded — not swallowed
        log.exception("job.error", error=f"{type(exc).__name__}: {exc}")
        await redis.hset(
            LAST_ERROR_KEY, job_id, f"{started.isoformat()} | {type(exc).__name__}: {exc}"
        )
    else:
        log.info("job.finished", result=repr(result)[:300])
        await redis.hset(LAST_SUCCESS_KEY, job_id, started.isoformat())
    finally:
        structlog.contextvars.unbind_contextvars("job")


def build_scheduler(rt: Runtime) -> AsyncIOScheduler:
    tz = rt.config.display_timezone
    scheduler = AsyncIOScheduler(timezone=tz)
    for spec in job_specs(tz):

        async def _run(spec: JobSpec = spec) -> None:
            await run_job(spec.id, lambda: spec.run(rt), rt.redis)

        scheduler.add_job(
            _run,
            trigger=spec.trigger,
            id=spec.id,
            name=spec.id,
            coalesce=True,  # after downtime, run once — not once per missed slot
            max_instances=1,
            misfire_grace_time=spec.misfire_grace_s,
            replace_existing=True,
        )
    return scheduler


async def main() -> None:
    configure_logging(get_settings().log_level)
    async with open_runtime() as rt:
        scheduler = build_scheduler(rt)
        scheduler.start()
        log.info("worker.started", jobs=[job.id for job in scheduler.get_jobs()])
        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)
            log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
