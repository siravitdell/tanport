from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from redis.asyncio import Redis

from app.config import Settings
from app.jobs.runtime import Runtime
from app.worker import (
    LAST_ERROR_KEY,
    LAST_SUCCESS_KEY,
    build_scheduler,
    job_specs,
    run_job,
)

BKK = ZoneInfo("Asia/Bangkok")
# Wed 16 Dec 2026, 05:01 in Bangkok (a :00 or :05 time would itself be a valid quotes slot)
NOW = datetime(2026, 12, 16, 5, 1, tzinfo=BKK)


def specs() -> dict[str, object]:
    return {s.id: s for s in job_specs("Asia/Bangkok", now=NOW)}


def test_phase1_jobs_are_registered() -> None:
    assert set(specs()) == {
        "sync_quotes",
        "sync_daily_close",
        "sync_daily_close_catchup",
        "sync_dividends",
        "sync_earnings",
        "sync_news",
        "sync_fx",
        "sync_fx_startup",
        "cleanup_sessions",
    }


@pytest.mark.parametrize(
    ("job_id", "expected_bkk"),
    [
        ("sync_quotes", datetime(2026, 12, 16, 5, 5, tzinfo=BKK)),
        ("sync_daily_close", datetime(2026, 12, 16, 5, 30, tzinfo=BKK)),
        ("sync_daily_close_catchup", datetime(2026, 12, 16, 8, 30, tzinfo=BKK)),
        ("sync_dividends", datetime(2026, 12, 16, 6, 0, tzinfo=BKK)),
        ("sync_earnings", datetime(2026, 12, 16, 6, 0, tzinfo=BKK)),
        ("sync_news", datetime(2026, 12, 16, 5, 7, tzinfo=BKK)),
        ("sync_fx", datetime(2026, 12, 16, 18, 30, tzinfo=BKK)),
        ("cleanup_sessions", datetime(2026, 12, 17, 4, 0, tzinfo=BKK)),
        ("sync_fx_startup", NOW),
    ],
)
def test_schedule_in_bangkok_time(job_id: str, expected_bkk: datetime) -> None:
    spec = job_specs("Asia/Bangkok", now=NOW)
    trigger = next(s.trigger for s in spec if s.id == job_id)
    fire = trigger.get_next_fire_time(None, NOW)
    assert fire is not None
    assert fire == expected_bkk
    assert fire.astimezone(UTC) == expected_bkk.astimezone(UTC)


async def test_run_job_records_success(redis: Redis) -> None:
    async def ok() -> str:
        return "done"

    await run_job("sync_fx", ok, redis)
    stamp = await redis.hget(LAST_SUCCESS_KEY, "sync_fx")
    assert stamp is not None
    assert isinstance(stamp, str)  # decode_responses=True
    assert datetime.fromisoformat(stamp).tzinfo is not None
    assert await redis.hget(LAST_ERROR_KEY, "sync_fx") is None


async def test_run_job_records_errors_without_raising(redis: Redis) -> None:
    async def boom() -> None:
        raise RuntimeError("tiingo down")

    await run_job("sync_daily_close", boom, redis)  # must not raise: the scheduler keeps going
    error = await redis.hget(LAST_ERROR_KEY, "sync_daily_close")
    assert error is not None
    assert "RuntimeError: tiingo down" in error
    assert await redis.hget(LAST_SUCCESS_KEY, "sync_daily_close") is None


def test_build_scheduler_registers_every_job(redis: Redis) -> None:
    rt = cast(Runtime, SimpleNamespace(config=Settings(_env_file=None), redis=redis))
    scheduler = build_scheduler(rt)
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == set(specs())
    assert all(job.max_instances == 1 and job.coalesce for job in jobs.values())
