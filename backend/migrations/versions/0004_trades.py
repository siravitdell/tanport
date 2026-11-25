"""trades: every buy/sell; holdings become derived from them

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25

Existing positions (entered as shares + average cost) become one opening buy each, dated the
day the holding was created, at its average cost, with the USD/THB rate of that day (the latest
earlier rate, else the earliest rate known). Downgrade drops the trades and leaves holdings as
they are.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("shares", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("price_usd", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("fee_usd", sa.Numeric(precision=20, scale=6), server_default="0", nullable=False),
        sa.Column("usd_thb", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("side IN ('buy', 'sell')", name=op.f("ck_trades_side_valid")),
        sa.CheckConstraint("shares > 0", name=op.f("ck_trades_shares_positive")),
        sa.CheckConstraint("price_usd >= 0", name=op.f("ck_trades_price_non_negative")),
        sa.CheckConstraint("fee_usd >= 0", name=op.f("ck_trades_fee_non_negative")),
        sa.CheckConstraint("usd_thb > 0", name=op.f("ck_trades_usd_thb_positive")),
        sa.CheckConstraint("ticker = upper(ticker)", name=op.f("ck_trades_ticker_upper")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_trades_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trades")),
    )
    op.create_index(
        "ix_trades_user_ticker_date", "trades", ["user_id", "ticker", "trade_date"], unique=False
    )

    bind = op.get_bind()
    positions = bind.execute(sa.text("SELECT count(*) FROM holdings WHERE shares > 0")).scalar_one()
    if positions:
        if not bind.execute(sa.text("SELECT count(*) FROM fx_rates WHERE pair = 'USD/THB'")).scalar_one():
            raise RuntimeError(
                "holdings exist but fx_rates has no USD/THB rate to value their opening trades: "
                "run `python -m app.jobs.sync_fx` first, then migrate again"
            )
        bind.execute(
            sa.text(
                """
                INSERT INTO trades (user_id, ticker, side, trade_date, shares, price_usd, fee_usd, usd_thb)
                SELECT h.user_id, h.ticker, 'buy', d.day, h.shares, h.avg_cost_usd, 0,
                       COALESCE(
                         (SELECT rate FROM fx_rates WHERE pair = 'USD/THB' AND date <= d.day
                          ORDER BY date DESC LIMIT 1),
                         (SELECT rate FROM fx_rates WHERE pair = 'USD/THB'
                          ORDER BY date ASC LIMIT 1))
                FROM holdings h
                CROSS JOIN LATERAL (SELECT (h.created_at AT TIME ZONE 'Asia/Bangkok')::date AS day) d
                WHERE h.shares > 0
                """
            )
        )
    # rows with shares = 0 carry nothing: holdings now only list what is held
    bind.execute(sa.text("DELETE FROM holdings WHERE shares = 0"))


def downgrade() -> None:
    op.drop_index("ix_trades_user_ticker_date", table_name="trades")
    op.drop_table("trades")
