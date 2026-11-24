from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import SecretStr

from app.config import Settings
from tests.api.conftest import INVITE, PASSWORD, ClientFactory


def _register(**overrides: Any) -> dict[str, Any]:
    body = {"email": "Bob@Example.com", "password": PASSWORD, "invite_code": INVITE}
    body.update(overrides)
    return body


async def test_register_logs_in_and_normalizes_email(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/register", json=_register(display_name="Bob"))
    assert resp.status_code == 201
    assert resp.json()["email"] == "bob@example.com"

    cookie = resp.headers["set-cookie"].lower()
    assert "tanport_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"id": resp.json()["id"], "email": "bob@example.com", "display_name": "Bob"}


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"invite_code": "wrong"}, 403),
        ({"password": "short"}, 422),
        ({"email": "not-an-email"}, 422),
    ],
)
async def test_register_rejections(
    client: AsyncClient, overrides: dict[str, Any], status: int
) -> None:
    resp = await client.post("/api/auth/register", json=_register(**overrides))
    assert resp.status_code == status
    assert "set-cookie" not in resp.headers


async def test_registration_disabled_without_invite_code(
    client: AsyncClient, test_config: Settings
) -> None:
    test_config.invite_code = SecretStr("")
    resp = await client.post("/api/auth/register", json=_register())
    assert resp.status_code == 403
    assert resp.json()["detail"] == "registration is disabled"


async def test_duplicate_email_conflict(client: AsyncClient) -> None:
    assert (await client.post("/api/auth/register", json=_register())).status_code == 201
    again = await client.post("/api/auth/register", json=_register(email="BOB@example.com"))
    assert again.status_code == 409


async def test_login_logout_flow(make_client: ClientFactory) -> None:
    first = make_client()
    await first.post("/api/auth/register", json=_register())

    browser = make_client()
    assert (await browser.get("/api/auth/me")).status_code == 401

    login = await browser.post(
        "/api/auth/login", json={"email": "BOB@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    assert (await browser.get("/api/auth/me")).status_code == 200

    assert (await browser.post("/api/auth/logout")).status_code == 204
    assert (await browser.get("/api/auth/me")).status_code == 401
    # logging out one browser does not affect the other session
    assert (await first.get("/api/auth/me")).status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [("bob@example.com", "wrong password!"), ("nobody@example.com", PASSWORD)],
)
async def test_login_failures_are_indistinguishable(
    client: AsyncClient, email: str, password: str
) -> None:
    await client.post("/api/auth/register", json=_register())
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid email or password"


async def test_forged_cookie_is_rejected(client: AsyncClient) -> None:
    client.cookies.set("tanport_session", "forged-token")
    assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/holdings"),
        ("POST", "/api/holdings"),
        ("POST", "/api/holdings/import"),
        ("GET", "/api/settings"),
        ("PUT", "/api/settings"),
    ],
)
async def test_protected_routes_require_login(client: AsyncClient, method: str, path: str) -> None:
    resp = await client.request(method, path, json={})
    assert resp.status_code == 401
