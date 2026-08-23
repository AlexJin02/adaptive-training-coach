"""compact completed-session AI analysis

Revision ID: f3a6d2e91b74
Revises: e8f3b7c91a42
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "f3a6d2e91b74"
down_revision: str | None = "e8f3b7c91a42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _compact(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw_summary = value.get("summary") or value.get("execution_summary")
    if not isinstance(raw_summary, str) or not raw_summary.strip():
        return None
    summary = " ".join(raw_summary.split())
    if len(summary) > 200:
        summary = f"{summary[:199].rstrip()}…"
    confidence = value.get("confidence")
    return {
        "summary": summary,
        "confidence": confidence if confidence in {"LOW", "MODERATE", "HIGH"} else None,
    }


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, ai_analysis FROM completed_sessions WHERE ai_analysis IS NOT NULL")
    ).mappings()
    for row in rows:
        raw = row["ai_analysis"]
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            parsed = None
        compact = _compact(parsed)
        connection.execute(
            sa.text("UPDATE completed_sessions SET ai_analysis = :analysis WHERE id = :id"),
            {
                "analysis": json.dumps(compact, ensure_ascii=False) if compact else None,
                "id": row["id"],
            },
        )


def downgrade() -> None:
    # The discarded verbose AI repetition cannot be reconstructed. Objective workout evidence
    # remains in its normalized session/detail tables.
    pass
