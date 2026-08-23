# Deterministic training engine

## Purpose and guarantees

The training engine turns completed training and optional recovery input into auditable planning signals. It is deterministic, replayable, configuration-driven, and independent of HTTP, ORM, UI, and AI provider code.

Its values are engineering heuristics. The UI and API must not label arbitrary units as exact physiological stress or readiness as a medical measurement.

Pure fatigue output carries an evaluation time, and persisted stress/snapshot rows carry the V1 algorithm label. The service recomputes current fatigue from all stored session-domain stresses at each read, so an appended backdated session participates in chronological replay. The current API does not expose completed-session editing, snapshot invalidation, or a versioned runtime-setting history; those remain requirements for a future edit/recalculation workflow.

## Units and missing data

- Completed and planned duration is stored in minutes.
- Running distance is stored in kilometres.
- Running pace is stored as seconds per kilometre. The service derives it from distance and duration when no parseable pace is supplied; V1 does not separately retain an imported display string/source.
- RPE uses a 1–10 scale in the UI, request model, engine, and database constraint. A missing RPE remains `null`.
- Heart rate, power, cadence, elevation, splits, intervals, hard attempts, and local soreness are optional.
- Positive duration is required to save a completed session. A session without RPE is saved as evidence with `sRPE_load = null`; it does not invent a fatigue input and is visibly marked load-incomplete.

## Session-RPE load

For a session with duration and RPE:

```text
sRPE_load = duration_minutes * RPE
base_stress = min(10, sRPE_load / 90)
```

`sRPE_load` is preserved as a longitudinal arbitrary-unit measure. `base_stress` is the configurable normalized input for domain mapping.

For each domain:

```text
session_domain_stress = base_stress * domain_coefficient * applicable_multiplier
```

The six and only six V1 fatigue domains are:

```text
CARDIOVASCULAR
LOWER_BODY
FINGER_FOREARM
PULLING_UPPER_BODY
NEURAL
SYSTEMIC
```

## Default fatigue mappings

Mappings live in the versioned V1 code configuration in `training_engine/config.py`. Unlisted coefficients are zero. Workout labels map to a documented profile rather than duplicating numbers throughout routes or components; profile coefficients are not editable through Settings in this revision.

| Profile | Cardio | Lower | Finger | Pulling | Neural | Systemic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy run | 0.70 | 0.60 | 0 | 0 | 0.10 | 0.30 |
| Long run | 0.90 | 0.90 | 0 | 0 | 0.20 | 0.60 |
| Threshold | 1.00 | 0.80 | 0 | 0 | 0.40 | 0.60 |
| VO2 / hard intervals | 1.00 | 0.90 | 0 | 0 | 0.60 | 0.70 |
| Easy technique / climbing volume | 0 | 0 | 0.35 | 0.40 | 0.20 | 0.20 |
| Limit bouldering | 0 | 0 | 1.00 | 0.90 | 1.00 | 0.50 |
| Board power | 0 | 0 | 0.90 | 0.90 | 1.00 | 0.50 |
| Power endurance | 0 | 0 | 0.80 | 0.80 | 0.50 | 0.70 |

Other running and climbing session types use an explicit configuration alias or their own configured row. They never fall through to an undocumented high-intensity default.

For limit, board-power, or other hard-attempt climbing profiles, the default multiplier is:

```text
hard_attempt_multiplier = min(1.25, 1 + max(0, hard_attempts - 10) * 0.015)
```

It applies only to `FINGER_FOREARM` and `NEURAL`; missing hard attempts means 1.0. Duration and RPE remain the dominant input.

Strength profiles are built from exercise names/tags. Weighted pull-ups target finger, pulling, and neural domains; max hangs target finger and neural; heavy squat targets lower, neural, and systemic; deadlift targets lower, pulling, neural, and systemic; core has only low systemic contribution. A session takes the maximum coefficient per domain across matched exercises, without creating strength readiness. These profiles are versioned V1 code configuration rather than editable runtime rows.

## Fatigue decay

The conceptual sequential form evaluates session events chronologically. Before adding an event at time `t`:

```text
remaining_fatigue = previous_latent_fatigue * 0.5 ^ (elapsed_hours / half_life_hours)
new_latent_fatigue = remaining_fatigue + session_domain_stress
```

The implementation uses the mathematically equivalent closed form: decay every historical stress directly to the evaluation time and sum it. This makes input order irrelevant while preserving the same exponential result. Never cap latent fatigue before the final sum is stored or used for readiness. The display value is:

```text
display_fatigue = min(10, max(0, latent_fatigue))
```

Default half-lives are:

| Domain | Half-life |
| --- | ---: |
| CARDIOVASCULAR | 18 h |
| LOWER_BODY | 30 h |
| FINGER_FOREARM | 36 h |
| PULLING_UPPER_BODY | 30 h |
| NEURAL | 24 h |
| SYSTEMIC | 18 h |

They are editable planning heuristics, not biological constants. Elapsed time is calculated in UTC after parsing athlete-local timestamps; daylight-saving changes therefore do not distort decay.

Fatigue labels use Low below 3.0, Moderate from 3.0 to 7.49, High from 7.5 to 8.99, and Very High at 9.0 or above. Each fatigue-domain API item returns this engine-owned `display_label` plus `is_high`; React does not reproduce the thresholds. The adaptation engine uses the same 7.5 high-conflict and 9.0 very-high-conflict gates. Readiness uses the separate thresholds below.

## Recovery modifier

The latest check-in no more than 36 hours old may modify readiness. Inputs are normalized to `[-1, 1]`:

```text
sleep_duration = clamp((hours - 7) / 2, -1, 1)
sleep_quality  = (quality_1_to_5 - 3) / 2
energy         = (energy_1_to_5 - 3) / 2
inverse_stress = (3 - stress_1_to_5) / 2
inverse_soreness = (5 - general_soreness_0_to_10) / 5
```

Use only present values and renormalize their weights rather than treating missing data as average recovery:

```text
weighted_mean = sum(normalized_value * present_weight) / sum(present_weight)

weights:
  sleep duration    0.20
  sleep quality     0.20
  energy            0.25
  inverse stress    0.15
  inverse soreness  0.20

subjective_modifier = clamp(weighted_mean, -1.0, +0.75)
```

No applicable data means a modifier of zero. Motivation is stored and displayed but is not part of the V1 default modifier. Resting HR and HRV likewise remain evidence-only until an athlete-specific baseline and explicitly enabled, tested configuration exist.

## Running readiness

Using latent domain values decayed to the evaluation time:

```text
running_fatigue =
    0.35 * CARDIOVASCULAR
  + 0.35 * LOWER_BODY
  + 0.20 * SYSTEMIC
  + 0.10 * NEURAL

running_readiness = clamp(0, 10, 10 - running_fatigue + subjective_modifier)
```

## Climbing readiness

```text
climbing_fatigue =
    0.40 * FINGER_FOREARM
  + 0.25 * PULLING_UPPER_BODY
  + 0.20 * NEURAL
  + 0.15 * SYSTEMIC

local_soreness_penalty =
    0.20 * finger_soreness
  + 0.10 * elbow_soreness
  + 0.10 * shoulder_soreness

climbing_readiness = clamp(
  0,
  10,
  10 - climbing_fatigue + subjective_modifier - local_soreness_penalty
)
```

Local soreness adds conservative gates after the general modifier:

- Finger soreness 3–5 caps finger-intensive readiness at MODERATE and blocks `PROGRESS`.
- Finger soreness 6–10 caps finger-intensive readiness at LOW and makes the session eligible only for `MOVE`, `REPLACE`, or reduced intensity/volume.
- High elbow or shoulder soreness contributes through the local penalty and blocks progression when the planned session stresses that area.
- Missing local soreness does not imply zero soreness; it simply adds no subjective signal.

The numeric result maps to the primary UI label:

```text
>= 7.5       GOOD
5.0–7.49     MODERATE
< 5.0        LOW
```

The API returns component values, labels, update time, and a short explanation so the UI can show why. It also exposes the bounded `subjective_delta`, `local_soreness_penalty`, warnings, and a `LOCAL_SORENESS` climbing component. A MODERATE cap caused by finger soreness is therefore auditable instead of appearing as an unexplained label. Persisted snapshot rows retain the subjective delta, warnings/components, and V1 algorithm label; the public readiness response does not currently expose a separate runtime-configuration version.

## Running athlete-state calculations

Calendar-month mileage sums completed running distance whose athlete-local date is within the named month. Rolling windows use the evaluation instant and completed-session timestamps:

```text
rolling_28d_weekly_average = distance_last_28_days / 4
```

Current month, previous month, rolling 7-day, and rolling 28-day values remain separate.

A 10K race-equivalent may use Riegel when evidence is suitable:

```text
target_time = source_time * (target_distance / source_distance) ^ 1.06
```

The implemented estimator appends evidence for a 3–50 km `Race` or `Time Trial`. It records an actual result for 9.95–10.05 km and otherwise applies Riegel with high confidence; an actual 10K from the last 90 days overrides other estimates. Repeated quality-session inference is not implemented. With no eligible event, time is `null` and display text is `Not enough data`.

The implemented LT2 row is appended from a completed Threshold, Tempo, or Cruise Intervals session when pace or heart rate is present. LT1 is derived only after at least three recent Easy, Recovery, or Steady sessions at RPE 4 or lower contain both pace and heart rate; it stores the observed pace/HR ranges with moderate confidence. Typed API endpoints can also append manual 10K and LT1/LT2 evidence. A Garmin-specific import path and AI-assisted estimate source are not implemented.

Easy-efficiency trends use Easy/Recovery runs within ±3 bpm of the median easy-run heart rate and require at least three comparable points. The UI always warns that weather, terrain, and workout conditions may differ; it does not yet test those metadata fields automatically.

## Climbing state calculations

TB2 progress uses verified grades at the same board and preserves angle in every point. Estimated grades are a separate series. Grade ordinals only sort and position labels; subtraction, averaging, and percentage improvement between ordinals are forbidden.

Home-gym colour ordinals likewise only order categories and identify the hardest colour with `sent_count > 0`. For a valid available count:

```text
completion_rate = sent_count / available_problem_count
```

An absent denominator produces no percentage. New sets start all colours at zero and never alter previous sets.

## Weekly-review evidence bounds

Weekly compliance treats `REST`, superseded `MOVED`, and superseded `REPLACED` rows as calendar
history rather than planned training in the denominator. A linked completion can overwrite the
current plan status with `COMPLETED`, so the review compares append-only plan revisions to preserve
a `modified` outcome; status-only skip history does not become a modification.

Historical climbing summaries select only a gym-set lifecycle that covers the review's
`week_end`; a future/current active set cannot leak into an older review. The optional AI context
uses four fixed seven-day buckets ending at `week_end`, with running distance/session count,
climbing time/hard attempts/session count, and sRPE/base-stress load trends.

## Mileage progression

The engine represents current capacity, current block target, and long-term goal separately. It chooses `BUILD`, `HOLD`, or `DELOAD`; it never applies a blind 10% rule.

`BUILD` requires at least 85% recent plan completion, stable easy-run RPE, a tolerated recent long run, stable comparable quality-session performance, no high recent relevant soreness, and acceptable readiness. Structured quality work uses the execution contract below; unstructured quality work requires two comparable successful sessions with pace within 3%, heart rate within 8 bpm, and readiness within 2 points. Missing quality evidence produces `HOLD`, not an inferred success. Holding multiple weeks is valid. The V1 code bands are +5–8% below 40 km/week, +3–6% from 40–70, and +2–4% above 70. They are ceilings, not quotas; they are not editable through Settings in this revision.

The running-state response exposes the recent longest run as a soft guardrail. When the adaptation engine progresses an existing long-run plan, proposed distance is capped at 110% of the longest completed long run in the prior 42 days. If the existing plan is already at or above that cap, the action remains `KEEP`.

## Adaptation rules and precedence

The deterministic service supplies the primary goal, both phases, comparable recent work, fatigue/readiness, planned-versus-actual execution, and the next seven days. In a non-emergency conflict involving several candidates, it protects current-goal-aligned and HIGH-priority work by adjusting a supporting candidate first. LOW readiness and very-high fatigue remain safety overrides and can still change a goal-aligned session. The action enum is constrained to `KEEP`, `REDUCE_VOLUME`, `REDUCE_INTENSITY`, `MOVE`, `REPLACE`, `ADD_RECOVERY`, or `PROGRESS`; current rule branches emit every listed action except `ADD_RECOVERY`, which is reserved for a future explicit rule.

Rules execute in conservative precedence:

1. Local soreness and very-high domain conflict prevent progression and may move or replace a risky session.
2. LOW sport readiness before a hard running/climbing session triggers schedule inspection and possible move/replacement, regardless of its priority label.
3. Supporting strength interference is checked for both relevant sports; deadlifts can conflict with lower-body running and weighted pull-ups with climbing pulling/finger work.
4. Unexpectedly high RPE, incomplete execution, or poor recovery causes the next hard session to be evaluated.
5. Missed easy mileage is not automatically moved to the next day.
6. A single exceptional session remains `KEEP` unless a safety rule requires reduction.
7. `PROGRESS` is eligible only after at least two comparable successful sessions, target RPE, pre-session readiness of at least MODERATE with a maximum two-point spread, no demand-overlapping soreness, and no major execution failure.

For structured interval evidence, a planned main block may provide `repetitions`, `work_minutes`, `recovery_minutes`, `target_pace_seconds_per_km`, and `target_hr_max`. Numeric fields take precedence, while descriptions such as `4 × 8 min @ 4:15/km, HR <= 172, 2 min recovery` are parsed as a backwards-compatible input. Completed work may provide per-rep pace/HR in `interval_blocks`; pace and HR can fall back to explicit lap `splits`. Missing measurements stay unknown.

A structured execution is strong only when all planned reps are recorded faster than target, work-rep HR remains within its target, RPE/readiness pass, and late-half pace is no more than 3% slower than early-half pace. Completing fewer than 75% of planned reps or slowing by more than 10% is a major failure. One strong execution remains `KEEP`; two chronologically comparable strong executions with readiness spread no greater than 2 points may progress. A recognised `4 × 8 min` threshold block becomes `3 × 12 min`, preserving pace, HR, and recovery targets. That is a single volume-variable change. Other plans use the safe duration-by-5% or distance-by-3% fallback. AI can explain a deterministic-safe action but cannot replace its action or patch, introduce another action, or bypass a gate.

## Required deterministic scenarios

- A hard interval session above target with moderate RPE is recognised as strong execution but does not cause a large immediate progression.
- Two comparable successful quality sessions with stable readiness may unlock `PROGRESS`.
- A missed easy run does not add mileage to tomorrow.
- An easy run with unexpectedly high RPE and poor recovery flags fatigue and evaluates the next hard session.
- A 145-minute limit session at RPE 9 with many hard attempts produces high/very-high finger and neural fatigue.
- Max hangs the next day produce `MOVE`, `REPLACE`, `REDUCE_VOLUME`, or `REDUCE_INTENSITY`, never unrestricted `REDUCE`.
- Heavy deadlifts and weighted pull-ups before important sessions detect lower-body and pulling interference respectively.
- A dramatic note recommendation cannot affect the engine while `use_for_coaching` is false.

Scenario tests use fixed dates/times where chronology matters and the checked-in V1 configuration. They run without a provider or API key.
