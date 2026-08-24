import pytest

from app.ai import functions
from app.ai.functions import (
    AIUnavailableError,
    PlanAdaptationOutput,
    SessionAnalysisOutput,
    WeeklyReviewOutput,
    extract_workout_from_text,
    generate_weekly_review,
    propose_plan_adaptation,
)
from app.enums import AdaptationAction
from app.services.serializers import compact_session_analysis


def test_workout_extraction_contract_preserves_rpe_and_structured_fields(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    def fake_call(**kwargs):  # noqa: ANN003, ANN202
        captured.update(kwargs)
        return {
            name: {
                "value": (
                    "RUNNING"
                    if name == "workout_kind"
                    else "Threshold"
                    if name in {"session_type", "activity_type"}
                    else 7
                    if name == "rpe"
                    else ["1 km @ 4:20"]
                    if name == "intervals"
                    else None
                ),
                "confidence": "HIGH" if name in {"workout_kind", "session_type", "rpe"} else "LOW",
                "source": "explicit text"
                if name in {"workout_kind", "session_type", "rpe"}
                else "not present",
            }
            for name in functions.WORKOUT_FIELDS
        }

    monkeypatch.setattr(functions, "_responses_json", fake_call)
    result = extract_workout_from_text("Threshold run, RPE 7")
    assert result.workout_kind.value == "RUNNING"
    assert result.session_type.value == "QUALITY"
    assert result.rpe.value == 7
    assert result.intervals.value == ["1 km @ 4:20"]
    assert {"title", "board_name", "angle", "max_hr", "splits", "intervals"}.issubset(
        captured["schema"]["properties"]
    )


def test_workout_extraction_normalises_voice_friendly_formats(monkeypatch) -> None:  # noqa: ANN001
    def fake_call(**_kwargs):  # noqa: ANN003, ANN202
        values = {
            "workout_kind": "RUNNING",
            "session_type": "Easy",
            "activity_type": "Running",
            "date": "今天",
            "duration_minutes": 62,
            "average_pace": "5分08秒 /km",
            "average_hr": 145.4,
            "max_hr": 171.8,
            "rpe": 4,
        }
        return {
            name: {
                "value": values.get(name),
                "confidence": "HIGH" if name in values else "LOW",
                "source": "spoken text" if name in values else "not present",
            }
            for name in functions.WORKOUT_FIELDS
        }

    monkeypatch.setattr(functions, "_responses_json", fake_call)
    result = extract_workout_from_text(
        "今天 easy run 62 分鐘，平均配速 5分08秒，心率 145，RPE 4",
        reference_date=functions.date(2026, 8, 23),
    )
    assert result.date.value == "2026-08-23"
    assert result.duration_minutes.value == 62
    assert result.average_pace.value == "5:08"
    assert result.average_hr.value == 145
    assert result.max_hr.value == 172


def test_typed_adaptation_contract_rejects_unrestricted_action(monkeypatch) -> None:  # noqa: ANN001
    def fake_call(**_kwargs):  # noqa: ANN003, ANN202
        return {
            "action": "MOVE",
            "proposed_plan": {
                "date": "2026-08-25",
                "session_type": None,
                "title": None,
                "description": None,
                "planned_duration_minutes": None,
                "planned_distance_km": None,
                "target_rpe": None,
                "structured_blocks": None,
            },
            "reason": "Finger fatigue conflicts with max hangs.",
            "evidence": ["FINGER_FOREARM 9.2"],
            "confidence": "HIGH",
        }

    monkeypatch.setattr(functions, "_responses_json", fake_call)
    output = propose_plan_adaptation(
        {
            "primary_goal": "BOULDERING",
            "running_phase": "AEROBIC_BASE",
            "climbing_phase": "LIMIT_BOULDERING",
            "recent_workouts": [],
            "fatigue": {"FINGER_FOREARM": 9.2},
            "readiness": {"climbing": "LOW"},
            "upcoming_seven_days": [],
            "deterministic_rule_result": {"action": "MOVE"},
            "approved_coaching_principles": [],
        }
    )
    assert isinstance(output, PlanAdaptationOutput)
    assert output.action == AdaptationAction.MOVE


def test_session_and_weekly_ai_have_distinct_typed_outputs(monkeypatch) -> None:  # noqa: ANN001
    def fake_session(**_kwargs):  # noqa: ANN003, ANN202
        return {
            "summary": "Controlled execution; RPE matched the target.",
            "confidence": "MODERATE",
        }

    monkeypatch.setattr(functions, "_responses_json", fake_session)
    session = functions.analyse_completed_session(
        {
            "primary_goal": "HALF_MARATHON",
            "running_phase": "THRESHOLD_BUILD",
            "climbing_phase": "TECHNIQUE_VOLUME",
            "planned_workout": {},
            "completed_workout": {},
            "fatigue": {},
            "readiness": {},
        }
    )
    assert isinstance(session, SessionAnalysisOutput)
    assert len(session.summary) <= 200

    def fake_weekly(**_kwargs):  # noqa: ANN003, ANN202
        return {
            "summary": ["Balanced week"],
            "running": ["30 km"],
            "climbing": ["180 min"],
            "recovery": ["Sleep stable"],
            "key_findings": ["Load tolerated"],
            "next_week": ["Hold volume"],
            "confidence": "MODERATE",
        }

    monkeypatch.setattr(functions, "_responses_json", fake_weekly)
    weekly = generate_weekly_review(
        {
            "goals": [],
            "phases": {"running": "AEROBIC_BASE", "climbing": "TECHNIQUE_VOLUME"},
            "planned_week": [],
            "completed_week": [],
            "recent_four_week_trends": {},
            "recovery": [],
        }
    )
    assert isinstance(weekly, WeeklyReviewOutput)


def test_session_analysis_enforces_200_character_limit(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        functions,
        "_responses_json",
        lambda **_kwargs: {"summary": "x" * 201, "confidence": "LOW"},
    )
    with pytest.raises(AIUnavailableError):
        functions.analyse_completed_session(
            {
                "primary_goal": "HALF_MARATHON",
                "running_phase": "AEROBIC_BASE",
                "climbing_phase": "TECHNIQUE_VOLUME",
                "planned_workout": {},
                "completed_workout": {},
                "fatigue": {},
                "readiness": {},
            }
        )


def test_legacy_session_analysis_is_compacted_for_display() -> None:
    compact = compact_session_analysis(
        {"execution_summary": f"  {'long ' * 80}  ", "confidence": "MODERATE"}
    )
    assert compact is not None
    assert len(compact["summary"]) == 200
    assert compact["summary"].endswith("…")
    assert compact["confidence"] == "MODERATE"
