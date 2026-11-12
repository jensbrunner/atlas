# Retrieval and Context Selection

## Problem

A long campaign can contain thousands of people, places, facts, and clocks. Sending
all of them to the narrator every turn wastes tokens, pushes the action and
instructions out of the context window, and buries the relevant material.

ATLAS keeps canonical state in markdown, then builds a small, derived retrieval
index for each turn. Only a relevant packet goes to the model. A tool lets the
narrator ask for omitted canon on demand.

## Design

```text
markdown canon
   │
   ├─ character / world / NPC files / facts
   ▼
derived BM25 index (in memory, disposable)
   │
   ├─ query: action + current place + present cast + last narration
   ├─ rank: BM25 + exact-name boost
   ├─ expand: present scene, NPC knowledge, NPC locations, active clocks
   ▼
context packet (selected entities + omission counts)
   │
   ├─ prompt says: omitted canon is still binding
   └─ lookup_canon(query, kind) tool for on-demand expansion
```

### Indexed documents

| Kind | Indexed text |
|---|---|
| NPC | name, attitude, location, goals, plans, known facts, body |
| Location | name, description, tags |
| Faction | name, goal, stance, resources |
| Fact | text, tags |
| Clock | name, trigger |

The index is rebuilt from the in-memory `CampaignState`; markdown remains
canonical. It is not a second source of truth.

### Ranking

- BM25 over action and context query terms.
- Exact name or phrase match receives a large boost.
- A relative score cutoff drops weak matches. A query with only common words
  does not drag in hundreds of unrelated facts.
- Current location, present NPCs, and facts known by the selected cast are always
  included or strongly preferred.

### Selection quotas

| Mode | NPCs | Locations | Factions | Facts | Clocks |
|---|---:|---:|---:|---:|---:|
| Narrator | 6 | 4 | 4 | 12 | 6 |
| World | 10 | 6 | 6 | 20 | 10 |
| Audit | 14 | 8 | 8 | 30 | 12 |

Present NPCs, the current location, active clocks, and selected NPCs' known
facts are added before discretionary matches. Locations of selected NPCs are kept
for continuity. Quotas cap context regardless of canon size.

### Prompt contract

The packet includes a line such as:

```text
Context packet: 2/1002 npcs, 2/3 locations, 1/1 factions, 3/5003 facts, 1/2 clocks.
Canon not listed above is still binding. If you need an omitted person, place,
faction, fact, or clock, call `lookup_canon` with a name or keyword before using
it. Do not contradict omitted canon.
```

`lookup_canon` performs the same BM25 search against the full state and returns
compact NPC, location, faction, fact, or clock records. It is a tool call, so it
costs tokens only when the narrator needs it.

## Measured performance

Synthetic campaign: 1,002 NPCs, 5,003 facts, 3 locations, 1 faction, 2 clocks.

```text
index build: 15.8 ms
selection:   14.7 ms
prompt:      14.2 ms
packet:      2/1002 npcs, 2/3 locations, 1/1 factions, 3/5003 facts, 1/2 clocks
prompt size: 3,067 characters
relevant:    yes
noise:       excluded
```

A small campaign still sends nearly all canon because the quotas are not reached.
The savings grow with the world.

State loading is separate from retrieval: loading 502 NPC files and 2,003 facts
took about 406 ms on this machine. Retrieval and prompt assembly then cost ~15 ms
each. A persisted/lazy index is the next step if state loading becomes the
bottleneck.

## Tests

- `tests/unit/test_retrieval.py` builds 120 NPCs and 200 facts, then verifies:
  - the present NPC, relevant external NPC, and relevant fact are selected;
  - unrelated facts are omitted;
  - the prompt stays within budget and contains the lookup instruction;
  - `lookup_canon` finds omitted canon and reports misses cleanly.
- `tests/unit/test_context.py` verifies prompt truncation preserves the action and
  instructions while retrieval shrinks the context.

## Limitations

- Retrieval is lexical (BM25), not semantic. Synonyms and paraphrases may miss;
  `lookup_canon` and explicit names compensate.
- The index is rebuilt each turn. State loading still reads the full campaign
  directory; a persisted index would be the next step for very large worlds.
- Audit uses a wider packet but not necessarily every fact. It is a continuity
  aid, not a proof.
- Entity relationships are inferred from location, NPC knowledge, tags, and text;
  there is no general relationship graph yet.
- Player panels still list all known entities; retrieval efficiency applies to the
  model packet. Player-side pagination or a codex search is future work.
