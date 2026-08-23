from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app import models
from app.db import Base, build_engine
from app.enums import Confidence, EstimateType, PlanStatus, SessionPriority, Sport
from app.migration_bootstrap import (
    LegacySchemaError,
    _schema_diffs,
    bootstrap_unversioned_database,
)
from app.services.core import initialize_defaults

ALEMBIC_HEAD = "f3a6d2e91b74"


def _new_current_database(path: Path) -> sa.Engine:
    engine = build_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return engine


def _current_revision(engine: sa.Engine) -> str | None:
    if "alembic_version" not in inspect(engine).get_table_names():
        return None
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).scalar_one_or_none()


def _make_known_legacy_schema(engine: sa.Engine) -> None:
    """Recreate the exact additive pre-Alembic shape while preserving table rows."""

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        operations = Operations(MigrationContext.configure(connection))
        with connection.begin():
            with operations.batch_alter_table("completed_sessions", recreate="always") as batch:
                batch.drop_column("ai_analysis")
                batch.drop_constraint("ck_session_rpe", type_="check")
                batch.create_check_constraint(
                    "ck_session_rpe",
                    "rpe IS NULL OR (rpe >= 0 AND rpe <= 10)",
                )
            for table in ("running_fitness_estimates", "threshold_estimates"):
                with operations.batch_alter_table(table, recreate="always") as batch:
                    batch.drop_column("is_demo")
            with operations.batch_alter_table("planned_sessions", recreate="always") as batch:
                batch.drop_constraint("ck_plan_target_rpe_min", type_="check")
                batch.drop_constraint("ck_plan_target_rpe_max", type_="check")
                batch.drop_constraint("ck_plan_target_rpe_range", type_="check")
            with operations.batch_alter_table("strength_sets", recreate="always") as batch:
                batch.drop_constraint("ck_strength_set_rpe", type_="check")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def _seed_legacy_rows(engine: sa.Engine) -> dict[str, int]:
    with Session(engine) as session:
        initialize_defaults(session)
        plan = models.PlannedSession(
            athlete_id=1,
            session_date=date(2026, 8, 23),
            sport=Sport.RUNNING,
            workout_type="Easy",
            title="Legacy easy run",
            target_rpe_min=3,
            target_rpe_max=4,
            priority=SessionPriority.NORMAL,
            status=PlanStatus.PLANNED,
        )
        run = models.CompletedSession(
            athlete_id=1,
            planned_session_id=None,
            session_date=date(2026, 8, 22),
            duration_minutes=42,
            sport=Sport.RUNNING,
            workout_type="Easy",
            rpe=3,
            notes="preserve this run",
            ai_analysis=None,
        )
        strength = models.CompletedSession(
            athlete_id=1,
            planned_session_id=None,
            session_date=date(2026, 8, 21),
            duration_minutes=35,
            sport=Sport.STRENGTH,
            workout_type="Strength",
            rpe=6,
            notes="preserve this strength session",
            ai_analysis=None,
        )
        fitness = models.RunningFitnessEstimate(
            athlete_id=1,
            estimated_10k_seconds=2550,
            confidence=Confidence.MODERATE,
            source_event="Legacy 5K",
            source_date=date(2026, 8, 1),
            formula="legacy fixture",
            evidence="preserve this estimate",
        )
        threshold = models.ThresholdEstimate(
            athlete_id=1,
            estimate_type=EstimateType.LT1,
            pace_low_seconds_per_km=330,
            pace_high_seconds_per_km=345,
            confidence=Confidence.MODERATE,
            source="Legacy field test",
            measured_at=date(2026, 8, 2),
        )
        session.add_all([plan, run, strength, fitness, threshold])
        session.flush()
        strength_detail = models.StrengthSessionDetail(
            session_id=strength.id,
            workout_name="Legacy strength",
        )
        session.add(strength_detail)
        session.flush()
        strength_set = models.StrengthSet(
            strength_session_id=strength.id,
            exercise="Deadlift",
            set_count=3,
            reps=5,
            load_kg=100,
            rpe=7,
        )
        session.add(strength_set)
        session.commit()
        return {
            "plan": plan.id,
            "run": run.id,
            "strength": strength.id,
            "fitness": fitness.id,
            "threshold": threshold.id,
            "strength_set": strength_set.id,
        }


def test_current_create_all_database_is_backed_up_and_stamped(tmp_path: Path) -> None:
    database_path = tmp_path / "current.db"
    engine = _new_current_database(database_path)
    with Session(engine) as session:
        session.add(models.AppSetting(key="migration-marker", value={"kept": True}))
        session.commit()

    backup = bootstrap_unversioned_database(engine)

    assert backup is not None and backup.exists()
    assert _current_revision(engine) == ALEMBIC_HEAD
    with engine.connect() as connection:
        assert _schema_diffs(connection) == []
        assert connection.scalar(
            select(models.AppSetting.value).where(models.AppSetting.key == "migration-marker")
        ) == {"kept": True}
    with sqlite3.connect(backup) as connection:
        assert connection.execute(
            "SELECT value FROM app_settings WHERE key = 'migration-marker'"
        ).fetchone() == ('{"kept": true}',)
        assert "alembic_version" not in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def test_known_legacy_schema_upgrades_without_losing_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    engine = _new_current_database(database_path)
    ids = _seed_legacy_rows(engine)
    _make_known_legacy_schema(engine)

    with engine.connect() as connection:
        diffs = _schema_diffs(connection)
    assert diffs
    backup = bootstrap_unversioned_database(engine)

    assert backup is not None and backup.exists()
    assert _current_revision(engine) == ALEMBIC_HEAD
    schema = inspect(engine)
    assert "ai_analysis" in {column["name"] for column in schema.get_columns("completed_sessions")}
    for table in ("running_fitness_estimates", "threshold_estimates"):
        assert "is_demo" in {column["name"] for column in schema.get_columns(table)}
    assert {
        "ck_plan_target_rpe_min",
        "ck_plan_target_rpe_max",
        "ck_plan_target_rpe_range",
    }.issubset(
        {constraint["name"] for constraint in schema.get_check_constraints("planned_sessions")}
    )
    assert "ck_strength_set_rpe" in {
        constraint["name"] for constraint in schema.get_check_constraints("strength_sets")
    }
    completed_rpe_check = next(
        constraint
        for constraint in schema.get_check_constraints("completed_sessions")
        if constraint["name"] == "ck_session_rpe"
    )
    assert ">= 1" in completed_rpe_check["sqltext"]
    with engine.connect() as connection:
        assert _schema_diffs(connection) == []
        assert (
            connection.exec_driver_sql(
                "SELECT title FROM planned_sessions WHERE id = ?", (ids["plan"],)
            ).scalar_one()
            == "Legacy easy run"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT notes FROM completed_sessions WHERE id = ?", (ids["run"],)
            ).scalar_one()
            == "preserve this run"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT exercise FROM strength_sets WHERE id = ?", (ids["strength_set"],)
            ).scalar_one()
            == "Deadlift"
        )
        assert connection.exec_driver_sql(
            "SELECT evidence, is_demo FROM running_fitness_estimates WHERE id = ?",
            (ids["fitness"],),
        ).one() == ("preserve this estimate", 0)
        assert connection.exec_driver_sql(
            "SELECT source, is_demo FROM threshold_estimates WHERE id = ?",
            (ids["threshold"],),
        ).one() == ("Legacy field test", 0)
    with sqlite3.connect(backup) as connection:
        assert connection.execute(
            "SELECT notes FROM completed_sessions WHERE id = ?", (ids["run"],)
        ).fetchone() == ("preserve this run",)
        assert "ai_analysis" not in {
            row[1] for row in connection.execute("PRAGMA table_info(completed_sessions)")
        }
        completed_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'completed_sessions'"
        ).fetchone()[0]
        assert "rpe >= 0" in completed_sql


def test_unknown_unversioned_schema_refuses_without_backup_or_stamp(tmp_path: Path) -> None:
    database_path = tmp_path / "unknown.db"
    engine = _new_current_database(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE app_settings ADD COLUMN rogue_value TEXT")

    with pytest.raises(LegacySchemaError, match="No stamp was written"):
        bootstrap_unversioned_database(engine)

    assert _current_revision(engine) is None
    assert not list(tmp_path.glob("unknown.db.pre-alembic-*.bak"))
    assert "rogue_value" in {
        column["name"] for column in inspect(engine).get_columns("app_settings")
    }


def test_unknown_partial_index_predicate_refuses_without_stamp(tmp_path: Path) -> None:
    database_path = tmp_path / "unknown-index.db"
    engine = _new_current_database(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX uq_goals_one_current")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_goals_one_current ON goals (athlete_id) WHERE is_current IS 0"
        )

    with pytest.raises(LegacySchemaError, match="modify_index_signature"):
        bootstrap_unversioned_database(engine)

    assert _current_revision(engine) is None
    assert not list(tmp_path.glob("unknown-index.db.pre-alembic-*.bak"))


def test_legacy_zero_rpe_refuses_without_rewriting_evidence(tmp_path: Path) -> None:
    database_path = tmp_path / "invalid-rpe.db"
    engine = _new_current_database(database_path)
    ids = _seed_legacy_rows(engine)
    _make_known_legacy_schema(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE completed_sessions SET rpe = 0 WHERE id = ?", (ids["run"],)
        )

    with pytest.raises(LegacySchemaError, match="cannot be preserved"):
        bootstrap_unversioned_database(engine)

    assert _current_revision(engine) is None
    assert not list(tmp_path.glob("invalid-rpe.db.pre-alembic-*.bak"))
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT rpe FROM completed_sessions WHERE id = ?", (ids["run"],)
            ).scalar_one()
            == 0
        )
        assert "ai_analysis" not in {
            column["name"] for column in inspect(connection).get_columns("completed_sessions")
        }
