from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import pow

from app.enums import FatigueDomain
from app.training_engine.config import HALF_LIFE_HOURS


@dataclass(frozen=True)
class StressEvent:
    occurred_at: datetime
    stresses: dict[FatigueDomain, float]


@dataclass(frozen=True)
class FatigueResult:
    calculated_at: datetime
    latent: dict[FatigueDomain, float]
    display: dict[FatigueDomain, float]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def decay(value: float, elapsed_hours: float, half_life_hours: float) -> float:
    if elapsed_hours < 0:
        raise ValueError("elapsed_hours cannot be negative")
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    return value * pow(0.5, elapsed_hours / half_life_hours)


def calculate_fatigue(
    events: list[StressEvent],
    *,
    as_of: datetime | None = None,
    half_lives: dict[FatigueDomain, float] | None = None,
) -> FatigueResult:
    calculation_time = _aware(as_of or datetime.now(UTC))
    configured_half_lives = half_lives or HALF_LIFE_HOURS
    latent = {domain: 0.0 for domain in FatigueDomain}

    # Closed-form replay is equivalent to sequential decay-and-add, handles backdated edits,
    # and deliberately leaves latent fatigue uncapped before persistence.
    for event in events:
        occurred_at = _aware(event.occurred_at)
        if occurred_at > calculation_time:
            continue
        elapsed_hours = (calculation_time - occurred_at).total_seconds() / 3600.0
        for domain, stress in event.stresses.items():
            if stress < 0:
                raise ValueError("domain stress cannot be negative")
            latent[domain] += decay(stress, elapsed_hours, configured_half_lives[domain])

    return FatigueResult(
        calculated_at=calculation_time,
        latent=latent,
        display={domain: min(10.0, value) for domain, value in latent.items()},
    )
