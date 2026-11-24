"""Provider interfaces (typing.Protocol) and the data they return.

Implementations convert provider floats to Decimal at this boundary (Decimal(str(x))),
so nothing past here ever sees a float. Times are UTC.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol

# ---------------------------------------------------------------- errors


class ProviderError(Exception):
    """Base class for failures talking to an external data provider."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class ProviderAccessDeniedError(ProviderError):
    """401/403 — bad key or endpoint not on our plan. Retrying will not help."""


class ProviderRateLimitedError(ProviderError):
    """Our own limiter or the provider refused the call; try again later."""

    def __init__(self, provider: str, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(provider, message)
        self.retry_after_s = retry_after_s


class ProviderUnavailableError(ProviderError):
    """Network error or 5xx after retries."""


class ProviderResponseError(ProviderError):
    """The provider answered, but not with data we can use (bad shape, error body)."""


# ---------------------------------------------------------------- data


@dataclass(frozen=True, slots=True)
class Quote:
    ticker: str
    price: Decimal
    prev_close: Decimal
    change: Decimal
    change_pct: Decimal  # 1.5 means +1.5 %
    as_of_utc: datetime


@dataclass(frozen=True, slots=True)
class DailyBar:
    ticker: str
    trade_date: date  # US trading date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal


@dataclass(frozen=True, slots=True)
class Dividend:
    ticker: str
    ex_date: date
    pay_date: date | None
    record_date: date | None
    declaration_date: date | None
    amount: Decimal  # USD per share, before tax


EarningsHour = Literal["bmo", "amc", "dmh", "unknown"]


@dataclass(frozen=True, slots=True)
class Earnings:
    ticker: str
    report_date: date  # US date
    hour: EarningsHour  # before market open / after market close / during market hours
    eps_estimate: Decimal | None
    quarter: int | None
    year: int | None


@dataclass(frozen=True, slots=True)
class NewsItem:
    ticker: str
    published_at: datetime
    headline: str
    url: str
    source: str
    summary: str | None


@dataclass(frozen=True, slots=True)
class MacroEvent:
    name: str  # e.g. "FOMC", "CPI", "NFP"
    event_date: date
    event_time_utc: datetime | None
    country: str


@dataclass(frozen=True, slots=True)
class FxRate:
    rate_date: date
    pair: str  # "USD/THB"
    rate: Decimal


# ---------------------------------------------------------------- protocols


class QuoteProvider(Protocol):
    async def get_quote(self, ticker: str) -> Quote: ...


class PriceHistoryProvider(Protocol):
    async def get_daily_bars(self, ticker: str, start: date, end: date) -> Sequence[DailyBar]: ...


class DividendProvider(Protocol):
    async def get_dividends(self, ticker: str) -> Sequence[Dividend]:
        """Paid and declared dividends, any order. Empty for non-payers."""
        ...


class EarningsProvider(Protocol):
    async def get_earnings(self, ticker: str, start: date, end: date) -> Sequence[Earnings]: ...


class NewsProvider(Protocol):
    async def get_news(self, ticker: str, start: date, end: date) -> Sequence[NewsItem]: ...


class MacroProvider(Protocol):
    async def get_macro_events(self, start: date, end: date) -> Sequence[MacroEvent]: ...


class FXProvider(Protocol):
    async def get_usd_thb(self, start: date, end: date) -> Sequence[FxRate]: ...
