"""simplified factual logging and external plan workflow

Revision ID: a61c92d4e807
Revises: f3a6d2e91b74
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a61c92d4e807"
down_revision: str | None = "f3a6d2e91b74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("completed_sessions") as batch:
        batch.add_column(sa.Column("title", sa.String(length=200), nullable=True))
    with op.batch_alter_table("climbing_session_details") as batch:
        batch.add_column(sa.Column("board_name", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("angle_degrees", sa.Integer(), nullable=True))
    with op.batch_alter_table("climbing_attempts") as batch:
        batch.add_column(sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("monthly_training_blocks") as batch:
        batch.alter_column("source_proposal_id", existing_type=sa.Integer(), nullable=True)

    op.create_table(
        "imported_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cadence", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("raw_markdown", sa.Text(), nullable=False),
        sa.Column("parsed_content", sa.JSON(), nullable=False),
        sa.Column("imported_session_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_imported_plans_cadence", "imported_plans", ["cadence"])
    op.create_index("ix_imported_plans_period_start", "imported_plans", ["period_start"])

    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE completed_sessions SET title = workout_type WHERE title IS NULL")
    )
    connection.execute(
        sa.text(
            """
            UPDATE completed_sessions
            SET workout_type = CASE
                WHEN sport = 'RUNNING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('easy', 'easy run', 'recovery', 'recovery run', 'z2', 'zone 2', 'aerobic run') THEN 'EASY'
                WHEN sport = 'RUNNING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('long', 'long run', 'lr', 'long aerobic run') THEN 'LONG_RUN'
                WHEN sport = 'RUNNING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('race', 'time trial', '5k race', '10k race', 'half marathon', 'marathon') THEN 'RACE'
                WHEN sport = 'RUNNING' THEN 'QUALITY'
                WHEN sport = 'CLIMBING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('tension board', 'kilter board', 'moonboard', 'board') THEN 'BOARD'
                WHEN sport = 'CLIMBING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('sport / lead', 'sport climbing', 'sport lead', 'lead climbing', 'top rope') THEN 'SPORT_CLIMBING'
                WHEN sport = 'CLIMBING' THEN 'BOULDERING'
                ELSE workout_type
            END
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE planned_sessions
            SET workout_type = CASE
                WHEN sport = 'RUNNING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('easy', 'easy run', 'recovery', 'recovery run', 'z2', 'zone 2', 'aerobic run') THEN 'EASY'
                WHEN sport = 'RUNNING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('long', 'long run', 'lr', 'long aerobic run') THEN 'LONG_RUN'
                WHEN sport = 'RUNNING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('race', 'time trial', '5k race', '10k race', 'half marathon', 'marathon') THEN 'RACE'
                WHEN sport = 'RUNNING' THEN 'QUALITY'
                WHEN sport = 'CLIMBING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('tension board', 'kilter board', 'moonboard', 'board') THEN 'BOARD'
                WHEN sport = 'CLIMBING' AND lower(replace(workout_type, '_', ' ')) IN
                    ('sport / lead', 'sport climbing', 'sport lead', 'lead climbing', 'top rope') THEN 'SPORT_CLIMBING'
                WHEN sport = 'CLIMBING' THEN 'BOULDERING'
                ELSE workout_type
            END
            """
        )
    )
    connection.execute(
        sa.text("UPDATE climbing_attempts SET send_count = CASE WHEN sent THEN 1 ELSE 0 END")
    )


def downgrade() -> None:
    op.drop_index("ix_imported_plans_period_start", table_name="imported_plans")
    op.drop_index("ix_imported_plans_cadence", table_name="imported_plans")
    op.drop_table("imported_plans")
    with op.batch_alter_table("monthly_training_blocks") as batch:
        batch.alter_column("source_proposal_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("climbing_attempts") as batch:
        batch.drop_column("send_count")
    with op.batch_alter_table("climbing_session_details") as batch:
        batch.drop_column("angle_degrees")
        batch.drop_column("board_name")
    with op.batch_alter_table("completed_sessions") as batch:
        batch.drop_column("title")
