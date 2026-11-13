<script lang="ts">
  import { onMount } from 'svelte'
  import { getCanon, type CanonNPC, type CanonView } from '../lib/api'
  import Modal from './Modal.svelte'

  let { campaignId, onClose }: { campaignId: string; onClose: () => void } = $props()

  type Tab =
    | 'overview'
    | 'character'
    | 'world'
    | 'people'
    | 'factions'
    | 'clocks'
    | 'facts'
    | 'journal'
    | 'turns'

  const tabs: Array<[Tab, string]> = [
    ['overview', 'Overview'],
    ['character', 'Character'],
    ['world', 'World'],
    ['people', 'People'],
    ['factions', 'Factions'],
    ['clocks', 'Clocks'],
    ['facts', 'Facts'],
    ['journal', 'Journal'],
    ['turns', 'Turns'],
  ]

  let data = $state<CanonView | null>(null)
  let error = $state<string | null>(null)
  let tab = $state<Tab>('overview')

  onMount(async () => {
    try {
      data = await getCanon(campaignId)
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
    }
  })

  function text(value: unknown): string {
    return typeof value === 'string' ? value : ''
  }

  function list(value: unknown): string[] {
    return Array.isArray(value) ? value.map(String) : []
  }

  function object(value: unknown): Record<string, number> {
    return value && typeof value === 'object' ? (value as Record<string, number>) : {}
  }

  function npcName(npc: CanonNPC): string {
    return text(npc.sheet.name) || npc.id
  }

  function npcAttributes(npc: CanonNPC): Array<[string, number]> {
    return Object.entries(object(npc.sheet.attributes))
  }

  function npcSkills(npc: CanonNPC): Array<[string, number]> {
    return Object.entries(object(npc.sheet.skills))
  }

  function fmt(value: number): string {
    return new Intl.NumberFormat().format(value)
  }
</script>

<Modal title="Canon / world data" wide onClose={onClose}>
  {#if error}
    <p class="error">{error}</p>
  {:else if !data}
    <p class="muted">Reading the campaign canon…</p>
  {:else}
    <div class="toolbar">
      <span class="badge">inspection only</span>
      <span class="muted">
        {data.counts.npcs} people · {data.counts.locations} places ·
        {data.counts.factions} factions · {data.counts.clocks} clocks ·
        {data.counts.facts} facts · {data.counts.turns} turns
      </span>
    </div>

    <nav class="tabs" aria-label="Canon sections">
      {#each tabs as [id, label]}
        <button class:active={tab === id} onclick={() => (tab = id)}>{label}</button>
      {/each}
    </nav>

    <div class="content">
      {#if tab === 'overview'}
        <section class="grid">
          <div><span class="label">Title</span><strong>{data.campaign.title}</strong></div>
          <div><span class="label">Campaign ID</span><span class="mono">{data.campaign.id}</span></div>
          <div><span class="label">Genre</span><span>{data.campaign.genre || '—'}</span></div>
          <div><span class="label">Tone</span><span>{data.campaign.tone || '—'}</span></div>
          <div><span class="label">Time</span><span>{data.campaign.time_of_day} · {data.campaign.world_time}</span></div>
          <div><span class="label">Turns</span><span>{data.campaign.turn_count}</span></div>
          <div><span class="label">Narrator model</span><span class="mono">{data.campaign.narrator_model}</span></div>
          <div><span class="label">Created</span><span>{data.campaign.created_at}</span></div>
        </section>
        <h4>Premise</h4>
        <p class="prose">{data.campaign.premise || '—'}</p>
        {#if data.campaign.creative_brief}
          <h4>Creative brief</h4>
          <pre>{data.campaign.creative_brief}</pre>
        {/if}
        {#if data.notes.campaign}
          <h4>Campaign notes</h4>
          <pre>{data.notes.campaign}</pre>
        {/if}
        {#if data.notes.world}
          <h4>World notes</h4>
          <pre>{data.notes.world}</pre>
        {/if}
        {#if data.notes.character}
          <h4>Character notes</h4>
          <pre>{data.notes.character}</pre>
        {/if}
      {:else if tab === 'character'}
        <h3>{data.character.name}</h3>
        <p class="muted">{data.character.concept}</p>
        {#if data.character.description}
          <p class="prose">{data.character.description}</p>
        {/if}
        <div class="attributes">
          {#each Object.entries(data.character.attributes) as [name, value]}
            <div><span class="label">{name}</span><strong>{value >= 0 ? '+' : ''}{value}</strong></div>
          {/each}
        </div>
        <h4>Skills</h4>
        <p>{Object.entries(data.character.skills).map(([name, value]) => `${name} ${value >= 0 ? '+' : ''}${value}`).join(' · ') || 'none'}</p>
        <div class="track-row">
          <span>Health {data.character.health.current}/{data.character.health.max}</span>
          <span>Stress {data.character.stress.current}/{data.character.stress.max}</span>
          <span>Supplies {data.character.supplies}</span>
          <span>Currency {data.character.currency}</span>
        </div>
        <h4>Conditions</h4>
        <p>{data.character.conditions.join(', ') || 'none'}</p>
        <h4>Inventory</h4>
        <ul class="plain">
          {#each data.inventory as item (item.id)}
            <li>
              <strong>{item.name}</strong> ×{item.quantity}
              {#if item.tags.length}<span class="faint"> · {item.tags.join(', ')}</span>{/if}
              {#if item.description}<div class="faint small">{item.description}</div>{/if}
            </li>
          {/each}
        </ul>
      {:else if tab === 'world'}
        <h4>Current situation</h4>
        <p class="prose">{data.world.situation || '—'}</p>
        <p class="muted">Current location: {data.world.current_location}</p>
        <h4>Locations</h4>
        <ul class="plain">
          {#each data.world.locations as location (location.id)}
            <li>
              <strong>{location.name}</strong>
              <span class="badge {location.player_known ? 'player' : 'gm'}">
                {location.player_known ? 'known' : 'hidden'}
              </span>
              <span class="faint mono">{location.id}</span>
              {#if location.description}<div class="small">{location.description}</div>{/if}
            </li>
          {/each}
        </ul>
      {:else if tab === 'people'}
        {#each data.npcs as npc (npc.id)}
          <details class="entry">
            <summary>
              <strong>{npcName(npc)}</strong>
              <span class="faint mono"> {npc.id}</span>
              <span class="badge {npc.sheet.player_known ? 'player' : 'gm'}">
                {npc.sheet.player_known ? 'known' : 'hidden'}
              </span>
            </summary>
            <div class="entry-body">
              <p class="muted">
                {text(npc.sheet.location) || 'unknown location'} · {text(npc.sheet.attitude) || 'no attitude'}
              </p>
              <div class="attributes">
                {#each npcAttributes(npc) as [name, value]}
                  <div><span class="label">{name}</span><strong>{value >= 0 ? '+' : ''}{value}</strong></div>
                {/each}
              </div>
              <p><span class="label">Skills</span> {npcSkills(npc).map(([name, value]) => `${name} ${value >= 0 ? '+' : ''}${value}`).join(' · ') || 'none'}</p>
              <p><span class="label">Goals</span> {list(npc.sheet.goals).join('; ') || 'none'}</p>
              <p><span class="label">Plans</span> {list(npc.sheet.plans).join('; ') || 'none'}</p>
              <p><span class="label">Knows</span> {list(npc.sheet.knows).join(', ') || 'nothing recorded'}</p>
              {#if npc.notes}<pre>{npc.notes}</pre>{/if}
            </div>
          </details>
        {/each}
      {:else if tab === 'factions'}
        {#each data.world.factions as faction (faction.id)}
          <article class="entry">
            <header class="entry-head">
              <strong>{faction.name}</strong>
              <span class="faint mono"> {faction.id}</span>
              <span class="badge {faction.player_known ? 'player' : 'gm'}">
                {faction.player_known ? 'known' : 'hidden'}
              </span>
            </header>
            <p><span class="label">Stance</span> {faction.stance || '—'}</p>
            <p><span class="label">Goal</span> {faction.goal || '—'}</p>
            <p><span class="label">Resources</span> {Object.entries(faction.resources).map(([name, value]) => `${name} ${value}`).join(' · ') || 'none'}</p>
          </article>
        {/each}
      {:else if tab === 'clocks'}
        {#each data.world.clocks as clock (clock.id)}
          <article class="entry">
            <header class="entry-head">
              <strong>{clock.name}</strong>
              <span class="faint mono"> {clock.id}</span>
              <span class="badge {clock.visibility}">{clock.visibility}</span>
            </header>
            <p>{clock.filled}/{clock.segments} segments</p>
            <div class="pips">
              {#each Array(clock.segments) as _, index}
                <span class="pip" class:filled={index < clock.filled}></span>
              {/each}
            </div>
            {#if clock.trigger}<p class="muted">{clock.trigger}</p>{/if}
          </article>
        {/each}
      {:else if tab === 'facts'}
        <ul class="plain">
          {#each data.world.facts as fact (fact.id)}
            <li>
              <span class="badge {fact.visibility}">{fact.visibility}</span>
              <span class="mono faint">{fact.id}</span>
              <div>{fact.text}</div>
              {#if fact.tags.length}<div class="faint small">{fact.tags.join(', ')}</div>{/if}
            </li>
          {/each}
        </ul>
      {:else if tab === 'journal'}
        <pre class="journal">{data.journal || 'No journal entries yet.'}</pre>
      {:else if tab === 'turns'}
        {#each [...data.turns].reverse() as turn, index (`${turn.turn}-${turn.kind}-${index}`)}
          <details class="entry">
            <summary>
              <strong>{turn.kind === 'opening' ? 'Opening' : `${turn.kind} ${turn.turn}`}</strong>
              <span class="faint"> · {turn.model || '—'} · {fmt(turn.usage.input_tokens)} in / {fmt(turn.usage.output_tokens)} out</span>
            </summary>
            <div class="entry-body">
              {#if turn.action}<p><span class="label">Action</span> {turn.action}</p>{/if}
              {#if turn.narrative_lens}
                <p><span class="label">Creative texture</span> {turn.narrative_lens}</p>
              {/if}
              <div class="prose">{turn.narration}</div>
              {#if turn.rolls.length}
                <h4>Rolls</h4>
                <ul class="plain">
                  {#each turn.rolls as roll}
                    <li class="mono small">
                      {roll.label}{#if roll.attribute} · {roll.attribute}{#if roll.skill} + {roll.skill}{/if}{/if}:
                      {roll.dice[0]}+{roll.dice[1]}{roll.modifier >= 0 ? '+' : ''}{roll.modifier}
                      = {roll.total} vs {roll.difficulty} · {roll.outcome}
                    </li>
                  {/each}
                </ul>
              {/if}
              {#if turn.changes.length}
                <h4>Changes</h4>
                <ul class="plain">
                  {#each turn.changes as change}<li class="small">{change}</li>{/each}
                </ul>
              {/if}
              <p class="faint small">
                World time {turn.world_time_before} → {turn.world_time_after} ·
                {turn.usage.estimated_usd > 0 ? `$${turn.usage.estimated_usd.toFixed(4)}` : 'unpriced'}
              </p>
            </div>
          </details>
        {/each}
      {/if}
    </div>
  {/if}
</Modal>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin-bottom: 0.8rem;
    flex-wrap: wrap;
  }

  .tabs {
    display: flex;
    gap: 0.2rem;
    overflow-x: auto;
    border-bottom: 1px solid var(--line);
    margin-bottom: 1rem;
  }

  .tabs button {
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
    color: var(--muted);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.6rem 0.65rem;
    white-space: nowrap;
  }

  .tabs button.active {
    color: var(--ink);
    border-bottom-color: var(--accent);
  }

  .content {
    padding-bottom: 1rem;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.7rem;
    margin-bottom: 1.2rem;
  }

  .grid > div,
  .attributes > div {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 0.55rem 0.7rem;
  }

  .label {
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }

  h3 {
    margin: 0 0 0.2rem;
    font-size: 1.4rem;
  }

  h4 {
    margin: 1.1rem 0 0.4rem;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent);
  }

  .attributes {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.4rem;
    margin: 0.8rem 0;
  }

  .track-row {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin: 0.6rem 0;
    color: var(--muted);
    font-size: 0.86rem;
  }

  .plain {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .plain > li {
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--line);
  }

  .entry {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    margin-bottom: 0.6rem;
    background: var(--panel-2);
  }

  .entry summary {
    cursor: pointer;
  }

  .entry-head {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    flex-wrap: wrap;
  }

  .entry-body {
    margin-top: 0.6rem;
    font-size: 0.88rem;
  }

  .entry-body p {
    margin: 0.35rem 0;
  }

  .badge {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border: 1px solid var(--line);
    border-radius: 99px;
    padding: 0.05rem 0.4rem;
    color: var(--muted);
  }

  .badge.gm {
    color: var(--danger);
    border-color: rgba(212, 114, 94, 0.45);
  }

  .badge.player {
    color: var(--good);
    border-color: rgba(127, 176, 131, 0.35);
  }

  .mono {
    font-family: var(--mono);
  }

  .small {
    font-size: 0.8rem;
  }

  pre {
    font-family: var(--mono);
    font-size: 0.76rem;
    white-space: pre-wrap;
    background: #14110e;
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 0.7rem;
    color: #cbbdaa;
    max-height: 320px;
    overflow: auto;
  }

  .journal {
    max-height: 60vh;
  }

  .prose {
    white-space: pre-wrap;
    line-height: 1.65;
  }

  .pips {
    display: flex;
    gap: 0.3rem;
    margin: 0.5rem 0;
  }

  .pip {
    flex: 1;
    height: 7px;
    border-radius: 2px;
    background: #2c2621;
    border: 1px solid var(--line);
  }

  .pip.filled {
    background: var(--accent);
    border-color: var(--accent);
  }

  @media (max-width: 620px) {
    .attributes {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
