"""initial schema: orders, alerts, audit_log

Baseline migration matching app.core.db models. The running app still calls
init_db() (create_all) for zero-setup dev; this migration is the same schema
for real (Postgres) deployments via `alembic upgrade head`.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _kv_table(name: str) -> None:
    """orders/alerts share the same shape: a JSON `data` blob keyed by id."""
    op.create_table(
        name,
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index(f"ix_{name}_id", name, ["id"], unique=True)
    op.create_index(f"ix_{name}_status", name, ["status"], unique=False)
    op.create_index(f"ix_{name}_symbol", name, ["symbol"], unique=False)


def upgrade() -> None:
    _kv_table("orders")
    _kv_table("alerts")
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
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"], unique=False)
    op.create_index("ix_audit_log_event", "audit_log", ["event"], unique=False)
    op.create_index("ix_audit_log_run_id", "audit_log", ["run_id"], unique=False)
    op.create_index("ix_audit_log_symbol", "audit_log", ["symbol"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_log")
    for name in ("alerts", "orders"):
        op.drop_index(f"ix_{name}_symbol", table_name=name)
        op.drop_index(f"ix_{name}_status", table_name=name)
        op.drop_index(f"ix_{name}_id", table_name=name)
        op.drop_table(name)
