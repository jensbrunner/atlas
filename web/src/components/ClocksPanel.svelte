<script lang="ts">
  import type { Clock } from '../lib/api'

  let { clocks }: { clocks: Clock[] } = $props()
</script>

<section class="panel">
  <h3>Clocks</h3>
  {#if clocks.length === 0}
    <p class="muted">No visible pressure yet.</p>
  {:else}
    {#each clocks as clock (clock.id)}
      <div class="clock">
        <div class="head">
          <span>{clock.name}</span>
          <span class="faint">{clock.filled}/{clock.segments}</span>
        </div>
        <div class="pips">
          {#each Array(clock.segments) as _, index}
            <span class="pip" class:filled={index < clock.filled}></span>
          {/each}
        </div>
        {#if clock.trigger}
          <p class="trigger faint">{clock.trigger}</p>
        {/if}
      </div>
    {/each}
  {/if}
</section>

<style>
  h3 {
    margin: 0 0 0.9rem;
  }

  .clock {
    margin-bottom: 1.3rem;
  }

  .head {
    display: flex;
    justify-content: space-between;
    font-size: 0.9rem;
    margin-bottom: 0.4rem;
  }

  .pips {
    display: flex;
    gap: 0.3rem;
  }

  .pip {
    height: 8px;
    flex: 1;
    border-radius: 2px;
    background: #2c2621;
    border: 1px solid var(--line);
  }

  .pip.filled {
    background: var(--accent);
    border-color: var(--accent);
  }

  .trigger {
    margin: 0.4rem 0 0;
    font-size: 0.8rem;
    font-style: italic;
  }
</style>
