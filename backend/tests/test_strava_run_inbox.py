from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services import application, reporting, strava


def _activity(activity_id: int, *, start: str = "2026-08-24T07:15:00") -> dict[str, Any]:
    return {
        "id": activity_id,
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date_local": start,
        "distance": 10_000,
        "elapsed_time": 3_100,
        "moving_time": 3_000,
        "average_heartrate": 148.4,
        "max_heartrate": 171.6,
        "total_elevation_gain": 82,
        "average_cadence": 87.1,
        "workout_type": 3,
    }


def _laps() -> list[dict[str, Any]]:
    return [
        {
            "lap_index": 1,
            "distance": 1_000,
            "elapsed_time": 305,
            "moving_time": 300,
            "average_heartrate": 145,
            "average_cadence": 86.5,
        },
        {
            "lap_index": 2,
            "distance": 1_000,
            "elapsed_time": 298,
            "moving_time": 294,
            "average_heartrate": 151,
            "average_cadence": 88,
        },
    ]


def _detail() -> dict[str, Any]:
    return {
        "laps": _laps(),
        "best_efforts": [
            {
                "name": "10K",
                "distance": 10_000,
                "elapsed_time": 2_999,
                "moving_time": 2_999,
            }
        ],
    }


def test_strava_run_review_links_plan_laps_feedback_calendar_and_report(
    client, monkeypatch
) -> None:  # noqa: ANN001
    plan = client.post(
        "/api/v1/planned-sessions",
        json={
            "date": "2026-08-24",
            "start_time": "07:00:00",
            "workout_kind": "RUNNING",
            "session_type": "QUALITY",
            "title": "Threshold 4 x 8",
            "planned_duration_minutes": 60,
            "planned_distance_km": 11,
            "target_rpe": 7,
            "structured_blocks": [{"label": "Main", "raw_text": "4 x 8 min threshold"}],
        },
    ).json()

    def fake_sync(db: Session):  # noqa: ANN202
        imported = strava.ingest_activities(db, [_activity(987654)], {"987654": _laps()})
        return strava.StravaSyncResult(imported=imported, restored=[], enriched=[])

    monkeypatch.setattr(strava, "sync_runs", fake_sync)
    synced = client.post("/api/v1/integrations/strava/sync")
    assert synced.status_code == 200
    assert synced.json()["imported"] == 1
    imported = synced.json()["items"][0]
    assert imported["needs_review"] is True
    assert imported["suggested_session_type"] == "QUALITY"
    assert imported["title"] == "Threshold 4 x 8"
    assert imported["cadence"] == 174.2
    assert imported["planned_session"]["id"] == plan["id"]
    assert imported["laps"][0] == {
        "lap_index": 1,
        "distance_km": 1.0,
        "elapsed_time_seconds": 305,
        "pace_seconds_per_km": 300.0,
        "average_hr": 145,
        "cadence": 173.0,
    }
    today_before_review = client.get("/api/v1/today?date=2026-08-24").json()
    assert [run["id"] for run in today_before_review["imported_runs"]] == [imported["id"]]
    assert today_before_review["sessions"][0]["completed"] is None

    missing_rpe = client.post(
        f"/api/v1/integrations/strava/runs/{imported['id']}/complete",
        json={"session_type": "QUALITY"},
    )
    assert missing_rpe.status_code == 422
    assert client.get("/api/v1/integrations/strava/runs/inbox").json()["total"] == 1

    completed_response = client.post(
        f"/api/v1/integrations/strava/runs/{imported['id']}/complete",
        json={
            "session_type": "QUALITY",
            "title": "Threshold 4 x 8",
            "rpe": 7,
            "subjective_feedback_text": "心肺受控，最後兩圈腿有點沉。",
            "subjective_feedback_source": "VOICE",
        },
    )
    assert completed_response.status_code == 200
    completed = completed_response.json()
    assert completed["planned_session_id"] == plan["id"]
    assert completed["distance_km"] == 10
    assert completed["cadence"] == 174.2
    assert completed["rpe"] == 7
    assert completed["splits"][1]["pace_seconds_per_km"] == 294
    assert completed["subjective_feedback_source"] == "VOICE"
    assert completed["subjective_feedback_text"] == "心肺受控，最後兩圈腿有點沉。"
    assert client.get("/api/v1/integrations/strava/runs/inbox").json()["total"] == 0
    today_after_review = client.get("/api/v1/today?date=2026-08-24").json()
    assert today_after_review["imported_runs"] == []
    assert today_after_review["sessions"][0]["completed"]["id"] == completed["id"]

    calendar = client.get("/api/v1/calendar?start=2026-08-24&end=2026-08-24").json()["items"]
    linked = next(row for row in calendar if row["planned"]["id"] == plan["id"])
    assert linked["status"] == "COMPLETED"
    assert linked["planned"]["structured_blocks"][0]["label"] == "Main"
    assert linked["completed"]["subjective_feedback_text"].startswith("心肺受控")

    report = client.get("/api/v1/training-reports/weekly?week_start=2026-08-24").text
    assert "TITLE: Threshold 4 x 8" in report
    assert "LAPS:" in report
    assert "Lap 1: 1 km; elapsed 05:05; pace 5:00/km; avg HR 145; cadence 173" in report
    assert "心肺受控，最後兩圈腿有點沉。" in report


def test_standalone_strava_run_and_duplicate_sync(db) -> None:  # noqa: ANN001
    activity = _activity(123, start="2026-08-25T18:00:00")
    first = strava.ingest_activities(db, [activity], {"123": _laps()})
    second = strava.ingest_activities(db, [activity], {"123": _laps()})
    assert len(first) == 1
    assert second == []
    pending = strava.inbox(db)[0]
    assert pending["planned_session"] is None
    assert pending["suggested_session_type"] == "QUALITY"

    completed = strava.complete_review(
        db,
        pending["id"],
        {
            "session_type": "EASY",
            "rpe": 3,
            "subjective_feedback_text": None,
            "subjective_feedback_source": "NONE",
        },
    )
    assert completed["planned_session_id"] is None
    assert completed["session_type"] == "EASY"
    assert strava.inbox(db) == []


def test_sync_restores_recent_strava_run_when_completed_workout_was_deleted(
    db, monkeypatch
) -> None:  # noqa: ANN001
    activity = _activity(456, start="2026-08-26T06:30:00")
    imported = strava.ingest_activities(db, [activity], {"456": _laps()})[0]
    completed = strava.complete_review(
        db,
        imported.id,
        {
            "session_type": "EASY",
            "rpe": 4,
            "subjective_feedback_text": "Comfortable run.",
            "subjective_feedback_source": "TEXT",
        },
    )
    application.delete_completed_session(db, completed["id"])
    db.expire_all()

    monkeypatch.setattr(
        strava,
        "_get_json",
        lambda path, params=None: [activity] if path == "/athlete/activities" else _laps(),
    )
    result = strava.sync_runs(db)

    assert result.imported == []
    assert [row.id for row in result.restored] == [imported.id]
    restored = strava.inbox(db)
    assert len(restored) == 1
    assert restored[0]["external_activity_id"] == "456"
    assert restored[0]["completed_session_id"] is None

    second = strava.sync_runs(db)
    assert second.imported == []
    assert second.restored == []


def test_sync_backfills_strava_best_efforts_once_and_progress_uses_measured_data(
    db, monkeypatch
) -> None:  # noqa: ANN001
    activity = _activity(789, start="2026-08-24T07:15:00")
    imported = strava.ingest_activities(db, [activity], {"789": _laps()})[0]

    calls: list[str] = []

    def fake_get(path: str, params=None):  # noqa: ANN001, ANN202
        calls.append(path)
        return [activity] if path == "/athlete/activities" else _detail()

    monkeypatch.setattr(strava, "_get_json", fake_get)
    result = strava.sync_runs(db)
    assert result.imported == []
    assert [row.id for row in result.enriched] == [imported.id]
    assert result.enriched[0].best_efforts == [
        {
            "name": "10K",
            "distance_m": 10_000.0,
            "elapsed_time_seconds": 2_999,
            "moving_time_seconds": 2_999,
        }
    ]

    strava.complete_review(
        db,
        imported.id,
        {
            "session_type": "QUALITY",
            "title": "Threshold 10K",
            "rpe": 7,
            "subjective_feedback_text": None,
            "subjective_feedback_source": "NONE",
        },
    )
    progress = reporting.progress_data(db, "4w", today=date(2026, 8, 30))["running"]
    assert "estimated_10k" not in progress
    assert "strava_10k" not in progress
    assert "race_predictions" not in progress
    assert "lt2" not in progress

    strava.sync_runs(db)
    assert calls.count("/activities/789") == 1
