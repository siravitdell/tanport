"""In-memory fakes for every provider Protocol. Each records the calls it received."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.providers.base import (
    DailyBar,
    Dividend,
    DividendProvider,
    Earnings,
    EarningsProvider,
    FXProvider,
    FxRate,
    MacroEvent,
    MacroProvider,
    NewsItem,
    NewsProvider,
    PriceHistoryProvider,
    ProviderError,
    Quote,
    QuoteProvider,
)


@dataclass
class _Recorder:
    calls: list[tuple[Any, ...]] = field(default_factory=list)
    fail_with: ProviderError | None = None

    def _record(self, *args: Any) -> None:
        self.calls.append(args)
        if self.fail_with is not None:
            raise self.fail_with


@dataclass
class FakeQuoteProvider(_Recorder):
    quotes: dict[str, Quote] = field(default_factory=dict)

    async def get_quote(self, ticker: str) -> Quote:
        self._record(ticker)
        return self.quotes[ticker]


@dataclass
class FakePriceHistoryProvider(_Recorder):
    bars: dict[str, list[DailyBar]] = field(default_factory=dict)

    async def get_daily_bars(self, ticker: str, start: date, end: date) -> Sequence[DailyBar]:
        self._record(ticker, start, end)
        return [b for b in self.bars.get(ticker, []) if start <= b.trade_date <= end]


@dataclass
class FakeDividendProvider(_Recorder):
    dividends: dict[str, list[Dividend]] = field(default_factory=dict)

    async def get_dividends(self, ticker: str) -> Sequence[Dividend]:
        self._record(ticker)
        return list(self.dividends.get(ticker, []))


@dataclass
class FakeEarningsProvider(_Recorder):
    earnings: dict[str, list[Earnings]] = field(default_factory=dict)

    async def get_earnings(self, ticker: str, start: date, end: date) -> Sequence[Earnings]:
        self._record(ticker, start, end)
        return [e for e in self.earnings.get(ticker, []) if start <= e.report_date <= end]


@dataclass
class FakeNewsProvider(_Recorder):
    news: dict[str, list[NewsItem]] = field(default_factory=dict)

    async def get_news(self, ticker: str, start: date, end: date) -> Sequence[NewsItem]:
        self._record(ticker, start, end)
        return [n for n in self.news.get(ticker, []) if start <= n.published_at.date() <= end]


@dataclass
class FakeMacroProvider(_Recorder):
    events: list[MacroEvent] = field(default_factory=list)

    async def get_macro_events(self, start: date, end: date) -> Sequence[MacroEvent]:
        self._record(start, end)
        return [e for e in self.events if start <= e.event_date <= end]


@dataclass
class FakeFXProvider(_Recorder):
    rates: list[FxRate] = field(default_factory=list)

    async def get_usd_thb(self, start: date, end: date) -> Sequence[FxRate]:
        self._record(start, end)
        return [r for r in self.rates if start <= r.rate_date <= end]


# Static conformance check: mypy fails here if a fake drifts from its Protocol.
_quote: QuoteProvider = FakeQuoteProvider()
_history: PriceHistoryProvider = FakePriceHistoryProvider()
_dividends: DividendProvider = FakeDividendProvider()
_earnings: EarningsProvider = FakeEarningsProvider()
_news: NewsProvider = FakeNewsProvider()
_macro: MacroProvider = FakeMacroProvider()
_fx: FXProvider = FakeFXProvider()
