import json
from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.ai.functions import WeeklyReviewInput, WeeklyReviewOutput, classify_note_text
from app.enums import (
    AdaptationAction,
    AdaptationDecision,
    AdaptationSource,
    Confidence,
    NoteCategory,
    PlanStatus,
    SessionPriority,
    Sport,
)
from app.services import core, data_portability, demo, notes, reporting


def test_frontend_settings_contract_and_patch(client: TestClient) -> None:
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["gym_name"] == "Home Gym"
    assert body["grade_display"] == "BOTH"
    assert body["engine"]["half_lives"]["FINGER_FOREARM"] == 36

    patched = client.patch(
        "/api/v1/settings",
        json={"gym_name": "Depot", "retain_audio": True, "grade_display": "FONT"},
    )
    assert patched.status_code == 200
    assert patched.json()["gym_name"] == "Depot"
    assert patched.json()["retain_audio"] is True

    engine = patched.json()["engine"]
    engine["half_lives"]["FINGER_FOREARM"] = 48
    engine["readiness_good_threshold"] = 9.5
    engine["readiness_moderate_threshold"] = 9.0
    configured = client.patch("/api/v1/settings", json={"engine": engine})
    assert configured.status_code == 200
    assert configured.json()["engine"]["half_lives"]["FINGER_FOREARM"] == 48
    fatigue = client.get("/api/v1/load-readiness/fatigue").json()
    finger = next(item for item in fatigue["items"] if item["domain"] == "FINGER_FOREARM")
    assert finger["half_life_hours"] == 48
    logged = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "duration_minutes": 30,
            "rpe": 3,
        },
    )
    assert logged.status_code == 201
    readiness = client.get("/api/v1/load-readiness/readiness").json()
    running = next(item for item in readiness["items"] if item["sport"] == "RUNNING")
    cardio = next(
        component for component in running["components"] if component["domain"] == "CARDIOVASCULAR"
    )
    assert cardio["label"] == "MODERATE"


def test_rpe_contract_rejects_zero(client: TestClient) -> None:
    response = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "duration_minutes": 30,
            "rpe": 0,
        },
    )
    assert response.status_code == 422

    plan = client.post(
        "/api/v1/planned-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "target_rpe": 0,
        },
    )
    assert plan.status_code == 422


def test_planned_session_structured_blocks_round_trip(client: TestClient) -> None:
    structured_blocks = [
        {
            "exercise": "Max Hangs",
            "sets": 5,
            "work_seconds": 10,
            "rest_seconds": 180,
            "edge_mm": 20,
        }
    ]
    created = client.post(
        "/api/v1/planned-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "CLIMBING",
            "session_type": "Max Hangs",
            "title": "Max Hangs",
            "target_rpe": 8,
            "structured_blocks": structured_blocks,
        },
    )
    assert created.status_code == 201
    assert created.json()["structured_blocks"] == structured_blocks

    listed = client.get("/api/v1/planned-sessions")
    assert listed.status_code == 200
    matching = next(item for item in listed.json()["items"] if item["id"] == created.json()["id"])
    assert matching["structured_blocks"] == structured_blocks


def test_run_without_distance_is_valid_and_snapshots_are_idempotent(
    client: TestClient,
) -> None:
    payload = {
        "date": date.today().isoformat(),
        "workout_kind": "RUNNING",
        "session_type": "Easy",
        "duration_minutes": 45,
        "rpe": 3,
    }
    response = client.post("/api/v1/completed-sessions", json=payload)
    assert response.status_code == 201
    assert response.json()["distance_km"] is None
    fatigue = client.get("/api/v1/load-readiness/fatigue").json()["items"]
    assert next(item for item in fatigue if item["domain"] == "CARDIOVASCULAR")["latent_value"] > 0


def test_snapshot_service_upserts_by_source_key(db: Session) -> None:
    session = core.create_completed_session(
        db,
        {
            "date": date.today(),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "duration_minutes": 30,
            "rpe": 3,
        },
    )
    core.persist_load_readiness_snapshot(db, source_key=f"session:{session.id}")
    core.persist_load_readiness_snapshot(db, source_key=f"session:{session.id}")
    assert db.scalar(select(func.count(models.FatigueSnapshot.id))) == 1
    assert db.scalar(select(func.count(models.ReadinessSnapshot.id))) == 1


def test_riegel_estimate_and_recent_actual_10k_override(client: TestClient) -> None:
    five_k_date = date.today() - timedelta(days=10)
    first = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": five_k_date.isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Race",
            "duration_minutes": 22,
            "distance_km": 5,
            "rpe": 9,
        },
    )
    assert first.status_code == 201
    expected = 22 * 60 * (10 / 5) ** 1.06
    state = client.get("/api/v1/athlete-state/running").json()
    assert state["estimated_10k"]["value"] == pytest.approx(expected)
    assert "Riegel" in state["estimated_10k"]["formula"]

    actual = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": (date.today() - timedelta(days=5)).isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Race",
            "duration_minutes": 45,
            "distance_km": 10,
            "rpe": 9,
        },
    )
    assert actual.status_code == 201
    state = client.get("/api/v1/athlete-state/running").json()
    assert state["estimated_10k"]["value"] == 2700
    assert state["estimated_10k"]["formula"] == "ACTUAL_10K"


def test_threshold_and_lt1_evidence_are_derived(client: TestClient) -> None:
    # Deliberately backfill newest to oldest; derivation must not depend on entry order.
    for offset, pace, hr in [(4, "5:10", 149), (8, "5:15", 147), (12, "5:20", 145)]:
        response = client.post(
            "/api/v1/completed-sessions",
            json={
                "date": (date.today() - timedelta(days=offset)).isoformat(),
                "workout_kind": "RUNNING",
                "session_type": "Easy",
                "duration_minutes": 50,
                "distance_km": 9,
                "average_pace": pace,
                "average_hr": hr,
                "rpe": 3,
            },
        )
        assert response.status_code == 201
    state = client.get("/api/v1/athlete-state/running").json()
    assert state["lt1_pace_range"] == [310.0, 320.0]
    response = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Threshold",
            "duration_minutes": 60,
            "distance_km": 12,
            "average_pace": "4:20",
            "average_hr": 170,
            "rpe": 7,
        },
    )
    assert response.status_code == 201
    state = client.get("/api/v1/athlete-state/running").json()
    assert state["lt1_pace_range"] == [310.0, 320.0]
    assert state["lt2_pace_seconds_per_km"] == 260.0
    assert "Threshold" in state["lt2_source"]


def test_accept_move_preserves_original_and_creates_linked_successor(db: Session) -> None:
    original_date = date.today() + timedelta(days=1)
    new_date = original_date + timedelta(days=2)
    plan = core.create_planned_session(
        db,
        {
            "date": original_date,
            "start_time": time(7, 0),
            "workout_kind": Sport.CLIMBING,
            "session_type": "Limit Bouldering",
            "title": "Limit session",
            "planned_duration_minutes": 90,
            "target_rpe": 8,
            "priority": SessionPriority.HIGH,
        },
    )
    original_public = core.plan_snapshot(plan)
    event = models.AdaptationEvent(
        affected_session_id=plan.id,
        original_plan=original_public,
        proposed_plan={**original_public, "session_date": new_date.isoformat()},
        action=AdaptationAction.MOVE,
        reason="High finger fatigue",
        evidence=["FINGER_FOREARM 9.5"],
        confidence=Confidence.HIGH,
        source=AdaptationSource.RULE_ENGINE,
        decision=AdaptationDecision.PENDING,
    )
    db.add(event)
    db.commit()
    core.decide_adaptation(db, event, "ACCEPT")
    db.refresh(plan)
    successor = db.scalar(
        select(models.PlannedSession).where(models.PlannedSession.moved_from_id == plan.id)
    )
    assert plan.status == PlanStatus.MOVED
    assert plan.session_date == original_date
    assert successor is not None
    assert successor.session_date == new_date
    assert successor.start_time == time(7, 0)


def test_accept_reduce_intensity_changes_target_not_only_status(db: Session) -> None:
    plan = core.create_planned_session(
        db,
        {
            "date": date.today() + timedelta(days=1),
            "workout_kind": "RUNNING",
            "session_type": "Threshold",
            "title": "Threshold",
            "planned_duration_minutes": 60,
            "target_rpe": 8,
        },
    )
    original = core.plan_snapshot(plan)
    event = models.AdaptationEvent(
        affected_session_id=plan.id,
        original_plan=original,
        proposed_plan={**original, "target_rpe": 7.6},
        action=AdaptationAction.REDUCE_INTENSITY,
        reason="Unexpected fatigue",
        evidence=["Easy-run RPE 8"],
        confidence=Confidence.MODERATE,
        source=AdaptationSource.RULE_ENGINE,
        decision=AdaptationDecision.PENDING,
    )
    db.add(event)
    db.commit()
    core.decide_adaptation(db, event, "ACCEPT")
    db.refresh(plan)
    assert plan.status == PlanStatus.MODIFIED
    assert plan.target_rpe_min == pytest.approx(7.6)
    assert plan.target_rpe_max == pytest.approx(7.6)


def test_mixed_chinese_english_note_classifies_running() -> None:
    category, confidence = classify_note_text(
        "这个 threshold 训练与 LT2 有关，今天控制在 RPE 7，之后再跑 easy。"
    )
    assert category == NoteCategory.RUNNING
    assert confidence == Confidence.HIGH


def test_unapproved_dramatic_note_cannot_change_plan(db: Session) -> None:
    plan = core.create_planned_session(
        db,
        {
            "date": date.today() + timedelta(days=1),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "title": "Easy run",
            "planned_distance_km": 8,
        },
    )
    notes.create_note(
        db,
        {
            "primary_category": "RUNNING",
            "title": "Dramatic internet advice",
            "raw_input": "Immediately double all weekly mileage.",
            "cleaned_note": "Immediately double all weekly mileage.",
            "use_for_coaching": False,
        },
    )
    db.refresh(plan)
    assert plan.planned_distance_km == 8
    assert db.scalar(select(func.count(models.AdaptationEvent.id))) == 0


def test_backup_omits_host_media_paths_and_restore_replaces_atomically(db: Session) -> None:
    db.add(
        models.MediaImport(
            kind="AUDIO",
            status="EXTRACTED",
            local_path="/private/secret/audio.webm",
            retain_raw=True,
        )
    )
    db.commit()
    payload = data_portability.create_backup(db)
    assert payload["data"]["media_imports"][0]["local_path"] is None
    assert payload["data"]["media_imports"][0]["retain_raw"] is False
    restored = data_portability.restore_backup(db, payload)
    assert restored > 0
    assert db.scalar(select(func.count(models.AthleteProfile.id))) == 1


def test_restore_rejects_missing_tables_without_changing_local_rows(db: Session) -> None:
    plan = core.create_planned_session(
        db,
        {
            "date": date.today(),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "title": "Keep me",
        },
    )
    before = db.scalar(select(func.count(models.PlannedSession.id)))

    with pytest.raises(ValueError, match="missing required tables"):
        data_portability.restore_backup(db, {"schema_version": "1.0", "data": {}})

    assert db.scalar(select(func.count(models.PlannedSession.id))) == before
    assert db.get(models.PlannedSession, plan.id).title == "Keep me"


def test_restore_rejects_complete_but_empty_backup_without_changing_rows(db: Session) -> None:
    before = data_portability.create_backup(db)
    all_empty = {
        "schema_version": before["schema_version"],
        "data": {table_name: [] for table_name in before["data"]},
    }

    with pytest.raises(ValueError, match="exactly one athlete_profiles"):
        data_portability.restore_backup(db, all_empty)

    assert db.scalar(select(func.count(models.AthleteProfile.id))) == 1
    assert db.scalar(select(func.count(models.Goal.id))) == 1


def test_restore_rejects_incomplete_profile_instead_of_fabricating_defaults(
    db: Session,
) -> None:
    payload = data_portability.create_backup(db)
    payload["data"]["athlete_profiles"] = [{"id": 1}]

    with pytest.raises(ValueError, match="incomplete or malformed"):
        data_portability.restore_backup(db, payload)

    profile = db.get(models.AthleteProfile, 1)
    assert profile is not None
    assert profile.display_name == "Alex"


def test_restore_endpoint_rejects_missing_tables_and_preserves_rows(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/planned-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "title": "Keep me through invalid restore",
        },
    )
    assert created.status_code == 201

    rejected = client.post(
        "/api/v1/data/restore",
        files={
            "backup": (
                "incomplete.json",
                json.dumps({"schema_version": "1.0", "data": {}}),
                "application/json",
            )
        },
    )
    assert rejected.status_code == 422
    assert "missing required tables" in rejected.json()["detail"]
    listed = client.get("/api/v1/planned-sessions").json()["items"]
    assert any(item["id"] == created.json()["id"] for item in listed)


def test_restore_endpoint_rejects_complete_empty_backup_and_preserves_profile(
    client: TestClient,
) -> None:
    payload = client.get("/api/v1/data/backup").json()
    payload["data"] = {table_name: [] for table_name in payload["data"]}

    rejected = client.post(
        "/api/v1/data/restore",
        files={"backup": ("empty.json", json.dumps(payload), "application/json")},
    )
    assert rejected.status_code == 422
    assert "exactly one athlete_profiles" in rejected.json()["detail"]
    assert client.get("/api/v1/athlete/profile").json()["display_name"] == "Alex"


def test_backup_restore_roundtrip_preserves_start_times(client: TestClient) -> None:
    plan = client.post(
        "/api/v1/planned-sessions",
        json={
            "date": date.today().isoformat(),
            "start_time": "07:05",
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "title": "Early run",
            "target_rpe": 3,
        },
    )
    assert plan.status_code == 201
    completed = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "start_time": "08:15",
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "duration_minutes": 30,
            "rpe": 3,
        },
    )
    assert completed.status_code == 201

    backup = client.get("/api/v1/data/backup")
    assert backup.status_code == 200
    payload = backup.json()
    restored = client.post(
        "/api/v1/data/restore",
        files={
            "backup": (
                "training-coach-backup.json",
                json.dumps(payload),
                "application/json",
            )
        },
    )
    assert restored.status_code == 200
    plans = client.get("/api/v1/planned-sessions").json()["items"]
    sessions = client.get("/api/v1/completed-sessions").json()["items"]
    assert plans[0]["start_time"] == "07:05"
    assert sessions[0]["start_time"] == "08:15"


@pytest.mark.parametrize(
    "soreness",
    [
        {"wrist": 3},
        {"finger": -0.1},
        {"shoulder": 10.1},
    ],
)
def test_recovery_rejects_unknown_or_out_of_range_soreness(
    client: TestClient, soreness: dict[str, float]
) -> None:
    response = client.post(
        "/api/v1/recovery-checkins",
        json={"date": date.today().isoformat(), "soreness": soreness},
    )
    assert response.status_code == 422


def test_tb2_endpoint_rejects_non_tb2_board(client: TestClient) -> None:
    response = client.post(
        "/api/v1/climbing/tb2-benchmarks",
        json={
            "date": date.today().isoformat(),
            "board": "MoonBoard",
            "angle": 40,
            "verified_grade": "6C",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "row",
    [
        {"colour": "Yellow", "sent_count": -1, "available_problem_count": 2},
        {"colour": "Yellow", "sent_count": 1, "available_problem_count": -1},
        {"colour": "Yellow", "sent_count": 3, "available_problem_count": 2},
    ],
)
def test_gym_progress_rejects_impossible_counts(client: TestClient, row: dict[str, object]) -> None:
    response = client.post(
        "/api/v1/climbing/gym-sets",
        json={
            "gym": "Validation Gym",
            "start_date": date.today().isoformat(),
            "progress": [row],
        },
    )
    assert response.status_code == 422


def test_gym_progress_patch_rejects_sent_above_available(client: TestClient) -> None:
    created = client.post(
        "/api/v1/climbing/gym-sets",
        json={
            "gym": "Validation Gym",
            "start_date": date.today().isoformat(),
            "progress": [{"colour": "Yellow", "sent_count": 1, "available_problem_count": 2}],
        },
    )
    assert created.status_code == 201
    response = client.patch(
        f"/api/v1/climbing/gym-sets/{created.json()['id']}/progress",
        json={"progress": [{"colour": "Yellow", "sent_count": 3, "available_problem_count": 2}]},
    )
    assert response.status_code == 422


def test_persisted_medium_finger_soreness_blocks_progression(db: Session) -> None:
    first_day = date.today() - timedelta(days=10)
    second_day = date.today() - timedelta(days=3)
    for day, finger_soreness in ((first_day, 0), (second_day, 4)):
        core.create_recovery_checkin(
            db,
            {
                "recorded_at": datetime.combine(day, time(8), tzinfo=UTC),
                "area_soreness": {"finger": finger_soreness},
            },
        )
        plan = core.create_planned_session(
            db,
            {
                "date": day,
                "start_time": time(18),
                "workout_kind": "CLIMBING",
                "session_type": "Limit Bouldering",
                "title": "Limit bouldering",
                "planned_duration_minutes": 10,
                "target_rpe": 3,
            },
        )
        core.create_completed_session(
            db,
            {
                "date": day,
                "start_time": time(18),
                "workout_kind": "CLIMBING",
                "session_type": "Limit Bouldering",
                "duration_minutes": 10,
                "rpe": 2,
                "planned_session_id": plan.id,
            },
        )
    core.create_planned_session(
        db,
        {
            "date": date.today() + timedelta(days=1),
            "workout_kind": "CLIMBING",
            "session_type": "Limit Bouldering",
            "title": "Next limit bouldering",
            "planned_duration_minutes": 10,
            "target_rpe": 3,
        },
    )
    proposals = core.create_adaptation_proposals(db)
    assert proposals
    assert not any(proposal.action == AdaptationAction.PROGRESS for proposal in proposals)
    assert any("Finger soreness 4/10" in evidence for evidence in proposals[0].evidence)


def test_demo_contains_high_fatigue_adaptation_and_is_removable(db: Session) -> None:
    assert demo.seed_demo(db) > 0
    adaptations = list(db.scalars(select(models.AdaptationEvent)))
    assert adaptations
    assert adaptations[0].action in {
        AdaptationAction.MOVE,
        AdaptationAction.REPLACE,
        AdaptationAction.REDUCE_VOLUME,
    }
    progress = reporting.progress_data(db, "4 weeks")
    assert progress["running"]["estimated_10k"]
    assert progress["running"]["lt2"]
    assert progress["running"]["easy_efficiency"]
    removed = demo.remove_demo(db)
    assert removed > 0
    assert db.scalar(select(func.count(models.RunningFitnessEstimate.id))) == 0
    assert db.scalar(select(func.count(models.ThresholdEstimate.id))) == 0


def test_phase_changes_are_append_only_history(db: Session) -> None:
    core.update_profile(db, {"running_phase": "THRESHOLD_BUILD"})
    core.update_profile(db, {"running_phase": "HALF_MARATHON_SPECIFIC"})
    history = list(
        db.scalars(select(models.AthleteStateHistory).order_by(models.AthleteStateHistory.id))
    )
    assert [(row.old_value, row.new_value) for row in history] == [
        ("AEROBIC_BASE", "THRESHOLD_BUILD"),
        ("THRESHOLD_BUILD", "HALF_MARATHON_SPECIFIC"),
    ]


def test_ai_enabled_weekly_review_validates_context_and_uses_typed_output(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EnabledSettings:
        openai_api_key = "test-key"

    def fake_review(context):  # noqa: ANN001, ANN202
        WeeklyReviewInput.model_validate(context)
        return WeeklyReviewOutput(
            summary=["Evidence-backed summary"],
            running=["Running evidence"],
            climbing=["Climbing evidence"],
            recovery=["Recovery evidence"],
            key_findings=["Finding"],
            next_week=["Keep next week conservative"],
            confidence="MODERATE",
        )

    monkeypatch.setattr(reporting, "get_settings", lambda: EnabledSettings())
    monkeypatch.setattr(reporting, "generate_ai_weekly_review", fake_review)
    monday = date.today() - timedelta(days=date.today().weekday())
    response = client.post(
        "/api/v1/weekly-reviews/generate", json={"week_start": monday.isoformat()}
    )
    assert response.status_code == 200
    assert response.json()["source"] == "AI"
    assert response.json()["running"] == ["Running evidence"]
