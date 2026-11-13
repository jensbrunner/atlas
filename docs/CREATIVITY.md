# Creativity and Entropy

## Problem

A model asked to invent a campaign from the same neutral context tends to reach
for the same shapes: a civic inspection, a waterfront, a caravan, a missing
shipment, or a bell. The model is good at connecting a fresh specific idea to a
world; it is less reliable at producing the fresh idea itself.

## Solution

Use local OS randomness to supply **raw material**, then let the model connect it.

### Campaign creative brief

When a campaign is created, `atlas/creativity.py` draws one item from each of six
broad pools using `secrets.SystemRandom`:

- setting seed
- relationship seed
- opening seed
- pressure seed
- texture seed
- wildcard seed

The brief is appended to the campaign-generation input and stored in
`campaign.md` as `creative_brief`. The prompt asks the model to connect at least
three elements into one specific situation.

The pools are deliberately broad and mixed. They are not a list of preferred
settings and they are not a blacklist; the combination is random.

### Per-turn narrative texture

For each player turn, the harness draws a **narrative lens** from a separate pool,
avoiding the last four used. The lens is appended to the narrator packet as
optional texture:

- a small object changes hands
- a sound from outside the scene
- a smell tied to a specific person or place
- a routine task is interrupted
- a private moment is observed
- etc.

The narrator is told to weave it in only if it fits and never mention the
instruction. The lens is stored on the turn record and visible in the Canon
inspector.

## Why local randomness

- No extra model call or provider dependency.
- No network service or API key.
- The model still does the creative connection work.
- The brief is stored, so a campaign can be inspected after the fact.
- Disable with `ATLAS_CREATIVE_BRIEFS=false` or
  `ATLAS_NARRATIVE_LENSES=false`.

## What this does not do

- It does not guarantee uniqueness. Random combinations can still resemble each
  other.
- It does not filter or blacklist model output.
- It does not add randomness to world logic, dice, or state changes.
- It does not force a lens into a scene where it would break continuity.

## Verification

- `tests/unit/test_creativity.py` checks brief completeness, non-fixed output,
  and lens non-repetition.
- `tests/unit/test_campaign_generator.py` checks the brief reaches the generator.
- `tests/integration/test_campaign.py` checks the brief is persisted.
- `tests/integration/test_turns.py` checks a lens is recorded.
- Two live empty-premise generations produced different settings: a
  printing-house neighborhood and a dry-country pilgrim hostel.
