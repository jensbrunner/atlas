# Time and Clocks

## Question

Is a separate time system worth having, or should the narrator handle time
naturally?

## Assessment

The useful part is a **persistent time anchor**, not a minute-by-minute clock.
Cross-turn chronology matters for:

- the journal and turn files;
- deadlines and "before the storm" pressure;
- offscreen world turns;
- the UI showing whether it is dawn, evening, or the next day.

The narrator is good at deciding how long a scene takes. It does not need a
bookkeeping system that asks it to account for every exchange.

## Decision

Keep one canonical value, `world_time_minutes`, and one tool, `advance_time`.
Use it for meaningful intervals, not routine conversation.

- The narrator may call `advance_time` **at most once per turn**.
- The tool rejects a second call in the same turn and tells the model to combine
  the elapsed time.
- The prompt says time is an anchor, not a stopwatch.
- Scene-level time is carried by prose ("by the time the storm breaks", "the next
  morning"); the anchor is only updated when a meaningful interval passes.
- Named clocks remain separate. They are **event pressure**, not wall time:
  `patch_clock` advances when the fiction earns it, not on a timer.
- The world agent runs automatically after the turn interval or in-world minute
  threshold, so time passing also has offscreen consequences without a button
  click. The manual "World now" control is only an override.

This keeps the benefits of chronology without turning play into time
bookkeeping. Removing the anchor entirely would make clocks, deadlines, world
turns, and the journal less verifiable.

## What is deliberately not modeled

- Time zones, calendars, and exact travel tables.
- Automatic clock ticks per minute or per turn.
- A second "scene phase" state; the phase is derived from the anchor.
- Requiring the narrator to mention a clock time in prose. Numeric clock times
  are avoided in player-facing narration.

## Verification

- `tests/unit/test_tools.py::test_advance_time_is_once_per_turn` verifies the
  one-call rule and that time does not double-advance.
- `tests/unit/test_context.py` verifies the time phase reaches the narrator.
- Live turns show time advancing in meaningful increments (minutes to hours) and
  the journal/usage views retaining the anchor.
