"""replace reversible voiding with permanent completed-session deletion

Revision ID: e8f3b7c91a42
Revises: c4e81a6b2d90
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8f3b7c91a42"
down_revision: str | None = "c4e81a6b2d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The athlete explicitly chose permanent deletion. Remove previously voided evidence and
    # detach audit/media references before dropping the temporary reversible-delete columns.
    op.execute(
        sa.text(
            "UPDATE adaptation_events SET trigger_session_id = NULL "
            "WHERE trigger_session_id IN "
            "(SELECT id FROM completed_sessions WHERE voided_at IS NOT NULL)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE media_imports SET confirmed_session_id = NULL "
            "WHERE confirmed_session_id IN "
            "(SELECT id FROM completed_sessions WHERE voided_at IS NOT NULL)"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM fatigue_snapshots WHERE source_key IN "
            "(SELECT 'session:' || id FROM completed_sessions WHERE voided_at IS NOT NULL)"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM readiness_snapshots WHERE source_key IN "
            "(SELECT 'session:' || id FROM completed_sessions WHERE voided_at IS NOT NULL)"
        )
    )
    op.execute(sa.text("DELETE FROM completed_sessions WHERE voided_at IS NOT NULL"))
    op.drop_index("ix_completed_sessions_voided_at", table_name="completed_sessions")
    op.drop_column("completed_sessions", "void_reason")
    op.drop_column("completed_sessions", "voided_at")


def downgrade() -> None:
    op.add_column(
        "completed_sessions",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("completed_sessions", sa.Column("void_reason", sa.Text(), nullable=True))
    op.create_index("ix_completed_sessions_voided_at", "completed_sessions", ["voided_at"])
