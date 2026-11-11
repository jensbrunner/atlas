# ATLAS

A local-first harness for AI-narrated solo roleplay.

The narrator is the game master. ATLAS is the table it works on: deterministic
dice, bounded state tools, plain-text persistence, a hidden GM view, a
player-facing view, and a localhost browser UI. There is no prewritten adventure,
no story branches in the engine, and no database.

> **Status:** the offline harness works end to end. Live OpenAI narration is
> implemented and opt-in, but has not been exercised against a real key in this
> repository yet.

## What it does

- You start a campaign from a short premise. A campaign generator invents the
  place, factions, NPCs, clocks, secrets, a player character, and an opening
  scene.
- You type an action in the browser. A narrator model reads the GM packet, calls
  tools when it needs to roll dice or change state, and writes the scene.
- Inventory, health, stress, clocks, time, NPCs, factions, facts, and the journal
  live in markdown files under `campaigns/<id>/`.
- Every mechanical change goes through a validated tool. A failed model call or
  invalid change leaves the files untouched.
- The server renders a player view by stripping GM-only material from the same
  canon the narrator sees. There is no second state copy to drift.
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
- A short skill list (Negotiation, Engineering, Confrontation, Survival by
  default; additional skills are allowed).
- `2d6 + attribute + skill + situational modifier` against a difficulty. The
  result is `failure`, `mixed_success`, or `success`.
- Health, stress, supplies, currency, conditions, inventory quantities.
- Named clocks with segments and triggers.
- World time in minutes.
- Factions, NPC goals/knowledge, and canonical facts with GM/player visibility.

The narrator decides when a roll is needed. The tool layer decides what is legal.

## Agents and cost

- **Narrator:** one model loop per player turn, plus tool round-trips. It cannot
  write state directly; it calls tools.
- **Campaign generator:** one structured call at campaign creation.
- **World agent:** only on a manual "Advance world" action or when the narrator
  asks for an offscreen turn. It does not narrate the player's scene.
- **Continuity auditor:** on demand. Advisory only; it has no write tools.

Context is assembled from the GM packet with recent-turn and character budgets.
Every turn records token usage.

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

The automated suite uses only the fake provider. It makes no network calls and
requires no credentials.

## Not in this slice

- Narration streaming (the UI waits for a committed turn).
- Campaign export/import and deletion confirmation in the UI.
- Automatic time-threshold world turns; world evolution is manual or
  narrator-requested.
- Semantic secret-leak detection. The current check is verbatim matching against
  GM fact text, GM prose blocks, and hidden NPC names.
- Multi-user or remote access. This is a localhost, single-user harness.
