"""SQLAlchemy 2.0 models. Money is Numeric (Decimal in Python), times are timestamptz (UTC)."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Column types, defined once so precision stays consistent.
Money = Numeric(20, 6)  # USD/THB amounts and prices
Shares = Numeric(20, 8)  # fractional shares
Pct = Numeric(12, 6)  # percentages, e.g. 1.234567 means 1.234567 %
Rate = Numeric(12, 6)  # FX rates, tax rates


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EventType(enum.StrEnum):
    PRICE_MOVE = "price_move"
    EX_DIVIDEND = "ex_dividend"
    DIVIDEND_PAY = "dividend_pay"
    EARNINGS = "earnings"
    SPLIT = "split"
    MACRO = "macro"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lower"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class UserSession(Base):
    """Login session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Holding(TimestampMixin, Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker"),
        CheckConstraint("shares >= 0", name="shares_non_negative"),
        CheckConstraint("avg_cost_usd >= 0", name="avg_cost_non_negative"),
        CheckConstraint("ticker = upper(ticker)", name="ticker_upper"),
        Index("ix_holdings_ticker", "ticker"),  # jobs collect distinct tickers
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Shares, nullable=False, server_default="0")
    avg_cost_usd: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")


class News(Base):
    """Shared market data: one row per (ticker, article). Raw text from the provider; the Thai
    summary and the 1–5 importance are filled in later by the LLM step (NULL until then)."""

    __tablename__ = "news"
    __table_args__ = (
        UniqueConstraint("ticker", "url"),  # the same article can be filed under two holdings
        CheckConstraint("importance BETWEEN 1 AND 5", name="importance_range"),
        CheckConstraint("ticker = upper(ticker)", name="ticker_upper"),
        Index("ix_news_ticker_published_at", "ticker", "published_at"),
        Index("ix_news_ticker_headline_key", "ticker", "headline_key"),  # near-duplicate check
        Index("ix_news_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    headline_key: Mapped[str] = mapped_column(Text, nullable=False)  # normalized, for dedupe
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)  # outlet, e.g. "Yahoo"
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "finnhub"
    provider_id: Mapped[str | None] = mapped_column(String(64))
    snippet: Mapped[str | None] = mapped_column(Text)  # provider's own summary (English)
    summary: Mapped[str | None] = mapped_column(Text)  # LLM summary (Thai)
    importance: Mapped[int | None] = mapped_column(SmallInteger)
    summarized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TradeSide(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class Trade(Base):
    """One buy or sell. The source of truth for a user's positions: `holdings` is rebuilt from
    these (average cost) after every change."""

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("side IN ('buy', 'sell')", name="side_valid"),
        CheckConstraint("shares > 0", name="shares_positive"),
        CheckConstraint("price_usd >= 0", name="price_non_negative"),
        CheckConstraint("fee_usd >= 0", name="fee_non_negative"),
        CheckConstraint("usd_thb > 0", name="usd_thb_positive"),
        CheckConstraint("ticker = upper(ticker)", name="ticker_upper"),
        Index("ix_trades_user_ticker_date", "user_id", "ticker", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    shares: Mapped[Decimal] = mapped_column(Shares, nullable=False)
    price_usd: Mapped[Decimal] = mapped_column(Money, nullable=False)
    fee_usd: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    usd_thb: Mapped[Decimal] = mapped_column(Rate, nullable=False)  # the rate actually paid
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Price(Base):
    """Daily close per ticker. change_pct is NULL when there is no previous close."""

    __tablename__ = "prices"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Money)
    high: Mapped[Decimal | None] = mapped_column(Money)
    low: Mapped[Decimal | None] = mapped_column(Money)
    close: Mapped[Decimal] = mapped_column(Money, nullable=False)
    change_pct: Mapped[Decimal | None] = mapped_column(Pct)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PortfolioDaily(Base):
    """Per user, derived after each close. usd_thb records which FX rate was used."""

    __tablename__ = "portfolio_daily"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    value_usd: Mapped[Decimal] = mapped_column(Money, nullable=False)
    value_thb: Mapped[Decimal] = mapped_column(Money, nullable=False)
    change_pct: Mapped[Decimal | None] = mapped_column(Pct)
    change_thb: Mapped[Decimal | None] = mapped_column(Money)
    usd_thb: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    fx_rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        # ticker is NULL for macro events, so NULLs must collide for upserts to be idempotent.
        UniqueConstraint(
            "type",
            "ticker",
            "event_date",
            "source",
            name="uq_events_identity",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "type IN ({})".format(", ".join(f"'{t.value}'" for t in EventType)),
            name="type_valid",
        ),
        Index("ix_events_event_date", "event_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(16))
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (CheckConstraint("rate > 0", name="rate_positive"),)

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    pair: Mapped[str] = mapped_column(String(7), primary_key=True)  # e.g. "USD/THB"
    rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


DEFAULT_DCA_SPLIT_SQL = """'{"VOO": "70", "QQQM": "20", "SCHD": "10"}'::jsonb"""


class UserSettings(Base):
    """One row per user, created at registration."""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            "withholding_rate >= 0 AND withholding_rate <= 1", name="withholding_range"
        ),
        CheckConstraint("big_move_threshold_pct > 0", name="big_move_positive"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    withholding_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False, server_default="0.15")
    big_move_threshold_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, server_default="3")
    # percent strings per ticker (money/ratios never as float)
    dca_split: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text(DEFAULT_DCA_SPLIT_SQL)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
