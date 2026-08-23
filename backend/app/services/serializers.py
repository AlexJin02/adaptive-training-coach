from __future__ import annotations

from typing import Any

from app import models
from app.enums import FatigueDomain, ReadinessLabel, Sport
from app.training_engine.config import (
    HALF_LIFE_HOURS,
    HIGH_FATIGUE_THRESHOLD,
    MODERATE_FATIGUE_THRESHOLD,
    VERY_HIGH_FATIGUE_THRESHOLD,
)


def _fatigue_display_label(value: float) -> str:
    if value >= VERY_HIGH_FATIGUE_THRESHOLD:
        return "VERY_HIGH"
    if value >= HIGH_FATIGUE_THRESHOLD:
        return "HIGH"
    if value >= MODERATE_FATIGUE_THRESHOLD:
        return "MODERATE"
    return "LOW"


def athlete_profile(item: models.AthleteProfile) -> dict[str, Any]:
    return {
        "id": item.id,
        "display_name": item.display_name,
        "timezone": item.timezone,
        "current_half_marathon_seconds": item.current_half_marathon_seconds,
        "current_monthly_km": item.baseline_monthly_distance_km,
        "long_term_monthly_km": item.long_term_monthly_distance_km,
        "stable_weekly_min_km": item.stable_weekly_distance_min_km,
        "stable_weekly_max_km": item.stable_weekly_distance_max_km,
        "half_marathon_primary_goal_seconds": item.half_marathon_goal_seconds,
        "half_marathon_stretch_goal_seconds": item.half_marathon_stretch_seconds,
        "marathon_goal_seconds": item.marathon_goal_seconds,
        "tb2_verified_grade": item.tb2_verified_grade,
        "tb2_estimated_grade": item.tb2_estimated_grade,
        "top_rope_grade": item.top_rope_current_grade,
        "tb2_long_term_goal": item.tb2_long_term_goal,
        "outdoor_boulder_goal": item.outdoor_boulder_goal,
        "bouldering_goal": item.tb2_long_term_goal,
        "route_goal": item.route_long_term_goal,
        "running_phase": item.running_phase.value,
        "climbing_phase": item.climbing_phase.value,
    }


PROFILE_INPUT_MAP = {
    "current_monthly_km": "baseline_monthly_distance_km",
    "long_term_monthly_km": "long_term_monthly_distance_km",
    "stable_weekly_min_km": "stable_weekly_distance_min_km",
    "stable_weekly_max_km": "stable_weekly_distance_max_km",
    "half_marathon_primary_goal_seconds": "half_marathon_goal_seconds",
    "half_marathon_stretch_goal_seconds": "half_marathon_stretch_seconds",
    "top_rope_grade": "top_rope_current_grade",
    "bouldering_goal": "tb2_long_term_goal",
    "route_goal": "route_long_term_goal",
}


def goal(item: models.Goal) -> dict[str, Any]:
    return {
        "id": item.id,
        "goal_type": item.goal_type.value,
        "description": item.description,
        "target_value": item.target_value,
        "target_date": item.target_date.isoformat() if item.target_date else None,
        "current_status": item.current_status,
        "notes": item.notes,
        "is_current": item.is_current,
    }


def planned_session(item: models.PlannedSession) -> dict[str, Any]:
    target_rpe = item.target_rpe_max if item.target_rpe_max is not None else item.target_rpe_min
    return {
        "id": item.id,
        "date": item.session_date.isoformat(),
        "start_time": item.start_time.isoformat(timespec="minutes") if item.start_time else None,
        "workout_kind": item.sport.value,
        "session_type": item.workout_type,
        "title": item.title,
        "description": item.description,
        "planned_duration_minutes": item.planned_duration_minutes,
        "planned_distance_km": item.planned_distance_km,
        "target_rpe": target_rpe,
        "priority": item.priority.value,
        "status": item.status.value,
        "original_session_id": item.moved_from_id or item.replaced_session_id,
        "is_demo": item.is_demo,
        "structured_blocks": item.structured_blocks,
    }


def completed_session(item: models.CompletedSession) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": item.id,
        "date": item.session_date.isoformat(),
        "start_time": item.start_time.isoformat(timespec="minutes") if item.start_time else None,
        "workout_kind": item.sport.value,
        "session_type": item.workout_type,
        "title": item.workout_type,
        "duration_minutes": item.duration_minutes,
        "distance_km": None,
        "rpe": item.rpe,
        "srpe_load": item.srpe_load,
        "average_pace_seconds_per_km": None,
        "average_hr": None,
        "max_hr": None,
        "elevation_m": None,
        "cadence": None,
        "power_w": None,
        "gym_or_crag": None,
        "hard_attempts": None,
        "max_attempted": None,
        "max_sent": None,
        "splits": [],
        "interval_blocks": [],
        "climbing_attempts": [],
        "workout_name": None,
        "rounds": None,
        "result_time_seconds": None,
        "strength_sets": [],
        "strength": None,
        "notes": item.notes,
        "planned_session_id": item.planned_session_id,
        "ai_analysis": item.ai_analysis,
        "is_demo": item.is_demo,
    }
    if item.running:
        result.update(
            {
                "distance_km": item.running.distance_km,
                "average_pace_seconds_per_km": item.running.average_pace_seconds_per_km,
                "average_hr": item.running.average_hr,
                "max_hr": item.running.maximum_hr,
                "elevation_m": item.running.elevation_m,
                "cadence": item.running.cadence,
                "power_w": item.running.power_watts,
                "splits": item.running.splits or [],
                "interval_blocks": item.running.intervals or [],
            }
        )
    if item.climbing:
        result.update(
            {
                "gym_or_crag": item.climbing.gym_or_crag,
                "hard_attempts": item.climbing.hard_attempts,
                "max_attempted": item.climbing.maximum_attempted,
                "max_sent": item.climbing.maximum_sent,
                "climbing_attempts": [
                    {
                        "id": attempt.id,
                        "problem": attempt.problem,
                        "grade": attempt.grade,
                        "attempts": attempt.attempts,
                        "sent": attempt.sent,
                        "flash": attempt.flash,
                        "repeat": attempt.repeat,
                        "project": attempt.project,
                        "style_tags": attempt.style_tags or [],
                    }
                    for attempt in item.climbing.attempts
                ],
            }
        )
    if item.strength:
        strength_sets = [
            {
                "id": row.id,
                "exercise": row.exercise,
                "sets": row.set_count,
                "set_count": row.set_count,
                "reps": row.reps,
                "load": row.load_kg,
                "load_kg": row.load_kg,
                "rpe": row.rpe,
                "rir": row.rir,
                "tags": row.tags or [],
            }
            for row in item.strength.sets
        ]
        strength = {
            "workout_name": item.strength.workout_name,
            "rounds": item.strength.rounds,
            "result_time_seconds": item.strength.result_time_seconds,
            "sets": strength_sets,
        }
        result.update(
            {
                "workout_name": item.strength.workout_name,
                "rounds": item.strength.rounds,
                "result_time_seconds": item.strength.result_time_seconds,
                "strength_sets": strength_sets,
                "strength": strength,
            }
        )
    return result


def tb2(item: models.TB2Benchmark) -> dict[str, Any]:
    return {
        "id": item.id,
        "date": item.benchmark_date.isoformat(),
        "board": item.board,
        "angle": item.angle_degrees,
        "verified_grade": item.verified_grade,
        "estimated_grade": item.estimated_grade,
        "notes": item.notes,
        "is_demo": item.is_demo,
    }


def gym_set(item: models.GymSet) -> dict[str, Any]:
    return {
        "id": item.id,
        "gym": item.gym,
        "start_date": item.start_date.isoformat(),
        "end_date": item.end_date.isoformat() if item.end_date else None,
        "notes": item.notes,
        "is_demo": item.is_demo,
        "progress": [
            {
                "colour": row.colour,
                "ordinal": row.ordinal,
                "sent_count": row.sent_count,
                "available_problem_count": row.available_problem_count,
            }
            for row in sorted(item.colours, key=lambda row: row.ordinal)
        ],
    }


def route_benchmark(item: models.RouteBenchmark | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "top_rope_verified_grade": item.top_rope_verified_grade,
        "lead_verified_grade": item.lead_verified_grade,
        "target_grade": item.target_grade,
        "last_updated": item.benchmark_date.isoformat(),
    }


def adaptation(item: models.AdaptationEvent, title: str = "Planned session") -> dict[str, Any]:
    return {
        "id": item.id,
        "session_id": item.affected_session_id,
        "session_title": title,
        "action": item.action.value,
        "original_plan": item.original_plan,
        "proposed_plan": item.proposed_plan,
        "reason": item.reason,
        "evidence": item.evidence,
        "confidence": item.confidence.value,
        "source": item.source.value,
        "status": item.decision.value,
        "created_at": item.created_at.isoformat(),
    }


def fatigue_values(
    latent: dict[FatigueDomain, float],
    display: dict[FatigueDomain, float],
    calculated_at: str,
    half_lives: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "domain": domain.value,
            "latent_value": round(latent[domain], 3),
            "display_value": round(display[domain], 3),
            "display_label": _fatigue_display_label(display[domain]),
            "is_high": display[domain] >= HIGH_FATIGUE_THRESHOLD,
            "half_life_hours": (
                half_lives.get(domain.value, HALF_LIFE_HOURS[domain])
                if half_lives
                else HALF_LIFE_HOURS[domain]
            ),
            "updated_at": calculated_at,
        }
        for domain in FatigueDomain
    ]


def readiness_summary(
    *,
    sport: Sport,
    value: float,
    label: ReadinessLabel,
    components: dict[str, float],
    updated_at: str,
    explanation: str,
    good_threshold: float = 7.5,
    moderate_threshold: float = 5.0,
    subjective_delta: float = 0.0,
    local_soreness_penalty: float = 0.0,
    warnings: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    return {
        "sport": sport.value,
        "value": round(value, 2),
        "label": label.value,
        "components": [
            {
                "domain": name,
                "value": round(component, 2),
                "label": (
                    ReadinessLabel.GOOD.value
                    if component >= good_threshold
                    else ReadinessLabel.MODERATE.value
                    if component >= moderate_threshold
                    else ReadinessLabel.LOW.value
                ),
            }
            for name, component in components.items()
            if name in {domain.value for domain in FatigueDomain} | {"LOCAL_SORENESS"}
        ],
        "updated_at": updated_at,
        "explanation": explanation,
        "subjective_delta": round(subjective_delta, 3),
        "local_soreness_penalty": round(local_soreness_penalty, 3),
        "warnings": list(warnings),
    }
