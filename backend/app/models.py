from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import (
    AdaptationAction,
    AdaptationDecision,
    AdaptationSource,
    ClimbingPhase,
    Confidence,
    EstimateType,
    FatigueDomain,
    GoalType,
    MediaKind,
    MediaStatus,
    NoteCategory,
    NoteInputType,
    PlanStatus,
    ReadinessLabel,
    RunningPhase,
    SessionPriority,
    Sport,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def enum_column(enum_cls: type, **kwargs: Any) -> SAEnum:
    return SAEnum(
        enum_cls,
        values_callable=lambda values: [item.value for item in values],
        native_enum=False,
        validate_strings=True,
        name=enum_cls.__name__.lower(),
        **kwargs,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AthleteProfile(TimestampMixin, Base):
    __tablename__ = "athlete_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    display_name: Mapped[str] = mapped_column(String(120), default="Alex")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/London")
    running_phase: Mapped[RunningPhase] = mapped_column(
        enum_column(RunningPhase), default=RunningPhase.AEROBIC_BASE
    )
    climbing_phase: Mapped[ClimbingPhase] = mapped_column(
        enum_column(ClimbingPhase), default=ClimbingPhase.TECHNIQUE_VOLUME
    )
    current_half_marathon_seconds: Mapped[int] = mapped_column(Integer, default=6300)
    baseline_monthly_distance_km: Mapped[float] = mapped_column(Float, default=100.0)
    long_term_monthly_distance_km: Mapped[float] = mapped_column(Float, default=400.0)
    stable_weekly_distance_min_km: Mapped[float] = mapped_column(Float, default=80.0)
    stable_weekly_distance_max_km: Mapped[float] = mapped_column(Float, default=100.0)
    half_marathon_goal_seconds: Mapped[int] = mapped_column(Integer, default=5400)
    half_marathon_stretch_seconds: Mapped[int] = mapped_column(Integer, default=4800)
    marathon_goal_seconds: Mapped[int] = mapped_column(Integer, default=12600)
    tb2_verified_grade: Mapped[str] = mapped_column(String(16), default="6C")
    tb2_estimated_grade: Mapped[str] = mapped_column(String(16), default="6C+")
    top_rope_current_grade: Mapped[str] = mapped_column(String(16), default="6C–6C+")
    tb2_long_term_goal: Mapped[str] = mapped_column(String(32), default="V9–V10")
    outdoor_boulder_goal: Mapped[str] = mapped_column(String(32), default="V10")
    route_long_term_goal: Mapped[str] = mapped_column(String(32), default="7B+–7C")
    home_gym_name: Mapped[str] = mapped_column(String(160), default="Home Gym")


class AthleteStateHistory(Base):
    """Append-only audit trail for phase changes used by the adaptation engine."""

    __tablename__ = "athlete_state_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    state_type: Mapped[str] = mapped_column(String(32))
    old_value: Mapped[str] = mapped_column(String(80))
    new_value: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(32), default="MANUAL")


class Goal(TimestampMixin, Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    goal_type: Mapped[GoalType] = mapped_column(enum_column(GoalType))
    description: Mapped[str] = mapped_column(Text, default="")
    target_value: Mapped[str | None] = mapped_column(String(160))
    target_date: Mapped[date | None] = mapped_column(Date)
    current_status: Mapped[str] = mapped_column(String(120), default="ACTIVE")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


Index(
    "uq_goals_one_current",
    Goal.athlete_id,
    unique=True,
    sqlite_where=Goal.is_current.is_(True),
)


class PlannedSession(TimestampMixin, Base):
    __tablename__ = "planned_sessions"
    __table_args__ = (
        CheckConstraint(
            "target_rpe_min IS NULL OR (target_rpe_min >= 1 AND target_rpe_min <= 10)",
            name="ck_plan_target_rpe_min",
        ),
        CheckConstraint(
            "target_rpe_max IS NULL OR (target_rpe_max >= 1 AND target_rpe_max <= 10)",
            name="ck_plan_target_rpe_max",
        ),
        CheckConstraint(
            "target_rpe_min IS NULL OR target_rpe_max IS NULL OR target_rpe_min <= target_rpe_max",
            name="ck_plan_target_rpe_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    sport: Mapped[Sport] = mapped_column(enum_column(Sport), index=True)
    workout_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    planned_duration_minutes: Mapped[float | None] = mapped_column(Float)
    planned_distance_km: Mapped[float | None] = mapped_column(Float)
    target_rpe_min: Mapped[float | None] = mapped_column(Float)
    target_rpe_max: Mapped[float | None] = mapped_column(Float)
    priority: Mapped[SessionPriority] = mapped_column(
        enum_column(SessionPriority), default=SessionPriority.NORMAL
    )
    status: Mapped[PlanStatus] = mapped_column(enum_column(PlanStatus), default=PlanStatus.PLANNED)
    structured_blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    moved_from_id: Mapped[int | None] = mapped_column(ForeignKey("planned_sessions.id"))
    replaced_session_id: Mapped[int | None] = mapped_column(ForeignKey("planned_sessions.id"))

    revisions: Mapped[list[PlannedSessionRevision]] = relationship(
        back_populates="planned_session", cascade="all, delete-orphan"
    )


class PlannedSessionRevision(Base):
    __tablename__ = "planned_session_revisions"
    __table_args__ = (UniqueConstraint("planned_session_id", "version", name="uq_plan_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    planned_session_id: Mapped[int] = mapped_column(
        ForeignKey("planned_sessions.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    planned_session: Mapped[PlannedSession] = relationship(back_populates="revisions")


class CompletedSession(TimestampMixin, Base):
    __tablename__ = "completed_sessions"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_session_duration_positive"),
        CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="ck_session_rpe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    planned_session_id: Mapped[int | None] = mapped_column(ForeignKey("planned_sessions.id"))
    session_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    duration_minutes: Mapped[float] = mapped_column(Float)
    sport: Mapped[Sport] = mapped_column(enum_column(Sport), index=True)
    workout_type: Mapped[str] = mapped_column(String(80))
    rpe: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")
    srpe_load: Mapped[float | None] = mapped_column(Float)
    base_stress: Mapped[float | None] = mapped_column(Float)
    ai_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    subjective_feedback_text: Mapped[str | None] = mapped_column(Text)
    subjective_feedback_source: Mapped[str] = mapped_column(
        String(16), default="NONE", nullable=False
    )
    subjective_feedback_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    running: Mapped[RunningSessionDetail | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    climbing: Mapped[ClimbingSessionDetail | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    strength: Mapped[StrengthSessionDetail | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    domain_stresses: Mapped[list[SessionDomainStress]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class RunningSessionDetail(Base):
    __tablename__ = "running_session_details"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("completed_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    distance_km: Mapped[float | None] = mapped_column(Float)
    average_pace_seconds_per_km: Mapped[float | None] = mapped_column(Float)
    average_hr: Mapped[int | None] = mapped_column(Integer)
    maximum_hr: Mapped[int | None] = mapped_column(Integer)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    cadence: Mapped[float | None] = mapped_column(Float)
    power_watts: Mapped[float | None] = mapped_column(Float)
    splits: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    intervals: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    session: Mapped[CompletedSession] = relationship(back_populates="running")


class ClimbingSessionDetail(Base):
    __tablename__ = "climbing_session_details"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("completed_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    gym_or_crag: Mapped[str | None] = mapped_column(String(200))
    hard_attempts: Mapped[int | None] = mapped_column(Integer)
    maximum_attempted: Mapped[str | None] = mapped_column(String(32))
    maximum_sent: Mapped[str | None] = mapped_column(String(32))
    grade_scale: Mapped[str | None] = mapped_column(String(32))
    session: Mapped[CompletedSession] = relationship(back_populates="climbing")
    attempts: Mapped[list[ClimbingAttempt]] = relationship(
        back_populates="climbing_session", cascade="all, delete-orphan"
    )


class ClimbingAttempt(Base):
    __tablename__ = "climbing_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    climbing_session_id: Mapped[int] = mapped_column(
        ForeignKey("climbing_session_details.session_id", ondelete="CASCADE")
    )
    problem: Mapped[str | None] = mapped_column(String(160))
    grade: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    flash: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat: Mapped[bool] = mapped_column(Boolean, default=False)
    project: Mapped[bool] = mapped_column(Boolean, default=False)
    style_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    climbing_session: Mapped[ClimbingSessionDetail] = relationship(back_populates="attempts")


class StrengthSessionDetail(Base):
    __tablename__ = "strength_session_details"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("completed_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    workout_name: Mapped[str | None] = mapped_column(String(200))
    rounds: Mapped[float | None] = mapped_column(Float)
    result_time_seconds: Mapped[float | None] = mapped_column(Float)
    session: Mapped[CompletedSession] = relationship(back_populates="strength")
    sets: Mapped[list[StrengthSet]] = relationship(
        back_populates="strength_session", cascade="all, delete-orphan"
    )


class StrengthSet(Base):
    __tablename__ = "strength_sets"
    __table_args__ = (
        CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="ck_strength_set_rpe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strength_session_id: Mapped[int] = mapped_column(
        ForeignKey("strength_session_details.session_id", ondelete="CASCADE")
    )
    exercise: Mapped[str] = mapped_column(String(160))
    set_count: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[float | None] = mapped_column(Float)
    load_kg: Mapped[float | None] = mapped_column(Float)
    rpe: Mapped[float | None] = mapped_column(Float)
    rir: Mapped[float | None] = mapped_column(Float)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    strength_session: Mapped[StrengthSessionDetail] = relationship(back_populates="sets")


class SessionDomainStress(Base):
    __tablename__ = "session_domain_stresses"
    __table_args__ = (UniqueConstraint("session_id", "domain", name="uq_session_domain_stress"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("completed_sessions.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[FatigueDomain] = mapped_column(enum_column(FatigueDomain), index=True)
    coefficient: Mapped[float] = mapped_column(Float)
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    stress: Mapped[float] = mapped_column(Float)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="v1")
    session: Mapped[CompletedSession] = relationship(back_populates="domain_stresses")


class RecoveryCheckin(TimestampMixin, Base):
    __tablename__ = "recovery_checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    sleep_duration_hours: Mapped[float | None] = mapped_column(Float)
    sleep_quality: Mapped[int | None] = mapped_column(Integer)
    energy: Mapped[int | None] = mapped_column(Integer)
    motivation: Mapped[int | None] = mapped_column(Integer)
    stress: Mapped[int | None] = mapped_column(Integer)
    general_soreness: Mapped[float | None] = mapped_column(Float)
    area_soreness: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    resting_hr: Mapped[int | None] = mapped_column(Integer)
    hrv: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class FatigueSnapshot(Base):
    __tablename__ = "fatigue_snapshots"
    __table_args__ = (
        UniqueConstraint("athlete_id", "source_key", name="uq_fatigue_snapshot_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    source_key: Mapped[str | None] = mapped_column(String(120))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    latent_by_domain: Mapped[dict[str, float]] = mapped_column(JSON)
    display_by_domain: Mapped[dict[str, float]] = mapped_column(JSON)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="v1")


class ReadinessSnapshot(Base):
    __tablename__ = "readiness_snapshots"
    __table_args__ = (
        UniqueConstraint("athlete_id", "source_key", name="uq_readiness_snapshot_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    source_key: Mapped[str | None] = mapped_column(String(120))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    running_score: Mapped[float] = mapped_column(Float)
    running_label: Mapped[ReadinessLabel] = mapped_column(enum_column(ReadinessLabel))
    climbing_score: Mapped[float] = mapped_column(Float)
    climbing_label: Mapped[ReadinessLabel] = mapped_column(enum_column(ReadinessLabel))
    components: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    subjective_delta: Mapped[float] = mapped_column(Float, default=0.0)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="v1")


class RunningFitnessEstimate(TimestampMixin, Base):
    __tablename__ = "running_fitness_estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    estimated_10k_seconds: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[Confidence] = mapped_column(enum_column(Confidence))
    source_event: Mapped[str | None] = mapped_column(String(160))
    source_date: Mapped[date | None] = mapped_column(Date)
    formula: Mapped[str | None] = mapped_column(String(200))
    evidence: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class ThresholdEstimate(TimestampMixin, Base):
    __tablename__ = "threshold_estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    estimate_type: Mapped[EstimateType] = mapped_column(enum_column(EstimateType))
    pace_low_seconds_per_km: Mapped[float | None] = mapped_column(Float)
    pace_high_seconds_per_km: Mapped[float | None] = mapped_column(Float)
    hr_low: Mapped[int | None] = mapped_column(Integer)
    hr_high: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[Confidence] = mapped_column(enum_column(Confidence))
    source: Mapped[str] = mapped_column(String(200))
    measured_at: Mapped[date] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class TB2Benchmark(TimestampMixin, Base):
    __tablename__ = "tb2_benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    benchmark_date: Mapped[date] = mapped_column(Date, index=True)
    board: Mapped[str] = mapped_column(String(64), default="TB2")
    angle_degrees: Mapped[int] = mapped_column(Integer)
    verified_grade: Mapped[str] = mapped_column(String(16))
    estimated_grade: Mapped[str | None] = mapped_column(String(16))
    grade_scale: Mapped[str] = mapped_column(String(32), default="Fontainebleau")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class GymSet(TimestampMixin, Base):
    __tablename__ = "gym_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    gym: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    colours: Mapped[list[GymSetColourProgress]] = relationship(
        back_populates="gym_set", cascade="all, delete-orphan"
    )


Index(
    "uq_gym_sets_one_active_per_gym",
    GymSet.athlete_id,
    GymSet.gym,
    unique=True,
    sqlite_where=GymSet.is_active.is_(True),
)


class GymSetColourProgress(TimestampMixin, Base):
    __tablename__ = "gym_set_colour_progress"
    __table_args__ = (UniqueConstraint("gym_set_id", "colour", name="uq_gym_set_colour"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    gym_set_id: Mapped[int] = mapped_column(
        ForeignKey("gym_sets.id", ondelete="CASCADE"), index=True
    )
    colour: Mapped[str] = mapped_column(String(32))
    ordinal: Mapped[int] = mapped_column(Integer)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    available_problem_count: Mapped[int | None] = mapped_column(Integer)
    gym_set: Mapped[GymSet] = relationship(back_populates="colours")

    @property
    def completion_rate(self) -> float | None:
        if not self.available_problem_count:
            return None
        return self.sent_count / self.available_problem_count


class RouteBenchmark(TimestampMixin, Base):
    __tablename__ = "route_benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athlete_profiles.id"), default=1)
    benchmark_date: Mapped[date] = mapped_column(Date, index=True)
    top_rope_verified_grade: Mapped[str | None] = mapped_column(String(16))
    lead_verified_grade: Mapped[str | None] = mapped_column(String(16))
    target_grade: Mapped[str | None] = mapped_column(String(16))
    notes: Mapped[str] = mapped_column(Text, default="")


class AdaptationEvent(TimestampMixin, Base):
    __tablename__ = "adaptation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    affected_session_id: Mapped[int | None] = mapped_column(ForeignKey("planned_sessions.id"))
    trigger_session_id: Mapped[int | None] = mapped_column(ForeignKey("completed_sessions.id"))
    original_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    proposed_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action: Mapped[AdaptationAction] = mapped_column(enum_column(AdaptationAction))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[Confidence] = mapped_column(enum_column(Confidence))
    source: Mapped[AdaptationSource] = mapped_column(enum_column(AdaptationSource))
    decision: Mapped[AdaptationDecision] = mapped_column(
        enum_column(AdaptationDecision), default=AdaptationDecision.PENDING
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WeeklyReview(TimestampMixin, Base):
    __tablename__ = "weekly_reviews"
    __table_args__ = (UniqueConstraint("week_start", name="uq_weekly_review_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compliance: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    running: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    climbing: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recovery: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    key_findings: Mapped[list[str]] = mapped_column(JSON, default=list)
    next_week: Mapped[list[str]] = mapped_column(JSON, default=list)
    narrative: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="RULE_ENGINE")


class PlanningMemory(TimestampMixin, Base):
    """Compact persisted summaries used by planning calls, never raw media."""

    __tablename__ = "planning_memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    memory_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    level: Mapped[str] = mapped_column(String(24), index=True)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(32), default="RULE_ENGINE")


class PlanningProposal(TimestampMixin, Base):
    """Append-only AI preview. Approval is the only path that applies its plan."""

    __tablename__ = "planning_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    cadence: Mapped[str] = mapped_column(String(16), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    target_start: Mapped[date] = mapped_column(Date)
    target_end: Mapped[date] = mapped_column(Date)
    deterministic_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    proposed_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="PREVIEW", index=True)
    source: Mapped[str] = mapped_column(String(32), default="AI")
    model_name: Mapped[str | None] = mapped_column(String(120))
    approval_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonthlyTrainingBlock(TimestampMixin, Base):
    __tablename__ = "monthly_training_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_start: Mapped[date] = mapped_column(Date, index=True)
    month_end: Mapped[date] = mapped_column(Date)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_proposal_id: Mapped[int] = mapped_column(ForeignKey("planning_proposals.id"))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)


class TrainingNote(TimestampMixin, Base):
    __tablename__ = "training_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    primary_category: Mapped[NoteCategory] = mapped_column(enum_column(NoteCategory), index=True)
    title: Mapped[str] = mapped_column(String(240))
    raw_input: Mapped[str] = mapped_column(Text)
    cleaned_note: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    key_takeaways: Mapped[list[str]] = mapped_column(JSON, default=list)
    actionable_ideas: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_title: Mapped[str | None] = mapped_column(String(240))
    source_creator: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    input_type: Mapped[NoteInputType] = mapped_column(enum_column(NoteInputType))
    classification_confidence: Mapped[Confidence] = mapped_column(enum_column(Confidence))
    use_for_coaching: Mapped[bool] = mapped_column(Boolean, default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class CoachingPrinciple(TimestampMixin, Base):
    __tablename__ = "coaching_principles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_note_id: Mapped[int | None] = mapped_column(ForeignKey("training_notes.id"))
    category: Mapped[NoteCategory] = mapped_column(enum_column(NoteCategory))
    principle: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    athlete_approved: Mapped[bool] = mapped_column(Boolean, default=True)


class MediaImport(TimestampMixin, Base):
    __tablename__ = "media_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[MediaKind] = mapped_column(enum_column(MediaKind))
    status: Mapped[MediaStatus] = mapped_column(enum_column(MediaStatus))
    original_filename: Mapped[str | None] = mapped_column(String(300))
    local_path: Mapped[str | None] = mapped_column(String(1000))
    retain_raw: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    confirmed_session_id: Mapped[int | None] = mapped_column(ForeignKey("completed_sessions.id"))


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
