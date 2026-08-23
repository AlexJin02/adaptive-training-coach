from __future__ import annotations

import json
from datetime import date, time
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai import (
    AIUnavailableError,
    extract_workout_from_text,
    process_training_note,
)
from app.config import get_settings
from app.db import DatabaseSession, get_db
from app.enums import (
    ClimbingPhase,
    Confidence,
    EstimateType,
    NoteCategory,
    NoteInputType,
    PlanStatus,
    RunningPhase,
    SessionPriority,
    Sport,
)
from app.services import (
    application,
    core,
    data_portability,
    demo,
    media,
    notes,
    planning,
    reporting,
    serializers,
    settings_service,
    uploads,
)

router = APIRouter()
DateType = date


class InputModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ProfilePatch(InputModel):
    display_name: str | None = None
    timezone: str | None = None
    current_half_marathon_seconds: int | None = Field(None, gt=0)
    current_monthly_km: float | None = Field(None, ge=0)
    long_term_monthly_km: float | None = Field(None, ge=0)
    stable_weekly_min_km: float | None = Field(None, ge=0)
    stable_weekly_max_km: float | None = Field(None, ge=0)
    half_marathon_primary_goal_seconds: int | None = Field(None, gt=0)
    half_marathon_stretch_goal_seconds: int | None = Field(None, gt=0)
    marathon_goal_seconds: int | None = Field(None, gt=0)
    tb2_verified_grade: str | None = None
    tb2_estimated_grade: str | None = None
    top_rope_grade: str | None = None
    tb2_long_term_goal: str | None = None
    outdoor_boulder_goal: str | None = None
    bouldering_goal: str | None = None
    route_goal: str | None = None
    running_phase: RunningPhase | None = None
    climbing_phase: ClimbingPhase | None = None


class GoalInput(InputModel):
    goal_type: str
    description: str = ""
    target_value: str | None = None
    target_date: date | None = None
    current_status: str | None = "ACTIVE"
    notes: str | None = ""
    is_current: bool = False


class PlannedSessionInput(InputModel):
    date: date
    start_time: time | None = None
    workout_kind: Sport
    session_type: str
    title: str | None = None
    description: str | None = None
    planned_duration_minutes: float | None = Field(None, gt=0)
    planned_distance_km: float | None = Field(None, ge=0)
    target_rpe: float | None = Field(None, ge=1, le=10)
    priority: SessionPriority = SessionPriority.NORMAL
    status: PlanStatus = PlanStatus.PLANNED
    structured_blocks: list[dict[str, Any]] = Field(default_factory=list)
    is_locked: bool = False


class CompletedSessionInput(InputModel):
    date: date
    start_time: time | None = None
    workout_kind: Sport
    session_type: str
    duration_minutes: float = Field(gt=0)
    rpe: float | None = Field(None, ge=1, le=10)
    notes: str | None = None
    planned_session_id: int | str | None = None
    distance_km: float | None = Field(None, ge=0)
    average_pace: str | float | None = None
    average_pace_seconds_per_km: float | None = Field(None, gt=0)
    average_hr: int | None = Field(None, gt=0)
    max_hr: int | None = Field(None, gt=0)
    elevation_m: float | None = None
    cadence: float | None = Field(None, gt=0)
    power_w: float | None = Field(None, gt=0)
    gym_or_crag: str | None = None
    hard_attempts: int | None = Field(None, ge=0)
    max_attempted: str | None = None
    max_sent: str | None = None
    grade_scale: str | None = None
    workout_name: str | None = None
    rounds: float | None = Field(None, ge=0)
    result_time: str | None = None
    result_time_seconds: float | None = Field(None, ge=0)
    interval_blocks: list[dict[str, Any]] = Field(default_factory=list)
    splits: list[dict[str, Any]] = Field(default_factory=list)
    climbing_attempts: list[dict[str, Any]] = Field(default_factory=list)
    strength_sets: list[dict[str, Any]] = Field(default_factory=list)
    extraction_reviewed: bool = False
    extraction_fields: dict[str, Any] | None = None
    subjective_feedback_text: str | None = Field(None, max_length=5000)
    subjective_feedback_source: Literal["VOICE", "TEXT", "NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_subjective_feedback(self) -> CompletedSessionInput:
        text = (self.subjective_feedback_text or "").strip()
        if self.workout_kind != Sport.RUNNING and text:
            raise ValueError("subjective running feedback is only valid for RUNNING sessions")
        if not text:
            self.subjective_feedback_text = None
            self.subjective_feedback_source = "NONE"
        elif self.subjective_feedback_source == "NONE":
            self.subjective_feedback_source = "TEXT"
        return self

    @model_validator(mode="after")
    def derive_result_time_seconds(self) -> CompletedSessionInput:
        if self.result_time_seconds is not None or not self.result_time:
            return self
        parts = self.result_time.strip().split(":")
        try:
            values = [float(part) for part in parts]
        except ValueError:
            return self
        if len(values) == 1 and values[0] >= 0:
            self.result_time_seconds = values[0]
        elif len(values) == 2 and values[0] >= 0 and 0 <= values[1] < 60:
            self.result_time_seconds = values[0] * 60 + values[1]
        elif len(values) == 3 and values[0] >= 0 and 0 <= values[1] < 60 and 0 <= values[2] < 60:
            self.result_time_seconds = values[0] * 3600 + values[1] * 60 + values[2]
        return self


class RecoveryInput(InputModel):
    date: date
    sleep_duration_hours: float | None = Field(None, ge=0, le=24)
    sleep_quality: int | None = Field(None, ge=1, le=5)
    energy: int | None = Field(None, ge=1, le=5)
    motivation: int | None = Field(None, ge=1, le=5)
    stress: int | None = Field(None, ge=1, le=5)
    general_soreness: float | None = Field(None, ge=0, le=10)
    soreness: dict[str, float] = Field(default_factory=dict)
    resting_hr: int | None = Field(None, gt=0)
    hrv: float | None = Field(None, ge=0)
    notes: str | None = None

    @field_validator("soreness")
    @classmethod
    def validate_soreness(cls, value: dict[str, float]) -> dict[str, float]:
        allowed = {"finger", "elbow", "shoulder", "back", "hip", "knee", "calf", "ankle"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown soreness areas: {sorted(unknown)}")
        if any(not 0 <= score <= 10 for score in value.values()):
            raise ValueError("Area soreness values must be between 0 and 10")
        return value


class PhaseInput(InputModel):
    phase: str


class TB2Input(InputModel):
    date: date
    board: Literal["TB2"] = "TB2"
    angle: int = Field(ge=0, le=90)
    verified_grade: str
    estimated_grade: str | None = None
    notes: str | None = None


class GymColourProgressInput(InputModel):
    colour: Literal["Yellow", "Green", "Purple", "Grey", "Blue", "Red", "Black"]
    ordinal: int | None = Field(None, ge=1)
    sent_count: int = Field(ge=0)
    available_problem_count: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> GymColourProgressInput:
        if (
            self.available_problem_count is not None
            and self.sent_count > self.available_problem_count
        ):
            raise ValueError("sent_count cannot exceed available_problem_count")
        return self


class GymSetInput(InputModel):
    gym: str
    start_date: date
    notes: str | None = None
    progress: list[GymColourProgressInput] = Field(default_factory=list)


class GymProgressPatch(InputModel):
    progress: list[GymColourProgressInput]


class RouteInput(InputModel):
    top_rope_verified_grade: str | None = None
    lead_verified_grade: str | None = None
    target_grade: str | None = None
    last_updated: date | None = None
    notes: str | None = None


class NoteInput(InputModel):
    primary_category: NoteCategory
    title: str
    raw_input: str
    cleaned_note: str | None = None
    summary: str | None = None
    key_takeaways: list[str] = Field(default_factory=list)
    actionable_ideas: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_title: str | None = None
    source_creator: str | None = None
    source_url: str | None = None
    input_type: NoteInputType = NoteInputType.TEXT
    classification_confidence: Confidence | None = None
    use_for_coaching: bool = False
    favorite: bool = False


class NoteProcessInput(InputModel):
    raw_input: str = Field(min_length=1)
    input_type: NoteInputType = NoteInputType.TEXT


class TextExtractionInput(InputModel):
    text: str = Field(min_length=1)


class AdaptationPlanEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | str | None = None
    date: DateType | None = None
    session_date: DateType | None = None
    start_time: time | None = None
    workout_kind: Sport | None = None
    sport: Sport | None = None
    session_type: str | None = None
    workout_type: str | None = None
    title: str | None = None
    description: str | None = None
    planned_duration_minutes: float | None = Field(None, gt=0)
    planned_distance_km: float | None = Field(None, ge=0)
    target_rpe: float | None = Field(None, ge=1, le=10)
    priority: SessionPriority | None = None
    status: PlanStatus | None = None
    structured_blocks: list[dict[str, Any]] | None = None
    original_session_id: int | str | None = None
    is_demo: bool | None = None
    is_locked: bool | None = None
    progressed_variable: Literal["volume", "intensity", "none"] | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_aliases(self) -> AdaptationPlanEdit:
        if (
            self.date is not None
            and self.session_date is not None
            and self.date != self.session_date
        ):
            raise ValueError("date and session_date must match when both are provided")
        if (
            self.workout_kind is not None
            and self.sport is not None
            and self.workout_kind != self.sport
        ):
            raise ValueError("workout_kind and sport must match when both are provided")
        if (
            self.session_type is not None
            and self.workout_type is not None
            and self.session_type != self.workout_type
        ):
            raise ValueError("session_type and workout_type must match when both are provided")
        return self


class AdaptationDecisionInput(InputModel):
    decision: str
    proposed_plan: AdaptationPlanEdit | None = None

    @field_validator("proposed_plan", mode="before")
    @classmethod
    def parse_proposed_plan(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("proposed_plan must be a JSON object") from exc
        if not isinstance(parsed, dict):
            raise ValueError("proposed_plan must be a JSON object")
        return parsed


class WeeklyReviewInput(InputModel):
    week_start: date


class MonthlyReviewPlanInput(InputModel):
    month_start: date


class PlanningProposalEdit(InputModel):
    proposed_plan: dict[str, Any]


class CoachingPrincipleInput(InputModel):
    principle: str = Field(min_length=1)
    source_note_id: int | None = None


class SettingsPatch(InputModel):
    gym_name: str | None = None
    grade_display: str | None = None
    retain_screenshots: bool | None = None
    retain_audio: bool | None = None
    engine: dict[str, Any] | None = None


class RunningEstimateInput(InputModel):
    estimated_10k_seconds: float | None = Field(None, gt=0)
    confidence: Confidence
    source_event: str
    source_date: date
    formula: str
    evidence: str = ""


class ThresholdEstimateInput(InputModel):
    estimate_type: EstimateType
    pace_low_seconds_per_km: float | None = Field(None, gt=0)
    pace_high_seconds_per_km: float | None = Field(None, gt=0)
    hr_low: int | None = Field(None, gt=0)
    hr_high: int | None = Field(None, gt=0)
    confidence: Confidence
    source: str
    measured_at: date


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    settings = get_settings()
    configured = bool(settings.openai_api_key)
    return {
        "ai_configured": configured,
        "image_extraction": configured,
        "text_extraction": configured,
        "transcription": configured,
        "note_processing": configured,
        "ai_session_analysis": configured,
        "ai_adaptation": configured,
        "ai_weekly_review": configured,
        "ai_planner": configured,
        "model": settings.openai_model if configured else None,
        "planner_model": settings.openai_planner_model if configured else None,
        "vision_model": settings.openai_vision_model if configured else None,
        "transcription_model": settings.openai_transcribe_model if configured else None,
        "reason": None
        if configured
        else "OPENAI_API_KEY is not configured; core features still work.",
    }


@router.get("/athlete/profile")
def athlete_profile(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    return serializers.athlete_profile(core.get_profile(db))


@router.patch("/athlete/profile")
def patch_athlete_profile(
    payload: ProfilePatch, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    return serializers.athlete_profile(
        core.update_profile(db, payload.model_dump(exclude_none=True))
    )


@router.get("/goals")
def goals(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    items = application.list_goals(db)
    return {"items": [serializers.goal(item) for item in items], "total": len(items)}


@router.post("/goals", status_code=status.HTTP_201_CREATED)
def save_goal(payload: GoalInput, db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    try:
        return serializers.goal(core.create_goal(db, payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/planned-sessions")
def planned_sessions(
    start: date | None = None, end: date | None = None, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    items = application.list_planned_sessions(db, start, end)
    return {"items": [serializers.planned_session(item) for item in items], "total": len(items)}


@router.post("/planned-sessions", status_code=status.HTTP_201_CREATED)
def save_planned_session(
    payload: PlannedSessionInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    return serializers.planned_session(core.create_planned_session(db, payload.model_dump()))


@router.patch("/planned-sessions/{session_id}")
def patch_planned_session(
    session_id: int, payload: dict[str, Any], db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        return serializers.planned_session(
            application.update_planned_session(db, session_id, payload)
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/planned-sessions/{session_id}/skip")
def skip_planned_session(session_id: int, db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    try:
        item, proposals = application.skip_planned_session(db, session_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "session": serializers.planned_session(item),
        "adaptations": [serializers.adaptation(proposal) for proposal in proposals],
    }


@router.get("/completed-sessions")
def completed_sessions(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    items = core.list_completed_sessions(db)
    return {"items": [serializers.completed_session(item) for item in items], "total": len(items)}


@router.post("/completed-sessions", status_code=status.HTTP_201_CREATED)
def save_completed_session(
    payload: CompletedSessionInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        item = application.record_completed_session(db, payload.model_dump())
        return serializers.completed_session(item)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/completed-sessions/{session_id}")
def delete_completed_session(
    session_id: int, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        deleted_id = application.delete_completed_session(db, session_id)
        return {"deleted": True, "id": deleted_id}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/recovery-checkins", status_code=status.HTTP_201_CREATED)
def save_recovery_checkin(
    payload: RecoveryInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    item = application.record_recovery_checkin(db, payload.model_dump())
    return {
        "id": item.id,
        "date": item.recorded_at.date().isoformat(),
        "sleep_duration_hours": item.sleep_duration_hours,
        "sleep_quality": item.sleep_quality,
        "energy": item.energy,
        "motivation": item.motivation,
        "stress": item.stress,
        "general_soreness": item.general_soreness,
        "soreness": item.area_soreness,
        "resting_hr": item.resting_hr,
        "hrv": item.hrv,
    }


@router.get("/load-readiness/fatigue")
def fatigue(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    fatigue_result, _, _ = core.current_load_readiness(db)
    timestamp = fatigue_result.calculated_at.isoformat()
    half_lives = core.engine_configuration(db)["half_lives"]
    items = serializers.fatigue_values(
        fatigue_result.latent, fatigue_result.display, timestamp, half_lives
    )
    return {"items": items, "total": len(items)}


@router.get("/load-readiness/readiness")
def readiness(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    fatigue_result, result, _ = core.current_load_readiness(db)
    timestamp = fatigue_result.calculated_at.isoformat()
    engine = core.engine_configuration(db)
    items = [
        serializers.readiness_summary(
            sport=Sport.RUNNING,
            value=result.running_score,
            label=result.running_label,
            components=result.running_components,
            updated_at=timestamp,
            explanation="Weighted running fatigue plus a bounded recovery modifier.",
            good_threshold=engine["readiness_good_threshold"],
            moderate_threshold=engine["readiness_moderate_threshold"],
            subjective_delta=result.subjective_delta,
            local_soreness_penalty=result.local_soreness_penalty,
            warnings=result.warnings,
        ),
        serializers.readiness_summary(
            sport=Sport.CLIMBING,
            value=result.climbing_score,
            label=result.climbing_label,
            components=result.climbing_components,
            updated_at=timestamp,
            explanation="Weighted climbing fatigue plus bounded recovery and local soreness.",
            good_threshold=engine["readiness_good_threshold"],
            moderate_threshold=engine["readiness_moderate_threshold"],
            subjective_delta=result.subjective_delta,
            local_soreness_penalty=result.local_soreness_penalty,
            warnings=result.warnings,
        ),
    ]
    return {"items": items, "total": len(items), "warnings": list(result.warnings)}


@router.get("/athlete-state/running")
def athlete_state_running(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    return core.running_state(db)


@router.post("/athlete-state/running/estimates", status_code=status.HTTP_201_CREATED)
def create_running_estimate(
    payload: RunningEstimateInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    item = application.create_running_estimate(db, payload.model_dump())
    return {
        "id": item.id,
        "value": item.estimated_10k_seconds,
        "confidence": item.confidence.value,
        "source": item.source_event,
        "source_date": item.source_date.isoformat(),
        "formula": item.formula,
        "evidence": [item.evidence] if item.evidence else [],
    }


@router.post("/athlete-state/running/threshold-estimates", status_code=status.HTTP_201_CREATED)
def create_threshold_estimate(
    payload: ThresholdEstimateInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    if (
        payload.pace_low_seconds_per_km
        and payload.pace_high_seconds_per_km
        and payload.pace_low_seconds_per_km > payload.pace_high_seconds_per_km
    ):
        raise HTTPException(422, "pace_low_seconds_per_km cannot exceed pace_high")
    if payload.hr_low and payload.hr_high and payload.hr_low > payload.hr_high:
        raise HTTPException(422, "hr_low cannot exceed hr_high")
    item = application.create_threshold_estimate(db, payload.model_dump())
    return {
        "id": item.id,
        "estimate_type": item.estimate_type.value,
        "pace_low_seconds_per_km": item.pace_low_seconds_per_km,
        "pace_high_seconds_per_km": item.pace_high_seconds_per_km,
        "hr_low": item.hr_low,
        "hr_high": item.hr_high,
        "confidence": item.confidence.value,
        "source": item.source,
        "measured_at": item.measured_at.isoformat(),
    }


@router.patch("/athlete-state/running/phase")
def set_running_phase(payload: PhaseInput, db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    try:
        core.update_profile(db, {"running_phase": RunningPhase(payload.phase)})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return core.running_state(db)


@router.get("/athlete-state/climbing")
def athlete_state_climbing(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    return core.climbing_state(db)


@router.patch("/athlete-state/climbing/phase")
def set_climbing_phase(
    payload: PhaseInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        core.update_profile(db, {"climbing_phase": ClimbingPhase(payload.phase)})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return core.climbing_state(db)


@router.get("/calendar")
def calendar(
    start: date = Query(...), end: date = Query(...), db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    if end < start:
        raise HTTPException(422, "end must be on or after start")
    items = core.calendar_entries(db, start, end)
    return {"items": items, "total": len(items)}


def _readiness_payloads(db: DatabaseSession) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    fatigue_result, result, _ = core.current_load_readiness(db)
    timestamp = fatigue_result.calculated_at.isoformat()
    engine = core.engine_configuration(db)
    running = serializers.readiness_summary(
        sport=Sport.RUNNING,
        value=result.running_score,
        label=result.running_label,
        components=result.running_components,
        updated_at=timestamp,
        explanation="Conservative planning heuristic; not a physiological measurement.",
        good_threshold=engine["readiness_good_threshold"],
        moderate_threshold=engine["readiness_moderate_threshold"],
        subjective_delta=result.subjective_delta,
        local_soreness_penalty=result.local_soreness_penalty,
        warnings=result.warnings,
    )
    climbing = serializers.readiness_summary(
        sport=Sport.CLIMBING,
        value=result.climbing_score,
        label=result.climbing_label,
        components=result.climbing_components,
        updated_at=timestamp,
        explanation="Conservative planning heuristic with local soreness safeguards.",
        good_threshold=engine["readiness_good_threshold"],
        moderate_threshold=engine["readiness_moderate_threshold"],
        subjective_delta=result.subjective_delta,
        local_soreness_penalty=result.local_soreness_penalty,
        warnings=result.warnings,
    )
    warnings = list(result.warnings)
    warnings.extend(
        f"{domain.value} fatigue is high ({value:.1f})."
        for domain, value in fatigue_result.display.items()
        if value >= 7.5
    )
    return running, climbing, warnings


@router.get("/today")
def today_dashboard(
    date_value: date | None = Query(None, alias="date"), db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    day = date_value or date.today()
    profile, goal, adaptations = application.today_context(db)
    running, climbing, warnings = _readiness_payloads(db)
    return {
        "date": day.isoformat(),
        "goal": serializers.goal(goal) if goal else None,
        "running_phase": profile.running_phase.value,
        "climbing_phase": profile.climbing_phase.value,
        "running_readiness": running,
        "climbing_readiness": climbing,
        "sessions": core.calendar_entries(db, day, day),
        "fatigue_warnings": warnings,
        "pending_adaptations": [serializers.adaptation(item, title) for item, title in adaptations],
    }


@router.get("/progress")
def progress(range: str = "3 months", db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    return reporting.progress_data(db, range)


@router.get("/adaptations")
def adaptations(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    items = application.list_adaptations(db)
    output = [serializers.adaptation(item, title) for item, title in items]
    return {"items": output, "total": len(output)}


@router.post("/adaptations/propose")
def propose_adaptation(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    items = application.propose_adaptations(db)
    output = [serializers.adaptation(item, title) for item, title in items]
    return {"items": output, "total": len(output)}


@router.post("/adaptations/{adaptation_id}/decision")
def adaptation_decision(
    adaptation_id: int, payload: AdaptationDecisionInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    proposed_plan = (
        payload.proposed_plan.model_dump(mode="json", exclude_none=True)
        if payload.proposed_plan is not None
        else None
    )
    try:
        item, title = application.decide_adaptation(
            db, adaptation_id, payload.decision, proposed_plan
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return serializers.adaptation(item, title)


@router.get("/climbing/tb2-benchmarks")
def tb2_benchmarks(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    rows = application.list_tb2_benchmarks(db)
    return {"items": [serializers.tb2(item) for item in rows], "total": len(rows)}


@router.post("/climbing/tb2-benchmarks", status_code=status.HTTP_201_CREATED)
def create_tb2_benchmark(
    payload: TB2Input, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    return serializers.tb2(application.create_tb2_benchmark(db, payload.model_dump()))


@router.post("/climbing/gym-sets", status_code=status.HTTP_201_CREATED)
def create_gym_set(payload: GymSetInput, db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    return serializers.gym_set(core.create_gym_set(db, payload.model_dump()))


@router.patch("/climbing/gym-sets/{set_id}/progress")
def patch_gym_progress(
    set_id: int, payload: GymProgressPatch, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        return serializers.gym_set(core.update_gym_progress(db, set_id, payload.model_dump()))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/climbing/route-benchmark")
def save_route_benchmark(
    payload: RouteInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    item = application.create_route_benchmark(db, payload.model_dump())
    return serializers.route_benchmark(item) or {}


@router.get("/training-notes")
def training_notes(
    q: str | None = None,
    category: NoteCategory | None = None,
    tag: str | None = None,
    favorite: bool | None = None,
    db: DatabaseSession = Depends(get_db),
) -> dict[str, Any]:
    items = notes.list_notes(db, query=q, category=category, tag=tag, favorite=favorite)
    return {"items": [notes.note_public(item) for item in items], "total": len(items)}


@router.post("/training-notes", status_code=status.HTTP_201_CREATED)
def create_training_note(
    payload: NoteInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    return notes.note_public(notes.create_note(db, payload.model_dump()))


@router.post("/coaching-principles", status_code=status.HTTP_201_CREATED)
def create_coaching_principle(
    payload: CoachingPrincipleInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    item = application.create_coaching_principle(db, payload.principle, payload.source_note_id)
    return {"id": item.id, "principle": item.principle, "athlete_approved": True}


def _ai_error(exc: AIUnavailableError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _upload_error(exc: uploads.UploadValidationError) -> HTTPException:
    if isinstance(exc, uploads.UploadTooLargeError):
        return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc))
    if isinstance(exc, uploads.UnsupportedUploadTypeError):
        return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/ai/notes/process")
def ai_process_note(payload: NoteProcessInput) -> dict[str, Any]:
    try:
        return process_training_note(payload.raw_input).model_dump(mode="json")
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc


@router.post("/ai/notes/transcribe")
async def ai_transcribe_note(
    audio: UploadFile = File(...),
    retain_raw: bool = Form(False),
    db: DatabaseSession = Depends(get_db),
) -> dict[str, str]:
    try:
        raw = await uploads.read_audio(audio)
    except uploads.UploadValidationError as exc:
        raise _upload_error(exc) from exc
    try:
        transcript = media.transcribe_audio(
            db,
            raw,
            original_filename=audio.filename,
            content_type=audio.content_type,
            retain_raw=retain_raw,
        )
        return {"transcript": transcript}
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc


@router.post("/ai/running-feedback/transcribe")
async def ai_transcribe_running_feedback(
    audio: UploadFile = File(...),
    retain_raw: bool = Form(False),
    db: DatabaseSession = Depends(get_db),
) -> dict[str, str]:
    try:
        raw = await uploads.read_audio(audio)
    except uploads.UploadValidationError as exc:
        raise _upload_error(exc) from exc
    try:
        transcript = media.transcribe_audio(
            db,
            raw,
            original_filename=audio.filename,
            content_type=audio.content_type,
            retain_raw=retain_raw,
            purpose="RUNNING_FEEDBACK",
        )
        return {"transcript": transcript}
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc


@router.post("/ai/workouts/transcribe")
async def ai_transcribe_workout_input(
    audio: UploadFile = File(...),
    db: DatabaseSession = Depends(get_db),
) -> dict[str, str]:
    try:
        raw = await uploads.read_audio(audio)
    except uploads.UploadValidationError as exc:
        raise _upload_error(exc) from exc
    try:
        transcript = media.transcribe_audio(
            db,
            raw,
            original_filename=audio.filename,
            content_type=audio.content_type,
            retain_raw=False,
            purpose="WORKOUT_IMPORT",
        )
        return {"transcript": transcript}
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc


@router.post("/ai/workouts/extract-text")
def ai_extract_text(payload: TextExtractionInput) -> dict[str, Any]:
    try:
        return extract_workout_from_text(payload.text).model_dump(mode="json")
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc


@router.post("/ai/workouts/extract-image")
async def ai_extract_image(
    image: UploadFile = File(...),
    retain_raw: bool = Form(False),
    db: DatabaseSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        raw = await uploads.read_screenshot(image)
    except uploads.UploadValidationError as exc:
        raise _upload_error(exc) from exc
    try:
        return media.extract_image(
            db,
            raw,
            original_filename=image.filename,
            content_type=image.content_type,
            retain_raw=retain_raw,
        )
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc


@router.get("/weekly-reviews")
def weekly_reviews(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    rows = application.list_weekly_reviews(db)
    return {"items": [reporting.weekly_review_public(item) for item in rows], "total": len(rows)}


@router.post("/weekly-reviews/generate")
def generate_weekly_review(
    payload: WeeklyReviewInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    return reporting.weekly_review_public(reporting.generate_weekly_review(db, payload.week_start))


@router.get("/review-plan/proposals")
def review_plan_proposals(
    cadence: Literal["WEEKLY", "MONTHLY"] | None = None,
    db: DatabaseSession = Depends(get_db),
) -> dict[str, Any]:
    rows = planning.list_proposals(db, cadence)
    return {"items": [planning.proposal_public(item) for item in rows], "total": len(rows)}


@router.post("/review-plan/weekly/generate")
def generate_weekly_review_plan(
    payload: WeeklyReviewInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        return planning.proposal_public(planning.review_and_plan_week(db, payload.week_start))
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/review-plan/monthly/generate")
def generate_monthly_review_plan(
    payload: MonthlyReviewPlanInput, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        return planning.proposal_public(planning.review_and_plan_month(db, payload.month_start))
    except AIUnavailableError as exc:
        raise _ai_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/review-plan/proposals/{proposal_id}")
def edit_review_plan_proposal(
    proposal_id: int,
    payload: PlanningProposalEdit,
    db: DatabaseSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return planning.proposal_public(
            planning.edit_proposal(db, proposal_id, payload.proposed_plan)
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/review-plan/proposals/{proposal_id}/approve")
def approve_review_plan_proposal(
    proposal_id: int, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        return planning.proposal_public(planning.approve_proposal(db, proposal_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/review-plan/proposals/{proposal_id}/cancel")
def cancel_review_plan_proposal(
    proposal_id: int, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        return planning.proposal_public(planning.cancel_proposal(db, proposal_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/review-plan/monthly-block/current")
def current_monthly_training_block(
    on: date | None = None, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any] | None:
    return planning.current_monthly_block(db, on or date.today())


@router.get("/data/backup")
def backup(db: DatabaseSession = Depends(get_db)) -> JSONResponse:
    payload = data_portability.create_backup(db)
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": "attachment; filename=adaptive-training-coach-backup.json"},
    )


@router.get("/data/export/{entity}.csv")
def csv_export(entity: str, db: DatabaseSession = Depends(get_db)) -> PlainTextResponse:
    try:
        content = data_portability.export_csv(db, entity)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return PlainTextResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={entity}.csv"},
    )


@router.post("/data/restore")
async def restore(
    backup: UploadFile = File(...), db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    try:
        raw = await uploads.read_restore_json(backup)
    except uploads.UploadValidationError as exc:
        raise _upload_error(exc) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
        restored = data_portability.restore_backup(db, payload)
        return {"restored": True, "records": restored}
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"Invalid backup: {exc}") from exc
    except Exception as exc:
        raise HTTPException(409, f"Restore failed without partial changes: {exc}") from exc


@router.post("/demo/seed")
def seed_demo(db: DatabaseSession = Depends(get_db)) -> dict[str, int]:
    return {"created": demo.seed_demo(db)}


@router.delete("/demo")
def remove_demo(db: DatabaseSession = Depends(get_db)) -> dict[str, int]:
    return {"removed": demo.remove_demo(db)}


@router.get("/settings")
def app_settings(db: DatabaseSession = Depends(get_db)) -> dict[str, Any]:
    return settings_service.get_app_settings(db)


@router.patch("/settings")
def patch_app_settings(
    payload: SettingsPatch, db: DatabaseSession = Depends(get_db)
) -> dict[str, Any]:
    values = payload.model_dump(exclude_none=True)
    if "grade_display" in values and values["grade_display"] not in {"FONT", "V_SCALE", "BOTH"}:
        raise HTTPException(422, "grade_display must be FONT, V_SCALE, or BOTH")
    try:
        return settings_service.update_app_settings(db, values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
