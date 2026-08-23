from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MileageDecision:
    action: str
    target_min_km: float
    target_max_km: float
    reason: str


def mileage_progression_band(current_weekly_km: float) -> tuple[float, float]:
    if current_weekly_km < 40:
        return (0.05, 0.08)
    if current_weekly_km <= 70:
        return (0.03, 0.06)
    return (0.02, 0.04)


def decide_mileage_target(
    *,
    current_weekly_km: float,
    completion_rate: float,
    easy_rpe_stable: bool,
    long_run_tolerated: bool,
    readiness_acceptable: bool,
    persistent_soreness: bool,
    quality_session_performance_stable: bool | None = None,
) -> MileageDecision:
    if persistent_soreness or not readiness_acceptable:
        return MileageDecision(
            "DELOAD",
            round(current_weekly_km * 0.80, 1),
            round(current_weekly_km * 0.90, 1),
            "Recovery evidence does not support building volume.",
        )
    if (
        completion_rate < 0.85
        or not easy_rpe_stable
        or not long_run_tolerated
        or quality_session_performance_stable is not True
    ):
        return MileageDecision(
            "HOLD",
            round(current_weekly_km * 0.95, 1),
            round(current_weekly_km * 1.02, 1),
            "Current volume or quality-session stability needs more evidence before progression.",
        )
    low, high = mileage_progression_band(current_weekly_km)
    return MileageDecision(
        "BUILD",
        round(current_weekly_km * (1 + low), 1),
        round(current_weekly_km * (1 + high), 1),
        "Completion, easy effort, stable quality execution, long-run tolerance and readiness "
        "support a conservative build.",
    )
