# Decisions

Architecture decisions for the harness rebuild. Earlier decisions about the
deleted SQLite/event-sourced engine remain in git history.

## ADR-001 — The narrator is the game master

Accepted. The model decides how scenes resolve, what NPCs do, and when a roll is
needed. The harness does not encode a story, a correct path, or a fixed
adventure. Code exists to make the model's decisions persistent, bounded, and
visible.

Consequence: the quality of play depends on the prompt, context packet, and
tools. Engine code must stay generic.

## ADR-002 — Markdown files are canonical; no database

Accepted. A campaign is a directory of markdown documents with YAML
frontmatter. There is no SQLite schema, migration chain, or event ledger. The
turn files and journal form the audit trail.

Consequence: state is inspectable and editable by hand, but the harness must
validate hand edits on load and must write atomically.

## ADR-003 — One canon, two rendered views

Accepted. The canonical files may contain GM blocks, hidden facts, and hidden
NPC knowledge. The server renders a player view by stripping that material. The
frontend never receives a second editable copy.

Consequence: views cannot drift. The leak scan is defense in depth, not a proof
that a model will never reveal a secret.

## ADR-004 — Tools gate all persistent change

Accepted. The narrator may propose any change, but health, inventory, time,
clocks, NPCs, factions, facts, and scenes change only through typed tools.
Narration without a tool call changes nothing.

Consequence: tool schemas and validation are part of the product surface. A
rejected tool call is returned to the model as an error string, not a crash.

## ADR-005 — Atomic in-memory turns

Accepted. A turn loads the campaign, mutates the in-memory state through tools,
validates it, and only then writes files. Model failure, leak detection, or
validation failure discards the turn.

Consequence: there is no resumable half-turn. A crashed process leaves the last
committed files intact.

## ADR-006 — One narrator loop per turn

Accepted. Cost control comes from one narrator call per turn plus tool
round-trips. There is no per-turn subagent committee. The campaign generator is a
single structured call. World evolution and continuity audit are on demand.

## ADR-007 — Four attributes and modest mechanics

Accepted. Might, Agility, Insight, Presence; a short skill list; 2d6 plus
attribute plus skill against a difficulty; health, stress, supplies, currency,
conditions, inventory, clocks, and world minutes. No tactical grid, no combat
subsystem, no character-creation workflow.

Consequence: mechanics support adjudication without turning the game into a
rules engine.

## ADR-008 — Facts carry GM/player visibility

Accepted. Canonical facts are explicit records with `visibility: gm|player`.
Revealing a fact flips visibility and records the turn. NPC knowledge is a list
of fact ids and is GM-only. Locations, factions, and NPCs use `player_known`.

## ADR-009 — The fake provider is the default

Accepted. `ATLAS_PROVIDER=fake` requires no credentials and makes no network
calls. Tests and the offline demo use it. Live calls require
`ATLAS_PROVIDER=openai`, a key, and `ATLAS_ALLOW_CLOUD=true`.

## ADR-010 — OpenAI Responses API, configurable model IDs

Accepted. The live adapter uses the Responses API with function tools. The
default model for campaign generation, narration, world turns, and audit is
`gpt-6-luna`, configurable by environment. ATLAS does not silently substitute a
model if the configured one is unavailable; the provider error is reported.

## ADR-011 — Campaign generation is structured and validated

Accepted. The generator returns a single `submit_campaign` payload containing
premise, opening scene, character, locations, factions, clocks, facts, and NPCs.
Pydantic validates references (`current_location`, NPC locations, known facts)
before any file is written. A failed generation creates nothing.

## ADR-012 — World evolution is explicit

Accepted. A world turn runs only on manual request or when the narrator asks for
one. It updates clocks, factions, NPCs, and offscreen facts. It does not narrate
the player's scene and does not resolve the player's situation.

Consequence: the world does not silently spiral while the player reads.

## ADR-013 — The auditor is advisory

Accepted. The continuity auditor returns findings with severity, summary, and
evidence. It has no write tools. It is invoked on demand, not every turn.

## ADR-014 — Svelte 5 + Vite, served by FastAPI

Accepted. The frontend is a single-page Svelte 5 app with no UI framework. Vite
proxies `/api` in development; FastAPI serves `web/dist` in production. Turns
stream progress events over SSE; narration is not token-streamed.

## ADR-015 — Delete the old engine

Accepted. The SQLite/event-sourced engine, deterministic adjudicator, migrations,
old tests, old docs, and the prewritten Broken Span scenario were removed from
the working tree. Git history preserves them. The new harness does not import or
depend on any of it.

## ADR-016 — Discovery and creation are tools

Accepted. The narrator can introduce a new place or NPC with `create_location`
and `create_npc`, and mark a genuine discovery with `reveal_location`,
`reveal_npc`, or `reveal_faction`. `set_scene` reveals its destination. This lets
the world grow without leaking hidden material.

## ADR-017 — A leaked draft gets one repair pass

Accepted. If narration mentions protected material, the narrator sees the
rejection and may reveal what the fiction genuinely discovered or rewrite without
it. The repair shares the in-memory turn, so already-applied mechanical changes
survive. A second leak fails the turn with nothing written.

## ADR-018 — Identical tool effects apply once per turn

Accepted. Repeating a tool call with the same mechanical arguments (ignoring
purely descriptive fields such as `reason`) is ignored for the rest of the turn.
This prevents a model that re-enters the tool loop from double-charging
inventory, clocks, or time. If a larger effect is intended, the model must make
one call with a larger value.

## ADR-019 — Generate a starting time

Accepted. Campaign generation includes `start_minute`, stored as
`world_time_minutes`, so an opening at dusk does not display as Day 1, 00:00.
Narration avoids numeric clock times and shows time through the fiction.

## ADR-020 — The player view is deliberately sparse

Accepted. The player sees character, inventory, known places, faction names, NPC
names/locations/descriptions, visible clocks, revealed facts, and the transcript.
NPC attitudes, goals, plans, knowledge, faction goals/stances/resources, and full
sheets remain GM-side. This keeps social inference and mystery in the fiction.

## ADR-021 — Avoid names from previous campaigns

Accepted. Campaign generation receives the character, NPC, location, and faction
names already present in the data directory and is told not to reuse them. This
keeps a stable of local campaigns from feeling like the same cast under different
titles.

## ADR-022 — Stream turn progress, not prose

Accepted. `/turns/stream` runs the atomic turn in a worker thread and emits SSE
`status` and `tool` events, followed by a `done` event with the full result. The
browser shows what the narrator is doing and an elapsed timer. Prose tokens are
not streamed because a draft can be rejected by the leak scan or repair pass, and
the turn must remain all-or-nothing.

## ADR-023 — Usage is read from turn files

Accepted. Token usage is stored in each turn's frontmatter. The usage endpoint
aggregates it by campaign and per turn; the UI exposes it through a Usage modal.
Input tokens include the GM packet and every tool round-trip, so the totals are
larger than the visible narration. Cost remains optional until per-million rates
are configured.

## ADR-024 — Local BM25 retrieval selects context

Accepted. The narrator does not receive all canon. `atlas/retrieval.py` builds a
derived BM25 index over NPCs, locations, factions, facts, and clocks. The query
combines the action, current location, present cast, and last narration. Ranking
has a name boost and a relative cutoff; scene entities and NPC knowledge are
forced in. The index is disposable and rebuilt from canonical markdown.

## ADR-025 — lookup_canon is the escape hatch

Accepted. Omitted canon remains binding. The prompt tells the narrator how many
entities are in the packet versus canon, and `lookup_canon` searches the full
state on demand. This keeps normal context small without making distant canon
inaccessible. The tool is model-facing and costs tokens only when called.

## Deferred decisions

- Token-level narration streaming.
- Export/import of campaign directories.
- Automatic world-turn thresholds based on world time.
- Semantic/vector retrieval and a persisted index for very large worlds.
- Semantic secret-leak detection and model-side redaction.
- Bundled per-model price presets for accurate USD accounting.
- Multi-user or remote hosting.
