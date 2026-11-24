"""users, sessions, per-user holdings / settings / portfolio_daily

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24

Market data (prices, events, fx_rates) stays shared across users.
Upgrade refuses to run if holdings contain real positions (they would have no owner);
the seed rows from 0002 (shares = 0) are removed. portfolio_daily is derived and is cleared.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_TICKERS = ("VOO", "QQQM", "SCHD", "V", "MSFT", "KO", "GOOGL", "NVDA", "AMZN")
DEFAULT_DCA_SPLIT_SQL = """'{"VOO": "70", "QQQM": "20", "SCHD": "10"}'::jsonb"""


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    ]


def upgrade() -> None:
    real_positions = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM holdings WHERE shares <> 0 OR avg_cost_usd <> 0"))
        .scalar_one()
    )
    if real_positions:
        raise RuntimeError(
            f"{real_positions} holding(s) have shares/cost but no owner. "
            "Export them (GET /api/holdings) and delete them before upgrading."
        )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lower")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_user_sessions")),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    # holdings: per user
    op.execute("DELETE FROM holdings")  # only untouched seed rows can be left (checked above)
    op.drop_constraint(op.f("uq_holdings_ticker"), "holdings", type_="unique")
    op.add_column("holdings", sa.Column("user_id", sa.BigInteger(), nullable=False))
    op.create_foreign_key(
        op.f("fk_holdings_user_id_users"),
        "holdings",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_holdings_user_id_ticker"), "holdings", ["user_id", "ticker"]
    )
    op.create_index("ix_holdings_ticker", "holdings", ["ticker"])

    # portfolio_daily: per user (derived data — safe to clear)
    op.execute("DELETE FROM portfolio_daily")
    op.drop_constraint(op.f("pk_portfolio_daily"), "portfolio_daily", type_="primary")
    op.add_column("portfolio_daily", sa.Column("user_id", sa.BigInteger(), nullable=False))
    op.create_foreign_key(
        op.f("fk_portfolio_daily_user_id_users"),
        "portfolio_daily",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_primary_key(op.f("pk_portfolio_daily"), "portfolio_daily", ["user_id", "trade_date"])

    # settings: single row -> one row per user
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "withholding_rate",
            sa.Numeric(precision=12, scale=6),
            server_default="0.15",
            nullable=False,
        ),
        sa.Column(
            "big_move_threshold_pct",
            sa.Numeric(precision=12, scale=6),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "dca_split",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(DEFAULT_DCA_SPLIT_SQL),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "big_move_threshold_pct > 0", name=op.f("ck_user_settings_big_move_positive")
        ),
        sa.CheckConstraint(
            "withholding_rate >= 0 AND withholding_rate <= 1",
            name=op.f("ck_user_settings_withholding_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_settings")),
    )
    op.drop_table("settings")


def downgrade() -> None:
    # Per-user data cannot be mapped back to a single-user schema; it is discarded.
    op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "withholding_rate",
            sa.Numeric(precision=12, scale=6),
            server_default="0.15",
            nullable=False,
        ),
        sa.Column(
            "big_move_threshold_pct",
            sa.Numeric(precision=12, scale=6),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "dca_split",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("big_move_threshold_pct > 0", name=op.f("ck_settings_big_move_positive")),
        sa.CheckConstraint("id = 1", name=op.f("ck_settings_single_row")),
        sa.CheckConstraint(
            "withholding_rate >= 0 AND withholding_rate <= 1",
            name=op.f("ck_settings_withholding_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
    )
    op.execute(
        "INSERT INTO settings (id, withholding_rate, big_move_threshold_pct, dca_split) "
        f"VALUES (1, 0.15, 3, {DEFAULT_DCA_SPLIT_SQL})"
    )
    op.drop_table("user_settings")

    op.execute("DELETE FROM portfolio_daily")
    op.drop_constraint(op.f("pk_portfolio_daily"), "portfolio_daily", type_="primary")
    op.drop_constraint(
        op.f("fk_portfolio_daily_user_id_users"), "portfolio_daily", type_="foreignkey"
    )
    op.drop_column("portfolio_daily", "user_id")
    op.create_primary_key(op.f("pk_portfolio_daily"), "portfolio_daily", ["trade_date"])

    op.execute("DELETE FROM holdings")
    op.drop_index("ix_holdings_ticker", table_name="holdings")
    op.drop_constraint(op.f("uq_holdings_user_id_ticker"), "holdings", type_="unique")
    op.drop_constraint(op.f("fk_holdings_user_id_users"), "holdings", type_="foreignkey")
    op.drop_column("holdings", "user_id")
    op.create_unique_constraint(op.f("uq_holdings_ticker"), "holdings", ["ticker"])
    for ticker in SEED_TICKERS:
        op.execute(
            sa.text(
                "INSERT INTO holdings (ticker, shares, avg_cost_usd) VALUES (:t, 0, 0)"
            ).bindparams(t=ticker)
        )

    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
