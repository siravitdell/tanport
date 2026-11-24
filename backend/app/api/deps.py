"""FastAPI dependencies: DB session, Redis, config, current user."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.store.models import User
from app.store.users import get_user_for_token

SESSION_COOKIE = "tanport_session"


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Handlers commit explicitly; anything uncommitted is rolled back."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
ConfigDep = Annotated[Settings, Depends(get_settings)]


async def get_current_user(request: Request, session: SessionDep) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user = await get_user_for_token(session, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_now() -> datetime:
    """Current time (UTC). Overridden in tests to pin market open/closed scenarios."""
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]
