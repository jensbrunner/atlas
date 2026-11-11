# Data Model (M0)

The event ledger is history. Relational state is a projection that can be rebuilt
from history and checked against a canonical hash.

## Tables

### `campaigns`

`id`, `title`, `rules_version`, `status`, `state_version`, `current_time`, `seed`,
`settings_json`, `created_at`, `updated_at`.

`state_version` is derived from `turn.committed` events during replay.
`current_time` is integer world minutes from campaign epoch.

### `entities`

`id`, `campaign_id`, `kind`, `slug`, `display_name`, `static_json`,
`created_event_id`, `retired_event_id`.

Unique `(campaign_id, slug)`. Kinds: `player_character`, `npc`, `location`,
`item`, `faction`. Names are not identifiers.

### `entity_state`

`entity_id` (PK), `campaign_id`, `version`, `state_json`.

One row per entity, derived only from events. Mutable values include
`location_id`, `health`, `stress`, `supplies`, `currency`, and item `quantity`.
Per-entity `version` increments when a state-changing event is applied.

### `events` (append-only)

`id`, `campaign_id`, `turn_id`, `seq`, `type`, `actor_id`, `subject_id`,
`payload_json`, `inverse_json`, `occurred_at_world`, `created_at`,
`schema_version`, `provenance_json`, `visibility`, `cause_event_ids_json`.

Unique `(campaign_id, seq)`, contiguous from 1. M0 event types:

| Type | Payload | Projection effect |
|---|---|---|
| `entity.created` | kind, slug, display name, static, initial state | Insert entity and state |
| `entity.resource_changed` | resource, delta, before, after, bounds, reason | Set resource value |
| `entity.moved` | from/to location, reason | Set `location_id` |
| `time.advanced` | minutes, before, after, reason | Set campaign world time |
| `turn.committed` | turn ID, ordinal, new state version | Increment campaign version |

Payloads are validated by `domain.events.PAYLOAD_MODELS`; unknown types or extra
fields are rejected. Event IDs and sequences are assigned by the persistence
layer, never by a model.

### `turns`

`id`, `campaign_id`, `client_action_id`, `ordinal`, `player_text`, `status`,
`snapshot_version`, `narrator_text`, `mechanics_json`, `error_code`,
`rng_seed_hex`, `created_at`, `committed_at`.

Unique `(campaign_id, client_action_id)` for idempotency and
`(campaign_id, ordinal)` for ordering. Status values mirror the planned
lifecycle; M0 writes `RECEIVED` and then `COMMITTED` in one transaction.

### `rolls`

`id`, `campaign_id`, `turn_id`, `label`, `formula_json`, `rng_algorithm`,
`seed_ref`, `result_json`, `visibility`.

Committed roll outcomes are immutable. The seed reproduces the exact dice. Raw
`seed_ref` is sensitive and must not be exposed in player-facing responses before
an authorized reveal.

### `checkpoints`

`id`, `campaign_id`, `event_seq`, `state_hash`, `snapshot_json`, `created_at`.

Unique `(campaign_id, event_seq)`. Repeating a checkpoint at the same sequence
returns the existing row if the hash matches; a hash mismatch is an invariant
violation.

## Projection and hashing

`domain.projection.apply_event` applies one validated envelope and rejects:

- wrong campaign, unsupported schema, non-contiguous sequence;
- duplicate entity ID or slug;
- stale resource `before` value, inconsistent delta, out-of-bounds result;
- unknown/stale location, moving to the same location;
- stale time or inconsistent time step;
- a turn commit that does not increment the version by exactly one.

`hash_projection` canonicalizes campaign ID, current time, state version, and
sorted entities (ID, kind, slug, display name, static, state, per-entity version,
retirement) and SHA-256 hashes compact sorted JSON. `verify_replay` compares the
live projection hash with a hash rebuilt from events.

## Enforced M0 invariants

- Foreign keys and uniqueness are enforced by SQLite.
- A living actor must reference an existing location.
- Only actors and items may move; locations and factions may not.
- Resources cannot leave configured bounds; inventories cannot go negative.
- Entity slugs are unique per campaign.
- Every command references an entity in the same campaign.
- State changes are proposed as typed events and validated before commit.
- A turn's events and state projection commit atomically or not at all.
- A committed `(campaign_id, client_action_id)` returns its saved result.
- GM-only entities are omitted from `public_state_view`.

## Deferred to later milestones

`facts`, `knowledge`, `statements`, `relationships`, `items`, `locations`,
`npc_goals`, `factions`, `clocks`, `scenes`, `narrative_fingerprints`,
`player_preferences`, `model_calls`, and journal views. M0 represents locations
and items as entities; M2 will normalize their specialized fields and add the
four-truth model.
