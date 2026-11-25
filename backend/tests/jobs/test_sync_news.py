from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import sync_news
from app.providers.base import NewsItem, ProviderResponseError
from app.store.db import SessionFactory
from app.store.models import Holding, News, User
from tests.fakes import FakeNewsProvider

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def news(ticker: str, hours_ago: float, headline: str, url: str) -> NewsItem:
    return NewsItem(
        ticker=ticker,
        published_at=NOW - timedelta(hours=hours_ago),
        headline=headline,
        url=url,
        source="Yahoo",
        summary="snippet",
        provider_id=url[-1],
    )


@pytest.fixture
async def held(session: AsyncSession) -> None:
    user = User(email="n@example.com", password_hash="x")
    session.add(user)
    await session.flush()
    session.add_all(
        [
            Holding(user_id=user.id, ticker=t, shares=Decimal(1), avg_cost_usd=Decimal(1))
            for t in ("NVDA", "VOO")
        ]
    )
    await session.flush()


async def stored(session: AsyncSession) -> list[tuple[str, str]]:
    rows = (await session.execute(select(News).order_by(News.ticker, News.published_at))).scalars()
    return [(n.ticker, n.url) for n in rows]


@pytest.mark.usefixtures("held")
async def test_first_run_backfills_and_dedupes(
    session_factory: SessionFactory, session: AsyncSession, redis: Redis
) -> None:
    shared = "https://finnhub.io/api/news?id=s"
    provider = FakeNewsProvider(
        news={
            "NVDA": [
                news(
                    "NVDA",
                    30,
                    "Nvidia beats third quarter revenue estimates as shares jump",
                    "https://n/1",
                ),
                news(
                    "NVDA",
                    29,
                    "Nvidia Beats Third-Quarter Revenue Estimates As Shares Jump - CNBC",
                    "https://n/2",
                ),
                news("NVDA", 5, "Market wrap: chips lead", shared),
            ],
            "VOO": [
                news("VOO", 4, "Market wrap: chips lead", shared)
            ],  # same article, other holding
        }
    )
    result = await sync_news.run(session_factory, redis, provider, now=NOW)
    assert result.fetched == {"NVDA": 3, "VOO": 1}
    assert result.inserted == {"NVDA": 2, "VOO": 1}
    # first time: three days back for each ticker
    assert {(c[0], c[1], c[2]) for c in provider.calls} == {
        ("NVDA", date(2026, 11, 22), date(2026, 11, 25)),
        ("VOO", date(2026, 11, 22), date(2026, 11, 25)),
    }
    assert await stored(session) == [("NVDA", "https://n/1"), ("NVDA", shared), ("VOO", shared)]
    row = (await session.execute(select(News).where(News.url == "https://n/1"))).scalar_one()
    assert (row.headline_key, row.snippet, row.summary, row.importance) == (
        "nvidia beats third quarter revenue estimates as shares jump",
        "snippet",
        None,  # the LLM step fills these
        None,
    )


@pytest.mark.usefixtures("held")
async def test_later_runs_look_one_day_back_and_skip_known_stories(
    session_factory: SessionFactory, session: AsyncSession, redis: Redis
) -> None:
    provider = FakeNewsProvider(
        news={
            "NVDA": [
                news(
                    "NVDA",
                    2,
                    "Nvidia beats third quarter revenue estimates as shares jump",
                    "https://n/1",
                )
            ]
        }
    )
    await sync_news.run(session_factory, redis, provider, now=NOW)

    provider.calls.clear()
    provider.news["NVDA"] = [
        news(
            "NVDA", 2, "Nvidia beats third quarter revenue estimates as shares jump", "https://n/1"
        ),  # same URL
        news(
            "NVDA", 1, "Nvidia beats third-quarter revenue estimates as shares rise", "https://n/9"
        ),  # same story
        news("NVDA", 0.5, "Nvidia to build new chip plant", "https://n/3"),
    ]
    result = await sync_news.run(session_factory, redis, provider, now=NOW + timedelta(minutes=30))
    assert result.inserted["NVDA"] == 1
    assert ("NVDA", date(2026, 11, 24), date(2026, 11, 25)) in provider.calls
    assert [u for t, u in await stored(session) if t == "NVDA"] == ["https://n/1", "https://n/3"]


@pytest.mark.usefixtures("held")
async def test_old_news_is_pruned_and_errors_are_per_ticker(
    session_factory: SessionFactory, session: AsyncSession, redis: Redis
) -> None:
    session.add(
        News(
            ticker="NVDA",
            published_at=NOW - timedelta(days=200),
            headline="ancient",
            headline_key="ancient",
            url="https://old/1",
            source="x",
            provider="finnhub",
        )
    )
    await session.flush()
    provider = FakeNewsProvider(fail_with=ProviderResponseError("finnhub", "bad body"))
    result = await sync_news.run(session_factory, redis, provider, now=NOW)
    assert set(result.failed) == {"NVDA", "VOO"}
    assert result.pruned == 1
    assert await stored(session) == []
