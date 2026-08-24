from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime, time
from enum import Enum
from typing import Any

from sqlalchemy import Date, DateTime, Time, select
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Session

from app.db import Base

SCHEMA_VERSION = "1.3"
LEGACY_SCHEMA_VERSIONS = {"1.0", "1.1", "1.2"}
EXPORTABLE_TABLES = {
    "completed_sessions",
    "planned_sessions",
    "running_session_details",
    "climbing_session_details",
    "recovery_checkins",
    "tb2_benchmarks",
    "gym_sets",
    "gym_set_colour_progress",
    "training_notes",
    "weekly_reviews",
    "adaptation_events",
}
CSV_ALIASES = {
    "workouts": "completed_sessions",
    "recovery": "recovery_checkins",
    "benchmarks": "tb2_benchmarks",
    "notes": "training_notes",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def create_backup(db: Session) -> dict[str, Any]:
    data: dict[str, list[dict[str, Any]]] = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(select(table)).mappings().all()
        serialized = [{key: _json_value(value) for key, value in row.items()} for row in rows]
        if table.name == "media_imports":
            for row in serialized:
                row["local_path"] = None
                row["retain_raw"] = False
        data[table.name] = serialized
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "data": data,
    }


def _db_value(column: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Time) and isinstance(value, str):
        return time.fromisoformat(value)
    if (
        isinstance(column.type, Date)
        and not isinstance(column.type, DateTime)
        and isinstance(value, str)
    ):
        return date.fromisoformat(value)
    if isinstance(column.type, SAEnum) and isinstance(value, str):
        enum_cls = column.type.enum_class
        return enum_cls(value) if enum_cls else value
    return value


def restore_backup(db: Session, payload: dict[str, Any]) -> int:
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION and schema_version not in LEGACY_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported backup schema version: {payload.get('schema_version')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Backup data must be an object")
    if schema_version == "1.0" and "imported_running_activities" not in data:
        # Version 1.0 predates the Strava Inbox. Treat only this known new table as empty; all
        # original tables remain mandatory so a partial payload can never wipe local data.
        data = {**data, "imported_running_activities": []}
    if schema_version in {"1.0", "1.1"}:
        imported_rows = data.get("imported_running_activities", [])
        if isinstance(imported_rows, list):
            for row in imported_rows:
                if isinstance(row, dict):
                    row.setdefault("best_efforts", [])
                    row.setdefault("detail_synced_at", None)
    if schema_version in LEGACY_SCHEMA_VERSIONS:
        imported_rows = data.get("imported_running_activities", [])
        linked_running: dict[int, tuple[float | None, list[Any]]] = {}
        if isinstance(imported_rows, list):
            for row in imported_rows:
                if not isinstance(row, dict) or row.get("provider") != "STRAVA":
                    continue
                cadence = row.get("cadence")
                if isinstance(cadence, (int, float)):
                    row["cadence"] = cadence * 2
                laps = row.get("laps")
                if isinstance(laps, list):
                    for lap in laps:
                        if isinstance(lap, dict) and isinstance(lap.get("cadence"), (int, float)):
                            lap["cadence"] *= 2
                completed_id = row.get("completed_session_id")
                if isinstance(completed_id, int):
                    linked_running[completed_id] = (
                        row.get("cadence"),
                        laps if isinstance(laps, list) else [],
                    )
        running_rows = data.get("running_session_details", [])
        if isinstance(running_rows, list):
            for row in running_rows:
                if not isinstance(row, dict) or row.get("session_id") not in linked_running:
                    continue
                row["cadence"], row["splits"] = linked_running[row["session_id"]]
    required_tables = {table.name for table in Base.metadata.sorted_tables}
    missing_tables = sorted(required_tables - set(data))
    if missing_tables:
        raise ValueError(f"Backup is missing required tables: {missing_tables}")
    unexpected_tables = sorted(set(data) - required_tables)
    if unexpected_tables:
        raise ValueError(f"Backup contains unexpected tables: {unexpected_tables}")
    profile_rows = data["athlete_profiles"]
    if not isinstance(profile_rows, list) or len(profile_rows) != 1:
        raise ValueError("Backup must contain exactly one athlete_profiles record")
    profile_row = profile_rows[0]
    profile_columns = {column.name for column in Base.metadata.tables["athlete_profiles"].columns}
    if not isinstance(profile_row, dict) or set(profile_row) != profile_columns:
        raise ValueError("Backup athlete_profiles record is incomplete or malformed")
    if profile_row.get("id") != 1:
        raise ValueError("Backup athlete_profiles record must have id 1")
    # Validate the full structure and values before changing any local state.
    prepared: dict[str, list[dict[str, Any]]] = {}
    for table in Base.metadata.sorted_tables:
        incoming = data.get(table.name, [])
        if not isinstance(incoming, list):
            raise ValueError(f"Table {table.name} must be a list")
        allowed = {column.name for column in table.columns}
        prepared[table.name] = []
        for raw in incoming:
            if not isinstance(raw, dict):
                raise ValueError(f"Rows in {table.name} must be objects")
            unknown = set(raw) - allowed
            if unknown:
                raise ValueError(f"Unknown columns in {table.name}: {sorted(unknown)}")
            missing = allowed - set(raw)
            if missing:
                raise ValueError(f"Missing columns in {table.name}: {sorted(missing)}")
            prepared[table.name].append(
                {
                    column.name: _db_value(column, raw[column.name])
                    for column in table.columns
                    if column.name in raw
                }
            )
    restored = 0
    try:
        # The UI requires an explicit RESTORE confirmation. Replace atomically: reverse FK order
        # for deletes, then forward FK order for inserts; rollback restores the old state on error.
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        for table in Base.metadata.sorted_tables:
            for values in prepared[table.name]:
                db.execute(table.insert().values(**values))
                restored += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return restored


def export_csv(db: Session, table_name: str) -> str:
    table_name = CSV_ALIASES.get(table_name, table_name)
    if table_name not in EXPORTABLE_TABLES:
        raise ValueError(f"Unsupported CSV export: {table_name}")
    table = Base.metadata.tables[table_name]
    rows = db.execute(select(table)).mappings().all()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[column.name for column in table.columns])
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else _json_value(value)
                for key, value in row.items()
            }
        )
    return output.getvalue()
