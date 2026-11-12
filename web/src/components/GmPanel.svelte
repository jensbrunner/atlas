<script lang="ts">
  import { onMount } from 'svelte'
  import { getGm, type GmView } from '../lib/api'
  import Modal from './Modal.svelte'

  let { campaignId, onClose }: { campaignId: string; onClose: () => void } = $props()

  let view = $state<GmView | null>(null)
  let error = $state<string | null>(null)

  onMount(async () => {
    try {
      view = await getGm(campaignId)
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc)
    }
  })
</script>

<Modal title="GM view — secrets included" onClose={onClose}>
  {#if error}
    <p class="error">{error}</p>
  {:else if !view}
    <p class="muted">Loading the hidden side of the campaign…</p>
  {:else}
    <div class="gm">
      <section>
        <h3>Campaign notes</h3>
        <p class="prose">{view.gm.campaign_notes || '—'}</p>
        {#if view.gm.character_notes}
          <h4>Character notes</h4>
          <p class="prose">{view.gm.character_notes}</p>
        {/if}
        {#if view.gm.world_notes}
          <h4>World notes</h4>
          <p class="prose">{view.gm.world_notes}</p>
        {/if}
        {#if view.gm.world_gm_blocks}
          <h4>World secrets</h4>
          <pre>{view.gm.world_gm_blocks}</pre>
        {/if}
      </section>

      <section>
        <h3>Facts</h3>
        <ul class="plain">
          {#each view.gm.facts as fact (fact.id)}
            <li>
              <span class="badge {fact.visibility}">{fact.visibility}</span>
              {fact.text}
              {#if fact.revealed_at_turn !== null}
                <span class="faint small">(revealed turn {fact.revealed_at_turn})</span>
              {/if}
            </li>
          {/each}
        </ul>
      </section>

      <section>
        <h3>NPCs</h3>
        {#each view.gm.npcs as npc (npc.id)}
          <div class="npc">
            <h4>{(npc.sheet as { name?: string }).name ?? npc.id} <span class="faint">({npc.id})</span></h4>
            <p class="small muted">
              Goals: {((npc.sheet as { goals?: string[] }).goals ?? []).join('; ') || 'none'}
            </p>
            <p class="small muted">
              Plans: {((npc.sheet as { plans?: string[] }).plans ?? []).join('; ') || 'none'}
            </p>
            <p class="small muted">
              Knows: {((npc.sheet as { knows?: string[] }).knows ?? []).join(', ') || 'nothing recorded'}
            </p>
            {#if npc.notes}
              <pre>{npc.notes}</pre>
            {/if}
          </div>
        {/each}
      </section>

      <section>
        <h3>Factions</h3>
        <ul class="plain">
          {#each view.gm.factions as faction (faction.id)}
            <li>
              <strong>{faction.name}</strong>
              <span class="badge {faction.player_known ? 'player' : 'gm'}">
                {faction.player_known ? 'known' : 'hidden'}
              </span>
              <div class="small muted">Stance: {faction.stance || 'none'}</div>
              <div class="small muted">Goal: {faction.goal || 'none'}</div>
              {#if Object.keys(faction.resources).length}
                <div class="faint small">
                  Resources: {Object.entries(faction.resources)
                    .map(([key, value]) => `${key} ${value}`)
                    .join(', ')}
                </div>
              {/if}
            </li>
          {/each}
        </ul>
      </section>

      <section>
        <h3>All clocks</h3>
        <ul class="plain">
          {#each view.gm.clocks as clock (clock.id)}
            <li>
              {clock.name} — {clock.filled}/{clock.segments}
              <span class="badge {clock.visibility}">{clock.visibility}</span>
              {#if clock.trigger}<div class="faint small">{clock.trigger}</div>{/if}
            </li>
          {/each}
        </ul>
      </section>

      <section>
        <h3>Raw journal</h3>
        <pre class="journal">{view.gm.journal_raw}</pre>
      </section>
    </div>
  {/if}
</Modal>

<style>
  .gm {
    display: grid;
    gap: 1.6rem;
  }

  h3 {
    margin: 0 0 0.5rem;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
  }

  h4 {
    margin: 1rem 0 0.3rem;
  }

  .plain {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .plain li {
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--line);
  }

  .badge {
    display: inline-block;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.05rem 0.4rem;
    border-radius: 99px;
    border: 1px solid var(--line);
    color: var(--muted);
    margin-right: 0.3rem;
  }

  .badge.gm {
    color: var(--danger);
    border-color: rgba(212, 114, 94, 0.5);
  }

  .npc {
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--line);
  }

  .small {
    font-size: 0.82rem;
    margin: 0.15rem 0;
  }

  pre {
    font-family: var(--mono);
    font-size: 0.78rem;
    white-space: pre-wrap;
    background: #14110e;
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 0.7rem;
    color: #cbbdaa;
    max-height: 280px;
    overflow-y: auto;
  }

  .journal {
    max-height: 360px;
  }
</style>
