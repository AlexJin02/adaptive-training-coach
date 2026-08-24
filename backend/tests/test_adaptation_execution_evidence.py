from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.enums import FatigueDomain, ReadinessLabel, SessionPriority, Sport
from app.services import core
from app.training_engine.adaptation import (
    AdaptationContext,
    CompletedEvidence,
    PlannedWorkout,
    assess_execution,
    propose_adaptations,
)


def blank_fatigue() -> dict[FatigueDomain, float]:
    return {domain: 0.0 for domain in FatigueDomain}


def threshold_blocks() -> tuple[dict[str, object], ...]:
    return (
        {"phase": "Warmup", "duration_minutes": 15},
        {
            "phase": "Main",
            "description": "4 × 8 min threshold",
            "repetitions": 4,
            "work_minutes": 8,
            "recovery_minutes": 2,
            "target_pace_seconds_per_km": 270,
            "target_hr_max": 172,
        },
        {"phase": "Cooldown", "duration_minutes": 10},
    )


def strong_intervals() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "phase": "Main",
            "repetition": index,
            "duration_minutes": 8,
            "pace_seconds_per_km": pace,
            "average_hr": hr,
        }
        for index, (pace, hr) in enumerate(
            [(266, 165), (264, 167), (263, 168), (264, 169)], start=1
        )
    )


def completed_threshold(
    *, session_id: int, session_date: date, intervals: tuple[dict[str, object], ...]
) -> CompletedEvidence:
    return CompletedEvidence(
        id=session_id,
        session_date=session_date,
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=50,
        rpe=7,
        planned_duration_minutes=50,
        target_rpe_max=8,
        pre_session_readiness=8,
        planned_structured_blocks=threshold_blocks(),
        completed_interval_blocks=intervals,
        splits=(
            {"distance": 1, "time": "4:26", "hr": 165},
            {"distance": 1, "time": "4:24", "hr": 169},
        ),
        average_pace_seconds_per_km=265,
        average_hr=167,
    )


def upcoming_threshold() -> PlannedWorkout:
    return PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        title="Threshold",
        duration_minutes=50,
        target_rpe_min=7,
        target_rpe_max=8,
        priority=SessionPriority.HIGH,
        structured_blocks=threshold_blocks(),
    )


def test_one_verified_strong_execution_is_recognised_but_kept() -> None:
    trigger = completed_threshold(
        session_id=1, session_date=date(2026, 8, 23), intervals=strong_intervals()
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming_threshold(),),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
        )
    )[0]
    assert proposal.action.value == "KEEP"
    assert "Strong execution" in proposal.reason
    assert "All recorded work reps were faster than target pace" in proposal.evidence
    assert "Work-rep HR stayed within the recorded target" in proposal.evidence
    assert "No late-session pace deterioration detected" in proposal.evidence


def test_two_verified_strong_executions_progress_only_threshold_volume() -> None:
    earlier = completed_threshold(
        session_id=1, session_date=date(2026, 8, 12), intervals=strong_intervals()
    )
    trigger = completed_threshold(
        session_id=2, session_date=date(2026, 8, 23), intervals=strong_intervals()
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming_threshold(),),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )[0]
    assert proposal.action.value == "PROGRESS"
    assert set(proposal.proposed_changes) == {"structured_blocks", "progressed_variable"}
    main = proposal.proposed_changes["structured_blocks"][1]
    assert (main["repetitions"], main["work_minutes"]) == (3, 12)
    assert main["target_pace_seconds_per_km"] == 270
    assert main["target_hr_max"] == 172
    assert main["recovery_minutes"] == 2


def test_major_interval_execution_failure_blocks_progression() -> None:
    earlier = completed_threshold(
        session_id=1, session_date=date(2026, 8, 12), intervals=strong_intervals()
    )
    failed = completed_threshold(
        session_id=2,
        session_date=date(2026, 8, 23),
        intervals=strong_intervals()[:2],
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=failed,
            upcoming=(upcoming_threshold(),),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )[0]
    assert proposal.action.value == "KEEP"
    assert "major execution failure" in proposal.reason.lower()
    assert "Completed only 2/4 planned work reps" in proposal.evidence


def test_text_prescription_and_split_hr_drive_strong_execution_without_inference() -> None:
    evidence = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=50,
        rpe=7,
        planned_duration_minutes=50,
        target_rpe_max=8,
        pre_session_readiness=8,
        planned_structured_blocks=(
            {
                "phase": "Main",
                "detail": "4 × 8 min @ 4:15/km, HR <= 172, 2 min recovery",
            },
        ),
        completed_interval_blocks=({"phase": "Main", "detail": "Completed as laps"},),
        splits=(
            {"distance": 1, "time": "4:12", "hr": 165},
            {"distance": 1, "time": "4:11", "hr": 167},
            {"distance": 1, "time": "4:10", "hr": 169},
            {"distance": 1, "time": "4:11", "hr": 170},
        ),
    )
    assessment = assess_execution(evidence)
    assert assessment.strong is True
    assert assessment.no_late_deterioration is True
    assert "Work-rep HR stayed within the recorded target" in assessment.evidence


def test_numeric_prescription_fields_take_priority_over_description() -> None:
    evidence = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=50,
        rpe=7,
        planned_duration_minutes=50,
        target_rpe_max=8,
        pre_session_readiness=8,
        planned_structured_blocks=(
            {
                "phase": "Main",
                "detail": "4 × 8 min @ 4:15/km, HR <= 172, 2 min recovery",
                "repetitions": 4,
                "work_minutes": 8,
                "target_pace_seconds_per_km": 270,
                "target_hr_max": 180,
                "recovery_minutes": 3,
            },
        ),
        completed_interval_blocks=tuple(
            {
                "repetition": index,
                "pace_seconds_per_km": pace,
                "average_hr": 175,
            }
            for index, pace in enumerate((265, 264, 263, 264), start=1)
        ),
    )
    assert assess_execution(evidence).strong is True


@pytest.mark.parametrize(
    ("goal", "affected_id"),
    [("HALF_MARATHON", 20), ("BOULDERING", 10)],
)
def test_primary_goal_protects_aligned_session_in_non_emergency_conflict(
    goal: str, affected_id: int
) -> None:
    running = PlannedWorkout(
        id=10,
        session_date=date(2026, 8, 24),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        title="Goal running quality",
        duration_minutes=60,
        priority=SessionPriority.HIGH,
    )
    climbing = PlannedWorkout(
        id=20,
        session_date=date(2026, 8, 24),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        title="Goal climbing quality",
        duration_minutes=90,
        priority=SessionPriority.HIGH,
    )
    fatigue = blank_fatigue()
    fatigue[FatigueDomain.CARDIOVASCULAR] = 8
    fatigue[FatigueDomain.FINGER_FOREARM] = 8
    trigger = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.STRENGTH,
        workout_type="Strength",
        duration_minutes=30,
        rpe=4,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(running, climbing),
            latent_fatigue=fatigue,
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            primary_goal=goal,
        )
    )[0]
    assert proposal.action.value == "REDUCE_VOLUME"
    assert proposal.affected_session_id == affected_id
    assert f"Primary goal {goal}" in proposal.evidence[-1]


def test_api_pipeline_uses_saved_structured_execution_evidence(client: TestClient) -> None:
    first_day = date.today() - timedelta(days=9)
    second_day = date.today() - timedelta(days=3)
    next_day = date.today() + timedelta(days=2)
    plan_ids: list[int] = []
    for day in (first_day, second_day, next_day):
        response = client.post(
            "/api/v1/planned-sessions",
            json={
                "date": day.isoformat(),
                "start_time": "18:00",
                "workout_kind": "RUNNING",
                "session_type": "Threshold",
                "title": "4 x 8 threshold",
                "planned_duration_minutes": 50,
                "target_rpe": 8,
                "priority": "HIGH",
                "structured_blocks": list(threshold_blocks()),
            },
        )
        assert response.status_code == 201
        plan_ids.append(response.json()["id"])
    for day, plan_id in zip((first_day, second_day), plan_ids, strict=False):
        checkin = client.post(
            "/api/v1/recovery-checkins",
            json={"date": day.isoformat(), "sleep_quality": 4, "energy": 4},
        )
        assert checkin.status_code == 201
        completed = client.post(
            "/api/v1/completed-sessions",
            json={
                "date": day.isoformat(),
                "start_time": "18:00",
                "workout_kind": "RUNNING",
                "session_type": "Threshold",
                "duration_minutes": 50,
                "distance_km": 11,
                "average_pace_seconds_per_km": 265,
                "average_hr": 167,
                "rpe": 7,
                "planned_session_id": plan_id,
                "interval_blocks": list(strong_intervals()),
                "splits": [
                    {"distance": 1, "time": "4:26", "hr": 165},
                    {"distance": 1, "time": "4:24", "hr": 169},
                ],
            },
        )
        assert completed.status_code == 201
    adaptations = client.get("/api/v1/adaptations")
    assert adaptations.status_code == 200
    assert adaptations.json()["items"] == []
    plans = client.get("/api/v1/planned-sessions").json()["items"]
    unchanged_plan = next(item for item in plans if item["id"] == plan_ids[2])
    assert unchanged_plan["structured_blocks"][1]["repetitions"] == 4
    assert unchanged_plan["structured_blocks"][1]["work_minutes"] == 8


def test_service_pipeline_uses_incomplete_reps_as_major_failure(db) -> None:  # noqa: ANN001
    first_day = date.today() - timedelta(days=9)
    second_day = date.today() - timedelta(days=3)
    plan_ids: list[int] = []
    for day in (first_day, second_day):
        core.create_recovery_checkin(
            db,
            {
                "recorded_at": datetime.combine(day, time(8), tzinfo=UTC),
                "sleep_quality": 4,
                "energy": 4,
            },
        )
        plan = core.create_planned_session(
            db,
            {
                "date": day,
                "start_time": time(18),
                "workout_kind": "RUNNING",
                "session_type": "Threshold",
                "title": "4 x 8 threshold",
                "planned_duration_minutes": 50,
                "target_rpe": 8,
                "structured_blocks": list(threshold_blocks()),
            },
        )
        plan_ids.append(plan.id)
    core.create_completed_session(
        db,
        {
            "date": first_day,
            "start_time": time(18),
            "workout_kind": "RUNNING",
            "session_type": "Threshold",
            "duration_minutes": 50,
            "rpe": 7,
            "planned_session_id": plan_ids[0],
            "interval_blocks": list(strong_intervals()),
        },
    )
    core.create_completed_session(
        db,
        {
            "date": second_day,
            "start_time": time(18),
            "workout_kind": "RUNNING",
            "session_type": "Threshold",
            "duration_minutes": 50,
            "rpe": 7,
            "planned_session_id": plan_ids[1],
            "interval_blocks": list(strong_intervals()[:2]),
        },
    )
    upcoming = core.create_planned_session(
        db,
        {
            "date": date.today() + timedelta(days=2),
            "workout_kind": "RUNNING",
            "session_type": "Threshold",
            "title": "Next threshold",
            "planned_duration_minutes": 50,
            "target_rpe": 8,
            "structured_blocks": list(threshold_blocks()),
        },
    )
    proposals = core.create_adaptation_proposals(db)
    proposal = next(item for item in proposals if item.affected_session_id == upcoming.id)
    assert proposal.action.value == "KEEP"
    assert "major execution failure" in proposal.reason.lower()
    assert "Completed only 2/4 planned work reps" in proposal.evidence


def test_running_state_build_gate_uses_stable_quality_execution(db) -> None:  # noqa: ANN001
    session_specs = [
        (20, "Easy", 3, 2.0, None, None),
        (16, "Threshold", 7, 2.2, 260, 165),
        (12, "Easy", 3, 2.0, None, None),
        (8, "Long Run", 5, 4.0, None, None),
        (4, "Threshold", 7, 2.2, 262, 168),
    ]
    for days_ago, workout_type, rpe, distance, pace, hr in session_specs:
        day = date.today() - timedelta(days=days_ago)
        plan = core.create_planned_session(
            db,
            {
                "date": day,
                "start_time": time(18),
                "workout_kind": "RUNNING",
                "session_type": workout_type,
                "title": workout_type,
                "planned_duration_minutes": 10,
                "target_rpe": rpe + 1,
            },
        )
        core.create_completed_session(
            db,
            {
                "date": day,
                "start_time": time(18),
                "workout_kind": "RUNNING",
                "session_type": workout_type,
                "duration_minutes": 10,
                "distance_km": distance,
                "average_pace_seconds_per_km": pace,
                "average_hr": hr,
                "rpe": rpe,
                "planned_session_id": plan.id,
            },
        )
    state = core.running_state(db)
    assert state["progression_decision"] == "BUILD"
    assert "Comparable quality-session execution is stable" in state["progression_evidence"]
