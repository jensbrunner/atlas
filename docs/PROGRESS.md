# Progress

> Last updated: 2026-11-11  
> Current milestone: **M0 complete**  
> Next milestone: **M1 — transactional turn engine** (not started)

## Milestone status

| Milestone | Status | Evidence |
|---|---|---|
| M0 — Scaffold and offline database | **Complete** | Tests, migration, offline demo, replay/restart checks below |
| M1 — Transactional turn engine | Not started | M0 contains early slices: simple idempotency, optimistic version check, event commit |
| M2 — Minimal game, no frontier dependency | Not started | Broken Span is a seed fixture only |
| M3 — AI integration and narration | Not started | Only the deterministic fake gateway exists |
| M4 — Usable frontend | Not started | No frontend directory yet |
| M5 — Narrative originality system | Not started | — |
| M6 — Advanced simulation | Not started | — |
| M7 — Optional future directions | Not started | — |

## M0 checklist

- [x] Initialize Python package, API app, env configuration, dev dependencies, lint/test commands, docs, ignore rules.
- [x] Implement Pydantic domain schemas and stable prefixed ULIDs.
- [x] Configure SQLite foreign keys, WAL, busy timeout, transactions, and the first Alembic migration.
- [x] Implement campaigns, entities, entity projections, events, checkpoints, and `state_version`.
- [x] Implement typed domain commands and a hard invariant validator.
- [x] Implement the deterministic seeded 2d6 engine with a versioned RNG.
- [x] Implement event replay, canonical state hashing, and replay verification.
- [x] Add a deterministic fake model provider and the initial Broken Span seed fixture.
- [x] Write M0 unit/integration/e2e tests and a command-line offline scripted turn.

### Extra M0-adjacent pieces intentionally included

These reduce M1 risk but are not claimed as a completed M1:

- `turns` rows and a scripted offline turn service with atomic commit.
- Sequential idempotency by `(campaign_id, client_action_id)`.
- Optimistic campaign-version compare-and-swap and stale-version rejection.
- Roll persistence with reproducible seeds.
- Minimal campaign API (`POST/GET /api/v1/campaigns`, `GET /healthz`).

## Commands executed and results

Environment: macOS 27.2 arm64, Python 3.12.16 managed by `uv`; no cloud account.

```text
$ uv sync --group dev
Resolved 44 packages
Built atlas-rpg @ file:///Users/jens/Desktop/projects/roleplay
Installed 43 packages
```

```text
$ uv run alembic upgrade head
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> c4b9a1b5dbf2, M0 core schema
```

Upgrade → downgrade → upgrade was also verified on a temporary database:

```text
Running upgrade  -> c4b9a1b5dbf2, M0 core schema
Running downgrade c4b9a1b5dbf2 -> , M0 core schema
Running upgrade  -> c4b9a1b5dbf2, M0 core schema
```

Offline demonstration (recorded run; IDs and the turn seed are random, so a
fresh `--reset` run will produce different IDs and a different state hash):

```text
$ uv run python scripts/offline_turn.py --db data/m0_demo.db --reset
database: data/m0_demo.db
campaign: cmp_01M75T9JRZSP7MCC56W69M2BWX (seeded=True)
turn: trn_01M75T9JS7ZSDY2W32VJ1SXH4S  version: 1
narration: Rowan reaches the quarry and searches the scree for replacement stone. Outcome: failure (6 against difficulty 2); the search consumes 240 world minutes.
mechanics: {"commands": ["move_entity", "adjust_resource", "advance_time"], "elapsed_world_minutes": 240, "event_ids": ["evt_01M75T9JS8C04Z0Y74ZD8G6KKY", "evt_01M75T9JS813ADQAX9AG09V70A", "evt_01M75T9JS84F4EEV8J3ASJAVWE", "evt_01M75T9JS84B9CSW3A6R2JPQ0D"], "resolution": "failure", "roll": {"dice": [4, 1], "difficulty": 2, "label": "search the quarry for replacement stone", "modifier": 3, "outcome": "failure", "rng_algorithm": "hmac-sha256-ctr-v1", "total": 6}, "turn_ordinal": 1}
player: {"entity_id": "ent_01M75T9JRZH9HW7K17XYMKDZWG", "health": 7, "location": "North Quarry", "name": "Rowan", "state_version": 1, "supplies": 1, "world_minutes": 240}
replay: {"event_seq": 21, "matched": true, "state_hash": "d3b6d4b6de0edc4b98ee348443451d3ea6156f8d56da80aa887ec35aae8935cc"}
checkpoint: {"event_seq": 21, "state_hash": "d3b6d4b6de0edc4b98ee348443451d3ea6156f8d56da80aa887ec35aae8935cc"}
restart: {"current_time": 240, "replay_hash": "d3b6d4b6de0edc4b98ee348443451d3ea6156f8d56da80aa887ec35aae8935cc", "state_version": 1}
restart_persistence: True
idempotent_replay: True
```

Running the same command again without `--reset` returned the same turn ID,
narration, version `1`, and state hash. A duplicate client action did not add
events.

Verification suite:

```text
$ uv run pytest
56 passed, 1 warning in 1.14s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
All checks passed!

$ uv run mypy
Success: no issues found in 40 source files
```

The only warning is third-party: FastAPI's Starlette test client notes that
`httpx` support is deprecated in favor of `httpx2`. It does not affect test
results and no project code is responsible.

Tests cover, among other things:

- fixed-seed dice sequences, band boundaries, distribution sanity, and
  Hypothesis properties for totals and resource bounds;
- unknown event types, unknown payload fields, and schema-version rejection;
- exact resource accounting, negative inventory rejection, health bounds,
  location invariants, duplicate slugs, and time advancement;
- replay equality after seed and after a turn;
- detection of direct projection tampering and event sequence gaps;
- checkpoint idempotency and hash equality;
- turn commit, roll persistence/reproduction, idempotent duplicate requests,
  stale-version rejection, and no partial writes after invalid commands;
- SQLite pragmas and foreign-key enforcement;
- GM-only secret omission from the player-visible view;
- health/campaign API endpoints, including a 503 for an unmigrated database;
- end-to-end script execution, restart persistence, and idempotent re-run.

## Acceptance assessment for M0

| M0 done criterion | Result |
|---|---|
| Clean install | Verified with `uv sync --group dev` |
| Migration | Verified upgrade; upgrade/downgrade/upgrade on temp DB |
| One no-LLM action | Verified by offline script and integration tests |
| Replay | Live projection hash equals replay hash; tamper/gap detection tested |
| Restart | Script disposes the engine, reopens the DB, and rechecks state |
| All tests work | 56 passed; lint, format, and mypy clean |

**M0 is complete.** No UI, AI narration, intent parsing, or originality logic is
claimed.

## Known limitations / unresolved items

1. **No real turn pipeline yet.** M0 accepts `ScriptedTurnPlan`; there is no
   `IntentProposal`, `OutcomeProposal`, adjudicator, narrator, or validator
   chain. Narration is a template, not AI prose.
2. **No turn API.** `POST/GET /campaigns/{id}/turns` and `/state`, `/journal`
   are M1 work. The M0 API only exposes health and campaign creation/read.
3. **Idempotency race not demonstrated.** Sequential duplicates are safe. Two
   simultaneous writers with the same client ID can produce a conflict/unique
   error instead of returning the winner. No crash-injection recovery exists.
4. **Event ledger is append-only by repository discipline.** No SQLite trigger
   blocks direct `UPDATE`/`DELETE`; replay hashing detects tampering. DB-level
   enforcement and campaign-delete semantics are deferred.
5. **No four-truth tables.** Facts, knowledge, statements, relationships, goals,
   clocks, factions, scenes, and narrative fingerprints are not implemented.
   Seed beliefs/intentions are static metadata only.
6. **No 100-turn replay test.** M0 verifies one turn; M1 must prove a long
   fake-model simulation replays exactly.
7. **Seed is a world fixture, not full M2 gameplay.** Items, stone acquisition,
   repair, multiple divergent endings, and a CLI play loop remain.
8. **Raw roll seeds are stored unencrypted.** Local database only; never expose
   them in player-facing responses without an explicit reveal.
9. **No export/backup/import/delete UI or endpoints.**
10. **No live provider tests** and no verified model IDs; M3 must check current
    provider capabilities and pricing.
11. **No frontend.**
12. `campaigns.title` and settings are metadata, not part of world-state hashes.
    Intentional for M0; review if title changes become narratively meaningful.

## Exact next step for the next agent (M1)

Start with the turn lifecycle and API, not with a provider:

1. Add `domain/outcomes.py` contracts for `IntentProposal` and `OutcomeProposal`
   with schema versions; reject unknown fields and event types.
2. Implement a deterministic adjudicator that turns a validated intent +
   projection into commands/events, including automatic success/failure and
   optional 2d6 rolls. Keep the M0 command/event commit boundary.
3. Refactor `OfflineTurnService` into a lifecycle-aware service:
   `RECEIVED → PARSED → RESOLVED → NARRATED → VALIDATED → COMMITTED/FAILED`,
   with durable pending-attempt records, seed persistence, and recovery that
   never applies uncommitted effects.
4. Add `POST /api/v1/campaigns/{id}/turns` with `client_action_id`,
   `player_text`, and `expected_version`; add `GET` turns/state/journal with
   player-only filtering. Return typed `409` conflicts and stable error codes.
5. Add crash-injection tests at each phase, concurrent duplicate-request tests,
   a 100-turn fake-model replay test, and rollback tests.
6. Add scene observations, resource/time projections, and journal data needed by
   the fake narrator. Do not add frontier narration yet.

Use `docs/DECISIONS.md` ADR-007 as the starting boundary; update it if pending
state or concurrency behavior changes.
