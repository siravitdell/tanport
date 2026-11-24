from __future__ import annotations

import asyncio

from redis.asyncio import Redis

from app.jobs.lock import JobLock, job_lock


async def test_second_holder_is_refused(redis: Redis) -> None:
    first, second = JobLock(redis, "sync", 60), JobLock(redis, "sync", 60)
    assert await first.acquire()
    assert not await second.acquire()
    assert await first.release()
    assert await second.acquire()


async def test_different_jobs_do_not_block_each_other(redis: Redis) -> None:
    assert await JobLock(redis, "sync_quotes", 60).acquire()
    assert await JobLock(redis, "sync_news", 60).acquire()


async def test_cannot_release_someone_elses_lock(redis: Redis) -> None:
    """A run that outlived its TTL must not release the lock a newer run now holds."""
    stale = JobLock(redis, "slow", 0.1)
    assert await stale.acquire()
    await asyncio.sleep(0.15)  # TTL expires
    fresh = JobLock(redis, "slow", 60)
    assert await fresh.acquire()
    assert not await stale.release()
    assert await redis.exists(fresh.key) == 1


async def test_context_manager_skips_overlapping_run(redis: Redis) -> None:
    runs: list[str] = []

    async def job(name: str, hold: float) -> None:
        async with job_lock(redis, "daily_close", 60) as acquired:
            if not acquired:
                runs.append(f"{name}:skipped")
                return
            runs.append(f"{name}:ran")
            await asyncio.sleep(hold)

    await asyncio.gather(job("a", 0.1), job("b", 0))
    assert sorted(runs) == ["a:ran", "b:skipped"]
    # released afterwards → the next run proceeds
    await job("c", 0)
    assert runs[-1] == "c:ran"


async def test_context_manager_releases_on_error(redis: Redis) -> None:
    try:
        async with job_lock(redis, "boom", 60) as acquired:
            assert acquired
            raise RuntimeError("job failed")
    except RuntimeError:
        pass
    assert await JobLock(redis, "boom", 60).acquire()
