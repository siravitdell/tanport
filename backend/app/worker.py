"""Scheduled-jobs entrypoint. Run exactly one: python -m app.worker

Jobs are registered in build_scheduler(); they are added step by step in Phase 1.
"""

from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.logs import configure_logging


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    return AsyncIOScheduler(timezone=settings.display_timezone)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger()
    scheduler = build_scheduler()
    scheduler.start()
    log.info("worker.started", jobs=[job.id for job in scheduler.get_jobs()])
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
