"""add reversible voiding to completed sessions

Revision ID: c4e81a6b2d90
Revises: 7a9d2f1c4b10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4e81a6b2d90"
down_revision: str | None = "7a9d2f1c4b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "completed_sessions",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("completed_sessions", sa.Column("void_reason", sa.Text(), nullable=True))
    op.create_index("ix_completed_sessions_voided_at", "completed_sessions", ["voided_at"])


def downgrade() -> None:
    op.drop_index("ix_completed_sessions_voided_at", table_name="completed_sessions")
    op.drop_column("completed_sessions", "void_reason")
    op.drop_column("completed_sessions", "voided_at")
