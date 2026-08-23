from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.enums import (
    AdaptationAction,
    AdaptationDecision,
    AdaptationSource,
    ClimbingPhase,
    Confidence,
    FatigueDomain,
    GoalType,
    NoteCategory,
    NoteInputType,
    PlanStatus,
    ReadinessLabel,
    RunningPhase,
    SessionPriority,
    Sport,
)


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(APIModel):
    message: str


class AthleteProfileUpdate(APIModel):
    display_name: str | None = None
    timezone: str | None = None
    running_phase: RunningPhase | None = None
    climbing_phase: ClimbingPhase | None = None
    current_half_marathon_seconds: int | None = Field(None, gt=0)
    baseline_monthly_distance_km: float | None = Field(None, ge=0)
    long_term_monthly_distance_km: float | None = Field(None, ge=0)
    stable_weekly_distance_min_km: float | None = Field(None, ge=0)
    stable_weekly_distance_max_km: float | None = Field(None, ge=0)
    half_marathon_goal_seconds: int | None = Field(None, gt=0)
    half_marathon_stretch_seconds: int | None = Field(None, gt=0)
    marathon_goal_seconds: int | None = Field(None, gt=0)
    tb2_verified_grade: str | None = None
    tb2_estimated_grade: str | None = None
    top_rope_current_grade: str | None = None
    tb2_long_term_goal: str | None = None
    outdoor_boulder_goal: str | None = None
    route_long_term_goal: str | None = None
    home_gym_name: str | None = None


class AthleteProfileOut(AthleteProfileUpdate):
    id: int
    display_name: str
    timezone: str
    running_phase: RunningPhase
    climbing_phase: ClimbingPhase
    current_half_marathon_seconds: int
    baseline_monthly_distance_km: float
    long_term_monthly_distance_km: float
    stable_weekly_distance_min_km: float
    stable_weekly_distance_max_km: float
    half_marathon_goal_seconds: int
    half_marathon_stretch_seconds: int
    marathon_goal_seconds: int
    tb2_verified_grade: str
    tb2_estimated_grade: str
    top_rope_current_grade: str
    tb2_long_term_goal: str
    outdoor_boulder_goal: str
    route_long_term_goal: str
    home_gym_name: str
    created_at: datetime
    updated_at: datetime


class GoalCreate(APIModel):
    goal_type: GoalType
    description: str = ""
    target_value: str | None = None
    target_date: date | None = None
    current_status: str = "ACTIVE"
    notes: str = ""
    is_current: bool = False


class GoalUpdate(APIModel):
    goal_type: GoalType | None = None
    description: str | None = None
    target_value: str | None = None
    target_date: date | None = None
    current_status: str | None = None
    notes: str | None = None
    is_current: bool | None = None


class GoalOut(GoalCreate):
    id: int
    athlete_id: int
    created_at: datetime
    updated_at: datetime


class PlannedSessionCreate(APIModel):
    session_date: date
    start_time: time | None = None
    sport: Sport
    workout_type: str
    title: str
    description: str = ""
    planned_duration_minutes: float | None = Field(None, gt=0)
    planned_distance_km: float | None = Field(None, ge=0)
    target_rpe_min: float | None = Field(None, ge=1, le=10)
    target_rpe_max: float | None = Field(None, ge=1, le=10)
    priority: SessionPriority = SessionPriority.NORMAL
    status: PlanStatus = PlanStatus.PLANNED
    structured_blocks: list[dict[str, Any]] = Field(default_factory=list)
    is_locked: bool = False

    @model_validator(mode="after")
    def validate_rpe_range(self) -> PlannedSessionCreate:
        if (
            self.target_rpe_min is not None
            and self.target_rpe_max is not None
            and self.target_rpe_min > self.target_rpe_max
        ):
            raise ValueError("target_rpe_min cannot exceed target_rpe_max")
        return self


class PlannedSessionUpdate(APIModel):
    session_date: date | None = None
    start_time: time | None = None
    sport: Sport | None = None
    workout_type: str | None = None
    title: str | None = None
    description: str | None = None
    planned_duration_minutes: float | None = Field(None, gt=0)
    planned_distance_km: float | None = Field(None, ge=0)
    target_rpe_min: float | None = Field(None, ge=1, le=10)
    target_rpe_max: float | None = Field(None, ge=1, le=10)
    priority: SessionPriority | None = None
    status: PlanStatus | None = None
    structured_blocks: list[dict[str, Any]] | None = None
    revision_reason: str = "Manual edit"


class PlannedSessionOut(PlannedSessionCreate):
    id: int
    athlete_id: int
    version: int
    moved_from_id: int | None = None
    replaced_session_id: int | None = None
    created_at: datetime
    updated_at: datetime


class RunningDetailIn(APIModel):
    distance_km: float | None = Field(None, gt=0)
    average_pace_seconds_per_km: float | None = Field(None, gt=0)
    average_hr: int | None = Field(None, gt=0)
    maximum_hr: int | None = Field(None, gt=0)
    elevation_m: float | None = None
    cadence: float | None = Field(None, gt=0)
    power_watts: float | None = Field(None, gt=0)
    splits: list[dict[str, Any]] = Field(default_factory=list)
    intervals: list[dict[str, Any]] = Field(default_factory=list)


class ClimbingAttemptIn(APIModel):
    problem: str | None = None
    grade: str | None = None
    attempts: int = Field(1, ge=1)
    sent: bool = False
    flash: bool = False
    repeat: bool = False
    project: bool = False
    style_tags: list[str] = Field(default_factory=list)


class ClimbingDetailIn(APIModel):
    gym_or_crag: str | None = None
    hard_attempts: int | None = Field(None, ge=0)
    maximum_attempted: str | None = None
    maximum_sent: str | None = None
    grade_scale: str | None = None
    attempts: list[ClimbingAttemptIn] = Field(default_factory=list)


class StrengthSetIn(APIModel):
    exercise: str
    set_count: int | None = Field(None, ge=1)
    reps: float | None = Field(None, ge=0)
    load_kg: float | None = Field(None, ge=0)
    rpe: float | None = Field(None, ge=1, le=10)
    rir: float | None = Field(None, ge=0)
    tags: list[str] = Field(default_factory=list)


class StrengthDetailIn(APIModel):
    workout_name: str | None = None
    rounds: float | None = Field(None, ge=0)
    result_time_seconds: float | None = Field(None, ge=0)
    sets: list[StrengthSetIn] = Field(default_factory=list)


class CompletedSessionCreate(APIModel):
    planned_session_id: int | None = None
    session_date: date
    start_time: time | None = None
    duration_minutes: float = Field(gt=0)
    sport: Sport
    workout_type: str
    rpe: float | None = Field(None, ge=1, le=10)
    notes: str = ""
    running: RunningDetailIn | None = None
    climbing: ClimbingDetailIn | None = None
    strength: StrengthDetailIn | None = None
    subjective_feedback_text: str | None = Field(None, max_length=5000)
    subjective_feedback_source: Literal["VOICE", "TEXT", "NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_sport_detail(self) -> CompletedSessionCreate:
        if self.sport == Sport.RUNNING and self.running is None:
            raise ValueError("running detail is required for a RUNNING session")
        if self.sport == Sport.CLIMBING and self.climbing is None:
            raise ValueError("climbing detail is required for a CLIMBING session")
        return self


class SessionDomainStressOut(APIModel):
    domain: FatigueDomain
    coefficient: float
    multiplier: float
    stress: float
    algorithm_version: str


class RunningDetailOut(RunningDetailIn):
    session_id: int


class ClimbingAttemptOut(ClimbingAttemptIn):
    id: int


class ClimbingDetailOut(ClimbingDetailIn):
    session_id: int
    attempts: list[ClimbingAttemptOut] = Field(default_factory=list)


class StrengthSetOut(StrengthSetIn):
    id: int


class StrengthDetailOut(StrengthDetailIn):
    session_id: int
    sets: list[StrengthSetOut] = Field(default_factory=list)


class CompletedSessionOut(APIModel):
    id: int
    athlete_id: int
    planned_session_id: int | None
    session_date: date
    start_time: time | None
    duration_minutes: float
    sport: Sport
    workout_type: str
    rpe: float | None
    notes: str
    srpe_load: float | None
    base_stress: float | None
    subjective_feedback_text: str | None
    subjective_feedback_source: Literal["VOICE", "TEXT", "NONE"]
    subjective_feedback_created_at: datetime | None
    is_demo: bool
    running: RunningDetailOut | None = None
    climbing: ClimbingDetailOut | None = None
    strength: StrengthDetailOut | None = None
    domain_stresses: list[SessionDomainStressOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RecoveryCheckinCreate(APIModel):
    recorded_at: datetime | None = None
    sleep_duration_hours: float | None = Field(None, ge=0, le=24)
    sleep_quality: int | None = Field(None, ge=1, le=5)
    energy: int | None = Field(None, ge=1, le=5)
    motivation: int | None = Field(None, ge=1, le=5)
    stress: int | None = Field(None, ge=1, le=5)
    general_soreness: float | None = Field(None, ge=0, le=10)
    area_soreness: dict[str, float] = Field(default_factory=dict)
    resting_hr: int | None = Field(None, gt=0)
    hrv: float | None = Field(None, ge=0)
    notes: str = ""


class RecoveryCheckinOut(RecoveryCheckinCreate):
    id: int
    athlete_id: int
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime


class FatigueReadinessOut(APIModel):
    calculated_at: datetime
    latent_fatigue: dict[FatigueDomain, float]
    display_fatigue: dict[FatigueDomain, float]
    running_score: float
    running_label: ReadinessLabel
    climbing_score: float
    climbing_label: ReadinessLabel
    running_components: dict[str, float]
    climbing_components: dict[str, float]
    subjective_delta: float
    local_soreness_penalty: float
    warnings: list[str] = Field(default_factory=list)


class RunningVolumeOut(APIModel):
    current_calendar_month_km: float
    previous_calendar_month_km: float
    rolling_7d_km: float
    rolling_28d_km: float
    rolling_28d_weekly_average_km: float


class RunningEstimateCreate(APIModel):
    estimated_10k_seconds: float | None = Field(None, gt=0)
    confidence: Confidence
    source_event: str | None = None
    source_date: date | None = None
    formula: str | None = None
    evidence: str = ""


class RunningEstimateOut(RunningEstimateCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class ThresholdEstimateCreate(APIModel):
    estimate_type: str
    pace_low_seconds_per_km: float | None = Field(None, gt=0)
    pace_high_seconds_per_km: float | None = Field(None, gt=0)
    hr_low: int | None = Field(None, gt=0)
    hr_high: int | None = Field(None, gt=0)
    confidence: Confidence
    source: str
    measured_at: date


class ThresholdEstimateOut(ThresholdEstimateCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class RunningStateOut(APIModel):
    phase: RunningPhase
    volume: RunningVolumeOut
    estimated_10k: RunningEstimateOut | None
    lt1: ThresholdEstimateOut | None
    lt2: ThresholdEstimateOut | None


class TB2BenchmarkCreate(APIModel):
    benchmark_date: date
    board: str = "TB2"
    angle_degrees: int = Field(ge=0, le=90)
    verified_grade: str
    estimated_grade: str | None = None
    grade_scale: str = "Fontainebleau"
    notes: str = ""


class TB2BenchmarkOut(TB2BenchmarkCreate):
    id: int
    athlete_id: int
    created_at: datetime
    updated_at: datetime


class GymColourUpdate(APIModel):
    sent_count: int = Field(ge=0)
    available_problem_count: int | None = Field(None, ge=0)


class GymColourOut(GymColourUpdate):
    id: int
    colour: str
    ordinal: int
    completion_rate: float | None = None


class GymSetCreate(APIModel):
    gym: str
    start_date: date
    notes: str = ""
    available_counts: dict[str, int] = Field(default_factory=dict)


class GymSetOut(APIModel):
    id: int
    athlete_id: int
    gym: str
    start_date: date
    end_date: date | None
    notes: str
    is_active: bool
    is_demo: bool
    colours: list[GymColourOut]
    created_at: datetime
    updated_at: datetime


class RouteBenchmarkCreate(APIModel):
    benchmark_date: date
    top_rope_verified_grade: str | None = None
    lead_verified_grade: str | None = None
    target_grade: str | None = None
    notes: str = ""


class RouteBenchmarkOut(RouteBenchmarkCreate):
    id: int
    athlete_id: int
    created_at: datetime
    updated_at: datetime


class ClimbingStateOut(APIModel):
    phase: ClimbingPhase
    latest_tb2: TB2BenchmarkOut | None
    active_gym_set: GymSetOut | None
    latest_route: RouteBenchmarkOut | None


class AdaptationProposalOut(APIModel):
    id: int
    affected_session_id: int | None
    trigger_session_id: int | None
    original_plan: dict[str, Any]
    proposed_plan: dict[str, Any]
    action: AdaptationAction
    reason: str
    evidence: list[str]
    confidence: Confidence
    source: AdaptationSource
    decision: AdaptationDecision
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdaptationEdit(APIModel):
    proposed_plan: dict[str, Any] | None = None


class CalendarDayOut(APIModel):
    date: date
    planned: list[PlannedSessionOut]
    completed: list[CompletedSessionOut]


class TodayOut(APIModel):
    date: date
    readiness: FatigueReadinessOut
    planned_sessions: list[PlannedSessionOut]
    recent_fatigue_warnings: list[str]
    primary_goal: GoalOut | None
    running_phase: RunningPhase
    climbing_phase: ClimbingPhase
    pending_adaptations: list[AdaptationProposalOut]


class ProgressOut(APIModel):
    from_date: date
    to_date: date
    monthly_mileage: list[dict[str, Any]]
    rolling_volume: list[dict[str, Any]]
    estimated_10k: list[RunningEstimateOut]
    lt2: list[ThresholdEstimateOut]
    tb2_benchmarks: list[TB2BenchmarkOut]
    gym_sets: list[GymSetOut]


class WeeklyReviewOut(APIModel):
    id: int
    week_start: date
    week_end: date
    summary: dict[str, Any]
    compliance: dict[str, int]
    running: dict[str, Any]
    climbing: dict[str, Any]
    recovery: dict[str, Any]
    key_findings: list[str]
    next_week: list[str]
    narrative: str
    source: str
    created_at: datetime
    updated_at: datetime


class TrainingNoteCreate(APIModel):
    primary_category: NoteCategory
    title: str
    raw_input: str
    cleaned_note: str | None = None
    summary: str = ""
    key_takeaways: list[str] = Field(default_factory=list)
    actionable_ideas: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_title: str | None = None
    source_creator: str | None = None
    source_url: HttpUrl | None = None
    input_type: NoteInputType = NoteInputType.TEXT
    classification_confidence: Confidence = Confidence.HIGH
    use_for_coaching: bool = False
    favorite: bool = False


class TrainingNoteUpdate(APIModel):
    primary_category: NoteCategory | None = None
    title: str | None = None
    cleaned_note: str | None = None
    summary: str | None = None
    key_takeaways: list[str] | None = None
    actionable_ideas: list[str] | None = None
    tags: list[str] | None = None
    use_for_coaching: bool | None = None
    favorite: bool | None = None


class TrainingNoteOut(APIModel):
    id: int
    primary_category: NoteCategory
    title: str
    raw_input: str
    cleaned_note: str
    summary: str
    key_takeaways: list[str]
    actionable_ideas: list[str]
    tags: list[str]
    source_title: str | None
    source_creator: str | None
    source_url: str | None
    input_type: NoteInputType
    classification_confidence: Confidence
    use_for_coaching: bool
    favorite: bool
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class NoteProcessingRequest(APIModel):
    text: str = Field(min_length=1)


class NoteProcessingPreview(APIModel):
    primary_category: NoteCategory
    suggested_title: str
    cleaned_note: str
    short_summary: str
    key_takeaways: list[str]
    actionable_ideas: list[str]
    tags: list[str]
    classification_confidence: Confidence
    source: str


class ExtractedField(APIModel):
    value: Any | None
    confidence: Confidence
    source: str


class WorkoutExtractionPreview(APIModel):
    fields: dict[str, ExtractedField]
    warnings: list[str] = Field(default_factory=list)
    source: str
    media_import_id: int | None = None


class WorkoutTextExtractionRequest(APIModel):
    text: str = Field(min_length=1)


class BackupOut(APIModel):
    schema_version: str
    exported_at: datetime
    data: dict[str, list[dict[str, Any]]]


class RestoreRequest(APIModel):
    schema_version: str
    data: dict[str, list[dict[str, Any]]]
    replace_existing: bool = False


class DemoStatusOut(APIModel):
    installed: bool
    completed_sessions: int
    notes: int
    gym_sets: int


class SettingsOut(APIModel):
    ai_available: bool
    openai_model: str
    openai_vision_model: str
    openai_transcribe_model: str
    database_path: str
    retain_raw_screenshots: bool
    retain_raw_audio: bool
