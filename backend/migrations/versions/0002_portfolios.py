"""portfolios table

Adds the portfolios table (multi-portfolio groundwork). The app ensures a
'default' row at startup; orders carry an optional portfolio_id in their JSON
blob, so no change to the orders table is needed.

Revision ID: 0002_portfolios
Revises: 0001_initial
Create Date: 2026-06-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_portfolios"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("portfolios")
