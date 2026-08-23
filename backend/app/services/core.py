from __future__ import annotations

import json
from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import get_settings
from app.enums import (
    AdaptationDecision,
    AdaptationSource,
    ClimbingPhase,
    Confidence,
    EstimateType,
    GoalType,
    PlanStatus,
    ReadinessLabel,
    RunningPhase,
    SessionPriority,
    Sport,
)
from app.services import serializers
from app.training_engine.adaptation import (
    AdaptationContext,
    CompletedEvidence,
    PlannedWorkout,
    assess_execution,
    comparable_execution,
    propose_adaptations,
)
from app.training_engine.config import (
    GYM_COLOUR_ORDINALS,
    HALF_LIFE_HOURS,
    NO_LATE_DETERIORATION_PACE_FRACTION,
    QUALITY_HR_STABILITY_MAX_BPM,
    READINESS_STABILITY_MAX_SPREAD,
    SUBJECTIVE_MAX_AGE_HOURS,
)
from app.training_engine.fatigue import StressEvent, calculate_fatigue
from app.training_engine.progression import decide_mileage_target
from app.training_engine.readiness import RecoveryInputs, calculate_readiness
from app.training_engine.session_load import calculate_session_load

ENGINE_DEFAULTS: dict[str, Any] = {
    "base_stress_divisor": 90,
    "base_stress_cap": 10,
    "hard_attempt_threshold": 10,
    "hard_attempt_increment": 0.015,
    "hard_attempt_cap": 1.25,
    "readiness_good_threshold": 7.5,
    "readiness_moderate_threshold": 5.0,
    "half_lives": {domain.value: hours for domain, hours in HALF_LIFE_HOURS.items()},
}


def engine_configuration(db: Session) -> dict[str, Any]:
    """Return the effective, fully populated engine configuration."""

    setting = db.get(models.AppSetting, "engine")
    stored = setting.value if setting and isinstance(setting.value, dict) else {}
    config = {**ENGINE_DEFAULTS, **stored}
    stored_half_lives = stored.get("half_lives")
    config["half_lives"] = {
        **ENGINE_DEFAULTS["half_lives"],
        **(stored_half_lives if isinstance(stored_half_lives, dict) else {}),
    }
    return config


def initialize_defaults(db: Session) -> models.AthleteProfile:
    profile = db.get(models.AthleteProfile, 1)
    if profile is None:
        profile = models.AthleteProfile(id=1)
        db.add(profile)
        db.flush()
    if db.scalar(select(func.count(models.Goal.id))) == 0:
        db.add(
            models.Goal(
                athlete_id=profile.id,
                goal_type=GoalType.HALF_MARATHON,
                description="Run a sub-1:30 half marathon",
                target_value="1:30:00",
                current_status="ACTIVE",
                is_current=True,
            )
        )
    db.commit()
    db.refresh(profile)
    return profile


def get_profile(db: Session) -> models.AthleteProfile:
    return db.get(models.AthleteProfile, 1) or initialize_defaults(db)


def update_profile(db: Session, values: dict[str, Any]) -> models.AthleteProfile:
    profile = get_profile(db)
    for public_name, value in values.items():
        if value is None:
            continue
        internal_name = serializers.PROFILE_INPUT_MAP.get(public_name, public_name)
        if internal_name == "running_phase":
            value = RunningPhase(value)
        elif internal_name == "climbing_phase":
            value = ClimbingPhase(value)
        if hasattr(profile, internal_name):
            if internal_name in {"running_phase", "climbing_phase"}:
                previous = getattr(profile, internal_name)
                if previous != value:
                    db.add(
                        models.AthleteStateHistory(
                            athlete_id=profile.id,
                            state_type=internal_name,
                            old_value=previous.value,
                            new_value=value.value,
                            source="MANUAL",
                        )
                    )
            setattr(profile, internal_name, value)
    db.commit()
    db.refresh(profile)
    return profile


def create_goal(db: Session, values: dict[str, Any]) -> models.Goal:
    is_current = bool(values.get("is_current", False))
    if is_current:
        db.execute(
            models.Goal.__table__.update()
            .where(models.Goal.athlete_id == 1)
            .values(is_current=False)
        )
    item = models.Goal(
        athlete_id=1,
        goal_type=GoalType(values["goal_type"]),
        description=values.get("description") or "",
        target_value=values.get("target_value"),
        target_date=values.get("target_date"),
        current_status=values.get("current_status") or "ACTIVE",
        notes=values.get("notes") or "",
        is_current=is_current,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def plan_snapshot(item: models.PlannedSession) -> dict[str, Any]:
    return serializers.planned_session(item)


def create_planned_session(db: Session, values: dict[str, Any]) -> models.PlannedSession:
    target_rpe = values.get("target_rpe")
    item = models.PlannedSession(
        athlete_id=1,
        session_date=values["date"],
        start_time=values.get("start_time"),
        sport=Sport(values["workout_kind"]),
        workout_type=values["session_type"],
        title=values.get("title") or values["session_type"],
        description=values.get("description") or "",
        planned_duration_minutes=values.get("planned_duration_minutes"),
        planned_distance_km=values.get("planned_distance_km"),
        target_rpe_min=target_rpe,
        target_rpe_max=target_rpe,
        priority=SessionPriority(values.get("priority") or SessionPriority.NORMAL),
        status=PlanStatus(values.get("status") or PlanStatus.PLANNED),
        structured_blocks=values.get("structured_blocks") or [],
        is_demo=bool(values.get("is_demo", False)),
    )
    db.add(item)
    db.flush()
    db.add(
        models.PlannedSessionRevision(
            planned_session_id=item.id,
            version=1,
            snapshot=plan_snapshot(item),
            reason="Initial plan",
        )
    )
    db.commit()
    db.refresh(item)
    return item


def update_planned_session(
    db: Session, item: models.PlannedSession, values: dict[str, Any], reason: str
) -> models.PlannedSession:
    item.version += 1
    mapping = {
        "date": "session_date",
        "workout_kind": "sport",
        "session_type": "workout_type",
        "target_rpe": "target_rpe_max",
    }
    for key, value in values.items():
        if key in {"revision_reason", "id"} or value is None:
            continue
        internal = mapping.get(key, key)
        if internal == "sport":
            value = Sport(value)
        elif internal == "status":
            value = PlanStatus(value)
        elif internal == "priority":
            value = SessionPriority(value)
        elif internal == "session_date" and isinstance(value, str):
            value = date.fromisoformat(value)
        elif internal == "start_time" and isinstance(value, str):
            value = time.fromisoformat(value)
        if hasattr(item, internal):
            setattr(item, internal, value)
            if key == "target_rpe":
                item.target_rpe_min = value
    db.flush()
    db.add(
        models.PlannedSessionRevision(
            planned_session_id=item.id,
            version=item.version,
            snapshot=plan_snapshot(item),
            reason=reason,
        )
    )
    db.commit()
    db.refresh(item)
    return item


def _parse_pace_seconds(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().replace("/km", "").split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except (TypeError, ValueError):
        return None


def create_completed_session(db: Session, values: dict[str, Any]) -> models.CompletedSession:
    sport = Sport(values["workout_kind"])
    duration = float(values["duration_minutes"])
    rpe = values.get("rpe")
    exercises = [str(row.get("exercise", "")) for row in values.get("strength_sets", [])]
    engine_config = engine_configuration(db)
    load = calculate_session_load(
        sport=sport,
        workout_type=values["session_type"],
        duration_minutes=duration,
        rpe=float(rpe) if rpe is not None else None,
        hard_attempts=values.get("hard_attempts"),
        exercises=exercises,
        stress_divisor=float(engine_config.get("base_stress_divisor", 90)),
        max_base_stress=float(engine_config.get("base_stress_cap", 10)),
        hard_attempt_threshold=int(engine_config.get("hard_attempt_threshold", 10)),
        hard_attempt_increment=float(engine_config.get("hard_attempt_increment", 0.015)),
        hard_attempt_cap=float(engine_config.get("hard_attempt_cap", 1.25)),
    )
    planned_id = int(values["planned_session_id"]) if values.get("planned_session_id") else None
    item = models.CompletedSession(
        athlete_id=1,
        planned_session_id=planned_id,
        session_date=values["date"],
        start_time=values.get("start_time"),
        duration_minutes=duration,
        sport=sport,
        workout_type=values["session_type"],
        rpe=float(rpe) if rpe is not None else None,
        notes=values.get("notes") or "",
        srpe_load=load.srpe_load,
        base_stress=load.base_stress,
        is_demo=bool(values.get("is_demo", False)),
    )
    db.add(item)
    db.flush()

    if sport == Sport.RUNNING:
        distance = values.get("distance_km")
        pace_seconds = _parse_pace_seconds(
            values.get("average_pace_seconds_per_km") or values.get("average_pace")
        )
        if pace_seconds is None and distance is not None and float(distance) > 0:
            pace_seconds = duration * 60.0 / float(distance)
        item.running = models.RunningSessionDetail(
            distance_km=float(distance) if distance is not None else None,
            average_pace_seconds_per_km=pace_seconds,
            average_hr=values.get("average_hr"),
            maximum_hr=values.get("max_hr"),
            elevation_m=values.get("elevation_m"),
            cadence=values.get("cadence"),
            power_watts=values.get("power_w"),
            splits=values.get("splits") or [],
            intervals=values.get("interval_blocks") or [],
        )
    elif sport == Sport.CLIMBING:
        climbing = models.ClimbingSessionDetail(
            gym_or_crag=values.get("gym_or_crag"),
            hard_attempts=values.get("hard_attempts"),
            maximum_attempted=values.get("max_attempted"),
            maximum_sent=values.get("max_sent"),
            grade_scale=values.get("grade_scale"),
        )
        for attempt in values.get("climbing_attempts") or []:
            outcome = str(attempt.get("outcome", "")).lower()
            climbing.attempts.append(
                models.ClimbingAttempt(
                    problem=attempt.get("problem"),
                    grade=attempt.get("grade"),
                    attempts=int(attempt.get("attempts") or 1),
                    sent=bool(attempt.get("sent") or outcome in {"send", "sent", "flash"}),
                    flash=bool(attempt.get("flash") or outcome == "flash"),
                    repeat=bool(attempt.get("repeat") or outcome == "repeat"),
                    project=bool(attempt.get("project") or outcome == "project"),
                    style_tags=attempt.get("styles") or attempt.get("style_tags") or [],
                )
            )
        item.climbing = climbing
    elif sport in {Sport.STRENGTH, Sport.CROSSFIT_CONDITIONING}:
        strength = models.StrengthSessionDetail(
            workout_name=values.get("workout_name"),
            rounds=values.get("rounds"),
            result_time_seconds=values.get("result_time_seconds"),
        )
        for row in values.get("strength_sets") or []:
            strength.sets.append(
                models.StrengthSet(
                    exercise=row.get("exercise") or "custom exercise",
                    set_count=row.get("sets") or row.get("set_count"),
                    reps=row.get("reps"),
                    load_kg=row.get("load") or row.get("load_kg"),
                    rpe=row.get("rpe"),
                    rir=row.get("rir"),
                    tags=row.get("tags") or [],
                )
            )
        item.strength = strength

    for row in load.domain_stresses:
        item.domain_stresses.append(
            models.SessionDomainStress(
                domain=row.domain,
                coefficient=row.coefficient,
                multiplier=row.multiplier,
                stress=row.stress,
                algorithm_version=load.algorithm_version,
            )
        )
    if planned_id:
        planned = db.get(models.PlannedSession, planned_id)
        if planned:
            planned.status = PlanStatus.COMPLETED
    db.commit()
    return get_completed_session(db, item.id)


def get_completed_session(db: Session, session_id: int) -> models.CompletedSession:
    query = (
        select(models.CompletedSession)
        .options(
            selectinload(models.CompletedSession.running),
            selectinload(models.CompletedSession.climbing).selectinload(
                models.ClimbingSessionDetail.attempts
            ),
            selectinload(models.CompletedSession.strength).selectinload(
                models.StrengthSessionDetail.sets
            ),
            selectinload(models.CompletedSession.domain_stresses),
        )
        .where(models.CompletedSession.id == session_id)
    )
    item = db.scalar(query)
    if item is None:
        raise LookupError("completed session not found")
    return item


def list_completed_sessions(db: Session) -> list[models.CompletedSession]:
    query = (
        select(models.CompletedSession)
        .options(
            selectinload(models.CompletedSession.running),
            selectinload(models.CompletedSession.climbing),
            selectinload(models.CompletedSession.strength),
            selectinload(models.CompletedSession.domain_stresses),
        )
        .order_by(models.CompletedSession.session_date.desc(), models.CompletedSession.id.desc())
    )
    return list(db.scalars(query))


def _session_event_time(item: models.CompletedSession, profile: models.AthleteProfile) -> datetime:
    local_tz = ZoneInfo(profile.timezone)
    if item.start_time is None:
        created = item.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        created_local = created.astimezone(local_tz)
        if created_local.date() == item.session_date:
            # A same-day quick log with no start time happened by save time, not at future noon.
            return created.astimezone(UTC)
    start = datetime.combine(item.session_date, item.start_time or time(12, 0), tzinfo=local_tz)
    return (start + timedelta(minutes=item.duration_minutes)).astimezone(UTC)


def current_load_readiness(
    db: Session, *, as_of: datetime | None = None
) -> tuple[Any, Any, models.RecoveryCheckin | None]:
    profile = get_profile(db)
    calculation_time = as_of or datetime.now(UTC)
    sessions = list_completed_sessions(db)
    events = [
        StressEvent(
            occurred_at=_session_event_time(item, profile),
            stresses={row.domain: row.stress for row in item.domain_stresses},
        )
        for item in sessions
        if item.domain_stresses
    ]
    engine_config = engine_configuration(db)
    configured_half_lives = engine_config["half_lives"]
    half_lives = {
        domain: float(configured_half_lives.get(domain.value, default))
        for domain, default in HALF_LIFE_HOURS.items()
    }
    fatigue = calculate_fatigue(events, as_of=calculation_time, half_lives=half_lives)
    latest = db.scalar(
        select(models.RecoveryCheckin)
        .where(models.RecoveryCheckin.recorded_at <= calculation_time)
        .order_by(models.RecoveryCheckin.recorded_at.desc())
        .limit(1)
    )
    if latest and latest.recorded_at.tzinfo is None:
        recorded_at = latest.recorded_at.replace(tzinfo=UTC)
    else:
        recorded_at = latest.recorded_at if latest else None
    if (
        recorded_at
        and (calculation_time - recorded_at).total_seconds() <= SUBJECTIVE_MAX_AGE_HOURS * 3600
    ):
        recovery = RecoveryInputs(
            sleep_duration_hours=latest.sleep_duration_hours,
            sleep_quality=latest.sleep_quality,
            energy=latest.energy,
            stress=latest.stress,
            general_soreness=latest.general_soreness,
            area_soreness=latest.area_soreness or {},
        )
    else:
        recovery = None
        latest = None
    readiness = calculate_readiness(
        fatigue.latent,
        recovery,
        good_threshold=float(engine_config.get("readiness_good_threshold", 7.5)),
        moderate_threshold=float(engine_config.get("readiness_moderate_threshold", 5.0)),
    )
    return fatigue, readiness, latest


def completed_execution_evidence(
    db: Session,
    item: models.CompletedSession,
    profile: models.AthleteProfile | None = None,
) -> CompletedEvidence:
    """Build the engine's explicit evidence contract from durable workout records."""

    athlete = profile or get_profile(db)
    planned = item.planned_session_id and db.get(models.PlannedSession, item.planned_session_id)
    started_at = _session_event_time(item, athlete) - timedelta(minutes=item.duration_minutes)
    _, pre_readiness, checkin = current_load_readiness(db, as_of=started_at)
    areas = checkin.area_soreness if checkin else {}
    persistent_soreness = bool(checkin and (checkin.general_soreness or 0) >= 6)
    execution_failed = bool(
        planned
        and (
            (
                planned.planned_duration_minutes
                and item.duration_minutes < 0.50 * planned.planned_duration_minutes
            )
            or (
                item.rpe is not None
                and planned.target_rpe_max is not None
                and item.rpe > planned.target_rpe_max + 2
            )
        )
    )
    return CompletedEvidence(
        id=item.id,
        session_date=item.session_date,
        sport=item.sport,
        workout_type=item.workout_type,
        duration_minutes=item.duration_minutes,
        rpe=item.rpe,
        planned_duration_minutes=planned.planned_duration_minutes if planned else None,
        target_rpe_max=planned.target_rpe_max if planned else None,
        pre_session_readiness=(
            pre_readiness.running_score
            if item.sport == Sport.RUNNING
            else pre_readiness.climbing_score
        ),
        persistent_soreness=persistent_soreness,
        area_soreness={key: float(value) for key, value in areas.items()},
        planned_structured_blocks=tuple(planned.structured_blocks if planned else ()),
        completed_interval_blocks=tuple(item.running.intervals if item.running else ()),
        splits=tuple(item.running.splits if item.running else ()),
        average_pace_seconds_per_km=(
            item.running.average_pace_seconds_per_km if item.running else None
        ),
        average_hr=item.running.average_hr if item.running else None,
        execution_failed=execution_failed,
    )


def persist_load_readiness_snapshot(
    db: Session,
    *,
    source_key: str,
    as_of: datetime | None = None,
) -> tuple[models.FatigueSnapshot, models.ReadinessSnapshot]:
    fatigue, readiness, _ = current_load_readiness(db, as_of=as_of)
    fatigue_snapshot = db.scalar(
        select(models.FatigueSnapshot).where(
            models.FatigueSnapshot.athlete_id == 1,
            models.FatigueSnapshot.source_key == source_key,
        )
    )
    if fatigue_snapshot is None:
        fatigue_snapshot = models.FatigueSnapshot(athlete_id=1, source_key=source_key)
        db.add(fatigue_snapshot)
    fatigue_snapshot.calculated_at = fatigue.calculated_at
    fatigue_snapshot.latent_by_domain = {
        domain.value: value for domain, value in fatigue.latent.items()
    }
    fatigue_snapshot.display_by_domain = {
        domain.value: value for domain, value in fatigue.display.items()
    }
    fatigue_snapshot.algorithm_version = "v1"

    readiness_snapshot = db.scalar(
        select(models.ReadinessSnapshot).where(
            models.ReadinessSnapshot.athlete_id == 1,
            models.ReadinessSnapshot.source_key == source_key,
        )
    )
    if readiness_snapshot is None:
        readiness_snapshot = models.ReadinessSnapshot(athlete_id=1, source_key=source_key)
        db.add(readiness_snapshot)
    readiness_snapshot.calculated_at = fatigue.calculated_at
    readiness_snapshot.running_score = readiness.running_score
    readiness_snapshot.running_label = readiness.running_label
    readiness_snapshot.climbing_score = readiness.climbing_score
    readiness_snapshot.climbing_label = readiness.climbing_label
    readiness_snapshot.components = {
        "running": readiness.running_components,
        "climbing": readiness.climbing_components,
        "warnings": list(readiness.warnings),
    }
    readiness_snapshot.subjective_delta = readiness.subjective_delta
    readiness_snapshot.algorithm_version = "v1"
    db.commit()
    db.refresh(fatigue_snapshot)
    db.refresh(readiness_snapshot)
    return fatigue_snapshot, readiness_snapshot


def update_running_fitness_estimate(
    db: Session, session: models.CompletedSession
) -> models.RunningFitnessEstimate | None:
    if session.sport != Sport.RUNNING or session.running is None:
        return None
    if session.workout_type.lower() not in {"race", "time trial"}:
        return None
    distance_km = session.running.distance_km
    if not distance_km or distance_km < 3 or distance_km > 50:
        return None
    source_seconds = session.duration_minutes * 60.0
    is_actual_10k = 9.95 <= distance_km <= 10.05
    estimated_seconds = (
        source_seconds if is_actual_10k else source_seconds * (10.0 / distance_km) ** 1.06
    )
    item = models.RunningFitnessEstimate(
        athlete_id=1,
        estimated_10k_seconds=estimated_seconds,
        confidence=Confidence.HIGH,
        source_event=f"{distance_km:g} km {session.workout_type}",
        source_date=session.session_date,
        formula=("ACTUAL_10K" if is_actual_10k else "Riegel: T2 = T1 × (D2 / D1)^1.06"),
        evidence=f"Completed session {session.id}: {source_seconds:.0f} seconds over {distance_km:g} km",
        is_demo=session.is_demo,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_threshold_estimates(
    db: Session, session: models.CompletedSession
) -> list[models.ThresholdEstimate]:
    if session.sport != Sport.RUNNING or session.running is None:
        return []
    created: list[models.ThresholdEstimate] = []
    pace = session.running.average_pace_seconds_per_km
    hr = session.running.average_hr
    if session.workout_type.lower() in {"threshold", "tempo", "cruise intervals"} and (
        pace is not None or hr is not None
    ):
        created.append(
            models.ThresholdEstimate(
                athlete_id=1,
                estimate_type=EstimateType.LT2,
                pace_low_seconds_per_km=pace,
                pace_high_seconds_per_km=pace,
                hr_low=hr,
                hr_high=hr,
                confidence=Confidence.MODERATE,
                source=f"Completed {session.workout_type} session (session {session.id})",
                measured_at=session.session_date,
                is_demo=session.is_demo,
            )
        )

    reference_date = (
        db.scalar(
            select(func.max(models.CompletedSession.session_date)).where(
                models.CompletedSession.sport == Sport.RUNNING
            )
        )
        or session.session_date
    )
    window_start = reference_date - timedelta(days=27)
    easy_rows = list(
        db.scalars(
            select(models.CompletedSession)
            .options(selectinload(models.CompletedSession.running))
            .where(
                models.CompletedSession.sport == Sport.RUNNING,
                models.CompletedSession.workout_type.in_(["Easy", "Recovery", "Steady"]),
                models.CompletedSession.session_date.between(window_start, reference_date),
                models.CompletedSession.rpe <= 4,
            )
        )
    )
    comparable = [
        row
        for row in easy_rows
        if row.running
        and row.running.average_pace_seconds_per_km is not None
        and row.running.average_hr is not None
    ]
    existing_lt1 = db.scalar(
        select(models.ThresholdEstimate).where(
            models.ThresholdEstimate.estimate_type == EstimateType.LT1,
            models.ThresholdEstimate.measured_at == reference_date,
        )
    )
    if len(comparable) >= 3 and existing_lt1 is None:
        paces = [row.running.average_pace_seconds_per_km for row in comparable if row.running]
        hrs = [row.running.average_hr for row in comparable if row.running]
        created.append(
            models.ThresholdEstimate(
                athlete_id=1,
                estimate_type=EstimateType.LT1,
                pace_low_seconds_per_km=min(paces),
                pace_high_seconds_per_km=max(paces),
                hr_low=min(hrs),
                hr_high=max(hrs),
                confidence=Confidence.MODERATE,
                source=f"Range from {len(comparable)} recent easy/steady runs at RPE <= 4",
                measured_at=reference_date,
                is_demo=all(row.is_demo for row in comparable),
            )
        )
    if created:
        db.add_all(created)
        db.commit()
        for item in created:
            db.refresh(item)
    return created


def create_recovery_checkin(db: Session, values: dict[str, Any]) -> models.RecoveryCheckin:
    recorded_at = values.get("recorded_at")
    if recorded_at is None and values.get("date"):
        profile = get_profile(db)
        recorded_at = datetime.combine(values["date"], time(8), tzinfo=ZoneInfo(profile.timezone))
    item = models.RecoveryCheckin(
        athlete_id=1,
        recorded_at=recorded_at or datetime.now(UTC),
        sleep_duration_hours=values.get("sleep_duration_hours"),
        sleep_quality=values.get("sleep_quality"),
        energy=values.get("energy"),
        motivation=values.get("motivation"),
        stress=values.get("stress"),
        general_soreness=values.get("general_soreness"),
        area_soreness=values.get("soreness") or values.get("area_soreness") or {},
        resting_hr=values.get("resting_hr"),
        hrv=values.get("hrv"),
        notes=values.get("notes") or "",
        is_demo=bool(values.get("is_demo", False)),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _month_bounds(day: date) -> tuple[date, date]:
    return day.replace(day=1), day.replace(day=monthrange(day.year, day.month)[1])


def _previous_month(day: date) -> tuple[date, date]:
    previous_last = day.replace(day=1) - timedelta(days=1)
    return _month_bounds(previous_last)


def _running_distance_between(db: Session, start: date, end: date) -> float:
    value = db.scalar(
        select(func.coalesce(func.sum(models.RunningSessionDetail.distance_km), 0.0))
        .join(models.CompletedSession)
        .where(models.CompletedSession.session_date.between(start, end))
    )
    return float(value or 0.0)


def _quality_session_performance_stable(
    db: Session,
    sessions: list[models.CompletedSession],
    profile: models.AthleteProfile,
) -> bool | None:
    quality = sorted(
        (
            item
            for item in sessions
            if item.workout_type.lower() not in {"easy", "recovery", "long run"}
            and item.planned_session_id is not None
        ),
        key=lambda item: (item.session_date, item.id),
    )
    evidence = [completed_execution_evidence(db, item, profile) for item in quality]
    for trigger_index in range(len(evidence) - 1, 0, -1):
        trigger = evidence[trigger_index]
        earlier = next(
            (
                candidate
                for candidate in reversed(evidence[:trigger_index])
                if comparable_execution(candidate, trigger)
            ),
            None,
        )
        if earlier is None:
            continue
        assessments = (assess_execution(earlier), assess_execution(trigger))
        if any(assessment.structured_evidence_required for assessment in assessments):
            execution_stable = all(assessment.strong for assessment in assessments)
        else:
            execution_stable = all(assessment.successful for assessment in assessments)
        readiness_values = (earlier.pre_session_readiness, trigger.pre_session_readiness)
        readiness_stable = bool(
            all(value is not None for value in readiness_values)
            and abs(float(readiness_values[0]) - float(readiness_values[1]))
            <= READINESS_STABILITY_MAX_SPREAD
        )
        if any(assessment.structured_evidence_required for assessment in assessments):
            performance_metrics_stable = True
        else:
            paces = (
                earlier.average_pace_seconds_per_km,
                trigger.average_pace_seconds_per_km,
            )
            hrs = (earlier.average_hr, trigger.average_hr)
            performance_metrics_stable = bool(
                all(value is not None for value in paces)
                and all(value is not None for value in hrs)
                and abs(float(paces[0]) - float(paces[1])) / min(float(paces[0]), float(paces[1]))
                <= NO_LATE_DETERIORATION_PACE_FRACTION
                and abs(int(hrs[0]) - int(hrs[1])) <= QUALITY_HR_STABILITY_MAX_BPM
            )
        return execution_stable and readiness_stable and performance_metrics_stable
    return None


def running_state(db: Session, today: date | None = None) -> dict[str, Any]:
    day = today or date.today()
    profile = get_profile(db)
    month_start, month_end = _month_bounds(day)
    previous_start, previous_end = _previous_month(day)
    recent_actual = db.scalar(
        select(models.RunningFitnessEstimate)
        .where(
            models.RunningFitnessEstimate.formula == "ACTUAL_10K",
            models.RunningFitnessEstimate.source_date >= day - timedelta(days=90),
        )
        .order_by(models.RunningFitnessEstimate.source_date.desc())
        .limit(1)
    )
    estimate = recent_actual or db.scalar(
        select(models.RunningFitnessEstimate)
        .order_by(
            models.RunningFitnessEstimate.source_date.desc().nullslast(),
            models.RunningFitnessEstimate.id.desc(),
        )
        .limit(1)
    )
    lt1 = db.scalar(
        select(models.ThresholdEstimate)
        .where(models.ThresholdEstimate.estimate_type == EstimateType.LT1)
        .order_by(models.ThresholdEstimate.measured_at.desc())
        .limit(1)
    )
    lt2 = db.scalar(
        select(models.ThresholdEstimate)
        .where(models.ThresholdEstimate.estimate_type == EstimateType.LT2)
        .order_by(models.ThresholdEstimate.measured_at.desc())
        .limit(1)
    )
    rolling_28 = _running_distance_between(db, day - timedelta(days=27), day)
    recent_start = day - timedelta(days=27)
    recent_sessions = [
        item
        for item in list_completed_sessions(db)
        if item.sport == Sport.RUNNING and recent_start <= item.session_date <= day
    ]
    recent_plans = list(
        db.scalars(
            select(models.PlannedSession).where(
                models.PlannedSession.sport == Sport.RUNNING,
                models.PlannedSession.session_date.between(recent_start, day),
                models.PlannedSession.status != PlanStatus.REST,
            )
        )
    )
    completed_plan_ids = {
        item.planned_session_id for item in recent_sessions if item.planned_session_id
    }
    completion_rate = (
        len(completed_plan_ids) / len(recent_plans)
        if recent_plans
        else (1.0 if recent_sessions else 0.0)
    )
    easy_rpes = [
        item.rpe
        for item in recent_sessions
        if item.workout_type.lower() in {"easy", "recovery"} and item.rpe is not None
    ]
    easy_rpe_stable = len(easy_rpes) >= 2 and max(easy_rpes) - min(easy_rpes) <= 2
    long_runs = [item for item in recent_sessions if item.workout_type.lower() == "long run"]
    long_run_tolerated = bool(long_runs) and all(
        item.rpe is not None and item.rpe <= 7 for item in long_runs
    )
    _, current_readiness, latest_checkin = current_load_readiness(db)
    areas = latest_checkin.area_soreness if latest_checkin else {}
    persistent_soreness = bool(
        (latest_checkin and (latest_checkin.general_soreness or 0) >= 6)
        or any(float(areas.get(area, 0)) >= 6 for area in ("hip", "knee", "calf", "ankle"))
    )
    quality_performance_stable = _quality_session_performance_stable(db, recent_sessions, profile)
    progression = decide_mileage_target(
        current_weekly_km=rolling_28 / 4.0,
        completion_rate=completion_rate,
        easy_rpe_stable=easy_rpe_stable,
        long_run_tolerated=long_run_tolerated,
        readiness_acceptable=current_readiness.running_label != ReadinessLabel.LOW,
        persistent_soreness=persistent_soreness,
        quality_session_performance_stable=quality_performance_stable,
    )
    recent_longest = max(
        (item.running.distance_km or 0 for item in recent_sessions if item.running), default=0.0
    )
    return {
        "current_month_km": _running_distance_between(db, month_start, month_end),
        "previous_month_km": _running_distance_between(db, previous_start, previous_end),
        "rolling_7d_km": _running_distance_between(db, day - timedelta(days=6), day),
        "rolling_28d_km": rolling_28,
        "rolling_28d_weekly_average_km": rolling_28 / 4.0,
        "estimated_10k": {
            "value": estimate.estimated_10k_seconds if estimate else None,
            "confidence": estimate.confidence.value if estimate else None,
            "source": estimate.source_event if estimate else "Not enough data",
            "source_date": estimate.source_date.isoformat()
            if estimate and estimate.source_date
            else None,
            "formula": estimate.formula if estimate else None,
            "evidence": [estimate.evidence] if estimate and estimate.evidence else [],
        },
        "lt1_pace_range": (
            [lt1.pace_low_seconds_per_km, lt1.pace_high_seconds_per_km] if lt1 else None
        ),
        "lt1_hr_range": [lt1.hr_low, lt1.hr_high] if lt1 else None,
        "lt1_confidence": lt1.confidence.value if lt1 else None,
        "lt1_source": lt1.source if lt1 else None,
        "lt2_pace_seconds_per_km": lt2.pace_low_seconds_per_km if lt2 else None,
        "lt2_hr": lt2.hr_low if lt2 else None,
        "lt2_confidence": lt2.confidence.value if lt2 else None,
        "lt2_source": lt2.source if lt2 else None,
        "lt2_updated_at": lt2.measured_at.isoformat() if lt2 else None,
        "phase": profile.running_phase.value,
        "current_capacity_km": rolling_28 / 4.0,
        "current_block_min_km": progression.target_min_km,
        "current_block_max_km": progression.target_max_km,
        "long_term_min_km": profile.stable_weekly_distance_min_km,
        "long_term_max_km": profile.stable_weekly_distance_max_km,
        "progression_decision": progression.action,
        "progression_evidence": [
            progression.reason,
            f"Recent plan completion: {completion_rate:.0%}",
            (
                "Comparable quality-session execution is stable"
                if quality_performance_stable
                else "Comparable quality-session evidence is missing or unstable"
            ),
            f"Recent longest run exposure: {recent_longest:.1f} km (soft guardrail)",
        ],
    }


def create_gym_set(db: Session, values: dict[str, Any]) -> models.GymSet:
    gym = values["gym"]
    start_date = values["start_date"]
    active = db.scalar(
        select(models.GymSet).where(
            models.GymSet.athlete_id == 1,
            models.GymSet.gym == gym,
            models.GymSet.is_active.is_(True),
        )
    )
    if active:
        active.is_active = False
        active.end_date = start_date - timedelta(days=1)
    item = models.GymSet(
        athlete_id=1,
        gym=gym,
        start_date=start_date,
        notes=values.get("notes") or "",
        is_active=True,
        is_demo=bool(values.get("is_demo", False)),
    )
    incoming = {row["colour"]: row for row in values.get("progress") or []}
    available = values.get("available_counts") or {}
    for colour, ordinal in GYM_COLOUR_ORDINALS.items():
        row = incoming.get(colour, {})
        sent_count, available_count = _validate_gym_counts(
            row.get("sent_count", 0), row.get("available_problem_count", available.get(colour))
        )
        item.colours.append(
            models.GymSetColourProgress(
                colour=colour,
                ordinal=ordinal,
                sent_count=sent_count,
                available_problem_count=available_count,
            )
        )
    db.add(item)
    db.commit()
    return get_gym_set(db, item.id)


def get_gym_set(db: Session, set_id: int) -> models.GymSet:
    item = db.scalar(
        select(models.GymSet)
        .options(selectinload(models.GymSet.colours))
        .where(models.GymSet.id == set_id)
    )
    if item is None:
        raise LookupError("gym set not found")
    return item


def _validate_gym_counts(sent: Any, available: Any) -> tuple[int, int | None]:
    sent_count = int(sent)
    available_count = int(available) if available is not None else None
    if sent_count < 0 or (available_count is not None and available_count < 0):
        raise ValueError("Gym progress counts cannot be negative")
    if available_count is not None and sent_count > available_count:
        raise ValueError("sent_count cannot exceed available_problem_count")
    return sent_count, available_count


def update_gym_progress(db: Session, set_id: int, values: dict[str, Any]) -> models.GymSet:
    item = get_gym_set(db, set_id)
    rows = values.get("progress") if isinstance(values, dict) else values
    if rows is None and "colour" in values:
        rows = [values]
    by_colour = {row.colour: row for row in item.colours}
    for payload in rows or []:
        row = by_colour.get(payload.get("colour"))
        if row:
            sent_count, available_count = _validate_gym_counts(
                payload.get("sent_count", row.sent_count),
                payload.get("available_problem_count", row.available_problem_count),
            )
            row.sent_count = sent_count
            row.available_problem_count = available_count
    db.commit()
    return get_gym_set(db, set_id)


def climbing_state(db: Session) -> dict[str, Any]:
    profile = get_profile(db)
    tb2_item = db.scalar(
        select(models.TB2Benchmark)
        .order_by(models.TB2Benchmark.benchmark_date.desc(), models.TB2Benchmark.id.desc())
        .limit(1)
    )
    gym = db.scalar(
        select(models.GymSet)
        .options(selectinload(models.GymSet.colours))
        .where(models.GymSet.is_active.is_(True))
        .order_by(models.GymSet.start_date.desc())
        .limit(1)
    )
    route = db.scalar(
        select(models.RouteBenchmark)
        .order_by(models.RouteBenchmark.benchmark_date.desc(), models.RouteBenchmark.id.desc())
        .limit(1)
    )
    return {
        "phase": profile.climbing_phase.value,
        "latest_tb2": serializers.tb2(tb2_item) if tb2_item else None,
        "current_gym_set": serializers.gym_set(gym) if gym else None,
        "route_benchmark": serializers.route_benchmark(route),
    }


def create_adaptation_proposals(db: Session) -> list[models.AdaptationEvent]:
    trigger = db.scalar(
        select(models.CompletedSession)
        .options(
            selectinload(models.CompletedSession.domain_stresses),
            selectinload(models.CompletedSession.running),
        )
        .order_by(models.CompletedSession.session_date.desc(), models.CompletedSession.id.desc())
        .limit(1)
    )
    if trigger is None:
        return []
    profile = get_profile(db)
    primary_goal = db.scalar(select(models.Goal).where(models.Goal.is_current.is_(True)).limit(1))
    fatigue, readiness, _ = current_load_readiness(db)
    upcoming_rows = list(
        db.scalars(
            select(models.PlannedSession)
            .where(
                models.PlannedSession.session_date > trigger.session_date,
                models.PlannedSession.session_date <= trigger.session_date + timedelta(days=7),
                models.PlannedSession.status.in_([PlanStatus.PLANNED, PlanStatus.MODIFIED]),
            )
            .order_by(models.PlannedSession.session_date, models.PlannedSession.id)
        )
    )
    if not upcoming_rows:
        return []
    planned = trigger.planned_session_id and db.get(
        models.PlannedSession, trigger.planned_session_id
    )
    trigger_started_at = _session_event_time(trigger, profile) - timedelta(
        minutes=trigger.duration_minutes
    )
    _, trigger_pre_readiness, trigger_checkin = current_load_readiness(db, as_of=trigger_started_at)
    trigger_areas = trigger_checkin.area_soreness if trigger_checkin else {}
    trigger_soreness = bool(trigger_checkin and (trigger_checkin.general_soreness or 0) >= 6)
    evidence = CompletedEvidence(
        id=trigger.id,
        session_date=trigger.session_date,
        sport=trigger.sport,
        workout_type=trigger.workout_type,
        duration_minutes=trigger.duration_minutes,
        rpe=trigger.rpe,
        planned_duration_minutes=planned.planned_duration_minutes if planned else None,
        target_rpe_max=planned.target_rpe_max if planned else None,
        pre_session_readiness=(
            trigger_pre_readiness.running_score
            if trigger.sport == Sport.RUNNING
            else trigger_pre_readiness.climbing_score
        ),
        persistent_soreness=trigger_soreness,
        area_soreness={key: float(value) for key, value in trigger_areas.items()},
        planned_structured_blocks=tuple(planned.structured_blocks if planned else ()),
        completed_interval_blocks=tuple(trigger.running.intervals if trigger.running else ()),
        splits=tuple(trigger.running.splits if trigger.running else ()),
        average_pace_seconds_per_km=(
            trigger.running.average_pace_seconds_per_km if trigger.running else None
        ),
        average_hr=trigger.running.average_hr if trigger.running else None,
        execution_failed=bool(
            planned
            and (
                (
                    planned.planned_duration_minutes
                    and trigger.duration_minutes < 0.50 * planned.planned_duration_minutes
                )
                or (
                    trigger.rpe is not None
                    and planned.target_rpe_max is not None
                    and trigger.rpe > planned.target_rpe_max + 2
                )
            )
        ),
    )
    history_rows = list(
        db.scalars(
            select(models.CompletedSession)
            .options(selectinload(models.CompletedSession.running))
            .where(
                models.CompletedSession.id != trigger.id,
                models.CompletedSession.sport == trigger.sport,
                models.CompletedSession.workout_type == trigger.workout_type,
                models.CompletedSession.session_date >= trigger.session_date - timedelta(days=42),
            )
        )
    )
    history_items: list[CompletedEvidence] = []
    for row in history_rows:
        row_plan = row.planned_session_id and db.get(models.PlannedSession, row.planned_session_id)
        row_started_at = _session_event_time(row, profile) - timedelta(minutes=row.duration_minutes)
        _, row_readiness, row_checkin = current_load_readiness(db, as_of=row_started_at)
        row_areas = row_checkin.area_soreness if row_checkin else {}
        row_soreness = bool(row_checkin and (row_checkin.general_soreness or 0) >= 6)
        history_items.append(
            CompletedEvidence(
                id=row.id,
                session_date=row.session_date,
                sport=row.sport,
                workout_type=row.workout_type,
                duration_minutes=row.duration_minutes,
                rpe=row.rpe,
                planned_duration_minutes=(row_plan.planned_duration_minutes if row_plan else None),
                target_rpe_max=row_plan.target_rpe_max if row_plan else None,
                pre_session_readiness=(
                    row_readiness.running_score
                    if row.sport == Sport.RUNNING
                    else row_readiness.climbing_score
                ),
                persistent_soreness=row_soreness,
                area_soreness={key: float(value) for key, value in row_areas.items()},
                planned_structured_blocks=tuple(row_plan.structured_blocks if row_plan else ()),
                completed_interval_blocks=tuple(row.running.intervals if row.running else ()),
                splits=tuple(row.running.splits if row.running else ()),
                average_pace_seconds_per_km=(
                    row.running.average_pace_seconds_per_km if row.running else None
                ),
                average_hr=row.running.average_hr if row.running else None,
            )
        )
    history = tuple(history_items)
    recent_longest_run_km = db.scalar(
        select(func.max(models.RunningSessionDetail.distance_km))
        .join(models.CompletedSession)
        .where(
            models.CompletedSession.sport == Sport.RUNNING,
            func.lower(models.CompletedSession.workout_type) == "long run",
            models.CompletedSession.session_date.between(
                trigger.session_date - timedelta(days=42), trigger.session_date
            ),
        )
    )
    upcoming = tuple(
        PlannedWorkout(
            id=row.id,
            session_date=row.session_date,
            sport=row.sport,
            workout_type=row.workout_type,
            title=row.title,
            duration_minutes=row.planned_duration_minutes,
            distance_km=row.planned_distance_km,
            target_rpe_min=row.target_rpe_min,
            target_rpe_max=row.target_rpe_max,
            priority=row.priority,
            exercises=tuple(
                block.get("exercise", "")
                for block in row.structured_blocks
                if block.get("exercise")
            ),
            structured_blocks=tuple(row.structured_blocks),
        )
        for row in upcoming_rows
    )
    proposals = propose_adaptations(
        AdaptationContext(
            trigger=evidence,
            upcoming=upcoming,
            latent_fatigue=fatigue.latent,
            running_readiness=readiness.running_label,
            climbing_readiness=readiness.climbing_label,
            comparable_history=history,
            primary_goal=primary_goal.goal_type.value if primary_goal else None,
            running_phase=profile.running_phase.value,
            climbing_phase=profile.climbing_phase.value,
            recent_longest_run_km=(
                float(recent_longest_run_km) if recent_longest_run_km is not None else None
            ),
        )
    )
    created: list[models.AdaptationEvent] = []
    for proposal in proposals:
        duplicate = db.scalar(
            select(models.AdaptationEvent).where(
                models.AdaptationEvent.trigger_session_id == trigger.id,
                models.AdaptationEvent.affected_session_id == proposal.affected_session_id,
                models.AdaptationEvent.action == proposal.action,
            )
        )
        if duplicate:
            created.append(duplicate)
            continue
        affected = db.get(models.PlannedSession, proposal.affected_session_id)
        old = plan_snapshot(affected) if affected else {}
        proposed = {**old, **proposal.proposed_changes}
        event_reason = proposal.reason
        event_evidence = list(proposal.evidence)
        event_confidence = proposal.confidence
        event_source = AdaptationSource.RULE_ENGINE
        if get_settings().openai_api_key:
            from app.ai import AIUnavailableError, propose_plan_adaptation

            principles = list(
                db.scalars(
                    select(models.CoachingPrinciple).where(
                        models.CoachingPrinciple.is_active.is_(True),
                        models.CoachingPrinciple.athlete_approved.is_(True),
                    )
                )
            )
            approved_notes = list(
                db.scalars(
                    select(models.TrainingNote).where(
                        models.TrainingNote.use_for_coaching.is_(True)
                    )
                )
            )
            recent_rows = [
                item
                for item in list_completed_sessions(db)
                if item.session_date >= trigger.session_date - timedelta(days=13)
            ]
            try:
                ai_proposal = propose_plan_adaptation(
                    {
                        "primary_goal": primary_goal.goal_type.value if primary_goal else "UNSET",
                        "running_phase": profile.running_phase.value,
                        "climbing_phase": profile.climbing_phase.value,
                        "recent_workouts": [
                            serializers.completed_session(item) for item in recent_rows
                        ],
                        "fatigue": {
                            domain.value: value for domain, value in fatigue.latent.items()
                        },
                        "readiness": {
                            "running": readiness.running_label.value,
                            "climbing": readiness.climbing_label.value,
                        },
                        "upcoming_seven_days": [
                            serializers.planned_session(item) for item in upcoming_rows
                        ],
                        "deterministic_rule_result": {
                            "action": proposal.action.value,
                            "reason": proposal.reason,
                            "evidence": list(proposal.evidence),
                            "proposed_changes": proposal.proposed_changes,
                        },
                        "approved_coaching_principles": [
                            *[item.principle for item in principles],
                            *[
                                f"Approved note — {item.title}: {item.summary or item.cleaned_note}"
                                for item in approved_notes
                            ],
                        ],
                    }
                )
                # AI may explain a deterministic proposal, but cannot change its bounded action/diff.
                if ai_proposal.action == proposal.action:
                    event_reason = ai_proposal.reason
                    event_evidence = [
                        *proposal.evidence,
                        *ai_proposal.evidence,
                        f"Deterministic rule permitted {proposal.action.value}",
                    ]
                    event_confidence = ai_proposal.confidence
                    event_source = AdaptationSource.AI
            except AIUnavailableError:
                pass
        event = models.AdaptationEvent(
            affected_session_id=proposal.affected_session_id,
            trigger_session_id=trigger.id,
            original_plan=old,
            proposed_plan=proposed,
            action=proposal.action,
            reason=event_reason,
            evidence=event_evidence,
            confidence=event_confidence,
            source=event_source,
            decision=AdaptationDecision.PENDING,
        )
        db.add(event)
        created.append(event)
    db.commit()
    for event in created:
        db.refresh(event)
    return created


def analyse_completed_session_with_ai(
    db: Session, session: models.CompletedSession
) -> dict[str, Any] | None:
    if not get_settings().openai_api_key:
        return None
    from app.ai import AIUnavailableError, analyse_completed_session

    profile = get_profile(db)
    goal = db.scalar(select(models.Goal).where(models.Goal.is_current.is_(True)).limit(1))
    planned = session.planned_session_id and db.get(
        models.PlannedSession, session.planned_session_id
    )
    fatigue, readiness, _ = current_load_readiness(db)
    try:
        analysis = analyse_completed_session(
            {
                "primary_goal": goal.goal_type.value if goal else "UNSET",
                "running_phase": profile.running_phase.value,
                "climbing_phase": profile.climbing_phase.value,
                "planned_workout": plan_snapshot(planned) if planned else {},
                "completed_workout": serializers.completed_session(session),
                "fatigue": {domain.value: value for domain, value in fatigue.latent.items()},
                "readiness": {
                    "running": readiness.running_label.value,
                    "climbing": readiness.climbing_label.value,
                },
            }
        )
    except AIUnavailableError:
        return None
    session.ai_analysis = analysis.model_dump(mode="json")
    db.commit()
    return session.ai_analysis


def mark_planned_session_skipped(
    db: Session, plan: models.PlannedSession
) -> list[models.AdaptationEvent]:
    update_planned_session(
        db,
        plan,
        {"status": PlanStatus.SKIPPED},
        "Athlete marked session skipped",
    )
    profile = get_profile(db)
    goal = db.scalar(select(models.Goal).where(models.Goal.is_current.is_(True)).limit(1))
    fatigue, readiness, _ = current_load_readiness(db)
    upcoming_rows = tuple(
        db.scalars(
            select(models.PlannedSession)
            .where(
                models.PlannedSession.session_date > plan.session_date,
                models.PlannedSession.session_date <= plan.session_date + timedelta(days=7),
                models.PlannedSession.status.in_([PlanStatus.PLANNED, PlanStatus.MODIFIED]),
            )
            .order_by(models.PlannedSession.session_date, models.PlannedSession.id)
        )
    )
    context = AdaptationContext(
        trigger=CompletedEvidence(
            id=-plan.id,
            session_date=plan.session_date,
            sport=plan.sport,
            workout_type=plan.workout_type,
            duration_minutes=0,
            rpe=None,
            planned_duration_minutes=plan.planned_duration_minutes,
            target_rpe_max=plan.target_rpe_max,
            missed=True,
        ),
        upcoming=tuple(
            PlannedWorkout(
                id=row.id,
                session_date=row.session_date,
                sport=row.sport,
                workout_type=row.workout_type,
                title=row.title,
                duration_minutes=row.planned_duration_minutes,
                distance_km=row.planned_distance_km,
                target_rpe_min=row.target_rpe_min,
                target_rpe_max=row.target_rpe_max,
                priority=row.priority,
            )
            for row in upcoming_rows
        ),
        latent_fatigue=fatigue.latent,
        running_readiness=readiness.running_label,
        climbing_readiness=readiness.climbing_label,
        primary_goal=goal.goal_type.value if goal else None,
        running_phase=profile.running_phase.value,
        climbing_phase=profile.climbing_phase.value,
    )
    events: list[models.AdaptationEvent] = []
    for proposal in propose_adaptations(context):
        affected = db.get(models.PlannedSession, proposal.affected_session_id)
        original = plan_snapshot(affected) if affected else {}
        event = models.AdaptationEvent(
            affected_session_id=proposal.affected_session_id,
            trigger_session_id=None,
            original_plan=original,
            proposed_plan={**original, **proposal.proposed_changes},
            action=proposal.action,
            reason=proposal.reason,
            evidence=[*proposal.evidence, f"Skipped planned session {plan.id}"],
            confidence=proposal.confidence,
            source=AdaptationSource.RULE_ENGINE,
            decision=AdaptationDecision.PENDING,
        )
        db.add(event)
        events.append(event)
    db.commit()
    for event in events:
        db.refresh(event)
    return events


def decide_adaptation(
    db: Session, event: models.AdaptationEvent, decision: str, proposed_plan: Any = None
) -> models.AdaptationEvent:
    accepted = decision.upper() in {"ACCEPT", "ACCEPTED"}
    edited = accepted and proposed_plan is not None
    event.decision = (
        AdaptationDecision.EDITED
        if edited
        else AdaptationDecision.ACCEPTED
        if accepted
        else AdaptationDecision.REJECTED
    )
    event.decided_at = datetime.now(UTC)
    if accepted and event.affected_session_id:
        plan = db.get(models.PlannedSession, event.affected_session_id)
        if plan:
            if isinstance(proposed_plan, dict):
                changes = proposed_plan
            elif isinstance(proposed_plan, str):
                try:
                    parsed = json.loads(proposed_plan)
                except json.JSONDecodeError:
                    parsed = {"description": proposed_plan}
                changes = parsed if isinstance(parsed, dict) else {"description": proposed_plan}
            else:
                changes = event.proposed_plan
            if edited:
                event.proposed_plan = changes
            public_keys = {
                "date",
                "session_date",
                "start_time",
                "workout_kind",
                "sport",
                "session_type",
                "workout_type",
                "title",
                "description",
                "planned_duration_minutes",
                "planned_distance_km",
                "target_rpe",
                "structured_blocks",
                "priority",
                "status",
            }
            filtered = {key: value for key, value in changes.items() if key in public_keys}
            if event.action.value in {"MOVE", "REPLACE"}:
                is_move = event.action.value == "MOVE"
                plan.status = PlanStatus.MOVED if is_move else PlanStatus.REPLACED
                raw_date = filtered.get("session_date") or filtered.get("date") or plan.session_date
                successor_date = (
                    date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
                )
                raw_start_time = filtered.get("start_time", plan.start_time)
                successor_start_time = (
                    time.fromisoformat(raw_start_time)
                    if isinstance(raw_start_time, str)
                    else raw_start_time
                )
                raw_sport = filtered.get("workout_kind") or filtered.get("sport") or plan.sport
                raw_type = (
                    filtered.get("session_type")
                    or filtered.get("workout_type")
                    or plan.workout_type
                )
                successor = models.PlannedSession(
                    athlete_id=plan.athlete_id,
                    session_date=successor_date,
                    start_time=successor_start_time,
                    sport=raw_sport if isinstance(raw_sport, Sport) else Sport(raw_sport),
                    workout_type=raw_type,
                    title=filtered.get("title", plan.title),
                    description=filtered.get("description", plan.description),
                    planned_duration_minutes=filtered.get(
                        "planned_duration_minutes", plan.planned_duration_minutes
                    ),
                    planned_distance_km=filtered.get(
                        "planned_distance_km", plan.planned_distance_km
                    ),
                    target_rpe_min=filtered.get("target_rpe", plan.target_rpe_min),
                    target_rpe_max=filtered.get("target_rpe", plan.target_rpe_max),
                    priority=plan.priority,
                    status=PlanStatus.PLANNED,
                    structured_blocks=list(
                        filtered.get("structured_blocks", plan.structured_blocks)
                    ),
                    is_demo=plan.is_demo,
                    moved_from_id=plan.id if is_move else None,
                    replaced_session_id=plan.id if not is_move else None,
                )
                db.add(successor)
                db.flush()
                db.add(
                    models.PlannedSessionRevision(
                        planned_session_id=successor.id,
                        version=1,
                        snapshot=plan_snapshot(successor),
                        reason=f"Successor created by adaptation {event.id}",
                    )
                )
            else:
                filtered["status"] = PlanStatus.MODIFIED
                update_planned_session(db, plan, filtered, f"Accepted adaptation {event.id}")
    db.commit()
    db.refresh(event)
    return event


def calendar_entries(db: Session, start: date, end: date) -> list[dict[str, Any]]:
    plans = list(
        db.scalars(
            select(models.PlannedSession)
            .where(models.PlannedSession.session_date.between(start, end))
            .order_by(models.PlannedSession.session_date, models.PlannedSession.id)
        )
    )
    completed = [row for row in list_completed_sessions(db) if start <= row.session_date <= end]
    entries: list[dict[str, Any]] = []
    linked_completed: set[int] = set()
    for plan in plans:
        completed_item = next((row for row in completed if row.planned_session_id == plan.id), None)
        if completed_item:
            linked_completed.add(completed_item.id)
        entries.append(
            {
                "id": f"plan-{plan.id}",
                "date": plan.session_date.isoformat(),
                "planned": serializers.planned_session(plan),
                "completed": serializers.completed_session(completed_item)
                if completed_item
                else None,
                "status": plan.status.value,
            }
        )
    for item in completed:
        if item.id in linked_completed:
            continue
        entries.append(
            {
                "id": f"completed-{item.id}",
                "date": item.session_date.isoformat(),
                "planned": None,
                "completed": serializers.completed_session(item),
                "status": PlanStatus.COMPLETED.value,
            }
        )
    return sorted(entries, key=lambda row: (row["date"], row["id"]))
