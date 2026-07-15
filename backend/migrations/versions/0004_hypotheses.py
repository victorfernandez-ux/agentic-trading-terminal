"""hypotheses table (hypothesis registry, roadmap A2)

Mirrors app.core.db.HypothesisRow exactly (parity is asserted by
tests/test_hardening.py against Base.metadata.create_all).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hypotheses",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(), nullable=True),
        sa.Column("ts", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_hypotheses_id", "hypotheses", ["id"], unique=True)
    op.create_index("ix_hypotheses_ts", "hypotheses", ["ts"])
    op.create_index("ix_hypotheses_symbol", "hypotheses", ["symbol"])
    op.create_index("ix_hypotheses_status", "hypotheses", ["status"])


def downgrade() -> None:
    op.drop_table("hypotheses")
