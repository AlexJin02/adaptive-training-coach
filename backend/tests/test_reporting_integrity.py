from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import api as api_module
from app.ai.functions import WeeklyReviewInput, WeeklyReviewOutput
from app.enums import FatigueDomain, PlanStatus
from app.services import core, reporting


def test_profile_keeps_tb2_and_outdoor_bouldering_goals_distinct(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/athlete/profile",
        json={
            "tb2_long_term_goal": "V11",
            "outdoor_boulder_goal": "V9",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tb2_long_term_goal"] == "V11"
    assert body["outdoor_boulder_goal"] == "V9"
    assert body["bouldering_goal"] == "V11"

    legacy = client.patch("/api/v1/athlete/profile", json={"bouldering_goal": "V12"})
    assert legacy.status_code == 200
    assert legacy.json()["tb2_long_term_goal"] == "V12"
    assert legacy.json()["outdoor_boulder_goal"] == "V9"


def test_completed_session_roundtrip_exposes_saved_sport_details(client: TestClient) -> None:
    running = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Intervals",
            "duration_minutes": 50,
            "rpe": 7,
            "splits": [{"km": 1, "seconds": 280}],
            "interval_blocks": [{"repetitions": 4, "duration_minutes": 5}],
        },
    )
    assert running.status_code == 201
    assert running.json()["splits"] == [{"km": 1, "seconds": 280}]
    assert running.json()["interval_blocks"] == [{"repetitions": 4, "duration_minutes": 5}]

    climbing = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "CLIMBING",
            "session_type": "Bouldering",
            "duration_minutes": 90,
            "rpe": 7,
            "climbing_attempts": [
                {
                    "problem": "Blue 4",
                    "grade": "6C",
                    "attempts": 3,
                    "outcome": "send",
                    "styles": ["crimp"],
                }
            ],
        },
    )
    assert climbing.status_code == 201
    attempt = climbing.json()["climbing_attempts"][0]
    assert attempt["problem"] == "Blue 4"
    assert attempt["grade"] == "6C"
    assert attempt["attempts"] == 3
    assert attempt["sent"] is True
    assert attempt["style_tags"] == ["crimp"]

    crossfit = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "CROSSFIT_CONDITIONING",
            "session_type": "Metcon",
            "duration_minutes": 30,
            "rpe": 8,
            "workout_name": "Fran",
            "rounds": 3,
            "result_time": "12:34.5",
            "strength_sets": [{"exercise": "thruster", "sets": 3, "reps": 21, "load": 43}],
        },
    )
    assert crossfit.status_code == 201
    result = crossfit.json()
    assert result["workout_name"] == "Fran"
    assert result["rounds"] == 3
    assert result["result_time_seconds"] == pytest.approx(754.5)
    assert result["strength_sets"][0]["exercise"] == "thruster"
    assert result["strength"]["sets"] == result["strength_sets"]

    persisted = client.get("/api/v1/completed-sessions")
    assert persisted.status_code == 200
    by_id = {item["id"]: item for item in persisted.json()["items"]}
    assert by_id[running.json()["id"]]["splits"] == [{"km": 1, "seconds": 280}]
    assert by_id[climbing.json()["id"]]["climbing_attempts"][0]["sent"] is True
    assert by_id[result["id"]]["result_time_seconds"] == pytest.approx(754.5)


def test_readiness_api_exposes_local_soreness_and_modifiers(client: TestClient) -> None:
    checkin = client.post(
        "/api/v1/recovery-checkins",
        json={
            "date": (date.today() - timedelta(days=1)).isoformat(),
            "sleep_duration_hours": 5,
            "sleep_quality": 1,
            "energy": 1,
            "stress": 5,
            "general_soreness": 8,
            "soreness": {"finger": 4},
        },
    )
    assert checkin.status_code == 201

    response = client.get("/api/v1/load-readiness/readiness")
    assert response.status_code == 200
    climbing = next(item for item in response.json()["items"] if item["sport"] == "CLIMBING")
    local = next(
        component for component in climbing["components"] if component["domain"] == "LOCAL_SORENESS"
    )
    assert local["value"] == pytest.approx(9.2)
    assert climbing["subjective_delta"] < 0
    assert climbing["local_soreness_penalty"] == pytest.approx(0.8)
    assert any("MODERATE" in warning for warning in climbing["warnings"])
    assert response.json()["warnings"] == climbing["warnings"]


def test_fatigue_api_labels_engine_boundaries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {
        FatigueDomain.CARDIOVASCULAR: 2.999,
        FatigueDomain.LOWER_BODY: 3.0,
        FatigueDomain.FINGER_FOREARM: 7.499,
        FatigueDomain.PULLING_UPPER_BODY: 7.5,
        FatigueDomain.NEURAL: 8.999,
        FatigueDomain.SYSTEMIC: 9.0,
    }
    result = SimpleNamespace(
        latent=values,
        display=values,
        calculated_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        api_module.core,
        "current_load_readiness",
        lambda _db: (result, SimpleNamespace(), None),
    )

    response = client.get("/api/v1/load-readiness/fatigue")
    assert response.status_code == 200
    items = {item["domain"]: item for item in response.json()["items"]}
    assert items["CARDIOVASCULAR"]["display_label"] == "LOW"
    assert items["LOWER_BODY"]["display_label"] == "MODERATE"
    assert items["FINGER_FOREARM"]["display_label"] == "MODERATE"
    assert items["PULLING_UPPER_BODY"]["display_label"] == "HIGH"
    assert items["NEURAL"]["display_label"] == "HIGH"
    assert items["SYSTEMIC"]["display_label"] == "VERY_HIGH"
    assert items["PULLING_UPPER_BODY"]["is_high"] is True
    assert items["FINGER_FOREARM"]["is_high"] is False


def test_adaptation_edits_reject_unknown_and_negative_fields(client: TestClient) -> None:
    assert client.post("/api/v1/demo/seed").status_code == 200
    proposals = client.get("/api/v1/adaptations").json()["items"]
    assert proposals
    proposal_id = proposals[0]["id"]

    unknown = client.post(
        f"/api/v1/adaptations/{proposal_id}/decision",
        json={
            "decision": "ACCEPT",
            "proposed_plan": {"planned_duration_minutes": 30, "untrusted_field": True},
        },
    )
    assert unknown.status_code == 422

    negative = client.post(
        f"/api/v1/adaptations/{proposal_id}/decision",
        json={"decision": "ACCEPT", "proposed_plan": {"planned_duration_minutes": -5}},
    )
    assert negative.status_code == 422

    edited_plan = dict(proposals[0]["proposed_plan"])
    edited_plan["planned_duration_minutes"] = 30
    valid = client.post(
        f"/api/v1/adaptations/{proposal_id}/decision",
        json={"decision": "ACCEPT", "proposed_plan": edited_plan},
    )
    assert valid.status_code == 200


def test_weekly_review_uses_plan_history_and_historical_climbing_state(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    week_start = date(2025, 1, 6)
    week_end = week_start + timedelta(days=6)

    modified = core.create_planned_session(
        db,
        {
            "date": week_start,
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "title": "Editable run",
            "planned_duration_minutes": 40,
            "target_rpe": 3,
        },
    )
    core.update_planned_session(
        db, modified, {"planned_duration_minutes": 50}, "Manual duration edit"
    )
    core.create_completed_session(
        db,
        {
            "date": week_start,
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "duration_minutes": 50,
            "distance_km": 8,
            "rpe": 3,
            "planned_session_id": modified.id,
        },
    )

    completed = core.create_planned_session(
        db,
        {
            "date": week_start + timedelta(days=1),
            "workout_kind": "RUNNING",
            "session_type": "Threshold",
            "title": "Unchanged run",
            "planned_duration_minutes": 45,
            "target_rpe": 7,
        },
    )
    core.create_completed_session(
        db,
        {
            "date": week_start + timedelta(days=1),
            "workout_kind": "RUNNING",
            "session_type": "Threshold",
            "duration_minutes": 45,
            "distance_km": 9,
            "rpe": 7,
            "planned_session_id": completed.id,
        },
    )

    core.create_planned_session(
        db,
        {
            "date": week_start + timedelta(days=2),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "title": "Skipped run",
            "status": PlanStatus.SKIPPED,
        },
    )
    for offset, status in enumerate(
        (PlanStatus.REST, PlanStatus.MOVED, PlanStatus.REPLACED), start=3
    ):
        core.create_planned_session(
            db,
            {
                "date": week_start + timedelta(days=offset),
                "workout_kind": "MOBILITY_RECOVERY",
                "session_type": status.value.title(),
                "title": status.value.title(),
                "status": status,
            },
        )

    core.create_completed_session(
        db,
        {
            "date": week_end,
            "workout_kind": "CLIMBING",
            "session_type": "Bouldering",
            "duration_minutes": 90,
            "rpe": 7,
            "hard_attempts": 6,
        },
    )

    core.create_gym_set(
        db,
        {
            "gym": "History Gym",
            "start_date": date(2025, 1, 1),
            "progress": [{"colour": "Yellow", "sent_count": 2}],
        },
    )
    core.create_gym_set(
        db,
        {
            "gym": "History Gym",
            "start_date": date(2025, 2, 1),
            "progress": [{"colour": "Black", "sent_count": 5}],
        },
    )

    captured: dict[str, object] = {}

    class EnabledSettings:
        openai_api_key = "test-key"

    def fake_review(context):  # noqa: ANN001, ANN202
        validated = WeeklyReviewInput.model_validate(context)
        captured.update(validated.model_dump(mode="json"))
        return WeeklyReviewOutput(
            summary=[],
            running=[],
            climbing=[],
            recovery=[],
            key_findings=[],
            next_week=[],
            confidence="MODERATE",
        )

    monkeypatch.setattr(reporting, "get_settings", lambda: EnabledSettings())
    monkeypatch.setattr(reporting, "generate_ai_weekly_review", fake_review)
    review = reporting.generate_weekly_review(db, week_start)

    assert review.compliance == {
        "planned": 3,
        "completed": 1,
        "modified": 1,
        "skipped": 1,
        "extra": 1,
    }
    assert any("Yellow" in line for line in review.climbing)
    assert all("Black" not in line for line in review.climbing)

    trends = captured["recent_four_week_trends"]
    assert isinstance(trends, dict)
    assert set(trends) == {"range", "running", "climbing", "load"}
    assert trends["running"]["weekly_distance_km"][-1]["value"] == 17
    assert trends["climbing"]["weekly_minutes"][-1]["value"] == 90
    assert trends["load"]["weekly_srpe"][-1]["value"] > 0
