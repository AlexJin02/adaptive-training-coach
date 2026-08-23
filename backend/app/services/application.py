from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.enums import AdaptationDecision, NoteCategory
from app.services import core


def list_goals(db: Session) -> list[models.Goal]:
    return list(db.scalars(select(models.Goal).order_by(models.Goal.created_at.desc())))


def list_planned_sessions(
    db: Session, start: date | None = None, end: date | None = None
) -> list[models.PlannedSession]:
    statement = select(models.PlannedSession)
    if start is not None and end is not None:
        statement = statement.where(models.PlannedSession.session_date.between(start, end))
    return list(
        db.scalars(statement.order_by(models.PlannedSession.session_date, models.PlannedSession.id))
    )


def update_planned_session(
    db: Session, session_id: int, values: dict[str, Any]
) -> models.PlannedSession:
    item = db.get(models.PlannedSession, session_id)
    if item is None:
        raise LookupError("Planned session not found")
    return core.update_planned_session(
        db, item, values, values.get("revision_reason", "Manual edit")
    )


def skip_planned_session(
    db: Session, session_id: int
) -> tuple[models.PlannedSession, list[models.AdaptationEvent]]:
    item = db.get(models.PlannedSession, session_id)
    if item is None:
        raise LookupError("Planned session not found")
    return item, core.mark_planned_session_skipped(db, item)


def record_completed_session(db: Session, values: dict[str, Any]) -> models.CompletedSession:
    item = core.create_completed_session(db, values)
    core.update_running_fitness_estimate(db, item)
    core.update_threshold_estimates(db, item)
    core.persist_load_readiness_snapshot(db, source_key=f"session:{item.id}")
    core.analyse_completed_session_with_ai(db, item)
    core.create_adaptation_proposals(db)
    return item


def record_recovery_checkin(db: Session, values: dict[str, Any]) -> models.RecoveryCheckin:
    item = core.create_recovery_checkin(db, values)
    core.persist_load_readiness_snapshot(db, source_key=f"recovery:{item.id}")
    core.create_adaptation_proposals(db)
    return item


def create_running_estimate(db: Session, values: dict[str, Any]) -> models.RunningFitnessEstimate:
    item = models.RunningFitnessEstimate(athlete_id=1, **values)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_threshold_estimate(db: Session, values: dict[str, Any]) -> models.ThresholdEstimate:
    item = models.ThresholdEstimate(athlete_id=1, **values)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def today_context(
    db: Session,
) -> tuple[
    models.AthleteProfile,
    models.Goal | None,
    list[tuple[models.AdaptationEvent, str]],
]:
    profile = core.get_profile(db)
    goal = db.scalar(select(models.Goal).where(models.Goal.is_current.is_(True)).limit(1))
    adaptations = list(
        db.scalars(
            select(models.AdaptationEvent)
            .where(models.AdaptationEvent.decision == AdaptationDecision.PENDING)
            .order_by(models.AdaptationEvent.created_at.desc())
        )
    )
    return profile, goal, _adaptations_with_titles(db, adaptations)


def _adaptations_with_titles(
    db: Session, items: list[models.AdaptationEvent]
) -> list[tuple[models.AdaptationEvent, str]]:
    session_ids = {item.affected_session_id for item in items if item.affected_session_id}
    titles = {
        item.id: item.title
        for item in db.scalars(
            select(models.PlannedSession).where(models.PlannedSession.id.in_(session_ids))
        )
    }
    return [(item, titles.get(item.affected_session_id, "Planned session")) for item in items]


def list_adaptations(db: Session) -> list[tuple[models.AdaptationEvent, str]]:
    items = list(
        db.scalars(
            select(models.AdaptationEvent).order_by(models.AdaptationEvent.created_at.desc())
        )
    )
    return _adaptations_with_titles(db, items)


def propose_adaptations(db: Session) -> list[tuple[models.AdaptationEvent, str]]:
    return _adaptations_with_titles(db, core.create_adaptation_proposals(db))


def decide_adaptation(
    db: Session,
    adaptation_id: int,
    decision: str,
    proposed_plan: dict[str, Any] | None,
) -> tuple[models.AdaptationEvent, str]:
    item = db.get(models.AdaptationEvent, adaptation_id)
    if item is None:
        raise LookupError("Adaptation not found")
    item = core.decide_adaptation(db, item, decision, proposed_plan)
    return _adaptations_with_titles(db, [item])[0]


def list_tb2_benchmarks(db: Session) -> list[models.TB2Benchmark]:
    return list(
        db.scalars(select(models.TB2Benchmark).order_by(models.TB2Benchmark.benchmark_date))
    )


def create_tb2_benchmark(db: Session, values: dict[str, Any]) -> models.TB2Benchmark:
    item = models.TB2Benchmark(
        athlete_id=1,
        benchmark_date=values["date"],
        board=values["board"],
        angle_degrees=values["angle"],
        verified_grade=values["verified_grade"],
        estimated_grade=values.get("estimated_grade"),
        notes=values.get("notes") or "",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_route_benchmark(db: Session, values: dict[str, Any]) -> models.RouteBenchmark:
    item = models.RouteBenchmark(
        athlete_id=1,
        benchmark_date=values.get("last_updated") or date.today(),
        top_rope_verified_grade=values.get("top_rope_verified_grade"),
        lead_verified_grade=values.get("lead_verified_grade"),
        target_grade=values.get("target_grade"),
        notes=values.get("notes") or "",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_coaching_principle(
    db: Session, principle: str, source_note_id: int | None
) -> models.CoachingPrinciple:
    source_note = source_note_id and db.get(models.TrainingNote, source_note_id)
    item = models.CoachingPrinciple(
        source_note_id=source_note_id,
        category=source_note.primary_category if source_note else NoteCategory.RUNNING,
        principle=principle,
        athlete_approved=True,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_weekly_reviews(db: Session) -> list[models.WeeklyReview]:
    return list(
        db.scalars(select(models.WeeklyReview).order_by(models.WeeklyReview.week_start.desc()))
    )
