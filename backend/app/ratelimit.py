"""Redis-backed sliding-window rate limiter, shared by every process (API + worker).

The window lives in a sorted set scored by Redis server time (ms), so all processes
agree on "now". Check-and-record is one Lua script, so concurrent callers can't
both take the last slot.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass

from redis.asyncio import Redis

_ACQUIRE = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local member = ARGV[3]
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window_ms)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now, member)
  redis.call('PEXPIRE', key, window_ms)
  return {1, 0}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
return {0, tonumber(oldest[2]) + window_ms - now}
"""


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    retry_after_s: float  # 0 when allowed


class RateLimitExceededError(Exception):
    def __init__(self, name: str, retry_after_s: float) -> None:
        super().__init__(f"rate limit {name!r} exceeded; retry in {retry_after_s:.1f}s")
        self.name = name
        self.retry_after_s = retry_after_s


class RateLimiter:
    def __init__(self, redis: Redis, name: str, limit: int, window_s: float) -> None:
        if limit < 1 or window_s <= 0:
            raise ValueError("limit must be >= 1 and window_s > 0")
        self._redis = redis
        self.name = name
        self.limit = limit
        self.window_ms = int(window_s * 1000)
        self._script = redis.register_script(_ACQUIRE)

    def _key(self, subject: str) -> str:
        return f"ratelimit:{self.name}:{subject}" if subject else f"ratelimit:{self.name}"

    async def try_acquire(self, subject: str = "") -> Decision:
        """Take one slot if available. `subject` scopes the limit (e.g. an IP or email)."""
        member = secrets.token_hex(8)
        allowed, wait_ms = await self._script(
            keys=[self._key(subject)], args=[self.window_ms, self.limit, member]
        )
        return Decision(allowed=bool(allowed), retry_after_s=max(0, int(wait_ms)) / 1000)

    async def acquire(self, subject: str = "", *, max_wait_s: float = 0) -> None:
        """Take a slot, sleeping up to `max_wait_s` for one; else raise RateLimitExceededError."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_wait_s
        while True:
            decision = await self.try_acquire(subject)
            if decision.allowed:
                return
            remaining = deadline - loop.time()
            if decision.retry_after_s > remaining:
                raise RateLimitExceededError(self.name, decision.retry_after_s)
            await asyncio.sleep(decision.retry_after_s + 0.01)

    async def reset(self, subject: str = "") -> None:
        await self._redis.delete(self._key(subject))


# Provider limits (free tiers), kept slightly under the published numbers.
PROVIDER_LIMITS: dict[str, tuple[int, float]] = {
    "finnhub": (55, 60),  # 60 / minute
    "tiingo": (45, 3600),  # 50 / hour (and 1000 / day)
    "tiingo_daily": (950, 86_400),
    "alphavantage": (24, 86_400),  # 25 / day
    "alphavantage_burst": (1, 1.2),  # and max 1 request / second (verified 2026-11-24)
    "bot": (180, 3600),  # 200 / hour
}


def provider_limiter(redis: Redis, provider: str) -> RateLimiter:
    limit, window = PROVIDER_LIMITS[provider]
    return RateLimiter(redis, f"provider:{provider}", limit, window)
