# ATLAS

A local-first, AI-native solo roleplaying engine. The authoritative world lives
in SQLite as typed state plus an append-only event ledger; language models may
propose, but only validated domain code mutates state.

**Current status: milestone M0.** The repository contains a tested offline
vertical slice: migrations, seeded campaign, typed commands, deterministic
seeded 2d6 rolls, transactional turns, event replay, state hashing, checkpoints,
a fake model provider, a minimal API, and a command-line demo. M0 does not use
an LLM and does not implement the M1 turn lifecycle, AI narration, or the
frontend.

## Requirements

- macOS or Linux with Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (recommended; `brew install uv`)

## Setup

```bash
uv python install 3.12
uv sync --group dev
uv run alembic upgrade head
```

No cloud account or API key is required. Copy `.env.example` to `.env` only when
you need to override defaults.

## Offline demo

```bash
uv run python scripts/offline_turn.py --db data/m0_demo.db --reset
```

The script migrates the database, seeds **The Broken Span**, commits one
deterministic action, verifies replay equality, reopens the database to prove
restart persistence, and writes a checkpoint. Run it again without `--reset` to
see idempotent replay of the same client action.

## Development commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run uvicorn atlas.main:app --reload
```

`GET /healthz` reports application/database status. `POST /api/v1/campaigns`
seeds a new Broken Span campaign; `GET /api/v1/campaigns` lists campaigns.

## Layout

```text
backend/atlas/        application package
  api/                FastAPI routes
  domain/             IDs, models, events, commands, rules, projections
  game/               scripted offline turn service
  models/             provider-neutral gateway + deterministic fake
  persistence/        SQLAlchemy tables, repositories, replay, migrations
  seed/               structured world fixtures
migrations/           Alembic migrations
scripts/              offline demo and setup helpers
tests/                unit, integration, and end-to-end tests
docs/                 decisions, progress, data model, API notes
```

See `docs/PROGRESS.md` for exact tested commands, known limitations, and the
next milestone. See `docs/DECISIONS.md` for architectural choices made in M0.
