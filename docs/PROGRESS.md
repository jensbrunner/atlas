# Progress

> Last updated: 2026-11-11  
> Current milestone: **M1 complete**  
> Next milestone: **M2 — minimal game, no frontier dependency**

## Milestone status

| Milestone | Status | Evidence |
|---|---|---|
| M0 — Scaffold and offline database | **Complete** | Migration, offline demo, replay/restart checks below |
| M1 — Transactional turn engine | **Complete** | Text turns, durable lifecycle/crash recovery, API, duplicate/concurrency, rollback, 100-turn replay |
| M2 — Minimal game, no frontier dependency | Not started | Broken Span is still a seed fixture; no clocks or four-truth tables |
| M3 — AI integration and narration | Not started | Only the deterministic fake gateway exists; no live provider calls |
| M4 — Usable frontend | Not started | No frontend directory yet |
| M5 — Narrative originality system | Not started | — |
| M6 — Advanced simulation | Not started | — |
| M7 — Optional future directions | Not started | — |

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

1. **Narrow deterministic grammar.** M1 understands explicit move/observe/search/
   speak/wait text. It is not natural-language understanding and does not use a
   model.
2. **Only search rolls.** Social, engineering, combat, and faction systems are
   M2/M6 work. Speech currently advances time and records an observation.
3. **Cross-process distinct turns are not queued.** In-process turns are
   serialized per campaign. Two separate processes submitting distinct actions
   may produce a typed conflict; the client retries. Duplicate application is
   still prevented by the unique key and commit CAS.
4. **Event ledger remains append-only by repository discipline.** No SQLite
   trigger blocks direct `UPDATE`/`DELETE`; replay hashing detects tampering.
5. **Narration secret filtering is marker-based.** It is defense in depth, not a
   semantic secret detector; M3 narrator checks must be stronger.
6. **No four-truth tables, clocks, scenes, or narrative fingerprints.** Beliefs
   and intentions remain seed-static metadata.
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

## Exact next step for the next agent (M2)

Start M2 on top of the M1 contracts; do not add a live model yet:

1. Add the four attributes, initial character templates, skills, and noncombat
   challenge resolution that consumes `OutcomeProposal`/typed commands.
2. Add the four-truth structures needed for statements, knowledge assertions,
   goals, and relationships, plus the first three faction clocks.
3. Turn **The Broken Span** into a structured M2 fixture with inventoried items,
   movement, dialogue/statement events, and multiple divergent end conditions.
4. Add scripted negotiation, engineering, and confrontation paths and prove they
   reach different persistent outcomes with exact replay.
5. Add a basic offline text/CLI play loop built on `TurnService.submit_text`.
6. Keep the M1 guarantees: validated proposals only, atomic commit, durable
   lifecycle, no seed leakage, and player-only filtering.

Re-read `docs/DECISIONS.md` ADR-012 through ADR-015 for the boundaries M2 must
preserve.
