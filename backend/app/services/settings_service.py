from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services import core


def get_app_settings(db: Session) -> dict[str, Any]:
    settings = get_settings()
    profile = core.get_profile(db)
    stored = {item.key: item.value for item in db.scalars(select(models.AppSetting))}
    demo_data_present = bool(
        db.scalar(
            select(models.CompletedSession.id)
            .where(models.CompletedSession.is_demo.is_(True))
            .limit(1)
        )
    )
    return {
        "gym_name": stored.get("gym_name", profile.home_gym_name),
        "grade_display": stored.get("grade_display", "BOTH"),
        "retain_screenshots": stored.get("retain_screenshots", settings.retain_raw_screenshots),
        "retain_audio": stored.get("retain_audio", settings.retain_raw_audio),
        "database_path": settings.database_url.removeprefix("sqlite:///"),
        "demo_data_present": demo_data_present,
        "engine": core.engine_configuration(db),
    }


def update_app_settings(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    if "gym_name" in values:
        core.update_profile(db, {"home_gym_name": values["gym_name"]})
    if "engine" in values:
        supplied_engine = values["engine"]
        current_engine = core.engine_configuration(db)
        engine_values = {**current_engine, **supplied_engine}
        supplied_half_lives = supplied_engine.get("half_lives")
        engine_values["half_lives"] = {
            **current_engine["half_lives"],
            **(supplied_half_lives if isinstance(supplied_half_lives, dict) else {}),
        }
        values["engine"] = engine_values
        _validate_engine(engine_values)
    for key, value in values.items():
        item = db.get(models.AppSetting, key)
        if item is None:
            db.add(models.AppSetting(key=key, value=value))
        else:
            item.value = value
    db.commit()
    return get_app_settings(db)


def _validate_engine(engine_values: dict[str, Any]) -> None:
    positive = ("base_stress_divisor", "base_stress_cap", "hard_attempt_cap")
    if any(float(engine_values.get(key, 1)) <= 0 for key in positive):
        raise ValueError("Engine stress constants must be positive")
    if float(engine_values.get("hard_attempt_increment", 0)) < 0:
        raise ValueError("Hard-attempt increment cannot be negative")
    good = float(engine_values.get("readiness_good_threshold", 7.5))
    moderate = float(engine_values.get("readiness_moderate_threshold", 5.0))
    if not 0 <= moderate < good <= 10:
        raise ValueError("Readiness thresholds must satisfy 0 <= MODERATE < GOOD <= 10")
    if any(float(value) <= 0 for value in engine_values.get("half_lives", {}).values()):
        raise ValueError("Fatigue half-lives must be positive")
