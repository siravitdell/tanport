"""seed settings row and initial holdings (shares = 0, to be filled in by the user)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_TICKERS = ("VOO", "QQQM", "SCHD", "V", "MSFT", "KO", "GOOGL", "NVDA", "AMZN")


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO settings (id, withholding_rate, big_move_threshold_pct, dca_split) "
            "VALUES (1, 0.15, 3, CAST(:split AS jsonb)) ON CONFLICT (id) DO NOTHING"
        ).bindparams(split='{"VOO": "70", "QQQM": "20", "SCHD": "10"}')
    )
    for ticker in SEED_TICKERS:
        op.execute(
            sa.text(
                "INSERT INTO holdings (ticker, shares, avg_cost_usd) VALUES (:t, 0, 0) "
                "ON CONFLICT (ticker) DO NOTHING"
            ).bindparams(t=ticker)
        )


def downgrade() -> None:
    # Only remove seed rows the user never touched.
    op.execute(
        sa.text(
            "DELETE FROM holdings WHERE ticker = ANY(:tickers) AND shares = 0 AND avg_cost_usd = 0"
        ).bindparams(sa.bindparam("tickers", value=list(SEED_TICKERS), type_=sa.ARRAY(sa.String)))
    )
    op.execute("DELETE FROM settings WHERE id = 1")
