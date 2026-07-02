"""portfolios table + orders.portfolio_id (multi-portfolio groundwork)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_portfolios_id", "portfolios", ["id"], unique=True)

    op.add_column("orders", sa.Column("portfolio_id", sa.String(), nullable=True))
    op.create_index("ix_orders_portfolio_id", "orders", ["portfolio_id"])


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:  # SQLite-safe column drop
        batch.drop_index("ix_orders_portfolio_id")
        batch.drop_column("portfolio_id")
    op.drop_table("portfolios")
