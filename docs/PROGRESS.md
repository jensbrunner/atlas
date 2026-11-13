# Progress

## Status

**Milestone exceeded: live campaigns play end to end.**

Live GPT-6 Luna campaigns have been generated and played through the real OpenAI
Responses API: campaign creation, multi-turn play with rolls and state changes,
discovery of hidden NPCs/locations, world turns, audits, and server restarts.
Narration has been consistently character-driven, with NPC plans, secrets, clocks,
and consequences carrying forward.

The offline fake provider remains the default for tests and development. Live use
still requires `ATLAS_PROVIDER=openai` + `ATLAS_OPENAI_API_KEY` +
`ATLAS_ALLOW_CLOUD=true`.

The old SQLite/event-sourced engine, migrations, deterministic adjudicator, and
the Broken Span scenario are deleted from the working tree. Git history keeps
them.

## Implemented

### State and persistence

- Canonical state is one campaign directory of markdown files with YAML
  frontmatter: `campaign.md`, `character.md`, `world.md`, `npcs/*.md`,
  `journal.md`, `turns/NNNN.md`, `turns/NNNN-world.md`.
- Atomic per-file writes (`os.replace`) and atomic in-memory turns: nothing is
  written until the model reply, leak scan, and state validation all pass.
- One canon, two views. `atlas/state/render.py` derives the player view by
  stripping `<!-- gm -->` blocks, hidden facts, hidden NPC knowledge, and
  `player_known: false` entities. NPC attitudes/plans and faction goals/stances
  stay GM-side. The GM view exposes everything.
- Campaigns open at a generated time of day, stored as `world_time_minutes`.
- Turn files and the journal are the audit trail: action, rolls, changes, model,
  token usage, world time, narration.

### Tools and mechanics

- Four attributes (Might, Agility, Insight, Presence), skills, health, stress,
  supplies, currency, conditions, inventory quantities.
- 2d6 + attribute + skill + modifier vs difficulty; `failure`, `mixed_success`,
  `success`.
- Tool-gated changes only: `roll`, `patch_character`, `patch_inventory`,
  `patch_clock`, `create_clock`, `advance_time`, `update_npc`, `update_faction`,
  `create_npc`, `create_location`, `reveal_npc`, `reveal_location`,
  `reveal_faction`, `record_fact`, `reveal_fact`, `append_journal`, `set_scene`,
  `request_world_turn`.
- `set_scene` reveals its destination; new places and people are introduced
  through tools rather than unmetered prose.
- Bounds and references are enforced server-side. A rejected call returns
  `ERROR: ...` to the model without aborting the turn. Identical tool effects are
  suppressed within a turn so a repeated loop cannot double-charge state.
- Time is a single anchor, not a stopwatch: at most one meaningful
  `advance_time` per turn; named clocks remain event-driven pressure.
- Rolls persist and display the attribute, skill, and their values; a completed
  clock archives its trigger as a fact and leaves active play.

### Context retrieval

- A derived BM25 index ranks NPCs, locations, factions, facts, and clocks without
  sending all canon to the model.
- The query combines the action, current location, present cast, and last
  narration. Present entities, NPC-known facts, selected NPC locations, and active
  clocks are always included.
- Narrator/world/audit use different quotas. The prompt reports selected-vs-total
  counts and says omitted canon is binding.
- `lookup_canon` searches the full state on demand for omitted people, places,
  factions, facts, or clocks.

### Creativity and variety

- Campaign generation receives a persisted six-part creative brief drawn with
  `secrets.SystemRandom`: setting, relationship, opening, pressure, texture, and
  wildcard. Each pool has 100 unique entries.
- Each player turn receives an optional randomized narrative lens from a 100-entry
  pool, avoiding the last four.
- The brief is shown in the Canon inspector; the lens is stored on each turn.
- `ATLAS_CREATIVE_BRIEFS` and `ATLAS_NARRATIVE_LENSES` can disable either layer.

### Agents

- Campaign generator: forced structured tool call (`submit_campaign`), tolerant of
  volunteered extra fields, retried once with validation feedback or incomplete
  JSON. Assigns fact ids and resolves NPC knowledge given as fact prose. Prompts
  contain no setting examples, keyword blacklists, or name avoid-lists.
- Narrator: one tool loop per player turn, retrieval-selected GM packet,
  recent-turn window, configurable model, wall-clock deadline, and one leak-repair
  pass.
- Player-view privacy: NPC attitudes/plans and faction goals/stances never reach
  the browser.
- World agent: offscreen evolution automatically after the turn/minute threshold,
  on narrator request, or via the manual override; updates clocks, factions, NPCs,
  and facts without narrating the player's scene.
- Auditor: on-demand structured findings with severity, summary, and evidence.
  Advisory only; no write tools.
- Fake provider: deterministic replies, generic demo seed, configurable audit
  findings. Default provider; no network, no credentials.

### API and UI

- FastAPI endpoints for health, config, campaign CRUD, player view, GM view,
  turns, streamed turn progress, world turn, and audit. Typed error envelope with
  stable codes.
- Svelte 5 + Vite + TypeScript UI: campaign list with delete confirmation,
  creation form, play view, narration transcript, action composer, character
  (with bio)/inventory/world/clocks/journal panels, GM modal with NPC plans and
  faction secrets, audit modal, token-usage modal, and a read-only Canon inspector
  with full state and turn records. Turns stream progress stages and an elapsed
  timer.
- FastAPI serves `web/dist`; Vite proxies `/api` in development.
- CLI: `list`, `demo`, `show`, and `serve`; `serve` honours `--data-dir` and
  `--provider` for both normal and reload modes.

## Verification evidence

Run on macOS, Python 3.12, Node 20+.

| Check | Result |
|---|---|
| `uv run pytest -q` | 91 passed |
| `uv run ruff check .` | clean |
| `uv run ruff format --check .` | 76 files already formatted |
| `uv run mypy` | no issues in 63 source files |
| `cd web && npm run check` | 0 errors, 0 warnings |
| `cd web && npm run build` | 137 modules transformed, build OK |

Automated tests use only the fake provider or a stub OpenAI client. They make no
network calls and need no credentials. Coverage includes:

- frontmatter round-trip, GM block stripping/extraction;
- dice outcomes and modifier math;
- roll records retaining the attribute, skill, and component values;
- tool bounds: inventory add/remove, health clamps, clock clamps, unknown tools,
  bad argument types, fact record/reveal;
- completed clocks archived as facts and removed from active clocks;
- one meaningful time advance per turn; a second call is rejected;
- campaign creation, generated start time and time-of-day label, file layout,
  player/GM separation, restart reload;
- seed validation: duplicate and slug-colliding ids, distinct character/NPC
  names, slug-normalized location references, fact-id assignment, prose knowledge
  resolution, unknown draft fields;
- store path-traversal rejection and partial directory handling;
- offline/live configuration gates, default Luna models, key requirements;
- multi-turn state carry-over, time, inventory, rolls, journal, turn files;
- hidden-fact leak rejection with no turn committed;
- short hidden facts remain protected;
- leak repair before commit, and repair that reveals a fact instead;
- hidden-name leaks matched on word boundaries, not inside ordinary words;
- leak errors never echo the protected text;
- player view omitting NPC attitudes and faction goals/stances;
- discovery and creation tools: new locations/NPCs, scene reveal, faction reveal;
- provider failure leaving files untouched;
- rejected tool call not aborting a turn;
- duplicate tool effects applying once per turn, including reworded clock reasons;
- tool-loop deadline and iteration limit;
- world turn clock changes hidden from player narration, world-turn files, and
  world turns loading after a player turn with the same number;
- automatic world turns after the configured player-turn interval;
- auditor findings and empty findings;
- campaign generation retry with validation feedback, failure after two tries,
  and a character-concept hint;
- context truncation preserving the player action and narrator instructions, plus
  character background, campaign notes, present NPCs, and time phase reaching the
  packet;
- BM25 retrieval selecting relevant people/facts out of 120 NPCs and 200 facts,
  excluding unrelated noise, keeping the packet bounded, and finding omitted canon
  through `lookup_canon`;
- OpenAI adapter request shape, tool call parsing, tool-result mapping, forced
  structured calls, pricing, and missing-tool errors;
- CLI settings overrides reaching the served app, and `demo` running without an
  explicit data directory;
- HTTP round-trip, 404, 422 validation, deletion;
- read-only canon endpoint exposing hidden facts, full NPC sheets, inventory, and
  complete turns;
- OS-random creative brief completeness/diversity, 100-unique-entry pool sizes,
  brief prompt injection and persistence, and narrative-lens non-repetition;
- streamed turn events ending in the committed turn result;
- token-usage aggregation by turn and model, plus the usage endpoint;
- built-in list prices for major models, dated-ID/alias resolution, known-model
  estimates, and custom fallback pricing for unknown models.

Manual smoke test (fake provider, built frontend):

1. `uv run atlas serve --port 8123` with `ATLAS_DATA_DIR` pointing at a temp dir.
2. `GET /healthz` → `provider: fake`, `live: false`.
3. `GET /` → 200 HTML from `web/dist`.
4. `POST /api/campaigns` with a premise → 201, campaign directory written.
5. `GET /api/campaigns/{id}/player` → opening scene, no hidden facts.
6. `GET /api/campaigns/{id}/gm` → hidden facts and GM blocks present.
7. `POST /api/campaigns/{id}/turns` → new turn, state changes.
8. Restart the server → `GET /api/campaigns` still lists the campaign and the
   transcript is intact.

Live OpenAI smoke test (GPT-6 Luna):

- `POST /api/campaigns` generated *Snowline at Split Fir* in 57.1 s
  (1,081 input / 4,989 output tokens), opening at Day 1, 16:45 with five known
  NPCs and four hidden facts.
- Two live empty-premise generations with independent random briefs produced
  *The Waxline at Bellweather Row* (printing-house neighborhood, beeswax,
  impossible broadsheet) and *The Black Rain Register* (dry-country pilgrim
  hostel, storm-washed ink, buried spring) — different settings, relationships,
  and pressures.
- The first player turn took 17.0 s (9,470 / 980 tokens) and produced a coherent
  NPC response, clock state, and no secret leak.
- A second campaign opened at Day 1, 05:20; asking about a hidden NPC triggered
  `reveal_npc`, and travelling to a hidden location triggered `set_scene` plus
  location discovery.
- A wound-care turn rolled `mixed_success`, consumed a dressing, reduced the
  wound clock, and revealed a fact. After duplicate suppression, a later turn
  produced no duplicate changes.
- One live world turn took 28.7 s and advanced hidden and visible clocks; the
  audit returned zero findings in 1.8 s.
- A risky climb ended in a failed roll, reduced health 6→5, advanced a hidden
  slope clock, moved the scene, and left the character stranded with a live
  consequence instead of killing them.
- A streamed live turn reported `reading → roll → advance_time → reveal_location →
  set_scene → update_npc → saving → done` in 38.1 s and committed the final
  result with a successful roll and new discovery.
- The usage endpoint reported 185,469 input / 15,117 output tokens across eight
  recorded turns for *Snowline at Split Fir*, with per-turn and model breakdown.
- Usage costs now come from the built-in price table: the live 15,724 / 1,367
  turn was estimated at **$0.002256** on GPT-6 Luna.
- Synthetic retrieval stress test: 1,002 NPCs and 5,003 facts produced a
  3,067-character packet with 2 NPCs and 3 facts in ~15 ms, including the relevant
  entity and excluding unrelated noise. Loading a 502-NPC / 2,003-fact campaign
  from markdown took ~0.4 s.
- A live turn against a 502-NPC / 2,003-fact campaign used 15,724 input / 1,367
  output tokens and produced a coherent Sable scene without noise facts.
- A live wait/travel scene advanced the anchor exactly once (+20m) and cost
  **$0.00733** at GPT-6 Luna list rates, confirming the one-time-advance rule and
  the new pricing table.
- Restarting the server preserved campaigns, turns, world time, and transcripts.

## Known limitations

- Narration is not token-streamed. The UI receives progress stages and then the
  committed turn; live turns have taken roughly 17–55 s.
- No campaign export/import.
- Retrieval is lexical BM25, not semantic. Synonyms may miss; names and
  `lookup_canon` compensate. The index is rebuilt each turn, and state loading
  still reads the full campaign directory.
- Player panels still render all known people/facts. Retrieval keeps the model
  context small; player-side pagination or a codex search is future work.
- Audit uses a wider retrieved packet, not necessarily every fact; it is a
  continuity aid, not a proof.
- Secret-leak detection is verbatim matching against GM fact text, GM prose
  blocks, and hidden names, followed by one repair pass. It is a backstop, not a
  semantic guarantee.
- Cost estimates use a built-in list-price table checked 2026-11-12. Long-context,
  promotional, peak/off-peak, cache, and regional rates are noted but not modeled;
  the standard short-context rate is used. Unknown model IDs use fallback rates.
  Session spend resets when the server restarts.
- Single-user localhost only. No auth, no remote hosting.

## Next steps

1. Add token-level narration streaming while preserving commit-time atomicity.
2. Add campaign export/import.
3. Replace verbatim leak matching with a model-side redaction pass or embedding
   similarity, then keep the verbatim check as a fast path.
4. Add a persisted or vector index and a rolling recap for very large worlds;
   current retrieval rebuilds in memory from markdown each turn.
5. Add an automated price-table refresh check against provider pricing pages.
