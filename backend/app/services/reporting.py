from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.ai import AIUnavailableError
from app.ai import generate_weekly_review as generate_ai_weekly_review
from app.config import get_settings
from app.enums import PlanStatus, Sport
from app.services import core, serializers

RANGE_DAYS = {
    "4 weeks": 28,
    "4w": 28,
    "3 months": 92,
    "3m": 92,
    "6 months": 183,
    "6m": 183,
    "1 year": 365,
    "1y": 365,
}

PLAN_COMPARISON_FIELDS = (
    "date",
    "start_time",
    "workout_kind",
    "session_type",
    "title",
    "description",
    "planned_duration_minutes",
    "planned_distance_km",
    "target_rpe",
    "priority",
    "structured_blocks",
)


def _plan_was_modified(item: models.PlannedSession) -> bool:
    """Use append-only revisions so completion does not erase a modified outcome."""

    if item.status == PlanStatus.MODIFIED:
        return True
    revisions = sorted(item.revisions, key=lambda revision: revision.version)
    if len(revisions) < 2:
        return False
    original = revisions[0].snapshot or {}
    return any(
        any(
            (revision.snapshot or {}).get(field) != original.get(field)
            for field in PLAN_COMPARISON_FIELDS
        )
        for revision in revisions[1:]
    )


def recent_four_week_trends(db: Session, week_end: date) -> dict[str, Any]:
    """Return four comparable weekly buckets using evidence available by ``week_end``."""

    start = week_end - timedelta(days=27)
    sessions = [
        item for item in core.list_completed_sessions(db) if start <= item.session_date <= week_end
    ]
    buckets: list[dict[str, Any]] = []
    for index in range(4):
        bucket_start = start + timedelta(days=index * 7)
        bucket_end = bucket_start + timedelta(days=6)
        bucket_sessions = [
            item for item in sessions if bucket_start <= item.session_date <= bucket_end
        ]
        running_sessions = [item for item in bucket_sessions if item.sport == Sport.RUNNING]
        climbing_sessions = [item for item in bucket_sessions if item.sport == Sport.CLIMBING]
        buckets.append(
            {
                "week_start": bucket_start.isoformat(),
                "week_end": bucket_end.isoformat(),
                "running_distance_km": round(
                    sum(
                        item.running.distance_km or 0
                        for item in running_sessions
                        if item.running is not None
                    ),
                    2,
                ),
                "running_sessions": len(running_sessions),
                "climbing_minutes": round(
                    sum(item.duration_minutes for item in climbing_sessions), 1
                ),
                "climbing_sessions": len(climbing_sessions),
                "climbing_hard_attempts": sum(
                    item.climbing.hard_attempts or 0
                    for item in climbing_sessions
                    if item.climbing is not None
                ),
                "srpe_load": round(sum(item.srpe_load or 0 for item in bucket_sessions), 1),
                "base_stress": round(sum(item.base_stress or 0 for item in bucket_sessions), 2),
            }
        )
    return {
        "range": {"start": start.isoformat(), "end": week_end.isoformat()},
        "running": {
            "weekly_distance_km": [
                {"week_start": row["week_start"], "value": row["running_distance_km"]}
                for row in buckets
            ],
            "weekly_session_count": [
                {"week_start": row["week_start"], "value": row["running_sessions"]}
                for row in buckets
            ],
        },
        "climbing": {
            "weekly_minutes": [
                {"week_start": row["week_start"], "value": row["climbing_minutes"]}
                for row in buckets
            ],
            "weekly_session_count": [
                {"week_start": row["week_start"], "value": row["climbing_sessions"]}
                for row in buckets
            ],
            "weekly_hard_attempts": [
                {"week_start": row["week_start"], "value": row["climbing_hard_attempts"]}
                for row in buckets
            ],
        },
        "load": {
            "weekly_srpe": [
                {"week_start": row["week_start"], "value": row["srpe_load"]} for row in buckets
            ],
            "weekly_base_stress": [
                {"week_start": row["week_start"], "value": row["base_stress"]} for row in buckets
            ],
        },
    }


def progress_data(db: Session, range_name: str, today: date | None = None) -> dict[str, Any]:
    end = today or date.today()
    start = end - timedelta(days=RANGE_DAYS.get(range_name.lower(), 92) - 1)
    history_sessions = [
        item
        for item in core.list_completed_sessions(db)
        if start - timedelta(days=27) <= item.session_date <= end
    ]
    sessions = [item for item in history_sessions if start <= item.session_date <= end]
    monthly: dict[str, float] = defaultdict(float)
    daily: dict[date, float] = defaultdict(float)
    for item in history_sessions:
        if item.running and item.running.distance_km is not None:
            daily[item.session_date] += item.running.distance_km
            if item.session_date >= start:
                monthly[item.session_date.strftime("%Y-%m")] += item.running.distance_km
    monthly_series = [
        {"date": f"{month}-01", "value": round(value, 2), "label": month}
        for month, value in sorted(monthly.items())
    ]
    rolling_series: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        seven = sum(
            value for day, value in daily.items() if cursor - timedelta(days=6) <= day <= cursor
        )
        twenty_eight = sum(
            value for day, value in daily.items() if cursor - timedelta(days=27) <= day <= cursor
        )
        rolling_series.append(
            {
                "date": cursor.isoformat(),
                "value": round(seven, 2),
                "secondary": round(twenty_eight / 4, 2),
            }
        )
        cursor += timedelta(days=7)
    estimates = list(
        db.scalars(
            select(models.RunningFitnessEstimate)
            .where(
                models.RunningFitnessEstimate.source_date.between(start, end)
                | (
                    models.RunningFitnessEstimate.source_date.is_(None)
                    & (models.RunningFitnessEstimate.created_at >= start)
                )
            )
            .order_by(
                models.RunningFitnessEstimate.source_date,
                models.RunningFitnessEstimate.created_at,
            )
        )
    )
    lt2_rows = list(
        db.scalars(
            select(models.ThresholdEstimate)
            .where(
                models.ThresholdEstimate.estimate_type == "LT2",
                models.ThresholdEstimate.measured_at.between(start, end),
            )
            .order_by(models.ThresholdEstimate.measured_at)
        )
    )
    tb2_rows = list(
        db.scalars(
            select(models.TB2Benchmark)
            .where(models.TB2Benchmark.benchmark_date.between(start, end))
            .order_by(models.TB2Benchmark.benchmark_date)
        )
    )
    gym_rows = list(
        db.scalars(
            select(models.GymSet)
            .options(selectinload(models.GymSet.colours))
            .where(
                models.GymSet.start_date <= end,
                (models.GymSet.end_date.is_(None)) | (models.GymSet.end_date >= start),
            )
            .order_by(models.GymSet.start_date)
        )
    )
    comparable_easy = [
        item
        for item in sessions
        if item.sport == Sport.RUNNING
        and item.workout_type.lower() in {"easy", "recovery"}
        and item.running
        and item.running.average_hr is not None
        and item.running.average_pace_seconds_per_km is not None
    ]
    if comparable_easy:
        sorted_hr = sorted(item.running.average_hr for item in comparable_easy if item.running)
        median_hr = sorted_hr[len(sorted_hr) // 2]
        efficiency = [
            {
                "date": item.session_date.isoformat(),
                "value": item.running.average_pace_seconds_per_km,
                "secondary": item.running.average_hr,
                "label": f"Easy HR band {median_hr - 3}–{median_hr + 3} bpm",
            }
            for item in comparable_easy
            if item.running and abs(item.running.average_hr - median_hr) <= 3
        ]
    else:
        efficiency = []
    return {
        "running": {
            "monthly_mileage": monthly_series,
            "rolling_volume": rolling_series,
            "estimated_10k": [
                {
                    "date": (item.source_date or item.created_at.date()).isoformat(),
                    "value": item.estimated_10k_seconds,
                    "confidence": item.confidence.value,
                    "label": item.source_event,
                }
                for item in estimates
                if item.estimated_10k_seconds is not None
            ],
            "lt2": [
                {
                    "date": item.measured_at.isoformat(),
                    "value": item.pace_low_seconds_per_km,
                    "secondary": item.hr_low,
                    "confidence": item.confidence.value,
                    "label": item.source,
                }
                for item in lt2_rows
                if item.pace_low_seconds_per_km is not None
            ],
            "easy_efficiency": efficiency if len(efficiency) >= 3 else [],
            "easy_efficiency_warning": (
                "Pace is compared only within a narrow easy-HR band; weather, terrain and "
                "workout conditions may still differ."
                if len(efficiency) >= 3
                else "Not enough comparable easy-HR data."
            ),
        },
        "climbing": {
            "tb2_benchmarks": [serializers.tb2(item) for item in tb2_rows],
            "gym_sets": [serializers.gym_set(item) for item in gym_rows],
        },
    }


def build_running_subjective_feedback_summary(
    sessions: list[models.CompletedSession], *, max_chars: int = 240
) -> list[dict[str, Any]]:
    """Compact edited feedback for weekly decisions without another model call."""

    result: list[dict[str, Any]] = []
    for item in sorted(sessions, key=lambda row: (row.session_date, row.id)):
        if item.sport != Sport.RUNNING or not item.subjective_feedback_text:
            continue
        compact = " ".join(item.subjective_feedback_text.split())
        if len(compact) > max_chars:
            compact = compact[: max_chars - 1].rstrip() + "…"
        result.append(
            {
                "date": item.session_date.isoformat(),
                "session_type": item.workout_type,
                "feedback": compact,
                "source": item.subjective_feedback_source,
                "rpe": item.rpe,
            }
        )
    return result


def generate_weekly_review(
    db: Session, week_start: date, *, include_ai: bool = True
) -> models.WeeklyReview:
    week_end = week_start + timedelta(days=6)
    sessions = [
        item
        for item in core.list_completed_sessions(db)
        if week_start <= item.session_date <= week_end
    ]
    plans = list(
        db.scalars(
            select(models.PlannedSession)
            .options(selectinload(models.PlannedSession.revisions))
            .where(models.PlannedSession.session_date.between(week_start, week_end))
        )
    )
    training_plans = [
        item
        for item in plans
        if item.status not in {PlanStatus.REST, PlanStatus.MOVED, PlanStatus.REPLACED}
    ]
    running_distance = sum(
        item.running.distance_km or 0 for item in sessions if item.running is not None
    )
    climbing_minutes = sum(
        item.duration_minutes for item in sessions if item.sport == Sport.CLIMBING
    )
    strength_count = sum(item.sport == Sport.STRENGTH for item in sessions)
    trained_days = {item.session_date for item in sessions}
    compliance = {
        "planned": len(training_plans),
        "completed": sum(
            item.status == PlanStatus.COMPLETED and not _plan_was_modified(item)
            for item in training_plans
        ),
        "modified": sum(
            item.status != PlanStatus.SKIPPED and _plan_was_modified(item)
            for item in training_plans
        ),
        "skipped": sum(item.status == PlanStatus.SKIPPED for item in training_plans),
        "extra": sum(item.planned_session_id is None for item in sessions),
    }
    quality = [
        item.workout_type
        for item in sessions
        if item.sport == Sport.RUNNING
        and item.workout_type.lower() not in {"easy", "recovery", "long run"}
    ]
    hard_attempts = sum(
        item.climbing.hard_attempts or 0 for item in sessions if item.climbing is not None
    )
    summary = {
        "total_training_minutes": round(sum(item.duration_minutes for item in sessions), 1),
        "running_distance_km": round(running_distance, 2),
        "climbing_minutes": round(climbing_minutes, 1),
        "strength_sessions": strength_count,
        "rest_days": 7 - len(trained_days),
        "running_subjective_feedback": build_running_subjective_feedback_summary(sessions),
    }
    running = [f"Weekly mileage: {running_distance:.1f} km"]
    if quality:
        running.append(f"Quality sessions: {', '.join(quality)}")
    long_runs = [item for item in sessions if item.workout_type.lower() == "long run"]
    if long_runs:
        longest = max(long_runs, key=lambda item: item.running.distance_km if item.running else 0)
        running.append(
            f"Long run: {(longest.running.distance_km or 0):.1f} km, "
            f"RPE {longest.rpe if longest.rpe is not None else 'unknown'}"
        )
    paced_runs = [
        item for item in sessions if item.running and item.running.average_pace_seconds_per_km
    ]
    if paced_runs:
        running.append(
            f"Pace/HR evidence available for {len(paced_runs)} runs; compare like conditions only."
        )
    lt2 = db.scalar(
        select(models.ThresholdEstimate)
        .where(
            models.ThresholdEstimate.estimate_type == "LT2",
            models.ThresholdEstimate.measured_at <= week_end,
        )
        .order_by(models.ThresholdEstimate.measured_at.desc())
        .limit(1)
    )
    if lt2:
        running.append(f"Latest LT2 evidence: {lt2.source} ({lt2.confidence.value}).")
    climbing = [
        f"Climbing time: {climbing_minutes:.0f} min",
        f"Hard attempts: {hard_attempts}",
    ]
    hardest = [
        item.climbing.maximum_sent
        for item in sessions
        if item.climbing and item.climbing.maximum_sent
    ]
    if hardest:
        climbing.append(f"Hardest logged sends: {', '.join(sorted(set(hardest)))}")
    tb2 = db.scalar(
        select(models.TB2Benchmark)
        .where(models.TB2Benchmark.benchmark_date.between(week_start, week_end))
        .order_by(models.TB2Benchmark.benchmark_date.desc())
        .limit(1)
    )
    if tb2:
        climbing.append(f"TB2 benchmark at {tb2.angle_degrees}°: verified {tb2.verified_grade}.")
    gym = db.scalar(
        select(models.GymSet)
        .options(selectinload(models.GymSet.colours))
        .where(
            models.GymSet.start_date <= week_end,
            (models.GymSet.end_date.is_(None)) | (models.GymSet.end_date >= week_end),
        )
        .order_by(models.GymSet.start_date.desc())
        .limit(1)
    )
    if gym:
        hardest_colour = max(
            (row for row in gym.colours if row.sent_count > 0),
            key=lambda row: row.ordinal,
            default=None,
        )
        if hardest_colour:
            climbing.append(
                f"Gym set at week end hardest colour: {hardest_colour.colour} "
                f"({hardest_colour.sent_count} sends)."
            )
    checkins = list(
        db.scalars(
            select(models.RecoveryCheckin)
            .where(
                models.RecoveryCheckin.recorded_at >= week_start,
                models.RecoveryCheckin.recorded_at < week_end + timedelta(days=1),
            )
            .order_by(models.RecoveryCheckin.recorded_at)
        )
    )
    readiness_rows = list(
        db.scalars(
            select(models.ReadinessSnapshot)
            .where(
                models.ReadinessSnapshot.calculated_at >= week_start,
                models.ReadinessSnapshot.calculated_at < week_end + timedelta(days=1),
            )
            .order_by(models.ReadinessSnapshot.calculated_at)
        )
    )
    recovery = ["Review hydration and fueling alongside sleep and soreness evidence."]
    if checkins:
        sleep_values = [item.sleep_duration_hours for item in checkins if item.sleep_duration_hours]
        soreness_values = [
            item.general_soreness for item in checkins if item.general_soreness is not None
        ]
        if sleep_values:
            recovery.append(
                f"Average reported sleep: {sum(sleep_values) / len(sleep_values):.1f} h."
            )
        if soreness_values:
            recovery.append(f"Peak general soreness: {max(soreness_values):.1f}/10.")
    if readiness_rows:
        recovery.append(
            f"Readiness range: running {min(row.running_score for row in readiness_rows):.1f}–"
            f"{max(row.running_score for row in readiness_rows):.1f}; climbing "
            f"{min(row.climbing_score for row in readiness_rows):.1f}–"
            f"{max(row.climbing_score for row in readiness_rows):.1f}."
        )
    findings = [
        f"Completed {len(sessions)} sessions with {summary['rest_days']} rest days.",
        "Recommendations are planning guidance, not medical diagnosis.",
    ]
    next_week = [
        "Keep hard sessions separated when the same fatigue domain remains high.",
        "Prioritise sleep and adequate fueling around quality work.",
    ]
    existing = db.scalar(
        select(models.WeeklyReview).where(models.WeeklyReview.week_start == week_start)
    )
    if existing is None:
        existing = models.WeeklyReview(week_start=week_start, week_end=week_end)
        db.add(existing)
    source = "RULE_ENGINE"
    narrative = " ".join(findings)
    if include_ai and get_settings().openai_api_key:
        profile = core.get_profile(db)
        goals = list(db.scalars(select(models.Goal).where(models.Goal.is_current.is_(True))))
        previous = db.scalar(
            select(models.WeeklyReview)
            .where(models.WeeklyReview.week_start < week_start)
            .order_by(models.WeeklyReview.week_start.desc())
            .limit(1)
        )
        try:
            ai_review = generate_ai_weekly_review(
                {
                    "goals": [serializers.goal(item) for item in goals],
                    "phases": {
                        "running": profile.running_phase.value,
                        "climbing": profile.climbing_phase.value,
                    },
                    "planned_week": [serializers.planned_session(item) for item in plans],
                    "completed_week": [serializers.completed_session(item) for item in sessions],
                    "recent_four_week_trends": recent_four_week_trends(db, week_end),
                    "recovery": recovery,
                    "previous_review": weekly_review_public(previous) if previous else None,
                }
            )
            running = ai_review.running or running
            climbing = ai_review.climbing or climbing
            recovery = ai_review.recovery or recovery
            findings = ai_review.key_findings or findings
            next_week = ai_review.next_week or next_week
            narrative = " ".join(ai_review.summary)
            source = "AI"
        except AIUnavailableError:
            pass
    existing.summary = summary
    existing.compliance = compliance
    existing.running = running
    existing.climbing = climbing
    existing.recovery = recovery
    existing.key_findings = findings
    existing.next_week = next_week
    existing.narrative = narrative
    existing.source = source
    db.commit()
    db.refresh(existing)
    return existing


def weekly_review_public(item: models.WeeklyReview) -> dict[str, Any]:
    return {
        "id": item.id,
        "week_start": item.week_start.isoformat(),
        "status": "GENERATED",
        "summary": item.summary,
        "compliance": item.compliance,
        "running": item.running,
        "climbing": item.climbing,
        "recovery": item.recovery,
        "key_findings": item.key_findings,
        "next_week": item.next_week,
        "source": item.source,
    }
