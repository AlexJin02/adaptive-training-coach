from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

WEEKLY_PLAN = """# TRAINING_WEEKLY_PLAN_V1

## PLAN_INFO
WEEK_START: 2026-09-07
WEEK_END: 2026-09-13
RUNNING_TARGET_KM: 42
CLIMBING_TARGET_SESSIONS: 1

## MONDAY
SESSION_1:
SPORT: REST
TITLE: Rest Day

## THURSDAY
SESSION_1:
SPORT: RUNNING
TYPE: QUALITY
TITLE: Nested intervals
TARGET_RPE: 7-8
WORKOUT:
- WARMUP: 3 km easy
- MAIN: 3 sets x 5 x 1 km @ 3:30/km, HR <= 176
- REP_RECOVERY: 90 sec jog
- SET_RECOVERY: 4 min easy jog
- COOLDOWN: 2 km easy
NOTES:
Keep every repetition controlled.

## SUNDAY
SESSION_1:
SPORT: CLIMBING
TYPE: BOARD
TITLE: Board session
BOARD: Tension Board 2
ANGLE: 40
DURATION_MIN: 100
TARGET_RPE: 8
WORKOUT:
- Main work around current hard grades

## END_PLAN
"""


MONTHLY_PLAN = """# TRAINING_MONTHLY_PLAN_V1

## PLAN_INFO
MONTH: 2026-10

## RUNNING
PHASE: Volume Build
MONTHLY_OBJECTIVE:
Build factual volume.
WEEKLY_DISTANCE_TARGETS:
- Week 1: 36 km
- Week 2: 39 km
- Week 3: 42 km
- Week 4: 35 km
QUALITY_GUIDANCE:
One quality session.
LONG_RUN_GUIDANCE:
Progress gradually.
OTHER_RUNNING_NOTES:
Keep most running easy.

## CLIMBING
PHASE: General Progression
SESSIONS_PER_WEEK: 3
TARGET_STRUCTURE:
- BOARD: 每周1次高质量尝试
- 2 Bouldering sessions
BOARD_FOCUS:
Current hard grades.
OTHER_CLIMBING_NOTES:
Quality movement.

## AUXILIARY
STRENGTH:
One short session.
MOBILITY:
As needed.

## GENERAL_NOTES
N/A
## END_PLAN
"""

EXTENDED_MONTHLY_PLAN = """# TRAINING_MONTHLY_PLAN_V1

## PLAN_INFO
MONTH: 2026-09

## RUNNING
PHASE: Volume Build
MONTHLY_OBJECTIVE:
Increase sustainable aerobic volume while maintaining controlled quality work.
RUNNING_SESSIONS_PER_WEEK: 4
RUNNING_SESSION_STRUCTURE:
- EASY: 2
- LONG_RUN: 1
- QUALITY: 1
- RACE: 0
WEEKLY_DISTANCE_TARGETS:
- Week 1: 36 km
- Week 2: 39 km
- Week 3: 42 km
- Week 4: 35 km
QUALITY_GUIDANCE:
One controlled threshold session per week.
LONG_RUN_GUIDANCE:
- Week 1: 14 km
- Week 2: 15 km
- Week 3: 16 km
- Week 4: 13 km
KEY_PRINCIPLES:
- Keep most running easy.
- Do not compensate for missed easy mileage.
OTHER_RUNNING_NOTES:
Week 4 is lower volume.

## CLIMBING
PHASE: Board Strength / General Progression
SESSIONS_PER_WEEK: 3
TARGET_STRUCTURE:
- BOARD: 1
- BOULDERING: 1
- BOULDERING_OR_SPORT_CLIMBING: 1
BOARD_FOCUS:
Hard Tension Board 2 climbing with long rests.
KEY_PRINCIPLES:
- Prioritise attempt quality over session duration.
OTHER_CLIMBING_NOTES:
Maintain technical volume.

## AUXILIARY
STRENGTH:
1-2 short supporting sessions per week.
MOBILITY:
As needed.

## GENERAL_NOTES
Hold progression when recovery is poor.

## END_PLAN
"""


def test_primary_session_types_are_normalised_and_unknown_rejected(client: TestClient) -> None:
    logged = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "threshold",
            "title": "4 x 8 min",
            "duration_minutes": 50,
            "rpe": 7,
        },
    )
    assert logged.status_code == 201
    assert logged.json()["session_type"] == "QUALITY"
    assert logged.json()["title"] == "4 x 8 min"
    assert logged.json()["srpe_load"] is None
    assert logged.json()["domain_stresses"] == [] if "domain_stresses" in logged.json() else True

    invalid = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "mystery",
            "duration_minutes": 20,
        },
    )
    assert invalid.status_code == 422


def test_climbing_board_and_send_counts_round_trip(client: TestClient) -> None:
    response = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "CLIMBING",
            "session_type": "BOARD",
            "title": "TB2 session",
            "duration_minutes": 90,
            "board_name": "Tension Board 2",
            "angle": 40,
            "climbing_attempts": [{"grade": "6C+", "attempts": 8, "send_count": 2}],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["board_name"] == "Tension Board 2"
    assert body["angle"] == 40
    assert body["climbing_attempts"][0]["send_count"] == 2


def test_weekly_report_is_fixed_factual_markdown_and_keeps_feedback(client: TestClient) -> None:
    week_start = date(2026, 8, 17)
    response = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": "2026-08-18",
            "workout_kind": "RUNNING",
            "session_type": "QUALITY",
            "title": "Threshold 4 x 8 min",
            "duration_minutes": 53.7,
            "distance_km": 10.8,
            "average_hr": 164,
            "max_hr": 181,
            "rpe": 7,
            "interval_blocks": [
                {"segment_kind": "WARMUP", "raw_text": "15 min easy"},
                {"segment_kind": "INTERVAL", "raw_text": "4 x 8 min @ 4:20/km"},
            ],
            "subjective_feedback_text": "后两组腿部疲劳增加，但呼吸可控。",
            "subjective_feedback_source": "VOICE",
        },
    )
    assert response.status_code == 201
    report = client.get(
        "/api/v1/training-reports/weekly", params={"week_start": week_start.isoformat()}
    )
    assert report.status_code == 200
    assert report.text.startswith("# TRAINING_WEEKLY_REPORT_V1")
    assert "## RUNNING_SESSIONS" in report.text
    assert "TYPE: QUALITY" in report.text
    assert "后两组腿部疲劳增加" in report.text
    assert "FATIGUE_SCORE" not in report.text


def test_monthly_report_does_not_repeat_raw_subjective_transcript(client: TestClient) -> None:
    secret_transcript = "UNIQUE_RAW_TRANSCRIPT_DO_NOT_COPY"
    saved = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": "2026-08-18",
            "workout_kind": "RUNNING",
            "session_type": "EASY",
            "duration_minutes": 45,
            "distance_km": 8,
            "subjective_feedback_text": secret_transcript,
            "subjective_feedback_source": "TEXT",
        },
    )
    assert saved.status_code == 201
    report = client.get("/api/v1/training-reports/monthly", params={"month": "2026-08"})
    assert report.status_code == 200
    assert report.text.startswith("# TRAINING_MONTHLY_REPORT_V1")
    assert secret_transcript not in report.text
    assert "RUNNING_SUBJECTIVE_TRENDS" in report.text


def test_weekly_plan_preview_and_import_preserve_nested_structure(client: TestClient) -> None:
    preview = client.post(
        "/api/v1/training-plans/parse",
        json={"cadence": "WEEKLY", "markdown": WEEKLY_PLAN},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["can_import"] is True
    nested = next(item for item in body["sessions"] if item["title"] == "Nested intervals")
    main = next(item for item in nested["structured_blocks"] if item["segment_kind"] == "INTERVAL")
    assert main["sets"] == 3
    assert main["repetitions"] == 5
    assert main["distance_km"] == 1
    assert main["target_pace_min"] == "3:30"
    assert main["target_hr_max"] == 176
    board = next(item for item in body["sessions"] if item["title"] == "Board session")
    setup = next(item for item in board["structured_blocks"] if item["label"] == "Board setup")
    assert setup["board_name"] == "Tension Board 2"
    assert setup["angle"] == 40
    imported = client.post(
        "/api/v1/training-plans/import",
        json={"cadence": "WEEKLY", "markdown": WEEKLY_PLAN},
    )
    assert imported.status_code == 201
    assert len(imported.json()["imported_session_ids"]) == 3
    calendar = client.get(
        "/api/v1/calendar", params={"start": "2026-09-07", "end": "2026-09-13"}
    ).json()["items"]
    imported_nested = next(
        item for item in calendar if item["planned"]["title"] == "Nested intervals"
    )
    assert imported_nested["planned"]["structured_blocks"] == nested["structured_blocks"]


def test_monthly_plan_saves_one_block_without_calendar_sessions(client: TestClient) -> None:
    imported = client.post(
        "/api/v1/training-plans/import",
        json={"cadence": "MONTHLY", "markdown": MONTHLY_PLAN},
    )
    assert imported.status_code == 201
    assert imported.json()["imported_session_ids"] == []
    current = client.get("/api/v1/training-plans/monthly/current")
    assert current.status_code == 200
    assert current.json()["content"]["running"]["weekly_distance_targets"][2] == {
        "week": 3,
        "distance_km": 42.0,
    }
    assert current.json()["content"]["running"]["sessions_per_week"] is None
    assert current.json()["content"]["climbing"]["target_structure"] == [
        {"session_type": "BOARD", "sessions_per_week": 1.0},
        {"session_type": "BOULDERING", "sessions_per_week": 2.0},
    ]
    assert current.json()["content"]["raw_plan_text"] == MONTHLY_PLAN.strip()
    calendar = client.get("/api/v1/calendar", params={"start": "2026-10-01", "end": "2026-10-31"})
    assert calendar.json()["items"] == []


def test_extended_monthly_plan_is_structured_editable_and_does_not_fill_calendar(
    client: TestClient,
) -> None:
    preview = client.post(
        "/api/v1/training-plans/parse",
        json={"cadence": "MONTHLY", "markdown": EXTENDED_MONTHLY_PLAN},
    )
    assert preview.status_code == 200
    content = preview.json()["block"]
    assert content["running"]["sessions_per_week"] == 4
    assert content["running"]["session_structure"][2] == {
        "session_type": "QUALITY",
        "sessions_per_week": 1.0,
    }
    assert content["running"]["long_run_targets"][3] == {
        "week": 4,
        "distance_km": 13.0,
    }
    assert content["running"]["key_principles"] == [
        "Keep most running easy.",
        "Do not compensate for missed easy mileage.",
    ]
    assert content["climbing"]["target_structure"][2]["session_type"] == (
        "BOULDERING_OR_SPORT_CLIMBING"
    )
    assert content["general_notes"] == "Hold progression when recovery is poor."

    imported = client.post(
        "/api/v1/training-plans/import",
        json={"cadence": "MONTHLY", "markdown": EXTENDED_MONTHLY_PLAN},
    )
    assert imported.status_code == 201
    current = client.get("/api/v1/training-plans/monthly/current").json()
    edit_payload = {
        key: value
        for key, value in current["content"].items()
        if key in {"running", "climbing", "auxiliary", "general_notes"}
    }
    edit_payload["running"]["phase"] = "Edited Volume Build"
    edited = client.patch(f"/api/v1/training-plans/monthly/{current['id']}", json=edit_payload)
    assert edited.status_code == 200
    assert edited.json()["id"] != current["id"]
    assert edited.json()["content"]["running"]["phase"] == "Edited Volume Build"
    assert edited.json()["content"]["raw_plan_text"] == EXTENDED_MONTHLY_PLAN.strip()
    calendar = client.get("/api/v1/calendar", params={"start": "2026-09-01", "end": "2026-09-30"})
    assert calendar.json()["items"] == []


def test_planned_session_edit_and_delete_preserve_revision_history(client: TestClient) -> None:
    imported = client.post(
        "/api/v1/training-plans/import",
        json={"cadence": "WEEKLY", "markdown": WEEKLY_PLAN},
    ).json()
    session_id = imported["imported_session_ids"][1]
    edited = client.patch(
        f"/api/v1/planned-sessions/{session_id}",
        json={"title": "Edited nested intervals", "session_type": "QUALITY"},
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Edited nested intervals"
    deleted = client.delete(f"/api/v1/planned-sessions/{session_id}")
    assert deleted.status_code == 200
    listed = client.get("/api/v1/planned-sessions").json()["items"]
    assert all(item["id"] != session_id for item in listed)
