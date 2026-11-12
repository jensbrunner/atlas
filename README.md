# ATLAS

A local-first harness for AI-narrated solo roleplay.

The narrator is the game master. ATLAS is the table it works on: deterministic
dice, bounded state tools, plain-text persistence, a hidden GM view, a
player-facing view, and a localhost browser UI. There is no prewritten adventure,
no story branches in the engine, and no database.

> **Status:** live GPT-6 Luna campaigns have been generated and played end to
> end. The default remains the offline fake provider; live calls are opt-in.

## What it does

- You start a campaign from a short premise. A campaign generator invents the
  place, factions, NPCs, clocks, secrets, a player character, an opening scene,
  and a plausible starting time.
- You type an action in the browser. A narrator model reads the GM packet, calls
  tools when it needs to roll dice or change state, and writes the scene.
- Inventory, health, stress, clocks, time, NPCs, factions, facts, and the journal
  live in markdown files under `campaigns/<id>/`.
- Every mechanical change goes through a validated tool. A failed model call or
  invalid change leaves the files untouched.
- The narrator can introduce new places and people, and reveal hidden ones when
  the fiction reaches them.
- New campaigns are told to avoid names already used in your previous campaigns.
- If a draft leaks hidden material, the harness gives the narrator one repair
  pass: reveal what was genuinely discovered, or rewrite without it.
- The server renders a player view by stripping GM-only material from the same
  canon the narrator sees. NPC attitudes, NPC plans, faction goals, and hidden
  facts stay GM-side.
- The world can evolve offscreen through a world agent, and a continuity auditor
  can review the canon without rewriting it.

## Requirements

- macOS or Linux with Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ and npm (for the frontend)

## Quick start (offline, no API key)

```bash
uv sync --group dev
uv run atlas serve
```

In a second terminal:

```bash
cd web
npm install
npm run dev
```

Open <http://localhost:5173>. The default provider is `fake`, which creates a
deterministic demo campaign and returns fixed narration. No network calls are
made.

For a single production-style server:

```bash
cd web && npm run build && cd ..
uv run atlas serve
```

Open <http://127.0.0.1:8000>. FastAPI serves `web/dist` when it exists.

## Live narration (opt-in)

Live calls require all three: the OpenAI provider, a key, and explicit cloud
permission.

```bash
export ATLAS_PROVIDER=openai
export ATLAS_OPENAI_API_KEY=sk-...
export ATLAS_ALLOW_CLOUD=true
uv run atlas serve
```

Models are configurable:

```bash
export ATLAS_CAMPAIGN_MODEL=gpt-6-luna
export ATLAS_NARRATOR_MODEL=gpt-6-luna
export ATLAS_WORLD_MODEL=gpt-6-luna
export ATLAS_AUDITOR_MODEL=gpt-6-luna
```

ATLAS fails with a clear configuration error if cloud use is not allowed, the key
is missing, or the provider name is unknown. It does not silently substitute a
different model. The configured model is used as given; provider errors are
reported as `provider_error`.

Copy `.env.example` to `.env` for local overrides. Never commit `.env`.

## Campaign files

Each campaign is a directory of text files. Structured fields use YAML
frontmatter; prose lives below it.

```text
campaigns/<id>/
  campaign.md        # title, premise, tone, turn count, world time
  character.md       # player sheet, inventory, conditions
  world.md           # locations, factions, clocks, facts, situation
  npcs/<slug>.md     # NPC sheet, goals, knowledge, description, GM secrets
  journal.md         # player-facing chronological log
  turns/0000.md      # opening scene
  turns/0001.md      # player turns
  turns/0001-world.md# offscreen world turns (GM-facing)
```

- **Canon is the full GM view.** Files may contain `<!-- gm --> ... <!-- /gm -->`
  blocks and facts with `visibility: gm`.
- **The player view is derived on the server.** GM blocks are stripped, hidden
  facts and NPC knowledge are omitted, and locations/NPCs marked
  `player_known: false` do not appear at all.
- **A turn is all-or-nothing.** State is loaded into memory, tools mutate it, and
  files are written only after validation passes. A failed narration or rejected
  leak does not advance the campaign.
- **The journal and turn files are the audit trail.** They record the action,
  rolls, changes, model and usage, and the narration.

## Mechanics

Deliberately small:

- Four attributes: Might, Agility, Insight, Presence.
- A short, free-form skill list; the generator picks a handful suited to the
  character, and any skill name can carry an integer rating.
- `2d6 + attribute + skill + situational modifier` against a difficulty. The
  result is `failure`, `mixed_success`, or `success`.
- Health, stress, supplies, currency, conditions, inventory quantities. Health
  loss is concrete; at 0 the character is incapacitated rather than arbitrarily
  killed. Stress represents fear, guilt, and exhaustion.
- Named clocks with segments and triggers.
- World time in minutes, with a generated starting time.
- Factions, NPC goals/plans/knowledge, and canonical facts with GM/player visibility.
- Discovery tools for new or hidden locations, NPCs, factions, and facts.

The narrator decides when a roll is needed. The tool layer decides what is legal.

## Agents and cost

- **Narrator:** one model loop per player turn, plus tool round-trips. It cannot
  write state directly; it calls tools. A rejected draft gets one leak-repair
  pass. Identical tool effects are suppressed within a turn, and a turn has a
  wall-clock deadline.
- **Campaign generator:** one structured call, retried once with validation
  feedback if references or ids are malformed.
- **World agent:** only on a manual "Advance world" action or when the narrator
  asks for an offscreen turn. It does not narrate the player's scene.
- **Continuity auditor:** on demand. Advisory only; it has no write tools.

Context is assembled from the GM packet with recent-turn and character budgets.
Every turn records token usage. Set `ATLAS_INPUT_USD_PER_MILLION` and
`ATLAS_OUTPUT_USD_PER_MILLION` to price tokens; `ATLAS_SESSION_USD_LIMIT` then
stops a session that exceeds the configured estimate. With the default zero
rates, cost estimates stay at zero.

## HTTP API

```text
GET    /healthz
GET    /api/config
GET    /api/campaigns
POST   /api/campaigns                 {title?, prompt?, genre?, tone?}
GET    /api/campaigns/{id}
DELETE /api/campaigns/{id}
GET    /api/campaigns/{id}/player
GET    /api/campaigns/{id}/gm
GET    /api/campaigns/{id}/turns
POST   /api/campaigns/{id}/turns      {action}
POST   /api/campaigns/{id}/turns/stream {action}   # SSE progress + final result
POST   /api/campaigns/{id}/world-turn {reason?}
POST   /api/campaigns/{id}/audit
```

The player view never includes GM facts, NPC goals/knowledge, hidden entities, or
GM prose blocks. The GM view includes all of it and is intended for local
inspection only.

## CLI

```bash
uv run atlas list
uv run atlas demo --prompt "A harbor town with a missing shipment."
uv run atlas show <campaign-id>
uv run atlas serve --port 8000
```

`atlas demo` uses the fake provider and writes a real campaign directory, so you
can inspect the files without a key.

## Tests and checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
cd web && npm run check && npm run build
```

The automated suite uses the fake provider and a stub OpenAI client. It makes no
network calls and requires no credentials.

## Not in this slice

- Token-by-token narration streaming. The UI streams progress events (reading,
  rolling, updating, saving) and then commits the finished turn atomically.
- Campaign export/import.
- Automatic time-threshold world turns; world evolution is manual or
  narrator-requested.
- Semantic secret-leak detection. The check is verbatim matching against GM fact
  text, GM prose, and hidden names, followed by one narrator repair pass.
- Multi-user or remote access. This is a localhost, single-user harness.
