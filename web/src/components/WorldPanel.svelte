<script lang="ts">
  import type { Fact, NPC, WorldView } from '../lib/api'

  let {
    world,
    npcs,
    facts,
  }: { world: WorldView; npcs: NPC[]; facts: Fact[] } = $props()

  const locationNames = $derived(
    Object.fromEntries(world.locations.map((location) => [location.id, location.name])),
  )
</script>

<section class="panel">
  <h3>World</h3>
  <p class="situation">{world.situation}</p>

  <h4>Present</h4>
  <p class="muted">
    {world.location?.name ?? world.current_location}
    {#if world.location?.description}
      — {world.location.description}
    {/if}
  </p>

  {#if npcs.length}
    <h4>People</h4>
    <ul class="people">
      {#each npcs as npc (npc.id)}
        <li>
          <strong>{npc.name}</strong>
          {#if npc.location}
            <div class="faint small">at {locationNames[npc.location] ?? npc.location}</div>
          {/if}
          {#if npc.description}
            <p class="desc">{npc.description}</p>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  {#if world.factions.length}
    <h4>Factions</h4>
    <ul class="plain">
      {#each world.factions as faction (faction.id)}
        <li>
          <strong>{faction.name}</strong>
        </li>
      {/each}
    </ul>
  {/if}

  {#if world.locations.length}
    <h4>Known places</h4>
    <ul class="plain">
      {#each world.locations as location (location.id)}
        <li>
          <strong>{location.name}</strong>
          {#if location.description}
            <div class="faint small">{location.description}</div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  {#if facts.length}
    <h4>What you know</h4>
    <ul class="plain">
      {#each facts as fact (fact.id)}
        <li>{fact.text}</li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  h3 {
    margin: 0 0 0.8rem;
  }

  h4 {
    margin: 1.4rem 0 0.5rem;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
  }

  .situation {
    font-family: var(--serif);
    line-height: 1.7;
    white-space: pre-wrap;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    padding: 0.45rem 0;
    border-bottom: 1px solid var(--line);
  }

  li:last-child {
    border-bottom: none;
  }

  .small {
    font-size: 0.8rem;
    margin-top: 0.15rem;
  }

  .desc {
    margin: 0.3rem 0 0;
    font-size: 0.86rem;
    white-space: pre-wrap;
  }
</style>
