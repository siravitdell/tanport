"""News repository (shared market data)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.news import headline_key
from app.providers.base import NewsItem
from app.store.models import News


async def known_since(
    session: AsyncSession, ticker: str, since: datetime
) -> tuple[list[str], set[str]]:
    """Headline keys and URLs of a ticker's news published since `since` (for de-duplication)."""
    result = await session.execute(
        select(News.headline_key, News.url).where(News.ticker == ticker, News.published_at >= since)
    )
    rows = result.all()
    return [k for k, _ in rows], {u for _, u in rows}


async def latest_published(session: AsyncSession, ticker: str) -> datetime | None:
    result = await session.execute(select(func.max(News.published_at)).where(News.ticker == ticker))
    return result.scalar_one_or_none()


async def insert_news(session: AsyncSession, items: Sequence[NewsItem], provider: str) -> int:
    """Insert new articles; an existing (ticker, url) is left as it is. Returns rows inserted."""
    if not items:
        return 0
    stmt = (
        insert(News)
        .values(
            [
                {
                    "ticker": n.ticker,
                    "published_at": n.published_at,
                    "headline": n.headline,
                    "headline_key": headline_key(n.headline),
                    "url": n.url,
                    "source": n.source,
                    "provider": provider,
                    "provider_id": n.provider_id,
                    "snippet": n.summary,
                }
                for n in items
            ]
        )
        .on_conflict_do_nothing(index_elements=[News.ticker, News.url])
        .returning(News.id)
    )
    return len((await session.execute(stmt)).all())


async def prune_news(session: AsyncSession, before: datetime) -> int:
    result = await session.execute(
        delete(News).where(News.published_at < before).returning(News.id)
    )
    return len(result.all())
