from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings
from app.enums import AdaptationAction, Confidence, NoteCategory


class AIUnavailableError(RuntimeError):
    pass


class StrictAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedValue(BaseModel):
    value: Any | None = None
    confidence: Confidence = Confidence.LOW
    source: str


class WorkoutExtraction(BaseModel):
    workout_kind: ExtractedValue
    session_type: ExtractedValue
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
    rpe: ExtractedValue
    splits: ExtractedValue
    intervals: ExtractedValue
    notes: ExtractedValue


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
    execution_summary: str
    planned_vs_actual: list[str]
    strong_execution: bool
    unexpected_fatigue: bool
    evidence: list[str]
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


WORKOUT_FIELDS = (
    "workout_kind",
    "session_type",
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


def extract_workout_from_text(text: str) -> WorkoutExtraction:
    settings = get_settings()
    data = _responses_json(
        system=(
            "Extract only workout facts explicitly present in the user's text. "
            "Every field is {value, confidence, source}; unseen values must be null. "
            "Do not infer physiology or fabricate measurements. The output is a preview, never a save."
        ),
        user_content=[{"type": "input_text", "text": text}],
        schema_name="workout_extraction",
        schema=_workout_schema(),
        model=settings.openai_model,
    )
    return _validate_provider_output(WorkoutExtraction, data)


def extract_workout_from_image(image: bytes, media_type: str) -> WorkoutExtraction:
    settings = get_settings()
    encoded = base64.b64encode(image).decode("ascii")
    data = _responses_json(
        system=(
            "Extract only values visibly present in this Garmin, Strava, or training screenshot. "
            "Return null for unseen or unreadable values. Every source must name visible evidence. "
            "This is a correctable preview and must not claim it was saved."
        ),
        user_content=[
            {"type": "input_text", "text": "Extract the workout."},
            {"type": "input_image", "image_url": f"data:{media_type};base64,{encoded}"},
        ],
        schema_name="workout_image_extraction",
        schema=_workout_schema(),
        model=settings.openai_vision_model,
    )
    return _validate_provider_output(WorkoutExtraction, data)


def transcribe_training_note(audio: bytes, filename: str, media_type: str) -> str:
    settings = get_settings()
    key = _require_key(settings)
    prompt = (
        "Chinese and English running/climbing note. Vocabulary: LT1, LT2, threshold, VO2max, "
        "Tension Board, TB2, heel hook, toe hook, limit bouldering, max hangs, power endurance, RPE."
    )
    try:
        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            data={"model": settings.openai_transcribe_model, "prompt": prompt},
            files={"file": (filename, audio, media_type)},
            timeout=90,
        )
        response.raise_for_status()
        transcript = response.json().get("text")
    except (httpx.HTTPError, ValueError) as exc:
        raise AIUnavailableError(f"Transcription failed: {exc}") from exc
    if not transcript:
        raise AIUnavailableError("Transcription returned no text.")
    return str(transcript)


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
        "Analyse execution against the planned session using evidence only. Never invent data.",
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
