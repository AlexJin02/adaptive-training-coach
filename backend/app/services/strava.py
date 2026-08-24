from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.enums import PlanStatus, Sport
from app.services import application, serializers

RUN_SPORT_TYPES = {"RUN", "TRAILRUN", "VIRTUALRUN"}
REVIEWABLE_PLAN_STATUSES = {PlanStatus.PLANNED, PlanStatus.MODIFIED}
DETAIL_BACKFILL_LIMIT = 12


class StravaUnavailableError(RuntimeError):
    pass


_token_cache: dict[str, Any] = {}


@dataclass(frozen=True)
class StravaSyncResult:
    imported: list[models.ImportedRunningActivity]
    restored: list[models.ImportedRunningActivity]
    enriched: list[models.ImportedRunningActivity]


def is_configured() -> bool:
    settings = get_settings()
    refresh_ready = all(
        (settings.strava_client_id, settings.strava_client_secret, settings.strava_refresh_token)
    )
    return bool(settings.strava_access_token or refresh_ready)


def _access_token() -> str:
    settings = get_settings()
    now = int(datetime.now(UTC).timestamp())
    cached = _token_cache.get("access_token")
    if cached and int(_token_cache.get("expires_at") or 0) > now + 60:
        return str(cached)
    refresh_ready = all(
        (settings.strava_client_id, settings.strava_client_secret, settings.strava_refresh_token)
    )
    if refresh_ready:
        refresh_token = str(_token_cache.get("refresh_token") or settings.strava_refresh_token)
        try:
            response = httpx.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": settings.strava_client_id,
                    "client_secret": settings.strava_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            _token_cache.update(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token", refresh_token),
                expires_at=payload.get("expires_at", now + 3600),
            )
            return str(payload["access_token"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise StravaUnavailableError(
                "Strava authentication failed. Check the backend Strava credentials."
            ) from exc
    if settings.strava_access_token:
        return settings.strava_access_token
    raise StravaUnavailableError(
        "Strava sync is not configured. Add a Strava access token or refresh credentials to .env."
    )


def _get_json(path: str, *, params: dict[str, Any] | None = None) -> Any:
    try:
        response = httpx.get(
            f"https://www.strava.com/api/v3{path}",
            headers={"Authorization": f"Bearer {_access_token()}"},
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except StravaUnavailableError:
        raise
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise StravaUnavailableError(
            "Strava could not be reached. No imported or completed workout data was changed."
        ) from exc


def _parse_local_start(value: Any) -> tuple[date, time | None]:
    if not isinstance(value, str) or not value:
        raise ValueError("Strava activity is missing start_date_local")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.date(), parsed.time().replace(tzinfo=None, microsecond=0)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _whole_number(value: Any) -> int | None:
    parsed = _number(value)
    return round(parsed) if parsed is not None else None


def _running_cadence(value: Any) -> float | None:
    """Strava's running API cadence is per foot; the product displays total steps/minute."""

    parsed = _number(value)
    return parsed * 2 if parsed is not None else None


def _suggested_type(activity: dict[str, Any]) -> str:
    # Strava run workout_type: 1 race, 2 long run, 3 workout; 0/None is an ordinary run.
    return {1: "RACE", 2: "LONG_RUN", 3: "QUALITY"}.get(
        _whole_number(activity.get("workout_type")), "EASY"
    )


def _normalise_laps(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        distance_m = _number(row.get("distance")) or 0
        distance_km = distance_m / 1000
        elapsed = _whole_number(row.get("elapsed_time"))
        moving = _number(row.get("moving_time"))
        pace = moving / distance_km if moving is not None and distance_km > 0 else None
        output.append(
            {
                "lap_index": _whole_number(row.get("lap_index")) or position,
                "distance_km": round(distance_km, 3),
                "elapsed_time_seconds": elapsed,
                "pace_seconds_per_km": pace,
                "average_hr": _whole_number(row.get("average_heartrate")),
                "cadence": _running_cadence(row.get("average_cadence")),
            }
        )
    return output


def _normalise_best_efforts(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        distance_m = _number(row.get("distance"))
        elapsed = _whole_number(row.get("elapsed_time"))
        if distance_m is None or distance_m <= 0 or elapsed is None or elapsed <= 0:
            continue
        output.append(
            {
                "name": str(row.get("name") or "Best effort")[:80],
                "distance_m": round(distance_m, 1),
                "elapsed_time_seconds": elapsed,
                "moving_time_seconds": _whole_number(row.get("moving_time")),
            }
        )
    return output


def _match_planned_session(
    db: Session, activity_date: date, start_time: time | None
) -> models.PlannedSession | None:
    rows = list(
        db.scalars(
            select(models.PlannedSession)
            .where(
                models.PlannedSession.session_date == activity_date,
                models.PlannedSession.sport == Sport.RUNNING,
                models.PlannedSession.status.in_(REVIEWABLE_PLAN_STATUSES),
                ~models.PlannedSession.id.in_(
                    select(models.CompletedSession.planned_session_id).where(
                        models.CompletedSession.planned_session_id.is_not(None)
                    )
                ),
                ~models.PlannedSession.id.in_(
                    select(models.ImportedRunningActivity.planned_session_id).where(
                        models.ImportedRunningActivity.needs_review.is_(True),
                        models.ImportedRunningActivity.planned_session_id.is_not(None),
                    )
                ),
            )
            .order_by(models.PlannedSession.start_time, models.PlannedSession.id)
        )
    )
    if not rows:
        return None
    if start_time is None:
        return rows[0]
    target = start_time.hour * 60 + start_time.minute
    return min(
        rows,
        key=lambda item: (
            abs((item.start_time.hour * 60 + item.start_time.minute) - target)
            if item.start_time
            else 24 * 60,
            item.id,
        ),
    )


def _is_run(activity: dict[str, Any]) -> bool:
    sport_type = str(activity.get("sport_type") or activity.get("type") or "")
    return sport_type.upper().replace("_", "") in RUN_SPORT_TYPES


def ingest_activities(
    db: Session,
    activities: list[dict[str, Any]],
    laps_by_activity: dict[str, list[dict[str, Any]]] | None = None,
    details_by_activity: dict[str, dict[str, Any]] | None = None,
) -> list[models.ImportedRunningActivity]:
    laps_by_activity = laps_by_activity or {}
    details_by_activity = details_by_activity or {}
    imported: list[models.ImportedRunningActivity] = []
    for activity in activities:
        if not _is_run(activity) or activity.get("id") is None:
            continue
        external_id = str(activity["id"])
        existing = db.scalar(
            select(models.ImportedRunningActivity).where(
                models.ImportedRunningActivity.provider == "STRAVA",
                models.ImportedRunningActivity.external_activity_id == external_id,
            )
        )
        if existing:
            continue
        activity_date, start_time = _parse_local_start(activity.get("start_date_local"))
        distance_km = (_number(activity.get("distance")) or 0) / 1000
        elapsed = _whole_number(activity.get("elapsed_time"))
        moving = _whole_number(activity.get("moving_time"))
        if elapsed is None or elapsed <= 0:
            continue
        planned = _match_planned_session(db, activity_date, start_time)
        suggested_type = planned.workout_type if planned else _suggested_type(activity)
        title = (
            planned.title
            if planned
            else str(activity.get("name") or suggested_type.replace("_", " ").title())
        )
        pace = moving / distance_km if moving is not None and distance_km > 0 else None
        detail = details_by_activity.get(external_id)
        item = models.ImportedRunningActivity(
            athlete_id=1,
            provider="STRAVA",
            external_activity_id=external_id,
            activity_date=activity_date,
            start_time=start_time,
            title=title[:200],
            suggested_session_type=suggested_type,
            distance_km=distance_km,
            elapsed_time_seconds=elapsed,
            moving_time_seconds=moving,
            average_pace_seconds_per_km=pace,
            average_hr=_whole_number(activity.get("average_heartrate")),
            maximum_hr=_whole_number(activity.get("max_heartrate")),
            elevation_m=_number(activity.get("total_elevation_gain")),
            cadence=_running_cadence(activity.get("average_cadence")),
            laps=_normalise_laps(laps_by_activity.get(external_id, [])),
            best_efforts=_normalise_best_efforts(detail.get("best_efforts")) if detail else [],
            detail_synced_at=datetime.now(UTC) if detail else None,
            planned_session_id=planned.id if planned else None,
            needs_review=True,
        )
        db.add(item)
        db.flush()
        imported.append(item)
    db.commit()
    return imported


def sync_runs(db: Session) -> StravaSyncResult:
    payload = _get_json("/athlete/activities", params={"page": 1, "per_page": 50})
    if not isinstance(payload, list):
        raise StravaUnavailableError("Strava returned an invalid activity list.")
    activities = [row for row in payload if isinstance(row, dict) and _is_run(row)]
    laps: dict[str, list[dict[str, Any]]] = {}
    details: dict[str, dict[str, Any]] = {}
    existing_by_id = {
        row.external_activity_id: row
        for row in db.scalars(
            select(models.ImportedRunningActivity).where(
                models.ImportedRunningActivity.provider == "STRAVA"
            )
        )
    }
    detail_candidates = [
        activity
        for activity in activities
        if (existing := existing_by_id.get(str(activity.get("id")))) is None
        or existing.detail_synced_at is None
    ][:DETAIL_BACKFILL_LIMIT]
    for activity in detail_candidates:
        external_id = str(activity.get("id"))
        try:
            detail_payload = _get_json(
                f"/activities/{external_id}", params={"include_all_efforts": "false"}
            )
        except StravaUnavailableError:
            continue
        if isinstance(detail_payload, dict):
            details[external_id] = detail_payload
    for activity in activities:
        external_id = str(activity.get("id"))
        if external_id in existing_by_id:
            continue
        detail = details.get(external_id)
        if detail is not None:
            lap_payload = detail.get("laps") or []
        else:
            try:
                lap_payload = _get_json(f"/activities/{external_id}/laps")
            except StravaUnavailableError:
                lap_payload = []
        laps[external_id] = lap_payload if isinstance(lap_payload, list) else []
    imported = ingest_activities(db, activities, laps, details)
    restored: list[models.ImportedRunningActivity] = []
    enriched: list[models.ImportedRunningActivity] = []
    for activity in activities:
        existing = existing_by_id.get(str(activity.get("id")))
        if existing is None or existing.needs_review:
            continue
        completed = (
            db.get(models.CompletedSession, existing.completed_session_id)
            if existing.completed_session_id
            else None
        )
        if completed is not None:
            continue
        existing.completed_session_id = None
        existing.needs_review = True
        existing.reviewed_at = None
        restored.append(existing)
    for external_id, detail in details.items():
        existing = existing_by_id.get(external_id)
        if existing is None:
            continue
        existing.best_efforts = _normalise_best_efforts(detail.get("best_efforts"))
        existing.detail_synced_at = datetime.now(UTC)
        enriched.append(existing)
    if restored or enriched:
        db.commit()
    return StravaSyncResult(imported=imported, restored=restored, enriched=enriched)


def _serialise(item: models.ImportedRunningActivity, db: Session) -> dict[str, Any]:
    planned = (
        db.get(models.PlannedSession, item.planned_session_id) if item.planned_session_id else None
    )
    return {
        "id": item.id,
        "provider": item.provider,
        "external_activity_id": item.external_activity_id,
        "date": item.activity_date.isoformat(),
        "start_time": item.start_time.isoformat(timespec="minutes") if item.start_time else None,
        "title": item.title,
        "suggested_session_type": item.suggested_session_type,
        "distance_km": item.distance_km,
        "elapsed_time_seconds": item.elapsed_time_seconds,
        "moving_time_seconds": item.moving_time_seconds,
        "average_pace_seconds_per_km": item.average_pace_seconds_per_km,
        "average_hr": item.average_hr,
        "max_hr": item.maximum_hr,
        "elevation_m": item.elevation_m,
        "cadence": item.cadence,
        "laps": item.laps or [],
        "best_efforts": item.best_efforts or [],
        "detail_synced_at": (item.detail_synced_at.isoformat() if item.detail_synced_at else None),
        "needs_review": item.needs_review,
        "planned_session": serializers.planned_session(planned) if planned else None,
        "completed_session_id": item.completed_session_id,
        "imported_at": item.imported_at.isoformat(),
    }


def inbox(db: Session) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(models.ImportedRunningActivity)
            .where(models.ImportedRunningActivity.needs_review.is_(True))
            .order_by(
                models.ImportedRunningActivity.activity_date.desc(),
                models.ImportedRunningActivity.start_time.desc(),
                models.ImportedRunningActivity.id.desc(),
            )
        )
    )
    return [_serialise(row, db) for row in rows]


def complete_review(db: Session, imported_id: int, values: dict[str, Any]) -> dict[str, Any]:
    item = db.get(models.ImportedRunningActivity, imported_id)
    if item is None:
        raise LookupError("imported run not found")
    if not item.needs_review:
        if item.completed_session_id:
            return serializers.completed_session(
                application.get_completed_session(db, item.completed_session_id)
            )
        raise ValueError("This imported run has already been reviewed")
    session_type = str(values["session_type"])
    if session_type not in {"EASY", "LONG_RUN", "QUALITY", "RACE"}:
        raise ValueError("Choose Easy, Long Run, Quality, or Race")
    feedback = str(values.get("subjective_feedback_text") or "").strip() or None
    source = str(values.get("subjective_feedback_source") or "NONE")
    if not feedback:
        source = "NONE"
    try:
        completed = application.record_completed_session(
            db,
            {
                "date": item.activity_date,
                "start_time": item.start_time,
                "workout_kind": "RUNNING",
                "session_type": session_type,
                "title": values.get("title") or item.title,
                "duration_minutes": item.elapsed_time_seconds / 60,
                "rpe": values["rpe"],
                "planned_session_id": item.planned_session_id,
                "distance_km": item.distance_km,
                "average_pace_seconds_per_km": item.average_pace_seconds_per_km,
                "average_hr": item.average_hr,
                "max_hr": item.maximum_hr,
                "elevation_m": item.elevation_m,
                "cadence": item.cadence,
                "splits": item.laps or [],
                "subjective_feedback_text": feedback,
                "subjective_feedback_source": source,
            },
            commit=False,
        )
        item.needs_review = False
        item.completed_session_id = completed.id
        item.reviewed_at = datetime.now(UTC)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return serializers.completed_session(completed)
