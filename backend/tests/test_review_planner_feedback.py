from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.ai.functions import MonthlyReviewPlanOutput, WeeklyReviewPlanOutput
from app.enums import PlanStatus, SessionPriority, Sport
from app.services import planning


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _running_payload(day: date, feedback: str) -> dict[str, object]:
    return {
        "date": day.isoformat(),
        "workout_kind": "RUNNING",
        "session_type": "Easy",
        "duration_minutes": 45,
        "rpe": 5,
        "distance_km": 8,
        "subjective_feedback_text": feedback,
        "subjective_feedback_source": "VOICE",
    }


def test_running_feedback_is_saved_on_completed_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.application.core.analyse_completed_session_with_ai",
        lambda *_args, **_kwargs: None,
    )
    response = client.post(
        "/api/v1/completed-sessions",
        json=_running_payload(date.today(), "前半程輕鬆，後段腿有一點沉。"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["subjective_feedback_text"] == "前半程輕鬆，後段腿有一點沉。"
    assert body["subjective_feedback_source"] == "VOICE"
    assert body["subjective_feedback_created_at"]


def test_running_feedback_rejected_for_non_running_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/completed-sessions",
        json={
            "date": date.today().isoformat(),
            "workout_kind": "CLIMBING",
            "session_type": "Bouldering",
            "duration_minutes": 60,
            "subjective_feedback_text": "run feedback",
            "subjective_feedback_source": "TEXT",
        },
    )
    assert response.status_code == 422


def test_running_feedback_transcription_is_preview_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_transcribe(_db, _raw, **kwargs):  # noqa: ANN001, ANN202
        seen.update(kwargs)
        return "legs felt heavy late"

    monkeypatch.setattr("app.api.media.transcribe_audio", fake_transcribe)
    response = client.post(
        "/api/v1/ai/running-feedback/transcribe",
        data={"retain_raw": "false"},
        files={"audio": ("run.webm", b"\x1aE\xdf\xa3audio", "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json() == {"transcript": "legs felt heavy late"}
    assert seen["purpose"] == "RUNNING_FEEDBACK"
    assert seen["retain_raw"] is False
    assert client.get("/api/v1/completed-sessions").json()["total"] == 0


def test_workout_voice_input_transcribes_to_preview_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_transcribe(_db, _raw, **kwargs):  # noqa: ANN001, ANN202
        seen.update(kwargs)
        return "10 km easy，52 分鐘，RPE 3"

    monkeypatch.setattr("app.api.media.transcribe_audio", fake_transcribe)
    response = client.post(
        "/api/v1/ai/workouts/transcribe",
        files={"audio": ("workout.webm", b"\x1aE\xdf\xa3audio", "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json() == {"transcript": "10 km easy，52 分鐘，RPE 3"}
    assert seen["purpose"] == "WORKOUT_IMPORT"
    assert seen["retain_raw"] is False
    assert client.get("/api/v1/completed-sessions").json()["total"] == 0


def test_weekly_context_uses_compact_feedback_and_approval_preserves_existing(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    week_start = _monday(date.today())
    feedback = "腿很沉 " + ("但心率正常 " * 80)
    from app.services import core

    payload = _running_payload(week_start + timedelta(days=1), feedback)
    payload["date"] = week_start + timedelta(days=1)
    core.create_completed_session(db, payload)
    locked = models.PlannedSession(
        athlete_id=1,
        session_date=week_start + timedelta(days=8),
        sport=Sport.RUNNING,
        workout_type="Easy",
        title="Locked easy run",
        description="Do not change",
        priority=SessionPriority.HIGH,
        status=PlanStatus.PLANNED,
        structured_blocks=[],
        is_locked=True,
    )
    db.add(locked)
    db.commit()
    captured: dict[str, object] = {}

    def fake_week(context):  # noqa: ANN001, ANN202
        captured.update(context)
        target = week_start + timedelta(days=8)
        return WeeklyReviewPlanOutput.model_validate(
            {
                "review": {
                    "summary": "Useful week",
                    "running_analysis": "Heavy legs matter despite normal HR.",
                    "climbing_analysis": "No climbing evidence.",
                    "recovery_analysis": "Monitor recovery.",
                    "key_findings": ["Repeated heavy legs"],
                },
                "next_week": {
                    "summary": "Conservative build",
                    "running_target_km": 30,
                    "running_objectives": ["Keep easy work easy"],
                    "climbing_objectives": [],
                    "sessions": [
                        {
                            "date": target.isoformat(),
                            "start_time": None,
                            "workout_kind": "RUNNING",
                            "session_type": "Easy",
                            "title": "Generated easy run",
                            "description": "Easy aerobic run",
                            "planned_duration_minutes": 45,
                            "planned_distance_km": 8,
                            "target_rpe": 3,
                            "priority": "NORMAL",
                            "structured_blocks": [],
                        },
                        {
                            "date": (target + timedelta(days=2)).isoformat(),
                            "start_time": None,
                            "workout_kind": "CLIMBING",
                            "session_type": "Technique",
                            "title": "Technique climbing",
                            "description": "Low fatigue",
                            "planned_duration_minutes": 60,
                            "planned_distance_km": None,
                            "target_rpe": 5,
                            "priority": "NORMAL",
                            "structured_blocks": [],
                        },
                    ],
                    "warnings": [],
                },
            }
        )

    monkeypatch.setattr(planning, "ai_review_and_plan_week", fake_week)
    proposal = planning.review_and_plan_week(db, week_start)
    feedback_rows = captured["running_subjective_feedback"]
    assert len(feedback_rows) == 1
    assert feedback_rows[0]["feedback"].startswith("腿很沉")
    assert len(feedback_rows[0]["feedback"]) <= 240
    approved = planning.approve_proposal(db, proposal.id)
    assert approved.approval_result["created_session_ids"]
    assert (
        approved.approval_result["preserved_existing"][0]["reason"] == "existing session preserved"
    )
    db.refresh(locked)
    assert locked.title == "Locked easy run"
    assert locked.is_locked is True


def test_monthly_context_excludes_raw_running_transcripts_and_approval_saves_block(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    month_start = date.today().replace(day=1)
    sentinel = "RAW-VOICE-SENTINEL-DO-NOT-SEND-MONTHLY"
    from app.services import core

    payload = _running_payload(month_start, sentinel)
    payload["date"] = month_start
    core.create_completed_session(db, payload)
    weekly_start = _monday(month_start)
    db.add(
        models.WeeklyReview(
            week_start=weekly_start,
            week_end=weekly_start + timedelta(days=6),
            summary={
                "running_distance_km": 8,
                "running_subjective_feedback": [{"feedback": sentinel}],
            },
            compliance={},
            running=["8 km"],
            climbing=[],
            recovery=[],
            key_findings=["legs felt heavy twice"],
            next_week=[],
            narrative="Weekly aggregate",
            source="AI",
        )
    )
    db.commit()
    context = planning.build_monthly_planning_context(db, month_start)
    assert sentinel not in json.dumps(context, ensure_ascii=False)
    assert "legs felt heavy twice" in json.dumps(context)

    def fake_month(payload):  # noqa: ANN001, ANN202
        assert sentinel not in json.dumps(payload, ensure_ascii=False)
        return MonthlyReviewPlanOutput.model_validate(
            {
                "review": {
                    "summary": "Stable month",
                    "running_analysis": "Volume was consistent.",
                    "climbing_analysis": "Technique work was stable.",
                    "recovery_analysis": "Recovery was adequate.",
                    "goal_progress": "On track.",
                    "key_findings": ["Hold intensity"],
                },
                "next_month_block": {
                    "running_phase": "AEROBIC_BASE",
                    "climbing_phase": "TECHNIQUE_VOLUME",
                    "running_objectives": ["Build consistency"],
                    "climbing_objectives": ["Improve movement quality"],
                    "weekly_running_volume_targets": [30, 32, 34, 26],
                    "quality_session_guidance": "One threshold session weekly.",
                    "long_run_guidance": "Progress conservatively.",
                    "climbing_frequency_guidance": "Two sessions weekly.",
                    "climbing_focus": ["Technique"],
                    "supporting_strength_guidance": "One short session.",
                    "progression_criteria": ["Stable readiness"],
                    "hold_criteria": ["Unexpected fatigue"],
                    "deload_criteria": ["Low readiness"],
                },
            }
        )

    monkeypatch.setattr(planning, "ai_review_and_plan_month", fake_month)
    proposal = planning.review_and_plan_month(db, month_start)
    approved = planning.approve_proposal(db, proposal.id)
    block = db.scalar(
        select(models.MonthlyTrainingBlock).where(
            models.MonthlyTrainingBlock.source_proposal_id == approved.id
        )
    )
    assert block is not None
    assert block.content["weekly_running_volume_targets"] == [30.0, 32.0, 34.0, 26.0]
