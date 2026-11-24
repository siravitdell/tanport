"""Async engine / session factory."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# What jobs take: anything that opens a session as an async context manager.
# An async_sessionmaker fits; tests pass one that reuses their rolled-back session.
type SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
