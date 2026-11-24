"""Redis connection factory (redis.asyncio)."""

from __future__ import annotations

from redis.asyncio import Redis


def make_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)
