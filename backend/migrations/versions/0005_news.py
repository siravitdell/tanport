"""news: shared market news per (ticker, article), LLM summary/importance filled in later

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | Sequence[str] | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('news',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('ticker', sa.String(length=16), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('headline', sa.Text(), nullable=False),
    sa.Column('headline_key', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('provider_id', sa.String(length=64), nullable=True),
    sa.Column('snippet', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('importance', sa.SmallInteger(), nullable=True),
    sa.Column('summarized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('importance BETWEEN 1 AND 5', name=op.f('ck_news_importance_range')),
    sa.CheckConstraint('ticker = upper(ticker)', name=op.f('ck_news_ticker_upper')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_news')),
    sa.UniqueConstraint('ticker', 'url', name=op.f('uq_news_ticker_url'))
    )
    op.create_index('ix_news_published_at', 'news', ['published_at'], unique=False)
    op.create_index('ix_news_ticker_headline_key', 'news', ['ticker', 'headline_key'], unique=False)
    op.create_index('ix_news_ticker_published_at', 'news', ['ticker', 'published_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_news_ticker_published_at', table_name='news')
    op.drop_index('ix_news_ticker_headline_key', table_name='news')
    op.drop_index('ix_news_published_at', table_name='news')
    op.drop_table('news')
