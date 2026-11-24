from __future__ import annotations

import asyncio
import time

import pytest
from redis.asyncio import Redis

from app.ratelimit import PROVIDER_LIMITS, RateLimiter, RateLimitExceededError, provider_limiter


async def test_allows_up_to_limit_then_blocks(redis: Redis) -> None:
    limiter = RateLimiter(redis, "t", limit=3, window_s=60)
    decisions = [await limiter.try_acquire() for _ in range(4)]
    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert 0 < decisions[-1].retry_after_s <= 60


async def test_subjects_are_independent(redis: Redis) -> None:
    limiter = RateLimiter(redis, "login", limit=1, window_s=60)
    assert (await limiter.try_acquire("a@example.com")).allowed
    assert not (await limiter.try_acquire("a@example.com")).allowed
    assert (await limiter.try_acquire("b@example.com")).allowed


async def test_limiters_share_state_across_instances(redis: Redis) -> None:
    """API and worker processes build their own limiter objects — the count must be shared."""
    assert (await RateLimiter(redis, "shared", 1, 60).try_acquire()).allowed
    assert not (await RateLimiter(redis, "shared", 1, 60).try_acquire()).allowed


async def test_concurrent_callers_cannot_exceed_limit(redis: Redis) -> None:
    limiter = RateLimiter(redis, "race", limit=5, window_s=60)
    decisions = await asyncio.gather(*(limiter.try_acquire() for _ in range(25)))
    assert sum(d.allowed for d in decisions) == 5


async def test_window_slides(redis: Redis) -> None:
    limiter = RateLimiter(redis, "slide", limit=1, window_s=0.2)
    assert (await limiter.try_acquire()).allowed
    assert not (await limiter.try_acquire()).allowed
    await asyncio.sleep(0.25)
    assert (await limiter.try_acquire()).allowed


async def test_acquire_waits_for_a_slot(redis: Redis) -> None:
    limiter = RateLimiter(redis, "wait", limit=1, window_s=0.2)
    await limiter.acquire()
    started = time.monotonic()
    await limiter.acquire(max_wait_s=1)
    assert time.monotonic() - started >= 0.1


async def test_acquire_raises_when_wait_too_long(redis: Redis) -> None:
    limiter = RateLimiter(redis, "daily", limit=1, window_s=86_400)
    await limiter.acquire()
    with pytest.raises(RateLimitExceededError) as info:
        await limiter.acquire(max_wait_s=5)
    assert info.value.retry_after_s > 86_000


async def test_reset(redis: Redis) -> None:
    limiter = RateLimiter(redis, "reset", limit=1, window_s=60)
    await limiter.acquire("x")
    await limiter.reset("x")
    assert (await limiter.try_acquire("x")).allowed


@pytest.mark.parametrize(("limit", "window"), [(0, 60), (1, 0), (-1, 60)])
def test_invalid_config(redis: Redis, limit: int, window: float) -> None:
    with pytest.raises(ValueError, match="limit must be"):
        RateLimiter(redis, "bad", limit, window)


@pytest.mark.parametrize("provider", sorted(PROVIDER_LIMITS))
def test_provider_limiters_exist(redis: Redis, provider: str) -> None:
    limiter = provider_limiter(redis, provider)
    assert limiter.name == f"provider:{provider}"


def test_alphavantage_stays_under_free_quota() -> None:
    limit, window = PROVIDER_LIMITS["alphavantage"]
    assert limit < 25
    assert window == 86_400
