from __future__ import annotations

from dataclasses import dataclass

from app.enums import FatigueDomain, Sport
from app.training_engine.config import (
    ALGORITHM_VERSION,
    CLIMBING_GENERAL,
    CLIMBING_PROFILES,
    CROSSFIT_PROFILE,
    DEFAULT_STRENGTH_PROFILE,
    HARD_ATTEMPT_INCREMENT,
    HARD_ATTEMPT_MULTIPLIER_CAP,
    HARD_ATTEMPT_THRESHOLD,
    MAX_BASE_STRESS,
    MOBILITY_PROFILE,
    RUNNING_EASY,
    RUNNING_PROFILES,
    STRENGTH_EXERCISE_PROFILES,
    STRESS_DIVISOR,
)


@dataclass(frozen=True)
class DomainStress:
    domain: FatigueDomain
    coefficient: float
    multiplier: float
    stress: float


@dataclass(frozen=True)
class SessionLoadResult:
    srpe_load: float | None
    base_stress: float | None
    domain_stresses: tuple[DomainStress, ...]
    algorithm_version: str = ALGORITHM_VERSION


def hard_attempt_multiplier(
    hard_attempts: int | None,
    *,
    threshold: int = HARD_ATTEMPT_THRESHOLD,
    increment: float = HARD_ATTEMPT_INCREMENT,
    cap: float = HARD_ATTEMPT_MULTIPLIER_CAP,
) -> float:
    if hard_attempts is None:
        return 1.0
    return min(
        cap,
        1.0 + max(0, hard_attempts - threshold) * increment,
    )


def _strength_profile(exercises: list[str]) -> dict[FatigueDomain, float]:
    if not exercises:
        return DEFAULT_STRENGTH_PROFILE.copy()
    resolved: list[dict[FatigueDomain, float]] = []
    for exercise in exercises:
        normalized = exercise.strip().lower()
        match = next(
            (
                value
                for key, value in sorted(
                    STRENGTH_EXERCISE_PROFILES.items(),
                    key=lambda item: len(item[0]),
                    reverse=True,
                )
                if key in normalized
            ),
            DEFAULT_STRENGTH_PROFILE,
        )
        resolved.append(match)
    # Max aggregation captures all interference domains without multiplying one session's base load.
    return {domain: max(profile[domain] for profile in resolved) for domain in FatigueDomain}


def demand_profile(
    sport: Sport,
    workout_type: str,
    exercises: list[str] | None = None,
) -> dict[FatigueDomain, float]:
    normalized = workout_type.strip().lower()
    if sport == Sport.RUNNING:
        return RUNNING_PROFILES.get(normalized, RUNNING_EASY).copy()
    if sport == Sport.CLIMBING:
        return CLIMBING_PROFILES.get(normalized, CLIMBING_GENERAL).copy()
    if sport == Sport.STRENGTH:
        return _strength_profile([workout_type, *(exercises or [])])
    if sport == Sport.CROSSFIT_CONDITIONING:
        return CROSSFIT_PROFILE.copy()
    return MOBILITY_PROFILE.copy()


def calculate_session_load(
    *,
    sport: Sport,
    workout_type: str,
    duration_minutes: float,
    rpe: float | None,
    hard_attempts: int | None = None,
    exercises: list[str] | None = None,
    stress_divisor: float = STRESS_DIVISOR,
    max_base_stress: float = MAX_BASE_STRESS,
    hard_attempt_threshold: int = HARD_ATTEMPT_THRESHOLD,
    hard_attempt_increment: float = HARD_ATTEMPT_INCREMENT,
    hard_attempt_cap: float = HARD_ATTEMPT_MULTIPLIER_CAP,
) -> SessionLoadResult:
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if rpe is None:
        return SessionLoadResult(srpe_load=None, base_stress=None, domain_stresses=())
    if not 1 <= rpe <= 10:
        raise ValueError("rpe must be between 1 and 10")

    srpe_load = duration_minutes * rpe
    if stress_divisor <= 0 or max_base_stress <= 0:
        raise ValueError("stress configuration must be positive")
    base_stress = min(max_base_stress, srpe_load / stress_divisor)
    coefficients = demand_profile(sport, workout_type, exercises)
    attempt_multiplier = hard_attempt_multiplier(
        hard_attempts,
        threshold=hard_attempt_threshold,
        increment=hard_attempt_increment,
        cap=hard_attempt_cap,
    )
    domain_stresses: list[DomainStress] = []
    for domain in FatigueDomain:
        coefficient = coefficients[domain]
        multiplier = (
            attempt_multiplier
            if sport == Sport.CLIMBING
            and domain in {FatigueDomain.FINGER_FOREARM, FatigueDomain.NEURAL}
            else 1.0
        )
        domain_stresses.append(
            DomainStress(
                domain=domain,
                coefficient=coefficient,
                multiplier=multiplier,
                stress=base_stress * coefficient * multiplier,
            )
        )
    return SessionLoadResult(
        srpe_load=srpe_load,
        base_stress=base_stress,
        domain_stresses=tuple(domain_stresses),
    )
