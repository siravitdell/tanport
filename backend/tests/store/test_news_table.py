from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import News

AT = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


def item(ticker: str = "NVDA", url: str = "https://finnhub.io/api/news?id=1", **kw: object) -> News:
    fields: dict[str, object] = {
        "ticker": ticker,
        "published_at": AT,
        "headline": "Nvidia beats",
        "headline_key": "nvidia beats",
        "url": url,
        "source": "Yahoo",
        "provider": "finnhub",
        **kw,
    }
    return News(**fields)


async def test_same_article_under_two_tickers_is_allowed(session: AsyncSession) -> None:
    session.add_all([item("NVDA"), item("QQQM")])
    await session.flush()


async def test_same_article_twice_for_one_ticker_is_not(session: AsyncSession) -> None:
    session.add_all([item("NVDA"), item("NVDA")])
    with pytest.raises(IntegrityError, match="uq_news_ticker_url"):
        await session.flush()


@pytest.mark.parametrize(
    ("importance", "ok"), [(None, True), (1, True), (5, True), (0, False), (6, False)]
)
async def test_importance_is_1_to_5_or_not_scored_yet(
    session: AsyncSession, importance: int | None, ok: bool
) -> None:
    session.add(item(importance=importance))
    if ok:
        await session.flush()
    else:
        with pytest.raises(IntegrityError, match="ck_news_importance_range"):
            await session.flush()
