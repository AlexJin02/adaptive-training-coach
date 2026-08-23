# Adaptive Running & Climbing Training Coach

A local-first training application for one athlete who trains running and climbing concurrently. It records what was planned and what actually happened, calculates transparent workload and fatigue heuristics, maintains separate running and climbing readiness, shows long-term progress, and proposes conservative changes to the next seven days.

This is not a medical device and it does not produce a hidden "AI fitness score." Calculations and adaptation evidence remain inspectable, and no proposal changes the plan until the athlete accepts it.

This README describes the checked-in runtime. [Product specification](docs/product-spec.md) is the normative V1 acceptance contract; where it is more ambitious than the implementation, the implementation-status notes in [AI contracts](docs/ai-contracts.md), [data model](docs/data-model.md), and [training engine](docs/training-engine.md) take precedence as a statement of current behavior.

## What it covers

- Today / Coach dashboard, weekly calendar, planned sessions, and fast workout logging
- Running state, volume, race estimates, LT1/LT2 evidence, and progression charts
- Climbing state, angle-aware Tension Board 2 benchmarks, home-gym set history, and route benchmarks
- Session-RPE load, six-domain decaying fatigue, recovery check-ins, and sport-specific readiness
- Deterministic plan comparison and constrained adaptation proposals with revision/decision history
- Screenshot and natural-language workout extraction with preview-before-save
- Text and voice Training Notes, structured into Running, Climbing, or Strength & Mobility
- Weekly reviews, versioned JSON backup/restore, CSV export, and removable demo data

Strength, CrossFit/conditioning, and mobility are supporting activities. They affect fatigue but do not have their own goal, athlete-state, readiness, or progress dashboard.

## Architecture

The browser client is React, strict TypeScript, and Vite. The local API is FastAPI with Pydantic schemas, a layered service and deterministic training engine, SQLAlchemy persistence, Alembic migrations, and SQLite. OpenAI integrations are optional backend adapters.

```text
frontend/                         backend/
  React pages and components       app/api.py           HTTP boundary
  typed API client                 app/services/        use cases
  views and preview arithmetic     app/training_engine/ deterministic rules
                                    app/ai/              optional provider calls
                                    app/models.py, db.py relational persistence

backend/data/training_coach.db    local data (not committed)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) and the contracts in [docs/](docs/).

## Requirements

- Python 3.11 or newer
- Node.js 20.19+ (or 22.12+) and pnpm 11
- GNU Make
- SQLite support in Python
- Optional: an OpenAI API key for image, language, transcription, and AI coaching workflows
- Optional: GitHub CLI (`gh`) for repository creation and push

## Install and run

From the repository root:

```bash
cp .env.example .env
make install
make dev
```

`make dev` applies local migrations, starts FastAPI at `http://127.0.0.1:8000`, and starts Vite at `http://127.0.0.1:5173`. Stop both with `Ctrl-C`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

The SQLite database is stored at:

```text
backend/data/training_coach.db
```

`make migrate` safely adopts the recognised unversioned SQLite schema produced by early
`create_all` builds. It writes and verifies a timestamped `*.pre-alembic-*.bak` beside the
database before changing schema or stamping a revision. Unknown schema drift, or legacy RPE
values that cannot be preserved under the current constraints, stop the migration without a
stamp.

Useful commands:

```bash
make migrate       # apply Alembic migrations
make dev           # run backend and frontend together
make test          # full verification suite
make backend-test  # pytest only
make frontend-test # Vitest only
make build         # production frontend build
make lint          # backend and frontend lint
make clean         # remove generated caches/build output, not athlete data
```

## Environment configuration

`.env.example` documents the supported day-to-day local settings. `.env` is ignored by Git.

| Variable | Purpose | Default behaviour |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy SQLite URL | Resolves to `backend/data/training_coach.db` |
| `VITE_API_BASE_URL` | Browser API base | `http://127.0.0.1:8000/api/v1` |
| `CORS_ORIGINS` | JSON array of allowed browser origins | Vite localhost origins |
| `OPENAI_API_KEY` | Optional provider credential | AI features report unavailable when blank |
| `OPENAI_MODEL` | Text analysis/coaching model | Chosen in backend configuration |
| `OPENAI_VISION_MODEL` | Screenshot extraction model | Chosen in backend configuration |
| `OPENAI_TRANSCRIBE_MODEL` | Voice transcription model | Chosen in backend configuration |
| `RETAIN_RAW_SCREENSHOTS` | Retain uploaded screenshots locally | `false` |
| `RETAIN_RAW_AUDIO` | Retain uploaded voice-note audio locally | `false` |
| `LOAD_DEMO_DATA` | Explicitly enable demo-data loading | `false` |

Do not put API keys in frontend variables, source files, screenshots, commits, or backups. Core training features do not require a key.

## AI-assisted workflows

All provider calls run on the backend. The application has separate typed functions for image extraction, text extraction, transcription, note processing, completed-session analysis, plan adaptation, and weekly review instead of one universal prompt.

Workout import always follows:

```text
Extract -> structured preview -> athlete correction -> confirmation -> save
```

Unknown extraction values remain `null`; extracted workout fields retain confidence and source metadata. Screenshot and raw-audio retention is off by default. A failed file request may leave a `media_imports` audit row, but it does not create a completed workout or note and cannot edit the plan.

Voice notes use the browser `MediaRecorder` and send audio only to the configured transcription provider. The transcription prompt is tuned for Chinese, English, and mixed running/climbing terminology. The transcript and organised note are editable before saving.

Training Notes are advisory knowledge, not measured evidence. `use_for_coaching` is false by default, and enabling it only makes the note eligible for a bounded AI context; it does not turn the note into a deterministic rule.

## Testing

Run the complete local suite with one command:

```bash
make test
```

The command is wired to run backend unit/integration tests, mocked AI-contract tests, frontend tests, TypeScript type-checking, backend/frontend linting, a production build, and an Alembic upgrade smoke test against a temporary database. Tests never require a live API key. Treat a release as verified only after this command exits successfully in the current checkout.

The automated suite includes the required running, climbing, concurrent-strength-interference, mixed-language note-classification, and note-safety scenarios. See [docs/training-engine.md](docs/training-engine.md) for expected rule behaviour.

## Backup, restore, and export

Use Settings to create a versioned full JSON backup, restore a compatible backup after validation, or export useful training tables as CSV. Backups include durable athlete data and omit secrets and temporary raw media. Restore is transactional: validation failure leaves the current database unchanged. Keep exported files somewhere outside `backend/data/` if they need independent retention.

Plan edits preserve revision snapshots, moves/replacements retain the original plan, and gym-set and benchmark updates append historical rows. Running estimates and load/readiness snapshots are also append-only evidence. Profile/settings fields are current-value records unless a dedicated history table is present. Never use a copied SQLite file while the app is writing to it as a substitute for the supported backup flow.

## Demo data

Demo data is opt-in, visibly labelled, and removable without deleting real athlete records. It contains several weeks of running, climbing, TB2, strength, recovery, adaptation, and note examples so charts can be evaluated immediately. It is never silently loaded in a normal profile.

## GitHub workflow

The intended private repository is `AlexJin02/adaptive-training-coach` on the `main` branch. Before creating or pushing it:

```bash
gh auth status
gh repo view AlexJin02/adaptive-training-coach
```

If it does not exist and authentication is available:

```bash
gh repo create AlexJin02/adaptive-training-coach --private --source=. --remote=origin
git branch -M main
git push -u origin main
gh repo view AlexJin02/adaptive-training-coach
```

Do not report repository creation or push success until the final `gh repo view` succeeds. GitHub authentication failure does not block local development, tests, or a local commit.

## Known limitations

- V1 uses screenshots and manual input rather than Garmin or Strava OAuth.
- V1 is a single-athlete, trusted-host application with no user authentication. Both servers bind to loopback, and browser writes require a trusted Origin, but loopback does not isolate other accounts or processes on a shared computer. Do not run it on an untrusted multi-user host.
- File handlers enforce MIME/signature checks and 10 MiB screenshot / 25 MiB audio or restore limits after multipart parsing. An untrusted local process could still consume temporary-disk space while the web framework spools a request; this is another reason the V1 host must be trusted.
- Load normalization, fatigue half-lives, and readiness thresholds are editable planning heuristics, not measurements or medical advice. Mileage progression bands and demand profiles remain V1 code configuration.
- LT1, LT2, and 10K estimates depend on available evidence and may intentionally display `Not enough data`.
- Climbing grades are ordinal labels for sorting and chart placement; distances between grades are not treated as linear physiology.
- The coach can flag soreness and recommend conservative training changes, but it does not diagnose injury or disease.
