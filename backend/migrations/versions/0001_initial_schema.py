"""initial schema: orders, alerts, audit_log

Mirrors app.core.db models exactly (parity is asserted by
tests/test_hardening.py against Base.metadata.create_all).

Revision ID: 0001
Revises:
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_orders_id", "orders", ["id"], unique=True)
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])

    op.create_table(
        "alerts",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_alerts_id", "alerts", ["id"], unique=True)
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_symbol", "alerts", ["symbol"])

    op.create_table(
        "audit_log",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.String(), nullable=True),
        sa.Column("event", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])
    op.create_index("ix_audit_log_event", "audit_log", ["event"])
    op.create_index("ix_audit_log_run_id", "audit_log", ["run_id"])
    op.create_index("ix_audit_log_symbol", "audit_log", ["symbol"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("alerts")
    op.drop_table("orders")
