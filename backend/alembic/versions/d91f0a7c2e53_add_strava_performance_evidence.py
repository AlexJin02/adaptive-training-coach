"""add Strava performance evidence

Revision ID: d91f0a7c2e53
Revises: b72df5a813c4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d91f0a7c2e53"
down_revision: str | None = "b72df5a813c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("imported_running_activities") as batch_op:
        batch_op.add_column(
            sa.Column("best_efforts", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
        )
        batch_op.add_column(
            sa.Column("detail_synced_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("imported_running_activities") as batch_op:
        batch_op.drop_column("detail_synced_at")
        batch_op.drop_column("best_efforts")
