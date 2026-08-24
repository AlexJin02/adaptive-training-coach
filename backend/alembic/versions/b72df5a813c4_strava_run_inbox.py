"""add Strava run inbox

Revision ID: b72df5a813c4
Revises: a61c92d4e807
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b72df5a813c4"
down_revision: str | None = "a61c92d4e807"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "imported_running_activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("external_activity_id", sa.String(length=80), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("suggested_session_type", sa.String(length=80), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("elapsed_time_seconds", sa.Integer(), nullable=False),
        sa.Column("moving_time_seconds", sa.Integer(), nullable=True),
        sa.Column("average_pace_seconds_per_km", sa.Float(), nullable=True),
        sa.Column("average_hr", sa.Integer(), nullable=True),
        sa.Column("maximum_hr", sa.Integer(), nullable=True),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column("cadence", sa.Float(), nullable=True),
        sa.Column("laps", sa.JSON(), nullable=False),
        sa.Column("planned_session_id", sa.Integer(), nullable=True),
        sa.Column("completed_session_id", sa.Integer(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("distance_km >= 0", name="ck_imported_run_distance_nonnegative"),
        sa.CheckConstraint("elapsed_time_seconds > 0", name="ck_imported_run_elapsed_positive"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.id"]),
        sa.ForeignKeyConstraint(
            ["completed_session_id"], ["completed_sessions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["planned_session_id"], ["planned_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("completed_session_id"),
        sa.UniqueConstraint("provider", "external_activity_id", name="uq_imported_run_provider_id"),
    )
    op.create_index(
        op.f("ix_imported_running_activities_activity_date"),
        "imported_running_activities",
        ["activity_date"],
    )
    op.create_index(
        op.f("ix_imported_running_activities_needs_review"),
        "imported_running_activities",
        ["needs_review"],
    )
    op.create_index(
        op.f("ix_imported_running_activities_planned_session_id"),
        "imported_running_activities",
        ["planned_session_id"],
    )
    op.create_index(
        op.f("ix_imported_running_activities_provider"),
        "imported_running_activities",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_imported_running_activities_provider"),
        table_name="imported_running_activities",
    )
    op.drop_index(
        op.f("ix_imported_running_activities_planned_session_id"),
        table_name="imported_running_activities",
    )
    op.drop_index(
        op.f("ix_imported_running_activities_needs_review"),
        table_name="imported_running_activities",
    )
    op.drop_index(
        op.f("ix_imported_running_activities_activity_date"),
        table_name="imported_running_activities",
    )
    op.drop_table("imported_running_activities")
