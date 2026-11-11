# Architecture Decisions

Decisions recorded during M0. Later milestones may supersede them only with an
explicit entry here.

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
database-level append-only guard is a candidate for M1.

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
before an authorized reveal. M0 only exposes it through local database
inspection and internal `RollResult` objects.

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

Known M1 gaps: a same-client-ID race between two writers currently surfaces as a
version conflict or uniqueness error rather than transparently returning the
winner; crash-injection and `PROCESSING` recovery are not implemented. M1 owns
those tests.

## ADR-008 — M0 uses scripted plans, not an LLM

Accepted. The M0 turn service accepts an explicit `ScriptedTurnPlan` (typed
commands, optional 2d6 request, optional narration template). This is deliberate:
it proves state integrity and mechanics before any provider is integrated. It is
not presented as AI narration, and the deterministic fake provider is a separate
test double. M1 will replace the plan source with intent/outcome contracts while
preserving the commit boundary.

Cloud/local modes are rejected at startup in M0. Model IDs remain configurable
settings but are not verified or called.

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
than calling `metadata.create_all()`. The initial revision is
`c4b9a1b5dbf2` (`M0 core schema`). Upgrade → downgrade → upgrade was verified on
a temporary database.

## Deferred decisions

- DB-level append-only triggers and campaign-delete semantics.
- Async provider gateway and provider capability discovery (M3).
- FTS5 retrieval and context token budgets (M3).
- Clock scheduling and offline wall-clock policy (M2/M6).
- Export/import archive format and deletion confirmation flow (M4/M6).
- Exact model IDs and pricing table: verify at integration time; do not assume
  the examples in VISION.md are still available.
