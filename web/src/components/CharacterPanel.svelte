<script lang="ts">
  import type { Character } from '../lib/api'

  let { character }: { character: Character } = $props()

  const attributes = $derived([
    ['Might', character.attributes.might],
    ['Agility', character.attributes.agility],
    ['Insight', character.attributes.insight],
    ['Presence', character.attributes.presence],
  ] as Array<[string, number]>)

  const skills = $derived(Object.entries(character.skills ?? {}).sort((a, b) => b[1] - a[1]))
</script>

<section class="panel">
  <h3>{character.name}</h3>
  <p class="concept muted">{character.concept}</p>

  <div class="stats">
    {#each attributes as [label, value]}
      <div class="stat">
        <span class="value">{value >= 0 ? '+' : ''}{value}</span>
        <span class="label">{label}</span>
      </div>
    {/each}
  </div>

  <div class="track">
    <div class="track-head"><span>Health</span><span>{character.health.current}/{character.health.max}</span></div>
    <div class="meter danger">
      <span style="width: {(character.health.current / character.health.max) * 100}%"></span>
    </div>
  </div>

  <div class="track">
    <div class="track-head"><span>Stress</span><span>{character.stress.current}/{character.stress.max}</span></div>
    <div class="meter">
      <span style="width: {(character.stress.current / character.stress.max) * 100}%"></span>
    </div>
  </div>

  <div class="counts">
    <div><span class="muted">Supplies</span><strong>{character.supplies}</strong></div>
    <div><span class="muted">Currency</span><strong>{character.currency}</strong></div>
  </div>

  {#if skills.length}
    <h4>Skills</h4>
    <div class="skills">
      {#each skills as [name, value]}
        <span class="tag">{name} {value >= 0 ? '+' : ''}{value}</span>
      {/each}
    </div>
  {/if}

  {#if character.conditions.length}
    <h4>Conditions</h4>
    <ul class="conditions">
      {#each character.conditions as condition}
        <li>{condition}</li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  h3 {
    margin: 0 0 0.15rem;
    font-size: 1.35rem;
  }

  .concept {
    margin: 0 0 1.25rem;
    font-size: 0.88rem;
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.4rem;
    margin-bottom: 1.2rem;
  }

  .stat {
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 0.5rem 0.2rem;
    text-align: center;
  }

  .value {
    display: block;
    font-family: var(--serif);
    font-size: 1.1rem;
    color: var(--accent);
  }

  .label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }

  .track {
    margin-bottom: 0.8rem;
  }

  .track-head {
    display: flex;
    justify-content: space-between;
    font-size: 0.78rem;
    color: var(--muted);
    margin-bottom: 0.25rem;
  }

  .counts {
    display: flex;
    gap: 1.6rem;
    margin: 1.1rem 0;
  }

  .counts div {
    display: flex;
    flex-direction: column;
  }

  .counts strong {
    font-family: var(--serif);
    font-size: 1.2rem;
  }

  h4 {
    margin: 1.2rem 0 0.5rem;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
  }

  .skills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }

  .conditions {
    margin: 0;
    padding-left: 1.1rem;
  }
</style>
