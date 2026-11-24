"""Users and login sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.security import new_session_token, token_digest
from app.store.models import User, UserSession, UserSettings


class DuplicateEmailError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"an account with {email} already exists")
        self.email = email


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession, *, email: str, password_hash: str, display_name: str | None
) -> User:
    """Create the user and their default settings row."""
    stmt = (
        insert(User)
        .values(email=email.lower(), password_hash=password_hash, display_name=display_name)
        .on_conflict_do_nothing(index_elements=[User.email])
        .returning(User.id)
    )
    user_id = (await session.execute(stmt)).scalar_one_or_none()
    if user_id is None:
        raise DuplicateEmailError(email)
    session.add(UserSettings(user_id=user_id))
    await session.flush()
    user = await session.get(User, user_id)
    if user is None:  # pragma: no cover — inserted in this same transaction
        raise RuntimeError(f"user {user_id} vanished after insert")
    return user


async def create_session(session: AsyncSession, user_id: int, ttl: timedelta) -> str:
    """Return the raw token (for the cookie); only its digest is stored."""
    token = new_session_token()
    session.add(
        UserSession(
            token_hash=token_digest(token),
            user_id=user_id,
            expires_at=datetime.now(UTC) + ttl,
        )
    )
    await session.flush()
    return token


async def get_user_for_token(session: AsyncSession, token: str) -> User | None:
    stmt = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_digest(token),
            UserSession.expires_at > func.now(),
            User.is_active.is_(True),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_session(session: AsyncSession, token: str) -> None:
    await session.execute(delete(UserSession).where(UserSession.token_hash == token_digest(token)))


async def delete_expired_sessions(session: AsyncSession) -> int:
    result = await session.execute(
        delete(UserSession)
        .where(UserSession.expires_at <= func.now())
        .returning(UserSession.token_hash)
    )
    return len(result.all())
