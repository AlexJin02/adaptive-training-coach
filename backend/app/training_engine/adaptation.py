from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import ceil
from statistics import mean
from typing import Any

from app.enums import (
    AdaptationAction,
    Confidence,
    FatigueDomain,
    ReadinessLabel,
    SessionPriority,
    Sport,
)
from app.training_engine.config import (
    COMPARABLE_SESSION_WINDOW_DAYS,
    COMPARABLE_SUCCESS_COUNT,
    FINGER_MODERATE_CAP_THRESHOLD,
    HEAVY_DOMAIN_COEFFICIENT,
    HIGH_FATIGUE_THRESHOLD,
    INTENSITY_REDUCTION_FRACTION,
    LONG_RUN_MAX_INCREASE_FRACTION,
    MAJOR_INTERVAL_COMPLETION_FRACTION,
    MAJOR_LATE_DETERIORATION_PACE_FRACTION,
    NO_LATE_DETERIORATION_PACE_FRACTION,
    READINESS_STABILITY_MAX_SPREAD,
    UPPER_JOINT_SORENESS_BLOCK_THRESHOLD,
    VERY_HIGH_FATIGUE_THRESHOLD,
    VOLUME_REDUCTION_FRACTION,
)
from app.training_engine.session_load import demand_profile


@dataclass(frozen=True)
class PlannedWorkout:
    id: int
    session_date: date
    sport: Sport
    workout_type: str
    title: str
    duration_minutes: float | None = None
    distance_km: float | None = None
    target_rpe_min: float | None = None
    target_rpe_max: float | None = None
    priority: SessionPriority = SessionPriority.NORMAL
    exercises: tuple[str, ...] = ()
    structured_blocks: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class CompletedEvidence:
    id: int
    session_date: date
    sport: Sport
    workout_type: str
    duration_minutes: float
    rpe: float | None
    planned_duration_minutes: float | None = None
    target_rpe_max: float | None = None
    pre_session_readiness: float | None = None
    persistent_soreness: bool = False
    area_soreness: dict[str, float] = field(default_factory=dict)
    planned_structured_blocks: tuple[dict[str, Any], ...] = ()
    completed_interval_blocks: tuple[dict[str, Any], ...] = ()
    splits: tuple[dict[str, Any], ...] = ()
    average_pace_seconds_per_km: float | None = None
    average_hr: int | None = None
    execution_failed: bool = False
    missed: bool = False


@dataclass(frozen=True)
class AdaptationContext:
    trigger: CompletedEvidence
    upcoming: tuple[PlannedWorkout, ...]
    latent_fatigue: dict[FatigueDomain, float]
    running_readiness: ReadinessLabel
    climbing_readiness: ReadinessLabel
    comparable_history: tuple[CompletedEvidence, ...] = ()
    primary_goal: str | None = None
    running_phase: str | None = None
    climbing_phase: str | None = None
    recent_longest_run_km: float | None = None


@dataclass(frozen=True)
class EngineProposal:
    affected_session_id: int
    action: AdaptationAction
    reason: str
    evidence: tuple[str, ...]
    confidence: Confidence
    proposed_changes: dict[str, Any] = field(default_factory=dict)


EASY_RUNNING_TYPES = {"easy", "recovery"}
RUNNING_GOALS = {"RUNNING_MILEAGE", "HALF_MARATHON", "MARATHON"}
CLIMBING_GOALS = {"BOULDERING", "LEAD_CLIMBING"}


@dataclass(frozen=True)
class IntervalPrescription:
    repetitions: int
    work_minutes: float
    recovery_minutes: float | None
    target_pace_seconds_per_km: float | None
    target_hr_max: int | None
    block_index: int


@dataclass(frozen=True)
class ExecutionAssessment:
    successful: bool
    strong: bool
    major_failure: bool
    structured_evidence_required: bool
    no_late_deterioration: bool | None
    evidence: tuple[str, ...]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pace_seconds(value: Any) -> float | None:
    numeric = _number(value)
    if numeric is not None:
        return numeric if numeric > 0 else None
    if not isinstance(value, str):
        return None
    cleaned = value.lower().replace("/km", "").strip()
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", cleaned)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    return None


def _block_text(block: dict[str, Any]) -> str:
    return " ".join(str(block.get(key) or "") for key in ("description", "detail", "name", "title"))


def _interval_prescription(
    blocks: tuple[dict[str, Any], ...],
) -> IntervalPrescription | None:
    for index, block in enumerate(blocks):
        repetitions = _number(
            block.get("repetitions", block.get("reps", block.get("repeat_count")))
        )
        work_minutes = _number(
            block.get(
                "work_minutes",
                block.get("duration_minutes", block.get("rep_duration_minutes")),
            )
        )
        text = _block_text(block)
        if repetitions is None or work_minutes is None:
            match = re.search(
                r"(\d+)\s*(?:x|×)\s*(\d+(?:\.\d+)?)\s*(?:min|minute)",
                text,
                re.IGNORECASE,
            )
            if match:
                repetitions = float(match.group(1))
                work_minutes = float(match.group(2))
        if repetitions is None or work_minutes is None:
            continue
        target_pace = _pace_seconds(
            block.get(
                "target_pace_seconds_per_km",
                block.get("target_pace", block.get("pace_seconds_per_km")),
            )
        )
        target_hr = _number(block.get("target_hr_max", block.get("hr_max")))
        recovery = _number(block.get("recovery_minutes", block.get("rest_minutes")))
        if target_pace is None:
            pace_match = re.search(
                r"@\s*(\d{1,2}:\d{2})\s*(?:/\s*km|per\s*km)",
                text,
                re.IGNORECASE,
            )
            if pace_match:
                target_pace = _pace_seconds(pace_match.group(1))
        if target_hr is None:
            hr_match = re.search(
                r"\bHR\s*(?:<=|≤|max(?:imum)?\s*)?\s*(\d{2,3})\b",
                text,
                re.IGNORECASE,
            )
            if hr_match:
                target_hr = float(hr_match.group(1))
        if recovery is None:
            recovery_match = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:min|minute)s?\s*(?:recovery|rest)\b",
                text,
                re.IGNORECASE,
            )
            if recovery_match:
                recovery = float(recovery_match.group(1))
        return IntervalPrescription(
            repetitions=int(repetitions),
            work_minutes=float(work_minutes),
            recovery_minutes=recovery,
            target_pace_seconds_per_km=target_pace,
            target_hr_max=int(target_hr) if target_hr is not None else None,
            block_index=index,
        )
    return None


def _explicit_bool(blocks: tuple[dict[str, Any], ...], key: str) -> bool | None:
    for block in blocks:
        value = block.get(key)
        if isinstance(value, bool):
            return value
    return None


def _series_values(
    blocks: tuple[dict[str, Any], ...], scalar_keys: tuple[str, ...], list_keys: tuple[str, ...]
) -> list[float]:
    values: list[float] = []
    for block in blocks:
        for key in list_keys:
            raw_values = block.get(key)
            if isinstance(raw_values, list):
                values.extend(
                    value for raw in raw_values if (value := _number(raw)) is not None and value > 0
                )
        for key in scalar_keys:
            value = _number(block.get(key))
            if value is not None and value > 0:
                values.append(value)
                break
    return values


def _interval_paces(blocks: tuple[dict[str, Any], ...]) -> list[float]:
    values: list[float] = []
    for block in blocks:
        raw_values = block.get("paces_seconds_per_km", block.get("paces"))
        if isinstance(raw_values, list):
            values.extend(pace for raw in raw_values if (pace := _pace_seconds(raw)) is not None)
        for key in ("pace_seconds_per_km", "average_pace_seconds_per_km", "pace"):
            pace = _pace_seconds(block.get(key))
            if pace is not None:
                values.append(pace)
                break
    return values


def _split_paces(splits: tuple[dict[str, Any], ...]) -> list[float]:
    values: list[float] = []
    for split in splits:
        direct = _pace_seconds(split.get("pace_seconds_per_km", split.get("pace")))
        if direct is not None:
            values.append(direct)
            continue
        distance = _number(split.get("distance_km", split.get("distance")))
        elapsed = _pace_seconds(split.get("time", split.get("duration")))
        if distance and elapsed:
            values.append(elapsed / distance)
    return values


def _late_deterioration(paces: list[float]) -> tuple[bool | None, bool]:
    if len(paces) < 2:
        return None, False
    midpoint = max(1, len(paces) // 2)
    early = mean(paces[:midpoint])
    late = mean(paces[midpoint:])
    ratio = late / early
    return (
        ratio <= 1 + NO_LATE_DETERIORATION_PACE_FRACTION,
        ratio > 1 + MAJOR_LATE_DETERIORATION_PACE_FRACTION,
    )


def _completed_repetitions(evidence: CompletedEvidence, paces: list[float]) -> int | None:
    for block in evidence.completed_interval_blocks:
        value = _number(
            block.get(
                "repetitions_completed",
                block.get("completed_repetitions", block.get("reps_completed")),
            )
        )
        if value is not None:
            return int(value)
    marked = sum(
        1
        for block in evidence.completed_interval_blocks
        if block.get("repetition") is not None or block.get("rep") is not None
    )
    if marked:
        return marked
    return len(paces) or None


def _base_execution_success(evidence: CompletedEvidence) -> bool:
    if evidence.missed or evidence.execution_failed or evidence.persistent_soreness:
        return False
    # Progression needs affirmative execution/recovery evidence; missing values are not success.
    if evidence.rpe is None or evidence.target_rpe_max is None:
        return False
    if evidence.pre_session_readiness is None or evidence.pre_session_readiness < 5.0:
        return False
    if (
        evidence.planned_duration_minutes is not None
        and evidence.duration_minutes < 0.90 * evidence.planned_duration_minutes
    ):
        return False
    return not (
        evidence.rpe is not None
        and evidence.target_rpe_max is not None
        and evidence.rpe > evidence.target_rpe_max
    )


def _assess_execution(evidence: CompletedEvidence) -> ExecutionAssessment:
    base_success = _base_execution_success(evidence)
    prescription = _interval_prescription(evidence.planned_structured_blocks)
    if prescription is None:
        return ExecutionAssessment(
            successful=base_success,
            strong=False,
            major_failure=evidence.execution_failed,
            structured_evidence_required=False,
            no_late_deterioration=None,
            evidence=("Duration and RPE were within the recorded plan",) if base_success else (),
        )

    interval_paces = _interval_paces(evidence.completed_interval_blocks)
    split_paces = _split_paces(evidence.splits)
    work_paces = (
        interval_paces
        if len(interval_paces) >= prescription.repetitions
        else split_paces
        if len(split_paces) >= prescription.repetitions
        else interval_paces or split_paces
    )
    late_paces = work_paces
    explicit_late = _explicit_bool(evidence.completed_interval_blocks, "late_deterioration")
    if explicit_late is not None:
        no_late_deterioration = not explicit_late
        major_late_deterioration = (
            explicit_late
            and _explicit_bool(evidence.completed_interval_blocks, "major_late_deterioration")
            is True
        )
    else:
        no_late_deterioration, major_late_deterioration = _late_deterioration(late_paces)

    repetitions_completed = _completed_repetitions(evidence, work_paces)
    major_rep_failure = repetitions_completed is not None and repetitions_completed < ceil(
        prescription.repetitions * MAJOR_INTERVAL_COMPLETION_FRACTION
    )
    explicit_failure = _explicit_bool(evidence.completed_interval_blocks, "execution_failed")
    major_failure = bool(
        evidence.execution_failed
        or explicit_failure
        or major_rep_failure
        or major_late_deterioration
    )

    explicit_faster = _explicit_bool(
        evidence.completed_interval_blocks, "all_reps_faster_than_target"
    )
    all_reps_faster = (
        explicit_faster
        if explicit_faster is not None
        else bool(
            prescription.target_pace_seconds_per_km is not None
            and len(work_paces) >= prescription.repetitions
            and all(
                pace < prescription.target_pace_seconds_per_km
                for pace in work_paces[: prescription.repetitions]
            )
        )
    )
    interval_hrs = _series_values(
        evidence.completed_interval_blocks,
        ("average_hr", "hr"),
        ("average_hrs", "hrs"),
    )
    if len(interval_hrs) < prescription.repetitions:
        interval_hrs = _series_values(
            evidence.splits,
            ("average_hr", "hr"),
            ("average_hrs", "hrs"),
        )
    explicit_hr_controlled = _explicit_bool(evidence.completed_interval_blocks, "hr_controlled")
    hr_controlled = (
        explicit_hr_controlled
        if explicit_hr_controlled is not None
        else bool(
            prescription.target_hr_max is not None
            and len(interval_hrs) >= prescription.repetitions
            and max(interval_hrs[: prescription.repetitions]) <= prescription.target_hr_max
        )
    )
    completed_as_planned = (
        repetitions_completed is not None and repetitions_completed >= prescription.repetitions
    )
    successful = bool(
        base_success
        and completed_as_planned
        and no_late_deterioration is True
        and not major_failure
    )
    strong = bool(successful and all_reps_faster and hr_controlled)
    details: list[str] = []
    if completed_as_planned:
        details.append(
            f"Completed {repetitions_completed}/{prescription.repetitions} planned work reps"
        )
    elif repetitions_completed is None:
        details.append("Completed work-rep count is unavailable")
    else:
        details.append(
            f"Completed only {repetitions_completed}/{prescription.repetitions} planned work reps"
        )
    if all_reps_faster:
        details.append("All recorded work reps were faster than target pace")
    elif prescription.target_pace_seconds_per_km is not None:
        details.append("Not all work reps can be verified at target pace")
    else:
        details.append("Target pace evidence is unavailable")
    if hr_controlled:
        details.append("Work-rep HR stayed within the recorded target")
    elif prescription.target_hr_max is not None:
        details.append("Work-rep HR control was not verified")
    else:
        details.append("Target HR evidence is unavailable")
    if no_late_deterioration is True:
        details.append("No late-session pace deterioration detected")
    elif no_late_deterioration is False:
        details.append("Late-session pace deterioration detected")
    else:
        details.append("Late-session deterioration cannot be assessed")
    if major_failure:
        details.append("Major execution failure detected")
    return ExecutionAssessment(
        successful=successful,
        strong=strong,
        major_failure=major_failure,
        structured_evidence_required=True,
        no_late_deterioration=no_late_deterioration,
        evidence=tuple(details),
    )


def _qualifies_for_progression(evidence: CompletedEvidence) -> bool:
    assessment = _assess_execution(evidence)
    return assessment.strong if assessment.structured_evidence_required else assessment.successful


def _is_successful(evidence: CompletedEvidence) -> bool:
    """Compatibility helper for non-progression branches and existing engine callers."""

    return _assess_execution(evidence).successful


def _progression_soreness_evidence(
    evidence: CompletedEvidence, workout: PlannedWorkout
) -> tuple[str, ...]:
    """Return only soreness signals that overlap the workout's demand profile."""

    if evidence.persistent_soreness:
        return ("Persistent or high general soreness signal",)
    demands = _hard_demands(workout)
    areas = {name.lower(): float(value) for name, value in evidence.area_soreness.items()}
    conflicts: list[str] = []
    finger = max(areas.get("finger", 0.0), areas.get("fingers", 0.0))
    if finger >= FINGER_MODERATE_CAP_THRESHOLD and demands[FatigueDomain.FINGER_FOREARM] > 0:
        conflicts.append(f"Finger soreness {finger:g}/10 overlaps finger demand")
    for area in ("elbow", "shoulder"):
        value = max(areas.get(area, 0.0), areas.get(f"{area}s", 0.0))
        if (
            value >= UPPER_JOINT_SORENESS_BLOCK_THRESHOLD
            and demands[FatigueDomain.PULLING_UPPER_BODY] > 0
        ):
            conflicts.append(f"{area.title()} soreness {value:g}/10 overlaps pulling demand")
    return tuple(conflicts)


def _comparable(a: CompletedEvidence, b: CompletedEvidence) -> bool:
    if not (
        a.sport == b.sport
        and a.workout_type.strip().lower() == b.workout_type.strip().lower()
        and abs((a.session_date - b.session_date).days) <= COMPARABLE_SESSION_WINDOW_DAYS
    ):
        return False
    a_plan = _interval_prescription(a.planned_structured_blocks)
    b_plan = _interval_prescription(b.planned_structured_blocks)
    if a_plan is None and b_plan is None:
        return True
    if a_plan is None or b_plan is None:
        return False
    return (
        a_plan.repetitions == b_plan.repetitions
        and abs(a_plan.work_minutes - b_plan.work_minutes) < 0.01
        and (
            a_plan.recovery_minutes is None
            or b_plan.recovery_minutes is None
            or abs(a_plan.recovery_minutes - b_plan.recovery_minutes) < 0.01
        )
    )


def assess_execution(evidence: CompletedEvidence) -> ExecutionAssessment:
    """Public deterministic assessment used by persistence-facing services."""

    return _assess_execution(evidence)


def comparable_execution(a: CompletedEvidence, b: CompletedEvidence) -> bool:
    return _comparable(a, b)


def _hard_demands(workout: PlannedWorkout) -> dict[FatigueDomain, float]:
    return demand_profile(workout.sport, workout.workout_type, list(workout.exercises))


def _is_hard(workout: PlannedWorkout) -> bool:
    return max(_hard_demands(workout).values()) >= HEAVY_DOMAIN_COEFFICIENT


def _goal_aligned(workout: PlannedWorkout, primary_goal: str | None) -> bool:
    if primary_goal in RUNNING_GOALS:
        return workout.sport == Sport.RUNNING
    if primary_goal in CLIMBING_GOALS:
        return workout.sport == Sport.CLIMBING
    return False


def _supporting_adjustment_rank(
    workout: PlannedWorkout, primary_goal: str | None
) -> tuple[bool, bool, date, int]:
    """Prefer adjusting supporting/normal sessions while preserving safety overrides."""

    return (
        _goal_aligned(workout, primary_goal),
        workout.priority == SessionPriority.HIGH,
        workout.session_date,
        workout.id,
    )


def _first_free_date(workout: PlannedWorkout, upcoming: tuple[PlannedWorkout, ...]) -> date | None:
    occupied = {item.session_date for item in upcoming if item.id != workout.id}
    for offset in range(1, 8):
        candidate = workout.session_date + timedelta(days=offset)
        if candidate not in occupied:
            return candidate
    return None


def _move_or_replace(
    workout: PlannedWorkout,
    upcoming: tuple[PlannedWorkout, ...],
    reason: str,
    evidence: tuple[str, ...],
) -> EngineProposal:
    free_date = _first_free_date(workout, upcoming)
    if free_date is not None:
        return EngineProposal(
            affected_session_id=workout.id,
            action=AdaptationAction.MOVE,
            reason=reason,
            evidence=evidence,
            confidence=Confidence.HIGH,
            proposed_changes={"session_date": free_date.isoformat()},
        )
    return EngineProposal(
        affected_session_id=workout.id,
        action=AdaptationAction.REPLACE,
        reason=reason,
        evidence=evidence,
        confidence=Confidence.MODERATE,
        proposed_changes={"workout_type": "Recovery", "title": "Recovery session"},
    )


def _threshold_structured_progression(
    workout: PlannedWorkout,
) -> tuple[list[dict[str, Any]], str] | None:
    prescription = _interval_prescription(workout.structured_blocks)
    if (
        prescription is None
        or "threshold" not in workout.workout_type.lower()
        or prescription.repetitions != 4
        or abs(prescription.work_minutes - 8.0) >= 0.01
    ):
        return None
    blocks = [dict(block) for block in workout.structured_blocks]
    main = blocks[prescription.block_index]
    repetition_key = next(
        (key for key in ("repetitions", "reps", "repeat_count") if key in main),
        "repetitions",
    )
    duration_key = next(
        (
            key
            for key in ("work_minutes", "duration_minutes", "rep_duration_minutes")
            if key in main
        ),
        "work_minutes",
    )
    main[repetition_key] = 3
    main[duration_key] = 12
    for key in ("description", "detail", "name", "title"):
        if isinstance(main.get(key), str):
            main[key] = re.sub(
                r"4\s*(?:x|×)\s*8\s*(?:min|minute)",
                "3 × 12 min",
                main[key],
                count=1,
                flags=re.IGNORECASE,
            )
    return blocks, "Threshold main work 4 × 8 min → 3 × 12 min; targets and recovery unchanged"


def _progression_proposal(
    workout: PlannedWorkout,
    context: AdaptationContext,
    execution_evidence: tuple[str, ...] = (),
) -> EngineProposal:
    structured = _threshold_structured_progression(workout)
    if structured is not None:
        blocks, structured_evidence = structured
        changes: dict[str, Any] = {
            "structured_blocks": blocks,
            "progressed_variable": "volume",
        }
    elif (
        workout.sport == Sport.RUNNING
        and workout.workout_type.lower() == "long run"
        and workout.distance_km is not None
        and context.recent_longest_run_km is not None
    ):
        exposure_cap = round(
            context.recent_longest_run_km * (1 + LONG_RUN_MAX_INCREASE_FRACTION), 1
        )
        if exposure_cap <= workout.distance_km:
            return EngineProposal(
                affected_session_id=workout.id,
                action=AdaptationAction.KEEP,
                reason="Recent longest-run exposure does not yet support progressing this plan.",
                evidence=(
                    f"Recent longest run {context.recent_longest_run_km:.1f} km",
                    f"Soft progression guardrail {exposure_cap:.1f} km",
                ),
                confidence=Confidence.HIGH,
            )
        changes = {
            "planned_distance_km": min(round(workout.distance_km * 1.03, 1), exposure_cap),
            "progressed_variable": "volume",
        }
    elif workout.duration_minutes is not None:
        new_duration = round(workout.duration_minutes * 1.05, 1)
        changes = {
            "planned_duration_minutes": new_duration,
            "progressed_variable": "volume",
        }
    elif workout.distance_km is not None:
        changes = {
            "planned_distance_km": round(workout.distance_km * 1.03, 1),
            "progressed_variable": "volume",
        }
    else:
        changes = {"progressed_variable": "none", "note": "Progression is available for review."}
    progression_evidence = (
        (structured_evidence,) if structured is not None else ("Only volume is changed",)
    )
    return EngineProposal(
        affected_session_id=workout.id,
        action=AdaptationAction.PROGRESS,
        reason="At least two comparable sessions succeeded with stable readiness and no soreness signal.",
        evidence=tuple(
            item
            for item in (
                "Two comparable successful sessions",
                *execution_evidence,
                *progression_evidence,
                f"Primary goal: {context.primary_goal}" if context.primary_goal else None,
                (
                    f"Current phase: {context.running_phase}"
                    if workout.sport == Sport.RUNNING and context.running_phase
                    else f"Current phase: {context.climbing_phase}"
                    if context.climbing_phase
                    else None
                ),
            )
            if item is not None
        ),
        confidence=Confidence.MODERATE,
        proposed_changes=changes,
    )


def propose_adaptations(context: AdaptationContext) -> list[EngineProposal]:
    if not context.upcoming:
        return []
    upcoming = tuple(sorted(context.upcoming, key=lambda item: (item.session_date, item.id)))
    next_workout = upcoming[0]
    trigger = context.trigger

    # Missing easy mileage is intentionally not transferred to the next day.
    if (
        trigger.missed
        and trigger.sport == Sport.RUNNING
        and trigger.workout_type.lower() in EASY_RUNNING_TYPES
    ):
        return [
            EngineProposal(
                affected_session_id=next_workout.id,
                action=AdaptationAction.KEEP,
                reason="A missed easy run is not automatically added to another day.",
                evidence=("Missed easy mileage",),
                confidence=Confidence.HIGH,
            )
        ]

    # Safety overrides goal priority: LOW readiness is always handled first.
    for candidate in upcoming:
        readiness = (
            context.running_readiness
            if candidate.sport == Sport.RUNNING
            else context.climbing_readiness
        )
        if (
            candidate.sport in {Sport.RUNNING, Sport.CLIMBING}
            and readiness == ReadinessLabel.LOW
            and _is_hard(candidate)
        ):
            return [
                _move_or_replace(
                    candidate,
                    upcoming,
                    "Readiness is LOW before a hard workout.",
                    (f"{candidate.sport.value} readiness LOW",),
                )
            ]

    conflict_rows: list[tuple[PlannedWorkout, tuple[FatigueDomain, ...]]] = []
    for candidate in upcoming:
        demands = _hard_demands(candidate)
        conflicts = tuple(
            domain
            for domain, coefficient in demands.items()
            if coefficient >= HEAVY_DOMAIN_COEFFICIENT
            and context.latent_fatigue.get(domain, 0.0) >= HIGH_FATIGUE_THRESHOLD
        )
        if conflicts:
            conflict_rows.append((candidate, conflicts))

    # Very-high domain fatigue is another safety override and stays chronological.
    for candidate, conflicts in conflict_rows:
        if not any(
            context.latent_fatigue.get(domain, 0.0) >= VERY_HIGH_FATIGUE_THRESHOLD
            for domain in conflicts
        ):
            continue
        evidence = tuple(
            f"{domain.value} fatigue {context.latent_fatigue.get(domain, 0.0):.1f}"
            for domain in conflicts
        )
        return [
            _move_or_replace(
                candidate,
                upcoming,
                "The planned workout heavily stresses a very fatigued domain.",
                evidence,
            )
        ]

    # For non-emergency conflicts, protect goal-aligned/high-priority work by adjusting a
    # supporting candidate first. This influences selection only; it cannot bypass safety.
    if conflict_rows:
        candidate, conflicts = min(
            conflict_rows,
            key=lambda item: _supporting_adjustment_rank(item[0], context.primary_goal),
        )
        evidence = tuple(
            f"{domain.value} fatigue {context.latent_fatigue.get(domain, 0.0):.1f}"
            for domain in conflicts
        )
        reduced = {}
        if candidate.duration_minutes is not None:
            reduced["planned_duration_minutes"] = round(
                candidate.duration_minutes * (1 - VOLUME_REDUCTION_FRACTION), 1
            )
        if candidate.distance_km is not None:
            reduced["planned_distance_km"] = round(
                candidate.distance_km * (1 - VOLUME_REDUCTION_FRACTION), 1
            )
        return [
            EngineProposal(
                affected_session_id=candidate.id,
                action=AdaptationAction.REDUCE_VOLUME,
                reason="The planned workout conflicts with an already-high fatigue domain.",
                evidence=(
                    *evidence,
                    (
                        f"Primary goal {context.primary_goal}: supporting work adjusted first"
                        if context.primary_goal
                        and not _goal_aligned(candidate, context.primary_goal)
                        else "Goal alignment did not override the fatigue safety gate"
                    ),
                ),
                confidence=Confidence.HIGH,
                proposed_changes=reduced,
            )
        ]

    unexpectedly_hard_easy = (
        trigger.sport == Sport.RUNNING
        and trigger.workout_type.lower() in EASY_RUNNING_TYPES
        and trigger.rpe is not None
        and trigger.rpe >= max(7.0, (trigger.target_rpe_max or 4.0) + 2.0)
    )
    if unexpectedly_hard_easy and _is_hard(next_workout):
        if next_workout.target_rpe_max is not None:
            target = max(1.0, next_workout.target_rpe_max * (1 - INTENSITY_REDUCTION_FRACTION))
            changes = {"target_rpe": round(target, 1), "progressed_variable": "intensity"}
        else:
            changes = {
                "description": (
                    "Reduce target pace/intensity by approximately 5%; preserve the rest of the session."
                )
            }
        return [
            EngineProposal(
                affected_session_id=next_workout.id,
                action=AdaptationAction.REDUCE_INTENSITY,
                reason="An easy run had unexpectedly high effort; protect the next hard session.",
                evidence=(f"Easy-run RPE {trigger.rpe:g}",),
                confidence=Confidence.MODERATE,
                proposed_changes=changes,
            )
        ]

    comparable_successes = [
        item
        for item in (*context.comparable_history, trigger)
        if _comparable(item, trigger)
        and _qualifies_for_progression(item)
        and not _progression_soreness_evidence(item, next_workout)
    ]
    comparable_successes.sort(key=lambda item: (item.session_date, item.id))
    recent_successes = comparable_successes[-COMPARABLE_SUCCESS_COUNT:]
    readiness_values = [
        item.pre_session_readiness
        for item in recent_successes
        if item.pre_session_readiness is not None
    ]
    readiness_stable = (
        len(readiness_values) >= COMPARABLE_SUCCESS_COUNT
        and max(readiness_values) - min(readiness_values) <= READINESS_STABILITY_MAX_SPREAD
    )
    trigger_soreness = _progression_soreness_evidence(trigger, next_workout)
    trigger_assessment = _assess_execution(trigger)
    if (
        len(comparable_successes) >= COMPARABLE_SUCCESS_COUNT
        and readiness_stable
        and not trigger_soreness
        and next_workout.sport == trigger.sport
        and next_workout.workout_type.lower() == trigger.workout_type.lower()
    ):
        execution_evidence = tuple(
            dict.fromkeys(
                evidence
                for item in recent_successes
                for evidence in _assess_execution(item).evidence
                if evidence
            )
        )
        return [_progression_proposal(next_workout, context, execution_evidence)]

    if trigger_assessment.major_failure:
        return [
            EngineProposal(
                affected_session_id=next_workout.id,
                action=AdaptationAction.KEEP,
                reason="Progression is withheld after a major execution failure.",
                evidence=trigger_assessment.evidence,
                confidence=Confidence.HIGH,
            )
        ]

    if trigger_soreness:
        return [
            EngineProposal(
                affected_session_id=next_workout.id,
                action=AdaptationAction.KEEP,
                reason="Progression is withheld because soreness overlaps the planned demand.",
                evidence=trigger_soreness,
                confidence=Confidence.HIGH,
            )
        ]

    if trigger_assessment.strong:
        return [
            EngineProposal(
                affected_session_id=next_workout.id,
                action=AdaptationAction.KEEP,
                reason="Strong execution is recognised, but one result is not enough to progress.",
                evidence=(*trigger_assessment.evidence, "One successful comparable session"),
                confidence=Confidence.HIGH,
            )
        ]
    if trigger_assessment.structured_evidence_required:
        return [
            EngineProposal(
                affected_session_id=next_workout.id,
                action=AdaptationAction.KEEP,
                reason="Structured execution evidence is insufficient for progression.",
                evidence=trigger_assessment.evidence,
                confidence=Confidence.MODERATE,
            )
        ]
    if trigger_assessment.successful:
        return [
            EngineProposal(
                affected_session_id=next_workout.id,
                action=AdaptationAction.KEEP,
                reason="Successful execution is recognised, but one result is not enough to progress.",
                evidence=("One successful comparable session",),
                confidence=Confidence.HIGH,
            )
        ]
    return []
