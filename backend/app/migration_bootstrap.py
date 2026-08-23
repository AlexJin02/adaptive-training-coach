"""Safely adopt databases created before Alembic owned the schema.

Early local builds used ``Base.metadata.create_all()``.  Such a database has real
athlete data and tables, but no Alembic revision, so a normal initial upgrade
would try to create every table again.  This module only adopts the two known
legacy shapes produced by this project:

* a schema already identical to the current ORM; or
* the pre-release schema missing the three additive columns and several RPE
  checks, with the earlier 0--10 completed-session RPE constraint.

Anything else fails closed.  A timestamped SQLite backup is written before any
schema mutation or stamp.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect
from sqlalchemy.engine import make_url

from app import models  # noqa: F401
from app.db import Base, engine

KNOWN_COLUMNS = {
    ("completed_sessions", "ai_analysis"),
    ("running_fitness_estimates", "is_demo"),
    ("threshold_estimates", "is_demo"),
}
KNOWN_CHECKS = {
    "ck_plan_target_rpe_min",
    "ck_plan_target_rpe_max",
    "ck_plan_target_rpe_range",
    "ck_strength_set_rpe",
}
KNOWN_CHECK_LOCATIONS = {
    ("planned_sessions", "ck_plan_target_rpe_min"),
    ("planned_sessions", "ck_plan_target_rpe_max"),
    ("planned_sessions", "ck_plan_target_rpe_range"),
    ("strength_sets", "ck_strength_set_rpe"),
}
KNOWN_MODIFIED_CHECKS = {
    (
        "completed_sessions",
        "ck_session_rpe",
        "rpe is null or (rpe >= 0 and rpe <= 10)",
        "rpe is null or (rpe >= 1 and rpe <= 10)",
    )
}


class LegacySchemaError(RuntimeError):
    """Raised when an unversioned database is not a recognised project schema."""


def _database_path(target_engine: Engine) -> Path | None:
    url = make_url(str(target_engine.url))
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database).expanduser().resolve()


def _backup_sqlite(target_engine: Engine) -> Path | None:
    source_path = _database_path(target_engine)
    if source_path is None or not source_path.exists():
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = source_path.with_name(f"{source_path.name}.pre-alembic-{timestamp}.bak")
    with sqlite3.connect(source_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
        result = destination.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise LegacySchemaError(
                f"SQLite refused the pre-migration backup integrity check: {backup_path}"
            )
    return backup_path


def _flatten_diffs(diffs: list[Any]) -> list[tuple[Any, ...]]:
    flattened: list[tuple[Any, ...]] = []
    for diff in diffs:
        if isinstance(diff, tuple):
            flattened.append(diff)
        elif isinstance(diff, list):
            flattened.extend(_flatten_diffs(diff))
    return flattened


def _known_legacy_diff(diff: tuple[Any, ...]) -> bool:
    if diff[0] == "add_column":
        return (str(diff[2]), str(diff[3].name)) in KNOWN_COLUMNS
    if diff[0] == "add_constraint":
        constraint = diff[1]
        return (
            str(constraint.table.name),
            str(constraint.name),
        ) in KNOWN_CHECK_LOCATIONS
    if diff[0] == "add_check":
        return (str(diff[1]), str(diff[2])) in KNOWN_CHECK_LOCATIONS
    if diff[0] == "modify_check":
        return tuple(str(item) for item in diff[1:]) in KNOWN_MODIFIED_CHECKS
    return False


def _normalise_check_sql(sqltext: Any) -> str:
    """Normalise harmless reflection whitespace while retaining SQL semantics."""

    return " ".join(str(sqltext).lower().split())


def _check_constraint_diffs(connection: sa.Connection) -> list[tuple[Any, ...]]:
    """Compare checks explicitly because Alembic does not diff SQLite CHECK clauses."""

    schema = inspect(connection)
    actual_tables = set(schema.get_table_names())
    diffs: list[tuple[Any, ...]] = []
    for table_name, table in Base.metadata.tables.items():
        # Missing tables are already reported by Alembic as ``add_table``.
        if table_name not in actual_tables:
            continue
        expected = {
            str(constraint.name): _normalise_check_sql(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, sa.CheckConstraint)
        }
        actual = {
            str(constraint["name"]): _normalise_check_sql(constraint["sqltext"])
            for constraint in schema.get_check_constraints(table_name)
        }
        for name in sorted(expected.keys() - actual.keys()):
            diffs.append(("add_check", table_name, name))
        for name in sorted(actual.keys() - expected.keys()):
            diffs.append(("remove_check", table_name, name))
        for name in sorted(expected.keys() & actual.keys()):
            if expected[name] != actual[name]:
                diffs.append(
                    (
                        "modify_check",
                        table_name,
                        name,
                        actual[name],
                        expected[name],
                    )
                )
    return diffs


def _normalise_index_where(
    where: Any,
    *,
    table_name: str,
    dialect: sa.engine.Dialect,
) -> str | None:
    if where is None:
        return None
    if hasattr(where, "compile"):
        where = where.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    normalised = _normalise_check_sql(where)
    # Reflected SQLite predicates omit the table qualification that SQLAlchemy
    # includes when compiling ORM expressions.
    return normalised.replace(f'"{table_name}".', "").replace(f"{table_name}.", "")


def _index_diffs(connection: sa.Connection) -> list[tuple[Any, ...]]:
    """Supplement Alembic's comparison with SQLite partial-index predicates."""

    schema = inspect(connection)
    actual_tables = set(schema.get_table_names())
    diffs: list[tuple[Any, ...]] = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in actual_tables:
            continue
        expected = {
            str(index.name): (
                bool(index.unique),
                tuple(str(expression.name) for expression in index.expressions),
                _normalise_index_where(
                    index.dialect_options["sqlite"].get("where"),
                    table_name=table_name,
                    dialect=connection.dialect,
                ),
            )
            for index in table.indexes
        }
        actual = {
            str(index["name"]): (
                bool(index["unique"]),
                tuple(str(column) for column in index["column_names"]),
                _normalise_index_where(
                    index.get("dialect_options", {}).get("sqlite_where"),
                    table_name=table_name,
                    dialect=connection.dialect,
                ),
            )
            for index in schema.get_indexes(table_name)
        }
        for name in sorted(expected.keys() - actual.keys()):
            diffs.append(("add_index_signature", table_name, name, expected[name]))
        for name in sorted(actual.keys() - expected.keys()):
            diffs.append(("remove_index_signature", table_name, name, actual[name]))
        for name in sorted(expected.keys() & actual.keys()):
            if expected[name] != actual[name]:
                diffs.append(
                    (
                        "modify_index_signature",
                        table_name,
                        name,
                        actual[name],
                        expected[name],
                    )
                )
    return diffs


def _schema_diffs(connection: sa.Connection) -> list[tuple[Any, ...]]:
    context = MigrationContext.configure(
        connection,
        opts={"compare_type": True, "compare_server_default": True},
    )
    return (
        _flatten_diffs(compare_metadata(context, Base.metadata))
        + _check_constraint_diffs(connection)
        + _index_diffs(connection)
    )


def _apply_known_legacy_upgrade(connection: sa.Connection) -> None:
    schema = inspect(connection)
    operations = Operations(MigrationContext.configure(connection))

    completed_columns = {column["name"] for column in schema.get_columns("completed_sessions")}
    if "ai_analysis" not in completed_columns:
        operations.add_column(
            "completed_sessions",
            sa.Column("ai_analysis", sa.JSON(), nullable=True),
        )

    completed_checks = {
        row.get("name"): _normalise_check_sql(row.get("sqltext"))
        for row in inspect(connection).get_check_constraints("completed_sessions")
    }
    if completed_checks.get("ck_session_rpe") == ("rpe is null or (rpe >= 0 and rpe <= 10)"):
        with operations.batch_alter_table("completed_sessions", recreate="always") as batch:
            batch.drop_constraint("ck_session_rpe", type_="check")
            batch.create_check_constraint(
                "ck_session_rpe",
                "rpe IS NULL OR (rpe >= 1 AND rpe <= 10)",
            )

    for table in ("running_fitness_estimates", "threshold_estimates"):
        columns = {column["name"] for column in inspect(connection).get_columns(table)}
        if "is_demo" not in columns:
            operations.add_column(
                table,
                sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
            # SQLite needs a default to populate existing rows when adding a NOT NULL
            # column. Rebuild immediately afterwards so the adopted schema exactly
            # matches the ORM (which intentionally has no server-side default).
            with operations.batch_alter_table(table, recreate="always") as batch:
                batch.alter_column(
                    "is_demo",
                    existing_type=sa.Boolean(),
                    nullable=False,
                    server_default=None,
                )

    planned_checks = {
        row.get("name") for row in inspect(connection).get_check_constraints("planned_sessions")
    }
    missing_planned = KNOWN_CHECKS.intersection(
        {
            "ck_plan_target_rpe_min",
            "ck_plan_target_rpe_max",
            "ck_plan_target_rpe_range",
        }
    ).difference(planned_checks)
    if missing_planned:
        with operations.batch_alter_table("planned_sessions", recreate="always") as batch:
            if "ck_plan_target_rpe_min" in missing_planned:
                batch.create_check_constraint(
                    "ck_plan_target_rpe_min",
                    "target_rpe_min IS NULL OR (target_rpe_min >= 1 AND target_rpe_min <= 10)",
                )
            if "ck_plan_target_rpe_max" in missing_planned:
                batch.create_check_constraint(
                    "ck_plan_target_rpe_max",
                    "target_rpe_max IS NULL OR (target_rpe_max >= 1 AND target_rpe_max <= 10)",
                )
            if "ck_plan_target_rpe_range" in missing_planned:
                batch.create_check_constraint(
                    "ck_plan_target_rpe_range",
                    "target_rpe_min IS NULL OR target_rpe_max IS NULL OR target_rpe_min <= target_rpe_max",
                )

    strength_checks = {
        row.get("name") for row in inspect(connection).get_check_constraints("strength_sets")
    }
    if "ck_strength_set_rpe" not in strength_checks:
        with operations.batch_alter_table("strength_sets", recreate="always") as batch:
            batch.create_check_constraint(
                "ck_strength_set_rpe",
                "rpe IS NULL OR (rpe >= 1 AND rpe <= 10)",
            )


def _validate_legacy_rows(connection: sa.Connection) -> None:
    """Refuse constraint adoption when existing evidence violates the new contract."""

    invalid_queries = {
        "completed_sessions.rpe": (
            "SELECT COUNT(*) FROM completed_sessions "
            "WHERE rpe IS NOT NULL AND (rpe < 1 OR rpe > 10)"
        ),
        "planned_sessions.target_rpe": (
            "SELECT COUNT(*) FROM planned_sessions WHERE "
            "(target_rpe_min IS NOT NULL AND (target_rpe_min < 1 OR target_rpe_min > 10)) "
            "OR (target_rpe_max IS NOT NULL AND (target_rpe_max < 1 OR target_rpe_max > 10)) "
            "OR (target_rpe_min IS NOT NULL AND target_rpe_max IS NOT NULL "
            "AND target_rpe_min > target_rpe_max)"
        ),
        "strength_sets.rpe": (
            "SELECT COUNT(*) FROM strength_sets WHERE rpe IS NOT NULL AND (rpe < 1 OR rpe > 10)"
        ),
    }
    invalid: dict[str, int] = {}
    for field, query in invalid_queries.items():
        count = int(connection.exec_driver_sql(query).scalar_one())
        if count:
            invalid[field] = count
    if invalid:
        details = ", ".join(f"{field}: {count} row(s)" for field, count in invalid.items())
        raise LegacySchemaError(
            "The recognised legacy schema contains values that cannot be preserved under "
            f"the current RPE constraints ({details}). No migration or stamp was written."
        )


def bootstrap_unversioned_database(
    target_engine: Engine = engine,
    *,
    alembic_ini: Path | None = None,
) -> Path | None:
    """Stamp a recognised unversioned schema and return its backup path.

    Empty or already-versioned databases are left untouched.  Unknown drift is
    rejected before a stamp so Alembic never pretends an incompatible schema is
    current.
    """

    with target_engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        application_tables = tables.difference({"alembic_version"})
        if not application_tables:
            return None
        if "alembic_version" in tables:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).scalar_one_or_none()
            if revision:
                return None
        if connection.dialect.name != "sqlite" or _database_path(target_engine) is None:
            raise LegacySchemaError(
                "Automatic adoption is restricted to file-backed SQLite databases because "
                "a verified pre-migration backup is required. No stamp was written."
            )

        diffs = _schema_diffs(connection)
        unknown = [diff for diff in diffs if not _known_legacy_diff(diff)]
        if unknown:
            summary = "; ".join(str(diff) for diff in unknown[:5])
            raise LegacySchemaError(
                "The unversioned database is not a recognised Adaptive Training Coach schema. "
                f"No stamp was written. Unexpected differences: {summary}"
            )
        if diffs:
            _validate_legacy_rows(connection)

    backup_path = _backup_sqlite(target_engine)
    if backup_path is None:
        raise LegacySchemaError(
            "The required pre-migration SQLite backup could not be created. "
            "No migration or stamp was written."
        )
    try:
        with target_engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    if diffs:
                        _apply_known_legacy_upgrade(connection)
            finally:
                if connection.in_transaction():
                    connection.rollback()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
    except Exception as exc:
        raise LegacySchemaError(
            "The recognised legacy upgrade failed before a stamp was written. "
            f"The original backup is at {backup_path}."
        ) from exc

    try:
        with target_engine.connect() as connection:
            remaining = _schema_diffs(connection)
            if remaining:
                summary = "; ".join(str(diff) for diff in remaining[:5])
                raise LegacySchemaError(
                    "The legacy database upgrade did not converge to the current schema. "
                    f"The original backup is at {backup_path}. Remaining differences: {summary}"
                )
            config_path = (
                alembic_ini or Path(__file__).resolve().parents[1] / "alembic.ini"
            ).resolve()
            config = Config(str(config_path))
            script_location = Path(config.get_main_option("script_location"))
            if not script_location.is_absolute():
                config.set_main_option(
                    "script_location", str((config_path.parent / script_location).resolve())
                )
            context = MigrationContext.configure(connection)
            context.stamp(ScriptDirectory.from_config(config), "head")
            connection.commit()
    except LegacySchemaError:
        raise
    except Exception as exc:
        raise LegacySchemaError(
            "The legacy schema converged but Alembic could not stamp it. "
            f"The original backup is at {backup_path}."
        ) from exc
    return backup_path


def main() -> None:
    try:
        backup = bootstrap_unversioned_database()
    except LegacySchemaError as exc:
        raise SystemExit(str(exc)) from exc
    if backup:
        print(f"Adopted legacy database; recoverable backup: {backup}")


if __name__ == "__main__":
    main()
