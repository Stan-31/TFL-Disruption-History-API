"""create line status periods

Revision ID: 89b911836326
Revises:
Create Date: 2026-07-18 13:22:30.104198

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "89b911836326"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "line_status_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.String(length=64), nullable=False),
        sa.Column("line_name", sa.String(length=128), nullable=False),
        sa.Column("mode_name", sa.String(length=32), nullable=False),
        sa.Column("status_severity", sa.SmallInteger(), nullable=False),
        sa.Column("status_severity_description", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_line_status_periods_line_id"), "line_status_periods", ["line_id"], unique=False
    )
    op.create_index(
        "uq_line_status_periods_open",
        "line_status_periods",
        ["line_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_line_status_periods_open",
        table_name="line_status_periods",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.drop_index(op.f("ix_line_status_periods_line_id"), table_name="line_status_periods")
    op.drop_table("line_status_periods")
