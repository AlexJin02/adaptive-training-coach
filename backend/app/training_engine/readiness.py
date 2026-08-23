from __future__ import annotations

from dataclasses import dataclass, field

from app.enums import FatigueDomain, ReadinessLabel
from app.training_engine.config import (
    CLIMBING_READINESS_WEIGHTS,
    ELBOW_SORENESS_PENALTY,
    FINGER_LOW_CAP_THRESHOLD,
    FINGER_MODERATE_CAP_THRESHOLD,
    FINGER_SORENESS_PENALTY,
    READINESS_GOOD_THRESHOLD,
    READINESS_MODERATE_THRESHOLD,
    RUNNING_READINESS_WEIGHTS,
    SHOULDER_SORENESS_PENALTY,
    SUBJECTIVE_DELTA_MAX,
    SUBJECTIVE_DELTA_MIN,
    SUBJECTIVE_WEIGHTS,
)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class RecoveryInputs:
    sleep_duration_hours: float | None = None
    sleep_quality: int | None = None
    energy: int | None = None
    stress: int | None = None
    general_soreness: float | None = None
    area_soreness: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReadinessResult:
    running_score: float
    running_label: ReadinessLabel
    climbing_score: float
    climbing_label: ReadinessLabel
    running_components: dict[str, float]
    climbing_components: dict[str, float]
    subjective_delta: float
    local_soreness_penalty: float
    warnings: tuple[str, ...]


def label_for_score(
    score: float,
    *,
    good_threshold: float = READINESS_GOOD_THRESHOLD,
    moderate_threshold: float = READINESS_MODERATE_THRESHOLD,
) -> ReadinessLabel:
    if score >= good_threshold:
        return ReadinessLabel.GOOD
    if score >= moderate_threshold:
        return ReadinessLabel.MODERATE
    return ReadinessLabel.LOW


def normalized_subjective_values(inputs: RecoveryInputs) -> dict[str, float]:
    values: dict[str, float] = {}
    if inputs.sleep_duration_hours is not None:
        # 7 h is neutral; 5 h or less = -1; 9 h or more = +1.
        values["sleep_duration_hours"] = clamp((inputs.sleep_duration_hours - 7.0) / 2.0, -1, 1)
    if inputs.sleep_quality is not None:
        values["sleep_quality"] = clamp((inputs.sleep_quality - 3.0) / 2.0, -1, 1)
    if inputs.energy is not None:
        values["energy"] = clamp((inputs.energy - 3.0) / 2.0, -1, 1)
    if inputs.stress is not None:
        values["stress"] = clamp((3.0 - inputs.stress) / 2.0, -1, 1)
    if inputs.general_soreness is not None:
        values["general_soreness"] = clamp((5.0 - inputs.general_soreness) / 5.0, -1, 1)
    return values


def subjective_recovery_delta(inputs: RecoveryInputs | None) -> float:
    if inputs is None:
        return 0.0
    values = normalized_subjective_values(inputs)
    if not values:
        return 0.0
    weight_sum = sum(SUBJECTIVE_WEIGHTS[key] for key in values)
    weighted_mean = (
        sum(SUBJECTIVE_WEIGHTS[key] * value for key, value in values.items()) / weight_sum
    )
    return clamp(weighted_mean, SUBJECTIVE_DELTA_MIN, SUBJECTIVE_DELTA_MAX)


def _weighted_fatigue(
    latent_fatigue: dict[FatigueDomain, float], weights: dict[FatigueDomain, float]
) -> float:
    return sum(weights[domain] * latent_fatigue.get(domain, 0.0) for domain in weights)


def calculate_readiness(
    latent_fatigue: dict[FatigueDomain, float],
    recovery: RecoveryInputs | None = None,
    *,
    good_threshold: float = READINESS_GOOD_THRESHOLD,
    moderate_threshold: float = READINESS_MODERATE_THRESHOLD,
) -> ReadinessResult:
    subjective_delta = subjective_recovery_delta(recovery)
    running_fatigue = _weighted_fatigue(latent_fatigue, RUNNING_READINESS_WEIGHTS)
    climbing_fatigue = _weighted_fatigue(latent_fatigue, CLIMBING_READINESS_WEIGHTS)

    areas = recovery.area_soreness if recovery else {}
    finger = clamp(float(areas.get("finger", 0.0)), 0, 10)
    elbow = clamp(float(areas.get("elbow", 0.0)), 0, 10)
    shoulder = clamp(float(areas.get("shoulder", 0.0)), 0, 10)
    local_penalty = (
        FINGER_SORENESS_PENALTY * finger
        + ELBOW_SORENESS_PENALTY * elbow
        + SHOULDER_SORENESS_PENALTY * shoulder
    )

    running_score = clamp(10.0 - running_fatigue + subjective_delta, 0.0, 10.0)
    climbing_score = clamp(10.0 - climbing_fatigue + subjective_delta - local_penalty, 0.0, 10.0)
    warnings: list[str] = []
    if finger >= FINGER_LOW_CAP_THRESHOLD:
        climbing_score = min(climbing_score, moderate_threshold - 0.01)
        warnings.append("Finger soreness is high; avoid finger-intensive training.")
    elif finger >= FINGER_MODERATE_CAP_THRESHOLD:
        climbing_score = min(climbing_score, good_threshold - 0.01)
        warnings.append("Finger soreness caps climbing readiness at MODERATE.")

    running_components = {
        domain.value: clamp(10.0 - latent_fatigue.get(domain, 0.0), 0.0, 10.0)
        for domain in RUNNING_READINESS_WEIGHTS
    }
    climbing_components = {
        domain.value: clamp(10.0 - latent_fatigue.get(domain, 0.0), 0.0, 10.0)
        for domain in CLIMBING_READINESS_WEIGHTS
    }
    climbing_components["LOCAL_SORENESS"] = clamp(10.0 - local_penalty, 0.0, 10.0)

    return ReadinessResult(
        running_score=running_score,
        running_label=label_for_score(
            running_score,
            good_threshold=good_threshold,
            moderate_threshold=moderate_threshold,
        ),
        climbing_score=climbing_score,
        climbing_label=label_for_score(
            climbing_score,
            good_threshold=good_threshold,
            moderate_threshold=moderate_threshold,
        ),
        running_components=running_components,
        climbing_components=climbing_components,
        subjective_delta=subjective_delta,
        local_soreness_penalty=local_penalty,
        warnings=tuple(warnings),
    )
