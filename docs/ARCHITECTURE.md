# Architecture

ATLAS is a thin, local harness around a narrator model. The model is the game
master; the harness supplies memory, dice, validated state changes, persistence,
and two renderings of the same canon.

```text
Browser (Svelte 5 + Vite)
   │  player action, panel reads
   ▼
FastAPI app (atlas/app.py)
   │  loads a campaign directory into memory
   │  builds a budgeted GM packet (atlas/context.py)
   ▼
Narrator agent (OpenAI Responses API, default gpt-6-luna)
   │  tool calls: roll, patch state, advance time, journal, reveal, world turn
   ▼
Deterministic tool layer (atlas/tools/)
   │  validates each change against in-memory state
   ▼
Commit: atomic markdown writes + append-only turn file + journal entry
   │
   └─► player view renderer (atlas/state/render.py), GM blocks stripped
```

## Modules

```text
atlas/
  config.py            env settings; live calls are opt-in
  app.py               FastAPI factory, CORS, typed errors, static SPA serving
  game.py              CampaignService: generation, turns, world turns, audit
  context.py           budgeted GM packet assembly
  errors.py            typed harness errors
  ids.py               ids and slugs

  api/
    routes.py          HTTP endpoints
    schemas.py         request bodies and error envelope

  agents/
    types.py           provider protocol, messages, tool calls, usage
    providers.py       OpenAI Responses adapter
    fake.py            deterministic offline provider and demo seed
    loop.py            provider-agnostic tool loop
    narrator.py        one player turn
    campaign.py        structured campaign generation
    world.py           offscreen evolution
    auditor.py         structured continuity findings
    prompts/           narrator, campaign, world, and auditor instructions

  state/
    schemas.py         Pydantic models for all structured state
    markdown.py        frontmatter parse/serialize, GM block stripping
    store.py           atomic file writes, load, create, append turn
    render.py          player and GM views
    validate.py        structural and numeric invariants

  tools/
    registry.py        tool schemas and dispatch
    dice.py            deterministic 2d6 resolution
    character.py       health, stress, supplies, currency, conditions
    inventory.py       add/remove/set item quantities
    clocks.py          clock creation and advancement
    time.py            world time
    facts.py           facts, reveals, journal
    npcs.py            NPCs and factions
    world.py           scene changes, world-turn requests

web/
  src/lib/api.ts       typed API client
  src/routes/          campaign list/create and play view
  src/components/      narration, composer, panels, GM view, audit
```

## Turn lifecycle

1. `POST /api/campaigns/{id}/turns` with `{action}`.
2. Acquire the per-campaign in-process lock.
3. Load the campaign directory into a `CampaignState` in memory.
4. Build the GM packet: campaign premise, character, world, NPCs, clocks, facts,
   and recent turns, within a character budget.
5. Run the narrator loop. Each provider call may return tool calls; tools mutate
   the in-memory state and return results to the model. Identical tool effects are
   ignored within the turn, and the loop has a wall-clock deadline.
6. Take the final assistant text as narration.
7. If the leak scan trips, run one repair pass: the narrator may reveal what was
   genuinely discovered with a discovery tool, or rewrite without it.
8. Reject the turn if narration is still empty or leaking, or if the resulting
   state violates an invariant.
9. Write changed state files atomically (`os.replace`).
10. Append `turns/NNNN.md` and the player-facing `journal.md` entry.
11. Return the narration, rolls, changes, usage, and a fresh player view.

If the model call fails, a tool raises an unexpected error, the leak scan still
trips after repair, or validation fails, nothing is written. A rejected tool call
is returned to the model as `ERROR: ...`; it does not abort the turn by itself.

If the narrator calls `request_world_turn`, the player turn is committed first,
then a world turn runs. A failed world turn never erases the committed player
turn.

## State files

- `campaign.md` — campaign metadata and prose notes.
- `character.md` — player sheet and inventory.
- `world.md` — locations, factions, clocks, facts, situation, prose/GM blocks.
- `npcs/<slug>.md` — NPC sheet, goals, plans, knowledge, description, GM block.
- `journal.md` — player-facing log.
- `turns/NNNN.md` — opening and player turns.
- `turns/NNNN-world.md` — offscreen world turns.

Structured fields are YAML frontmatter validated by Pydantic. Prose may contain
`<!-- gm --> ... <!-- /gm -->` blocks. Facts use `visibility: gm|player`; NPCs
and locations use `player_known`; clocks use `visibility`.

## Views

`atlas/state/render.py` derives both views from the same `CampaignState`:

- **Player view:** character sheet and description, inventory, player-known
  locations, faction names, NPC names/locations/descriptions, player-visible
  clocks, revealed facts, stripped journal, and the opening plus player turns.
  NPC attitudes, goals, plans, knowledge, secrets, faction goals/stances, and full
  sheets are omitted.
- **GM view:** everything, including hidden facts, all clocks, NPC goals/plans/
  knowledge, faction goals/resources, GM prose blocks, raw journal, and world
  turns.

The server renders the player view. The frontend never receives GM fields it
could accidentally display.

## Tools

| Tool | Purpose |
|---|---|
| `roll` | 2d6 + attribute + skill + modifier vs difficulty; records the roll |
| `patch_character` | health, stress, supplies, currency, conditions |
| `patch_inventory` | add/remove/set item quantities |
| `patch_clock` / `create_clock` | pressure clocks |
| `advance_time` | in-world minutes |
| `update_npc` / `update_faction` | location, attitude, goals, plans, knowledge, resources |
| `create_npc` / `create_location` | introduce new people and places |
| `reveal_npc` / `reveal_location` / `reveal_faction` | mark discoveries |
| `record_fact` / `reveal_fact` | canonical facts and secrets |
| `append_journal` | short player-facing journal note |
| `set_scene` | move scene, reveal the destination, update location/situation |
| `request_world_turn` | queue offscreen evolution after the turn |

Every tool has a closed JSON schema and returns a short result string. Bounds are
enforced in the handler: non-negative inventory, bounded health/stress/clocks,
known entity references, monotonic world time, valid fact/NPC references.

## Agents and cost

- The narrator is one provider loop per turn. `max_tool_iterations` caps the loop,
  `ATLAS_TURN_DEADLINE_SECONDS` caps wall time, and identical tool effects are
  suppressed within a turn.
- A rejected narration gets one leak-repair provider pass.
- The campaign generator is one structured tool call, retried once with the
  validation error if the seed is malformed. Tolerant draft models ignore unknown
  volunteered fields.
- The world agent is invoked only manually or when the narrator requests it.
- The auditor is invoked only on demand and returns structured findings.
- Recent turns and total prompt characters are budgeted.
- Token usage is stored in every turn file and returned by the API. The OpenAI
  client uses `ATLAS_REQUEST_TIMEOUT_SECONDS` and no hidden SDK retries.
- Startup time is stored as `world_time_minutes`; the generator chooses a
  plausible `start_minute` for the opening.
- `ATLAS_SESSION_USD_LIMIT` is checked against accumulated estimated cost. Set
  `ATLAS_INPUT_USD_PER_MILLION` and `ATLAS_OUTPUT_USD_PER_MILLION` to price
  tokens. With the default zero rates the estimate stays at zero, so the cap
  does not trigger; the fake provider always costs nothing.

## Failure semantics

- **Provider failure:** no files change; the API returns `502 provider_error`.
- **Empty narration:** no files change; `502 empty_narration`.
- **Leak detected:** one repair pass; if it still leaks, no files change and the
  API returns `422 content_leak`.
- **Invalid state:** no files change; `422 invalid_state`.
- **Unknown campaign:** `404 not_found`.
- **Invalid request body or action:** `422 invalid_request`.
- **Budget cap:** `402 budget_exceeded`.

## Frontend

Svelte 5 + Vite + TypeScript, no SvelteKit. The play view is a two-column layout:
transcript and composer on the left, tabbed panels on the right. The GM view and
audit are modal panels. Development uses a Vite proxy to FastAPI; production
serves `web/dist` from FastAPI. There is no streaming in this slice: narration
appears after the turn commits.
