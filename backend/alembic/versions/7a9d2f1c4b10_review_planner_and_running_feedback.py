"""review planner and running feedback

Revision ID: 7a9d2f1c4b10
Revises: 38c5cea16feb
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7a9d2f1c4b10"
down_revision: str | None = "38c5cea16feb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "planned_sessions",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("completed_sessions", sa.Column("subjective_feedback_text", sa.Text()))
    op.add_column(
        "completed_sessions",
        sa.Column(
            "subjective_feedback_source",
            sa.String(length=16),
            nullable=False,
            server_default="NONE",
        ),
    )
    op.add_column(
        "completed_sessions",
        sa.Column("subjective_feedback_created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "planning_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("memory_key", sa.String(length=80), nullable=False),
        sa.Column("level", sa.String(length=24), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_planning_memories_memory_key", "planning_memories", ["memory_key"], unique=True
    )
    op.create_index("ix_planning_memories_level", "planning_memories", ["level"])
    op.create_table(
        "planning_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cadence", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("target_start", sa.Date(), nullable=False),
        sa.Column("target_end", sa.Date(), nullable=False),
        sa.Column("deterministic_summary", sa.JSON(), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("review", sa.JSON(), nullable=False),
        sa.Column("proposed_plan", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=120)),
        sa.Column("approval_result", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_planning_proposals_cadence", "planning_proposals", ["cadence"])
    op.create_index("ix_planning_proposals_period_start", "planning_proposals", ["period_start"])
    op.create_index("ix_planning_proposals_status", "planning_proposals", ["status"])
    op.create_table(
        "monthly_training_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("month_start", sa.Date(), nullable=False),
        sa.Column("month_end", sa.Date(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source_proposal_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_proposal_id"], ["planning_proposals.id"]),
    )
    op.create_index(
        "ix_monthly_training_blocks_month_start", "monthly_training_blocks", ["month_start"]
    )
    op.create_index("ix_monthly_training_blocks_status", "monthly_training_blocks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_monthly_training_blocks_status", table_name="monthly_training_blocks")
    op.drop_index("ix_monthly_training_blocks_month_start", table_name="monthly_training_blocks")
    op.drop_table("monthly_training_blocks")
    op.drop_index("ix_planning_proposals_status", table_name="planning_proposals")
    op.drop_index("ix_planning_proposals_period_start", table_name="planning_proposals")
    op.drop_index("ix_planning_proposals_cadence", table_name="planning_proposals")
    op.drop_table("planning_proposals")
    op.drop_index("ix_planning_memories_level", table_name="planning_memories")
    op.drop_index("ix_planning_memories_memory_key", table_name="planning_memories")
    op.drop_table("planning_memories")
    op.drop_column("completed_sessions", "subjective_feedback_created_at")
    op.drop_column("completed_sessions", "subjective_feedback_source")
    op.drop_column("completed_sessions", "subjective_feedback_text")
    op.drop_column("planned_sessions", "is_locked")
