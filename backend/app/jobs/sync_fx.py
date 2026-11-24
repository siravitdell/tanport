"""Refresh USD/THB from the Bank of Thailand.

uv run python -m app.jobs.sync_fx                  # refresh unless done in the last 24 h
uv run python -m app.jobs.sync_fx --force          # refresh now
uv run python -m app.jobs.sync_fx --since 2025-01-01   # also backfill history
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

import structlog
from redis.asyncio import Redis

from app.config import get_settings
from app.jobs.lock import job_lock
from app.jobs.runtime import open_runtime
from app.logs import configure_logging
from app.providers.base import FXProvider
from app.services.fx import FxService
from app.store.db import SessionFactory

JOB = "sync_fx"
LOCK_TTL_S = 15 * 60

log = structlog.get_logger()


async def run(
    session_factory: SessionFactory,
    redis: Redis,
    provider: FXProvider,
    *,
    force: bool = False,
    since: date | None = None,
) -> int | None:
    """Returns rates written, or None if another run holds the lock."""
    async with job_lock(redis, JOB, LOCK_TTL_S) as acquired:
        if not acquired:
            log.info("job.skipped", job=JOB, reason="already running")
            return None
        async with session_factory() as session:
            service = FxService(session, redis, provider)
            written = await service.refresh(force=force)
            if since is not None:
                written += await service.backfill(since)
        log.info("job.done", job=JOB, rates=written)
        return written


async def _main(force: bool, since: date | None) -> None:
    configure_logging(get_settings().log_level)
    async with open_runtime() as rt:
        await run(rt.session_factory, rt.redis, rt.bot_fx(), force=force, since=since)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the 24 h cache")
    parser.add_argument("--since", type=date.fromisoformat, help="backfill from YYYY-MM-DD")
    args = parser.parse_args()
    asyncio.run(_main(args.force, args.since))
