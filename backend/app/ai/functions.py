from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings
from app.enums import AdaptationAction, Confidence, NoteCategory, SessionPriority, Sport
from app.session_types import normalise_session_type


class AIUnavailableError(RuntimeError):
    pass


_AUDIO_FILE_TYPES: dict[str, tuple[str, set[str]]] = {
    "audio/webm": (".webm", {".webm"}),
    "audio/mp4": (".m4a", {".m4a", ".mp4"}),
    "audio/m4a": (".m4a", {".m4a", ".mp4"}),
    "audio/x-m4a": (".m4a", {".m4a", ".mp4"}),
    "audio/mpeg": (".mp3", {".mp3", ".mpeg", ".mpga"}),
    "audio/mp3": (".mp3", {".mp3"}),
    "audio/ogg": (".ogg", {".ogg", ".opus"}),
    "audio/wav": (".wav", {".wav"}),
    "audio/x-wav": (".wav", {".wav"}),
    "audio/wave": (".wav", {".wav"}),
    "audio/flac": (".flac", {".flac"}),
    "audio/x-flac": (".flac", {".flac"}),
}


def _normalise_audio_upload(filename: str, media_type: str) -> tuple[str, str]:
    """Give OpenAI consistent filename and MIME metadata across browser recorders."""

    clean_media_type = media_type.split(";", 1)[0].strip().lower()
    preferred_suffix, accepted_suffixes = _AUDIO_FILE_TYPES.get(
        clean_media_type, (".webm", {".webm"})
    )
    clean_name = Path(filename).name or f"recording{preferred_suffix}"
    if Path(clean_name).suffix.lower() not in accepted_suffixes:
        clean_name = f"{Path(clean_name).stem or 'recording'}{preferred_suffix}"
    return clean_name, clean_media_type


def _transcription_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
    return f"OpenAI returned HTTP {response.status_code}"


def _transcribe_audio(audio: bytes, filename: str, media_type: str, prompt: str) -> str:
    settings = get_settings()
    key = _require_key(settings)
    upload_name, upload_media_type = _normalise_audio_upload(filename, media_type)
    try:
        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            data={"model": settings.openai_transcribe_model, "prompt": prompt},
            files={"file": (upload_name, audio, upload_media_type)},
            timeout=90,
        )
        response.raise_for_status()
        transcript = response.json().get("text")
    except httpx.HTTPStatusError as exc:
        raise AIUnavailableError(
            f"Transcription failed: {_transcription_error(exc.response)}"
        ) from exc
    except (httpx.HTTPError, AttributeError, ValueError) as exc:
        raise AIUnavailableError(
            "Transcription failed because OpenAI could not be reached."
        ) from exc
    if not transcript:
        raise AIUnavailableError("Transcription returned no text.")
    return str(transcript)


class StrictAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedValue(BaseModel):
    value: Any | None = None
    confidence: Confidence = Confidence.LOW
    source: str


class WorkoutExtraction(BaseModel):
    workout_kind: ExtractedValue
    session_type: ExtractedValue
    title: ExtractedValue
    activity_type: ExtractedValue
    date: ExtractedValue
    distance_km: ExtractedValue
    duration_minutes: ExtractedValue
    average_pace: ExtractedValue
    average_hr: ExtractedValue
    max_hr: ExtractedValue
    elevation_m: ExtractedValue
    cadence: ExtractedValue
    power_w: ExtractedValue
    board_name: ExtractedValue
    angle: ExtractedValue
    rpe: ExtractedValue
    splits: ExtractedValue
    intervals: ExtractedValue
    notes: ExtractedValue


def _mark_invalid(field: ExtractedValue, label: str) -> None:
    field.value = None
    field.confidence = Confidence.LOW
    field.source = f"{field.source}; {label} could not be normalised"


def _normalise_extracted_date(field: ExtractedValue, reference_date: date) -> None:
    if field.value is None:
        return
    raw = str(field.value).strip()
    lowered = raw.casefold()
    relative_days = {
        "today": 0,
        "今天": 0,
        "今日": 0,
        "yesterday": -1,
        "昨天": -1,
        "昨日": -1,
    }
    parsed: date | None = None
    if lowered in relative_days:
        parsed = reference_date + timedelta(days=relative_days[lowered])
    else:
        full = re.fullmatch(r"(\d{4})[年/.-](\d{1,2})[月/.-](\d{1,2})日?", raw)
        month_day = re.fullmatch(r"(\d{1,2})月(\d{1,2})日?", raw)
        try:
            if full:
                parsed = date(int(full.group(1)), int(full.group(2)), int(full.group(3)))
            elif month_day:
                parsed = date(reference_date.year, int(month_day.group(1)), int(month_day.group(2)))
            else:
                parsed = date.fromisoformat(raw)
        except ValueError:
            parsed = None
    if parsed is None:
        _mark_invalid(field, "date")
        return
    field.value = parsed.isoformat()


def _normalise_extracted_pace(field: ExtractedValue) -> None:
    if field.value is None:
        return
    raw = str(field.value).strip()
    match = re.search(
        r"(?P<minutes>\d{1,2})\s*(?:[:：分'′])\s*(?P<seconds>\d{1,2}(?:\.\d+)?)",
        raw,
    )
    if match:
        seconds = round(float(match.group("seconds")))
        minutes = int(match.group("minutes")) + seconds // 60
        field.value = f"{minutes}:{seconds % 60:02d}"
        return
    try:
        seconds_per_km = float(raw.replace("/km", "").strip())
    except ValueError:
        _mark_invalid(field, "pace")
        return
    if seconds_per_km <= 0:
        _mark_invalid(field, "pace")
        return
    field.value = str(round(seconds_per_km, 1)).removesuffix(".0")


def normalise_workout_extraction(
    extraction: WorkoutExtraction, *, reference_date: date
) -> WorkoutExtraction:
    """Convert AI preview values into the API's stable athlete-facing formats."""

    _normalise_extracted_date(extraction.date, reference_date)
    _normalise_extracted_pace(extraction.average_pace)
    for name in ("distance_km", "duration_minutes", "cadence", "power_w"):
        field = getattr(extraction, name)
        if field.value is not None and float(field.value) <= 0:
            _mark_invalid(field, name)
    if extraction.rpe.value is not None and not 1 <= float(extraction.rpe.value) <= 10:
        _mark_invalid(extraction.rpe, "RPE")
    for name in ("average_hr", "max_hr"):
        field = getattr(extraction, name)
        if field.value is not None:
            if float(field.value) <= 0:
                _mark_invalid(field, name)
            else:
                field.value = round(float(field.value))
    if extraction.workout_kind.value in {Sport.RUNNING.value, Sport.CLIMBING.value}:
        normalised = normalise_session_type(
            Sport(extraction.workout_kind.value), extraction.session_type.value
        )
        if normalised is None:
            _mark_invalid(extraction.session_type, "session type")
        else:
            extraction.session_type.value = normalised
    return extraction


class ProcessedNote(StrictAIOutput):
    primary_category: NoteCategory
    title: str
    cleaned_note: str
    summary: str
    key_takeaways: list[str]
    actionable_ideas: list[str]
    tags: list[str]
    classification_confidence: Confidence


class SessionAnalysisInput(BaseModel):
    primary_goal: str
    running_phase: str
    climbing_phase: str
    planned_workout: dict[str, Any]
    completed_workout: dict[str, Any]
    fatigue: dict[str, float]
    readiness: dict[str, Any]


class SessionAnalysisOutput(StrictAIOutput):
    summary: str = Field(min_length=1, max_length=200)
    confidence: Confidence


class ProposedPlanChange(StrictAIOutput):
    date: str | None
    session_type: str | None
    title: str | None
    description: str | None
    planned_duration_minutes: float | None
    planned_distance_km: float | None
    target_rpe: float | None
    structured_blocks: list[str] | None


class PlanAdaptationInput(BaseModel):
    primary_goal: str
    running_phase: str
    climbing_phase: str
    recent_workouts: list[dict[str, Any]]
    fatigue: dict[str, float]
    readiness: dict[str, Any]
    upcoming_seven_days: list[dict[str, Any]]
    deterministic_rule_result: dict[str, Any]
    approved_coaching_principles: list[str] = Field(default_factory=list)


class PlanAdaptationOutput(StrictAIOutput):
    action: AdaptationAction
    proposed_plan: ProposedPlanChange
    reason: str
    evidence: list[str]
    confidence: Confidence


class WeeklyReviewInput(BaseModel):
    goals: list[dict[str, Any]]
    phases: dict[str, str]
    planned_week: list[dict[str, Any]]
    completed_week: list[dict[str, Any]]
    recent_four_week_trends: dict[str, Any]
    recovery: list[str]
    previous_review: dict[str, Any] | None = None


class WeeklyReviewOutput(StrictAIOutput):
    summary: list[str]
    running: list[str]
    climbing: list[str]
    recovery: list[str]
    key_findings: list[str]
    next_week: list[str]
    confidence: Confidence


class WeeklyPlanningContext(BaseModel):
    long_term_goals: list[dict[str, Any]]
    long_term_summary: dict[str, Any]
    athlete_state: dict[str, Any]
    phases: dict[str, str]
    this_week_summary: dict[str, Any]
    previous_weekly_summaries: list[dict[str, Any]]
    current_monthly_block: dict[str, Any] | None
    load: dict[str, Any]
    readiness: dict[str, Any]
    recent_recovery: list[dict[str, Any]]
    upcoming_availability: list[dict[str, Any]]
    locked_sessions: list[dict[str, Any]]
    running_subjective_feedback: list[dict[str, Any]]


class StructuredBlockProposal(StrictAIOutput):
    phase: str | None
    description: str | None
    exercise: str | None


class PlannedSessionProposal(StrictAIOutput):
    date: str
    start_time: str | None
    workout_kind: Sport
    session_type: str
    title: str
    description: str
    planned_duration_minutes: float | None
    planned_distance_km: float | None
    target_rpe: float | None
    priority: SessionPriority
    structured_blocks: list[StructuredBlockProposal]


class WeeklyPlanReview(StrictAIOutput):
    summary: str
    running_analysis: str
    climbing_analysis: str
    recovery_analysis: str
    key_findings: list[str]


class NextWeekPlan(StrictAIOutput):
    summary: str
    running_target_km: float
    running_objectives: list[str]
    climbing_objectives: list[str]
    sessions: list[PlannedSessionProposal]
    warnings: list[str]


class WeeklyReviewPlanOutput(StrictAIOutput):
    review: WeeklyPlanReview
    next_week: NextWeekPlan


class MonthlyPlanningContext(BaseModel):
    long_term_goals: list[dict[str, Any]]
    long_term_summary: dict[str, Any]
    athlete_state: dict[str, Any]
    phases: dict[str, str]
    current_month_summary: dict[str, Any]
    previous_monthly_summaries: list[dict[str, Any]]
    recent_weekly_summaries: list[dict[str, Any]]
    running_volume_progression: dict[str, Any]
    running_performance_progression: dict[str, Any]
    climbing_benchmark_progression: dict[str, Any]
    readiness_fatigue_trend: dict[str, Any]
    known_future_constraints: list[dict[str, Any]]
    locked_events: list[dict[str, Any]]


class MonthlyPlanReview(StrictAIOutput):
    summary: str
    running_analysis: str
    climbing_analysis: str
    recovery_analysis: str
    goal_progress: str
    key_findings: list[str]


class NextMonthBlock(StrictAIOutput):
    running_phase: str
    climbing_phase: str
    running_objectives: list[str]
    climbing_objectives: list[str]
    weekly_running_volume_targets: list[float]
    quality_session_guidance: str
    long_run_guidance: str
    climbing_frequency_guidance: str
    climbing_focus: list[str]
    supporting_strength_guidance: str
    progression_criteria: list[str]
    hold_criteria: list[str]
    deload_criteria: list[str]


class MonthlyReviewPlanOutput(StrictAIOutput):
    review: MonthlyPlanReview
    next_month_block: NextMonthBlock


WORKOUT_FIELDS = (
    "workout_kind",
    "session_type",
    "title",
    "activity_type",
    "date",
    "distance_km",
    "duration_minutes",
    "average_pace",
    "average_hr",
    "max_hr",
    "elevation_m",
    "cadence",
    "power_w",
    "board_name",
    "angle",
    "rpe",
    "splits",
    "intervals",
    "notes",
)


def _require_key(settings: Settings) -> str:
    if not settings.openai_api_key:
        raise AIUnavailableError(
            "OPENAI_API_KEY is not configured; manual features remain available."
        )
    return settings.openai_api_key


def _validate_provider_output(output_type: type[BaseModel], data: Any) -> Any:
    try:
        return output_type.model_validate(data)
    except ValidationError as exc:
        raise AIUnavailableError("OpenAI returned output that failed schema validation.") from exc


def _responses_json(
    *, system: str, user_content: Any, schema_name: str, schema: dict[str, Any], model: str
) -> dict[str, Any]:
    settings = get_settings()
    key = _require_key(settings)
    payload = {
        "model": model,
        "instructions": system,
        "input": [{"role": "user", "content": user_content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AIUnavailableError(f"OpenAI request failed: {exc}") from exc
    output_text = body.get("output_text")
    if output_text is None:
        for output in body.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    output_text = content.get("text")
                    break
    if not output_text:
        raise AIUnavailableError("OpenAI returned no structured output.")
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise AIUnavailableError("OpenAI returned invalid structured output.") from exc


def _workout_schema() -> dict[str, Any]:
    numeric = {"type": ["number", "null"]}
    string = {"type": ["string", "null"]}
    value_schemas = {name: string for name in WORKOUT_FIELDS}
    for name in (
        "distance_km",
        "duration_minutes",
        "average_hr",
        "max_hr",
        "elevation_m",
        "cadence",
        "power_w",
        "rpe",
        "angle",
    ):
        value_schemas[name] = numeric
    for name in ("splits", "intervals"):
        value_schemas[name] = {
            "anyOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"},
            ]
        }
    value_schemas["workout_kind"] = {
        "type": ["string", "null"],
        "enum": [
            "RUNNING",
            "CLIMBING",
            "STRENGTH",
            "CROSSFIT_CONDITIONING",
            "MOBILITY_RECOVERY",
            None,
        ],
    }
    value_schemas["session_type"] = {
        "type": ["string", "null"],
        "enum": [
            "EASY",
            "LONG_RUN",
            "QUALITY",
            "RACE",
            "BOULDERING",
            "SPORT_CLIMBING",
            "BOARD",
            "Strength",
            "CrossFit / Conditioning",
            "Mobility / Recovery",
            None,
        ],
    }

    def field_schema(name: str) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "value": value_schemas[name],
                "confidence": {"type": "string", "enum": ["LOW", "MODERATE", "HIGH"]},
                "source": {"type": "string"},
            },
            "required": ["value", "confidence", "source"],
            "additionalProperties": False,
        }

    return {
        "type": "object",
        "properties": {name: field_schema(name) for name in WORKOUT_FIELDS},
        "required": list(WORKOUT_FIELDS),
        "additionalProperties": False,
    }


def extract_workout_from_text(
    text: str, *, reference_date: date | None = None
) -> WorkoutExtraction:
    settings = get_settings()
    local_date = reference_date or datetime.now(ZoneInfo(settings.athlete_timezone)).date()
    data = _responses_json(
        system=(
            "Extract only workout facts explicitly present in the user's text. "
            "Every field is {value, confidence, source}; unseen values must be null. "
            f"The athlete's current local date is {local_date.isoformat()}; resolve only explicit "
            "relative dates such as today or yesterday. Return date as YYYY-MM-DD, duration_minutes "
            "as total minutes, average_pace as M:SS per km, heart rates as whole bpm, and RPE as a "
            "number from 1 to 10. Do not infer physiology or fabricate measurements. The output is "
            "a preview, never a save. Running session_type must be EASY, LONG_RUN, QUALITY, or "
            "RACE; climbing session_type must be BOULDERING, SPORT_CLIMBING, or BOARD. If the "
            "type is uncertain, return null."
            " Preserve a factual workout title when explicitly present. For BOARD climbing, also "
            "extract board_name and angle when stated."
        ),
        user_content=[{"type": "input_text", "text": text}],
        schema_name="workout_extraction",
        schema=_workout_schema(),
        model=settings.openai_model,
    )
    extraction = _validate_provider_output(WorkoutExtraction, data)
    return normalise_workout_extraction(extraction, reference_date=local_date)


def extract_workout_from_image(image: bytes, media_type: str) -> WorkoutExtraction:
    settings = get_settings()
    local_date = datetime.now(ZoneInfo(settings.athlete_timezone)).date()
    encoded = base64.b64encode(image).decode("ascii")
    data = _responses_json(
        system=(
            "Extract only values visibly present in this Garmin, Strava, or training screenshot. "
            "Return null for unseen or unreadable values. Every source must name visible evidence. "
            "This is a correctable preview and must not claim it was saved."
            " Running session_type must be EASY, LONG_RUN, QUALITY, or RACE; climbing must be "
            "BOULDERING, SPORT_CLIMBING, or BOARD. Return null when uncertain."
            " Preserve a visible workout title and BOARD name/angle when present."
        ),
        user_content=[
            {"type": "input_text", "text": "Extract the workout."},
            {"type": "input_image", "image_url": f"data:{media_type};base64,{encoded}"},
        ],
        schema_name="workout_image_extraction",
        schema=_workout_schema(),
        model=settings.openai_vision_model,
    )
    extraction = _validate_provider_output(WorkoutExtraction, data)
    return normalise_workout_extraction(extraction, reference_date=local_date)


def transcribe_training_note(audio: bytes, filename: str, media_type: str) -> str:
    prompt = (
        "Chinese and English running/climbing note. Vocabulary: LT1, LT2, threshold, VO2max, "
        "Tension Board, TB2, heel hook, toe hook, limit bouldering, max hangs, power endurance, RPE."
    )
    return _transcribe_audio(audio, filename, media_type, prompt)


def classify_note_text(text: str) -> tuple[NoteCategory, Confidence]:
    lowered = text.lower()
    running_terms = (
        "run",
        "running",
        "threshold",
        "lt1",
        "lt2",
        "vo2",
        "pace",
        "跑",
        "馬拉松",
        "马拉松",
    )
    climbing_terms = (
        "climb",
        "boulder",
        "tension board",
        "tb2",
        "heel hook",
        "攀岩",
        "抱石",
        "爬",
    )
    strength_terms = ("strength", "mobility", "squat", "deadlift", "力量", "拉伸")
    scores = {
        NoteCategory.RUNNING: sum(term in lowered for term in running_terms),
        NoteCategory.CLIMBING: sum(term in lowered for term in climbing_terms),
        NoteCategory.STRENGTH_MOBILITY: sum(term in lowered for term in strength_terms),
    }
    category = max(scores, key=scores.get)
    score = scores[category]
    return (
        category,
        Confidence.HIGH if score >= 2 else Confidence.MODERATE if score == 1 else Confidence.LOW,
    )


def process_training_note(text: str) -> ProcessedNote:
    settings = get_settings()
    schema = ProcessedNote.model_json_schema()
    data = _responses_json(
        system=(
            "Organise a training knowledge note. Classify exactly RUNNING, CLIMBING, or "
            "STRENGTH_MOBILITY. Preserve Chinese/English training terms. Notes are advisory "
            "knowledge and must never claim to alter a plan."
        ),
        user_content=[{"type": "input_text", "text": text}],
        schema_name="processed_training_note",
        schema=schema,
        model=settings.openai_model,
    )
    return _validate_provider_output(ProcessedNote, data)


def analyse_completed_session(
    context: SessionAnalysisInput | dict[str, Any],
) -> SessionAnalysisOutput:
    try:
        validated = SessionAnalysisInput.model_validate(context)
    except ValidationError as exc:
        raise AIUnavailableError("Session-analysis context failed schema validation.") from exc
    return _typed_coaching_call(
        (
            "Write one concise athlete-facing analysis of this completed session using evidence "
            "only. The summary must be no more than 200 Unicode characters including spaces. "
            "Mention only the most useful planned-versus-actual or recovery point; do not repeat "
            "the raw workout, fatigue, or readiness payload and never invent data."
        ),
        validated,
        SessionAnalysisOutput,
        "session_analysis",
    )


def propose_plan_adaptation(
    context: PlanAdaptationInput | dict[str, Any],
) -> PlanAdaptationOutput:
    try:
        validated = PlanAdaptationInput.model_validate(context)
    except ValidationError as exc:
        raise AIUnavailableError("Adaptation context failed schema validation.") from exc
    return _typed_coaching_call(
        "Propose at most one conservative action from KEEP, REDUCE_VOLUME, REDUCE_INTENSITY, "
        "MOVE, REPLACE, ADD_RECOVERY, PROGRESS. Treat deterministic rules as binding; never "
        "rewrite the plan freely or progress from missing evidence.",
        validated,
        PlanAdaptationOutput,
        "plan_adaptation",
    )


def generate_weekly_review(
    context: WeeklyReviewInput | dict[str, Any],
) -> WeeklyReviewOutput:
    try:
        validated = WeeklyReviewInput.model_validate(context)
    except ValidationError as exc:
        raise AIUnavailableError("Weekly-review context failed schema validation.") from exc
    return _typed_coaching_call(
        "Generate an evidence-based weekly training review. Do not diagnose injury or disease.",
        validated,
        WeeklyReviewOutput,
        "weekly_review",
    )


def review_and_plan_week(
    context: WeeklyPlanningContext | dict[str, Any],
) -> WeeklyReviewPlanOutput:
    try:
        validated = WeeklyPlanningContext.model_validate(context)
    except ValidationError as exc:
        raise AIUnavailableError("Weekly planning context failed schema validation.") from exc
    return _typed_planner_call(
        (
            "Review the completed week and propose the next seven days. Use only supplied "
            "evidence. Treat subjective feedback as context, not objective measurement. Preserve "
            "locked sessions, do not invent missing values, and return a compact practical plan."
        ),
        validated,
        WeeklyReviewPlanOutput,
        "weekly_review_and_plan",
    )


def review_and_plan_month(
    context: MonthlyPlanningContext | dict[str, Any],
) -> MonthlyReviewPlanOutput:
    try:
        validated = MonthlyPlanningContext.model_validate(context)
    except ValidationError as exc:
        raise AIUnavailableError("Monthly planning context failed schema validation.") from exc
    return _typed_planner_call(
        (
            "Review the completed month and propose one next-month training block, not 30 daily "
            "workouts. Use weekly and monthly aggregates only. Never request or infer raw "
            "per-workout voice transcripts and do not claim to change athlete phases directly."
        ),
        validated,
        MonthlyReviewPlanOutput,
        "monthly_review_and_plan",
    )


def _typed_planner_call(
    system: str,
    context: BaseModel,
    output_type: type[BaseModel],
    name: str,
) -> Any:
    settings = get_settings()
    data = _responses_json(
        system=system,
        user_content=[{"type": "input_text", "text": context.model_dump_json()}],
        schema_name=name,
        schema=output_type.model_json_schema(),
        model=settings.openai_planner_model,
    )
    return _validate_provider_output(output_type, data)


def transcribe_running_feedback(audio: bytes, filename: str, media_type: str) -> str:
    prompt = (
        "Post-run subjective feedback in Chinese, English, or mixed language. Preserve training "
        "terms: easy run, threshold, tempo, interval, VO2, LT1, LT2, RPE, heart rate, pace, "
        "long run, strides. Transcribe faithfully; do not analyse or add advice."
    )
    return _transcribe_audio(audio, filename, media_type, prompt)


def _typed_coaching_call(
    system: str,
    context: BaseModel,
    output_type: type[BaseModel],
    name: str,
) -> Any:
    settings = get_settings()
    data = _responses_json(
        system=system,
        user_content=[{"type": "input_text", "text": context.model_dump_json(exclude_none=False)}],
        schema_name=name,
        schema=output_type.model_json_schema(),
        model=settings.openai_model,
    )
    return _validate_provider_output(output_type, data)


def basic_text_extraction_for_tests(text: str) -> dict[str, Any]:
    """Small deterministic parser used only as a no-network unit-test seam."""
    distance = re.search(r"(\d+(?:\.\d+)?)\s*km", text, re.IGNORECASE)
    duration = re.search(r"(\d+(?:\.\d+)?)\s*(?:min|分钟|分鐘)", text, re.IGNORECASE)
    return {
        "distance_km": float(distance.group(1)) if distance else None,
        "duration_minutes": float(duration.group(1)) if duration else None,
    }
