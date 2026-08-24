# Data model

> The current simplified workflow writes factual sessions, descriptive benchmarks, fixed report
> inputs, imported-plan history, monthly blocks, and Calendar revisions. Legacy stress, fatigue,
> readiness, recovery, and adaptation tables are retained for migration/backup compatibility but
> are not updated by normal completed-workout saving or external plan import.

## Document status

This file describes the SQLAlchemy model and initial Alembic migration in this checkout. Where a
future durability rule is still required, it is called out as an acceptance target rather than
described as implemented.

SQLite is the local source of truth. The normal development URL resolves to
`backend/data/training_coach.db`, and Alembic owns the portable schema.

## Implemented conventions

- Most tables use integer primary keys. One-to-one sport detail tables use the completed-session
  ID as their primary/foreign key; `app_settings` uses a string key.
- Top-level user-facing records generally have `created_at` and `updated_at`; detail, stress, and
  snapshot tables use only the timestamps needed by their contract.
- Athlete-facing session/benchmark dates are ISO dates. Completed sessions store an optional
  local start time, not a separate UTC start instant.
- Durations and distances are stored as minutes and kilometres. Pace uses seconds per kilometre,
  elevation metres, power watts, and strength load kilograms.
- The frontend presents duration and race-time values as `M:SS` or `H:MM:SS` and converts those
  inputs at the API boundary; SQLite retains the established numeric minute/second units.
- Nullable evidence remains SQL `NULL`; zero is not substituted for an unknown measurement.
- Completed-session RPE is nullable and otherwise constrained to 1–10.
- Enum values are stored as strings and validated through application/SQLAlchemy types. Numeric
  ranges are enforced by request models and selected database constraints.
- JSON is intentionally used for structured blocks, splits/intervals, soreness areas, style tags,
  note lists, fatigue/readiness components, plan snapshots, weekly-review sections, settings,
  and provider payloads.

## Identity, goals, and phases

### `athlete_profiles`

Singleton profile containing display name, timezone, current running/climbing phases, editable
running baselines/goals, editable climbing baselines/goals, home gym, and timestamps. Initial
values are seeds; services read the stored row. The public profile keeps `tb2_long_term_goal` and
`outdoor_boulder_goal` distinct. The older `bouldering_goal` request/response name remains a
backward-compatible alias for `tb2_long_term_goal` and never overwrites the outdoor goal.

### `athlete_state_history`

Append-only audit rows for actual running- or climbing-phase changes: athlete, change time, state
type, old/new value, and source. Updating other profile baselines still updates the current
profile row without a separate audit event.

### `goals`

Goal type, description, target value/date, status, notes, `is_current`, and timestamps. A partial
unique index permits one current goal per athlete. Creating a new current goal clears the prior
row's current flag but retains that row.

Allowed goal types are `RUNNING_MILEAGE`, `HALF_MARATHON`, `MARATHON`, `BOULDERING`, and
`LEAD_CLIMBING`.

## Plans and completed training

### `planned_sessions` and `planned_session_revisions`

A plan stores athlete, local date/start time, sport, workout type, title/description, planned
duration/distance, target-RPE bounds, priority, status, structured blocks, version, demo flag, and
optional move/replacement links.

Every created plan receives an initial revision snapshot. Manual/adaptation edits increment the
version and append a revision. Accepting `MOVE` or `REPLACE` retains the original row and inserts a
linked successor. Completing a linked workout changes the plan status to `COMPLETED`; the initial
revision still contains the original prescription.

Status is `PLANNED`, `COMPLETED`, `MODIFIED`, `SKIPPED`, `MOVED`, `REPLACED`, or `REST`.

### `completed_sessions`

Common evidence is athlete, optional plan link, local date/start time, duration minutes, sport,
workout type, nullable RPE, notes, nullable sRPE/base stress, optional AI analysis, demo flag, and
timestamps. The public API creates, lists, and permanently deletes completed sessions. Deletion
requires an explicit irreversible UI confirmation, removes sport-specific child evidence, and
rebuilds derived running estimates. A linked planned session returns to `PLANNED` when no other
completion remains; adaptation audit rows are detached from the removed trigger.

Sport-specific detail is stored as follows:

- `running_session_details`: distance, pace, average/max HR, elevation, cadence, power, and JSON
  split/interval lists.
- `climbing_session_details`: gym/crag, hard attempts, maximum attempted/sent label, and grade
  scale.
- `climbing_attempts`: optional relational problem rows with attempt/outcome flags and JSON style
  tags.
- `strength_session_details`: workout name, rounds, and result time. It is used for both
  `STRENGTH` and `CROSSFIT_CONDITIONING`.
- `strength_sets`: optional exercise, set count, reps, load, RPE, RIR, and JSON tags.

Completed-session create/list responses round-trip these durable details as `splits`,
`interval_blocks`, `climbing_attempts`, and `strength_sets`, with a nested `strength` summary as
well as flat workout-name/rounds/result-time fields. A `result_time` request in `MM:SS` or
`HH:MM:SS` form is normalized to the stored and returned `result_time_seconds`; callers may still
supply seconds directly.

There are no separate `running_splits`, `running_interval_blocks`, conditioning-detail, or style-
tag join tables in V1.

### `session_domain_stresses`

One row per completed session and fatigue domain, containing coefficient, multiplier, resulting
stress, and algorithm version. The unique session/domain constraint supports deterministic
recalculation without duplicate rows.

## Recovery, fatigue, and readiness

### `recovery_checkins`

Athlete, recorded timestamp, sleep duration/quality, energy, motivation, stress, general
soreness, JSON area-soreness values, resting HR, HRV, notes, demo flag, and timestamps. The API
accepts finger, elbow, shoulder, back, hip, knee, calf, and ankle values from 0–10. There is no
separate soreness-area table.

### `fatigue_snapshots`

One aggregate snapshot per athlete/source key, with calculation time, JSON latent/display maps
for all six domains, and algorithm version. Current fatigue views replay stored session-domain
stress rather than reading these snapshots as the only source of truth.

### `readiness_snapshots`

One combined running/climbing snapshot per athlete/source key, with both scores/labels, JSON
components, subjective delta, calculation time, and algorithm version.

## Athlete state and progress evidence

### `running_fitness_estimates`

Append-only 10K estimate rows containing seconds, confidence, source event/date, formula,
evidence, demo flag, and timestamps. Race/time-trial evidence creates these rows; a recent actual
10K takes display precedence over Riegel estimates.

### `threshold_estimates`

Append-only LT1/LT2 rows containing pace/HR ranges, confidence, source, measured date, demo flag,
and timestamps.

Calendar/rolling mileage and easy-efficiency series are derived from completed running sessions;
they are not competing mutable totals.

### Climbing evidence

- `tb2_benchmarks`: date, board (API-constrained to `TB2`), angle, verified/estimated
  grade, grade scale, notes, demo flag, and timestamps.
- `gym_sets`: gym, start/end dates, active flag, notes, demo flag, and timestamps.
- `gym_set_colour_progress`: colour ordinal, sent count, optional available count, and
  timestamps. A `(gym_set_id, colour)` unique constraint prevents duplicates. Create/patch
  request models reject negative counts and a sent count above a known available count.
- `route_benchmarks`: dated top-rope, lead, and target grade rows with notes/timestamps.

Starting a new set for the same gym closes the active set and inserts another row. Grade/colour
ordinals support ordering and chart placement only.

## Adaptation and weekly review

### `adaptation_events`

Affected plan, trigger workout, immutable original/proposed JSON snapshots, constrained action,
reason, evidence, confidence, source, decision, decision time, and timestamps. Apply/reject/edit
updates the event decision; an accepted plan change preserves revision or successor history. An
edited proposal crosses a strict typed allow-list at the API boundary: unknown fields and invalid
negative duration/distance/RPE values produce request-validation 422 responses before persistence.

### `weekly_reviews`

One row per week start, with end date, deterministic summary/compliance JSON, running/climbing/
recovery JSON sections, finding/recommendation lists, narrative, source, and timestamps. The
table does not currently store model, prompt, or configuration trace metadata. Compliance excludes
calendar `REST` and superseded `MOVED`/`REPLACED` rows from the planned denominator and consults
plan revisions to distinguish a completed-but-modified prescription. Historical gym summaries
select the set whose start/end lifecycle covers the review's `week_end`.

## Training knowledge

### `training_notes`

Category, title, raw and cleaned content, summary, JSON takeaways/actionable ideas/tags, optional
source metadata, input type, classification confidence, `use_for_coaching`, favorite, demo flag,
and timestamps. Lists are JSON rather than normalized takeaway/tag join tables. Search initially
uses SQL `LIKE` over title/content/summary and application filtering for tags.

### `coaching_principles`

Optional source-note link, category, principle text, active flag, athlete-approved flag, and
timestamps. The API creates explicitly approved principles; note processing cannot create one.

## Imports and settings

### `monthly_training_blocks` and `imported_plans`

An accepted `TRAINING_MONTHLY_PLAN_V1` is retained verbatim in `imported_plans` and saved as a
structured JSON monthly block. The structured content separates running phase, objective,
session frequency/structure, weekly distance targets, quality and long-run guidance, principles,
climbing frequency/structure and board focus, auxiliary guidance, and general notes. Older V1
imports without optional frequency or principle fields are normalised when read and remain valid.
Editing creates a new active monthly-block revision and archives the previous row. Monthly import
does not create Calendar sessions; only accepted weekly-plan sessions do that.

### `media_imports`

Media kind/status, original filename, optional local path, retention flag, extraction/transcript
JSON, error text, optional confirmed-session link, and timestamps. Current image/audio endpoints
create these rows; they do not populate provider/request IDs, confirmed time, or deleted time, and
the frontend confirmation flow does not yet attach the row to its completed session.

Raw media is never embedded in the database. It is written under `backend/data/media/` only when
retention is enabled.

### `app_settings`

String key, JSON value, and timestamps for non-secret current settings such as media retention,
grade display, and engine overrides. Provider credentials remain environment-only. Setting
changes overwrite the current row; there is no settings-history table in V1.

### Demo ownership

V1 uses `is_demo` flags on seeded top-level sessions, plans, recovery, benchmarks, gym sets,
notes, and derived running/threshold estimate rows. It does not use a `demo_batches` table.
Explicit demo cleanup deletes only flagged rows plus adaptation events triggered by or affecting
flagged records; relational child rows cascade from their owner.

## Referential and deletion behavior

- SQLite foreign-key enforcement is enabled on every application and migration connection.
- Completed-session sport details/stresses cascade with their owning completed session during
  restore replacement or explicit demo cleanup.
- Plan revisions and gym colour rows cascade with their owner in those administrative flows.
- Normal product routes do not delete athlete-owned completed sessions, plans, benchmarks, or
  notes.
- Plan moves/replacements retain originals; gym-set replacement closes the earlier set; benchmark
  and estimate updates append rows; phase updates append `athlete_state_history`.
- Current profile baselines, current app settings, gym colour counts within the active set, and
  note fields are mutable current-value records.

## Backup and restore format

`GET /api/v1/data/backup` returns:

```json
{
  "schema_version": "1.0",
  "exported_at": "2026-08-23T...+00:00",
  "data": {
    "athlete_profiles": [],
    "planned_sessions": [],
    "...": []
  }
}
```

It serializes every mapped table, including derived snapshots and audit rows. `media_imports`
local paths are set to `null` and retention flags to false; environment secrets and raw media
files are not included. The format currently has no application-version or athlete-timezone
top-level field.

Restore accepts schema version `1.0`, prepares known table rows and known columns/types before
replacement, deletes in reverse dependency order, inserts in forward order, and commits once.
Database/insert failure rolls the transaction back to the previous state. The Settings UI
requires typing `RESTORE`, while the API itself accepts the uploaded backup directly. V1 is full
replacement, not merge.

CSV export supports completed/planned sessions, running/climbing detail, recovery, TB2, gym sets/
colour progress, notes, weekly reviews, and adaptation events. UI aliases are `workouts`,
`recovery`, `benchmarks`, and `notes`; output uses database column names and ISO date/time values.

## Remaining durability acceptance work

- Add explicit model/config trace versions to AI analyses and weekly reviews.
- Link confirmed image/audio previews to the durable workout/note they produced.
- Add a versioned audit trail if edits to profile baselines or engine settings must be replayable.
- Define a compatible migration/transform policy before accepting backup schema versions other
  than `1.0`.
