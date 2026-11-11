# Progress

> Last updated: 2026-11-11  
> Current milestone: **M2 complete**  
> Next milestone: **M3 — AI integration and narration**

## Milestone status

| Milestone | Status | Evidence |
|---|---|---|
| M0 — Scaffold and offline database | **Complete** | Migration, offline demo, replay/restart checks below |
| M1 — Transactional turn engine | **Complete** | Text turns, durable lifecycle/crash recovery, API, duplicate/concurrency, rollback, 100-turn replay |
| M2 — Minimal game, no frontier dependency | **Complete** | Four attributes/templates, four-truth tables, inventory/gifts, three clocks, divergent endings, three scripted paths with exact replay, API state, M2 demo |
| M3 — AI integration and narration | Not started | Only the deterministic fake gateway exists; no live provider calls |
| M4 — Usable frontend | Not started | No frontend directory yet |
| M5 — Narrative originality system | Not started | — |
| M6 — Advanced simulation | Not started | — |
| M7 — Optional future directions | Not started | — |

## M2 checklist

- [x] Add Might, Agility, Insight, and Presence plus three character templates and four trained skills.
- [x] Resolve noncombat challenges deterministically from attributes, training, difficulty, and 2d6.
- [x] Add locations, movement, item stacks, inventory transfers, gifts, and consumption.
- [x] Add canonical facts, spoken statements (with hidden truth), knowledge links, and relationships.
- [x] Add NPC goals/plans and the first three faction/situation clocks.
- [x] Structure **The Broken Span** as an M2 fixture with materials, secrets, and multiple end conditions.
- [x] Implement divergent persistent endings: compromise, repaired gate, driven-off giant, returned stones, abandonment, and clock-forced failures.
- [x] Add an offline text/CLI play loop covering all M2 verbs.
- [x] Prove scripted negotiation, engineering, and confrontation reach different persistent outcomes with exact replay.
- [x] Keep M1 guarantees: validated proposals, atomic commit, durable lifecycle, no seed leakage, GM-only filtering.

M2 is deterministic and network-free. No live model, cloud account, or API key
was used.

## M1 checklist

- [x] Implement idempotent turn lifecycle, pending-attempt recovery, seed persistence, optimistic state-version checks.
- [x] Implement structured intent and outcome contracts and deterministic resolver.
- [x] Add scene observation projections, time advancement, basic resources, and rules outcomes.
- [x] Implement safe narrator pipeline using fake narrator with validations.
- [x] Add `POST turns`, `GET turns`, `GET state`, `GET journal` API endpoints.
- [x] Write duplicate-request, crash-injection, conflict, and rollback tests.
- [x] Prove the done criterion: a 100-turn fake-model text simulation replays exactly, and duplicate requests do not double-apply state.

M1 is deterministic and network-free. No live model, cloud account, or API key
was used.

## M0 checklist (retained)

- [x] Initialize Python package, API app, env configuration, dev dependencies, lint/test commands, docs, ignore rules.
- [x] Implement Pydantic domain schemas and stable prefixed ULIDs.
- [x] Configure SQLite foreign keys, WAL, busy timeout, transactions, and the first Alembic migration.
- [x] Implement campaigns, entities, entity projections, events, checkpoints, and `state_version`.
- [x] Implement typed domain commands and a hard invariant validator.
- [x] Implement the deterministic seeded 2d6 engine with a versioned RNG.
- [x] Implement event replay, canonical state hashing, and replay verification.
- [x] Add a deterministic fake model provider and the initial Broken Span seed fixture.
- [x] Write M0 unit/integration/e2e tests and a command-line offline scripted turn.

## M1 implementation summary

### Turn lifecycle

`backend/atlas/game/turn_service.py` now drives:

```text
RECEIVED -> PARSED -> RESOLVED -> NARRATED -> VALIDATED -> COMMITTED
                                                        \-> FAILED
```

- Each pre-commit phase is persisted with its own short transaction.
- `intent_json`, `outcome_json`, narration, and the original 32-byte seed survive
  a process stop.
- Resuming the same `client_action_id` starts at the persisted phase and reuses
  the stored seed; a committed roll reproduces exactly.
- Only the final commit transaction appends events, updates projections and
  observations, writes the roll, and marks the turn `COMMITTED`.
- The commit claims the campaign version with compare-and-swap and validates
  every command again immediately before writing.
- A pending turn overtaken by another commit is marked `FAILED` with
  `version_conflict`; it never applies stale effects.

### Structured contracts and deterministic game pipeline

- `backend/atlas/domain/outcomes.py` defines closed `IntentProposal`,
  `OutcomeProposal`, and `ObservationProposal` schemas.
- `backend/atlas/game/intent_parser.py` parses a small explicit grammar for
  move, observe, search, speak, and wait.
- `backend/atlas/game/adjudicator.py` converts a validated intent into typed
  domain commands, time advancement, observations, and an optional 2d6 search
  roll.
- `backend/atlas/game/narrator.py` provides a deterministic fake narrator and
  rejects empty/overlong text, control characters, and GM-only markers.
- `RollSummary` excludes `seed_ref`; player-facing turn/state/journal responses
  contain neither the seed reference nor GM-only data.

### Observations and player views

- New `scene.observed` event, `ProjectedObservation`, and `observations` table.
- Observation rows are derived from events and included in the canonical state
  hash.
- `GET /state` returns a focused scene plus public entities and recent
  observations.
- `GET /journal` returns paginated player-visible observations.
- GM-only entities and observations are omitted entirely, including subject IDs.

### API

- `POST /api/v1/campaigns/{id}/turns`
- `GET /api/v1/campaigns/{id}/turns`
- `GET /api/v1/campaigns/{id}/turns/{turn_id}`
- `GET /api/v1/campaigns/{id}/state`
- `GET /api/v1/campaigns/{id}/journal`

Typed `404`, `409`, and `422` mappings are documented in `docs/API.md`.

## M2 implementation summary

### Characters, challenges, and inventory

- `backend/atlas/domain/characters.py` defines the four attributes, training,
  three templates (`river_fixer`, `town_advocate`, `stone_warden`), and the
  `attribute + training` challenge modifier.
- Parser and adjudicator cover `negotiate`, `confront`, `engineer`, `gather`,
  `give`, and `abandon`, plus the M1 verbs.
- Item stacks carry `quantity`; `TransferItemCommand`, `GiveItemCommand`, and
  `ConsumeItemCommand` move or consume inventory through validated events.

### Four truths and clocks

- New projections and tables: `facts`, `statements`, `knowledge`,
  `relationships`, and `clocks`, plus `campaigns.ending_json`.
- Statements store a hidden `is_true`; player views return only statements the
  actor knows and never expose `is_true`.
- `storm_arrival` (6), `giant_deadline` (4), and `town_unrest` (4) advance only
  through explicit commands. Storm ticks only for whole two-hour blocks inside
  an explicit `AdvanceTimeCommand`.
- Filling a clock can force `storm_flood`, `bridge_collapse`, or `town_revolt`.
- Path endings also include `compromise_shared_guardianship`,
  `flood_gate_repaired`, `giant_driven_off`, `stones_returned`, and
  `town_abandoned`.

### API and demo

- `POST /api/v1/campaigns` accepts `template_slug`.
- Campaign responses expose `ending`; state responses expose `status`,
  `clocks`, `knowledge`, and `ending`.
- State entity views expose safe rules data (`template`, `attributes`,
  `training`, `equipment`, `abilities`) and omit goals, plans, beliefs, and
  other GM-only static fields.
- `scripts/m2_paths.py` plays the three divergent paths and verifies replay.

## Commands executed and results (M1)

Environment: macOS arm64, Python 3.12.16 managed by `uv`; no cloud account.

### Migration chain

```text
$ ATLAS_DATABASE_URL=sqlite:///.../m1_mig.db uv run alembic upgrade head
Running upgrade  -> c4b9a1b5dbf2, M0 core schema
Running upgrade c4b9a1b5dbf2 -> 467150db4c93, M1 turn lifecycle and observations

$ ATLAS_DATABASE_URL=... uv run alembic downgrade c4b9a1b5dbf2
Running downgrade 467150db4c93 -> c4b9a1b5dbf2, M1 turn lifecycle and observations

$ ATLAS_DATABASE_URL=... uv run alembic upgrade head
Running upgrade c4b9a1b5dbf2 -> 467150db4c93, M1 turn lifecycle and observations
```

`tests/integration/test_migrations.py` repeats this round trip and verifies that
an M0-era campaign row survives it, and that the new `turns` columns and
`observations` table appear, disappear, and reappear.

### Offline text demo

```text
$ uv run python scripts/m1_demo.py --db data/m1_demo.db --reset
campaign: cmp_01M75VBF3TX1Z2DKSKFNWANSKT (new seed: True)
  1. look around              v1   You take in Market Square. Present: Magistrate Elin, Vessa, Mercenary Captain. Rowan is at Market Square.
  2. go to north quarry       v2   You travel to North Quarry. Rowan is at North Quarry.
  3. search the quarry        v3   You search North Quarry. You find a little useful material. The attempt ends in success (11 against difficulty 2). Rowan is at North Quarry.
  4. wait 15 minutes          v4   You wait 15 minutes at North Quarry. Rowan is at North Quarry.
  5. go to market square      v5   You travel to Market Square. Rowan is at Market Square.
  6. talk to the magistrate   v6   You speak with Magistrate Elin. Rowan is at Market Square.
  7. look around              v7   You take in Market Square. Present: Magistrate Elin, Vessa, Mercenary Captain. Rowan is at Market Square.
  8. wait 1 hour              v8   You wait 60 minutes at Market Square. Rowan is at Market Square.
  9. look around              v9   You take in Market Square. Present: Magistrate Elin, Vessa, Mercenary Captain. Rowan is at Market Square.
 10. go to north quarry       v10  You travel to North Quarry. Rowan is at North Quarry.
 11. search the quarry        v11  You search North Quarry. You find a little useful material. The attempt ends in success (13 against difficulty 2). Rowan is at North Quarry.
 12. wait 15 minutes          v12  You wait 15 minutes at North Quarry. Rowan is at North Quarry.
final version: 12 | world minutes: 325 | observations: 12
replay: matched at event 58 | duplicate request idempotent: True
state hash: 151515f1821fd2db5613655ec536e84f55810d2ab58bec9c0cc5bedfffdeb16a
```

IDs, dice, and the state hash are random per fresh `--reset` run. Running the
same script again without `--reset` returns the same 12 turn IDs and narrations,
keeps version 12, and matches the same state hash. The e2e test
`tests/e2e/test_m1_demo_script.py` asserts this.

### Verification suite

```text
$ uv run pytest
102 passed in 3.13s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
64 files already formatted

$ uv run mypy
Success: no issues found in 54 source files
```

The only pytest warning is third-party: FastAPI's Starlette test client notes
that `httpx` support is deprecated in favor of `httpx2`. It does not affect test
results and no project code is responsible.

### M1 tests added

- `tests/unit/test_outcomes.py` — closed schemas, roll/resolution consistency,
  typed-command round trip, no seed field in `RollSummary`.
- `tests/unit/test_intent_parser.py` — supported grammar, ambiguity handling,
  hours/minutes, GM-only targets rejected.
- `tests/unit/test_adjudicator.py` — move/search/speak/wait commands, roll
  reproduction, supply bounds, invalid target rejection.
- `tests/integration/test_turn_lifecycle.py` — full phase order; crash after
  every phase including `COMMITTED`; seed reuse; commit rollback; stale pending
  failure; invalid-text durability; narration secret rejection; same-client
  concurrency; distinct concurrent actions; 100-turn replay and duplicate check.
- `tests/integration/test_turns_api.py` — POST/GET turns, state, journal,
  duplicate POST, expected-version conflict, 422/409/404, malformed requests,
  no seed or GM-only leakage.
- `tests/integration/test_migrations.py` — M1 round trip and data preservation.
- `tests/e2e/test_m1_demo_script.py` — demo replay and idempotency across
  restarts.

## Commands executed and results (M2)

Environment: macOS arm64, Python 3.12.16 managed by `uv`; no cloud account.

```text
$ uv run pytest -p no:warnings
114 passed in 5.80s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
69 files already formatted

$ uv run mypy
Success: no issues found in 58 source files
```

### Migration chain

The head is `9ddd09ccdad2` (M2). `tests/integration/test_migrations.py`
upgrades to M2, checks the new tables and `ending_json`, inserts an M0-era
campaign, downgrades through M1 to M0, and re-upgrades while preserving the row.

### Offline M2 demo

```text
$ uv run python scripts/m2_paths.py --db data/m2_demo.db --reset
== negotiation (town_advocate) ==
  ... 2 turns ...
  status: completed | ending: compromise_shared_guardianship | version: 2 | world minutes: 60
  replay: matched at event 46
== engineering (river_fixer) ==
  ... 10 turns ...
  status: completed | ending: flood_gate_repaired | version: 10 | world minutes: 520
  replay: matched at event 79
== confrontation (stone_warden) ==
  ... 1 turn ...
  status: completed | ending: giant_driven_off | version: 1 | world minutes: 30
  replay: matched at event 39
```

IDs and event numbers vary per fresh database; each path checks
`verify_replay(...).matched`. `tests/e2e/test_m2_path_script.py` reruns the demo
in the same database, confirms three new campaigns reach the same distinct
endings, and confirms each replays.

### M2 tests added

- `tests/integration/test_m2_paths.py` — negotiation, engineering,
  confrontation, returned stones, abandonment, storm-forced ending, distinct
  persistent endings, knowledge isolation, gift persistence, and event coverage.
- `tests/integration/test_api.py` — `template_slug`, campaign `ending`, state
  `status`/`clocks`/`knowledge`/`ending`, safe attribute exposure, no `is_true`
  or GM-only leakage.
- `tests/integration/test_migrations.py` — M2 head round trip and data
  preservation through M1 and M0.
- `tests/e2e/test_m2_path_script.py` — three-path demo and replay after restart.

## Acceptance assessment for M2

| M2 done criterion | Result |
|---|---|
| Scripted negotiation reaches a persistent outcome | `town_advocate` negotiates with Brannoc and Elin; success on both produces `compromise_shared_guardianship`, campaign status `completed`, and a matched replay |
| Scripted engineering reaches a different outcome | `river_fixer` learns Durn's lead, finds the quarry seam, gathers stone/timber/fittings, repairs the gate, and produces `flood_gate_repaired` with a matched replay |
| Scripted confrontation reaches a different outcome | `stone_warden` succeeds against Brannoc and produces `giant_driven_off` with a matched replay |
| Outcomes persist and replay exactly | Each path checks `campaign.ending`, `projection.status`, and `verify_replay(...).matched`; `test_each_path_leaves_a_different_persistent_ending` proves three distinct endings |
| Additional endings work | Tests cover `stones_returned`, `town_abandoned`, and the `storm_arrival` clock forcing `storm_flood` after an explicit 12-hour wait |
| Four truths stay isolated | `test_player_state_never_exposes_hidden_truth` and the API test assert no `is_true`, GM-only slug, or secret marker reaches a player view |
| Inventory and gifts persist | `test_gift_moves_inventory_between_characters` asserts exact quantities on both characters |
| M1 guarantees hold | The full M1 suite, including the 100-turn replay and duplicate-request tests, still passes |

**M2 is complete.** No live model narration, retrieval, frontend, or
originality logic is claimed.

## Acceptance assessment for M1

| M1 done criterion | Result |
|---|---|
| 100-turn fake-model simulation replays exactly | `test_hundred_turn_text_simulation_replays_exactly` commits 100 text turns, asserts version 100, 100 observations, `verify_replay(...).matched`, then replays every duplicate without changing the hash |
| Duplicate requests cannot double-apply state | Same-client concurrent test returns one turn id/version 1; 100-turn test replays all 100 client ids and keeps version 100 and the same state hash |
| Lifecycle and pending-attempt recovery | Parameterized crash injection at `RECEIVED`, `PARSED`, `RESOLVED`, `NARRATED`, `VALIDATED`, `COMMITTED`; pre-commit crashes leave version/events/hash unchanged, then resume and commit once |
| Seed persistence and roll reproduction | Recovery test compares the resumed dice/total/outcome with the stored outcome, keeps the same `rng_seed_hex`, and writes one roll row |
| Optimistic version checks and conflicts | Stale pending turn becomes durable `FAILED` with `version_conflict`; expected-version API request returns `409` and creates no turn |
| Atomic rollback | Injected write failure after event insertion leaves version 0, event/hash unchanged, zero observation/roll rows, and a non-committed turn |
| Structured intent/outcome and deterministic resolver | Unit tests cover closed schemas and parser/adjudicator behavior |
| Observations, time, resources, outcomes | Text turns produce `scene.observed`, time/resource events, and search roll outcomes |
| Safe narrator pipeline | Fake narrator output is validated; GM-only marker test produces `narrator_invalid` with no state change |
| API endpoints | Integration tests exercise POST/GET turns, state, journal, typed errors, and player-only filtering |

**M1 is complete.** No live model narration, frontend, four-truth tables, clocks,
or originality logic is claimed.

## Known limitations / unresolved items

1. **Narrow deterministic grammar.** M2 understands explicit move/observe/
   search/speak/wait/negotiate/confront/engineer/gather/give/abandon text. It is
   not natural-language understanding and does not use a model.
2. **Challenges are deterministic 2d6, not tactical combat.** Social,
   engineering, gathering, and confrontation are noncombat challenge paths; the
   advanced combat simulation remains M6 work.
3. **Cross-process distinct turns are not queued.** In-process turns are
   serialized per campaign. Two separate processes submitting distinct actions
   may produce a typed conflict; the client retries. Duplicate application is
   still prevented by the unique key and commit CAS.
4. **Event ledger remains append-only by repository discipline.** No SQLite
   trigger blocks direct `UPDATE`/`DELETE`; replay hashing detects tampering.
5. **Narration secret filtering is marker-based.** It is defense in depth, not a
   semantic secret detector; M3 narrator checks must be stronger.
6. **No scenes or narrative fingerprints.** M2 adds facts, statements,
   knowledge, relationships, and clocks, but no scene graph or originality
   system. NPC goals/plans remain seed-static metadata.
7. **Raw roll seeds are stored unencrypted** in the local database. They are
   excluded from all current player-facing responses; an explicit reveal flow is
   still future work.
8. **No export/backup/import/delete UI or endpoints.**
9. **No live provider tests** and no verified model IDs. M3 must check current
   provider capabilities and pricing.
10. **No frontend.**
11. `campaigns.title` and settings are metadata, not part of world-state hashes.
12. **Same-client cross-process recovery is not integration-tested** with two
    real processes. In-process duplicate concurrency, DB uniqueness, and CAS are
    tested.

## Exact next step for the next agent (M3)

Start M3 on top of the M2 contracts; live providers remain opt-in:

1. Add provider-neutral narration and intent adapters behind the existing
   `IntentProposal`/`OutcomeProposal` contracts; never let model text issue
   commands.
2. Add context assembly and retrieval over the event ledger, facts, statements,
   and knowledge without leaking `is_true` or GM-only material.
3. Add an opt-in live-provider configuration path and tests that require no
   network or credentials; keep deterministic fakes as the default.
4. Strengthen narrator secret filtering beyond marker matching.
5. Keep M1/M2 guarantees: validated proposals only, atomic commit, durable
   lifecycle, no seed leakage, player-only filtering, and exact replay.

Re-read `docs/DECISIONS.md` ADR-012 through ADR-019 for the boundaries M3 must
preserve.
