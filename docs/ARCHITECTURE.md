# Architecture (M0)

ATLAS separates authority from generation. The current slice proves the
authoritative side without any language model.

```text
offline script / test
        |
  ScriptedTurnPlan          (typed commands + optional 2d6 request)
        |
  OfflineTurnService
        |-- load projection at campaign version V
        |-- validate commands against state (hard invariants)
        |-- generate per-turn seed; resolve 2d6 reproducibly
        |-- render deterministic scripted narration
        |-- open short write transaction
        |     |-- compare-and-swap version V
        |     |-- insert turn, events, roll
        |     |-- apply events to projection rows
        |     '-- mark turn COMMITTED
        '-- return committed narration + mechanics

  Replay: events order -> apply_event -> projection -> SHA-256 hash
          compare with live projection hash
```

## Trust boundaries

- **Domain code** (`atlas.domain`) owns commands, event schemas, invariants,
  dice, and projection rules. It is the only authority that mutates state.
- **Persistence** (`atlas.persistence`) assigns event IDs/sequences, commits
  batches, writes projections, replays history, and hashes state. It never
  invents domain events.
- **Turn service** (`atlas.game`) coordinates a scripted plan and the commit
  boundary. In M0 the plan is local/test data, not model output.
- **API** exposes only health and campaign creation/read in M0. It does not
  expose GM-only data.
- **Model gateway** (`atlas.models`) is a provider-neutral interface plus a
  deterministic fake. M0 business logic does not call it. M3 adapters must
  return validated Pydantic structures; they still receive no write authority.
- **Seed fixtures** (`atlas.seed`) emit ordinary typed entity-creation commands
  and events. They are not privileged backdoors into projection rows.

## Transaction boundary

No transaction is held across a future model call. The intended M1+ flow is:
snapshot → parse → retrieve → adjudicate → narrate → validate → short
compare-and-swap commit. M0 already uses the compare-and-swap commit and atomic
rollback on invalid state.

## Trusted versus proposed data

| Data | Authority |
|---|---|
| Event ledger | committed, validated history |
| Projection rows | derived from events |
| Turn row | committed response and mechanics |
| Roll row | committed immutable outcome |
| Scripted narration | deterministic M0 output, stored with turn |
| Fake model content | test data only |
| Seed belief/lie strings | fixture metadata, not canonical facts |

## Directory responsibilities

```text
backend/atlas/api/          HTTP routes and API schemas
backend/atlas/domain/       IDs, models, commands, events, rules, projection
backend/atlas/game/         M0 scripted turn orchestration
backend/atlas/models/       gateway protocol and deterministic fake
backend/atlas/persistence/  SQLAlchemy tables, repositories, replay, Alembic runner
backend/atlas/seed/         structured Broken Span fixture
migrations/                 schema history
scripts/offline_turn.py     reproducible offline demonstration
tests/                      unit, integration, end-to-end
```

## Non-goals in this slice

No intent parser, narrator model, retrieval, facts/knowledge tables, clocks,
frontend, export, or originality engine. The M0 proof is that a seeded world
survives a validated turn, restart, duplicate request, and exact replay without
an LLM.
