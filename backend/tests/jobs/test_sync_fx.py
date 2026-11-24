from __future__ import annotations

from datetime import date
from decimal import Decimal

from redis.asyncio import Redis

from app.jobs import sync_fx
from app.jobs.lock import JobLock
from app.providers.base import FxRate
from app.store.db import SessionFactory
from tests.fakes import FakeFXProvider


def _provider() -> FakeFXProvider:
    return FakeFXProvider(rates=[FxRate(date(2026, 11, 24), "USD/THB", Decimal("33.944"))])


async def test_run_refreshes(session_factory: SessionFactory, redis: Redis) -> None:
    provider = _provider()
    written = await sync_fx.run(session_factory, redis, provider, force=True)
    assert written is not None
    assert len(provider.calls) == 1


async def test_run_is_skipped_while_another_run_holds_the_lock(
    session_factory: SessionFactory, redis: Redis
) -> None:
    provider = _provider()
    holder = JobLock(redis, sync_fx.JOB, 60)
    assert await holder.acquire()
    assert await sync_fx.run(session_factory, redis, provider, force=True) is None
    assert provider.calls == []
