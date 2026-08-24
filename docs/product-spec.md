# Product specification

> **Current simplified contract (August 2026):** the normal application is a factual logger,
> descriptive progress tracker, fixed report exporter, deterministic external-plan importer,
> Calendar, and personal notes store. Older load/fatigue/readiness/adaptation requirements below
> describe preserved legacy compatibility, not the active UI. The current workflow is
> `record -> progress -> weekly/monthly Markdown report -> external Web AI -> fixed plan format
> -> preview -> Calendar`. New completed sessions do not calculate sRPE load, fatigue, readiness,
> recovery, or automatic plan changes.

> **Document status:** This is the normative V1 product and release-acceptance contract. Wording
> such as "supports", "must", and "preserves" describes the target behavior; it is not by itself
> evidence that a particular checkout passed acceptance. See `README.md` for current runtime
> behavior and run `make test` to verify the checked-out revision.

## Product promise

Adaptive Training Coach builds a durable, auditable picture of one athlete's running and climbing state from completed training. It compares plan with execution, models recent load and fatigue, estimates separate readiness for the two sports, shows progress over months, and proposes conservative changes to upcoming work.

The second product pillar is a lightweight training-knowledge notebook. Text or voice notes can be organised automatically, but knowledge stays separate from measured evidence until the athlete explicitly enables it for coaching context.

## Scope and principles

- Primary sports: running and climbing.
- Supporting activities: strength, CrossFit/conditioning, and mobility/recovery.
- Data remains local by default and supports at least one year of history.
- The application explains estimates, evidence, confidence, and plan changes.
- No opaque fitness score, fake precise climbing metric, medical diagnosis, or guaranteed progression claim.
- A simple workout should be loggable in about 30 seconds.
- A voice note should require only record, review, and save in the happy path.
- Desktop is data-dense and technical; mobile remains usable for daily logging.

V1 deliberately excludes external Garmin/Strava OAuth, a separate strength dashboard, complex route-fitness or mandatory finger/pulling benchmarks, unrestricted AI plan generation, social/gamified features, and cloud hosting requirements.

## Initial editable profile

Initial values seed the profile; they are never permanent business-logic constants.

| Area | Initial value |
| --- | --- |
| Half-marathon performance | 1:45:00 |
| Current running volume | Less than about 100 km/calendar month |
| Long-term running volume | About 400 km/month; eventual 80–100 km/week only if sustainably absorbed |
| Half-marathon goals | Primary sub-1:30; stretch about 1:20 |
| Marathon goal | Sub-3:30 |
| TB2 verified benchmark | 6C |
| TB2 estimated maximum | About 6C+; stored separately from verified |
| Current top-rope level | About 6C–6C+ |
| Long-term TB2 goal | About V9–V10 |
| Long-term outdoor bouldering goal | About V10 |
| Long-term route goal | About 7B+–7C |

## Goals and phases

Exactly one goal is current. Historical goals may remain stored. Allowed current goal types are:

```text
RUNNING_MILEAGE
HALF_MARATHON
MARATHON
BOULDERING
LEAD_CLIMBING
```

Each goal has type, description, target value, target date, current status, and notes. It influences adaptation priority but does not disable supporting activities.

Running phase is one of `AEROBIC_BASE`, `VOLUME_BUILD`, `THRESHOLD_BUILD`, `HALF_MARATHON_SPECIFIC`, `MARATHON_SPECIFIC`, `TAPER`, or `RECOVERY_TRANSITION`.

Climbing phase is one of `TECHNIQUE_VOLUME`, `LIMIT_BOULDERING`, `MAX_STRENGTH`, `POWER`, `POWER_ENDURANCE`, `LEAD_SPECIFIC`, `PERFORMANCE`, or `RECOVERY`.

The phases are independent and manually editable. AI may recommend a phase change but cannot apply it silently.

## Navigation and page acceptance

### 1. Today / Coach

This is the default landing page. It shows the date, separate running and climbing readiness, today's planned sessions, relevant fatigue warning, current primary goal, and both phases. Primary actions are Complete Workout, Import Screenshot, Quick Log, Adapt Plan, and Recovery Check-In.

After a confirmed completion, the application saves the workout, updates athlete state, load, latent fatigue, readiness, planned-versus-actual analysis, and a bounded seven-day adaptation proposal. A provider failure may omit AI commentary but cannot lose the workout or deterministic update.

### 2. Calendar

The weekly calendar visually distinguishes planned, completed, modified, skipped, moved, replaced, and rest entries. Completed sessions can link to their plan; extras have no link. Original planned sessions remain available after moves or replacements.

### 3. Athlete State

The page has exactly two primary sections: Running and Climbing.

Running shows current and previous calendar-month mileage, rolling 7- and 28-day mileage, the 28-day weekly average (`distance / 4`), 10K estimate with evidence/confidence, LT1 range, LT2 estimate, and current phase. Calendar and rolling windows are never conflated. Insufficient estimate evidence displays `Not enough data`.

Climbing shows current phase, angle-specific TB2 verified and estimated benchmarks, current home-gym set completion, hardest current colour, set history, and a simple route benchmark. It does not collapse these into one climbing score.

### 4. Load & Readiness

The page shows sRPE load trends, the six fatigue domains, decayed component values, optional recovery evidence, and separate Running and Climbing readiness. The primary labels are GOOD, MODERATE, and LOW; underlying numeric components and heuristic explanations can be inspected.

### 5. Progress

This retrospective page never changes a plan. Running views include calendar-month mileage, rolling 7-day volume, rolling 28-day weekly average, estimated 10K confidence timeline, LT2 pace/HR, and comparable easy-running efficiency. Climbing views include verified TB2 grade labels and home-gym set pyramids with absolute sends and completion percentage when denominators are known. Filters are 4 weeks, 3 months, 6 months, and 1 year.

Environmental or workout-condition mismatch is disclosed when an efficiency comparison is weak.

### 6. Workout Log

The log supports `RUNNING`, `CLIMBING`, `STRENGTH`, `CROSSFIT_CONDITIONING`, and `MOBILITY_RECOVERY`. Common fields are date, start time, duration, RPE, notes, and optional planned-session linkage.

Displayed durations use `M:SS` below one hour and `H:MM:SS` from one hour upward. Manual workout, Calendar, and reviewed AI-import duration fields accept either form; a plain number remains a convenient total-minutes input. Running baseline and race-goal times use the same clock input, so the athlete never has to calculate total seconds.

Running supports Easy, Recovery, Long Run, Steady, Progression, Threshold, Tempo, Cruise Intervals, VO2max, Intervals, Hill Repeats, Fartlek, Strides, HM Pace, Marathon Pace, Time Trial, and Race. Fields include distance, duration, average pace/HR, maximum HR, elevation, cadence, power, RPE, splits, intervals, and notes. Interval blocks can represent warm-up, repeats, target, recovery, and cool-down.

Climbing supports Bouldering, Tension Board, Sport/Lead, Top Rope, Technique, Limit Bouldering, Power, Power Endurance, Easy Volume, and Outdoor. Quick session fields include location, duration, session type, RPE, hard attempts, maximum attempted/sent grade or colour, and notes. Problem details and style tags are optional.

Strength supports exercise, sets, reps, load, RPE, RIR, duration, and notes. Exercise tags include weighted pull-up, pull-up, one-arm progression, squat, deadlift, bench, overhead press, row, hangboard, core, and custom. Conditioning can record workout name, exercises, rounds, reps, time, load, and RPE.

Optional AI analysis for one completed workout is a single athlete-facing summary of at most 200
Unicode characters. It highlights only the most useful execution or recovery point and does not
repeat the detailed metrics already shown in the workout record.

Quick text entry accepts typed text or an optional browser-recorded voice transcription. Both
paths insert editable text before the normal extraction preview and confirmation. Completed
records can be permanently deleted only after an explicit irreversible confirmation. Deletion
removes the record from calculations and planning evidence and cannot be restored.

### 7. Training Notes

Every note belongs to exactly one of `RUNNING`, `CLIMBING`, or `STRENGTH_MOBILITY`. It stores raw and cleaned content, summary, takeaways, actionable ideas, tags, optional source metadata, input type, classification confidence, and `use_for_coaching`.

The athlete can override classification, edit AI output before save, search text, filter category/tags, and sort by date. Three category views remain obvious. Favorites are optional. This is a focused notebook, not a Notion replacement.

Voice capture uses browser MediaRecorder and backend transcription. Chinese, English, mixed speech, and terms such as LT1, LT2, threshold, VO2max, TB2, heel hook, max hangs, power endurance, and RPE are supported. Raw audio is deleted after successful transcription unless local retention is enabled.

### 8. Weekly Review

The review reports total training time, running distance, climbing duration, strength-session count, rest days, planned/completed/modified/skipped/extra compliance, running quality and long-run evidence, climbing hard attempts/set progress/benchmarks, recovery trends, evidence-based findings, and concrete next-week recommendations. Basic sleep, hydration, fueling, and recovery suggestions are allowed; injury or disease diagnosis is not.

### 9. Settings

Settings edits the athlete profile, current goal, running/climbing phase, gym name and colour system, configurable training-engine heuristics, AI model configuration status, media-retention preferences, demo data, and backup/restore/export. Secrets are environment-only and are never displayed back to the browser.

## Climbing benchmarks and gym-set lifecycle

TB2 entries contain date, board, angle, verified grade, estimated grade, and notes. Benchmarks are expected about every eight weeks but are not forged or auto-entered. Different angles stay distinguishable. Verified grade drives the primary chart; estimates may appear separately. Fontainebleau and V-scale ordinals only sort labels and place chart points.

The configurable home-gym colour order defaults to Yellow, Green, Purple, Grey, Blue, Red, Black with ordinals 1–7. Ordinals never calculate training load.

`New Set` closes the previous set when appropriate and creates a new immutable set with every colour at zero. Each colour tracks `sent_count` and optional `available_problem_count`; completion percentage appears only when a valid denominator exists. Removing a current set is not a shortcut for deleting history.

Route benchmark data remains limited to top-rope verified grade, lead verified grade, target grade, and last-updated time.

## Import and confirmation workflows

Screenshot import accepts Garmin Connect, Strava, and comparable activity screenshots. The backend vision function may extract activity type, date, distance, duration, pace, HR, elevation, splits, intervals, cadence, and power. Each extracted field contains value, confidence, and source; unseen fields are `null`.

Natural-language quick entry accepts Chinese, English, and mixed input and produces the same kind of structured preview. Neither workflow writes a completed workout until the athlete corrects and confirms it. Raw screenshots are deleted after successful extraction by default.

## Plan adaptation

Adaptation compares the planned and completed session using current goal, phases, athlete state, recent workload, six-domain fatigue, readiness, execution, and the next seven days. Output action is exactly one of:

```text
KEEP
REDUCE_VOLUME
REDUCE_INTENSITY
MOVE
REPLACE
ADD_RECOVERY
PROGRESS
```

The proposal shows old plan, new plan, action, reason, evidence, and confidence, with Apply, Reject, and Edit controls. The event history stores timestamp, affected session, both plan versions, action, reason, evidence, confidence, source (`RULE_ENGINE`, `AI`, or `MANUAL`), and disposition.

The engine does not move missed easy mileage automatically. It does not infer a new level from one exceptional performance. Important progression normally requires at least two comparable successful sessions with target RPE, stable readiness, no persistent relevant soreness, and no major execution failure. Progression changes one main variable at a time.

## Data durability

Full backup is versioned JSON. Useful tabular exports are CSV. Restore validates schema and references before a transactional import. Neither plan changes, gym resets, state updates, nor benchmark updates destroy history.

Demo data is an optional, labelled, removable dataset containing several useful weeks: easy and long runs, intervals, bouldering and TB2, strength, recovery, a high-fatigue climbing session, an adaptation event, and training notes.

## Delivery priority

P0 is the local app, SQLite/migrations, profile/goals, calendar/plans, workout logging, both athlete states, TB2 and gym sets, load/fatigue/readiness, progress, deterministic adaptation, note text input, and backup.

P1 is required before the project is called complete: screenshot and text extraction, voice notes, AI note processing, completed-session analysis, visible adaptation proposals/history, and weekly review.

P2 covers additional polish, advanced analytics, richer note search, PWA improvements, and optional athlete-approved coaching principles.

## Release acceptance

- Frontend build, strict TypeScript check, frontend tests, backend tests, lint, and fresh-database migration test pass.
- AI tests use mocks and no live key.
- A smoke test creates an athlete and planned run, completes it, calculates load/readiness, and displays progress.
- A smoke test creates a gym set, records colour sends, and displays climbing state.
- A smoke test creates, classifies, edits, saves, and searches a training note.
- Missing API keys, transcription/extraction failures, invalid workout data, missing HR/RPE, and database errors are handled without fabricated success.
