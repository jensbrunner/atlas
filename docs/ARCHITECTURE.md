# Architecture (M2)

ATLAS separates authority from generation. The current slice proves the
authoritative side with deterministic local components and no language model.

```text
player text
   |
   v
DeterministicIntentParser  -> IntentProposal (closed schema)
   |
   v
DeterministicAdjudicator   -> OutcomeProposal (typed commands + observations)
   |
   v
FakeNarrator               -> prose (validated: length, control chars, secrets)
   |
   v
TurnService lifecycle
   |-- RECEIVED    claim turn row, allocate ordinal, persist fresh 32-byte seed
   |-- PARSED      persist intent
   |-- RESOLVED    validate commands, persist outcome and public roll summary
   |-- NARRATED    persist validated narration
   |-- VALIDATED   re-validate commands against the snapshot
   '-- COMMITTED   short transaction:
         |-- compare-and-swap campaign version V
         |-- append typed events (including scene.observed)
         |-- write projection rows and observation rows
         |-- persist reproducible roll (raw seed stays server-side)
         '-- mark turn COMMITTED

Replay: events order -> apply_event -> projection -> SHA-256 hash
        compare with live projection hash
```

Each phase before `COMMITTED` is durable. If the process stops after a phase,
re-submitting the same `(campaign_id, client_action_id)` resumes at that phase
with the original seed. No uncommitted world effects are visible, and a resumed
roll reproduces the exact dice.

## Trust boundaries

- **Domain code** (`atlas.domain`) owns commands, event schemas, invariants,
  dice, outcome contracts, and projection rules. It is the only authority that
  mutates state.
- **Game pipeline** (`atlas.game`) parses text into `IntentProposal`, adjudicates
  it into typed commands, renders narration, and drives the lifecycle. In M2 all
  three components are deterministic and network-free; challenges use the four
  attributes and trained skills rather than a model.
- **Persistence** (`atlas.persistence`) assigns event IDs/sequences, commits
  batches, writes projections and observations, replays history, and hashes
  state. It never invents domain events.
- **API** exposes turns, state, and journal views. Player-facing responses omit
  GM-only entities, GM-only observations, and raw roll seeds.
- **Model gateway** (`atlas.models`) is a provider-neutral interface plus a
  deterministic fake. M1 business logic does not call it. M3 adapters must
  return validated structures; they still receive no write authority.
- **Seed fixtures** (`atlas.seed`) emit ordinary typed entity-creation commands
  and events. They are not privileged backdoors into projection rows.

## Transaction boundary

No transaction is held across a future model call. The flow is
parse → adjudicate → narrate → validate → short compare-and-swap commit. Only
the final commit transaction changes events, projections, observations, rolls,
and the turn status. Phase updates are small independent transactions.

Turns for one campaign are serialized in-process so a later action resolves
against the state produced by the previous one. Cross-process safety comes from
the unique `(campaign_id, client_action_id)` constraint, the unique turn ordinal,
and the campaign version compare-and-swap. A duplicate request returns the saved
turn instead of applying effects twice.

## Trusted versus proposed data

| Data | Authority |
|---|---|
| Event ledger | committed, validated history |
| Projection and observation rows | derived from events |
| Turn row | committed response and mechanics |
| Roll row | committed immutable outcome |
| Intent/outcome on pending turn | proposal data, re-validated before commit |
| Narration | validated stored prose, never a command source |
| Fake model content | test data only |
| Statements and hidden `is_true` | canonical GM truth, never exposed to players |
| Knowledge links | canonical facts about who heard what |
| Relationships and clocks | canonical, derived from validated events |
| Seed belief/lie strings | fixture metadata, projected into statements where used |

## Directory responsibilities

```text
backend/atlas/api/          HTTP routes and API schemas
backend/atlas/domain/       IDs, models, commands, events, rules, outcomes, projection
backend/atlas/game/         parser, adjudicator, narrator, lifecycle turn service
backend/atlas/models/       gateway protocol and deterministic fake
backend/atlas/persistence/  SQLAlchemy tables, repositories, replay, Alembic runner
backend/atlas/seed/         structured Broken Span fixture
migrations/                 schema history
scripts/m2_paths.py         three divergent M2 paths with replay checks
scripts/m1_demo.py          deterministic text-play demonstration
scripts/offline_turn.py     legacy M0 scripted-plan demonstration
tests/                      unit, integration, end-to-end
```

## Non-goals in this slice

No live model narration, retrieval, frontend, export, or originality engine. The
M2 proof is that scripted negotiation, engineering, and confrontation paths reach
different persistent endings, each replays exactly, and GM-only truth never
reaches a player-facing view.
