# ATLAS

A local-first, AI-native solo roleplaying engine. The authoritative world lives
in SQLite as typed state plus an append-only event ledger; language models may
propose, but only validated domain code mutates state.

**Current status: milestone M1.** The repository contains a tested offline
vertical slice: migrations, a seeded campaign, typed commands, deterministic
seeded 2d6 rolls, a durable turn lifecycle, transactional turns, event replay,
state hashing, checkpoints, observations/journal, a deterministic
parser/adjudicator/fake narrator, a typed HTTP API, and a command-line demo. M1
does not call a live language model and does not implement the frontend or the
originality system.

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
uv run python scripts/m1_demo.py --db data/m1_demo.db --reset
```

The M1 demo migrates the database, seeds **The Broken Span**, plays twelve
deterministic text turns (look, travel, search, wait, talk), verifies exact
replay, and rechecks duplicate-request idempotency. Run it again without
`--reset` to see the same turns returned from storage; `--json` emits the full
machine-readable result.

The original M0 scripted-plan demo is still available:

```bash
uv run python scripts/offline_turn.py --db data/m0_demo.db --reset
```

## Development commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run uvicorn atlas.main:app --reload
```

`GET /healthz` reports application/database status. The API can create and list
campaigns, submit text turns, read turns, and read player-safe state and journal
views. See `docs/API.md`.

## Layout

```text
backend/atlas/        application package
  api/                FastAPI routes and response schemas
  domain/             IDs, models, events, commands, rules, outcomes, projections
  game/               intent parser, adjudicator, narrator, turn service
  models/             provider-neutral gateway + deterministic fake
  persistence/        SQLAlchemy tables, repositories, replay, migrations
  seed/               structured world fixtures
migrations/           Alembic migrations
scripts/              offline demos and setup helpers
tests/                unit, integration, and end-to-end tests
docs/                 decisions, progress, data model, API notes
```

See `docs/PROGRESS.md` for exact tested commands, known limitations, and the
next milestone. See `docs/DECISIONS.md` for architectural choices. No model
output is treated as authoritative: proposals are validated before commit.
