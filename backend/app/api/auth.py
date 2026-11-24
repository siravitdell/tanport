"""Register (invite code), login, logout, me. Session = HttpOnly cookie."""

from __future__ import annotations

import hmac
import re
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import SESSION_COOKIE, ConfigDep, CurrentUser, SessionDep
from app.config import Settings
from app.security import dummy_hash, hash_password_async, verify_password_async
from app.store import users as repo

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INVALID_LOGIN = "invalid email or password"


def _email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError("invalid email address")
    return email


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=10, max_length=128)
    invite_code: str
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return _email(value)


class LoginIn(BaseModel):
    email: str
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return _email(value)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str | None


def _set_session_cookie(response: Response, token: str, config: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(timedelta(days=config.session_ttl_days).total_seconds()),
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, response: Response, session: SessionDep, config: ConfigDep
) -> UserOut:
    expected = config.invite_code.get_secret_value()
    if not expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "registration is disabled")
    if not hmac.compare_digest(body.invite_code.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid invite code")

    password_hash = await hash_password_async(body.password)
    try:
        user = await repo.create_user(
            session, email=body.email, password_hash=password_hash, display_name=body.display_name
        )
    except repo.DuplicateEmailError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    token = await repo.create_session(session, user.id, timedelta(days=config.session_ttl_days))
    await session.commit()
    _set_session_cookie(response, token, config)
    return UserOut.model_validate(user)


@router.post("/login")
async def login(
    body: LoginIn, response: Response, session: SessionDep, config: ConfigDep
) -> UserOut:
    user = await repo.get_user_by_email(session, body.email)
    # Always run scrypt so response time doesn't reveal whether the email exists.
    ok = await verify_password_async(body.password, user.password_hash if user else dummy_hash())
    if user is None or not ok or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    token = await repo.create_session(session, user.id, timedelta(days=config.session_ttl_days))
    await session.commit()
    _set_session_cookie(response, token, config)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, session: SessionDep) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await repo.delete_session(session, token)
        await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
