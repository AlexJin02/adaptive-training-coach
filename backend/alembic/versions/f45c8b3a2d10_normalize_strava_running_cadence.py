"""normalize Strava running cadence to total steps per minute

Revision ID: f45c8b3a2d10
Revises: d91f0a7c2e53
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "f45c8b3a2d10"
down_revision: str | None = "d91f0a7c2e53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalise_laps(value: Any, multiplier: float) -> list[Any]:
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            result.append(row)
            continue
        updated = dict(row)
        cadence = updated.get("cadence")
        if isinstance(cadence, (int, float)):
            updated["cadence"] = cadence * multiplier
        result.append(updated)
    return result


def _convert(multiplier: float) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, cadence, laps, completed_session_id "
            "FROM imported_running_activities WHERE provider = 'STRAVA'"
        )
    ).mappings()
    for row in rows:
        cadence = row["cadence"]
        converted_cadence = cadence * multiplier if cadence is not None else None
        converted_laps = _normalise_laps(row["laps"], multiplier)
        connection.execute(
            sa.text(
                "UPDATE imported_running_activities "
                "SET cadence = :cadence, laps = :laps WHERE id = :id"
            ),
            {
                "id": row["id"],
                "cadence": converted_cadence,
                "laps": json.dumps(converted_laps),
            },
        )
        if row["completed_session_id"] is not None:
            connection.execute(
                sa.text(
                    "UPDATE running_session_details SET cadence = :cadence, splits = :splits "
                    "WHERE session_id = :session_id"
                ),
                {
                    "session_id": row["completed_session_id"],
                    "cadence": converted_cadence,
                    "splits": json.dumps(converted_laps),
                },
            )


def upgrade() -> None:
    _convert(2.0)


def downgrade() -> None:
    _convert(0.5)
