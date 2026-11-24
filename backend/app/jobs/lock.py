"""Redis lock so an overlapping run of the same job is skipped, not run twice.

Release only deletes the key if we still own it (compare token), so a run that outlived
its TTL can't release a lock that another run has since taken.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class JobLock:
    def __init__(self, redis: Redis, name: str, ttl_s: float) -> None:
        self._redis = redis
        self.key = f"lock:job:{name}"
        self._ttl_ms = int(ttl_s * 1000)
        self._token = secrets.token_hex(16)
        self._release = redis.register_script(_RELEASE)

    async def acquire(self) -> bool:
        return bool(await self._redis.set(self.key, self._token, nx=True, px=self._ttl_ms))

    async def release(self) -> bool:
        return bool(await self._release(keys=[self.key], args=[self._token]))


@asynccontextmanager
async def job_lock(redis: Redis, name: str, ttl_s: float) -> AsyncIterator[bool]:
    """`async with job_lock(r, "sync_quotes", 600) as acquired: if not acquired: return`"""
    lock = JobLock(redis, name, ttl_s)
    acquired = await lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            await lock.release()
