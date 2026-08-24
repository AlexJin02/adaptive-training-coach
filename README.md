# Adaptive Running & Climbing Training Coach

A local-first factual training log for one athlete who runs and climbs. It preserves detailed completed sessions, shows descriptive progress, exports stable weekly/monthly Markdown reports, and deterministically imports externally generated plans into Calendar.

The application is deliberately not an autonomous coach. It does not turn duration and RPE into load, fatigue, readiness, or recovery scores. A Web AI can analyse exported reports and return a plan using the supplied fixed template; the app validates and previews that plan before importing it.

This README describes the checked-in runtime. [Product specification](docs/product-spec.md) is the normative V1 acceptance contract; where it is more ambitious than the implementation, the implementation-status notes in [AI contracts](docs/ai-contracts.md), [data model](docs/data-model.md), and [training engine](docs/training-engine.md) take precedence as a statement of current behavior.

## What it covers

- Today's Training as the home view, weekly Calendar, editable planned sessions, and a filterable factual workout history
- Running state, transparent volume trends, and comparable-HR easy-running efficiency
- Climbing state, angle-aware Tension Board 2 benchmarks, home-gym set history, and route benchmarks
- Strict running types (`EASY`, `LONG_RUN`, `QUALITY`, `RACE`) and climbing types (`BOULDERING`, `SPORT_CLIMBING`, `BOARD`)
- Screenshot, natural-language, and voice-assisted workout entry with preview-before-save
- Optional Strava running sync into a review Inbox with planned-session matching and lap detail
- Text and voice Training Notes, structured into Running, Climbing, or Strength & Mobility
- Fixed `TRAINING_WEEKLY_REPORT_V1` and `TRAINING_MONTHLY_REPORT_V1` Markdown exports
- Deterministic `TRAINING_WEEKLY_PLAN_V1` and `TRAINING_MONTHLY_PLAN_V1` preview/import, with a structured readable monthly-block view
- Versioned JSON backup/restore, CSV export, and removable demo data

Strength, CrossFit/conditioning, and mobility remain supporting factual records. They do not have a separate goal or analytical score.

## Architecture

The browser client is React, strict TypeScript, and Vite. The local API is FastAPI with Pydantic schemas, a layered service and deterministic training engine, SQLAlchemy persistence, Alembic migrations, and SQLite. OpenAI integrations are optional backend adapters.

```text
frontend/                         backend/
  React pages and components       app/api.py           HTTP boundary
  typed API client                 app/services/        use cases
  views and formatting             app/services/        reports and plan parser
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
make remote-server # build one-origin HTML and serve it on Mac for a private tunnel
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
| `VITE_API_BASE_URL` | Vite development API base | `http://127.0.0.1:8000/api/v1`; production builds always use same-origin `/api/v1` for phone access |
| `CORS_ORIGINS` | JSON array of allowed browser origins | Vite localhost origins |
| `OPENAI_API_KEY` | Optional provider credential | AI features report unavailable when blank |
| `OPENAI_MODEL` | Text analysis/coaching model | Chosen in backend configuration |
| `OPENAI_VISION_MODEL` | Screenshot extraction model | Chosen in backend configuration |
| `OPENAI_TRANSCRIBE_MODEL` | Voice transcription model | Chosen in backend configuration |
| `STRAVA_ACCESS_TOKEN` | Optional current Strava token | Enables manual Sync Strava from Run Inbox |
| `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` | Optional Strava refresh credentials | Backend refreshes access tokens in memory; secrets never reach the browser or backup |
| `RETAIN_RAW_SCREENSHOTS` | Retain uploaded screenshots locally | `false` |
| `RETAIN_RAW_AUDIO` | Retain uploaded voice-note audio locally | `false` |
| `LOAD_DEMO_DATA` | Explicitly enable demo-data loading | `false` |

Do not put API keys in frontend variables, source files, screenshots, commits, or backups. Core training features do not require a key.

## Private phone access

`make remote-server` builds the React application with a same-origin `/api/v1` base and serves
the HTML, assets, SPA routes, and API from FastAPI on `127.0.0.1:8000`. A private HTTPS tunnel
such as Tailscale Serve can proxy that single loopback service without exposing SQLite or a
development server directly to the LAN or public internet.

Install Tailscale on the Mac and phone, sign in to the same private tailnet, then configure the
Mac after adding its exact `https://<device>.<tailnet>.ts.net` URL to `CORS_ORIGINS`:

```bash
make remote-server
tailscale serve http://127.0.0.1:8000
```

Open the HTTPS URL printed by Tailscale on the phone. All reads and writes still use the SQLite
database on the Mac. The Mac must remain awake, connected to Tailscale, and running the server.
Use Tailscale **Serve**, not Funnel: Serve is private to the tailnet, while Funnel is public.

## Data and optional AI-assisted entry

All provider calls run on the backend. OpenAI is used only for optional screenshot/text extraction, transcription, and note organisation in the normal UI. Reports and pasted-plan parsing are deterministic and work without an API key.

Workout import always follows:

```text
Extract -> structured preview -> athlete correction -> confirmation -> save
```

Unknown extraction values remain `null`; extracted workout fields retain confidence and source metadata. Screenshot and raw-audio retention is off by default. A failed file request may leave a `media_imports` audit row, but it does not create a completed workout or note and cannot edit the plan.

Voice notes use the browser `MediaRecorder` and send audio only to the configured transcription provider. The transcription prompt is tuned for Chinese, English, and mixed running/climbing terminology. The transcript and organised note are editable before saving.

Strava sync is an optional backend-only import path. The Run Inbox fetches recent running
activities and available laps, deduplicates them by Strava activity ID, and tries to match an
uncompleted running plan on the same date. An imported run remains `needs_review` and does not
change Calendar until the athlete chooses its run type, adds RPE, optionally reviews voice/text
feedback, and presses **Save Completed Workout**. This release does not add an in-app Strava OAuth
connection screen; credentials are supplied through `.env`.

Training Notes are personal knowledge, not measured evidence. They do not change calculations or Calendar plans.

The external planning loop is:

```text
Training data -> fixed Markdown report -> Web AI -> fixed plan template -> preview -> Calendar
```

Weekly imports create detailed Calendar sessions. Monthly imports save one current training block and do not create a month of daily sessions.

## Testing

Run the complete local suite with one command:

```bash
make test
```

The command is wired to run backend unit/integration tests, mocked AI-contract tests, frontend tests, TypeScript type-checking, backend/frontend linting, a production build, and an Alembic upgrade smoke test against a temporary database. Tests never require a live API key. Treat a release as verified only after this command exits successfully in the current checkout.

The automated suite includes the required running, climbing, concurrent-strength-interference, mixed-language note-classification, and note-safety scenarios. See [docs/training-engine.md](docs/training-engine.md) for expected rule behaviour.

## Backup, restore, and export

Use Settings to create a versioned full JSON backup, restore a compatible backup after validation, or export useful training tables as CSV. Backups include durable athlete data and omit secrets and temporary raw media. Restore is transactional: validation failure leaves the current database unchanged. Keep exported files somewhere outside `backend/data/` if they need independent retention.

Plan edits preserve revision snapshots, deleted planned sessions are soft-cancelled, and gym-set and benchmark updates preserve history. Historical load/readiness tables from older versions remain migration-safe but are dormant in the simplified workflow. Profile/settings fields are current-value records unless a dedicated history table is present. Never use a copied SQLite file while the app is writing to it as a substitute for the supported backup flow.

## Demo data

Demo data is opt-in, visibly labelled, and removable without deleting real athlete records. It contains factual running, climbing, TB2, strength, and note examples so charts and reports can be evaluated immediately. It is never silently loaded in a normal profile.

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
- LT1 depends on available evidence and may intentionally display `Not enough data`. Progress deliberately omits race predictions and LT2 proxy charts.
- Climbing grades are ordinal labels for sorting and chart placement; distances between grades are not treated as linear physiology.
- Legacy engine tables and endpoints remain for migration and backup compatibility but are not part of normal navigation, session saving, reporting, or plan importing.
