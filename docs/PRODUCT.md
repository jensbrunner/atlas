# Product

ATLAS is a harness for solo roleplay with an AI narrator. It is not a game engine
with a story inside it. It is the surface a model needs to run a persistent
world: memory, dice, bounded state changes, a hidden GM view, a player view, and
a place to write.

## The experience

1. The player describes a situation they want to play.
2. A campaign generator invents a place, the people in it, what they want, and
   the pressure already in motion.
3. The opening scene appears in the browser.
4. The player types actions. A narrator model adjudicates and writes the scene,
   calling tools for rolls, injuries, inventory, time, clocks, factions, facts,
   and NPCs.
5. The side panels show the player character, inventory, world, clocks, and
   journal, all read from the same text files the narrator uses.
6. Time can pass offscreen. A world agent advances factions and clocks without
   the player's input.
7. A continuity auditor can flag contradictions on demand.

## Principles

- **The narrator is the game master.** Code does not decide the story, the
  outcome of a scene, or which path is correct.
- **Text is canonical.** A campaign is a directory of markdown files. There is no
  database and no event-sourced ledger.
- **One canon, two views.** The GM view contains secrets. The player view is
  rendered by stripping GM material. They cannot drift because only one copy is
  edited.
- **Tools are the only hands.** The narrator proposes changes; the harness
  validates and applies them. Narration alone never changes state.
- **Atomic turns.** A failed call or invalid change leaves the campaign where it
  was.
- **Player agency.** The narrator controls the world and every NPC, never the
  player character's voluntary actions, speech, or thoughts.
- **Cost discipline.** One narrator loop per turn. World and audit calls only on
  demand. No per-turn committee of agents.
- **Offline by default.** Tests and development use a deterministic fake
  provider. Live model use is explicit opt-in.

## What this is not

- Not a prewritten adventure, campaign setting, or branching story.
- Not a tactical combat simulator.
- Not a multi-user server or a hosted product.
- Not a claim that model output is authoritative. State changes are
  tool-gated and validated.
- Not a guarantee that a model will never leak a secret. The leak scan is a
  backstop, not a proof.

## First acceptance milestone

"Start a campaign": create one from a premise, see the opening scene in the
browser, play a turn with a roll and a state change, inspect the panels, restart
the server, and continue from the same text files — with no database and no
prewritten adventure.
