from app.ai import functions
from app.ai.functions import (
    PlanAdaptationOutput,
    SessionAnalysisOutput,
    WeeklyReviewOutput,
    extract_workout_from_text,
    generate_weekly_review,
    propose_plan_adaptation,
)
from app.enums import AdaptationAction


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
    assert result.session_type.value == "Threshold"
    assert result.rpe.value == 7
    assert result.intervals.value == ["1 km @ 4:20"]
    assert {"max_hr", "splits", "intervals"}.issubset(captured["schema"]["properties"])


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
            "execution_summary": "Controlled execution",
            "planned_vs_actual": ["RPE matched target"],
            "strong_execution": True,
            "unexpected_fatigue": False,
            "evidence": ["RPE 7"],
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
