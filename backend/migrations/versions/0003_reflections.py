"""reflections table (reflection memory, roadmap A1)

Mirrors app.core.db.ReflectionRow exactly (parity is asserted by
tests/test_hardening.py against Base.metadata.create_all).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reflections",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(), nullable=True),
        sa.Column("ts", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("portfolio_id", sa.String(), nullable=True),
        sa.Column("close_order_id", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_reflections_id", "reflections", ["id"], unique=True)
    op.create_index("ix_reflections_ts", "reflections", ["ts"])
    op.create_index("ix_reflections_symbol", "reflections", ["symbol"])
    op.create_index("ix_reflections_portfolio_id", "reflections", ["portfolio_id"])
    op.create_index("ix_reflections_close_order_id", "reflections",
                    ["close_order_id"], unique=True)


def downgrade() -> None:
    op.drop_table("reflections")
