# AI contracts

## Document status

This document records both the implemented V1 adapter contract and the remaining acceptance
work. Sections labelled **Implemented** describe the checked-in API. Sections labelled
**Acceptance target** are requirements, not claims that the behavior already exists.

AI is optional and backend-only. Core workout logging, state, load, fatigue, readiness,
progress, deterministic adaptation, notes, and deterministic weekly review work without an API
key. The browser never receives `OPENAI_API_KEY`.

## Implemented boundary rules

- Provider prose is parsed into Pydantic models before a successful adapter result is returned.
- Unknown workout-extraction values use `value = null`; every extraction field also has
  `confidence` and `source`.
- Extraction and note-processing endpoints return data to review. They do not create a completed
  session or training note.
- The React flows expose an editable review/confirmation step before calling the ordinary save
  endpoints. The completed-session API does not currently require a server-issued preview token.
- Completed-session analysis is commentary stored on the completed session. It does not compute
  load, fatigue, readiness, or progression.
- AI plan work starts only after a deterministic proposal exists. The service accepts AI wording
  only when its action exactly matches the deterministic action, and it retains the
  deterministic plan patch.
- Training notes default to `use_for_coaching = false`. Only explicitly approved notes and active
  coaching principles are included in AI adaptation context.
- Provider/model selection is centralized in backend environment settings.

## Implemented shared types

Workout extraction uses this conceptual shape for every field:

```python
class ExtractedValue(BaseModel):
    value: Any | None
    confidence: LOW | MODERATE | HIGH
    source: str
```

The current adapter does not return a common `AITrace`, request ID, prompt version, schema
version, or warnings collection. File imports do create a local `media_imports` audit row with
status and extraction/error payload.

## Errors and capability discovery

`GET /api/v1/capabilities` returns:

```text
ai_configured
image_extraction
text_extraction
transcription
note_processing
ai_session_analysis
ai_adaptation
ai_weekly_review
model / vision_model / transcription_model
reason
```

In V1 all AI capability booleans use the same gate: whether `OPENAI_API_KEY` is configured.
Model names are returned only when configured.

Missing configuration, provider HTTP failures, timeouts, invalid provider JSON, and an empty
provider result are mapped by the adapters to HTTP 503 with FastAPI's normal body:

```json
{"detail": "OPENAI_API_KEY is not configured; manual features remain available."}
```

FastAPI request validation and empty-upload checks return 422. The current upload routes do not
yet enforce a MIME allow-list or explicit byte-size limit, and errors do not yet use stable
`code`, `field_errors`, `retryable`, or `request_id` fields. Pydantic validates structured model
output, but every validation failure is not yet normalized into a dedicated 502 response.

## `extract_workout_from_image()`

**Implemented endpoint:** `POST /api/v1/ai/workouts/extract-image`

The request is multipart field `image` plus optional `retain_raw` (false by default). The backend
passes bytes and the uploaded content type to the configured vision model. It creates a
`media_imports` row before the provider call.

The response contains these fields, each as `ExtractedValue`:

```text
workout_kind, session_type, activity_type, date, distance_km, duration_minutes,
average_pace, average_hr, max_hr, elevation_m, cadence, power_w, rpe,
splits, intervals, notes
```

`splits` and `intervals` are currently nullable lists of strings, not nested typed rows. There is
no preview ID or trace object. The frontend lets the athlete correct these fields and then posts
the confirmed values to `POST /api/v1/completed-sessions`; the media row is not currently linked
to that completed session.

Raw bytes are written to `backend/data/media/` only when request or stored retention is enabled.
With default retention they exist only in request memory and are not written to disk. A provider
failure marks the audit row `FAILED` and does not create a completed session.

## `extract_workout_from_text()`

**Implemented endpoint:** `POST /api/v1/ai/workouts/extract-text`

Input is `{"text": "..."}`. It returns the same common field set as image extraction and does
not write a preview/media row. The common fields can represent a sport and session label, but the
current extraction schema does not contain dedicated climbing-attempt, gym/location, or strength-
set fields. Those details must be added in the manual editor after extraction.

Extraction alone never changes load or readiness. The frontend confirmation uses the normal
completed-session endpoint.

## `transcribe_training_note()`

**Implemented endpoint:** `POST /api/v1/ai/notes/transcribe`

The request uses multipart field `audio` plus optional `retain_raw`. The backend supplies a prompt
containing Chinese/English running and climbing terminology such as LT1, LT2, VO2max, TB2, heel
hook, max hangs, power endurance, and RPE.

The successful API response is currently:

```json
{"transcript": "..."}
```

It does not include detected languages, duration, warnings, trace metadata, or a media/preview
ID. The transcript is not organized or saved automatically. As with images, raw audio is written
to disk only when retention is enabled; otherwise only the audit row and transcript payload are
stored.

## `process_training_note()`

**Implemented endpoint:** `POST /api/v1/ai/notes/process`

Input contains `raw_input` and `input_type`; the current adapter sends only the raw text to the
model. It returns:

```text
primary_category: RUNNING | CLIMBING | STRENGTH_MOBILITY
title
cleaned_note
summary
key_takeaways[]
actionable_ideas[]
tags[]
classification_confidence
```

The processor has no field that can activate coaching use or create a coaching principle. The
athlete can edit every returned field before `POST /api/v1/training-notes`; saved notes default to
`use_for_coaching = false`.

## `analyse_completed_session()`

The completed-session service may call this function after saving a workout when AI is
configured. Context contains the current goal, both phases, linked plan when present, completed
workout, fatigue, and readiness. Output is:

```text
execution_summary
planned_vs_actual[]
strong_execution
unexpected_fatigue
evidence[]
confidence
```

The result is stored in `completed_sessions.ai_analysis`. An unavailable provider is ignored so
the workout remains saved.

## `propose_plan_adaptation()`

**Implemented endpoint:** `POST /api/v1/adaptations/propose`

The service first produces a deterministic proposal from the trigger workout, current fatigue
and readiness, comparable history, and the next seven days. If AI is configured, its bounded
context includes:

- current primary goal and both phases;
- completed sessions from the previous 14 days;
- current latent fatigue and readiness labels;
- next seven days of planned sessions;
- the complete deterministic action/reason/evidence/patch; and
- active approved principles plus notes with `use_for_coaching = true`.

The typed AI output is:

```text
action: KEEP | REDUCE_VOLUME | REDUCE_INTENSITY | MOVE | REPLACE |
        ADD_RECOVERY | PROGRESS
proposed_plan (typed optional fields)
reason
evidence[]
confidence
```

The service uses AI reason/evidence/confidence only if `action` matches the deterministic result.
It never uses the model's proposed patch in place of the deterministic patch. The persisted event
is `PENDING` and the UI offers Apply, Reject, and Edit. Decision endpoint
`POST /api/v1/adaptations/{id}/decision` accepts `ACCEPT`/`ACCEPTED` or rejection and an optional
edited plan. Edited plans are validated through a typed allow-list; unknown keys, invalid enum/date
values, and negative duration/distance or out-of-range RPE fail with 422 rather than reaching the
database. Moves/replacements create a linked successor; other accepted edits create a plan revision.

## `generate_weekly_review()`

**Implemented endpoint:** `POST /api/v1/weekly-reviews/generate`

Deterministic code computes totals, compliance, running/climbing observations, and recovery
evidence first. With AI configured, the model receives current goals/phases, planned and
completed week, four fixed historical buckets of running, climbing, and load trends ending at the
review's `week_end`, recovery text, and the previous review when present. Historical gym evidence
is likewise selected by the set lifecycle at `week_end`, so future active sets do not enter the
context. Its typed output is:

```text
summary[]
running[]
climbing[]
recovery[]
key_findings[]
next_week[]
confidence
```

AI narrative lists can replace deterministic narrative lists, but numeric totals and compliance
remain deterministic. Athlete-approved note/principle context is not currently included in the
weekly-review call.

## Prompt and context management

System instructions are currently inline in `backend/app/ai/functions.py`, with one instruction
per function. Model names come from `OPENAI_MODEL`, `OPENAI_VISION_MODEL`, and
`OPENAI_TRANSCRIBE_MODEL`. Explicit prompt versioning, context-length policies, provider request
IDs, and stored trace metadata remain acceptance work.

## Automated test coverage

Current mocked tests verify:

- common workout extraction fields, including RPE, splits, and intervals;
- the constrained adaptation action type; and
- distinct typed outputs for session analysis and weekly review; and
- the AI-enabled weekly-review context/service path with a mocked typed result.

Separate deterministic/service tests cover mixed Chinese-English note classification,
`use_for_coaching = false` plan safety, plan-move preservation, backup path scrubbing/replacement,
and engine safety scenarios. No automated test makes a live provider request.

## Acceptance target not yet claimed

Before treating the full AI contract as complete, add and verify:

- stable error envelopes and status mapping for authentication, rate limits, outages, malformed
  output, and timeout;
- MIME/type and upload-size validation;
- preview IDs and durable confirmation/provenance links;
- trace fields with provider/model/prompt/schema versions;
- typed nested split/interval rows and climbing/strength extraction fields;
- explicit context-length limits and approved-note context for weekly review; and
- mocked tests for media cleanup/retention, preview non-mutation, invalid enums/ranges, provider
  failures, and deterministic numeric precedence.
