"""API test fixtures: the app runs against the per-test rolled-back DB session."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, get_session
from app.config import Settings, get_settings
from app.main import create_app

INVITE = "test-invite-code"
PASSWORD = "correct horse battery"

type ClientFactory = Callable[[], AsyncClient]
type LoginAs = Callable[[str], Awaitable[AsyncClient]]


@pytest.fixture
def test_config() -> Settings:
    return Settings(_env_file=None, invite_code=INVITE)


@pytest.fixture
def app(session: AsyncSession, redis: Redis, test_config: Settings) -> FastAPI:
    application = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    application.dependency_overrides[get_session] = _session
    application.dependency_overrides[get_redis] = lambda: redis
    application.dependency_overrides[get_settings] = lambda: test_config
    return application


@pytest.fixture
async def make_client(app: FastAPI) -> AsyncIterator[ClientFactory]:
    """Each client has its own cookie jar, i.e. its own browser."""
    clients: list[AsyncClient] = []

    def factory() -> AsyncClient:
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield factory
    for c in clients:
        await c.aclose()


@pytest.fixture
async def client(make_client: ClientFactory) -> AsyncClient:
    return make_client()


@pytest.fixture
def login_as(make_client: ClientFactory) -> LoginAs:
    async def _login_as(email: str) -> AsyncClient:
        c = make_client()
        resp = await c.post(
            "/api/auth/register",
            json={"email": email, "password": PASSWORD, "invite_code": INVITE},
        )
        assert resp.status_code == 201, resp.text
        return c

    return _login_as


@pytest.fixture
async def alice(login_as: LoginAs) -> AsyncClient:
    return await login_as("alice@example.com")
