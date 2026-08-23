from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.ai import review_and_plan_month as ai_review_and_plan_month
from app.ai import review_and_plan_week as ai_review_and_plan_week
from app.ai.functions import NextMonthBlock, NextWeekPlan
from app.config import get_settings
from app.enums import PlanStatus, SessionPriority, Sport
from app.services import core, reporting, serializers


def _month_end(month_start: date) -> date:
    return date(
        month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1]
    )


def _next_month(month_start: date) -> date:
    return date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1)


def _memory(
    db: Session,
    *,
    key: str,
    level: str,
    content: dict[str, Any],
    period_start: date | None = None,
    period_end: date | None = None,
    source: str = "RULE_ENGINE",
) -> models.PlanningMemory:
    item = db.scalar(select(models.PlanningMemory).where(models.PlanningMemory.memory_key == key))
    if item is None:
        item = models.PlanningMemory(memory_key=key, level=level)
        db.add(item)
    item.period_start = period_start
    item.period_end = period_end
    item.content = content
    item.source = source
    db.flush()
    return item


def _long_term_context(db: Session) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile = core.get_profile(db)
    goals = list(db.scalars(select(models.Goal).order_by(models.Goal.created_at)))
    public_goals = [serializers.goal(item) for item in goals if item.is_current]
    summary = {
        "running_volume_goal_km_per_month": profile.long_term_monthly_distance_km,
        "half_marathon_goal_seconds": profile.half_marathon_goal_seconds,
        "marathon_goal_seconds": profile.marathon_goal_seconds,
        "tb2_goal": profile.tb2_long_term_goal,
        "outdoor_boulder_goal": profile.outdoor_boulder_goal,
        "route_goal": profile.route_long_term_goal,
    }
    _memory(db, key="LONG_TERM", level="LONG_TERM", content=summary)
    return public_goals, summary


def _load_and_readiness(db: Session) -> tuple[dict[str, Any], dict[str, Any]]:
    fatigue, readiness, _ = core.current_load_readiness(db)
    load = {
        "calculated_at": fatigue.calculated_at.isoformat(),
        "latent": {key.value: round(value, 3) for key, value in fatigue.latent.items()},
        "display": {key.value: round(value, 2) for key, value in fatigue.display.items()},
    }
    state = {
        "running_score": readiness.running_score,
        "running_label": readiness.running_label.value,
        "climbing_score": readiness.climbing_score,
        "climbing_label": readiness.climbing_label.value,
        "warnings": readiness.warnings,
    }
    return load, state


def _recent_recovery(db: Session, since: date) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(models.RecoveryCheckin)
            .where(
                models.RecoveryCheckin.recorded_at >= datetime.combine(since, datetime.min.time())
            )
            .order_by(models.RecoveryCheckin.recorded_at.desc())
            .limit(8)
        )
    )
    return [
        {
            "date": item.recorded_at.date().isoformat(),
            "sleep_hours": item.sleep_duration_hours,
            "sleep_quality": item.sleep_quality,
            "energy": item.energy,
            "stress": item.stress,
            "general_soreness": item.general_soreness,
            "area_soreness": item.area_soreness,
            "notes": item.notes or None,
        }
        for item in rows
    ]


def current_monthly_block(db: Session, day: date) -> dict[str, Any] | None:
    item = db.scalar(
        select(models.MonthlyTrainingBlock)
        .where(
            models.MonthlyTrainingBlock.month_start <= day,
            models.MonthlyTrainingBlock.month_end >= day,
            models.MonthlyTrainingBlock.status == "ACTIVE",
        )
        .order_by(models.MonthlyTrainingBlock.created_at.desc())
        .limit(1)
    )
    return monthly_block_public(item) if item else None


def _weekly_review_memory(item: models.WeeklyReview) -> dict[str, Any]:
    """Legacy weekly reviews are safe only after per-run feedback is removed."""

    return {
        "period": {"start": item.week_start.isoformat(), "end": item.week_end.isoformat()},
        "deterministic_summary": {
            "totals": {
                key: value
                for key, value in (item.summary or {}).items()
                if key != "running_subjective_feedback"
            },
            "compliance": item.compliance,
            "running": item.running,
            "climbing": item.climbing,
            "recovery": item.recovery,
        },
        "review": {
            "summary": item.narrative,
            "key_findings": item.key_findings,
        },
    }


def _previous_weekly_memories(db: Session, before: date, *, limit: int = 4) -> list[dict[str, Any]]:
    memories = list(
        db.scalars(
            select(models.PlanningMemory)
            .where(
                models.PlanningMemory.level == "WEEKLY",
                models.PlanningMemory.period_start < before,
            )
            .order_by(models.PlanningMemory.period_start.desc())
            .limit(limit)
        )
    )
    result = [item.content for item in memories]
    starts = {item.period_start for item in memories}
    if len(result) < limit:
        legacy = list(
            db.scalars(
                select(models.WeeklyReview)
                .where(models.WeeklyReview.week_start < before)
                .order_by(models.WeeklyReview.week_start.desc())
                .limit(limit * 2)
            )
        )
        result.extend(
            _weekly_review_memory(item) for item in legacy if item.week_start not in starts
        )
    return result[:limit]


def build_weekly_planning_context(db: Session, week_start: date) -> dict[str, Any]:
    week_end = week_start + timedelta(days=6)
    target_start = week_start + timedelta(days=7)
    target_end = target_start + timedelta(days=6)
    weekly = reporting.generate_weekly_review(db, week_start, include_ai=False)
    profile = core.get_profile(db)
    goals, long_term = _long_term_context(db)
    load, readiness = _load_and_readiness(db)
    upcoming = list(
        db.scalars(
            select(models.PlannedSession)
            .where(models.PlannedSession.session_date.between(target_start, target_end))
            .order_by(models.PlannedSession.session_date, models.PlannedSession.id)
        )
    )
    feedback = list(weekly.summary.get("running_subjective_feedback", []))
    return {
        "long_term_goals": goals,
        "long_term_summary": long_term,
        "athlete_state": serializers.athlete_profile(profile),
        "phases": {
            "running": profile.running_phase.value,
            "climbing": profile.climbing_phase.value,
        },
        "this_week_summary": {
            "period": {"start": week_start.isoformat(), "end": week_end.isoformat()},
            "totals": {
                key: value
                for key, value in weekly.summary.items()
                if key != "running_subjective_feedback"
            },
            "compliance": weekly.compliance,
            "running": weekly.running,
            "climbing": weekly.climbing,
            "recovery": weekly.recovery,
        },
        "previous_weekly_summaries": _previous_weekly_memories(db, week_start),
        "current_monthly_block": current_monthly_block(db, week_end),
        "load": load,
        "readiness": readiness,
        "recent_recovery": _recent_recovery(db, week_start - timedelta(days=7)),
        "upcoming_availability": [serializers.planned_session(item) for item in upcoming],
        "locked_sessions": [
            serializers.planned_session(item) for item in upcoming if item.is_locked
        ],
        "running_subjective_feedback": feedback,
    }


def review_and_plan_week(db: Session, week_start: date) -> models.PlanningProposal:
    context = build_weekly_planning_context(db, week_start)
    output = ai_review_and_plan_week(context)
    week_end = week_start + timedelta(days=6)
    target_start = week_start + timedelta(days=7)
    target_end = target_start + timedelta(days=6)
    proposed = output.next_week.model_dump(mode="json")
    for row in proposed["sessions"]:
        session_date = date.fromisoformat(row["date"])
        if not target_start <= session_date <= target_end:
            raise ValueError("AI proposed a session outside the next-week planning window")
    proposal = models.PlanningProposal(
        cadence="WEEKLY",
        period_start=week_start,
        period_end=week_end,
        target_start=target_start,
        target_end=target_end,
        deterministic_summary=context["this_week_summary"],
        context_snapshot=context,
        review=output.review.model_dump(mode="json"),
        proposed_plan=proposed,
        status="PREVIEW",
        source="AI",
        model_name=get_settings().openai_planner_model,
    )
    db.add(proposal)
    memory_content = {
        "period": context["this_week_summary"]["period"],
        "deterministic_summary": context["this_week_summary"],
        "review": proposal.review,
        "subjective_patterns": proposal.review.get("key_findings", []),
    }
    _memory(
        db,
        key=f"WEEKLY:{week_start.isoformat()}",
        level="WEEKLY",
        period_start=week_start,
        period_end=week_end,
        content=memory_content,
        source="AI",
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def _monthly_deterministic_summary(db: Session, month_start: date) -> dict[str, Any]:
    month_end = _month_end(month_start)
    sessions = [
        item
        for item in core.list_completed_sessions(db)
        if month_start <= item.session_date <= month_end
    ]
    running = [item for item in sessions if item.sport == Sport.RUNNING]
    climbing = [item for item in sessions if item.sport == Sport.CLIMBING]
    return {
        "period": {"start": month_start.isoformat(), "end": month_end.isoformat()},
        "total_training_minutes": round(sum(item.duration_minutes for item in sessions), 1),
        "running_distance_km": round(
            sum(item.running.distance_km or 0 for item in running if item.running), 2
        ),
        "running_sessions": len(running),
        "climbing_minutes": round(sum(item.duration_minutes for item in climbing), 1),
        "climbing_sessions": len(climbing),
        "strength_sessions": sum(item.sport == Sport.STRENGTH for item in sessions),
        "total_srpe_load": round(sum(item.srpe_load or 0 for item in sessions), 1),
    }


def _monthly_weekly_memories(
    db: Session, month_start: date, month_end: date
) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(models.PlanningMemory)
            .where(
                models.PlanningMemory.level == "WEEKLY",
                models.PlanningMemory.period_end >= month_start,
                models.PlanningMemory.period_start <= month_end,
            )
            .order_by(models.PlanningMemory.period_start)
        )
    )
    result = [item.content for item in rows]
    starts = {item.period_start for item in rows}
    legacy = list(
        db.scalars(
            select(models.WeeklyReview)
            .where(
                models.WeeklyReview.week_end >= month_start,
                models.WeeklyReview.week_start <= month_end,
            )
            .order_by(models.WeeklyReview.week_start)
        )
    )
    result.extend(_weekly_review_memory(item) for item in legacy if item.week_start not in starts)
    # These memories contain only weekly aggregates and findings, never per-run transcripts.
    return result


def build_monthly_planning_context(db: Session, month_start: date) -> dict[str, Any]:
    month_end = _month_end(month_start)
    target_start = _next_month(month_start)
    target_end = _month_end(target_start)
    profile = core.get_profile(db)
    goals, long_term = _long_term_context(db)
    load, readiness = _load_and_readiness(db)
    current = _monthly_deterministic_summary(db, month_start)
    previous = list(
        db.scalars(
            select(models.PlanningMemory)
            .where(
                models.PlanningMemory.level == "MONTHLY",
                models.PlanningMemory.period_start < month_start,
            )
            .order_by(models.PlanningMemory.period_start.desc())
            .limit(3)
        )
    )
    future = list(
        db.scalars(
            select(models.PlannedSession)
            .where(models.PlannedSession.session_date.between(target_start, target_end))
            .order_by(models.PlannedSession.session_date, models.PlannedSession.id)
        )
    )
    trends = reporting.recent_four_week_trends(db, month_end)
    estimates = list(
        db.scalars(
            select(models.RunningFitnessEstimate)
            .where(
                models.RunningFitnessEstimate.created_at
                <= datetime.combine(month_end, datetime.max.time())
            )
            .order_by(models.RunningFitnessEstimate.created_at.desc())
            .limit(4)
        )
    )
    tb2 = list(
        db.scalars(
            select(models.TB2Benchmark)
            .where(models.TB2Benchmark.benchmark_date <= month_end)
            .order_by(models.TB2Benchmark.benchmark_date.desc())
            .limit(4)
        )
    )
    return {
        "long_term_goals": goals,
        "long_term_summary": long_term,
        "athlete_state": serializers.athlete_profile(profile),
        "phases": {
            "running": profile.running_phase.value,
            "climbing": profile.climbing_phase.value,
        },
        "current_month_summary": current,
        "previous_monthly_summaries": [item.content for item in previous],
        "recent_weekly_summaries": _monthly_weekly_memories(db, month_start, month_end),
        "running_volume_progression": trends.get("running", {}),
        "running_performance_progression": {
            "estimated_10k": [
                {
                    "created_at": item.created_at.isoformat(),
                    "seconds": item.estimated_10k_seconds,
                    "confidence": item.confidence.value,
                }
                for item in reversed(estimates)
            ]
        },
        "climbing_benchmark_progression": {
            "tb2": [serializers.tb2(item) for item in reversed(tb2)]
        },
        "readiness_fatigue_trend": {"load": load, "readiness": readiness},
        "known_future_constraints": [serializers.planned_session(item) for item in future],
        "locked_events": [serializers.planned_session(item) for item in future if item.is_locked],
    }


def review_and_plan_month(db: Session, month_start: date) -> models.PlanningProposal:
    if month_start.day != 1:
        raise ValueError("month_start must be the first day of a calendar month")
    context = build_monthly_planning_context(db, month_start)
    output = ai_review_and_plan_month(context)
    month_end = _month_end(month_start)
    target_start = _next_month(month_start)
    target_end = _month_end(target_start)
    proposal = models.PlanningProposal(
        cadence="MONTHLY",
        period_start=month_start,
        period_end=month_end,
        target_start=target_start,
        target_end=target_end,
        deterministic_summary=context["current_month_summary"],
        context_snapshot=context,
        review=output.review.model_dump(mode="json"),
        proposed_plan=output.next_month_block.model_dump(mode="json"),
        status="PREVIEW",
        source="AI",
        model_name=get_settings().openai_planner_model,
    )
    db.add(proposal)
    _memory(
        db,
        key=f"MONTHLY:{month_start.isoformat()}",
        level="MONTHLY",
        period_start=month_start,
        period_end=month_end,
        content={
            "period": context["current_month_summary"]["period"],
            "deterministic_summary": context["current_month_summary"],
            "review": proposal.review,
        },
        source="AI",
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def list_proposals(db: Session, cadence: str | None = None) -> list[models.PlanningProposal]:
    statement = select(models.PlanningProposal)
    if cadence:
        statement = statement.where(models.PlanningProposal.cadence == cadence.upper())
    return list(db.scalars(statement.order_by(models.PlanningProposal.created_at.desc())))


def edit_proposal(
    db: Session, proposal_id: int, proposed_plan: dict[str, Any]
) -> models.PlanningProposal:
    item = db.get(models.PlanningProposal, proposal_id)
    if item is None:
        raise LookupError("Planning proposal not found")
    if item.status != "PREVIEW":
        raise ValueError("Only a preview can be edited")
    validated = (
        NextWeekPlan.model_validate(proposed_plan)
        if item.cadence == "WEEKLY"
        else NextMonthBlock.model_validate(proposed_plan)
    )
    item.proposed_plan = validated.model_dump(mode="json")
    db.commit()
    db.refresh(item)
    return item


def cancel_proposal(db: Session, proposal_id: int) -> models.PlanningProposal:
    item = db.get(models.PlanningProposal, proposal_id)
    if item is None:
        raise LookupError("Planning proposal not found")
    if item.status == "APPROVED":
        raise ValueError("An approved proposal cannot be cancelled")
    item.status = "CANCELLED"
    db.commit()
    db.refresh(item)
    return item


def _approve_weekly(db: Session, item: models.PlanningProposal) -> dict[str, Any]:
    rows = item.proposed_plan.get("sessions", [])
    existing = list(
        db.scalars(
            select(models.PlannedSession).where(
                models.PlannedSession.session_date.between(item.target_start, item.target_end)
            )
        )
    )
    existing_keys = {(row.session_date, row.sport, row.workout_type.lower()) for row in existing}
    created_ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    for values in rows:
        session_date = date.fromisoformat(values["date"])
        if not item.target_start <= session_date <= item.target_end:
            raise ValueError("A proposed session is outside the planning window")
        sport = Sport(values["workout_kind"])
        key = (session_date, sport, str(values["session_type"]).lower())
        if key in existing_keys:
            skipped.append(
                {
                    "date": values["date"],
                    "title": values["title"],
                    "reason": "existing session preserved",
                }
            )
            continue
        plan = models.PlannedSession(
            athlete_id=1,
            session_date=session_date,
            start_time=(
                datetime.strptime(values["start_time"], "%H:%M").time()
                if values.get("start_time")
                else None
            ),
            sport=sport,
            workout_type=values["session_type"],
            title=values["title"],
            description=values.get("description") or "",
            planned_duration_minutes=values.get("planned_duration_minutes"),
            planned_distance_km=values.get("planned_distance_km"),
            target_rpe_min=values.get("target_rpe"),
            target_rpe_max=values.get("target_rpe"),
            priority=SessionPriority(values.get("priority") or "NORMAL"),
            status=PlanStatus.PLANNED,
            structured_blocks=values.get("structured_blocks") or [],
            is_locked=False,
        )
        db.add(plan)
        db.flush()
        db.add(
            models.PlannedSessionRevision(
                planned_session_id=plan.id,
                version=1,
                snapshot=serializers.planned_session(plan),
                reason=f"Approved weekly proposal {item.id}",
            )
        )
        created_ids.append(plan.id)
        existing_keys.add(key)
    return {"created_session_ids": created_ids, "preserved_existing": skipped}


def _approve_monthly(db: Session, item: models.PlanningProposal) -> dict[str, Any]:
    active = list(
        db.scalars(
            select(models.MonthlyTrainingBlock).where(
                models.MonthlyTrainingBlock.month_start == item.target_start,
                models.MonthlyTrainingBlock.status == "ACTIVE",
            )
        )
    )
    for previous in active:
        previous.status = "SUPERSEDED"
    block = models.MonthlyTrainingBlock(
        month_start=item.target_start,
        month_end=item.target_end,
        content=item.proposed_plan,
        source_proposal_id=item.id,
        status="ACTIVE",
    )
    db.add(block)
    db.flush()
    return {"monthly_block_id": block.id}


def approve_proposal(db: Session, proposal_id: int) -> models.PlanningProposal:
    item = db.get(models.PlanningProposal, proposal_id)
    if item is None:
        raise LookupError("Planning proposal not found")
    if item.status == "APPROVED":
        return item
    if item.status != "PREVIEW":
        raise ValueError("Only a preview can be approved")
    item.approval_result = (
        _approve_weekly(db, item) if item.cadence == "WEEKLY" else _approve_monthly(db, item)
    )
    item.status = "APPROVED"
    item.approved_at = datetime.now(UTC)
    db.commit()
    db.refresh(item)
    return item


def proposal_public(item: models.PlanningProposal) -> dict[str, Any]:
    return {
        "id": item.id,
        "cadence": item.cadence,
        "period_start": item.period_start.isoformat(),
        "period_end": item.period_end.isoformat(),
        "target_start": item.target_start.isoformat(),
        "target_end": item.target_end.isoformat(),
        "deterministic_summary": item.deterministic_summary,
        "review": item.review,
        "proposed_plan": item.proposed_plan,
        "status": item.status,
        "source": item.source,
        "model": item.model_name,
        "approval_result": item.approval_result,
        "created_at": item.created_at.isoformat(),
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
    }


def monthly_block_public(item: models.MonthlyTrainingBlock) -> dict[str, Any]:
    return {
        "id": item.id,
        "month_start": item.month_start.isoformat(),
        "month_end": item.month_end.isoformat(),
        "content": item.content,
        "status": item.status,
        "source_proposal_id": item.source_proposal_id,
    }
