from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import models
from app.enums import Confidence, NoteCategory, NoteInputType
from app.services import core, notes


def seed_demo(db: Session, today: date | None = None) -> int:
    if db.scalar(
        select(func.count(models.CompletedSession.id)).where(models.CompletedSession.is_demo)
    ):
        return 0
    day = today or date.today()
    created = 0
    running_rows = [
        (27, "EASY", 7.0, 42, 3),
        (25, "QUALITY", 9.5, 58, 7),
        (23, "EASY", 8.0, 48, 3),
        (20, "LONG_RUN", 14.0, 90, 5),
        (18, "RACE", 10.0, 45, 9),
        (16, "EASY", 8.0, 47, 3),
        (13, "QUALITY", 10.0, 62, 7),
        (9, "EASY", 9.0, 52, 3),
        (6, "LONG_RUN", 16.0, 102, 5),
        (3, "QUALITY", 10.0, 60, 7),
    ]
    for ago, workout_type, distance, duration, rpe in running_rows:
        core.create_completed_session(
            db,
            {
                "date": day - timedelta(days=ago),
                "workout_kind": "RUNNING",
                "session_type": workout_type,
                "duration_minutes": duration,
                "distance_km": distance,
                "rpe": rpe,
                "average_hr": 145 if workout_type == "EASY" else 168,
                "average_pace": duration * 60 / distance,
                "is_demo": True,
            },
        )
        created += 1
    for ago, kind, duration, rpe, attempts in [
        (22, "BOULDERING", 90, 4, 8),
        (15, "BOARD", 105, 8, 15),
        (8, "BOULDERING", 120, 8, 18),
        (0, "BOULDERING", 145, 9, 22),
    ]:
        core.create_completed_session(
            db,
            {
                "date": day - timedelta(days=ago),
                "workout_kind": "CLIMBING",
                "session_type": kind,
                "duration_minutes": duration,
                "rpe": rpe,
                "hard_attempts": attempts,
                "gym_or_crag": "Demo Climbing Centre",
                "max_sent": "6C",
                "is_demo": True,
            },
        )
        created += 1
    core.create_completed_session(
        db,
        {
            "date": day - timedelta(days=5),
            "workout_kind": "STRENGTH",
            "session_type": "Strength",
            "duration_minutes": 60,
            "rpe": 7,
            "strength_sets": [
                {"exercise": "weighted pull-up", "sets": 4, "reps": 4, "load": 20},
                {"exercise": "deadlift", "sets": 3, "reps": 5, "load": 100},
            ],
            "is_demo": True,
        },
    )
    created += 1
    core.create_planned_session(
        db,
        {
            "date": day + timedelta(days=1),
            "workout_kind": "STRENGTH",
            "session_type": "Max Hangs",
            "title": "Max hangs",
            "planned_duration_minutes": 45,
            "target_rpe": 8,
            "priority": "HIGH",
            "is_demo": True,
        },
    )
    created += 1
    gym = core.create_gym_set(
        db,
        {
            "gym": "Demo Climbing Centre",
            "start_date": day - timedelta(days=30),
            "notes": "DEMO DATA",
            "progress": [
                {"colour": "Yellow", "sent_count": 8, "available_problem_count": 8},
                {"colour": "Green", "sent_count": 7, "available_problem_count": 8},
                {"colour": "Purple", "sent_count": 5, "available_problem_count": 7},
                {"colour": "Grey", "sent_count": 3, "available_problem_count": 8},
                {"colour": "Blue", "sent_count": 1, "available_problem_count": 6},
            ],
            "is_demo": True,
        },
    )
    created += 1 if gym else 0
    benchmark = models.TB2Benchmark(
        athlete_id=1,
        benchmark_date=day - timedelta(days=20),
        angle_degrees=40,
        verified_grade="6C",
        estimated_grade="6C+",
        notes="DEMO DATA",
        is_demo=True,
    )
    db.add(benchmark)
    core.create_recovery_checkin(
        db,
        {
            "date": day,
            "sleep_duration_hours": 6.5,
            "sleep_quality": 3,
            "energy": 3,
            "stress": 3,
            "general_soreness": 4,
            "soreness": {"finger": 4},
            "is_demo": True,
        },
    )
    notes.create_note(
        db,
        {
            "primary_category": NoteCategory.RUNNING,
            "title": "Controlled threshold work (DEMO)",
            "raw_input": "Keep threshold work around RPE 7 to preserve repeatability.",
            "cleaned_note": "Keep threshold work controlled enough to preserve repeatability.",
            "summary": "Controlled threshold work supports repeatability.",
            "key_takeaways": ["Avoid racing every threshold session"],
            "tags": ["threshold", "RPE"],
            "input_type": NoteInputType.TEXT,
            "classification_confidence": Confidence.HIGH,
            "use_for_coaching": False,
            "is_demo": True,
        },
    )
    db.commit()
    return created + 3


def remove_demo(db: Session) -> int:
    counts = []
    demo_session_ids = select(models.CompletedSession.id).where(
        models.CompletedSession.is_demo.is_(True)
    )
    demo_plan_ids = select(models.PlannedSession.id).where(models.PlannedSession.is_demo.is_(True))
    adaptation_result = db.execute(
        delete(models.AdaptationEvent).where(
            (models.AdaptationEvent.trigger_session_id.in_(demo_session_ids))
            | (models.AdaptationEvent.affected_session_id.in_(demo_plan_ids))
        )
    )
    counts.append(adaptation_result.rowcount or 0)
    # Child rows cascade from completed sessions, plans and gym sets.
    for model in (
        models.RunningFitnessEstimate,
        models.ThresholdEstimate,
        models.TrainingNote,
        models.RecoveryCheckin,
        models.TB2Benchmark,
        models.GymSet,
        models.CompletedSession,
        models.PlannedSession,
    ):
        result = db.execute(delete(model).where(model.is_demo.is_(True)))
        counts.append(result.rowcount or 0)
    db.commit()
    return sum(counts)
