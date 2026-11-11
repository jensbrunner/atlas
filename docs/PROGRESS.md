# Progress

## Status

**Milestone reached: start a campaign.**

The local-first rebuild works end to end with the offline fake provider: generate
a campaign from a premise, read the opening scene, play a turn that rolls dice and
changes state, inspect the panels, open the hidden GM view, run an audit, restart
the server, and continue from the same markdown files.

Live narration through the OpenAI Responses API is implemented and gated behind
`ATLAS_PROVIDER=openai` + `ATLAS_OPENAI_API_KEY` + `ATLAS_ALLOW_CLOUD=true`. It
has **not** been exercised against a real key in this repository yet.

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
  `player_known: false` entities. The GM view exposes everything.
- Turn files and the journal are the audit trail: action, rolls, changes, model,
  token usage, world time, narration.

### Tools and mechanics

- Four attributes (Might, Agility, Insight, Presence), skills, health, stress,
  supplies, currency, conditions, inventory quantities.
- 2d6 + attribute + skill + modifier vs difficulty; `failure`, `mixed_success`,
  `success`.
- Tool-gated changes only: `roll`, `patch_character`, `patch_inventory`,
  `patch_clock`, `create_clock`, `advance_time`, `update_npc`, `update_faction`,
  `record_fact`, `reveal_fact`, `append_journal`, `set_scene`,
  `request_world_turn`.
- Bounds and references are enforced server-side. A rejected call returns
  `ERROR: ...` to the model without aborting the turn.

### Agents

- Campaign generator: one forced structured tool call (`submit_campaign`),
  validated by Pydantic before any file is written.
- Narrator: one tool loop per player turn, budgeted GM packet, recent-turn
  window, configurable model.
- World agent: offscreen evolution on manual request or narrator request; updates
  clocks, factions, NPCs, and facts without narrating the player's scene.
- Auditor: on-demand structured findings with severity, summary, and evidence.
  Advisory only; no write tools.
- Fake provider: deterministic replies, generic demo seed, configurable audit
  findings. Default provider; no network, no credentials.

### API and UI

- FastAPI endpoints for health, config, campaign CRUD, player view, GM view,
  turns, world turn, and audit. Typed error envelope with stable codes.
- Svelte 5 + Vite + TypeScript UI: campaign list and creation form, play view,
  narration transcript, action composer, character/inventory/world/clocks/journal
  panels, GM modal, audit modal.
- FastAPI serves `web/dist`; Vite proxies `/api` in development.
- CLI: `list`, `demo`, `show`, and `serve`; `serve` honours `--data-dir` and
  `--provider` for both normal and reload modes.

## Verification evidence

Run on macOS, Python 3.12, Node 20+.

| Check | Result |
|---|---|
| `uv run pytest -q` | 50 passed |
| `uv run ruff check .` | clean |
| `uv run ruff format --check .` | 57 files already formatted |
| `uv run mypy` | no issues in 49 source files |
| `cd web && npm run check` | 0 errors, 0 warnings |
| `cd web && npm run build` | 137 modules transformed, build OK |

Automated tests use only the fake provider or a stub OpenAI client. They make no
network calls and need no credentials. Coverage includes:

- frontmatter round-trip, GM block stripping/extraction;
- dice outcomes and modifier math;
- tool bounds: inventory add/remove, health clamps, clock clamps, unknown tools,
  bad argument types, fact record/reveal;
- campaign creation, file layout, player/GM separation, restart reload;
- seed validation: duplicate and slug-colliding ids, slug-normalized location
  references;
- store path-traversal rejection and partial directory handling;
- offline/live configuration gates, default Luna models, key requirements;
- multi-turn state carry-over, time, inventory, rolls, journal, turn files;
- hidden-fact leak rejection with no turn committed;
- hidden-name leaks matched on word boundaries, not inside ordinary words;
- leak errors never echo the protected text;
- provider failure leaving files untouched;
- rejected tool call not aborting a turn;
- world turn clock changes hidden from player narration, world-turn files, and
  world turns loading after a player turn with the same number;
- auditor findings and empty findings;
- OpenAI adapter request shape, tool call parsing, tool-result mapping, forced
  structured calls, pricing, and missing-tool errors;
- CLI settings overrides reaching the served app, and `demo` running without an
  explicit data directory;
- HTTP round-trip, 404, 422 validation, deletion.

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

Live wiring smoke test (no model request): with `ATLAS_PROVIDER=openai`,
`ATLAS_ALLOW_CLOUD=true`, and a dummy key, `/healthz` reports `live: true` and
`/api/config` reports the four Luna models. Only a real key and provider
availability remain unverified.

## Known limitations

- No narration streaming; the UI waits for a committed turn.
- No campaign export/import, and no delete confirmation in the UI.
- World turns are manual or narrator-requested; no time-threshold automation.
- Context is a recent-turn window plus budgets, not retrieval over long
  campaigns.
- Secret-leak detection is verbatim matching against GM fact text, GM prose
  blocks, and hidden NPC names. It is a backstop, not a semantic guarantee.
- USD estimates use an optional static price table
  (`ATLAS_INPUT_USD_PER_MILLION` / `ATLAS_OUTPUT_USD_PER_MILLION`). No per-model
  price presets are bundled, so the session cap is inert until rates are set,
  and session spend resets when the server restarts.
- Single-user localhost only. No auth, no remote hosting.
- Live OpenAI behavior (model availability, tool-call format, structured output)
  is unverified without a key.

## Next steps

1. Live smoke test with an API key: campaign generation, three player turns with a
   roll and an inventory change, one world turn, one audit. Record actual model
   IDs and any adapter fixes.
2. Add per-model price presets so `ATLAS_SESSION_USD_LIMIT` is meaningful without
   hand-entering rates.
3. Add SSE streaming for narration while keeping commit-time atomicity.
4. Add UI deletion with confirmation and campaign export/import of the directory.
5. Replace verbatim leak matching with a model-side redaction pass or embedding
   similarity, then keep the verbatim check as a fast path.
6. Add retrieval over old turns once campaigns run long enough to exceed the
   context budget.
