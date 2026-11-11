<script lang="ts">
  import type { PlayerView } from '../lib/api'

  let { view, pending = false }: { view: PlayerView; pending?: boolean } = $props()

  let scroller = $state<HTMLDivElement | null>(null)

  $effect(() => {
    // Re-scroll when the transcript or pending state changes.
    void view.turns.length
    void pending
    if (scroller) {
      requestAnimationFrame(() => {
        if (scroller) scroller.scrollTop = scroller.scrollHeight
      })
    }
  })
</script>

<div class="transcript" bind:this={scroller}>
  {#each view.turns as turn (turn.turn + '-' + turn.kind)}
    <article class="turn" class:opening={turn.kind === 'opening'}>
      {#if turn.kind === 'opening'}
        <div class="opening-label">Prologue</div>
      {:else}
        <div class="action"><span class="chev">›</span> {turn.action}</div>
      {/if}
      <div class="prose narration">{turn.narration}</div>
      {#if turn.rolls?.length}
        <div class="rolls">
          {#each turn.rolls as roll}
            <span class="roll {roll.outcome}">
              {roll.label}: {roll.dice[0]}+{roll.dice[1]}
              {roll.modifier >= 0 ? '+' : ''}{roll.modifier} = {roll.total}
              vs {roll.difficulty} · {roll.outcome.replace('_', ' ')}
            </span>
          {/each}
        </div>
      {/if}
    </article>
  {/each}

  {#if pending}
    <div class="thinking">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span>The world is considering its answer…</span>
    </div>
  {/if}
</div>

<style>
  .transcript {
    flex: 1;
    overflow-y: auto;
    padding: 2rem clamp(1rem, 4vw, 3.5rem) 2rem;
    scroll-behavior: smooth;
  }

  .turn {
    max-width: 760px;
    margin: 0 auto 2.6rem;
  }

  .opening {
    margin-bottom: 3rem;
  }

  .opening-label {
    font-family: var(--sans);
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 0.8rem;
  }

  .action {
    font-size: 0.92rem;
    color: var(--muted);
    border-left: 2px solid var(--accent-soft);
    padding: 0.15rem 0 0.15rem 0.8rem;
    margin-bottom: 1rem;
  }

  .chev {
    color: var(--accent);
  }

  .narration {
    margin: 0;
  }

  .rolls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 1rem;
  }

  .roll {
    font-size: 0.75rem;
    font-family: var(--mono);
    color: var(--muted);
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 0.25rem 0.5rem;
  }

  .roll.success {
    color: var(--good);
    border-color: rgba(127, 176, 131, 0.4);
  }

  .roll.failure {
    color: var(--danger);
    border-color: rgba(212, 114, 94, 0.4);
  }

  .thinking {
    max-width: 760px;
    margin: 0 auto 2rem;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    color: var(--muted);
    font-size: 0.9rem;
    font-style: italic;
  }

  .dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse 1.2s infinite ease-in-out;
  }

  .dot:nth-child(2) {
    animation-delay: 0.15s;
  }

  .dot:nth-child(3) {
    animation-delay: 0.3s;
    margin-right: 0.4rem;
  }

  @keyframes pulse {
    0%,
    80%,
    100% {
      opacity: 0.25;
      transform: translateY(0);
    }
    40% {
      opacity: 1;
      transform: translateY(-2px);
    }
  }
</style>
