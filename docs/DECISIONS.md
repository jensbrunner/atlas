# Architecture Decisions

Decisions recorded during M0 and M1. Later milestones may supersede them only
with an explicit entry here.

## ADR-001 — Python 3.12, FastAPI, SQLAlchemy 2.x, sync persistence

Accepted. The backend is a single local-first Python package (`atlas`) built
from `backend/`. FastAPI serves HTTP; Pydantic v2 defines domain and API
contracts; SQLAlchemy 2.x provides typed ORM tables. Database sessions are
synchronous.

Rationale: SQLite has one writer anyway, and a local single-user application
does not gain correctness from async ORM calls. The future model gateway is
async, but it must never hold a database transaction open while waiting on a
provider. A sync transaction boundary is easier to audit for commit/rollback.

## ADR-002 — SQLite with mandatory pragmas

Accepted. Every SQLite connection applies:

- `PRAGMA foreign_keys=ON`
- `PRAGMA busy_timeout=5000`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA journal_mode=WAL`

WAL is only supported on a local disk. The configuration docs and code state
this; network filesystem use is out of scope. Tests assert that the pragmas are
actually applied rather than merely configured.

## ADR-003 — Event-sourced projections, canonical relational reads

Accepted. The append-only `events` table is the history. The current projection
(`campaigns.current_time`, `campaigns.state_version`, `entities`, and
`entity_state`) is derived by applying events with `domain.projection.apply_event`.
No repository offers an update/delete path for committed events.

Event payloads are validated by a registry of Pydantic models keyed by
`EventType`. Unknown event types and unknown payload fields raise
`EventValidationError` before any projection mutation.

M0 does not add SQLite triggers that forbid all direct SQL updates. Repository
code never updates events, and replay/state hashing detects tampering; a
database-level append-only guard remains deferred beyond M1.

## ADR-004 — Campaign versions increment only via `turn.committed`

Accepted. A turn batch ends with a `turn.committed` event whose payload carries
the new campaign `state_version`. Replaying history derives the same version
without trusting the `campaigns` row. Seeding emits entity events only, so a
freshly seeded campaign is version `0` and replay produces version `0`.

This makes `state_version` a replayable world fact rather than metadata written
independently of history.

## ADR-005 — Canonical JSON and SHA-256 state hashes

Accepted. World state is projected into a canonical structure:

- campaign ID, current world time, campaign version;
- entities sorted by stable ID with kind, slug, display name, static data,
  mutable state, per-entity state version, and retirement marker.

The structure is serialized as sorted, compact JSON and hashed with SHA-256.
Replay computes the same hash from the event log and compares it with the live
projection. Checkpoints store that hash plus the event sequence, so a mismatch
is detectable after restart. `campaigns.title` and presentation settings are not
world state and are excluded.

## ADR-006 — Versioned reproducible RNG

Accepted. Each turn receives a fresh 32-byte `os.urandom` seed. Dice use
`hmac-sha256-ctr-v1`: HMAC-SHA256 over the seed and a big-endian 64-bit counter,
split into 32-bit chunks, with rejection sampling for unbiased bounded values.
The seed is stored with the turn and each roll. A committed roll can be
reproduced exactly; tests verify fixed-seed sequences and property-test the
total/band invariant.

The raw seed is sensitive: it must not appear in player-facing API responses
before an authorized reveal. M1 enforces this through `RollSummary`, which omits
`seed_ref`; the stored seed is reachable only through local database inspection
or an explicit future reveal.

## ADR-007 — Optimistic turn commit, idempotent client action IDs

Accepted for the M0 scripted turn service. The commit path:

1. Loads the projection and its campaign version `V`.
2. Applies validated commands to an in-memory clone.
3. Opens a write transaction and rechecks `V`.
4. Claims the writer slot with `UPDATE campaigns ... WHERE state_version = V`.
5. Inserts the turn, events, roll, and updated projection rows.
6. Sets the turn to `COMMITTED` and commits atomically.

Repeated `(campaign_id, client_action_id)` requests return the saved committed
turn. A stale expected version returns a typed conflict and mutates nothing.
Invalid commands fail before or during the transaction, so no partial world
state is visible.

ADR-007 remains the commit contract. M1 closes its listed gaps:

- same-client duplicate requests are serialized in-process and resolve to the
  stored turn; the database uniqueness constraint covers cross-process races;
- the lifecycle persists each phase so crashes recover without double-applying
  effects (ADR-012);
- crash injection, duplicate concurrency, rollback, and 100-turn replay are
  covered by tests.

A stale pending turn whose snapshot version has been overtaken is marked
`FAILED` rather than retried against different state.

## ADR-008 — Scripted plans remain the legacy offline path

Accepted for M0 and retained in M1. The offline regression path still accepts an
explicit `ScriptedTurnPlan` (typed commands, optional 2d6 request, optional
narration template). Player-facing API turns use the deterministic intent
pipeline instead. Both paths share the same command validation, lifecycle, and
commit boundary.

This is not presented as AI narration, and the deterministic fake provider is a
separate test double. Cloud/local modes are rejected at startup in M1. Model IDs
remain configurable settings but are not verified or called.

## ADR-009 — Structured seed fixture

Accepted. **The Broken Span** is seeded as location, character, faction, and item
entities plus explicit resources and intentions. M0 does not seed clocks,
facts/knowledge tables, or a predetermined plot resolution; those belong to M2.
The fixture already contains:

- a mistaken belief held by the magistrate;
- an intentional lie attributed to the mercenary captain;
- a GM-only caravan secret entity used to test isolation.

The GM-only entity is omitted entirely from `public_state_view`; a visibility
label alone would leak its existence.

## ADR-010 — M0 scope excludes facts, knowledge, and clocks tables

Deferred. VISION.md defines the four-truth model. M0 instead implements the
minimum persistent world: campaigns, entities, current entity state, events,
turns, rolls, and checkpoints. Adding empty fact/knowledge/clock modules now
would create unused abstractions. M2 adds them together with real statements,
knowledge assertions, and clock triggers.

Until then, beliefs and intentions are seed-static metadata and are not treated
as canonical facts or exposed through a journal endpoint.

## ADR-011 — Alembic migration is the source of schema truth

Accepted. Tests run `alembic upgrade head` against a fresh SQLite file rather
than calling `metadata.create_all()`. The migration chain is:

- `c4b9a1b5dbf2` — M0 core schema;
- `467150db4c93` — M1 turn lifecycle and observations.

Upgrade → downgrade → upgrade was verified on a temporary database by test and
by the CLI; the migration test also verifies that an M0-era campaign row survives
the round trip.

## ADR-012 — Durable phased turn lifecycle with resume

Accepted. A turn moves through
`RECEIVED → PARSED → RESOLVED → NARRATED → VALIDATED → COMMITTED`, with `FAILED`
as a durable terminal state. Each phase update is its own small transaction.
Intent, outcome, narration, and the original seed are persisted as they are
produced.

If the process stops before commit, re-submitting the same client id resumes at
the persisted phase using the stored seed. Re-running the parser or adjudicator
is unnecessary; re-running the commit is safe because the commit transaction is
atomic and compare-and-swap guarded. `attempt_count` records resumes.

Rationale: a local process can crash or be restarted mid-turn. Persisting
proposals must not make them authoritative, so the final commit re-validates all
commands against the snapshot immediately before writing.

## ADR-013 — Observations are event-sourced scene data

Accepted. Player-visible observations are not free prose stored beside a turn.
Each one is a `scene.observed` event with text, kind, subject IDs, and
visibility. The projection appends it, the `observations` table mirrors it, and
the canonical state hash includes it.

Rationale: the journal and scene views must replay exactly with the rest of the
world, and GM-only filtering must be enforceable at the event boundary. The
journal endpoint derives from the projection, not from narrator output.

## ADR-014 — Deterministic M1 parser, adjudicator, and fake narrator

Accepted. M1 uses a small deterministic text grammar, a deterministic
adjudicator, and a fake narrator. This is deliberate: it proves the structured
intent/outcome boundary and the lifecycle before a provider is integrated.

`IntentProposal` and `OutcomeProposal` are closed Pydantic schemas. The
adjudicator returns typed domain commands, never model text. Narration is
validated for length, control characters, and GM-only markers, and it can never
issue commands or mutate state. Raw roll seeds are excluded from `RollSummary`
and player-facing responses.

M3 may replace the parser and narrator with live models, but the contracts,
validation, and commit boundary remain.

## ADR-015 — Campaign turns are sequential; duplicates are idempotent

Accepted. Turns for one campaign are serialized in-process by a per-campaign
lock. This matches solo play and ensures each action resolves against the state
produced by the previous one.

`(campaign_id, client_action_id)` is the idempotency key. Sequential and
same-process concurrent duplicates return the stored turn. Across processes, the
unique constraint plus campaign version compare-and-swap prevent double
application; the losing writer either returns the committed winner or reports a
typed conflict. Distinct concurrent actions in separate processes are not queued
and may need a client retry, which is acceptable for a local single-user app.

## Deferred decisions

- DB-level append-only triggers and campaign-delete semantics.
- Async provider gateway and provider capability discovery (M3).
- FTS5 retrieval and context token budgets (M3).
- Clock scheduling and offline wall-clock policy (M2/M6).
- Export/import archive format and deletion confirmation flow (M4/M6).
- Exact model IDs and pricing table: verify at integration time; do not assume
  the examples in VISION.md are still available.
