# Adaptive Training Coach: contributor guide

This file is a normative contributor contract, not an inventory of completed features. It
describes the boundaries that new work must preserve; use `README.md`, the current Alembic
migration, and the automated tests to verify what the checked-out revision actually implements.

## Product contract

This repository is a local-first, single-athlete running and climbing coach. Preserve the feedback loop:

`Plan -> Train -> Record -> Calculate Load -> Update Fatigue -> Update Readiness -> Analyse -> Adapt -> Review`

Running and climbing are the primary sports. Strength, conditioning, and mobility only contribute supporting workload and fatigue; do not add a separate strength goal, state, readiness, or progress product.

## Non-negotiable behaviour

- Keep measured training evidence separate from imported knowledge. A training note has `use_for_coaching = false` by default.
- Never let AI silently edit a phase or plan. AI output is a validated proposal with a visible diff and Apply, Reject, and Edit choices.
- Never save screenshot, natural-language, transcription, or note-processing output without a user preview and confirmation.
- Never fabricate missing values. Use `null`, an unavailable state, or `Not enough data`.
- Preserve history. Plan changes, gym resets, benchmarks, and state changes create new records or events rather than overwriting historical evidence.
- Keep deterministic calculations in `backend/app/training_engine/`; keep prompts and provider calls in `backend/app/ai/`; keep database access out of route handlers; keep calculations out of React components.
- Keep all OpenAI calls and secrets on the backend. Core logging, state, load, readiness, progress, and deterministic adaptation must work without an API key.
- Treat workload, fatigue, readiness, grade ordinals, and performance estimates as transparent planning heuristics, never medical or physiological facts.

## Repository boundaries

- `backend/`: FastAPI, Pydantic, SQLAlchemy, Alembic, deterministic engine, AI adapters, and SQLite persistence.
- `frontend/`: React, strict TypeScript, Vite, typed API client, and presentation only.
- `docs/`: durable product, engine, data, and AI contracts.
- `backend/data/training_coach.db`: local development database; never commit it.

Use configuration for fatigue coefficients, half-lives, model names, retention settings, thresholds, and other tunable heuristics. Do not scatter constants through routes or components.

## Development workflow

1. Copy `.env.example` to `.env` and set only the providers you intend to use.
2. Run `make install` once, then `make dev` for both services.
3. Run `make test` before handoff. It covers backend tests, frontend tests, type-checking, lint, build, and a migration smoke test.
4. Add Alembic migrations for schema changes; never edit a developer's local SQLite database directly as a substitute.
5. Mock AI provider calls in automated tests. No test may require a live API key or network access.

Prefer small services with typed inputs and outputs. Add regression tests for training-rule changes, especially chronological fatigue decay, progression gates, plan-history preservation, and note/coaching separation.

## Git hygiene

Preserve unrelated work in a dirty tree. Do not commit `.env`, databases, raw media, backups, caches, or coverage output. Use `main` as the primary branch and do not claim a push, repository creation, migration, test, or AI action succeeded unless it was actually verified.
