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
    Index,
    MetaData,
    Numeric,
    SmallInteger,
    String,
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


class Holding(TimestampMixin, Base):
    __tablename__ = "holdings"
    __table_args__ = (
        CheckConstraint("shares >= 0", name="shares_non_negative"),
        CheckConstraint("avg_cost_usd >= 0", name="avg_cost_non_negative"),
        CheckConstraint("ticker = upper(ticker)", name="ticker_upper"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    shares: Mapped[Decimal] = mapped_column(Shares, nullable=False, server_default="0")
    avg_cost_usd: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")


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
    """Derived after each close. usd_thb records which FX rate was used for value_thb."""

    __tablename__ = "portfolio_daily"

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


class AppSettings(Base):
    """Single-row table (id = 1) with user-editable settings."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint(
            "withholding_rate >= 0 AND withholding_rate <= 1", name="withholding_range"
        ),
        CheckConstraint("big_move_threshold_pct > 0", name="big_move_positive"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default="1")
    withholding_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False, server_default="0.15")
    big_move_threshold_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, server_default="3")
    # {"VOO": "70", "QQQM": "20", "SCHD": "10"} — percent strings (money/ratios never as float)
    dca_split: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
